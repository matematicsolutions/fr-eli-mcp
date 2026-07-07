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

## Update 2026-07-07 - Conseil constitutionnel + administrative courts (v0.2.0)

Audit against Legal Data Hunter (`worldwidelaw/legal-sources` manifest, `status: complete`) flagged
two French judicial gaps not covered by v0.1.0: `FR/ConseilConstitutionnel` and `FR/CouncilState`
(Conseil d'Etat, CAA, TA). A third candidate, `FR/Judilibre`, was also evaluated.

**Probed live on the same PISTE sandbox credentials already held by this connector** (no new
subscription):

- `POST /search {fond: "CONSTIT"}` - **200 OK**, 7 372 Conseil constitutionnel decisions indexed
  (QPC + DC + LP + RIP), native facets for `NATURE_CONSTIT` / `SOLUTION_CONSTIT`. Hit ids are
  `CONSTEXT...`.
- `POST /search {fond: "CETAT"}` - **200 OK**, 569 270 administrative decisions (Conseil d'Etat +
  CAA + TA + Tribunal des conflits), facet `JURIDICTION_NATURE` confirms all three court tiers.
  Hit ids are `CETATEXT...`.
- `POST /consult/juri {textId: "CONSTEXT..."}` and `{textId: "CETATEXT..."}` - **both 200 OK on the
  existing generic endpoint**, no new consult route needed. Both return a native `ecli`
  (`ECLI:FR:CC:...` for Conseil constitutionnel; `ECLI:FR:CECHR:...` for Conseil d'Etat). CAA/TA
  decisions frequently have `ecli: null` (confirmed live - a CAA de Marseille hit had no ECLI while
  a same-page Conseil d'Etat hit did) - never fabricated, left `None`.
- **Web URL patterns verified independently** (WebSearch, since direct `httpx` GETs to
  `legifrance.gouv.fr` 403 from this environment regardless of path - a general bot-block, not
  path-specific): `https://www.legifrance.gouv.fr/cons/id/CONSTEXT...` and
  `.../ceta/id/CETATEXT...` both resolve to real decision pages in third-party search results and
  WebFetch. (Guessed `/constit/id/...` first - wrong; confirmed via search before shipping, per the
  "never fabricate a citation path" rule.)
- **Judilibre** (`api.piste.gouv.fr/cassation/judilibre`) - `403 Forbidden` on the sandbox
  `/healthcheck` even with a valid Legifrance bearer token -> requires its **own** PISTE API
  subscription, separate from the Legifrance one. Not integrated this round; `JURI` already covers
  Cour de cassation case law via the existing subscription, so this isn't a hard gap, just a
  possible future upgrade path (better structuring, per LDH's `preferred_for: caselaw`).

**Decision: extend, not fork.** Both new fonds route through the *existing* `_FOND_MAP` /
`consult_juri` / `normalize_juri` machinery in `citations.py` + `server.py` - the only genuinely
new logic is a French-convention citation builder for Conseil constitutionnel
(`Cons. const., decision n° NNNN-NNN QPC du D mois AAAA - [case]`) and the `cons`/`ceta` URL kinds
in `legifrance_url()`. `fr_get_decision` now accepts `JURITEXT...` / `CONSTEXT...` / `CETATEXT...`
ids uniformly. No new client module, no new credentials, no new dependency.
