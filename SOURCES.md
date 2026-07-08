# Sources ledger - France (FR)

See `eu-legal-mcp/PLAYBOOK.md` section 8 and `eu-legal-mcp/template/SOURCES.template.md` for the
process this file supports.

| LDH id | LDH name | Our status | Our tool(s) | Notes / rejection reason |
|---|---|---|---|---|
| FR/LODA | Legifrance - Laws & Decrees | shipped | `fr_search` (fond LODA), `fr_get_act`, `fr_get_text` | original build (fr-eli-mcp 0.1.0) |
| FR/CASS | Legifrance - Cour de Cassation | shipped | `fr_search` (fond JURI), `fr_get_decision` | original build, native ECLI |
| FR/ConseilConstitutionnel | Conseil constitutionnel | shipped | `fr_search` (fond CONSTIT), `fr_get_decision` | 2026-07-07, commit f90bc25, ~7 372 decisions live on sandbox, native ECLI (ECLI:FR:CC:...) |
| FR/CouncilState | Conseil d'Etat, CAA, TA | shipped | `fr_search` (fond CETAT), `fr_get_decision` | 2026-07-07, commit f90bc25, ~569 270 decisions, native ECLI for CE only (CAA/TA left null, not fabricated) |
| FR/Judilibre | Judilibre (official case-law hub) | rejected | - | `needs_separate_subscription` - LDH status @ check 2026-07-08: `complete` (STALE-REJ re-verified, rejection STANDS). Live probes 2026-07-08: sandbox `sandbox-api.piste.gouv.fr/cassation/judilibre/v1.0/{search,stats,healthcheck}` -> 403 with a valid Bearer token (granted scope `openid resource.READ`; scope requests for `cassation`/`judilibre` are ignored), `KeyId`/no-auth -> 400; prod `oauth.piste.gouv.fr` -> `invalid_client` (app is sandbox-only). The Judilibre API is a separate per-application PISTE subscription (dashboard act, human-in-the-loop). JURI fond already covers Cassation. |
| FR/CNIL | Data Protection Authority | shipped | `fr_search` (fond CNIL), `fr_get_deliberation` | 2026-07-08, feature-003 (0.3.0). LDH status @ check: `todo`. >= 26 759 deliberations (live `totalResultNumber`, broad query), full verbatim text via `/consult/cnil`, no ECLI/ELI upstream (left null). |
| FR/ConventionsCollectives | Conventions Collectives (Base KALI) | shipped | `fr_search` (fond KALI), `fr_get_convention`, `fr_get_text` (KALIARTI ids) | 2026-07-08, feature-003 (0.3.0). LDH status @ check: `complete` (LDH lists the DILA bulk dump; we ship the same corpus via the existing PISTE `/search` + `/consult/kaliText` + shared `/consult/getArticle`). >= 35 790 texts live. |
| FR/ACCO (no exact LDH id; company-level agreements) | Accords d'entreprise (Base ACCO) | shipped | `fr_search` (fond ACCO), `fr_get_company_agreement` | 2026-07-08, feature-003 (0.3.0). >= 387 656 agreements live. METADATA ONLY on consult - Legifrance returns the full text solely as a base64 `.docx` attachment; the tool says so explicitly (`attachment_note`) and cites `source_url`, never re-serves or fabricates text. |
| FR/AssembleeNationale | French National Assembly | todo | - | not yet evaluated |
| FR/Senat | French Senate | todo | - | not yet evaluated |
| FR/BOFiP | Bulletin Officiel des Finances Publiques | todo | - | JSON backend exists (`data.economie.gouv.fr` bofip-vigueur dataset) - candidate for a future widen round, not probed live this round (budget spent on CNIL/KALI/ACCO + Judilibre re-verify) |
| FR/ADLC | Autorite de la concurrence | todo | - | not yet evaluated (no obvious JSON backend; website-first) |

Last updated: 2026-07-08 (widen round feature-003, see `eu-legal-mcp/AUDIT-LOG.md`).
