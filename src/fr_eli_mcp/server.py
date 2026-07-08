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
from .models import Act, ArticleText, CompanyAgreement, Decision, Deliberation, SearchResult

INSTRUCTIONS = """\
This MCP server exposes the French Legifrance API through PISTE (piste.gouv.fr). It covers consolidated legislation (LODA laws & decrees, and codes), case law from three jurisdictions - Cour de cassation / cours d'appel (JURI), the Conseil constitutionnel (CONSTIT - QPC/DC decisions), and the administrative courts (CETAT - Conseil d'Etat, cours administratives d'appel, tribunaux administratifs) - plus CNIL deliberations (CNIL), collective labour agreements (KALI) and company-level agreements (ACCO). Every response carries the citation contract: a stable `eli_uri`, a `human_readable_citation` (French convention) and a `source_url` (a resolvable legifrance.gouv.fr page).

## Call order

1. `fr_search` - keyword search a `fond` (`LODA` laws/decrees, `CODE` codes, `JURI` Cour de cassation case law, `CONSTIT` Conseil constitutionnel decisions, `CETAT` administrative case law, `CNIL` CNIL deliberations, `KALI` collective labour agreements, `ACCO` company-level agreements). Each hit carries `id`, `title`, `human_readable_citation`, `source_url`. For `CODE` hits, matched `articles` carry their `article_id`.
2. `fr_get_act` - consult a LODA law/decree by its `text_id` (a `LEGITEXT...` id). Returns metadata, citation and a table of contents (`articles` with their `article_id` + `num`).
3. `fr_get_text` - the verbatim text of a single article by `article_id` (a `LEGIARTI...` id from legislation/codes, or a `KALIARTI...` id from a collective agreement's table of contents).
4. `fr_get_decision` - a court decision by `decision_id` (a `JURITEXT...`, `CONSTEXT...` or `CETATEXT...` id, from `fr_search` on fond `JURI`, `CONSTIT` or `CETAT`). Returns the native `ecli`, court, formation, solution and the decision text.
5. `fr_get_deliberation` - a CNIL deliberation by its `CNILTEXT...` id (from `fr_search` on fond `CNIL`). Returns the verbatim deliberation text.
6. `fr_get_convention` - a collective labour agreement text by its `KALITEXT...` id (from `fr_search` on fond `KALI`). Returns metadata and a table of contents whose `KALIARTI...` ids resolve via `fr_get_text`.
7. `fr_get_company_agreement` - a company-level agreement by its `ACCOTEXT...` id (from `fr_search` on fond `ACCO`). Returns METADATA ONLY (company, SIRET, IDCC, sector, themes, unions, dates) - Legifrance distributes the full text of ACCO agreements only as a .docx attachment; cite `source_url`.

## Hard constraints

- **ELI on Legifrance:** the PISTE consult API returns the native ELI field *null* for legislation. `eli_uri` therefore carries the stable resolvable Legifrance resource URL - it is NOT a fabricated `/eli/...` string. Read `eli_note` and relay it; never invent an ELI.
- **ECLI is real for case law, but not always populated** - `fr_get_decision` returns a native authoritative `ecli` for Cour de cassation (e.g. `ECLI:FR:CCASS:2025:C100399`), Conseil constitutionnel (e.g. `ECLI:FR:CC:2025:2025.1173.QPC`) and Conseil d'Etat (e.g. `ECLI:FR:CECHR:2026:506507.20260529`). Cite it verbatim when present. CAA/TA decisions under fond `CETAT` frequently have `ecli=null` - never fabricate one; cite `human_readable_citation` + `source_url` instead.
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

- Cite legislation as `human_readable_citation` with the `source_url`: "LOI n° 2016-1321 du 7 octobre 2016, https://www.legifrance.gouv.fr/loda/id/LEGITEXT000033205014".
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
_FOND_MAP = {
    "LODA": "LODA_DATE",
    "CODE": "CODE_DATE",
    "JURI": "JURI",
    "CONSTIT": "CONSTIT",
    "CETAT": "CETAT",
    "CNIL": "CNIL",
    "KALI": "KALI",
    "ACCO": "ACCO",
}

# decision_id prefix -> which fonds' consult/juri endpoint can resolve it.
_DECISION_PREFIXES = ("JURITEXT", "CONSTEXT", "CETATEXT")


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
        fond: one of ``LODA`` (laws & decrees), ``CODE`` (codes), ``JURI`` (Cour de cassation
            case law), ``CONSTIT`` (Conseil constitutionnel - QPC/DC decisions), ``CETAT``
            (administrative case law: Conseil d'Etat, cours administratives d'appel, tribunaux
            administratifs), ``CNIL`` (CNIL deliberations, incl. sanctions), ``KALI``
            (collective labour agreements / conventions collectives), ``ACCO`` (company-level
            agreements - metadata + search only).
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
    """Fetch the verbatim text of a single article (``LEGIARTI...`` or ``KALIARTI...``).

    Args:
        article_id: a ``LEGIARTI...`` identifier (from ``fr_get_act`` or a ``CODE`` search
            hit), or a ``KALIARTI...`` identifier (from ``fr_get_convention``).

    Returns:
        ``ArticleText`` with the article ``text``, citation and ``source_url``.
    """
    audit = _audit()
    if not article_id or not article_id.strip():
        raise ToolError("invalid_arg", "article_id is required.")
    if not article_id.startswith(("LEGIARTI", "KALIARTI")):
        raise ToolError(
            "invalid_arg",
            f"article_id={article_id!r} must be a Legifrance LEGIARTI... or "
            "KALIARTI... identifier.",
        )
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
    """Consult a court decision by its id (returns the native ECLI).

    Covers three jurisdictions via the same Legifrance ``consult/juri`` endpoint:

    - ``JURITEXT...`` - Cour de cassation / cours d'appel (fond ``JURI``).
    - ``CONSTEXT...`` - Conseil constitutionnel QPC/DC decisions (fond ``CONSTIT``).
    - ``CETATEXT...`` - Conseil d'Etat, CAA, TA administrative case law (fond ``CETAT``).

    Args:
        decision_id: a ``JURITEXT...``, ``CONSTEXT...`` or ``CETATEXT...`` identifier (from
            ``fr_search`` on fond ``JURI``, ``CONSTIT`` or ``CETAT`` respectively).

    Returns:
        ``Decision`` with ``ecli``, court, formation, solution and the decision ``text``.
    """
    audit = _audit()
    if not decision_id or not decision_id.strip():
        raise ToolError("invalid_arg", "decision_id is required.")
    if not decision_id.startswith(_DECISION_PREFIXES):
        raise ToolError(
            "invalid_arg",
            f"decision_id={decision_id!r} must start with one of {_DECISION_PREFIXES}.",
        )
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


# ---------------------------------------------------------------------------
# fr_get_deliberation (fond CNIL, feature-003)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def fr_get_deliberation(deliberation_id: str) -> Deliberation:
    """Consult a CNIL deliberation by its ``CNILTEXT...`` id.

    Args:
        deliberation_id: a ``CNILTEXT...`` identifier (from ``fr_search`` on fond ``CNIL``).

    Returns:
        ``Deliberation`` with the deliberation ``text``, nature (e.g. ``Sanction``),
        citation and ``source_url``. CNIL deliberations carry no ECLI/ELI - none is invented.
    """
    audit = _audit()
    _require_prefix(deliberation_id, "CNILTEXT", "deliberation_id")
    input_hash = hash_input({"deliberation_id": deliberation_id})

    with timer() as t:
        try:
            async with LegifranceClient() as client:
                raw = await client.consult_cnil(deliberation_id)
        except Exception as exc:
            audit.log(tool="fr_get_deliberation", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms or 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    norm = citations.normalize_cnil(raw)
    if norm is None:
        raise ToolError("not_found", f"No CNIL deliberation found for {deliberation_id}.")
    text = norm.get("text") or ""
    norm["byte_size"] = len(text.encode("utf-8"))
    result = Deliberation.model_validate(norm)
    audit.log(tool="fr_get_deliberation", input_hash=input_hash,
              output_count_or_size=result.byte_size or 0,
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# fr_get_convention (fond KALI, feature-003)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def fr_get_convention(convention_id: str) -> Act:
    """Consult a collective labour agreement text by its ``KALITEXT...`` id.

    Args:
        convention_id: a ``KALITEXT...`` identifier (from ``fr_search`` on fond ``KALI``).

    Returns:
        ``Act`` with metadata, citation and a table of contents whose ``KALIARTI...``
        ``article_id`` values resolve through ``fr_get_text``.
    """
    audit = _audit()
    _require_prefix(convention_id, "KALITEXT", "convention_id")
    input_hash = hash_input({"convention_id": convention_id})

    with timer() as t:
        try:
            async with LegifranceClient() as client:
                raw = await client.consult_kali_text(convention_id)
        except Exception as exc:
            audit.log(tool="fr_get_convention", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms or 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    norm = citations.normalize_kali(raw)
    if norm is None:
        raise ToolError("not_found", f"No collective agreement text found for {convention_id}.")
    result = Act.model_validate(norm)
    audit.log(tool="fr_get_convention", input_hash=input_hash,
              output_count_or_size=len(result.articles),
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# fr_get_company_agreement (fond ACCO, feature-003)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def fr_get_company_agreement(agreement_id: str) -> CompanyAgreement:
    """Consult a company-level agreement by its ``ACCOTEXT...`` id - METADATA ONLY.

    Legifrance distributes the full text of ACCO agreements only as a ``.docx``
    attachment, so this tool returns the agreement metadata (company, SIRET, IDCC,
    sector, themes, signatory unions, dates) plus the resolvable ``source_url``.

    Args:
        agreement_id: an ``ACCOTEXT...`` identifier (from ``fr_search`` on fond ``ACCO``).

    Returns:
        ``CompanyAgreement`` metadata with citation and ``source_url``.
    """
    audit = _audit()
    _require_prefix(agreement_id, "ACCOTEXT", "agreement_id")
    input_hash = hash_input({"agreement_id": agreement_id})

    with timer() as t:
        try:
            async with LegifranceClient() as client:
                raw = await client.consult_acco(agreement_id)
        except Exception as exc:
            audit.log(tool="fr_get_company_agreement", input_hash=input_hash,
                      output_count_or_size=0, duration_ms=t.duration_ms or 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    norm = citations.normalize_acco(raw)
    if norm is None:
        raise ToolError("not_found", f"No company agreement found for {agreement_id}.")
    result = CompanyAgreement.model_validate(norm)
    audit.log(tool="fr_get_company_agreement", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return result


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
