"""Private labels and archive choices never rewrite text, public titles or memory grants."""
from django.db.models import BooleanField, F, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce, Greatest

from .material_models import ReaderMaterialPreference
from .services import decrypt_private_text, encrypt_private_text

CATEGORIES = {"research": "research", "annotations": "notes", "bookmarks": "bookmarks", "plans": "plans",
              "reading_lists": "lists", "audits": "audits", "memories": "confirmed", "saved_items": "saved"}


def get(user, kind, pk):
    return ReaderMaterialPreference.objects.filter(user=user, kind=kind, object_id=pk).first()


def revision(user, category, pk):
    kind = CATEGORIES.get(category)
    if kind is None:
        return None
    return ReaderMaterialPreference.objects.filter(user=user, kind=kind, object_id=pk).values_list("revision", flat=True).first() or 0


def annotate(rows, user, kind):
    preference = ReaderMaterialPreference.objects.filter(user=user, kind=kind, object_id=OuterRef("pk"))
    return rows.annotate(material_preference_revision=Coalesce(Subquery(preference.values("revision")[:1]), Value(0)),
        material_title_ciphertext=Subquery(preference.values("title_ciphertext")[:1]),
        material_archived=Coalesce(Subquery(preference.values("archived")[:1]), F("archived") if kind == "research" else Value(False), output_field=BooleanField()),
        material_updated_at=Greatest(F("updated_at"), Coalesce(Subquery(preference.values("updated_at")[:1]), F("updated_at"))))


def presentation(row, kind):
    if hasattr(row, "material_preference_revision"):
        return {"revision": row.material_preference_revision, "title": decrypt_private_text(row.material_title_ciphertext or b""),
                "archived": row.material_archived, "updated_at": row.material_updated_at}
    preference = get(row.user_id, kind, row.pk)
    return {"revision": preference.revision if preference else 0,
            "title": decrypt_private_text(preference.title_ciphertext) if preference else "",
            "archived": preference.archived if preference else bool(getattr(row, "archived", False)),
            "updated_at": max(row.updated_at, preference.updated_at) if preference else row.updated_at}


def save(user, kind, row, *, title=None, archived=None):
    preference = get(user, kind, row.pk)
    if preference is None:
        preference = ReaderMaterialPreference(user=user, kind=kind, object_id=row.pk)
    else:
        preference.revision += 1
    if title is not None:
        preference.title_ciphertext = encrypt_private_text(title)
    if archived is not None:
        preference.archived = archived
    preference.save()
    return preference


def export(user, category, row):
    kind = CATEGORIES.get(category)
    preference = get(user, kind, row.pk) if kind else None
    if not preference:
        return None
    return {"title": decrypt_private_text(preference.title_ciphertext), "archived": preference.archived,
            "revision": preference.revision, "updated_at": preference.updated_at.isoformat(),
            "notice": "本人在读者中心设置的显示名称与归档状态；原记录内容及公开题名保持独立。"}


def export_all(user):
    return [{"kind": row.kind, "object_id": str(row.object_id), "title": decrypt_private_text(row.title_ciphertext),
             "archived": row.archived, "revision": row.revision, "updated_at": row.updated_at.isoformat()}
            for row in ReaderMaterialPreference.objects.filter(user=user).order_by("kind", "object_id")]


def remove_for_deleted_material(sender, instance, **kwargs):
    model_kinds = {"researchproject": "research", "annotation": "notes", "bookmark": "bookmarks", "personalreadingplan": "plans",
                   "readinglist": "lists", "citationaudit": "audits", "researchmemory": "confirmed", "saveditem": "saved"}
    ReaderMaterialPreference.objects.filter(user_id=instance.user_id, kind=model_kinds[sender._meta.model_name], object_id=instance.pk).delete()
