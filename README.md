# fr-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/fr-eli-mcp -->


## Install (one command)

Published on PyPI + MCP Registry (`io.github.matematicsolutions/fr-eli-mcp`). Run without cloning:

```bash
uvx fr-eli-mcp
```

Requires PISTE credentials in env: `PISTE_CLIENT_ID`, `PISTE_CLIENT_SECRET` (Legifrance/PISTE).

Configure your MCP client (stdio):

```json
{ "mcpServers": { "fr-eli-mcp": { "command": "uvx", "args": ["fr-eli-mcp"] } } }
```

### Windows 11 with Smart App Control

Smart App Control blocks unsigned executables, which covers `uvx.exe`, `pip.exe`
and the `fr-eli-mcp.exe` launcher that pip writes at install time. The `python.exe` and
`py.exe` from the python.org installer are signed by the Python Software
Foundation, so running the module through the interpreter works:

```bash
python -m pip install fr-eli-mcp
python -m fr_eli_mcp
```

`pip.exe` is blocked for the same reason, so install with `python -m pip`, not
`pip install`. If `python` is not on PATH, use the Windows launcher: `py -3 -m fr_eli_mcp`.

```json
{ "mcpServers": { "fr-eli-mcp": { "command": "python", "args": ["-m", "fr_eli_mcp"] } } }
```

Do not turn Smart App Control off to work around this - it cannot be re-enabled
without reinstalling Windows.

Building from source: see [Install](#install).

An MCP server for the **French Legifrance API** via [PISTE](https://piste.gouv.fr). It searches
French legislation (LODA laws & decrees, codes), case law from three jurisdictions - Cour de
cassation / cours d'appel (JURI), the **Conseil constitutionnel** (CONSTIT - QPC/DC decisions) and
the **administrative courts** (CETAT - Conseil d'Etat, cours administratives d'appel, tribunaux
administratifs) - plus **CNIL deliberations** (CNIL), **collective labour agreements** (KALI) and
**company-level agreements** (ACCO), and returns verbatim text with verifiable citations. Part of
the **eu-legal-mcp** line of national legal connectors by [MateMatic](https://matematic.co).

Every response carries the citation contract: a stable `eli_uri`, a `human_readable_citation`
(French convention) and a resolvable `source_url`.

> **Read-only.** The server only queries Legifrance and writes a local audit log. It never modifies
> official text and never sends anything beyond your query / document id.

## Tools

| Tool | What it does |
| --- | --- |
| `fr_search(query, fond, page_size)` | Keyword search a `fond`: `LODA` (laws & decrees), `CODE` (codes), `JURI` (Cour de cassation case law), `CONSTIT` (Conseil constitutionnel decisions), `CETAT` (administrative case law: Conseil d'Etat, CAA, TA), `CNIL` (CNIL deliberations), `KALI` (collective labour agreements), `ACCO` (company-level agreements). Returns hits with the citation contract; `CODE` hits expose matched `article_id`s. |
| `fr_get_act(text_id, date)` | Consult a LODA law/decree by `LEGITEXT...` id. Returns metadata + a table of contents (`articles`). |
| `fr_get_text(article_id)` | Verbatim text of a single article by `LEGIARTI...` id (legislation/codes) or `KALIARTI...` id (collective agreements). |
| `fr_get_decision(decision_id)` | A court decision by `JURITEXT...`, `CONSTEXT...` or `CETATEXT...` id, with its **native `ecli`** (when populated), court, formation, solution and text. |
| `fr_get_deliberation(deliberation_id)` | A CNIL deliberation by `CNILTEXT...` id (sanctions, authorizations, opinions) with its verbatim text and the citation `CNIL, deliberation n° ... du ...`. |
| `fr_get_convention(convention_id)` | A collective labour agreement text by `KALITEXT...` id. Returns metadata + a table of contents whose `KALIARTI...` ids resolve via `fr_get_text`. |
| `fr_get_company_agreement(agreement_id)` | A company-level agreement by `ACCOTEXT...` id - **metadata only** (company, SIRET, IDCC, sector, themes, unions, dates). Legifrance ships the full ACCO text only as a `.docx` attachment, so the tool cites `source_url` instead of re-serving it. |

### Fonds covered (live totals, sandbox, 2026-07-08)

| Fond | Corpus | Verified total |
| --- | --- | --- |
| `CNIL` | CNIL deliberations | >= 26 759 (`totalResultNumber` on a broad stopword query) |
| `KALI` | Collective labour agreements (conventions collectives) | >= 35 790 |
| `ACCO` | Company-level agreements | >= 387 656 |

### Jurisdictions covered

| Fond | Court(s) | Id prefix | Native ECLI |
| --- | --- | --- | --- |
| `JURI` | Cour de cassation, cours d'appel | `JURITEXT...` | Yes |
| `CONSTIT` | Conseil constitutionnel (QPC + DC decisions, ~7 400+ live on PISTE) | `CONSTEXT...` | Yes (`ECLI:FR:CC:...`) |
| `CETAT` | Conseil d'Etat, cours administratives d'appel (CAA), tribunaux administratifs (TA) | `CETATEXT...` | Yes for Conseil d'Etat; frequently `null` for CAA/TA (uneven ECLI coverage upstream - never fabricated) |

Conseil constitutionnel decisions get the French citation convention: `Cons. const., decision n°
2025-1173 QPC du 7 novembre 2025 - [case name]`. JURI/CETAT decisions cite the Legifrance `titre`
(court, formation, date, dossier number) verbatim.

> **Judilibre** (`api.piste.gouv.fr/cassation/judilibre`) was evaluated as an alternative Cour de
> cassation source but requires its own PISTE API subscription beyond the Legifrance one already
> held by this connector. Re-verified 2026-07-08: a valid Legifrance token (granted scope
> `openid resource.READ`) gets `403` on the sandbox host for every endpoint and auth shape tried
> (`Bearer`, `KeyId`, no-auth -> `400`), and the sandbox application is rejected outright by the
> production OAuth endpoint (`invalid_client`). Subscribing the Judilibre API to the PISTE
> application is a dashboard action outside this connector. Not integrated - `JURI` already covers
> Cour de cassation case law through the existing Legifrance subscription.

### A note on ELI vs ECLI

France has an official ELI scheme, but the PISTE `lf-engine-app` **consult API returns the native
ELI field `null` for the legislation we tested**. Following this line's rule - *say what you do not
have, never fabricate an ELI* - `eli_uri` carries the **stable, resolvable Legifrance resource URL**
(CID-keyed), not a `/eli/...` string parsed from prose. Each response repeats this in `eli_note`.

Case law is different: the API returns a **native, authoritative ECLI** for Cour de cassation (e.g.
`ECLI:FR:CCASS:2025:C100399`), Conseil constitutionnel (e.g. `ECLI:FR:CC:2025:2025.1173.QPC`) and
Conseil d'Etat (e.g. `ECLI:FR:CECHR:2026:506507.20260529`), surfaced verbatim in `fr_get_decision`.
CAA/TA decisions under `CETAT` frequently have no ECLI - the field is `null`, never fabricated.

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
