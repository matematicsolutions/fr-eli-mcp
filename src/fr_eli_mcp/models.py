"""Pydantic v2 models for the French Legifrance API + fr-eli-mcp."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

DATASET_NOTE = (
    "Legifrance via PISTE. Legislation (LODA laws/decrees, codes) and case law (JURI) are "
    "searchable by keyword. The PISTE consult API does NOT expose a populated native ELI for "
    "legislation, so 'eli_uri' carries the stable resolvable Legifrance resource URL (never a "
    "fabricated /eli/ string). Case law carries a native authoritative 'ecli'."
)

ELI_NOTE = (
    "Legifrance lf-engine-app returns the ELI field null for legislation; 'eli_uri' is the "
    "stable CID-keyed legifrance.gouv.fr resource URL, not a synthesized /eli/ identifier."
)


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class CodeArticleRef(_Tolerant):
    """A matched article inside a code search hit."""

    article_id: str | None = None
    num: str | None = None
    snippet: str | None = None


class SearchHit(_Tolerant):
    """One normalized search result."""

    kind: str | None = None  # loda | code | juri | constit | cetat | cnil | kali | acco
    id: str | None = None
    cid: str | None = None
    title: str | None = None
    nature: str | None = None
    etat: str | None = None
    idcc: str | int | None = None  # KALI / ACCO - collective agreement number
    raison_sociale: str | None = None  # ACCO - depositing company
    articles: list[CodeArticleRef] = Field(default_factory=list)

    # Citation contract.
    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class SearchResult(_Tolerant):
    """Result of ``fr_search``."""

    fond: str
    query: str
    total: int
    hits: list[SearchHit] = Field(default_factory=list)
    eli_note: str = ELI_NOTE
    dataset_note: str = DATASET_NOTE


# ---------------------------------------------------------------------------
# Consult: law / decree (LODA)
# ---------------------------------------------------------------------------


class ArticleRef(_Tolerant):
    """An article entry in a law/decree table of contents."""

    article_id: str | None = None
    num: str | None = None
    etat: str | None = None


class Act(_Tolerant):
    """Result of ``fr_get_act`` - a consolidated LODA law or decree."""

    text_id: str | None = None
    cid: str | None = None
    nor: str | None = None
    title: str | None = None
    nature: str | None = None
    etat: str | None = None
    date_parution: str | None = None
    num_parution: str | None = None
    date_debut_version: str | None = None
    date_fin_version: str | None = None
    articles: list[ArticleRef] = Field(default_factory=list)

    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None
    eli_note: str = ELI_NOTE


# ---------------------------------------------------------------------------
# Consult: single article text
# ---------------------------------------------------------------------------


class ArticleText(_Tolerant):
    """Result of ``fr_get_text`` - a single article's verbatim text."""

    article_id: str | None = None
    num: str | None = None
    etat: str | None = None
    code_title: str | None = None
    full_sections_titre: str | None = None
    date_debut: str | None = None
    date_fin: str | None = None
    text: str | None = None
    byte_size: int | None = None

    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None
    eli_note: str = ELI_NOTE


# ---------------------------------------------------------------------------
# Consult: JURI decision (native ECLI)
# ---------------------------------------------------------------------------


class Deliberation(_Tolerant):
    """Result of ``fr_get_deliberation`` - a CNIL deliberation (fond CNIL)."""

    deliberation_id: str | None = None
    num: str | None = None
    nature: str | None = None
    nature_delib: str | None = None
    etat: str | None = None
    date_texte: str | None = None
    date_publication: str | None = None
    title: str | None = None
    title_long: str | None = None
    text: str | None = None
    byte_size: int | None = None

    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class CompanyAgreement(_Tolerant):
    """Result of ``fr_get_company_agreement`` - ACCO metadata (text is a docx attachment)."""

    agreement_id: str | None = None
    nature: str | None = None
    title: str | None = None
    raison_sociale: str | None = None
    siret: str | None = None
    idcc: str | int | None = None
    code_ape: str | None = None
    secteur: str | None = None
    themes: list[str] = Field(default_factory=list)
    syndicats: list[str] = Field(default_factory=list)
    date_texte: str | None = None
    date_effet: str | None = None
    date_depot: str | None = None
    attachment_note: str | None = None

    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class Decision(_Tolerant):
    """Result of ``fr_get_decision`` - a JURI court decision with a native ECLI."""

    decision_id: str | None = None
    ecli: str | None = None
    juridiction: str | None = None
    formation: str | None = None
    solution: str | None = None
    numero_affaire: list[str] | None = None
    date_texte: str | None = None
    nature: str | None = None
    title: str | None = None
    text: str | None = None
    byte_size: int | None = None

    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None
