"""Publication completion follows the selected index, not a retired model job."""
from datetime import timedelta
from uuid import uuid4
import pytest
from django.utils import timezone
from catalog.discovery_index_models import DiscoverySourceState
from catalog.models import ProjectionState, SemanticIndexJob
from catalog.services import projection_refresh as service
from ingestion.models import ProcessingJob
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def sample():
    edition, asset, _, docs = fixture_source(1)
    source = {"edition_id": str(edition.pk), "asset_id": str(asset.pk),
              "catalog_revision_id": str(edition.active_catalog_revision_id)}
    state = DiscoverySourceState.objects.create(generation=docs[0].generation,
        source_type="edition", source_id=edition.pk, source_revision=docs[0].source_revision,
        indexed_at=timezone.now(), expected_count=1, completed_count=1)
    return edition, asset, source, state


def test_exact_discovery_revision_completes_without_legacy_index(settings):
    settings.DISCOVERY_ENABLED = True
    edition, asset, _, _ = sample()
    job = ProcessingJob.objects.create(job_type="projection_refresh", stats={})
    result = service._semantic_projection(job, [asset], {}, catalog_revision=edition.active_catalog_revision)
    assert result["status"] == "current" and result["backend"] == "discovery"
    assert not SemanticIndexJob.objects.exists()
    job.refresh_from_db()
    assert job.stats["projection_plan"]["discovery_sources"][0]["asset_id"] == str(asset.pk)


@pytest.mark.parametrize("change", ["old_source", "incomplete", "wrong_asset", "wrong_catalog"])
def test_previous_or_incomplete_index_never_confirms_publication(change):
    _, _, source, state = sample()
    if change == "old_source":
        state.source_revision = "old"
    elif change == "incomplete":
        state.completed_count = 0
    elif change == "wrong_asset":
        source["asset_id"] = str(uuid4())
    else:
        source["catalog_revision_id"] = str(uuid4())
    state.save()
    assert service._discovery_publication_result([source])["status"] == "delegated"


def test_current_discovery_failure_remains_visible():
    _, _, source, state = sample()
    job = ProcessingJob.objects.create(job_type="discovery_index", status="failed",
        stats={"source_revision": state.source_revision})
    state.job = job
    state.completed_count = 0
    state.save()
    assert service._discovery_publication_result([source])["status"] == "failed"


def test_delegated_completion_reuses_revision_guard_and_lease():
    edition, _, source, state = sample()
    parent = ProcessingJob.objects.create(job_type="projection_refresh", status="running")
    tracked = ProjectionState.objects.create(object_type="edition", object_id=edition.pk,
        projection_type="semantic", source_revision=1, projected_revision=0, status="projecting",
        task_owner_type="ProcessingJob", task_owner_key=str(parent.pk), lease_token=uuid4(),
        lease_expires_at=timezone.now()+timedelta(hours=1))
    parent.stats = {"projection_plan": {"discovery_sources": [source],
        "semantic_state_id": str(tracked.pk), "semantic_source_revision": 1},
        "projection_results": {"semantic": {"status": "delegated"}}}
    parent.save()
    state.completed_count = 0
    state.save()
    assert service.reconcile_delegated_projection_job(parent.pk).status == "running"
    state.completed_count = 1
    state.save()
    assert service.reconcile_delegated_projection_job(parent.pk).status == "succeeded"
    tracked.refresh_from_db()
    assert tracked.projected_revision == 1 and tracked.status == "current"
