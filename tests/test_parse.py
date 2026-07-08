"""Offline parse tests - feed the saved Legifrance fixtures through the normalizers.

These never touch the network and assert the citation contract (eli_uri /
human_readable_citation / source_url) plus the ELI/ECLI policy of this connector.
"""

from __future__ import annotations

import json
from pathlib import Path

from fr_eli_mcp import citations

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_search_loda_hits():
    norm = citations.normalize_search(_load("search_loda.json"), "LODA_DATE")
    assert norm["total"] >= 1
    hit = norm["hits"][0]
    assert hit["kind"] == "loda"
    assert hit["id"].startswith("LEGITEXT")
    assert "_" not in hit["id"], "date suffix must be stripped"
    assert "Rpublique" not in (hit["title"] or ""), "marks should be gone"
    assert "<mark>" not in (hit["title"] or "")
    assert hit["source_url"].startswith("https://www.legifrance.gouv.fr/loda/id/")
    assert hit["eli_uri"] == hit["source_url"]
    assert hit["human_readable_citation"]


def test_search_code_hits_carry_article_ids():
    norm = citations.normalize_search(_load("search_code.json"), "CODE_DATE")
    hit = norm["hits"][0]
    assert hit["kind"] == "code"
    assert hit["articles"], "code hit should expose matched articles"
    assert hit["articles"][0]["article_id"].startswith("LEGIARTI")


def test_search_juri_hits():
    norm = citations.normalize_search(_load("search_juri.json"), "JURI")
    hit = norm["hits"][0]
    assert hit["kind"] == "juri"
    assert hit["source_url"].startswith("https://www.legifrance.gouv.fr/juri/id/")
    assert hit["human_readable_citation"]


def test_law_decree_metadata_and_toc():
    norm = citations.normalize_law_decree(_load("consult_loda.json"))
    assert norm is not None
    assert norm["text_id"].startswith("LEGITEXT")
    assert norm["nature"] == "LOI"
    assert norm["human_readable_citation"], "title-based citation expected"
    assert norm["source_url"].startswith("https://www.legifrance.gouv.fr/loda/id/")
    assert norm["eli_uri"] == norm["source_url"]
    assert norm["articles"], "table of contents expected"
    assert norm["articles"][0]["article_id"].startswith("LEGIARTI")


def test_article_text_and_citation():
    norm = citations.normalize_article(_load("consult_article.json"))
    assert norm is not None
    assert norm["article_id"].startswith("LEGIARTI")
    assert norm["num"] == "9"
    assert norm["code_title"] == "Code civil"
    assert norm["human_readable_citation"] == "Code civil, art. 9"
    assert norm["source_url"].startswith("https://www.legifrance.gouv.fr/codes/article_lc/")
    assert norm["text"]


def test_juri_native_ecli():
    norm = citations.normalize_juri(_load("consult_juri.json"))
    assert norm is not None
    assert norm["decision_id"].startswith("JURITEXT")
    assert norm["ecli"] and norm["ecli"].startswith("ECLI:FR:")
    assert norm["juridiction"]
    assert norm["source_url"].startswith("https://www.legifrance.gouv.fr/juri/id/")
    assert norm["human_readable_citation"]


def test_search_constit_hits():
    norm = citations.normalize_search(_load("search_constit.json"), "CONSTIT")
    assert norm["total"] >= 1
    hit = norm["hits"][0]
    assert hit["kind"] == "constit"
    assert hit["id"].startswith("CONSTEXT")
    assert hit["source_url"].startswith("https://www.legifrance.gouv.fr/cons/id/")
    assert hit["eli_uri"] == hit["source_url"]
    assert hit["human_readable_citation"]


def test_search_cetat_hits():
    norm = citations.normalize_search(_load("search_cetat.json"), "CETAT")
    assert norm["total"] >= 1
    hit = norm["hits"][0]
    assert hit["kind"] == "cetat"
    assert hit["id"].startswith("CETATEXT")
    assert hit["source_url"].startswith("https://www.legifrance.gouv.fr/ceta/id/")
    assert hit["eli_uri"] == hit["source_url"]
    assert hit["human_readable_citation"]


def test_consult_juri_constit_native_ecli_and_citation():
    norm = citations.normalize_juri(_load("consult_juri_constit.json"))
    assert norm is not None
    assert norm["decision_id"].startswith("CONSTEXT")
    assert norm["ecli"] == "ECLI:FR:CC:2025:2025.1173.QPC"
    assert norm["juridiction"] == "Conseil constitutionnel"
    assert norm["source_url"] == "https://www.legifrance.gouv.fr/cons/id/CONSTEXT000052555275"
    assert norm["eli_uri"] == norm["source_url"]
    # French citation convention: "Cons. const., decision n 2025-1173 QPC du 7 novembre 2025 - ..."
    citation = norm["human_readable_citation"]
    assert citation.startswith("Cons. const., decision n° 2025-1173 QPC du 7 novembre 2025")


def test_consult_juri_cetat_native_ecli():
    norm = citations.normalize_juri(_load("consult_juri_cetat.json"))
    assert norm is not None
    assert norm["decision_id"].startswith("CETATEXT")
    assert norm["ecli"] and norm["ecli"].startswith("ECLI:FR:CE")
    assert norm["juridiction"] == "Conseil d'État"
    assert norm["source_url"] == "https://www.legifrance.gouv.fr/ceta/id/CETATEXT000054178503"
    assert norm["eli_uri"] == norm["source_url"]
    assert norm["human_readable_citation"]


def test_strip_date_suffix_and_marks():
    assert citations.strip_date_suffix("LEGITEXT000033205014_08-09-2023") == "LEGITEXT000033205014"
    assert citations.strip_date_suffix("JURITEXT000051743650") == "JURITEXT000051743650"
    assert citations.strip_marks("a <mark>b</mark> c") == "a b c"


def test_no_fabricated_eli():
    """eli_uri must be a legifrance.gouv.fr URL, never a synthesized /eli/ path."""
    for fx, fond in [
        ("search_loda.json", "LODA_DATE"),
        ("search_juri.json", "JURI"),
        ("search_constit.json", "CONSTIT"),
        ("search_cetat.json", "CETAT"),
    ]:
        for hit in citations.normalize_search(_load(fx), fond)["hits"]:
            assert "/eli/" not in (hit["eli_uri"] or ""), "must not fabricate a native /eli/ URI"


# ---------------------------------------------------------------------------
# feature-003: CNIL deliberations, KALI collective agreements, ACCO agreements
# ---------------------------------------------------------------------------


def test_search_cnil_hits():
    norm = citations.normalize_search(_load("search_cnil.json"), "CNIL")
    assert norm["total"] >= 1
    hit = norm["hits"][0]
    assert hit["kind"] == "cnil"
    assert hit["id"].startswith("CNILTEXT")
    assert hit["source_url"].startswith("https://www.legifrance.gouv.fr/cnil/id/")
    assert hit["eli_uri"] == hit["source_url"]
    assert hit["human_readable_citation"]
    assert "<mark>" not in (hit["title"] or "")


def test_search_kali_hits():
    norm = citations.normalize_search(_load("search_kali.json"), "KALI")
    assert norm["total"] >= 1
    hit = norm["hits"][0]
    assert hit["kind"] == "kali"
    assert hit["id"].startswith("KALITEXT")
    assert hit["source_url"].startswith("https://www.legifrance.gouv.fr/conv_coll/id/")
    assert hit["eli_uri"] == hit["source_url"]
    assert hit["human_readable_citation"]


def test_search_acco_hits_carry_company():
    norm = citations.normalize_search(_load("search_acco.json"), "ACCO")
    assert norm["total"] >= 1
    hit = norm["hits"][0]
    assert hit["kind"] == "acco"
    assert hit["id"].startswith("ACCOTEXT")
    assert hit["source_url"].startswith("https://www.legifrance.gouv.fr/acco/id/")
    assert hit["raison_sociale"], "ACCO hit should carry the depositing company"
    assert hit["idcc"], "ACCO hit should carry the IDCC"
    # Citation carries the company so the agreement is identifiable.
    assert hit["raison_sociale"] in hit["human_readable_citation"]


def test_consult_cnil_citation_and_text():
    norm = citations.normalize_cnil(_load("consult_cnil.json"))
    assert norm is not None
    assert norm["deliberation_id"].startswith("CNILTEXT")
    assert norm["nature_delib"] == "Sanction"
    assert norm["text"], "deliberation text expected"
    assert norm["source_url"] == "https://www.legifrance.gouv.fr/cnil/id/CNILTEXT000053352643"
    assert norm["eli_uri"] == norm["source_url"]
    # Citation convention: "CNIL, deliberation n° SAN-2026-002 du 8 janvier 2026"
    assert norm["human_readable_citation"].startswith("CNIL, deliberation n° SAN-2026-002 du")


def test_consult_kali_toc_resolvable_via_get_text():
    norm = citations.normalize_kali(_load("consult_kali.json"))
    assert norm is not None
    assert norm["text_id"].startswith("KALITEXT")
    assert norm["source_url"].startswith("https://www.legifrance.gouv.fr/conv_coll/id/")
    assert norm["eli_uri"] == norm["source_url"]
    assert norm["human_readable_citation"]
    assert norm["articles"], "table of contents expected"
    assert norm["articles"][0]["article_id"].startswith("KALIARTI")


def test_consult_acco_metadata_only_no_docx_payload():
    norm = citations.normalize_acco(_load("consult_acco.json"))
    assert norm is not None
    assert norm["agreement_id"].startswith("ACCOTEXT")
    assert norm["raison_sociale"]
    assert norm["siret"]
    assert norm["themes"]
    assert norm["source_url"].startswith("https://www.legifrance.gouv.fr/acco/id/")
    assert norm["eli_uri"] == norm["source_url"]
    assert norm["attachment_note"], "must be explicit that full text is a docx attachment"
    assert "text" not in norm, "ACCO is metadata-only - no fabricated text field"
    assert norm["raison_sociale"] in norm["human_readable_citation"]


def test_kali_article_url_uses_conv_coll():
    fx = _load("consult_article.json")
    fx["article"]["id"] = "KALIARTI000049886059"
    norm = citations.normalize_article(fx)
    assert norm is not None
    assert norm["source_url"] == (
        "https://www.legifrance.gouv.fr/conv_coll/id/KALIARTI000049886059"
    )
