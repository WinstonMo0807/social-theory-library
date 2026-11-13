import re
import unicodedata

from catalog.models import Contribution, DocumentType, Edition
from catalog.services.contribution_scope import whole_edition_contribution
from catalog.services.publication_places import confirmed_publication_places


def _citation_name(preferred, confirmed, *, gbt=False):
    # GB/T permits a translated Western surname alone. That abbreviation is
    # not a replacement for the complete name in other reference styles.
    if confirmed and (gbt or not re.search(r"[\u3400-\u9fff]", confirmed)):
        return confirmed
    return preferred or confirmed


def _contributors(edition: Edition, snapshot: dict | None = None, role=Contribution.Role.AUTHOR, *, gbt=False) -> list[str]:
    if snapshot:
        return [
            _citation_name(str((row.get("person") or {}).get("preferred_name") or row.get("name") or ""), str((row.get("person") or {}).get("citation_name") or ""), gbt=gbt)
            for row in snapshot.get("contributions") or []
            if isinstance(row, dict)
            and row.get("role") == role and whole_edition_contribution(row)
            and ((row.get("person") or {}).get("preferred_name") or row.get("name"))
        ]
    return [_citation_name(row.person.preferred_name, row.person.citation_name, gbt=gbt) for row in edition.contributions.filter(
        role=role, approved=True).select_related("person").order_by("order") if whole_edition_contribution(row)]


def citation_edition(value) -> str:
    """Clean a display label for citation only; preserve original catalog metadata."""
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    # Catalogue labels also contain publisher/year, scan and binding notes.
    # For a translated edition, its own edition number takes precedence over
    # an explicitly labelled original-language edition number.
    if re.search(r"(?:中文|中译本?).*第?[0-9一二三四五六七八九十]+版", value):
        value = re.sub(r"原著第?[0-9一二三四五六七八九十]+版[;；,，]?", "", value)
    # Copyright-page dates and print runs are not edition statements.
    value = re.sub(r"\d{4}\s*年(?:\s*\d{1,2}\s*月)?(?:\s*\d{1,2}\s*日)?", "", value)
    parts = []
    for part in re.split(r"[,，;；、\n]", value):
        if re.search(r"[\u3400-\u9fff]", part):
            edition = re.search(r"(?:新)?第?\s*[0-9零一二三四五六七八九十]+\s*版", part)
            revision = re.search(r"修订译本|修订版|增订本|增订版|增补版|影印本|影印版", part)
            part = ", ".join(x.group(0) for x in (edition, revision) if x)
            if not part:
                continue
            if edition and revision:
                parts.append(revision.group(0))
                part = edition.group(0)
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


def _join_names(names, conjunction="and", *, serial_comma=True):
    if len(names) < 2:
        return names[0] if names else "佚名"
    separator = ", " if serial_comma and (len(names) > 2 or conjunction == "&" or ',' in names[0]) else " "
    return f"{', '.join(names[:-1])}{separator}{conjunction} {names[-1]}"


def _name_parts(name):
    # An explicit cataloguing comma establishes order. Never split on the last
    # space or middle dot: Chinese, Arabic and compound family names differ.
    name = re.sub(r"\s+", " ", str(name)).strip()
    parts = [part.strip() for part in name.split(",")]
    if 2 <= len(parts) <= 3 and parts[0] and parts[1] and not re.search(r"[\u3400-\u9fff]", name):
        return parts[0], parts[1], parts[2] if len(parts) == 3 else ""
    return name, "", ""


def _initials(given, compact=False):
    words = re.findall(r"[^\W\d_]+(?:[-‐‑][^\W\d_]+)*", given, re.UNICODE)
    result = " ".join("-".join(part[0].upper() + "." for part in re.split(r"[-‐‑]", word)) for word in words)
    return result.replace(" ", "") if compact else result


def _name(name, style, *, natural=False):
    family, given, suffix = _name_parts(name)
    if not given:
        return family
    if style in {"apa", "harvard", "gbt"}:
        given = _initials(given, compact=style == "harvard")
    if style == "gbt":
        return " ".join(value for value in [family, given.replace(".", ""), suffix] if value)
    if natural:
        return f"{given} {family}" + (f", {suffix}" if suffix else "")
    return f"{family}, {given}" + (f", {suffix}" if suffix else "")


def _natural_name(name):
    return _name(name, "full", natural=True)


def _editors(edition, snapshot, *, gbt=False):
    return _contributors(edition, snapshot, Contribution.Role.EDITOR, gbt=gbt) + _contributors(edition, snapshot, Contribution.Role.CHIEF_EDITOR, gbt=gbt)


def _sentence(text):
    return text if text.endswith((".", "?", "!", "。", "？", "！")) else text + "."


def _doi_url(value):
    return "https://doi.org/" + re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", str(value).strip(), flags=re.I)


def _harvard_online(doi):
    from django.utils import timezone
    today = timezone.localdate()
    month = ("January February March April May June July August September October November December".split())[today.month - 1]
    return f"[Accessed {today.day} {month} {today.year}]. Available from: {_doi_url(doi)}"


def _pages(value, *, compact=False):
    return f"{'pp.' if re.search(r'[-–—,，]', str(value)) else 'p.'}{'' if compact else ' '}{value}"


def _other_format(edition, snapshot, style, page):
    from catalog.services.citation_types import format_nonbook
    work, values = _snapshot_values(edition, snapshot)
    if work.get('document_type', 'book') == 'book':
        return None
    return format_nonbook(work, values, _contributors(edition, snapshot),
                          _editors(edition, snapshot), style, page,
                          translators=_contributors(edition, snapshot, Contribution.Role.TRANSLATOR))


def _locator(reference, page_label, style, authors, year, title="未题名"):
    """Book reference lists do not append a quoted page as publication pagination."""
    if not page_label:
        return reference
    short_names = [_name_parts(name)[0] for name in authors]
    lead = short_names[0] if short_names else title
    if len(authors) > 2:
        lead += " et al."
    elif len(authors) == 2:
        lead = f"{short_names[0]} {'&' if style == 'apa' else 'and'} {short_names[1]}"
    pages = _pages(page_label, compact=style == "harvard")
    if style == "harvard" and re.fullmatch(r"[ivxlcdm]+", page_label, re.I):
        pages = page_label
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
                "first_publication_date": edition.work.first_publication_date,
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
                "degree_type": edition.degree_type,
            },
        )
    work, values = dict(snapshot.get("work") or {}), snapshot.get("edition") or {}
    # A volume designation identifies the cited book, unlike a print run. Some
    # existing catalogue records carry 上卷/下卷 only in their version label.
    if work.get("document_type") == "book":
        volume = re.search(r"(?<![\u3400-\u9fff])([上中下]卷)(?![\u3400-\u9fff])", str(values.get("version_label") or ""))
        if volume and volume.group(1) not in work.get("title", ""):
            work["title"] = f"{work.get('title') or '未题名'}: {volume.group(1)}"
    return work, values


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
    names = [_name(name, "gbt") for name in names]
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
    people = _contributors(edition, snapshot, gbt=True)
    if not people and work.get('document_type') not in {DocumentType.CHAPTER, DocumentType.JOURNAL_ARTICLE}:
        people = _editors(edition, snapshot, gbt=True)
    authors = _gbt_author_text(people)
    author_prefix = f"{_sentence(authors)} " if people else ""
    year = values.get("publication_year") or "出版年不详"
    page = _gbt_page(page_label)
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR, gbt=True)
    translation = f" {_gbt_author_text(translators)}, 译." if translators else ""

    if work.get("document_type") == DocumentType.JOURNAL_ARTICLE:
        medium = "J"
        volume = f", {values.get('volume')}" if values.get("volume") else ""
        issue = f"({values.get('issue')})" if values.get("issue") else ""
        pages = _gbt_page(page_label or values.get("page_range") or "")
        doi = f". DOI:{_doi_url(values['doi']).removeprefix('https://doi.org/')}" if values.get("doi") else ""
        return (
            f"{author_prefix}{work.get('title') or '未题名'}[{medium}].{translation} "
            f"{values.get('journal_title') or '刊名不详'}, {year}{volume}{issue}{pages}{doi}."
        )

    places = _publication_places(edition, values, snapshot)
    primary_place = places[0] if places else ""

    if work.get("document_type") == DocumentType.THESIS:
        return (
            f"{author_prefix}{work.get('title') or '未题名'}[D].{translation} "
            f"{primary_place + ': ' if primary_place else ''}"
            f"{values.get('degree_institution') or '授予单位不详'}, {year}{page}."
        )

    if work.get("document_type") == DocumentType.REPORT:
        institution = values.get("report_institution") or values.get("publisher") or "责任机构不详"
        place = f"{primary_place}: " if primary_place else ""
        return f"{author_prefix}{work.get('title') or '未题名'}[R].{translation} {place}{institution}, {year}{page}."

    if work.get("document_type") == DocumentType.CHAPTER:
        pages = _gbt_page(page_label or values.get("page_range") or "")
        editors = _editors(edition, snapshot, gbt=True)
        container_editors = _gbt_author_text(editors) + '. ' if editors else ''
        version = _edition_text(values)
        version_statement = f" {version.rstrip('.')}." if version else ''
        other_responsibility = f" {_gbt_author_text(translators)}, 译" if translators else ''
        return f"{author_prefix}{work.get('title') or '未题名'}[M]{'.' + other_responsibility if translators else ''}//{container_editors}{values.get('container_title') or '论文集名称待补'}.{version_statement} {primary_place + ': ' if primary_place else ''}{values.get('publisher') or '出版者不详'}, {year}{pages}."
    if work.get("document_type") == DocumentType.JOURNAL_ISSUE:
        volume = f", {values['volume']}" if values.get('volume') else ''
        issue = f"({values['issue']})" if values.get('issue') else ''
        return f"{author_prefix}{work.get('title') or values.get('journal_title') or '未题名'}[J].{translation} {year}{volume}{issue}{page}."
    if work.get("document_type") == DocumentType.OTHER:
        return f"{author_prefix}{work.get('title') or '未题名'}[Z].{translation} {values.get('publisher') or '出版者不详'}, {year}{page}."

    place = primary_place or "[出版地不详]"
    publisher = values.get("publisher") or "出版者不详"
    version = _edition_text(values)
    edition_statement = f" {version.rstrip('.')}." if version else ""
    return f"{author_prefix}{work.get('title') or '未题名'}[M].{translation}{edition_statement} {place}: {publisher}, {year}{page}."


def format_apa(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    other = _other_format(edition, snapshot, "apa", page_label)
    if other is not None:
        return other
    work, values = _snapshot_values(edition, snapshot)
    authors = _contributors(edition, snapshot)
    editors = _editors(edition, snapshot) if not authors else []
    people = [_name(name, 'apa') for name in authors or editors]
    names = _join_names(people, "&") if len(people) <= 20 else f"{', '.join(people[:19])}, … {people[-1]}"
    if editors:
        names = names.rstrip(".") + (". (Ed.)" if len(editors) == 1 else ". (Eds.)")
    year = values.get("publication_year") or "n.d."
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    secondary_editors = _editors(edition, snapshot) if authors else []
    same_responsible = bool(secondary_editors and secondary_editors == translators)
    editor_role = 'Ed.' if len(secondary_editors) == 1 else 'Eds.'
    extra = [
        f"{_join_names([_name(n, 'apa', natural=True) for n in secondary_editors], '&', serial_comma=len(secondary_editors) > 2)}, {editor_role}{' & Trans.' if same_responsible else ''}" if secondary_editors else '',
        f"{_join_names([_name(name, 'apa', natural=True) for name in translators], '&', serial_comma=len(translators) > 2)}, Trans." if translators and not same_responsible else "",
        _edition_text(values),
    ]
    details = f" ({'; '.join(item for item in extra if item)})" if any(extra) else ""
    title = work.get('title') or '未题名'
    reference = (f"{_sentence(names)} ({year}). {title}{details}." if people else f"{title}{details}. ({year}).")
    if values.get('publisher'):
        reference += f" {values['publisher']}."
    if values.get("doi"):
        reference += " " + _doi_url(values["doi"])
    original_year = str(work.get('first_publication_date') or '')[:4]
    if translators and original_year.isdigit() and int(original_year) < int(year if str(year).isdigit() else 0):
        reference += f" (Original work published {original_year})"
        year = f"{original_year}/{year}"
    return _locator(reference, page_label, "apa", authors or editors, year, title)


def format_chicago(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    other = _other_format(edition, snapshot, "chicago", page_label)
    if other is not None:
        return other
    work, values = _snapshot_values(edition, snapshot)
    authors = _contributors(edition, snapshot)
    editors = _editors(edition, snapshot) if not authors else []
    people = authors or editors
    ordered = [people[0], *[_natural_name(name) for name in people[1:]]] if people else []
    names = _join_names(ordered) if len(ordered) <= 6 else f"{', '.join(ordered[:3])}, et al."
    if editors:
        names += ", ed." if len(editors) == 1 else ", eds."
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    secondary_editors = _editors(edition, snapshot) if authors else []
    details = [f"Edited by {_join_names([_natural_name(n) for n in secondary_editors])}" if secondary_editors else '', f"Translated by {_join_names([_natural_name(n) for n in translators])}" if translators else "", _edition_text(values)]
    extra = "".join(f" {item.rstrip('.')}." for item in details if item)
    year = values.get("publication_year") or "n.d."
    publication = ', '.join(str(v) for v in [values.get('publisher') or values.get('journal_title'), year] if v)
    reference = (f"{_sentence(names)} " if people else "") + f"{work.get('title') or '未题名'}.{extra} {publication}."
    doi = _doi_url(values['doi']) if values.get('doi') else ''
    if doi:
        reference += f' {doi}.'
    if page_label:
        note_names = _natural_name(people[0]) + ' et al.' if len(people) > 2 else _join_names([_natural_name(name) for name in people]) if people else ''
        if editors:
            note_names += ', ed.' if len(editors) == 1 else ', eds.'
        note = f"{note_names + ', ' if note_names else ''}{work.get('title') or '未题名'}"
        if secondary_editors:
            note += f", ed. {_join_names([_natural_name(n) for n in secondary_editors])}"
        if translators:
            note += f", trans. {_join_names([_natural_name(n) for n in translators])}"
        if _edition_text(values):
            note += f", {_edition_text(values)}"
        reference += f"\n\n脚注：{note} ({publication}), {page_label}" + (f", {doi}" if doi else '') + '.'
    return reference


def format_mla(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    other = _other_format(edition, snapshot, "mla", page_label)
    if other is not None:
        return other
    work, values = _snapshot_values(edition, snapshot)
    authors = _contributors(edition, snapshot)
    editors = _editors(edition, snapshot) if not authors else []
    people = authors or editors
    ordered = [people[0], *[_natural_name(name) for name in people[1:]]] if people else []
    names = f"{ordered[0]}, et al." if len(ordered) > 2 else ', and '.join(ordered) if len(ordered) == 2 else _join_names(ordered)
    if editors:
        names += ", editor" if len(editors) == 1 else ", editors"
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    secondary_editors = _editors(edition, snapshot) if authors else []
    same_responsible = bool(secondary_editors and secondary_editors == translators)
    details = [f"{'Edited and translated' if same_responsible else 'Edited'} by {_join_names([_natural_name(n) for n in secondary_editors])}" if secondary_editors else '', f"Translated by {_join_names([_natural_name(n) for n in translators])}" if translators and not same_responsible else "", _edition_text(values), values.get('publisher') or values.get('journal_title') or '', str(values.get('publication_year') or 'n.d.')]
    reference = (f"{_sentence(names)} " if people else "") + f"{work.get('title') or '未题名'}. {', '.join(item for item in details if item)}."
    if values.get("doi"):
        reference += " " + _doi_url(values["doi"]) + "."
    return _locator(reference, page_label, "mla", authors or editors, values.get('publication_year') or 'n.d.', work.get('title') or '未题名')


def format_harvard(edition: Edition, page_label: str = "", *, snapshot: dict | None = None) -> str:
    """Leeds Harvard: a named variant, not an alias for APA."""
    other = _other_format(edition, snapshot, "harvard", page_label)
    if other is not None:
        return other
    work, values = _snapshot_values(edition, snapshot)
    authors = _contributors(edition, snapshot)
    year = values.get('publication_year') or 'n.d.'
    places = _publication_places(edition, values, snapshot)
    translators = _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)
    secondary_editors = _editors(edition, snapshot) if authors else []
    details = ['[Online]' if values.get('doi') else '', _edition_text(values),
               _join_names([_name(n, 'harvard') for n in secondary_editors], serial_comma=False) + (' ed.' if len(secondary_editors) == 1 else ' eds.') if secondary_editors else '',
               'Translated by ' + _join_names([_name(n, 'harvard', natural=True) for n in translators], serial_comma=False) if translators else '']
    extra = "".join(f" {item.rstrip('.')}." for item in details if item)
    editors = _editors(edition, snapshot) if not authors else []
    names = _sentence(_join_names([_name(n, 'harvard') for n in authors or editors], serial_comma=False)) if authors or editors else ""
    if editors:
        names += " ed." if len(editors) == 1 else " eds."
    title = work.get("title") or "未题名"
    lead = f"{names} {year}. {title}." if names else f"{title}. {year}."
    reference = f"{lead}{extra} {places[0] + ': ' if places else ''}{values.get('publisher') or values.get('journal_title') or ''}."
    if values.get('doi'):
        reference += ' ' + _harvard_online(values['doi'])
    return _locator(reference, page_label, "harvard", authors or editors, year, work.get('title') or '未题名')


def _snapshot_csl(edition: Edition, snapshot: dict | None) -> dict:
    work, values = _snapshot_values(edition, snapshot)
    authors = [
        _csl_name(name)
        for name in _contributors(edition, snapshot)
    ]
    year = values.get("publication_year")
    return {
        **(edition.citation_data if snapshot is None else {}),
        "id": str(edition.id),
        "type": {"book": "book", "journal_article": "article-journal", "journal_issue": "periodical", "chapter": "chapter", "thesis": "thesis", "report": "report", "other": "document"}.get(work.get("document_type"), "document"),
        "title": work.get("title") or "未题名",
        "author": authors,
        "translator": [_csl_name(name) for name in _contributors(edition, snapshot, Contribution.Role.TRANSLATOR)],
        "editor": [_csl_name(name) for name in _editors(edition, snapshot)],
        "edition": _edition_text(values),
        "publisher": values.get("publisher") or "",
        "container-title": values.get("container_title") or values.get("journal_title") or "",
        "issued": {"date-parts": [[year]]} if year else {},
        "DOI": values.get("doi") or "",
        "volume": values.get("volume") or "",
        "issue": values.get("issue") or "",
        **({"page": values["page_range"]} if values.get("page_range") else {}),
        "publisher-place": values.get("publication_place") or "",
    }


def _csl_name(name):
    family, given, suffix = _name_parts(name)
    return {"family": family, "given": given, **({"suffix": suffix} if suffix else {})} if given else {"literal": family}


def citation_metadata_notes(edition, snapshot):
    work, values = _snapshot_values(edition, snapshot)
    notes = []
    for row in snapshot.get('contributions', []):
        person = row.get('person') or {}
        name = person.get('preferred_name') or row.get('name') or ''
        if not person.get('citation_name') and (not re.search(r'[\u3400-\u9fff]', name) and re.search(r'[A-Za-z] [A-Za-z]', name) and ',' not in name):
            notes.append('部分责任者的姓与名尚未单独确认，暂保留原名；馆长可在人物资料中填写引用姓名。')
            break
    required = {'journal_article': [('journal_title', '刊名')], 'chapter': [('container_title', '论文集名称')],
                'thesis': [('degree_institution', '授予单位'), ('degree_type', '学位类型')], 'report': [('report_institution', '责任机构')]}
    missing = [label for field, label in required.get(work.get('document_type'), []) if not values.get(field) and not (field == 'report_institution' and values.get('publisher'))]
    if missing:
        notes.append('书目待补：' + '、'.join(missing) + '。')
    if work.get('document_type') == 'thesis':
        notes.append('APA 学位论文还须核对原发表库或未发表状态，当前馆藏未记录该信息。')
    if work.get('document_type') in {'other', 'journal_issue'}:
        notes.append('请按资料的具体类型或整期刊物的题名核对引用，当前显示已有书目信息。')
    return notes


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
