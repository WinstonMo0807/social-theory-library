"""Catalog/PDF publication must not wait for optional semantic services.

Projection results are controlled here; the NAS service browser test separately
executes real Worker/Meilisearch delivery and records unavailable providers.
"""
from django.db.models import F
import pytest

from catalog.models import ProjectionState
from catalog.services.knowledge_publication import create_catalog_publication_event, process_knowledge_event
from catalog.services.publication_commands import catalog_publication_state
from ingestion.models import AuditEvent
from .test_metadata_publication_visibility_v305 import publication

pytestmark = pytest.mark.django_db


def projection_results(event, *, fulltext="current", public="current"):
    rows = ProjectionState.objects.filter(object_type=event.object_type, object_id=event.object_id)
    rows.update(status="current", projected_revision=F("source_revision"))
    rows.filter(projection_type="semantic").update(status="failed", projected_revision=0, last_error_code="INDEX_VERSION_REQUIRED")
    for name, state in (("fulltext", fulltext), ("public", public)):
        if state != "current":
            rows.filter(projection_type=name).update(status=state, projected_revision=0)


@pytest.mark.parametrize("fulltext", ["current", "failed", "waiting_for_capability"])
def test_A17_valid_pdf_is_public_independently_of_semantic_and_fulltext(settings, tmp_path, admin_user, api_client, fulltext):
    _, edition, _, reader, event = publication(settings, tmp_path, admin_user, text_ready=True)
    projection_results(event, fulltext=fulltext)
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    event.refresh_from_db()
    assert edition.active_catalog_revision_id == event.catalog_revision_id
    assert edition.active_catalog_revision.fulltext_ready is (fulltext == "current")
    assert catalog_publication_state(edition)["publicly_visible"] is True
    assert api_client.get(f"/api/catalog/works/{edition.public_slug}/").status_code == 200
    response = api_client.get(f"/api/distribution/assets/{reader.pk}/file/", HTTP_RANGE="bytes=0-4")
    assert response.status_code == 206
    assert b"".join(response.streaming_content) == b"%PDF-"
    response.close()
    assert event.status == "failed"
    assert event.deliveries.get(consumer="semantic").status == "failed"
    process_knowledge_event(event.pk)
    assert AuditEvent.objects.filter(action="catalog.metadata_activated", object_id=str(edition.pk)).count() == 1
    assert ProjectionState.objects.get(object_id=edition.pk, projection_type="semantic").last_error_code == "INDEX_VERSION_REQUIRED"


def test_A17_fulltext_can_become_ready_while_optional_failure_is_preserved(settings, tmp_path, admin_user):
    _, edition, _, _, event = publication(settings, tmp_path, admin_user, text_ready=True)
    projection_results(event, fulltext="waiting_for_capability")
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == event.catalog_revision_id
    assert not edition.active_catalog_revision.fulltext_ready
    ProjectionState.objects.filter(object_id=edition.pk, projection_type="fulltext").update(status="current", projected_revision=F("source_revision"))
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    event.refresh_from_db()
    assert edition.active_catalog_revision.fulltext_ready
    assert event.status == "failed"
    assert event.deliveries.get(consumer="semantic").status == "failed"
    process_knowledge_event(event.pk)
    assert AuditEvent.objects.filter(action="catalog.metadata_activated", object_id=str(edition.pk)).count() == 2
    receipt = AuditEvent.objects.filter(action="catalog.metadata_activated", object_id=str(edition.pk)).latest("created_at")
    assert receipt.before["active_catalog_revision_id"] == str(event.catalog_revision_id)
    assert receipt.before["fulltext_ready"] is False
    assert receipt.after["fulltext_ready"] is True


def test_A07_serving_snapshot_switches_only_after_its_own_public_delivery(settings, tmp_path, admin_user, api_client):
    _, edition, _, _, first = publication(settings, tmp_path, admin_user, text_ready=True)
    projection_results(first)
    process_knowledge_event(first.pk)
    edition.refresh_from_db()
    old = edition.active_catalog_revision_id
    assert old
    edition.work.title = "已明确发布的新题名"
    edition.work.save(update_fields=["title", "updated_at"])
    event = create_catalog_publication_event(edition, event_type="catalog_updated", changed_fields=["title", "catalog_publish"], idempotency_key="v306:independent-core-update", actor=admin_user)
    projection_results(event, public="failed")
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == old
    assert api_client.get(f"/api/catalog/works/{edition.public_slug}/").data["title"] != "已明确发布的新题名"
    projection_results(event, fulltext="failed")
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == event.catalog_revision_id
    assert not edition.active_catalog_revision.fulltext_ready
    assert api_client.get(f"/api/catalog/works/{edition.public_slug}/").data["title"] == "已明确发布的新题名"


@pytest.mark.parametrize("invalid", ["pending", "invalid", "missing_file", "newer_revision"])
def test_A02_partial_delivery_never_bypasses_reader_or_revision_checks(settings, tmp_path, admin_user, invalid):
    _, edition, _, reader, event = publication(settings, tmp_path, admin_user, text_ready=True)
    if invalid in {"pending", "invalid"}:
        reader.validation_status = invalid
        reader.save(update_fields=["validation_status"])
    elif invalid == "missing_file":
        reader.file = "public/does-not-exist-v306.pdf"
        reader.save(update_fields=["file"])
    else:
        create_catalog_publication_event(edition, event_type="catalog_updated", changed_fields=["cover"], idempotency_key="v306:newer-core-revision", actor=admin_user)
    projection_results(event)
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id is None


@pytest.mark.parametrize("consumer", ["public_cache", "bibliographic_search", "fulltext"])
@pytest.mark.parametrize("invalid", ["wrong_source", "missing_requirement"])
def test_A02_delivery_requires_matching_source_and_completion_evidence(settings, tmp_path, admin_user, consumer, invalid):
    _, edition, _, _, event = publication(settings, tmp_path, admin_user, text_ready=True)
    projection_results(event)
    delivery = event.deliveries.get(consumer=consumer)
    if invalid == "wrong_source":
        delivery.source_revision = 0
        delivery.save(update_fields=["source_revision"])
    else:
        delivery.result = {"required_projections": []}
        delivery.save(update_fields=["result"])
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    if consumer == "fulltext":
        assert edition.active_catalog_revision_id == event.catalog_revision_id
        assert not edition.active_catalog_revision.fulltext_ready
    else:
        assert edition.active_catalog_revision_id is None
