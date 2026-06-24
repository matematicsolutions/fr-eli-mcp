"""FastMCP entry point - French Legifrance (PISTE) legislation + case-law tools.

Run:

    python -m fr_eli_mcp.server

Configuration via env (PISTE OAuth2 - credentials are required, never hard-coded):

- ``FR_ELI_OAUTH_URL``     (default sandbox OAuth token endpoint)
- ``FR_ELI_BASE_URL``      (default sandbox lf-engine-app base)
- ``FR_ELI_CLIENT_ID``     (from your piste.gouv.fr application - REQUIRED)
- ``FR_ELI_CLIENT_SECRET`` (section "OAuth Credentials" - REQUIRED)
- ``FR_ELI_CACHE_DIR``     (default ``~/.matematic/cache/fr-eli``)
- ``FR_ELI_AUDIT_DIR``     (default ``~/.matematic/audit``)
"""

from __future__ import annotations

import time

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import citations
from .audit import AuditLogger, hash_input, timer
from .client import CredentialsError, LegifranceClient
from .models import Act, ArticleText, Decision, SearchResult

INSTRUCTIONS = """\
This MCP server exposes the French Legifrance API through PISTE (piste.gouv.fr). It covers consolidated legislation (LODA laws & decrees, and codes) and case law (JURI). Every response carries the citation contract: a stable `eli_uri`, a `human_readable_citation` (French convention) and a `source_url` (a resolvable legifrance.gouv.fr page).

## Call order

1. `fr_search` - keyword search a `fond` (`LODA` laws/decrees, `CODE` codes, `JURI` case law). Each hit carries `id`, `title`, `human_readable_citation`, `source_url`. For `CODE` hits, matched `articles` carry their `article_id`.
2. `fr_get_act` - consult a LODA law/decree by its `text_id` (a `LEGITEXT...` id). Returns metadata, citation and a table of contents (`articles` with their `article_id` + `num`).
3. `fr_get_text` - the verbatim text of a single article by `article_id` (a `LEGIARTI...` id).
4. `fr_get_decision` - a JURI court decision by `decision_id` (a `JURITEXT...` id). Returns the native `ecli`, court, formation, solution and the decision text.

## Hard constraints

- **ELI on Legifrance:** the PISTE consult API returns the native ELI field *null* for legislation. `eli_uri` therefore carries the stable resolvable Legifrance resource URL - it is NOT a fabricated `/eli/...` string. Read `eli_note` and relay it; never invent an ELI.
- **ECLI is real for case law** - `fr_get_decision` returns a native authoritative `ecli` (e.g. `ECLI:FR:CCASS:2025:C100399`). Cite it verbatim.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user.
- **No modification of official text** - articles and decisions are returned verbatim from Legifrance.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/fr-eli-mcp.jsonl`.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing, malformed, or an id has the wrong prefix.
- `not_found` - no act / article / decision exists for that id, or a search returned nothing.
- `upstream_error` - a Legifrance / PISTE API error (HTTP, timeout, OAuth rejection). Retry once before surfacing.
- `config_error` - PISTE credentials are not configured (FR_ELI_CLIENT_ID / FR_ELI_CLIENT_SECRET).

## Response style

- Cite legislation as `human_readable_citation` with the `source_url`: "LOI n 2016-1321 du 7 octobre 2016, https://www.legifrance.gouv.fr/loda/id/LEGITEXT000033205014".
- Cite case law with its `ecli` and `source_url`.
- NEVER invent an id, an ELI, an ECLI or a citation - take each from the tool output.
"""


class ToolError(Exception):
    """Structured error for fr-eli MCP tools - visible to the LLM with a [code] prefix."""

    VALID_CODES = frozenset({"invalid_arg", "not_found", "upstream_error", "config_error"})

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown ToolError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,
)

mcp: FastMCP = FastMCP(name="fr-eli-mcp", instructions=INSTRUCTIONS)

# User-facing fond -> API fond.
_FOND_MAP = {"LODA": "LODA_DATE", "CODE": "CODE_DATE", "JURI": "JURI"}


def _audit() -> AuditLogger:
    return AuditLogger()


def _map_upstream(exc: Exception) -> Exception:
    if isinstance(exc, CredentialsError):
        return ToolError("config_error", str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 404:
            return ToolError("not_found", "Legifrance returned 404 for that resource.")
        return ToolError(
            "upstream_error",
            f"Legifrance/PISTE HTTP {exc.response.status_code}: {exc}",
        )
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"Legifrance/PISTE error: {type(exc).__name__}: {exc}")
    return exc


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _now_ms() -> int:
    return int(time.time() * 1000)


def _build_search_payload(query: str, api_fond: str, page_size: int) -> dict[str, object]:
    filtres: list[dict[str, object]] = []
    if api_fond in ("LODA_DATE", "CODE_DATE"):
        filtres.append({"facette": "DATE_VERSION", "singleDate": _now_ms()})
    return {
        "fond": api_fond,
        "recherche": {
            "champs": [
                {
                    "typeChamp": "ALL",
                    "criteres": [
                        {"typeRecherche": "UN_DES_MOTS", "valeur": query, "operateur": "ET"}
                    ],
                    "operateur": "ET",
                }
            ],
            "filtres": filtres,
            "pageNumber": 1,
            "pageSize": page_size,
            "operateur": "ET",
            "sort": "PERTINENCE",
            "typePagination": "DEFAUT",
        },
    }


def _require_prefix(value: str, prefix: str, label: str) -> None:
    if not value or not value.strip():
        raise ToolError("invalid_arg", f"{label} is required.")
    if not value.startswith(prefix):
        raise ToolError(
            "invalid_arg", f"{label}={value!r} must be a Legifrance {prefix}... identifier."
        )


# ---------------------------------------------------------------------------
# fr_search
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def fr_search(query: str, fond: str = "LODA", page_size: int = 10) -> SearchResult:
    """Keyword-search French legislation or case law on Legifrance.

    Args:
        query: free-text query (e.g. "republique numerique", "responsabilite").
        fond: one of ``LODA`` (laws & decrees), ``CODE`` (codes), ``JURI`` (case law).
        page_size: number of hits (1..100).

    Returns:
        ``SearchResult`` with ``hits``, each carrying the citation contract.
    """
    audit = _audit()
    fond_key = (fond or "").strip().upper()
    if fond_key not in _FOND_MAP:
        raise ToolError("invalid_arg", f"fond={fond!r} must be one of {sorted(_FOND_MAP)}.")
    if not query or not query.strip():
        raise ToolError("invalid_arg", "query is required.")
    if not 1 <= page_size <= 100:
        raise ToolError("invalid_arg", f"page_size={page_size} out of range (1..100).")

    api_fond = _FOND_MAP[fond_key]
    payload = _build_search_payload(query.strip(), api_fond, page_size)
    input_hash = hash_input({"query": query, "fond": fond_key, "page_size": page_size})

    with timer() as t:
        try:
            async with LegifranceClient() as client:
                raw = await client.search(payload)
        except Exception as exc:
            audit.log(tool="fr_search", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms or 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    norm = citations.normalize_search(raw, api_fond)
    result = SearchResult(
        fond=fond_key,
        query=query.strip(),
        total=norm["total"],
        hits=norm["hits"],
    )
    audit.log(tool="fr_search", input_hash=input_hash, output_count_or_size=len(result.hits),
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# fr_get_act
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def fr_get_act(text_id: str, date: str | None = None) -> Act:
    """Consult a LODA law or decree by its ``LEGITEXT...`` id.

    Args:
        text_id: a ``LEGITEXT...`` identifier (from ``fr_search`` on fond ``LODA``).
        date: version date ``YYYY-MM-DD`` (default: today - the version in force now).

    Returns:
        ``Act`` with metadata, citation and a table of contents (``articles``).
    """
    audit = _audit()
    _require_prefix(text_id, "LEGITEXT", "text_id")
    version_date = (date or _today()).strip()
    input_hash = hash_input({"text_id": text_id, "date": version_date})

    with timer() as t:
        try:
            async with LegifranceClient() as client:
                raw = await client.consult_law_decree(text_id, version_date)
        except Exception as exc:
            audit.log(tool="fr_get_act", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms or 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    norm = citations.normalize_law_decree(raw)
    if norm is None:
        raise ToolError("not_found", f"No LODA text found for {text_id}.")
    result = Act.model_validate(norm)
    audit.log(tool="fr_get_act", input_hash=input_hash, output_count_or_size=len(result.articles),
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# fr_get_text
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def fr_get_text(article_id: str) -> ArticleText:
    """Fetch the verbatim text of a single article by its ``LEGIARTI...`` id.

    Args:
        article_id: a ``LEGIARTI...`` identifier (from ``fr_get_act`` or a ``CODE`` search hit).

    Returns:
        ``ArticleText`` with the article ``text``, citation and ``source_url``.
    """
    audit = _audit()
    _require_prefix(article_id, "LEGIARTI", "article_id")
    input_hash = hash_input({"article_id": article_id})

    with timer() as t:
        try:
            async with LegifranceClient() as client:
                raw = await client.consult_article(article_id)
        except Exception as exc:
            audit.log(tool="fr_get_text", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms or 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    norm = citations.normalize_article(raw)
    if norm is None:
        raise ToolError("not_found", f"No article found for {article_id}.")
    text = norm.get("text") or ""
    norm["byte_size"] = len(text.encode("utf-8"))
    result = ArticleText.model_validate(norm)
    audit.log(tool="fr_get_text", input_hash=input_hash, output_count_or_size=result.byte_size or 0,
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# fr_get_decision
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def fr_get_decision(decision_id: str) -> Decision:
    """Consult a JURI court decision by its ``JURITEXT...`` id (returns the native ECLI).

    Args:
        decision_id: a ``JURITEXT...`` identifier (from ``fr_search`` on fond ``JURI``).

    Returns:
        ``Decision`` with ``ecli``, court, formation, solution and the decision ``text``.
    """
    audit = _audit()
    _require_prefix(decision_id, "JURITEXT", "decision_id")
    input_hash = hash_input({"decision_id": decision_id})

    with timer() as t:
        try:
            async with LegifranceClient() as client:
                raw = await client.consult_juri(decision_id)
        except Exception as exc:
            audit.log(tool="fr_get_decision", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms or 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    norm = citations.normalize_juri(raw)
    if norm is None:
        raise ToolError("not_found", f"No JURI decision found for {decision_id}.")
    text = norm.get("text") or ""
    norm["byte_size"] = len(text.encode("utf-8"))
    result = Decision.model_validate(norm)
    audit.log(tool="fr_get_decision", input_hash=input_hash, output_count_or_size=result.byte_size or 0,
              duration_ms=t.duration_ms, status="ok")
    return result


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
