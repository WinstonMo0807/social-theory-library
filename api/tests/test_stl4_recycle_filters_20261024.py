"""Deferred acceptance for scoped recovery filters and actual image references."""
import pytest
from django.core.files.base import ContentFile

from accounts.models import User
from catalog.models import Asset, Edition, Person, RecycleEntry, Work
from catalog.recycle_workspace import directory, source_file_check
from ingestion.models import AuditEvent


@pytest.mark.django_db
def test_recycle_filters_apply_before_pagination_and_preserve_recorded_reason(admin_user):
    other = User.objects.create_user(username="other-recycle-editor", role="admin", display_name="另一编辑")
    selected = None
    for index in range(22):
        work = Work.objects.create(title=f"待恢复条目 {index}", cover="public/covers/recorded.jpg")
        RecycleEntry.objects.create(model_label="catalog.work", object_id=work.pk, kind="work", name=work.title,
            deleted_by=admin_user if index == 0 else other,
            before={"_recycle_reason": "误删待恢复" if index == 0 else "内容调整"})
        if index == 0:
            selected = work
    result = directory(actor=admin_user, operator=str(admin_user.pk), reason="误删")
    assert result["count"] == 1 and result["counts"]["deleted"] == 1
    assert result["results"][0]["object_id"] == str(selected.pk)
    assert result["results"][0]["reason"] == "误删待恢复"
    assert result["results"][0]["cover_url"].endswith("public/covers/recorded.jpg")
    assert result["operators"] == [{"id": str(admin_user.pk), "label": admin_user.display_name}]


@pytest.mark.django_db
def test_archived_operator_comes_from_original_event_without_inventing_reason(admin_user):
    person = Person.objects.create(preferred_name="待恢复人物", authority_status="archived")
    AuditEvent.objects.create(actor=admin_user, action="entity_archive", object_type="catalog.Person",
        object_id=str(person.pk), after={"status": "archived"})
    result = directory(actor=admin_user, state="archived", operator=str(admin_user.pk))
    assert result["count"] == 1
    assert result["results"][0]["actor_id"] == str(admin_user.pk)
    assert result["results"][0]["reason"] == ""
    assert directory(actor=admin_user, state="archived", reason="误删")["count"] == 0


@pytest.mark.django_db
def test_restore_checks_retained_original_files_without_writing_them(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="原件保留核对")
    edition = Edition.objects.create(work=work, version_label="版本")
    asset = Asset.objects.create(edition=edition, kind=Asset.Kind.ORIGINAL, sha256="a" * 64,
        byte_size=8, is_current=False, file=ContentFile(b"original", name="original.pdf"))
    assert source_file_check(work, "work")["state"] == "checked"
    assert asset.file.read() == b"original"
    asset.file.close()
    asset.byte_size = 9
    asset.save(update_fields=["byte_size"])
    assert source_file_check(edition, "edition")["checks"][0]["state"] == "size_changed"
    asset.file.storage.delete(asset.file.name)
    result = source_file_check(work, "work")
    assert result["state"] == "blocked" and result["checks"][0]["state"] == "missing"
    assert result["blockers"] and Asset.objects.filter(pk=asset.pk).exists()
