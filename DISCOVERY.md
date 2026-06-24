# Discovery - fr-eli-mcp (Legifrance via PISTE)

Date: 2026-06-24. Decision: **BUILD** (sandbox fully working: token + subscription + live data).

## Source

- **API:** Legifrance, exposed through PISTE (`piste.gouv.fr`). Base (sandbox):
  `https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app`.
- **Auth:** OAuth2 `client_credentials`. Token endpoint (sandbox):
  `https://sandbox-oauth.piste.gouv.fr/api/oauth/token`. Body params
  `grant_type=client_credentials` + `client_id` + `client_secret` + `scope=openid` →
  `access_token` (`token_type=Bearer`, `expires_in=3600`, scope `openid resource.READ`).
- **Production:** swap the sandbox hosts for `oauth.piste.gouv.fr` / `api.piste.gouv.fr`.

Registration (account + API subscription + ToS acceptance) is a one-time human act on the PISTE
portal; it was completed before this build. The connector itself is fully autonomous thereafter.

## Probed live (not trusted from docs)

All endpoints are `POST` JSON under the base, with a `Bearer` token.

- `POST /search` - `{fond, recherche:{champs[…], filtres[…], pageNumber, pageSize, operateur, sort,
  typePagination}}`. Verified for `fond` ∈ {`LODA_DATE`, `CODE_DATE`, `JURI`}. `LODA_DATE` /
  `CODE_DATE` require a `DATE_VERSION` `singleDate` (epoch ms) filter. Results:
  `results[].titles[]{id, cid, title}` + `nature` / `origin` / `etat`; `CODE_DATE` results also
  carry `sections[].extracts[]{id (LEGIARTI…), num, values}`.
- `POST /consult/lawDecree` - `{textId (LEGITEXT…), date (YYYY-MM-DD)}` → full LODA text with
  `id`, `cid` (JORFTEXT…), `title`, `nor`, `nature`, `dateParution`, nested `sections[].articles[]`.
- `POST /consult/getArticle` - `{id (LEGIARTI…)}` → `article{id, num, texte, etat, dateDebut,
  textTitles[] (carries the code title, e.g. "Code civil"), fullSectionsTitre}`.
- `POST /consult/juri` - `{textId (JURITEXT…)}` → `text{id, ecli, juridiction, formation, solution,
  numeroAffaire, dateTexte, titre, texte}`.

### Key finding - ELI is null, ECLI is native

For LODA texts and code articles the API returns `eli` / `idEli` / `idEliAlias` **null**, and there
are no `/eli/…` strings anywhere in the consult payloads. The act number ("2016-1321") and signature
date are only present inside the `title` prose string (`textNumber` / `dateTexte` are null on the
LODA consult). Per the line rule we therefore do **not** fabricate a `/eli/…` URI from prose; we
carry the stable, resolvable CID-keyed legifrance.gouv.fr URL as `eli_uri`.

JURI is different: `text.ecli` is a populated, authoritative ECLI (e.g. `ECLI:FR:CCASS:2025:C100399`).
This makes `fr-eli-mcp` the first connector in the line to surface a native ECLI straight from the
source API.

## Citation contract mapping

| Field | LODA / code article | JURI |
| --- | --- | --- |
| `eli_uri` | `https://www.legifrance.gouv.fr/loda/id/{LEGITEXT}` / `…/codes/article_lc/{LEGIARTI}` (resolvable, CID-keyed; **not** a native ELI) | `https://www.legifrance.gouv.fr/juri/id/{JURITEXT}` |
| `human_readable_citation` | the `title` prose ("LOI n° … du …") / "Code civil, art. 9" | the decision `titre` |
| `source_url` | same legifrance.gouv.fr page | same |
| `ecli` | - | native `text.ecli` |

## Build

3 reuse-verbatim modules (`audit.py`, `cache.py` - env `FR_ELI_*`, log `fr-eli-mcp.jsonl`), and the
FR-specific `client.py` (OAuth2 + in-memory token cache + 401 refresh + POST JSON), `citations.py`,
`models.py`, `server.py` (4 tools, `ToolError` {invalid_arg / not_found / upstream_error /
config_error}). Tests: offline drift + offline fixture parse + live smoke. The factory holds: the
infrastructure is reused, only the source adapter is new.
