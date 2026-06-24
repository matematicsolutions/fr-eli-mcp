# fr-eli-mcp

An MCP server for the **French Legifrance API** via [PISTE](https://piste.gouv.fr) — search
French legislation (LODA laws & decrees, codes) and case law (JURI), and fetch verbatim text with
verifiable citations. Part of the **eu-legal-mcp** line of national legal connectors by
[MateMatic](https://matematic.co).

Every response carries the citation contract: a stable `eli_uri`, a `human_readable_citation`
(French convention) and a resolvable `source_url`. Court decisions additionally carry a **native
ECLI**.

> **Read-only.** The server only queries Legifrance and writes a local audit log. It never modifies
> official text and never sends anything beyond your query / document id.

## Tools

| Tool | What it does |
| --- | --- |
| `fr_search(query, fond, page_size)` | Keyword search a `fond`: `LODA` (laws & decrees), `CODE` (codes), `JURI` (case law). Returns hits with the citation contract; `CODE` hits expose matched `article_id`s. |
| `fr_get_act(text_id, date)` | Consult a LODA law/decree by `LEGITEXT...` id. Returns metadata + a table of contents (`articles`). |
| `fr_get_text(article_id)` | Verbatim text of a single article by `LEGIARTI...` id. |
| `fr_get_decision(decision_id)` | A JURI court decision by `JURITEXT...` id, with its **native `ecli`**, court, formation, solution and text. |

### A note on ELI vs ECLI

France has an official ELI scheme, but the PISTE `lf-engine-app` **consult API returns the native
ELI field `null` for the legislation we tested**. Following this line's rule — *say what you do not
have, never fabricate an ELI* — `eli_uri` carries the **stable, resolvable Legifrance resource URL**
(CID-keyed), not a `/eli/...` string parsed from prose. Each response repeats this in `eli_note`.

Case law is different: the API returns a **native, authoritative ECLI**
(e.g. `ECLI:FR:CCASS:2025:C100399`), surfaced verbatim in `fr_get_decision`.

## Configuration

Legifrance requires OAuth2 application credentials from a free PISTE account
(`piste.gouv.fr` → *Applications* → subscribe to the Legifrance API → *OAuth Credentials*).
Credentials are read from the environment only:

| Variable | Meaning |
| --- | --- |
| `FR_ELI_OAUTH_URL` | OAuth token endpoint (sandbox default shown in `.mcp.json.example`). |
| `FR_ELI_BASE_URL` | Legifrance `lf-engine-app` base. |
| `FR_ELI_CLIENT_ID` | Your PISTE application client id (**required**). |
| `FR_ELI_CLIENT_SECRET` | Your PISTE application client secret (**required**). |
| `FR_ELI_CACHE_DIR` | Disk cache dir (default `~/.matematic/cache/fr-eli`). |
| `FR_ELI_AUDIT_DIR` | Audit log dir (default `~/.matematic/audit`). |

Copy `.mcp.json.example` to `.mcp.json` (gitignored) and fill in your credentials, or set the
variables in your host environment. The OAuth token is cached in memory and refreshed automatically.

## Install

```bash
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"   # Windows
# or: python -m pip install -e ".[dev]"                  # POSIX
```

## Tests

```bash
pytest tests/test_instructions_drift.py tests/test_parse.py   # offline, no creds
pytest tests/test_smoke.py -v                                 # live, needs PISTE creds in .env
```

## Distribution

Because Legifrance requires a PISTE key, this connector is distributed through the **PATRON /
appliance** channel (governed), not casual drop-in download. See the eu-legal-mcp line notes.

## Licence

Apache-2.0. Legifrance content is © the French Republic / DILA and subject to the Legifrance /
PISTE terms of use; this software only retrieves and cites it.
