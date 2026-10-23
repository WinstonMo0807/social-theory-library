"""Deferred acceptance for scoped recovery filters and actual image references."""
import pytest

from accounts.models import User
from catalog.models import Person, RecycleEntry, Work
from catalog.recycle_workspace import directory
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
