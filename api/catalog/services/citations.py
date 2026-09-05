from catalog.models import Contribution, DocumentType, Edition
from catalog.services.publication_places import confirmed_publication_places


def _contributors(edition: Edition, snapshot: dict | None = None) -> list[str]:
    if snapshot:
        return [
            str((row.get("person") or {}).get("preferred_name") or row.get("name") or "")
            for row in snapshot.get("contributions") or []
            if isinstance(row, dict)
            and row.get("role") == Contribution.Role.AUTHOR
            and ((row.get("person") or {}).get("preferred_name") or row.get("name"))
        ]
    return list(
        edition.contributions.filter(
            role=Contribution.Role.AUTHOR,
            approved=True,
        )
        .order_by("order")
        .values_list("person__preferred_name", flat=True)
    )


def _snapshot_values(edition: Edition, snapshot: dict | None):
    if not snapshot:
        return (
            {
                "title": edition.work.title,
                "document_type": edition.work.document_type,
            },
            {
                "publication_year": edition.publication_year,
                "publisher": edition.publisher,
                "journal_title": edition.journal_title,
                "publication_place": edition.publication_place,
                "volume": edition.volume,
                "issue": edition.issue,
                "page_range": edition.page_range,
                "doi": edition.doi,
                "degree_institution": edition.degree_institution,
                "report_institution": edition.report_institution,
                "version_label": edition.version_label,
            },
        )
    return snapshot.get("work") or {}, snapshot.get("edition") or {}


def _publication_places(edition: Edition, edition_values: dict, snapshot: dict | None):
    if snapshot:
        place = str(edition_values.get("publication_place") or "").strip()
        return [place] if place else []
    return confirmed_publication_places(edition)


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


def format_gbt_7714_2025(
    edition: Edition,
    page_label: str = "",
    *,
    snapshot: dict | None = None,
) -> str:
    work, values = _snapshot_values(edition, snapshot)
    authors = _gbt_author_text(_contributors(edition, snapshot))
    year = values.get("publication_year") or "出版年不详"
    page = _gbt_page(page_label)

    if work.get("document_type") == DocumentType.JOURNAL_ARTICLE:
        medium = "J/OL" if values.get("doi") else "J"
        volume = f"，{values.get('volume')}" if values.get("volume") else ""
        issue = f"（{values.get('issue')}）" if values.get("issue") else ""
        pages = _gbt_page(page_label or values.get("page_range") or "")
        doi = f". DOI:{values.get('doi')}" if values.get("doi") else ""
        return (
            f"{authors}. {work.get('title') or '未题名'}[{medium}]. "
            f"{values.get('journal_title') or '刊名不详'}，{year}{volume}{issue}{pages}{doi}."
        )

    places = _publication_places(edition, values, snapshot)
    primary_place = places[0] if places else ""

    if work.get("document_type") == DocumentType.THESIS:
        return (
            f"{authors}. {work.get('title') or '未题名'}[D]. "
            f"{primary_place + '：' if primary_place else ''}"
            f"{values.get('degree_institution') or '授予单位不详'}，{year}{page}."
        )

    if work.get("document_type") == DocumentType.REPORT:
        institution = values.get("report_institution") or values.get("publisher") or "责任机构不详"
        place = f"{primary_place}：" if primary_place else ""
        return f"{authors}. {work.get('title') or '未题名'}[R]. {place}{institution}，{year}{page}."

    place = primary_place or "[出版地不详]"
    publisher = values.get("publisher") or "出版者不详"
    edition_statement = f" {values.get('version_label')}." if values.get("version_label") else ""
    return f"{authors}. {work.get('title') or '未题名'}[M].{edition_statement} {place}：{publisher}，{year}{page}."


def format_apa(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    work, values = _snapshot_values(edition, snapshot)
    names = _author_text(_contributors(edition, snapshot), ", ")
    year = values.get("publication_year") or "n.d."
    page = f", p. {page_label}" if page_label else ""
    return f"{names}. ({year}). {work.get('title') or '未题名'}. {values.get('publisher') or values.get('journal_title') or ''}{page}."


def format_chicago(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    work, values = _snapshot_values(edition, snapshot)
    names = _author_text(_contributors(edition, snapshot), ", ")
    page = f", {page_label}" if page_label else ""
    places = _publication_places(edition, values, snapshot)
    place = places[0] if places else ""
    return (
        f"{names}. {work.get('title') or '未题名'}. "
        f"{place + ': ' if place else ''}"
        f"{values.get('publisher') or values.get('journal_title') or ''}, {values.get('publication_year') or 'n.d.'}{page}."
    )


def format_mla(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    work, values = _snapshot_values(edition, snapshot)
    names = _author_text(_contributors(edition, snapshot), ", ")
    page = f", p. {page_label}" if page_label else ""
    return f"{names}. {work.get('title') or '未题名'}. {values.get('publisher') or values.get('journal_title') or ''}, {values.get('publication_year') or 'n.d.'}{page}."


def _snapshot_csl(edition: Edition, snapshot: dict) -> dict:
    work, values = _snapshot_values(edition, snapshot)
    authors = [
        {"literal": name}
        for name in _contributors(edition, snapshot)
    ]
    year = values.get("publication_year")
    return {
        "id": str(edition.id),
        "type": (
            "article-journal"
            if work.get("document_type") == DocumentType.JOURNAL_ARTICLE
            else "book"
        ),
        "title": work.get("title") or "未题名",
        "author": authors,
        "publisher": values.get("publisher") or "",
        "container-title": values.get("journal_title") or "",
        "issued": {"date-parts": [[year]]} if year else {},
        "DOI": values.get("doi") or "",
    }


def citation_bundle(
    edition: Edition,
    page_label: str = "",
    *,
    snapshot: dict | None = None,
) -> dict:
    return {
        "gbt7714-2025": format_gbt_7714_2025(edition, page_label, snapshot=snapshot),
        "apa": format_apa(edition, page_label, snapshot=snapshot),
        "chicago": format_chicago(edition, page_label, snapshot=snapshot),
        "mla": format_mla(edition, page_label, snapshot=snapshot),
        "harvard": format_apa(edition, page_label, snapshot=snapshot),
        "csl": _snapshot_csl(edition, snapshot) if snapshot else edition.citation_data,
    }
