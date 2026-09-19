from copy import deepcopy
from datetime import timedelta
from io import StringIO
import json
import uuid
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import F
from django.utils import timezone

from catalog.models import (
    Asset, CatalogPublicationRevision, DocumentQualityAssessment, DocumentRevision,
    KnowledgePublicationEvent, ProjectionState,
)
from catalog.services.admin_workspace import build_admin_workspace
from catalog.services.knowledge_publication import (
    create_catalog_publication_event, metadata_activation_preflight,
    process_knowledge_event, recover_catalog_metadata,
)
from catalog.services.publication_commands import catalog_health, catalog_publication_state
from catalog.services.publication_eligibility import active_asset_q, active_document_q
from catalog.services.scoped_search import public_work_queryset
from ingestion.models import AuditEvent
from ingestion.services.publication import PublicationBlocked, publish_edition
from .publication_fixtures import confirm_book_identity
from .test_resilient_publication_v260 import create_item_with_files


pytestmark = pytest.mark.django_db


def publication(settings, tmp_path, actor, *, text_ready=False):
    work, edition, original, reader = create_item_with_files(settings, tmp_path, title="首次书目先公开")
    confirm_book_identity(edition, actor)
    if text_ready:
        document = DocumentRevision.objects.create(
            asset=reader, revision=1, source_checksum=reader.sha256,
            text_checksum="a" * 64, is_active=True,
        )
        DocumentQualityAssessment.objects.create(
            document_revision=document, assessor_version="visibility-test",
            reader_quality=0.9, fulltext_quality=0.8, semantic_quality=0.7,
            claim_quality=0.7, structure_quality=0.7, ocr_quality=0.8,
        )
    publish_edition(edition, actor=actor, confirm_warnings=True)
    edition.refresh_from_db()
    event = KnowledgePublicationEvent.objects.get(catalog_revision__edition=edition)
    return work, edition, original, reader, event


def finish_except_graph(event, *, graph_state="waiting_for_capability"):
    states = ProjectionState.objects.filter(object_type=event.object_type, object_id=event.object_id)
    states.exclude(projection_type="knowledge_graph").update(projected_revision=F("source_revision"), status="current")
    states.filter(projection_type="knowledge_graph").update(
        projected_revision=0, status=graph_state,
        last_error_code="executor_missing" if graph_state == "failed" else "",
    )


def legacy_pending_event(event):
    """The real pre-fix state: public processing complete, graph still pending."""
    finish_except_graph(event)
    event.deliveries.exclude(consumer__in=["knowledge_graph", "person_search", "fulltext", "semantic", "viewpoint"]).update(
        status="completed", completed_at=timezone.now(),
    )
    event.status = "processing"
    event.attempts = 1553
    event.lease_expires_at = timezone.now() - timedelta(minutes=1)
    event.lease_token = uuid.uuid4()
    event.save(update_fields=["status", "attempts", "lease_expires_at", "lease_token", "updated_at"])
    event.refresh_from_db()


def test_approved_first_book_is_visible_while_graph_stays_pending(settings, tmp_path, admin_user, api_client):
    work, edition, original, reader, event = publication(settings, tmp_path, admin_user)
    frozen = deepcopy(event.catalog_revision.snapshot)
    original_bytes = original.file.read()
    original.file.close()
    assert not public_work_queryset().filter(pk=work.pk).exists()
    assert catalog_publication_state(edition)["publicly_visible"] is False

    finish_except_graph(event)
    process_knowledge_event(event.pk)

    edition.refresh_from_db()
    event.refresh_from_db()
    assert edition.active_catalog_revision_id == event.catalog_revision_id
    assert event.status == "pending"
    assert edition.intelligence_status == "processing"
    assert event.deliveries.get(consumer="knowledge_graph").status == "pending"
    assert event.deliveries.get(consumer="person_search").status == "pending"
    assert event.deliveries.get(consumer="semantic").status == "skipped"
    assert event.catalog_revision.snapshot == frozen
    assert event.catalog_revision.fulltext_ready is False
    assert public_work_queryset().filter(pk=work.pk).exists()
    assert Asset.objects.filter(pk=reader.pk).filter(active_asset_q(asset_prefix="")).exists()
    assert not Asset.objects.filter(pk=reader.pk).filter(active_document_q(asset_prefix="")).exists()
    assert api_client.get(f"/api/catalog/works/{edition.public_slug}/").status_code == 200
    original.file.open("rb")
    assert original.file.read() == original_bytes
    original.file.close()
    assert catalog_health(edition)["publication"] == "published"
    assert catalog_health(edition)["processing"] == "processing"

    process_knowledge_event(event.pk)
    assert AuditEvent.objects.filter(action="catalog.metadata_activated", object_id=str(edition.pk)).count() == 1
    assert edition.catalog_revisions.count() == 1


def test_graph_failure_remains_failed_without_hiding_approved_book(settings, tmp_path, admin_user):
    settings.KNOWLEDGE_EVENT_MAX_ATTEMPTS = 1
    work, edition, _original, _reader, event = publication(settings, tmp_path, admin_user)
    finish_except_graph(event, graph_state="failed")
    process_knowledge_event(event.pk)
    event.refresh_from_db()
    edition.refresh_from_db()
    assert event.status == "dead_letter"
    assert event.deliveries.get(consumer="knowledge_graph").status == "failed"
    assert edition.intelligence_status == "failed"
    assert edition.active_catalog_revision.status == "active"
    assert edition.active_catalog_revision.failure_code == "projection_delivery_failed"
    assert public_work_queryset().filter(pk=work.pk).exists()


def test_fulltext_and_updates_use_their_own_delivery_gate_not_optional_graph(settings, tmp_path, admin_user):
    _work, edition, _original, _reader, event = publication(settings, tmp_path, admin_user, text_ready=True)
    assert event.payload["requested_fulltext_ready"] is True
    finish_except_graph(event)
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == event.catalog_revision_id
    assert edition.active_catalog_revision.fulltext_ready
    ProjectionState.objects.filter(object_type=event.object_type, object_id=event.object_id).update(
        projected_revision=F("source_revision"), status="current",
    )
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    previous = edition.active_catalog_revision_id
    assert edition.active_catalog_revision.fulltext_ready
    update = create_catalog_publication_event(
        edition, event_type="catalog_updated", changed_fields=["title", "catalog_publish"],
        idempotency_key="visibility:keep-previous", actor=admin_user,
    )
    finish_except_graph(update)
    process_knowledge_event(update.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == update.catalog_revision_id
    assert edition.active_catalog_revision_id != previous
    assert edition.active_catalog_revision.fulltext_ready
    assert update.deliveries.get(consumer="knowledge_graph").status == "pending"


def test_recovery_dry_run_and_apply_preserve_event_tasks_snapshot_and_files(settings, tmp_path, admin_user, api_client):
    _work, edition, original, reader, event = publication(settings, tmp_path, admin_user)
    legacy_pending_event(event)
    delivery_before = list(event.deliveries.order_by("consumer").values())
    event_before = KnowledgePublicationEvent.objects.filter(pk=event.pk).values().get()
    snapshot = deepcopy(event.catalog_revision.snapshot)
    output = StringIO()
    call_command("reconcile_catalog_metadata", event_id=event.pk, edition_id=edition.pk, stdout=output)
    assert json.loads(output.getvalue())["eligible"] is True
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id is None
    assert not AuditEvent.objects.filter(action="catalog.metadata_activated").exists()

    api_client.force_authenticate(admin_user)
    before = api_client.get(f"/api/catalog/admin/editions/{edition.pk}/knowledge-status/")
    assert before.status_code == 200
    assert before.json()["publicly_visible"] is False
    assert before.json()["public_state"] == "publishing"
    assert "正在准备" in before.json()["detail"]

    output = StringIO()
    call_command("reconcile_catalog_metadata", event_id=event.pk, edition_id=edition.pk, apply=True, stdout=output)
    assert json.loads(output.getvalue())["changed"] is True
    assert list(event.deliveries.order_by("consumer").values()) == delivery_before
    assert KnowledgePublicationEvent.objects.filter(pk=event.pk).values().get() == event_before
    event.catalog_revision.refresh_from_db()
    assert event.catalog_revision.snapshot == snapshot
    assert Asset.objects.filter(pk__in=[original.pk, reader.pk]).count() == 2
    assert recover_catalog_metadata(event.pk, expected_edition_id=edition.pk)["changed"] is False
    assert AuditEvent.objects.filter(action="catalog.metadata_activated").count() == 1
    after = api_client.get(f"/api/catalog/admin/editions/{edition.pk}/knowledge-status/")
    assert after.json()["publicly_visible"] is True
    assert after.json()["state"] == "processing"
    assert after.json()["fulltext_ready"] is False
    assert after.headers["Cache-Control"] == "private, no-store"
    workspace = build_admin_workspace(edition, user=admin_user, mode="maintenance")
    assert workspace["data"]["publication"]["public_state"] == "published"
    assert workspace["context"]["public_url"] == f"/works/{edition.public_slug}"


@pytest.mark.parametrize("blocker", ["public_pending", "live_lease", "newer_revision", "missing_file"])
def test_recovery_refuses_unready_or_changed_context(settings, tmp_path, admin_user, blocker):
    _work, edition, _original, reader, event = publication(settings, tmp_path, admin_user)
    legacy_pending_event(event)
    if blocker == "public_pending":
        event.deliveries.filter(consumer="public_cache").update(status="pending")
    elif blocker == "live_lease":
        event.lease_expires_at = timezone.now() + timedelta(minutes=1)
        event.save(update_fields=["lease_expires_at"])
    elif blocker == "newer_revision":
        create_catalog_publication_event(
            edition, event_type="catalog_updated", changed_fields=["cover"],
            idempotency_key="visibility:newer", actor=admin_user,
        )
    else:
        reader.file = "public/missing-visibility.pdf"
        reader.save(update_fields=["file"])
    with pytest.raises((CommandError, ValueError)):
        recover_catalog_metadata(event.pk, expected_edition_id=edition.pk, actor=admin_user)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id is None
    assert not AuditEvent.objects.filter(action="catalog.metadata_activated").exists()


def test_published_flag_without_a_formal_event_is_not_a_successful_republish(settings, tmp_path, admin_user):
    _work, edition, _original, _reader = create_item_with_files(settings, tmp_path)
    edition.state = "published"
    edition.save(update_fields=["state"])
    with pytest.raises(PublicationBlocked, match="缺少正式发布记录"):
        publish_edition(edition, actor=admin_user, confirm_warnings=True)
    assert not KnowledgePublicationEvent.objects.exists()


def test_republish_wakes_the_existing_approved_event_without_new_revision(settings, tmp_path, admin_user, django_capture_on_commit_callbacks):
    _work, edition, _original, _reader, event = publication(settings, tmp_path, admin_user)
    legacy_pending_event(event)
    with patch("catalog.services.knowledge_publication.dispatch_knowledge_event") as wake:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            result = publish_edition(edition, actor=admin_user, confirm_warnings=True)
        assert len(callbacks) == 1
        callbacks[0]()
    assert result.active_catalog_revision_id is None
    assert catalog_publication_state(result)["public_state"] == "publishing"
    wake.assert_called_once_with(event.pk)
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == event.catalog_revision_id
    assert edition.catalog_revisions.count() == 1
    assert KnowledgePublicationEvent.objects.filter(catalog_revision__edition=edition).count() == 1
