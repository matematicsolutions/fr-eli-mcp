"""Smoke tests - require internet + PISTE credentials (loaded from .env by conftest).

Run manually:

    pytest tests/test_smoke.py -v

Skipped automatically if FR_ELI_CLIENT_ID / FR_ELI_CLIENT_SECRET are not configured.
"""

from __future__ import annotations

import os

import pytest

from fr_eli_mcp.server import fr_get_act, fr_get_decision, fr_get_text, fr_search

_HAS_CREDS = bool(os.environ.get("FR_ELI_CLIENT_ID") and os.environ.get("FR_ELI_CLIENT_SECRET"))
pytestmark = pytest.mark.skipif(_HAS_CREDS is False, reason="PISTE credentials not configured")


@pytest.mark.asyncio
async def test_smoke_search_loda() -> None:
    res = await fr_search("republique numerique", fond="LODA", page_size=5)
    assert res.total >= 1
    hit = res.hits[0]
    assert hit.id and hit.id.startswith("LEGITEXT")
    assert hit.source_url and hit.source_url.startswith("https://www.legifrance.gouv.fr/")
    assert hit.human_readable_citation


@pytest.mark.asyncio
async def test_smoke_search_code() -> None:
    res = await fr_search("vie privee", fond="CODE", page_size=5)
    assert res.total >= 1


@pytest.mark.asyncio
async def test_smoke_get_act_and_text() -> None:
    act = await fr_get_act("LEGITEXT000033205014")
    assert act.nature == "LOI"
    assert act.human_readable_citation
    assert act.source_url and act.source_url.startswith("https://www.legifrance.gouv.fr/")
    assert act.articles, "expected a table of contents"
    art_id = act.articles[0].article_id
    assert art_id and art_id.startswith("LEGIARTI")
    text = await fr_get_text(art_id)
    assert text.text, "article should have verbatim text"
    assert text.source_url and "/codes/article_lc/" in text.source_url


@pytest.mark.asyncio
async def test_smoke_get_decision_has_native_ecli() -> None:
    res = await fr_search("responsabilite", fond="JURI", page_size=3)
    assert res.hits
    decision = await fr_get_decision(res.hits[0].id)
    assert decision.ecli and decision.ecli.startswith("ECLI:FR:")
    assert decision.source_url and "/juri/id/" in decision.source_url
    assert decision.human_readable_citation


@pytest.mark.asyncio
async def test_smoke_search_and_get_constit_decision() -> None:
    res = await fr_search("liberte", fond="CONSTIT", page_size=3)
    assert res.total >= 1
    hit = res.hits[0]
    assert hit.id and hit.id.startswith("CONSTEXT")
    assert hit.source_url and hit.source_url.startswith("https://www.legifrance.gouv.fr/cons/id/")

    decision = await fr_get_decision(hit.id)
    assert decision.ecli and decision.ecli.startswith("ECLI:FR:CC:")
    assert decision.juridiction == "Conseil constitutionnel"
    assert decision.source_url and "/cons/id/" in decision.source_url
    assert decision.human_readable_citation
    assert decision.human_readable_citation.startswith("Cons. const.")


@pytest.mark.asyncio
async def test_smoke_search_and_get_cetat_decision() -> None:
    # CETAT covers Conseil d'Etat, CAA and TA. Unlike CONSTIT, not every CETAT decision carries
    # a native ECLI (CAA/TA coverage is uneven) - search several hits and require at least one
    # populated ECLI, never assert it on an arbitrary single hit.
    res = await fr_search("urbanisme", fond="CETAT", page_size=5)
    assert res.total >= 1
    hit = res.hits[0]
    assert hit.id and hit.id.startswith("CETATEXT")
    assert hit.source_url and hit.source_url.startswith("https://www.legifrance.gouv.fr/ceta/id/")

    found_ecli = False
    for h in res.hits:
        decision = await fr_get_decision(h.id)
        assert decision.source_url and "/ceta/id/" in decision.source_url
        assert decision.human_readable_citation
        if decision.ecli:
            assert decision.ecli.startswith("ECLI:FR:CE")
            found_ecli = True
    assert found_ecli, "expected at least one CETAT hit with a native ECLI"
