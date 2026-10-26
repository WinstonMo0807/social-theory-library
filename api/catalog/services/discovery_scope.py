"""Searchable fields over existing text slices; source text stays authoritative."""
from catalog.services.text import normalize_search_text, page_text_range

SCOPE_FIELDS = {"title": "title", "body": "body_text", "notes": "notes_text", "topics": "topics_text", "authors": "authors", "terms": "normalized_text"}
NOTE_TYPES = {"footnote", "footnotes", "endnote", "endnotes", "note", "annotation"}


def unit_exclusions(page, text, start, end):
    """Only explicit extractor block types can classify a note, never typography guesses."""
    location = page_text_range(page.text, text, start, end)
    if location is None:
        return []
    ranges, cursor = [], 0
    for block in page.blocks.all():
        value = block.text.strip()
        if not value:
            continue
        at = page.text.find(value, cursor)
        if at < 0:
            continue
        cursor = at + len(value)
        kind = block.block_type.lower()
        if kind not in NOTE_TYPES | {"header", "footer"}:
            continue
        left, right = max(at, location["start"]), min(cursor, location["end"])
        if left < right:
            ranges.append((left - location["start"], right - location["start"], kind in NOTE_TYPES))
    return ranges


def chunk_fields(header, unit, child):
    body, notes, cursor = [], [], child["start"]
    for start, end, is_note in unit.get("scope_exclusions", []):
        left, right = max(start, child["start"]), min(end, child["end"])
        if left >= right:
            continue
        body.append(unit["text"][cursor:left])
        if is_note:
            notes.append(unit["text"][left:right])
        cursor = right
    body.append(unit["text"][cursor:child["end"]])
    topics = [str(item.get("name") or item.get("title") or "") for item in header.get("topics", []) if isinstance(item, dict)]
    return {"body_text": normalize_search_text("\n".join(body)), "notes_text": normalize_search_text("\n".join(notes)),
        "topics_text": normalize_search_text("\n".join(topics))}
