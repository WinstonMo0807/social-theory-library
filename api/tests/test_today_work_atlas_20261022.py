"""PDF80/81 queue contracts. Defined for the final acceptance phase, not run."""
from uuid import uuid4

import pytest

from accounts.models import User
from catalog.models import Asset, CatalogingSession, Contribution, Edition, EditorialRevision, Person, SemanticIndexJob, Topic, Work
from ingestion.models import ProcessingJob, UploadBatch, UploadItem
from ingestion.services.processing_center import processing_task_page

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/today-work/"


def topic_draft(actor, index=0):
    topic = Topic.objects.create(name=f"真实草稿 {index}", slug=f"today-{uuid4()}")
    EditorialRevision.objects.create(target_type="topic", target_id=topic.pk, revision=1, created_by=actor,
        materialized_preview={"name": f"已编辑标题 {index}"}, idempotency_key=f"today:{uuid4()}")
    return topic


def test_full_counts_pagination_and_sql_uuid_routes(api_client, admin_user):
    for index in range(23):
        topic_draft(admin_user, index)
    api_client.force_authenticate(admin_user)
    first = api_client.get(URL, {"category": "editing", "q": "已编辑标题"})
    second = api_client.get(URL, {"category": "editing", "q": "已编辑标题", "page": 2})
    assert first.status_code == second.status_code == 200
    assert first.data["count"] == first.data["counts"]["editing"] == 23
    assert len(first.data["results"]) == 20 and len(second.data["results"]) == 3
    assert not {r["id"] for r in first.data["results"]} & {r["id"] for r in second.data["results"]}
    for row in first.data["results"]:
        assert row["url"] == f'/admin/topics/{row["object_id"]}'
    assert first["Cache-Control"] == "private, no-store"


def test_reader_denied_and_editor_never_receives_processing_counts(api_client, admin_user, reader_user):
    ProcessingJob.objects.create(job_type="ocr", status="failed", created_by=admin_user)
    editor = User.objects.create_user(username="today-editor", role="editor")
    topic_draft(editor)
    api_client.force_authenticate(editor)
    data = api_client.get(URL).data
    assert data["restricted"] is True and data["counts"]["all"] == 1
    assert all(row["kind"] != "processing" for row in data["results"])
    assert api_client.get(URL, {"kind": "processing"}).data["count"] == 0
    assert api_client.get("/api/ingestion/processing-center/").status_code == 403
    api_client.force_authenticate(reader_user)
    assert api_client.get(URL).status_code == 403
    api_client.force_authenticate(None)
    assert api_client.get(URL).status_code in (401, 403)


def test_mine_uses_actual_editor_and_job_requester(api_client, admin_user):
    other = User.objects.create_user(username="other-today", role="admin")
    own = topic_draft(admin_user)
    topic_draft(other)
    semantic = SemanticIndexJob.objects.create(operation="build", status="partial", requested_by=admin_user)
    ProcessingJob.objects.create(job_type="ocr", status="failed", created_by=other)
    api_client.force_authenticate(admin_user)
    data = api_client.get(URL, {"owner": "me"}).data
    assert {row["object_id"] for row in data["results"]} == {str(own.pk), str(semantic.pk)}
    assert next(row for row in data["results"] if row["object_id"] == str(semantic.pk))["state"] == "partial"


def test_task_ordering_and_filters_preserve_real_state(api_client, admin_user):
    old = ProcessingJob.objects.create(job_type="ocr", status="paused", created_by=admin_user)
    ProcessingJob.objects.create(job_type="text_extraction", status="running", created_by=admin_user)
    api_client.force_authenticate(admin_user)
    data = api_client.get(URL, {"kind": "processing", "state": "paused", "ordering": "updated_at"}).data
    assert data["count"] == data["counts"]["all"] == 1
    assert data["results"][0]["object_id"] == str(old.pk)
    assert f"task_id={old.pk}" in data["results"][0]["url"]
    assert "task_source=processing_job" in data["results"][0]["url"]


def test_superseded_failure_is_not_still_a_current_job(api_client, admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="一个版本"))
    old = ProcessingJob.objects.create(edition=edition, job_type="ocr", status="failed")
    ProcessingJob.objects.create(edition=edition, job_type="ocr", status="succeeded")
    api_client.force_authenticate(admin_user)
    data = api_client.get(URL, {"kind": "processing"}).data
    assert str(old.pk) not in {row["object_id"] for row in data["results"]}


def test_a_later_job_does_not_hide_another_active_job(api_client, admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="仍在处理"))
    first = ProcessingJob.objects.create(edition=edition, job_type="ocr", status="running")
    second = ProcessingJob.objects.create(edition=edition, job_type="ocr", status="pending")
    api_client.force_authenticate(admin_user)
    data = api_client.get(URL, {"kind": "processing"}).data
    assert {str(first.pk), str(second.pk)} <= {row["object_id"] for row in data["results"]}


def test_exact_processing_identity_does_not_fallback_to_another_task(admin_user):
    first = ProcessingJob.objects.create(job_type="ocr", status="failed")
    ProcessingJob.objects.create(job_type="ocr", status="running")
    data = processing_task_page({"task_id": str(first.pk), "task_source": "processing_job"}, admin_user)
    assert data["count"] == 1 and data["results"][0]["id"] == str(first.pk)
    assert processing_task_page({"task_id": str(uuid4()), "task_source": "processing_job"}, admin_user)["count"] == 0


def test_catalog_continues_exact_open_session_and_upload(api_client, admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="已有编目"), publication_mode="bibliographic")
    session = CatalogingSession.objects.create(edition=edition, source_type="manual", created_by=admin_user)
    upload = UploadItem.objects.create(batch=UploadBatch.objects.create(created_by=admin_user), source_filename="source.pdf", sha256="a" * 64)
    api_client.force_authenticate(admin_user)
    data = api_client.get(URL, {"kind": "catalog"}).data
    rows = {row["object_id"]: row for row in data["results"]}
    assert rows[str(edition.pk)]["url"] == f"/admin/cataloging/{session.pk}"
    assert rows[str(upload.pk)]["url"] == f"/admin/uploads?item={upload.pk}"


def test_obsolete_asset_job_does_not_reappear(api_client, admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="原文件"))
    asset = Asset.objects.create(edition=edition, kind="normalized", file="synthetic/old.pdf", is_current=False, byte_size=1, sha256="b" * 64)
    job = ProcessingJob.objects.create(edition=edition, asset=asset, job_type="ocr", status="failed")
    api_client.force_authenticate(admin_user)
    assert str(job.pk) not in {row["object_id"] for row in api_client.get(URL, {"kind": "processing"}).data["results"]}


@pytest.mark.parametrize("parameters", [{"page": 0}, {"ordering": "random"}, {"owner": "someone"}, {"kind": "private_notes"}, {"category": "unknown"}])
def test_bad_filters_fail_explicitly(api_client, admin_user, parameters):
    api_client.force_authenticate(admin_user)
    assert api_client.get(URL, parameters).status_code == 400


def test_global_search_includes_formal_topics_and_completed_tasks(api_client, admin_user):
    topic = Topic.objects.create(name="正式检索主题", slug=f"search-{uuid4()}", editorial_status="published")
    job = SemanticIndexJob.objects.create(operation="build", status="completed", requested_by=admin_user, task_id="retained-complete-job")
    api_client.force_authenticate(admin_user)
    result = api_client.get("/api/catalog/admin/search/", {"q": "正式检索主题"})
    assert result.status_code == 200 and result["Cache-Control"] == "private, no-store"
    assert result.data["results"][0]["object_id"] == str(topic.pk)
    assert result.data["results"][0]["state"] == "published"
    assert api_client.get(URL, {"q": "正式检索主题"}).data["count"] == 0
    task = api_client.get("/api/catalog/admin/search/", {"q": "retained-complete-job"}).data
    assert task["count"] == 1 and task["results"][0]["object_id"] == str(job.pk)
    assert task["results"][0]["state"] == "completed"


def test_global_search_author_and_work_draft_title_reuse_existing_identity(api_client, admin_user):
    work = Work.objects.create(title="原有书名")
    edition = Edition.objects.create(work=work, publication_mode="bibliographic")
    person = Person.objects.create(preferred_name="检索作者")
    Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
    EditorialRevision.objects.create(target_type="work", target_id=work.pk, revision=1, created_by=admin_user,
        materialized_preview={"title": "更正后题名"}, idempotency_key=f"search:{uuid4()}")
    api_client.force_authenticate(admin_user)
    for query in ("检索作者", "更正后题名", str(edition.pk)):
        data = api_client.get("/api/catalog/admin/search/", {"q": query, "kind": "catalog"}).data
        assert data["count"] == 1
        assert data["results"][0]["object_id"] == str(edition.pk)
        assert data["results"][0]["title"] == "更正后题名"


def test_global_search_blank_is_empty_and_kind_counts_are_before_tab_filter(api_client, admin_user):
    Topic.objects.create(name="共同查询词", slug=f"search-{uuid4()}", editorial_status="published")
    edition = Edition.objects.create(work=Work.objects.create(title="共同查询词"))
    ProcessingJob.objects.create(edition=edition, job_type="ocr", status="succeeded")
    api_client.force_authenticate(admin_user)
    assert api_client.get("/api/catalog/admin/search/").data["count"] == 0
    data = api_client.get("/api/catalog/admin/search/", {"q": "共同查询词", "kind": "curation"}).data
    assert data["count"] == 1 and data["counts"] == {"all": 3, "catalog": 1, "curation": 1, "processing": 1}


def test_notices_count_every_current_problem_but_return_only_five(api_client, admin_user):
    for index in range(7):
        ProcessingJob.objects.create(job_type="ocr", status="paused" if index % 2 else "failed", created_by=admin_user)
    ProcessingJob.objects.create(job_type="text_extraction", status="running", created_by=admin_user)
    api_client.force_authenticate(admin_user)
    result = api_client.get("/api/catalog/admin/work-notices/")
    assert result.status_code == 200 and result["Cache-Control"] == "private, no-store"
    assert result.data["count"] == 7 and len(result.data["results"]) == 5
    assert all(row["state"] in {"failed", "paused", "partial"} for row in result.data["results"])


def test_search_and_notices_never_expose_forbidden_tasks(api_client, admin_user, reader_user):
    job = ProcessingJob.objects.create(job_type="ocr", status="failed", created_by=admin_user)
    editor = User.objects.create_user(username="search-editor", role="editor")
    for url in ("/api/catalog/admin/search/", "/api/catalog/admin/work-notices/"):
        api_client.force_authenticate(editor)
        response = api_client.get(url, {"q": str(job.pk)})
        assert response.status_code == 200 and response.data["count"] == 0
        api_client.force_authenticate(reader_user)
        assert api_client.get(url).status_code == 403
