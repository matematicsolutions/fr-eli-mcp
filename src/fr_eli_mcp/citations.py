"""French Legifrance normalization + citation helpers.

Citation contract (Art. 4 CONSTITUTION):
- ``eli_uri``: a stable, resolvable Legifrance resource URI.
- ``human_readable_citation``: the French legal citation convention.
- ``source_url``: the legifrance.gouv.fr page for the item.

IMPORTANT - ELI vs ECLI on Legifrance:
- **Legislation (LODA / codes):** the PISTE ``lf-engine-app`` consult API returns the
  ``eli`` / ``idEli`` fields *null* for the texts we tested - it does not expose a populated
  native ELI. Following the eu-legal-mcp rule "say what you do NOT have, never fabricate an
  ELI", ``eli_uri`` therefore carries the stable CID-keyed Legifrance resource URI (which
  resolves), NOT a synthesized ``/eli/...`` string parsed from prose.
- **Case law (JURI):** the API DOES return a native, authoritative ``ecli`` (e.g.
  ``ECLI:FR:CCASS:2025:C100399``). We surface it verbatim in a dedicated ``ecli`` field.
- **Conseil constitutionnel (CONSTIT):** same ``consult/juri`` endpoint, ``CONSTEXT...`` ids.
  Native ``ecli`` (e.g. ``ECLI:FR:CC:2025:2025.1173.QPC``); the decision ``titre`` already is
  the French citation convention ("Décision n° 2025-1173 QPC du 7 novembre 2025 - ...").
- **Administrative courts (CETAT):** same ``consult/juri`` endpoint, ``CETATEXT...`` ids. Covers
  Conseil d'Etat, cours administratives d'appel (CAA) and tribunaux administratifs (TA). Conseil
  d'Etat decisions carry a native ``ecli`` (e.g. ``ECLI:FR:CECHR:2026:506507.20260529``); CAA/TA
  coverage is uneven and ``ecli`` is frequently ``None`` - never fabricate one when absent, cite
  the decision's ``titre`` (court, formation, date, dossier number) and ``source_url`` instead.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

WEB_BASE = "https://www.legifrance.gouv.fr"

_ID_PREFIXES = ("LEGITEXT", "JORFTEXT", "JURITEXT", "CETATEXT", "KALITEXT", "LEGIARTI")
_MARK_RE = re.compile(r"</?mark>")


def strip_marks(text: str | None) -> str | None:
    """Remove the ``<mark>`` highlight tags Legifrance wraps around search hits."""
    if text is None:
        return None
    return _MARK_RE.sub("", text).strip() or None


def strip_date_suffix(identifier: str | None) -> str | None:
    """``LEGITEXT000033205014_08-09-2023`` -> ``LEGITEXT000033205014``."""
    if not identifier:
        return identifier
    if "_" in identifier:
        head = identifier.split("_", 1)[0]
        if head.startswith(_ID_PREFIXES):
            return head
    return identifier


def ms_to_date(ms: Any) -> str | None:
    """Epoch milliseconds -> ``YYYY-MM-DD`` (UTC). Tolerates None / non-int."""
    if not isinstance(ms, int):
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def legifrance_url(identifier: str | None, kind: str) -> str | None:
    """Build a resolvable legifrance.gouv.fr URL for a resource."""
    if not identifier:
        return None
    match kind:
        case "loda":
            return f"{WEB_BASE}/loda/id/{identifier}"
        case "code":
            return f"{WEB_BASE}/codes/texte_lc/{identifier}"
        case "code_article":
            return f"{WEB_BASE}/codes/article_lc/{identifier}"
        case "juri":
            return f"{WEB_BASE}/juri/id/{identifier}"
        case "constit":
            return f"{WEB_BASE}/cons/id/{identifier}"
        case "cetat":
            return f"{WEB_BASE}/ceta/id/{identifier}"
        case "jorf":
            return f"{WEB_BASE}/jorf/id/{identifier}"
        case _:
            return None


# ---------------------------------------------------------------------------
# Search hits
# ---------------------------------------------------------------------------


def normalize_search_hit(result: dict[str, Any], fond: str) -> dict[str, Any]:
    """Normalize one ``results[]`` entry from ``/search`` into the citation contract."""
    titles = result.get("titles") or [{}]
    head = titles[0] if titles else {}
    raw_id = head.get("id")
    text_id = strip_date_suffix(raw_id)
    cid = head.get("cid")
    title = strip_marks(head.get("title"))
    out: dict[str, Any] = {
        "id": text_id,
        "cid": cid,
        "title": title,
        "nature": result.get("nature"),
        "etat": result.get("etat"),
        "human_readable_citation": title,
    }

    if fond == "CONSTIT":
        out["kind"] = "constit"
        url = legifrance_url(cid or text_id, "constit")
    elif fond == "CETAT":
        out["kind"] = "cetat"
        url = legifrance_url(cid or text_id, "cetat")
    elif fond.startswith("JURI"):
        out["kind"] = "juri"
        url = legifrance_url(cid or text_id, "juri")
    elif fond.startswith("CODE"):
        out["kind"] = "code"
        url = legifrance_url(text_id, "code")
        arts: list[dict[str, Any]] = []
        for sec in result.get("sections") or []:
            for ex in sec.get("extracts") or []:
                if ex.get("id"):
                    snippet = strip_marks((ex.get("values") or [""])[0]) or ""
                    arts.append(
                        {
                            "article_id": ex.get("id"),
                            "num": ex.get("num"),
                            "snippet": snippet[:280],
                        }
                    )
        out["articles"] = arts
    else:  # LODA and other text fonds
        out["kind"] = "loda"
        url = legifrance_url(text_id, "loda")

    out["source_url"] = url
    out["eli_uri"] = url
    return out


def normalize_search(payload: dict[str, Any], fond: str) -> dict[str, Any]:
    """Normalize the full ``/search`` envelope."""
    results = payload.get("results") or []
    hits = [normalize_search_hit(r, fond) for r in results]
    total = payload.get("totalResultNumber")
    if not isinstance(total, int):
        total = len(hits)
    return {"total": total, "hits": hits}


# ---------------------------------------------------------------------------
# Consult: LODA law / decree
# ---------------------------------------------------------------------------


def _walk_articles(sections: list[dict[str, Any]] | None, out: list[dict[str, Any]]) -> None:
    for sec in sections or []:
        for art in sec.get("articles") or []:
            if art.get("id"):
                out.append(
                    {
                        "article_id": art.get("id"),
                        "num": art.get("num"),
                        "etat": art.get("etat"),
                    }
                )
        _walk_articles(sec.get("sections"), out)


def normalize_law_decree(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a ``/consult/lawDecree`` (LODA) response."""
    if not payload or not (payload.get("id") or payload.get("cid")):
        return None
    text_id = strip_date_suffix(payload.get("id"))
    title = payload.get("title")
    toc: list[dict[str, Any]] = []
    _walk_articles(payload.get("sections"), toc)
    url = legifrance_url(text_id, "loda")
    return {
        "text_id": text_id,
        "cid": payload.get("cid"),
        "nor": payload.get("nor"),
        "title": title,
        "nature": payload.get("nature"),
        "etat": payload.get("etat"),
        "date_parution": ms_to_date(payload.get("dateParution")),
        "num_parution": payload.get("numParution"),
        "date_debut_version": payload.get("dateDebutVersion"),
        "date_fin_version": payload.get("dateFinVersion"),
        "articles": toc,
        "human_readable_citation": title,
        "source_url": url,
        "eli_uri": url,
    }


# ---------------------------------------------------------------------------
# Consult: a single article (code or law)
# ---------------------------------------------------------------------------


def _code_title(article: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (code_title, code_id) from ``textTitles`` (prefer the CODE entry)."""
    titles = article.get("textTitles") or []
    if not isinstance(titles, list):
        return None, None
    code_entry = next((t for t in titles if (t or {}).get("nature") == "CODE"), None)
    entry = code_entry or (titles[0] if titles else None)
    if not entry:
        return None, None
    return entry.get("titre"), entry.get("id")


def normalize_article(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a ``/consult/getArticle`` response."""
    article = payload.get("article")
    if not article or not article.get("id"):
        return None
    art_id = article.get("id")
    num = article.get("num")
    code_title, _code_id = _code_title(article)
    if code_title and num:
        citation = f"{code_title}, art. {num}"
    elif num:
        citation = f"Art. {num}"
    else:
        citation = code_title
    url = legifrance_url(art_id, "code_article")
    return {
        "article_id": art_id,
        "num": num,
        "etat": article.get("etat"),
        "code_title": code_title,
        "full_sections_titre": article.get("fullSectionsTitre"),
        "date_debut": ms_to_date(article.get("dateDebut")),
        "date_fin": ms_to_date(article.get("dateFin")),
        "text": article.get("texte"),
        "human_readable_citation": citation,
        "source_url": url,
        "eli_uri": url,
    }


# ---------------------------------------------------------------------------
# Consult: JURI / CONSTIT / CETAT decision (native ECLI, shared endpoint)
# ---------------------------------------------------------------------------

_FR_MONTHS = (
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
)


def _fr_date(ms: Any) -> str | None:
    """Epoch milliseconds -> ``D mois AAAA`` (French prose date, no leading zero)."""
    date_str = ms_to_date(ms)
    if not date_str:
        return None
    year, month, day = date_str.split("-")
    return f"{int(day)} {_FR_MONTHS[int(month) - 1]} {year}"


def _constit_citation(text: dict[str, Any]) -> str | None:
    """French citation convention for a Conseil constitutionnel decision.

    ``Cons. const., decision n DEC-CIB NATURE du DD mois AAAA[ - objet]``
    e.g. "Cons. const., decision n 2025-1173 QPC du 7 novembre 2025 - [...]".
    """
    num = text.get("num")
    nature = (text.get("nature") or "").upper()  # "QPC" | "DC" | ...
    date_prose = _fr_date(text.get("dateTexte"))
    if not (num and date_prose):
        return None
    head = f"Cons. const., decision n° {num}"
    if nature:
        head += f" {nature}"
    head += f" du {date_prose}"
    titre = text.get("titre") or ""
    # Pull the bracketed case name out of the titre if present, e.g. "[...]" after the date.
    match = re.search(r"\[(.+?)\]", titre)
    if match:
        head += f" - {match.group(1)}"
    return head


def normalize_juri(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a ``/consult/juri`` response.

    Shared across three origins - Cour de cassation / cours d'appel (``JURI``), the Conseil
    constitutionnel (``CONSTIT``, ``CONSTEXT...`` ids) and the administrative courts (``CETAT``,
    ``CETATEXT...`` ids, covering Conseil d'Etat / CAA / TA). All three carry a native,
    authoritative ``ecli`` on this endpoint.
    """
    text = payload.get("text")
    if not text or not text.get("id"):
        return None
    decision_id = text.get("id")
    origine = (text.get("origine") or "").upper()
    url_kind = "constit" if origine == "CONSTIT" else "cetat" if origine == "CETAT" else "juri"
    url = legifrance_url(decision_id, url_kind)

    citation = text.get("titre")
    if origine == "CONSTIT":
        citation = _constit_citation(text) or citation

    return {
        "decision_id": decision_id,
        "ecli": text.get("ecli"),
        "juridiction": text.get("juridiction"),
        "formation": text.get("formation"),
        "solution": text.get("solution"),
        "numero_affaire": text.get("numeroAffaire"),
        "date_texte": ms_to_date(text.get("dateTexte")),
        "nature": text.get("nature"),
        "title": text.get("titre"),
        "text": text.get("texte"),
        "human_readable_citation": citation,
        "source_url": url,
        "eli_uri": url,
    }
