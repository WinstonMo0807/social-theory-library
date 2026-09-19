from copy import deepcopy

import pytest

from catalog.models import CatalogPublicationRevision, Edition, KnowledgePublicationEvent, ProjectionState
from catalog.services.publication_commands import (
    PublicationCommandError, activate_revision, prepare_revision, rollback_revision, validate_revision,
    catalog_health,
)
from catalog.services.knowledge_publication import process_knowledge_event
from catalog.services.publication_eligibility import active_catalog_snapshot
from ingestion.services.publication import PublicationBlocked
from .test_catalog_contracts_v305 import _manual_ready
from .test_publication_invariants_v305 import published_edition


pytestmark = pytest.mark.django_db


def finish(event):
    ProjectionState.objects.filter(object_type="edition", object_id=event.object_id).update(
        status="current", projected_revision=event.domain_event.canonical_revision,
    )
    return process_knowledge_event(event.pk)


def test_preparation_is_read_only_and_detects_title_diff(admin_user):
    edition, public = published_edition("旧公开题名")
    edition.work.title = "新草稿题名"
    edition.work.save()
    prepared = prepare_revision(edition)
    title = next(row for row in prepared["changes"] if row["field"] == "title")
    assert title["change"] == "changed"
    assert title["before_display"] == "旧公开题名"
    assert title["after_display"] == "新草稿题名"
    assert not KnowledgePublicationEvent.objects.exists()
    assert CatalogPublicationRevision.objects.count() == 1
    assert Edition.objects.get(pk=edition.pk).active_catalog_revision_id == public.pk


def test_preparation_displays_business_labels_without_changing_raw_values(admin_user):
    edition = _manual_ready(admin_user)
    edition.work.document_type = "report"
    edition.work.language = "zh-CN"
    edition.work.save()
    rows = {row["field"]: row for row in prepare_revision(edition)["changes"]}
    assert rows["document_type"]["after"] == "report"
    assert rows["document_type"]["after_display"] == "研究报告"
    assert rows["publication_mode"]["after"] == "bibliographic"
    assert rows["publication_mode"]["after_display"] == "纯书目"
    assert rows["language"]["after_display"] == "简体中文"


def test_stale_preparation_cannot_publish(admin_user):
    edition = _manual_ready(admin_user)
    prepared = prepare_revision(edition)
    edition.work.subtitle = "检查后被更改"
    edition.work.save()
    with pytest.raises(PublicationBlocked, match="内容已"):
        activate_revision(edition, actor=admin_user, prepared_fingerprint=prepared["fingerprint"], confirm_warnings=True)
    assert not KnowledgePublicationEvent.objects.exists()


def test_rollback_only_accepts_legally_activated_own_revision(admin_user):
    edition, _public = published_edition("当前题名")
    _other, unrelated = published_edition("其他题名")
    with pytest.raises(PublicationCommandError, match="不属于"):
        rollback_revision(edition, unrelated.pk, actor=admin_user, idempotency_key="rollback:other")
    failed = CatalogPublicationRevision.objects.create(edition=edition, revision=2, status="failed", metadata_ready=True, content_fingerprint="a" * 64)
    with pytest.raises(PublicationCommandError, match="合法公开"):
        rollback_revision(edition, failed.pk, actor=admin_user, idempotency_key="rollback:failed")
    assert not KnowledgePublicationEvent.objects.exists()


def test_rollback_republishes_immutable_old_content_and_is_idempotent(admin_user):
    edition, original = published_edition("恢复后的旧题名")
    original_snapshot = deepcopy(original.snapshot)
    original.status = "superseded"
    original.save()
    newer = CatalogPublicationRevision.objects.create(
        edition=edition, revision=2, status="active", activated_at=original.activated_at,
        metadata_ready=True, snapshot={"work": {"title": "当前错误题名"}}, content_fingerprint="b" * 64,
    )
    edition.active_catalog_revision = newer
    edition.save()
    event = rollback_revision(edition, original.pk, actor=admin_user, idempotency_key="rollback:legal")
    repeated = rollback_revision(edition, original.pk, actor=admin_user, idempotency_key="rollback:legal")
    assert repeated.pk == event.pk
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == newer.pk
    assert event.catalog_revision.snapshot == original_snapshot
    assert event.catalog_revision.revision == 3
    finish(event)
    edition.refresh_from_db()
    original.refresh_from_db()
    assert active_catalog_snapshot(edition)["work"]["title"] == "恢复后的旧题名"
    assert original.snapshot == original_snapshot
    assert original.status == "superseded"
    assert edition.active_catalog_revision.provenance["rollback_source_revision_id"] == str(original.pk)


def test_revision_validator_rejects_fulltext_without_document():
    edition, revision = published_edition("非法全文资格")
    revision.fulltext_ready = True
    assert validate_revision(revision, edition=edition)


def test_snapshot_is_immutable_in_model_and_queryset_writes():
    from django.core.exceptions import ValidationError

    _edition, revision = published_edition("不可改写快照")
    revision.snapshot = {"work": {"title": "意外覆盖"}}
    with pytest.raises(ValidationError, match="不可改写"):
        revision.save(update_fields=["snapshot"])
    with pytest.raises(ValidationError, match="不可改写"):
        CatalogPublicationRevision.objects.filter(pk=revision.pk).update(snapshot={})
    revision.refresh_from_db()
    assert revision.snapshot["work"]["title"] == "不可改写快照"
    revision.failure_code = "observable_processing_error"
    revision.save(update_fields=["failure_code", "updated_at"])


def test_preparation_endpoint_is_private_and_uses_live_draft(api_client, admin_user):
    edition = _manual_ready(admin_user)
    url = f"/api/catalog/admin/editions/{edition.pk}/publication/prepare/"
    assert api_client.get(url).status_code in {401, 403}
    api_client.force_authenticate(admin_user)
    result = api_client.get(url)
    assert result.status_code == 200
    assert result["Cache-Control"] == "private, no-store"
    assert result.data["can_publish"] is True
    assert not KnowledgePublicationEvent.objects.exists()


def test_rollback_does_not_reopen_withdrawn_work(admin_user):
    edition, old = published_edition("已撤回的作品")
    edition.state = "withdrawn"
    edition.save()
    with pytest.raises(PublicationCommandError, match="重新发布"):
        rollback_revision(edition, old.pk, actor=admin_user, idempotency_key="rollback:withdrawn")


def test_stale_revision_delivery_cannot_displace_newer_recovery(admin_user):
    from catalog.services.knowledge_publication import create_catalog_publication_event

    edition, old = published_edition("恢复保留原值")
    pending = create_catalog_publication_event(edition, event_type="catalog_updated", changed_fields=["cover"], idempotency_key="pending:earlier")
    recovery = rollback_revision(edition, old.pk, actor=admin_user, idempotency_key="rollback:newer")
    finish(recovery)
    finish(pending)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == recovery.catalog_revision_id
    assert active_catalog_snapshot(edition)["work"]["title"] == "恢复保留原值"


def test_editorial_and_publication_state_do_not_collapse_on_processing_failure(admin_user):
    edition = _manual_ready(admin_user)
    first = catalog_health(edition)
    assert first["publication"] == "unpublished"
    assert first["processing"] == "idle"
    edition.intelligence_status = "failed"
    next_health = catalog_health(edition)
    assert next_health["editorial"] == first["editorial"]
    assert next_health["processing"] == "failed"
    assert next_health["publication"] == "unpublished"
