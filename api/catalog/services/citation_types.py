"""Reference-list and locator templates for the catalog's non-book types.

Sources and executable examples: tests/test_citation_types_20261112.py.
Missing metadata is never inferred from a PDF filename or another edition.
"""
from catalog.services.citations import (
    _doi_url, _edition_text, _join_names, _locator, _name, _natural_name,
    _pages, _sentence, _harvard_online,
)


def _lead(people, style, *, editors=False, natural=False):
    if not people:
        return ""
    if style == 'apa':
        names = [_name(n, style, natural=natural) for n in people]
        result = _join_names(names, '&') if len(names) <= 20 else f"{', '.join(names[:19])}, … {names[-1]}"
        if editors:
            result += ' (Ed.)' if len(names) == 1 else ' (Eds.)'
        return result
    if style == 'harvard':
        result = _join_names([_name(n, style) for n in people], serial_comma=False)
        return result + (' ed.' if len(people) == 1 else ' eds.') if editors else result
    names = [_natural_name(n) if natural or i else n for i, n in enumerate(people)]
    if style == 'mla' and len(names) > 2:
        result = names[0] + ', et al.'
    elif style == 'chicago' and (len(names) > 6 or natural and len(names) > 2):
        result = ', '.join(names[:1 if natural else 3]) + ', et al.'
    else:
        # MLA's two-author reference retains the comma after the inverted name.
        result = ', and '.join(names) if style == 'mla' and len(names) == 2 and not natural else _join_names(names)
    if editors:
        result += (', editor' if len(people) == 1 else ', editors') if style == 'mla' else (', ed.' if len(people) == 1 else ', eds.')
    return result


def _degree(value, style):
    value = str(value or '').strip()
    doctoral = value.lower() in {'博士', '博士学位', '博士论文', '博士学位论文', 'phd', 'ph.d.', 'doctorate', 'doctoral'}
    masters = value.lower() in {'硕士', '硕士学位', '硕士论文', '硕士学位论文', 'master', 'masters', "master's"}
    if doctoral:
        return {'apa': 'Doctoral dissertation', 'chicago': 'PhD diss.', 'mla': 'PhD dissertation', 'harvard': 'Ph.D. thesis'}[style]
    if masters:
        return "Master's thesis" if style == 'apa' else "master's thesis"
    return value or '学位论文'


def format_nonbook(work, values, authors, editors, style, page, *, translators=()):
    kind = work.get('document_type')
    original_title = work.get('title') or '未题名'
    title = original_title
    if translators and style == 'apa':
        title += ' (' + _join_names([_name(n, 'apa', natural=True) for n in translators], '&', serial_comma=len(translators) > 2) + ', Trans.)'
    year = values.get('publication_year') or 'n.d.'
    publisher = values.get('publisher') or ''
    place = values.get('publication_place') or ''
    journal = values.get('journal_title') or ''
    container = values.get('container_title') or ''
    volume, issue, pages = (str(values.get(key) or '') for key in ('volume', 'issue', 'page_range'))
    doi = _doi_url(values['doi']) if values.get('doi') else ''
    # Only an entire edited work uses editors in place of authors.
    people = authors or (editors if kind in {'journal_issue', 'other'} else [])
    lead = _lead(people, style, editors=bool(people and not authors))
    prefix = _sentence(lead) + ' ' if lead else ''
    apa_prefix = f'{prefix}({year}). ' if lead else ''
    harvard_prefix = f'{prefix}{year}. ' if lead else ''
    edition = _edition_text(values)
    translated_names = _join_names([_natural_name(n) for n in translators]) if translators else ''
    translation = f'Translated by {translated_names}. ' if translators else ''
    note_translation = f'trans. {translated_names}, ' if translators else ''

    if kind == 'journal_article':
        journal = journal or '刊名不详'
        vol_issue = volume + (f'({issue})' if issue else '')
        if style == 'apa':
            body = f'{journal}' + (f', {vol_issue}' if vol_issue else '') + (f', {pages}' if pages else '')
            reference = f'{apa_prefix}{_sentence(title)} ' + (f'({year}). ' if not lead else '') + _sentence(body)
        elif style == 'mla':
            detail = [journal, f'vol. {volume}' if volume else '', f'no. {issue}' if issue else '', str(year), _pages(pages) if pages else '', doi]
            reference = f'{prefix}“{_sentence(title)}” {translation}' + _sentence(', '.join(x for x in detail if x))
            doi = ''
        elif style == 'chicago':
            detail = journal + (f' {volume}' if volume else '') + (f', no. {issue}' if issue else '') + f' ({year})'
            reference = f'{prefix}“{_sentence(title)}” {translation}{detail}' + (f': {pages}' if pages else '') + '.'
            if doi:
                reference += f' {doi}.'
            if page:
                reference += f'\n\n脚注：{_lead(people, style, natural=True) + ", " if people else ""}“{title.rstrip(".")},” {note_translation}{detail}: {page}' + (f', {doi}' if doi else '') + '.'
            return reference
        else:
            reference = f'{harvard_prefix}{_sentence(title)} {journal}. ' + ('[Online]. ' if doi else '')
            reference += _sentence(', '.join(x for x in [vol_issue, _pages(pages, compact=True) if pages else ''] if x)) if vol_issue or pages else ''
    elif kind == 'chapter':
        container = container or '论文集名称待补'
        if style == 'apa':
            editor_names = _join_names([_name(n, 'apa', natural=True) for n in editors], '&', serial_comma=len(editors) > 2)
            editor_text = f'{editor_names} ({"Ed." if len(editors) == 1 else "Eds."}), ' if editors else ''
            extra = ', '.join(x for x in [edition, _pages(pages) if pages else ''] if x)
            reference = f'{apa_prefix}{_sentence(title)} ' + (f'({year}). ' if not lead else '') + f'In {editor_text}{container}' + (f' ({extra})' if extra else '') + '.' + (f' {publisher}.' if publisher else '')
        elif style == 'mla':
            extra = [container, f'edited by {_lead(editors, style, natural=True)}' if editors else '', edition, publisher, str(year), _pages(pages) if pages else '', doi]
            reference = f'{prefix}“{_sentence(title)}” {translation}' + _sentence(', '.join(x for x in extra if x))
            doi = ''
        elif style == 'chicago':
            # Chicago 18 no longer requires chapter pagination in bibliography;
            # retaining the full range is useful and distinguishes it from a note.
            tail = f'In {container}' + (f', edited by {_lead(editors, style, natural=True)}' if editors else '')
            reference = f'{prefix}“{_sentence(title)}” {translation}{tail}' + (f', {pages}' if pages else '') + '.'
            reference += (f' {_sentence(edition)}' if edition else '') + f' {publisher + ", " if publisher else ""}{year}.'
            if doi:
                reference += f' {doi}.'
            if page:
                reference += f'\n\n脚注：{_lead(people, style, natural=True) + ", " if people else ""}“{title.rstrip(".")},” {note_translation}in {container}' + (f', ed. {_lead(editors, style, natural=True)}' if editors else '') + f' ({publisher + ", " if publisher else ""}{year}), {page}' + (f', {doi}' if doi else '') + '.'
            return reference
        else:
            edit = _lead(editors, style, editors=True)
            reference = f'{harvard_prefix}{_sentence(title)} In: {edit + " " if edit else ""}{container}.'
            if edition:
                reference += f' {_sentence(edition)}'
            reference += f' {place + ": " if place else ""}{publisher}' + (f', {_pages(pages, compact=True)}' if pages else '') + '.'
    elif kind == 'thesis':
        institution = values.get('degree_institution') or '授予单位不详'
        degree = _degree(values.get('degree_type'), style)
        if style == 'apa':
            # Holding a local PDF does not establish a repository publication.
            # Do not label it "unpublished" or invent a repository/URL.
            reference = f'{apa_prefix}{title} [{degree}, {institution}].' + (f' ({year}).' if not lead else '')
        elif style == 'mla':
            reference = f'{prefix}{_sentence(title)} {translation}{year}. {institution}, {degree}.'
        elif style == 'chicago':
            reference = f'{prefix}“{_sentence(title)}” {translation}{degree}, {institution}, {year}.'
            if page:
                reference += f'\n\n脚注：{_lead(people, style, natural=True) + ", " if people else ""}“{title.rstrip(".")},” {note_translation}({degree}, {institution}, {year}), {page}.'
            return reference
        else:
            reference = f'{harvard_prefix}{_sentence(title)} {degree}, {institution}.'
    elif kind == 'report':
        institution = values.get('report_institution') or publisher
        if style == 'apa':
            reference = f'{apa_prefix}{_sentence(title)}' + (f' ({year}).' if not lead else '')
            if institution and institution not in authors:
                reference += f' {institution}.'
        elif style == 'harvard':
            reference = f'{harvard_prefix}{_sentence(title)} {place + ": " if place else ""}{institution}.'
        else:
            reference = f'{prefix}{_sentence(title)} {translation}{institution + ", " if institution else ""}{year}.'
            if style == 'chicago' and page:
                reference += f'\n\n脚注：{_lead(people, style, natural=True) + ", " if people else ""}{title}, {note_translation}({institution + ", " if institution else ""}{year}), {page}.'
    elif kind == 'journal_issue':
        # Regular whole issues must not silently masquerade as authored books
        # or be called a "special issue" without that metadata.
        if style == 'apa':
            reference = f'{apa_prefix}{title} [期刊整期]. ' + (f'({year}). ' if not lead else '') + f'{journal or title}' + (f', {volume}' if volume else '') + (f'({issue})' if issue else '') + '.'
        else:
            reference = f'{harvard_prefix if style == "harvard" else prefix}{title} [期刊整期]. {journal or title}' + (f', vol. {volume}' if volume else '') + (f', no. {issue}' if issue else '') + (f', {year}' if style != 'harvard' else '') + '.'
    else:
        reference = f'{apa_prefix if style == "apa" else harvard_prefix if style == "harvard" else prefix}{title} [资料类型待核对].'
        if not lead and style in {'apa', 'harvard'}:
            reference += f' ({year}).' if style == 'apa' else f' {year}.'
        if publisher:
            reference += f' {publisher}.'
        if style in {'chicago', 'mla'}:
            reference += f' {year}.'

    if not lead and style == 'harvard':
        reference = reference.replace(_sentence(title), f'{_sentence(title)} {year}.', 1)
    if translators and style == 'harvard':
        translated = 'Translated by ' + _join_names([_name(n, 'harvard', natural=True) for n in translators], serial_comma=False) + '. '
        reference = reference.replace('].', ']. ' + translated, 1) if kind in {'journal_issue', 'other'} else reference.replace(_sentence(title), _sentence(title) + ' ' + translated, 1)
    elif translators and style in {'mla', 'chicago'} and kind in {'journal_issue', 'other'}:
        reference = reference.replace('].', ']. ' + translation, 1)
    if doi:
        if style == 'harvard':
            if kind != 'journal_article':
                reference = reference.replace(_sentence(title), _sentence(title) + ' [Online].', 1)
            reference += ' ' + _harvard_online(doi)
        else:
            reference += f' {doi}' + ('' if style == 'apa' else '.')
    original_year = str(work.get('first_publication_date') or '')[:4]
    if style == 'apa' and translators and original_year.isdigit() and str(year).isdigit() and int(original_year) < int(year):
        reference += f' (Original work published {original_year})'
        year = f'{original_year}/{year}'
    return _locator(reference.strip(), page, style, people, year, original_title) if style != 'chicago' else reference.strip()
