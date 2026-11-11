import re
import unicodedata

from catalog.models import Contribution, DocumentType, Edition
from catalog.services.contribution_scope import whole_edition_contribution
from catalog.services.publication_places import confirmed_publication_places


def _contributors(edition: Edition, snapshot: dict | None = None, role=Contribution.Role.AUTHOR) -> list[str]:
    if snapshot:
        return [
            str((row.get("person") or {}).get("preferred_name") or row.get("name") or "")
            for row in snapshot.get("contributions") or []
            if isinstance(row, dict)
            and row.get("role") == role and whole_edition_contribution(row)
            and ((row.get("person") or {}).get("preferred_name") or row.get("name"))
        ]
    return [row.person.preferred_name for row in edition.contributions.filter(
        role=role, approved=True).select_related("person").order_by("order") if whole_edition_contribution(row)]


def citation_edition(value) -> str:
    """Clean a display label for citation only; preserve original catalog metadata."""
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    # Copyright-page dates and print runs are not edition statements.
    value = re.sub(r"\d{4}\s*年(?:\s*\d{1,2}\s*月)?(?:\s*\d{1,2}\s*日)?", "", value)
    parts = []
    for part in re.split(r"[,，;；\n]", value):
        if re.search(r"印刷|印次|印行|\b(?:printing|impression)\b", part, re.I):
            # A version and a print run sometimes share one unpunctuated field.
            match = re.search(r".*?(?:版|\bed(?:ition)?\.)", part, re.I)
            part = match.group(0) if match else ""
        part = part.strip(" .。")
        if not part or re.fullmatch(r"(?:第?\s*(?:1|一)\s*版|初版|first\s+edition|1st\s+ed(?:ition)?)", part, re.I):
            continue
        match = re.fullmatch(r"第?\s*([0-9一二三四五六七八九十]+)\s*版", part)
        if match:
            number = match.group(1)
            digits = "零一二三四五六七八九"
            if number.isdigit():
                number = int(number)
            elif re.fullmatch(r"[一二三四五六七八九]?十[一二三四五六七八九]?", number):
                tens, units = number.split("十", 1)
                number = (digits.index(tens) if tens else 1) * 10 + (digits.index(units) if units else 0)
            elif len(number) == 1:
                number = digits.index(number)
            else:
                parts.append(part)
                continue
            part = f"{number}版"
        parts.append(part)
    return ", ".join(part + "." if re.search(r"\bed$", part, re.I) else part for part in parts)


def _edition_text(values):
    return citation_edition(values.get("edition_statement") or values.get("version_label"))


def _join_names(names, conjunction="and"):
    if len(names) < 2:
        return names[0] if names else "佚名"
    return f"{names[0]} {conjunction} {names[1]}" if len(names) == 2 and conjunction == "and" else f"{', '.join(names[:-1])}, {conjunction} {names[-1]}"


def _natural_name(name):
    if "," in name:
        family, given = name.split(",", 1)
        return f"{given.strip()} {family.strip()}"
    return name


def _editors(edition, snapshot):
    return _contributors(edition, snapshot, Contribution.Role.EDITOR) + _contributors(edition, snapshot, Contribution.Role.CHIEF_EDITOR)


def _sentence(text):
    return text.rstrip(".") + "."


def _doi_url(value):
    return "https://doi.org/" + re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", str(value).strip(), flags=re.I)


def _locator(reference, page_label, style, authors, year):
    """Book reference lists do not append a quoted page as publication pagination."""
    if not page_label:
        return reference
    short_names = [name.split(",", 1)[0] for name in authors]
    lead = short_names[0] if short_names else "佚名"
    if len(authors) > 2:
        lead += " et al."
    elif len(authors) == 2:
        lead = f"{short_names[0]} {'&' if style == 'apa' else 'and'} {short_names[1]}"
    pages = f"{'pp.' if re.search(r'[-–—,，]', page_label) else 'p.'} {page_label}"
    if style == "mla":
        locator = f"({lead} {page_label})"
    else:
        locator = f"({lead}, {year}, {pages})"
    return f"{reference}\n\n文内引用：{locator}"


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
                "container_title": edition.container_title,
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
        return ", ".join(names)
    suffix = "等" if re.search(r"[\u3400-\u9fff]", "".join(names)) else "et al."
    return f"{', '.join(names[:3])}, {suffix}"


def _gbt_page(page_label: str) -> str:
    return f": {page_label}" if page_label else ""


def format_gbt_7714_2025(
    edition: Edition,
    page_label: str = "",
    *,
    snapshot: dict | None = None,
) -> str:
    work, values = _snapshot_values(edition, snapshot)
    people = _contributors(edition, snapshot) or _editors(edition, snapshot)
    authors = _gbt_author_text(people)
    author_prefix = f"{_sentence(authors)} " if people else ""
    year = values.get("publication_year") or "出版年不详"
    page = _gbt_page(page_label)

    if work.get("document_type") == DocumentType.JOURNAL_ARTICLE:
        medium = "J/OL" if values.get("doi") else "J"
        volume = f", {values.get('volume')}" if values.get("volume") else ""
        issue = f"({values.get('issue')})" if values.get("issue") else ""
        pages = _gbt_page(page_label or values.get("page_range") or "")
        doi = f". DOI:{values.get('doi')}" if values.get("doi") else ""
        return (
            f"{author_prefix}{work.get('title') or '未题名'}[{medium}]. "
            f"{values.get('journal_title') or '刊名不详'}, {year}{volume}{issue}{pages}{doi}."
        )

    places = _publication_places(edition, values, snapshot)
    primary_place = places[0] if places else ""

    if work.get("document_type") == DocumentType.THESIS:
        return (
            f"{author_prefix}{work.get('title') or '未题名'}[D]. "
            f"{primary_place + ': ' if primary_place else ''}"
            f"{values.get('degree_institution') or '授予单位不详'}, {year}{page}."
        )

    if work.get("document_type") == DocumentType.REPORT:
        institution = values.get("report_institution") or values.get("publisher") or "责任机构不详"
        place = f"{primary_place}: " if primary_place else ""
        return f"{author_prefix}{work.get('title') or '未题名'}[R]. {place}{institution}, {year}{page}."

    if work.get("document_type") == DocumentType.CHAPTER:
        pages = _gbt_page(page_label or values.get("page_range") or "")
        return f"{author_prefix}{work.get('title') or '未题名'}[M]//{values.get('container_title') or '论文集名称待补'}. {primary_place + ': ' if primary_place else ''}{values.get('publisher') or '出版者不详'}, {year}{pages}."
    if work.get("document_type") == DocumentType.OTHER:
        return f"{author_prefix}{work.get('title') or '未题名'}[Z]. {values.get('publisher') or '出版者不详'}, {year}{page}."

    place = primary_place or "[出版地不详]"
    publisher = values.get("publisher") or "出版者不详"
    version = _edition_text(values)
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    translation = f" {_gbt_author_text(translators)}, 译." if translators else ""
    edition_statement = f" {version.rstrip('.')}." if version else ""
    return f"{author_prefix}{work.get('title') or '未题名'}[M].{translation}{edition_statement} {place}: {publisher}, {year}{page}."


def format_apa(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    work, values = _snapshot_values(edition, snapshot)
    authors = _contributors(edition, snapshot)
    editors = _editors(edition, snapshot) if not authors else []
    people = authors or editors
    names = _join_names(people, "&") if len(people) <= 20 else f"{', '.join(people[:19])}, … {people[-1]}"
    if editors:
        names = names.rstrip(".") + (". (Ed.)" if len(editors) == 1 else ". (Eds.)")
    year = values.get("publication_year") or "n.d."
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    extra = [f"{_join_names([_natural_name(name) for name in translators], '&')}, Trans." if translators else "", _edition_text(values)]
    details = f" ({'; '.join(item for item in extra if item)})" if any(extra) else ""
    title = work.get('title') or '未题名'
    reference = (f"{_sentence(names)} ({year}). {title}{details}." if people else f"{title}{details}. ({year}).") + f" {values.get('publisher') or values.get('journal_title') or ''}."
    if values.get("doi"):
        reference += " " + _doi_url(values["doi"])
    return _locator(reference, page_label, "apa", authors, year)


def format_chicago(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    work, values = _snapshot_values(edition, snapshot)
    authors = _contributors(edition, snapshot)
    editors = _editors(edition, snapshot) if not authors else []
    people = authors or editors
    ordered = [people[0], *[_natural_name(name) for name in people[1:]]] if people else []
    names = _join_names(ordered) if len(ordered) <= 6 else f"{', '.join(ordered[:3])}, et al."
    if editors:
        names += ", ed." if len(editors) == 1 else ", eds."
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    details = [f"Translated by {_join_names(translators)}" if translators else "", _edition_text(values)]
    extra = "".join(f" {item.rstrip('.')}." for item in details if item)
    year = values.get("publication_year") or "n.d."
    reference = (f"{_sentence(names)} " if people else "") + f"{work.get('title') or '未题名'}.{extra} {values.get('publisher') or values.get('journal_title') or ''}, {year}."
    if page_label:
        note = f"{_join_names([_natural_name(name) for name in people])}, {work.get('title') or '未题名'}"
        if translators:
            note += f", trans. {_join_names(translators)}"
        if _edition_text(values):
            note += f", {_edition_text(values)}"
        reference += f"\n\n脚注：{note} ({values.get('publisher') or ''}, {year}), {page_label}."
    return reference


def format_mla(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    work, values = _snapshot_values(edition, snapshot)
    authors = _contributors(edition, snapshot)
    editors = _editors(edition, snapshot) if not authors else []
    people = authors or editors
    ordered = [people[0], *[_natural_name(name) for name in people[1:]]] if people else []
    names = f"{ordered[0]}, et al." if len(ordered) > 2 else _join_names(ordered)
    if editors:
        names += ", editor" if len(editors) == 1 else ", editors"
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    details = [f"Translated by {_join_names(translators)}" if translators else "", _edition_text(values), values.get('publisher') or values.get('journal_title') or '', str(values.get('publication_year') or 'n.d.')]
    reference = (f"{_sentence(names)} " if people else "") + f"{work.get('title') or '未题名'}. {', '.join(item for item in details if item)}."
    if values.get("doi"):
        reference += " " + _doi_url(values["doi"]) + "."
    return _locator(reference, page_label, "mla", authors, values.get('publication_year') or 'n.d.')


def format_harvard(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    """Leeds Harvard: a named variant, not an alias for APA."""
    work, values = _snapshot_values(edition, snapshot)
    authors = _contributors(edition, snapshot)
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    year = values.get('publication_year') or 'n.d.'
    places = _publication_places(edition, values, snapshot)
    details = [_edition_text(values), f"Translated by {_join_names(translators)}" if translators else ""]
    extra = "".join(f" {item.rstrip('.')}." for item in details if item)
    editors = _editors(edition, snapshot) if not authors else []
    names = _sentence(_join_names(authors or editors)) if authors or editors else ""
    if editors:
        names += " ed." if len(editors) == 1 else " eds."
    reference = f"{names} {year}. {work.get('title') or '未题名'}.{extra} {places[0] + ': ' if places else ''}{values.get('publisher') or values.get('journal_title') or ''}."
    return _locator(reference, page_label, "harvard", authors, year)


def _snapshot_csl(edition: Edition, snapshot: dict | None) -> dict:
    work, values = _snapshot_values(edition, snapshot)
    authors = [
        {"literal": name}
        for name in _contributors(edition, snapshot)
    ]
    year = values.get("publication_year")
    return {
        **(edition.citation_data if snapshot is None else {}),
        "id": str(edition.id),
        "type": {"book": "book", "journal_article": "article-journal", "journal_issue": "periodical", "chapter": "chapter", "thesis": "thesis", "report": "report", "other": "document"}.get(work.get("document_type"), "document"),
        "title": work.get("title") or "未题名",
        "author": authors,
        "translator": [{"literal": name} for name in _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)],
        "editor": [{"literal": name} for name in _editors(edition, snapshot)],
        "edition": _edition_text(values),
        "publisher": values.get("publisher") or "",
        "container-title": values.get("container_title") or values.get("journal_title") or "",
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
        "harvard": format_harvard(edition, page_label, snapshot=snapshot),
        "csl": _snapshot_csl(edition, snapshot),
    }
