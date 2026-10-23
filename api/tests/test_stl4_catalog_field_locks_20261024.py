"""Deferred acceptance: explicit field protection preserves original content and receipts."""
from uuid import uuid4
import pytest
from rest_framework.exceptions import PermissionDenied
from catalog.models import Work, Edition
from catalog.services import field_locks
from catalog.services.workspace_edits import save_workspace_edits, workspace_edit_version
from catalog.services.work_editor import WorkflowEditConflict, WorkflowEditError
from ingestion.models import AuditEvent, FieldLock

pytestmark = pytest.mark.django_db


def command(edition, actor, action="lock", field="title", **options):
    return dict(work_id=edition.work_id, edition_id=edition.pk, actor=actor, expected_version=workspace_edit_version(edition),
                request_id=str(uuid4()), sections={}, confirmations=set(), suggestions=[],
                field_locks=[{"field": field, "action": action, "reason": "人工核对后的明确决定"}], **options)


def test_lock_receipt_replay_and_unlock_leave_values_untouched(admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="已核对题名"), publication_year=2020)
    data = command(edition, admin_user)
    _, receipt, replayed = save_workspace_edits(**data)
    assert not replayed and FieldLock.objects.get(edition=edition, field_name="title").locked_value == "已核对题名"
    assert save_workspace_edits(**data)[2] is True
    assert AuditEvent.objects.filter(request_id=data["request_id"]).count() == 1
    save_workspace_edits(**command(edition, admin_user, action="unlock"))
    edition.refresh_from_db(); edition.work.refresh_from_db()
    assert edition.work.title == "已核对题名" and edition.publication_year == 2020 and edition.state == "draft"
    assert not FieldLock.objects.filter(edition=edition).exists()
    assert receipt.after["field_locks"][0]["scope"] == "work"


def test_work_field_locks_span_editions_but_publication_fields_do_not(admin_user):
    work = Work.objects.create(title="共有题名")
    first, second = Edition.objects.create(work=work), Edition.objects.create(work=work)
    stale = command(second, admin_user)
    save_workspace_edits(**command(first, admin_user))
    assert workspace_edit_version(second) != stale["expected_version"]
    with pytest.raises(WorkflowEditConflict): save_workspace_edits(**stale)
    lock = next(row for row in field_locks.state(second, admin_user) if row["name"] == "title")
    assert lock["scope"] == "work" and lock["locks"][0]["edition_id"] == str(first.pk)
    save_workspace_edits(**command(first, admin_user, field="publication_year"))
    save_workspace_edits(**command(second, admin_user, action="unlock"))
    assert not FieldLock.objects.filter(field_name="title").exists()
    assert FieldLock.objects.filter(edition=first, field_name="publication_year").exists()
    assert not next(row for row in field_locks.state(second, admin_user) if row["name"] == "publication_year")["locks"]


def test_lock_request_cannot_mix_edits_or_run_after_stopped_receipt(admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="不得覆盖"))
    data = command(edition, admin_user)
    with pytest.raises(WorkflowEditError): save_workspace_edits(**{**data, "sections": {"work": {"title": "意外修改"}}})
    AuditEvent.objects.create(actor=admin_user, action="workspace.edits.saved", object_type="edition", object_id=str(edition.pk),
                              request_id=data["request_id"], after={"work_id":str(edition.work_id), "cancelled": True})
    with pytest.raises(WorkflowEditConflict): save_workspace_edits(**data)
    assert not FieldLock.objects.filter(edition=edition).exists()


def test_reader_cannot_change_protection_and_batch_is_atomic(admin_user, reader_user):
    edition = Edition.objects.create(work=Work.objects.create(title="保持原值"))
    with pytest.raises(PermissionDenied): save_workspace_edits(**command(edition, reader_user))
    data = command(edition, admin_user)
    data["field_locks"].append({"field":"unrecognized", "action":"lock", "reason":"不得保存"})
    with pytest.raises(WorkflowEditError): save_workspace_edits(**data)
    assert not FieldLock.objects.filter(edition=edition).exists()
    assert not AuditEvent.objects.filter(request_id=data["request_id"]).exists()


def test_lock_reads_saved_editorial_value_without_publishing(admin_user):
    from tests.test_publication_invariants_v305 import published_edition
    edition, public = published_edition("仍公开的旧题名")
    data = command(edition, admin_user)
    save_workspace_edits(**{**data, "field_locks": [], "sections": {"work": {"title": "已经保存但未发布的新题名"}}})
    edition.refresh_from_db(); edition.work.refresh_from_db()
    save_workspace_edits(**command(edition, admin_user))
    public.refresh_from_db(); edition.work.refresh_from_db()
    assert FieldLock.objects.get(edition=edition, field_name="title").locked_value == "已经保存但未发布的新题名"
    assert public.snapshot["work"]["title"] == "仍公开的旧题名" and edition.work.title == "仍公开的旧题名"


def test_edition_specific_draft_is_the_value_shown_and_locked(admin_user):
    from catalog.models import EditorialRevision
    edition = Edition.objects.create(work=Work.objects.create(title="版本年份"), publication_year=2001)
    EditorialRevision.objects.create(target_type="edition", target_id=edition.pk, revision=1,
                                     patch={"publication_year":2021}, idempotency_key=str(uuid4()))
    row = next(row for row in field_locks.state(edition, admin_user) if row["name"] == "publication_year")
    assert row["value"] == 2021
    save_workspace_edits(**command(edition, admin_user, field="publication_year"))
    edition.refresh_from_db()
    assert FieldLock.objects.get(edition=edition, field_name="publication_year").locked_value == 2021
    assert edition.publication_year == 2001
