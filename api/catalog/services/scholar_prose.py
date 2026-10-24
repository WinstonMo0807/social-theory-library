"""Formatting belongs to the exact saved prose, never a second biography."""
from rest_framework.exceptions import ValidationError

from catalog.services.editorial_blocks import normalize_text_format

FIELDS = ("short_description", "biography")


def normalize_profile_prose(value):
    if not isinstance(value, dict) or set(value) - set(FIELDS):
        raise ValidationError({"profile_prose": "仅可设置导读和生平说明的文字格式。"})
    result = {}
    for field, row in value.items():
        if not isinstance(row, dict) or set(row) - {"text", "text_style", "text_marks"}:
            raise ValidationError({"profile_prose": "文字格式须包含对应正文和格式标记。"})
        text = row.get("text")
        if not isinstance(text, str) or len(text) > (400 if field == "short_description" else 30000):
            raise ValidationError({"profile_prose": "导读格式最多对应400字，生平格式最多对应30000字。原长文可保留纯文本。"})
        try:
            block = normalize_text_format(row, {"type": "paragraph", "text": text.strip()})
        except ValidationError as exc:
            raise ValidationError({"profile_prose": exc.detail}) from exc
        result[field] = {"text": block["text"], "text_style": block.get("text_style", "paragraph"), "text_marks": block.get("text_marks", [])}
    return result


def bound_profile_prose(curation, description, biography):
    """Old clients may change Person text without updating its optional marks.

    Ignore stale or malformed legacy marks, but preserve the authoritative text.
    Public callers must pass the published snapshot, never the live draft.
    """
    value = curation.get("profile_prose", {}) if isinstance(curation, dict) else {}
    if not isinstance(value, dict):
        return {}
    result = {}
    for field, text in zip(FIELDS, (description, biography)):
        row = value.get(field)
        if not isinstance(row, dict) or row.get("text") != text:
            continue
        try:
            result.update(normalize_profile_prose({field: row}))
        except ValidationError:
            continue
    return result
