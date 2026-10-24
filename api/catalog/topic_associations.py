"""Per-selection editorial explanations, stored in the original Topic.curation."""
from rest_framework.exceptions import ValidationError

NOTE_LIMIT = 600
TOTAL_NOTE_LIMIT = 60000


def validate_association_notes(curation, fields):
    if "association_notes" not in curation:
        return
    notes = curation["association_notes"]
    if not isinstance(notes, dict) or set(notes) - set(fields):
        raise ValidationError({"association_notes": "关联说明须按已有内容分类填写。"})
    cleaned, total = {}, 0
    for field, entries in notes.items():
        selected = set(curation.get(field) or [])
        if not isinstance(entries, dict) or len(entries) > len(selected):
            raise ValidationError({"association_notes": "说明只能对应本次选入的内容。"})
        group = {}
        for identifier, text in entries.items():
            if identifier not in selected or not isinstance(text, str) or len(text) > NOTE_LIMIT:
                raise ValidationError({"association_notes": f"每项说明最多 {NOTE_LIMIT} 字，且必须对应本分类已选入的内容。"})
            text = text.strip()
            if text:
                group[identifier] = text
                total += len(text)
        if group:
            cleaned[field] = group
    if total > TOTAL_NOTE_LIMIT:
        raise ValidationError({"association_notes": "主题关联说明总量过大，请精简后保存。"})
    curation["association_notes"] = cleaned


def association_note(topic, identifier, *fields):
    """Only call after the associated object passed its existing public filters."""
    curation = topic.curation if isinstance(topic.curation, dict) else {}
    notes = curation.get("association_notes")
    if not isinstance(notes, dict):
        return ""
    identifier = str(identifier)
    for field in fields:
        group = notes.get(field)
        if identifier not in (curation.get(field) or []) or not isinstance(group, dict):
            continue
        value = group.get(identifier)
        if isinstance(value, str) and value.strip():
            return value.strip()[:NOTE_LIMIT]
    return ""


def annotated_rows(rows, topic, field):
    return [{**row, "curation_note": association_note(topic, row["id"], field)} for row in rows]
