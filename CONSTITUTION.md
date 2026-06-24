# Constitution of fr-eli-mcp

Version: 0.1.0
Date: 2026-06-24
Licence: Apache-2.0

`fr-eli-mcp` is an MCP server for the French Legifrance API exposed through PISTE
(`piste.gouv.fr`). It searches consolidated legislation (LODA laws & decrees, codes) and case law
(JURI), returning verifiable citations. Unlike the keyless connectors in this line, Legifrance
requires OAuth2 credentials.

The 4 principles below are inherited from the `eu-legal-mcp` line Constitution (Article IV).

---

## Art. 1. Public data only

Legifrance is the official, public source of French law. The server is read-only against the
Legifrance API and sends nothing beyond the search query / document id it is asked for. The OAuth2
credentials authenticate the *application*, not an end user, and are read from the environment only
(`FR_ELI_CLIENT_ID` / `FR_ELI_CLIENT_SECRET`) - never hard-coded, never logged.

## Art. 2. Mandatory audit log

Every tool call MUST append one JSON line to `~/.matematic/audit/fr-eli-mcp.jsonl`
(ts / tool / input_hash SHA-256 / output_count_or_size / duration_ms / status). Inability to write =
the tool returns an error, it does not silently skip.

## Art. 3. Vendor neutrality

No tool hardcodes an LLM provider, assumes a model, or adds commercial telemetry. The server talks
only to the PISTE OAuth + Legifrance endpoints and the local filesystem. The OAuth token is cached
in process memory only (never persisted to disk) and refreshed on expiry or on a 401.

## Art. 4. ELI / ECLI citations and a human-readable citation are mandatory

Every response MUST carry the citation contract:
- `eli_uri`: a **stable, resolvable Legifrance resource URL**. The PISTE `lf-engine-app` consult
  API returns the native `eli` / `idEli` fields *null* for legislation, so we DO NOT synthesize a
  `/eli/...` string from prose - we carry the CID-keyed legifrance.gouv.fr URL that resolves, and we
  say so (`eli_note`). Rule of the line: **state what you do not have; never fabricate an ELI.**
- `human_readable_citation`: the French citation convention (e.g. "LOI n° 2016-1321 du 7 octobre
  2016 pour une République numérique"; "Code civil, art. 9"; the JURI title for a decision).
- `source_url`: the legifrance.gouv.fr page for the item.
- For case law, `ecli` carries the **native, authoritative ECLI** returned by the API
  (e.g. `ECLI:FR:CCASS:2025:C100399`) - cited verbatim, never invented.

---

## Open points

1. **ELI** - if/when the PISTE API (or a dedicated ELI endpoint) exposes a populated native ELI for
   legislation, `eli_uri` should switch to it. Until then it is the resolvable CID-keyed URL.
2. **Distribution** - Legifrance requires a PISTE key, so this connector ships via the PATRON /
   appliance channel (governed), not casual drop-in download (see the line's distribution note).
3. **Sandbox vs production** - the defaults target the PISTE *sandbox*. Production uses the
   `oauth.piste.gouv.fr` / `api.piste.gouv.fr` hosts (set via `FR_ELI_OAUTH_URL` / `FR_ELI_BASE_URL`).
4. **Coverage** - MVP covers LODA + codes + JURI consult. Other fonds (JORF, CETAT, CONSTIT, KALI)
   are later features.

## Constitution evolution

Changes to art. 1-4 follow SEMVER + an entry in `CHANGELOG.md` + a `pyproject.toml` bump.

First version: 2026-06-24. Author: Wieslaw Mazur / MateMatic.
