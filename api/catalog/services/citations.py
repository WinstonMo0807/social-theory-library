from catalog.models import Contribution, DocumentType, Edition
from catalog.services.publication_places import confirmed_publication_places


def _contributors(edition: Edition) -> list[str]:
    return list(
        edition.contributions.filter(
            role=Contribution.Role.AUTHOR,
            approved=True,
        )
        .order_by("order")
        .values_list("person__preferred_name", flat=True)
    )


def _author_text(names: list[str], separator: str = ", ") -> str:
    if not names:
        return "佚名"
    if len(names) <= 3:
        return separator.join(names)
    return f"{separator.join(names[:3])}, 等"


def _gbt_author_text(names: list[str]) -> str:
    if not names:
        return "佚名"
    if len(names) <= 3:
        return "，".join(names)
    return f"{'，'.join(names[:3])}，等"


def _gbt_page(page_label: str) -> str:
    return f"：{page_label}" if page_label else ""


def format_gbt_7714_2025(edition: Edition, page_label: str = "") -> str:
    work = edition.work
    authors = _gbt_author_text(_contributors(edition))
    year = edition.publication_year or "出版年不详"
    page = _gbt_page(page_label)

    if work.document_type == DocumentType.JOURNAL_ARTICLE:
        medium = "J/OL" if edition.doi else "J"
        volume = f"，{edition.volume}" if edition.volume else ""
        issue = f"（{edition.issue}）" if edition.issue else ""
        pages = _gbt_page(page_label or edition.page_range)
        doi = f". DOI:{edition.doi}" if edition.doi else ""
        return (
            f"{authors}. {work.title}[{medium}]. "
            f"{edition.journal_title or '刊名不详'}，{year}{volume}{issue}{pages}{doi}."
        )

    places = confirmed_publication_places(edition)
    primary_place = places[0] if places else ""

    if work.document_type == DocumentType.THESIS:
        return (
            f"{authors}. {work.title}[D]. "
            f"{primary_place + '：' if primary_place else ''}"
            f"{edition.degree_institution or '授予单位不详'}，{year}{page}."
        )

    if work.document_type == DocumentType.REPORT:
        institution = edition.report_institution or edition.publisher or "责任机构不详"
        place = f"{primary_place}：" if primary_place else ""
        return f"{authors}. {work.title}[R]. {place}{institution}，{year}{page}."

    place = primary_place or "[出版地不详]"
    publisher = edition.publisher or "出版者不详"
    edition_statement = f" {edition.version_label}." if edition.version_label else ""
    return f"{authors}. {work.title}[M].{edition_statement} {place}：{publisher}，{year}{page}."


def format_apa(edition: Edition, page_label: str = "") -> str:
    names = _author_text(_contributors(edition), ", ")
    year = edition.publication_year or "n.d."
    page = f", p. {page_label}" if page_label else ""
    return f"{names}. ({year}). {edition.work.title}. {edition.publisher or edition.journal_title}{page}."


def format_chicago(edition: Edition, page_label: str = "") -> str:
    names = _author_text(_contributors(edition), ", ")
    page = f", {page_label}" if page_label else ""
    places = confirmed_publication_places(edition)
    place = places[0] if places else ""
    return (
        f"{names}. {edition.work.title}. "
        f"{place + ': ' if place else ''}"
        f"{edition.publisher or edition.journal_title}, {edition.publication_year or 'n.d.'}{page}."
    )


def format_mla(edition: Edition, page_label: str = "") -> str:
    names = _author_text(_contributors(edition), ", ")
    page = f", p. {page_label}" if page_label else ""
    return f"{names}. {edition.work.title}. {edition.publisher or edition.journal_title}, {edition.publication_year or 'n.d.'}{page}."


def citation_bundle(edition: Edition, page_label: str = "") -> dict:
    return {
        "gbt7714-2025": format_gbt_7714_2025(edition, page_label),
        "apa": format_apa(edition, page_label),
        "chicago": format_chicago(edition, page_label),
        "mla": format_mla(edition, page_label),
        "harvard": format_apa(edition, page_label),
        "csl": edition.citation_data,
    }
