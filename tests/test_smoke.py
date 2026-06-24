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
