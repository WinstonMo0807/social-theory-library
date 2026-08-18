from django.db import migrations


SCOPE_ALIASES = {
    "": "global",
    "global": "global",
    "whole_library": "global",
    "library": "global",
    "work": "works",
    "selected_work": "works",
    "selected_works": "works",
    "works": "works",
    "scholar": "scholars",
    "scholars": "scholars",
    "author": "scholars",
    "authors": "scholars",
    "discipline": "disciplines",
    "disciplines": "disciplines",
    "subdiscipline": "subdisciplines",
    "subdisciplines": "subdisciplines",
    "theory": "theories",
    "theories": "theories",
    "theory_school": "theories",
    "topic": "topics",
    "topics": "topics",
    "reading_path": "reading_paths",
    "reading_paths": "reading_paths",
}

LEGACY_ID_KEYS = {
    "works": ("work_ids", "work_id"),
    "scholars": ("authors", "author"),
    "theories": ("theories", "theory_school"),
    "topics": ("topics", "topic"),
    "reading_paths": ("reading_paths", "reading_path"),
}


def _values(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        values = value
    else:
        values = [value]
    output = []
    seen = set()
    for item in values:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output[:12]


def _normalize_scope(value):
    if not isinstance(value, dict):
        return {"context": "global"}
    raw = str(value.get("context") or value.get("type") or "").strip().casefold()
    ids = value.get("ids")
    if not raw:
        for context, keys in LEGACY_ID_KEYS.items():
            for key in keys:
                if value.get(key):
                    raw = context
                    ids = value.get(key)
                    break
            if raw:
                break
    context = SCOPE_ALIASES.get(raw, "global")
    normalized = {"context": context}
    if context != "global":
        normalized["ids"] = _values(ids)
    if value.get("asset_id"):
        normalized["asset_id"] = str(value["asset_id"]).strip()
        if context == "global":
            normalized["context"] = "works"
    if value.get("visibility") in {"public", "admin"}:
        normalized["visibility"] = value["visibility"]
    return normalized


def normalize_conversations(apps, schema_editor):
    conversation_model = apps.get_model("reading", "LibraryConversation")
    queryset = conversation_model.objects.filter(assist_mode="off").only(
        "id", "assist_mode", "scope"
    )
    for conversation in queryset.iterator(chunk_size=500):
        conversation.assist_mode = "auto"
        conversation.scope = _normalize_scope(conversation.scope)
        conversation.save(update_fields=["assist_mode", "scope", "updated_at"])

    # Normalize scopes on conversations that did not use the historical OFF
    # mode as well.  This keeps the migration deterministic for mixed data.
    remaining = conversation_model.objects.exclude(assist_mode="off").only(
        "id", "scope"
    )
    for conversation in remaining.iterator(chunk_size=500):
        normalized = _normalize_scope(conversation.scope)
        if normalized != (conversation.scope or {}):
            conversation.scope = normalized
            conversation.save(update_fields=["scope", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("reading", "0005_library_ai_runtime_rag")]

    operations = [
        migrations.RunPython(normalize_conversations, migrations.RunPython.noop),
    ]
