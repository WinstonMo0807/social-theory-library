"""Publication and external-write risks; these do not certify model relevance."""
from uuid import uuid4
from datetime import timedelta

import pytest
from django.utils import timezone

from catalog.discovery_index_models import DiscoveryDocument, DiscoverySourceState
from catalog.models import ReadingPath, ReadingPathItem, SemanticIndexVersion, Topic
from catalog.services import discovery_indexing as indexing
from catalog.services import discovery_projection as projection
from catalog.services import discovery_sources as sources
from catalog.services import editorial_issues
from ingestion.models import ProcessingJob
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def test_reading_path_scope_changes_only_with_public_copy():
    path = ReadingPath.objects.create(title="共同体阅读", slug="community-reading", status="published")
    item = ReadingPathItem.objects.create(reading_path=path, stage_name="起点",
        recommendation_reason="比较互助形式", editorial_note="私人工作说明不可公开")
    first = sources.get_source("reading_path", path.pk)[1]
    assert "比较互助形式" in first["text"]
    assert "私人工作说明" not in first["text"]
    item.editorial_note = "修改后的私人说明"
    item.save(update_fields=["editorial_note"])
    assert sources.get_source("reading_path", path.pk)[1]["scope_token"] == first["scope_token"]
    item.recommendation_reason = "新的已发布推荐理由"
    item.save(update_fields=["recommendation_reason"])
    changed = sources.get_source("reading_path", path.pk)[1]
    assert changed["scope_token"] != first["scope_token"]
    assert first["scope_token"] not in projection.current_scopes("curation", ["public"])


def test_recommendation_issue_indexes_published_item_note_not_draft(admin_user):
    issue = editorial_issues.create_issue({"title": "公开一期", "items": [
        {"kind": "planned", "title": "已确认计划", "note": "公开的互助推荐理由"}]}, admin_user)
    editorial_issues.publish_issue(issue.pk, editorial_issues.issue_payload(issue)["edit_version"], admin_user)
    first = sources.get_source("recommendation_issue", issue.pk)[1]
    assert "公开的互助推荐理由" in first["text"]
    draft = editorial_issues.issue_payload(issue)
    draft["items"][0]["note"] = "尚未发布的编辑文字"
    editorial_issues.save_issue(issue.pk, draft, admin_user)
    current = sources.get_source("recommendation_issue", issue.pk)[1]
    assert current["scope_token"] == first["scope_token"]
    assert "尚未发布" not in current["text"]


def test_span_local_offsets_become_page_offsets_without_rewriting_quote():
    _, _, spans, docs = fixture_source(1)
    span, doc = spans[0], docs[0]
    doc.payload = {**doc.payload, "source_start_offset": 125, "source_kind": "ocr", "language": "en"}
    doc.save(update_fields=["payload"])
    result = projection.validate_discovery_results("passages", [{"id": str(doc.pk)}], ["public"])[0]
    assert result["start_offset"] == 125
    assert result["end_offset"] == 125 + len(span.original_text)
    assert result["excerpt"] == span.original_text
    assert result["source_kind"] == "ocr"
    assert result["language"] == "en"


def test_successful_external_task_required_before_ready(monkeypatch):
    edition, _, _, docs = fixture_source(1)
    generation = docs[0].generation
    header = sources.get_source("edition", edition.pk)[1]
    unit = next(sources.source_units("edition", edition, header))
    child = {"start": 1, "end": 5, "text": unit["text"][1:5], "normalized_text": unit["text"][1:5],
             "embedding_text": unit["text"][1:5], "token_count": 10, "quality_flags": []}
    job = ProcessingJob.objects.create(job_type="discovery_index", task_id=str(uuid4()), status="running",
        stats={"source_type": "edition", "source_id": str(edition.pk), "source_revision": header["source_revision"]})
    monkeypatch.setattr(indexing, "embed_texts", lambda *a, **kw: {"vectors": [[1.0] + [0.0] * 383]})
    monkeypatch.setattr(indexing, "meili", lambda *a, **kw: {"taskUid": 7})
    def fail_task(*args, **kwargs):
        raise projection.DiscoveryIndexError("write_failed")
    monkeypatch.setattr(indexing, "wait_index_task", fail_task)
    with pytest.raises(projection.DiscoveryIndexError):
        indexing._write_chunk(job, generation, header, unit, child)
    projected = DiscoveryDocument.objects.exclude(pk__in=[doc.pk for doc in docs]).get()
    assert not projected.keyword_ready and not projected.vector_ready
    assert projected.indexed_at is None


def test_old_claim_cannot_checkpoint_after_requeue():
    task_id = str(uuid4())
    job = ProcessingJob.objects.create(job_type="discovery_index", task_id=task_id, status="running")
    ProcessingJob.objects.filter(pk=job.pk).update(task_id=str(uuid4()), status="pending", stats={"completed_units": 20})
    with pytest.raises(projection.DiscoveryIndexError, match="旧任务"):
        indexing._guard_job(job, stats={"completed_units": 1})
    job.refresh_from_db()
    assert job.status == "pending" and job.stats["completed_units"] == 20


def test_coverage_excludes_newly_private_source():
    edition, asset, _, docs = fixture_source(1)
    DiscoverySourceState.objects.create(generation=docs[0].generation, source_type="edition", source_id=edition.pk,
        source_revision=docs[0].source_revision, expected_count=1, completed_count=1, indexed_at=timezone.now())
    before = projection.discovery_coverage(["public"])
    assert before["eligible_editions"] == before["indexed_editions"] == before["vector_editions"] == 1
    asset.access_status = "private"
    asset.save(update_fields=["access_status"])
    after = projection.discovery_coverage(["public"])
    assert after["eligible_editions"] == after["indexed_editions"] == after["passage_count"] == 0


def test_discovery_generation_never_becomes_legacy_semantic_active():
    old = SemanticIndexVersion.objects.create(uid=f"legacy-{uuid4().hex}", provider="legacy", status="active")
    new = SemanticIndexVersion.discovery_objects.create(index_family="discovery", uid=f"discovery-{uuid4().hex}",
        provider="userProvided", status="active")
    assert list(SemanticIndexVersion.objects.filter(status="active").values_list("pk", flat=True)) == [old.pk]
    assert projection.active_generation().pk == new.pk


def test_reader_model_admission_wait_does_not_exhaust_index_retries(monkeypatch):
    edition, _, _, docs = fixture_source(1)
    job = ProcessingJob.objects.create(job_type="discovery_index", task_id=str(uuid4()), status="pending",
        stats={"action": "source", "generation_id": str(docs[0].generation_id)})
    old_task = job.task_id
    def occupied(*args):
        from catalog.services.discovery_inference import DiscoveryInferenceError
        raise DiscoveryInferenceError("inference_busy", "模型忙碌")
    monkeypatch.setattr(indexing, "process_source", occupied)
    indexing.run_job(job.pk, old_task)
    job.refresh_from_db()
    assert job.status == "pending"
    assert job.task_id != old_task
    assert job.attempt == 0
    assert job.error_code == "waiting_model"
    assert "自动继续" in job.error_message


def test_serialized_cpu_queue_wait_is_not_a_lost_running_lease(monkeypatch):
    rows = []
    for status, age in (("pending", 35), ("running", 20), ("pending", 70)):
        job = ProcessingJob.objects.create(job_type="discovery_index", task_id=str(uuid4()), status=status,
            stats={"action": "source"})
        ProcessingJob.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(minutes=age))
        rows.append(job)
    monkeypatch.setattr(indexing, "active_generation", lambda: None)
    monkeypatch.setattr(indexing, "finish_builds", lambda: None)
    indexing._reconcile()
    for job in rows:
        job.refresh_from_db()
    assert rows[0].status == "pending" and rows[0].attempt == 0
    assert all(job.status == "failed" and job.error_code == "worker_interrupted" and job.attempt == 1 for job in rows[1:])


@pytest.mark.parametrize("status", ["active", "building", "ready"])
def test_application_rollback_retires_discovery_without_losing_data_or_legacy_index(status):
    _, _, _, docs = fixture_source(1)
    generation = docs[0].generation
    generation.status = status
    generation.save(update_fields=["status"])
    queued = ProcessingJob.objects.create(job_type="discovery_index", task_id=str(uuid4()), status="pending",
        stats={"action": "source", "generation_id": str(generation.pk)})
    legacy = SemanticIndexVersion.objects.create(uid=f"rollback-legacy-{uuid4().hex}", provider="legacy", status="active")
    indexing.deactivate_generation(generation)
    generation.refresh_from_db()
    assert generation.status == "retired"
    assert DiscoveryDocument.objects.filter(generation=generation).count() == 1
    assert list(SemanticIndexVersion.all_objects.filter(status="active").values_list("pk", flat=True)) == [legacy.pk]
    queued.refresh_from_db()
    assert queued.status == "canceled" and queued.error_code == "application_rollback"
    indexing.run_job(queued.pk, queued.task_id)
    queued.refresh_from_db()
    assert queued.status == "canceled"


def test_activation_rechecks_source_revision_even_when_document_count_is_unchanged(monkeypatch):
    edition, asset, _, docs = fixture_source(1)
    generation = docs[0].generation
    generation.status = "ready"
    generation.save(update_fields=["status"])
    DiscoverySourceState.objects.create(generation=generation, source_type="edition", source_id=edition.pk,
        source_revision=docs[0].source_revision, expected_count=1, completed_count=1, indexed_at=timezone.now())
    asset.access_status = "private"
    asset.save(update_fields=["access_status"])
    def should_not_read_index(*args, **kwargs):
        raise AssertionError("Changed source must reject activation before any external index request")
    monkeypatch.setattr(indexing, "meili", should_not_read_index)
    with pytest.raises(projection.DiscoveryIndexError) as raised:
        indexing.activate_generation(generation)
    assert raised.value.code == "source_changed"
    generation.refresh_from_db()
    assert generation.status == "ready"


def test_ready_revision_refresh_keeps_single_visible_build_coordinator(monkeypatch, settings):
    settings.DISCOVERY_ENABLED = True
    generation = SemanticIndexVersion.discovery_objects.create(index_family="discovery",
        uid=f"refresh-{uuid4().hex}", provider="local", status="ready", config_snapshot={"index_configured": True})
    coordinator = ProcessingJob.objects.create(job_type="discovery_index", status="succeeded", progress=100,
        finished_at=timezone.now(), stats={"action": "build", "generation_id": str(generation.pk)})
    monkeypatch.setattr(indexing, "schedule_sources", lambda generation: 1)
    indexing.finish_builds()
    generation.refresh_from_db()
    coordinator.refresh_from_db()
    assert generation.status == "building"
    assert coordinator.status == "running" and coordinator.finished_at is None and coordinator.progress < 100
    assert indexing.request_rebuild().pk == coordinator.pk


def _queued_topic(monkeypatch, generation_status="active"):
    topic = Topic.objects.create(name="可恢复的公开主题", slug="restored-discovery-topic", editorial_status="published")
    def current_topic(kind):
        if kind == "topic":
            row, header = sources.get_source(kind, topic.pk)
            if row is not None:
                yield row, header
    # Data migrations also seed published knowledge. This risk fixture scans
    # only its target while still using the real public-source adapter.
    monkeypatch.setattr(indexing, "iter_source_headers", current_topic)
    generation = SemanticIndexVersion.discovery_objects.create(index_family="discovery",
        uid=f"restored-{uuid4().hex}", provider="local", status=generation_status)
    header = sources.get_source("topic", topic.pk)[1]
    assert indexing.schedule_sources(generation) == 1
    job = ProcessingJob.objects.get(job_type="discovery_index", stats__source_id=str(topic.pk))
    return topic, generation, header, job


@pytest.mark.parametrize("generation_status", ["building", "ready", "active"])
def test_withdrawn_topic_restored_unchanged_requeues_superseded_source(api_client, admin_user, monkeypatch, generation_status):
    topic, generation, header, job = _queued_topic(monkeypatch, generation_status)
    # A source may be withdrawn after chunks/checkpoints succeeded but before
    # its source-state completion. Keep these derived rows on requeue.
    document = DiscoveryDocument.objects.create(generation=generation, channel="entities", source_type="topic",
        source_id=topic.pk, source_revision=header["source_revision"], scope_token=header["scope_token"],
        input_hash=sources.fingerprint(header["text"]), text=header["text"], normalized_text=header["text"],
        keyword_ready=True, vector_ready=True, indexed_at=timezone.now())
    job.stats["completed_units"] = 1
    job.attempt = job.max_attempts - 1
    job.save(update_fields=["stats", "attempt"])
    old_task = job.task_id
    api_client.force_authenticate(admin_user)
    archived = api_client.post(f"/api/catalog/admin/lifecycle/topic/{topic.pk}/", {"action": "archive"}, format="json")
    assert archived.status_code == 202
    published = api_client.post(f"/api{archived.data['editorial_revision']['publish_url']}", {}, format="json")
    assert published.status_code == 200
    assert sources.get_source("topic", topic.pk) == (None, None)
    indexing.run_job(job.pk, old_task)
    job.refresh_from_db()
    assert job.status == "canceled" and job.error_code == "superseded"
    assert job.attempt == job.max_attempts

    restored = api_client.post(f"/api/catalog/admin/lifecycle/topic/{topic.pk}/", {"action": "restore"}, format="json")
    assert restored.status_code == 200
    detail_url = f"/api/catalog/admin/topics/{topic.pk}/"
    republished = api_client.patch(detail_url, {"editorial_status": "published"}, format="json",
        HTTP_IF_MATCH=api_client.get(detail_url).data["edit_version"])
    assert republished.status_code == 200
    assert sources.get_source("topic", topic.pk)[1]["source_revision"] == header["source_revision"]
    assert indexing.schedule_sources(generation) == 1
    job.refresh_from_db()
    assert job.status == "pending" and job.task_id != old_task
    assert job.attempt == 0 and not job.error_code and job.finished_at is None
    assert job.stats["completed_units"] == 0
    assert ProcessingJob.objects.filter(job_type="discovery_index", stats__source_id=str(topic.pk)).count() == 1
    document.refresh_from_db()
    assert document.keyword_ready and document.vector_ready and document.indexed_at is not None
    new_task = job.task_id
    indexing.run_job(job.pk, old_task)
    job.refresh_from_db()
    assert job.status == "pending" and job.task_id == new_task


@pytest.mark.parametrize("error_code", ["application_rollback", "canceled_by_admin", ""])
def test_source_schedule_preserves_other_cancellations(monkeypatch, error_code):
    _, generation, _, job = _queued_topic(monkeypatch)
    ProcessingJob.objects.filter(pk=job.pk).update(status="canceled", error_code=error_code, attempt=1)
    indexing.schedule_sources(generation)
    job.refresh_from_db()
    assert job.status == "canceled" and job.error_code == error_code and job.attempt == 1


def test_source_schedule_does_not_revive_retired_generation_from_stale_instance(monkeypatch):
    _, generation, _, job = _queued_topic(monkeypatch)
    ProcessingJob.objects.filter(pk=job.pk).update(status="canceled", error_code="superseded", attempt=1)
    SemanticIndexVersion.discovery_objects.filter(pk=generation.pk).update(status="retired")
    indexing.schedule_sources(generation)
    job.refresh_from_db()
    assert job.status == "canceled" and job.attempt == 1


@pytest.mark.parametrize("source_change", ["withdrawn", "changed"])
def test_superseded_source_requeue_rechecks_current_public_header(monkeypatch, source_change):
    topic, generation, header, job = _queued_topic(monkeypatch)
    ProcessingJob.objects.filter(pk=job.pk).update(status="canceled", error_code="superseded", attempt=1)
    # Simulate publication changing after the scheduler's source scan.
    if source_change == "withdrawn":
        Topic.objects.filter(pk=topic.pk).update(editorial_status="archived")
    else:
        Topic.objects.filter(pk=topic.pk).update(description="已经改变的公开内容")
    monkeypatch.setattr(indexing, "iter_source_headers", lambda kind: [(topic, header)] if kind == "topic" else [])
    indexing.schedule_sources(generation)
    job.refresh_from_db()
    assert job.status == "canceled" and job.attempt == 1


def test_source_schedule_does_not_revive_canceled_coordinator(monkeypatch):
    _, generation, _, job = _queued_topic(monkeypatch)
    ProcessingJob.objects.filter(pk=job.pk).update(status="canceled", error_code="superseded",
        stats={**job.stats, "action": "build"}, attempt=1)
    indexing.schedule_sources(generation)
    job.refresh_from_db()
    assert job.status == "canceled" and job.attempt == 1


def test_succeeded_source_restored_after_withdrawal_cleanup_replays_units(monkeypatch):
    topic, generation, header, job = _queued_topic(monkeypatch)
    document = DiscoveryDocument.objects.create(generation=generation, channel="entities", source_type="topic",
        source_id=topic.pk, source_revision=header["source_revision"], scope_token=header["scope_token"],
        input_hash=sources.fingerprint(header["text"]), text=header["text"], normalized_text=header["text"],
        keyword_ready=True, vector_ready=True, indexed_at=timezone.now())
    ProcessingJob.objects.filter(pk=job.pk).update(status="succeeded", attempt=1,
        stats={**job.stats, "completed_units": 1}, finished_at=timezone.now())
    DiscoverySourceState.objects.filter(job=job).update(source_revision=header["source_revision"],
        expected_count=1, completed_count=1, indexed_at=timezone.now())
    # Model the external deletion confirmation; run the actual withdrawal
    # cleanup so the old checkpoint outlives its deleted documents/state.
    def external_index(method, path, data=None):
        if path.endswith("/search"):
            return {"hits": [{"id": str(key)} for key in DiscoveryDocument.objects.filter(
                generation=generation).values_list("pk", flat=True)]}
        return {"taskUid": 1}
    monkeypatch.setattr(indexing, "meili", external_index)
    monkeypatch.setattr(indexing, "wait_index_task", lambda *args, **kwargs: {})
    topic.editorial_status = "archived"
    topic.save(update_fields=["editorial_status"])
    assert indexing.schedule_sources(generation) == 0
    assert not DiscoveryDocument.objects.filter(pk=document.pk).exists()
    assert not DiscoverySourceState.objects.filter(generation=generation, source_id=topic.pk).exists()
    topic.editorial_status = "published"
    topic.save(update_fields=["editorial_status"])
    assert sources.get_source("topic", topic.pk)[1]["source_revision"] == header["source_revision"]
    assert indexing.schedule_sources(generation) == 1
    job.refresh_from_db()
    assert job.status == "pending" and job.attempt == 0
    assert job.stats["completed_units"] == 0
