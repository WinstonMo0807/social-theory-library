"""Exhausted projection retries must stay bounded across automatic recovery."""
from unittest.mock import patch

import pytest

from catalog.models import Work
from catalog.services.projection_refresh import _claim, queue_projection_refresh
from ingestion.models import ProcessingJob


@pytest.mark.django_db
def test_automatic_recovery_keeps_budget_and_manual_retry_is_explicit():
    work = Work.objects.create(title="Projection recovery check")
    with patch("catalog.services.projection_refresh._schedule_job_capability"):
        job = queue_projection_refresh(target_type="work", target_id=str(work.pk))
        job.status = ProcessingJob.Status.FAILED
        job.attempt = job.max_attempts
        job.error_code = "projection_partial_failure"
        job.save()
        for force, preserve in [(False, False), (True, True)]:
            recovered = queue_projection_refresh(target_type="work", target_id=str(work.pk),
                                                 force=force, preserve_attempts=preserve)
            assert recovered.status == "failed" and recovered.attempt == job.max_attempts
            assert recovered.error_code == "projection_partial_failure"
        # Old deployments can leave an already-exhausted pending wakeup.
        job.status = "pending"
        job.save(update_fields=["status"])
        blocked, claimed = _claim(str(job.pk), "")
        assert not claimed and blocked.status == "failed"
        assert blocked.attempt == job.max_attempts
        assert blocked.error_code == "max_attempts_exhausted"
        retried = queue_projection_refresh(target_type="work", target_id=str(work.pk), force=True)
        assert retried.status == "pending" and retried.attempt == 0


@pytest.mark.django_db
def test_publication_stops_waiting_for_its_exhausted_projection_owner():
    from catalog.models import KnowledgePublicationEvent, KnowledgeProjectionDelivery, ProjectionState
    from catalog.services.knowledge_publication import process_knowledge_event
    work = Work.objects.create(title="Exhausted publication check")
    job = ProcessingJob.objects.create(job_type="projection_refresh", status="failed", attempt=3,
        max_attempts=3, stats={"target_type": "work", "target_id": str(work.pk)})
    state = ProjectionState.objects.create(object_type="work", object_id=work.pk,
        projection_type="semantic", source_revision=1, projected_revision=0,
        status="waiting_for_capability", task_owner_type="ProcessingJob", task_owner_key=str(job.pk))
    event = KnowledgePublicationEvent.objects.create(event_type="catalog_updated", object_type="work",
        object_id=work.pk, attempts=100, idempotency_key="exhausted-publication-check")
    delivery = KnowledgeProjectionDelivery.objects.create(event=event, consumer="semantic", source_revision=1,
        idempotency_key="exhausted-delivery-check", result={"required_projections": ["semantic"]})
    result = process_knowledge_event(event.pk)
    delivery.refresh_from_db()
    assert result.status == "dead_letter" and result.next_attempt_at is None
    assert delivery.status == "failed" and delivery.last_error_code == "projection_failed"
    assert process_knowledge_event(event.pk).attempts == 101
    # An actually completed projection must still win over its owner's old failure.
    state.projected_revision = 1; state.save(update_fields=["projected_revision"])
    event.status = "pending"; event.save(update_fields=["status"])
    assert process_knowledge_event(event.pk).status == "completed"


@pytest.mark.django_db
def test_authorized_publication_retry_restarts_exhausted_same_projection(admin_user):
    from django.utils import timezone
    from catalog.models import DomainChangeEvent, KnowledgePublicationEvent
    from catalog.services.knowledge_publication import retry_knowledge_publication
    work = Work.objects.create(title="Manual publication recovery")
    source = DomainChangeEvent.objects.create(object_type="work", object_id=work.pk,
        canonical_revision=1, change_kind="publish", processed_at=timezone.now(),
        idempotency_key="manual-publication-recovery-source")
    event = KnowledgePublicationEvent.objects.create(event_type="entity_published",
        object_type="work", object_id=work.pk, domain_event=source,
        status="failed", attempts=3, idempotency_key="manual-publication-recovery-event")
    with patch("catalog.services.projection_refresh._schedule_job_capability"), patch(
        "catalog.services.knowledge_publication.dispatch_knowledge_event"
    ):
        job = queue_projection_refresh(target_type="work", target_id=str(work.pk), source_event=source)
        job.status = "failed"
        job.attempt = job.max_attempts
        job.error_code = "TimeoutError"
        job.save()
        retried = retry_knowledge_publication(event.pk, actor=admin_user)
        job.refresh_from_db()
        assert retried.pk == event.pk and retried.status == "pending"
        assert job.status == "pending" and job.attempt == 0 and not job.error_code
        assert job.stats["manual_retry"]["previous_status"] == "failed"
        assert ProcessingJob.objects.filter(idempotency_key=job.idempotency_key).count() == 1
        # A repeat click while pending must not replace or reset the active job.
        job.attempt = 1
        job.save(update_fields=["attempt"])
        retry_knowledge_publication(event.pk, actor=admin_user)
        job.refresh_from_db()
        assert job.attempt == 1
