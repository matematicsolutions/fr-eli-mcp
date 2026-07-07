# Sources ledger - France (FR)

See `eu-legal-mcp/PLAYBOOK.md` section 8 and `eu-legal-mcp/template/SOURCES.template.md` for the
process this file supports.

| LDH id | LDH name | Our status | Our tool(s) | Notes / rejection reason |
|---|---|---|---|---|
| FR/LODA | Legifrance - Laws & Decrees | shipped | `fr_search` (fond LODA), `fr_get_act`, `fr_get_text` | original build (fr-eli-mcp 0.1.0) |
| FR/CASS | Legifrance - Cour de Cassation | shipped | `fr_search` (fond JURI), `fr_get_decision` | original build, native ECLI |
| FR/ConseilConstitutionnel | Conseil constitutionnel | shipped | `fr_search` (fond CONSTIT), `fr_get_decision` | 2026-07-07, commit f90bc25, ~7 372 decisions live on sandbox, native ECLI (ECLI:FR:CC:...) |
| FR/CouncilState | Conseil d'Etat, CAA, TA | shipped | `fr_search` (fond CETAT), `fr_get_decision` | 2026-07-07, commit f90bc25, ~569 270 decisions, native ECLI for CE only (CAA/TA left null, not fabricated) |
| FR/Judilibre | Judilibre (official case-law hub) | rejected | - | `needs_separate_subscription` - `api.piste.gouv.fr/cassation/judilibre` returns 403 even with a valid Legifrance token; JURI fond already covers Cassation |
| FR/AssembleeNationale | French National Assembly | todo | - | not yet evaluated |
| FR/Senat | French Senate | todo | - | not yet evaluated |
| FR/CNIL | Data Protection Authority | todo | - | not yet evaluated (regulator, lower priority than courts) |

Last updated: 2026-07-07 (widen round, see `eu-legal-mcp/AUDIT-LOG.md`).
