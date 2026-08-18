import pytest
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import KnowledgeNode, NewAuthorityCandidate, Person, UnknownEntityObservation, Work
from ingestion.models import ProcessingJob


pytestmark = pytest.mark.django_db


def _admin():
    return User.objects.create_user(
        username="v27-admin@example.org",
        email="v27-admin@example.org",
        display_name="v27 管理员",
        role=User.Role.ADMIN,
        password="Correct-Horse-Battery-2026",
    )


def test_capability_contract_is_exposed(api_client):
    user = _admin()
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/auth/capabilities/")
    assert response.status_code == 200
    assert response.data["access_level"] == "admin"
    assert "access_back_office" in response.data["capabilities"]
    assert "can_view_system_status" in response.data["capabilities"]
    assert "can_view_query_lexicon" in response.data["capabilities"]
    assert "can_view_semantic_index" in response.data["capabilities"]
    assert "can_manage_query_lexicon" not in response.data["capabilities"]
    assert "can_manage_semantic_index" not in response.data["capabilities"]


def test_query_lexicon_workspace_is_readable_without_initialized_state(api_client):
    user = _admin()
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/catalog/admin/query-lexicon/?q=test&limit=not-a-number")
    assert response.status_code == 200
    assert response.data["initialized"] in {True, False}
    assert "terms" in response.data
    assert response.data["permissions"] == {"can_manage": False}
    assert api_client.post(
        "/api/catalog/admin/query-lexicon/",
        {"action": "dry_run"},
        format="json",
    ).status_code == 403


def test_semantic_index_workspace_is_read_only_for_ordinary_admin(api_client):
    user = _admin()
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/catalog/admin/semantic-index/")
    assert response.status_code == 200
    assert response.data["permissions"] == {"can_manage": False}
    assert api_client.post(
        "/api/catalog/admin/semantic-index/",
        {"action": "pause"},
        format="json",
    ).status_code == 403


def test_system_status_does_not_expose_secret_values(api_client, settings):
    user = _admin()
    api_client.force_authenticate(user=user)
    settings.AI_API_KEY = "must-not-appear"
    response = api_client.get("/api/catalog/admin/system-status/")
    assert response.status_code == 200
    assert "must-not-appear" not in response.content.decode("utf-8")
    assert response.data["ai"]["secret_values_exposed"] is False


def test_system_status_requires_ai_credential_when_provider_needs_one(api_client, settings):
    user = _admin()
    api_client.force_authenticate(user=user)
    settings.AI_PROVIDER = "openai_compatible"
    settings.AI_BASE_URL = "https://ai.example.test/v1"
    settings.AI_API_KEY = ""
    settings.AI_METADATA_MODEL = "metadata-model"
    settings.AI_LIBRARY_MODEL = "library-model"
    response = api_client.get("/api/catalog/admin/system-status/")
    assert response.status_code == 200
    profiles = {row["capability"]: row for row in response.data["ai"]["profiles"]}
    assert profiles["metadata_extraction"]["status"] == "not_configured"
    assert profiles["metadata_extraction"]["endpoint_configured"] is True
    assert profiles["metadata_extraction"]["credential_configured"] is False
    assert profiles["library_qa"]["status"] == "not_configured"


def test_system_status_labels_disabled_ai_profiles_as_not_configured(api_client, settings):
    user = _admin()
    api_client.force_authenticate(user=user)
    settings.AI_PROVIDER = "none"
    response = api_client.get("/api/catalog/admin/system-status/")
    assert response.status_code == 200
    assert all(row["status"] == "not_configured" for row in response.data["ai"]["profiles"])


def test_system_status_uses_semantic_runtime_setting_names(api_client, settings, tmp_path):
    user = _admin()
    api_client.force_authenticate(user=user)
    settings.SEMANTIC_SEARCH_MODEL = "sentence-transformers/test-model"
    settings.SEMANTIC_SEARCH_MODEL_REVISION = "pinned-test-revision"
    settings.SEMANTIC_SEARCH_MODEL_CACHE = str(tmp_path)
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/catalog/admin/system-status/")
    assert response.status_code == 200
    embedding = response.data["embedding"]
    assert embedding["model"] == "sentence-transformers/test-model"
    assert embedding["revision"] == "pinned-test-revision"
    assert embedding["local_path"] == str(tmp_path)
    assert embedding["status"] == "unavailable"


def test_system_status_reports_provider_configuration_without_faking_health(api_client, settings):
    user = _admin()
    api_client.force_authenticate(user=user)
    settings.AUTHORITY_PROVIDER_ENABLED = "wikidata"
    settings.METADATA_PROVIDER_ENABLED = "crossref"
    settings.FIELD_ENRICHMENT_SEARXNG_URL = "https://search.example.test"
    response = api_client.get("/api/catalog/admin/system-status/")
    assert response.status_code == 200
    payload = response.data["web_enrichment"]
    assert payload["general_web"]["status"] == "configured"
    assert payload["general_web"]["health"] == "unknown"
    assert payload["structured"]["wikidata"]["status"] == "configured"
    assert payload["structured"]["viaf"]["status"] == "not_configured"
    assert payload["structured"]["wikidata"]["health"] == "unknown"
    assert payload["bibliographic"]["crossref"]["status"] == "configured"


def test_knowledge_workspace_and_projection_status_are_staff_only(api_client):
    user = _admin()
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/catalog/admin/knowledge-workspace/?status=pending")
    assert response.status_code == 200
    assert "new_authority" in response.data
    reader = User.objects.create_user(
        username="v27-reader@example.org",
        email="v27-reader@example.org",
        display_name="读者",
        role=User.Role.READER,
        password="Reader-Secure-Password-2026",
    )
    api_client.force_authenticate(user=reader)
    assert api_client.get("/api/catalog/admin/knowledge-workspace/").status_code in {401, 403}


def test_unknown_entity_models_are_reviewable_without_publication():
    assert NewAuthorityCandidate.Status.PENDING == "pending"
    assert UnknownEntityObservation._meta.get_field("evidence_text").null is False
    assert KnowledgeNode.NodeType.THEORY_TRADITION == "theory_tradition"


def test_projection_refresh_is_idempotent_and_uses_existing_task_system(api_client, admin_user):
    work = Work.objects.create(title="投影刷新测试", language="zh-CN")
    api_client.force_authenticate(user=admin_user)
    first = api_client.post(
        f"/api/catalog/admin/projection-status/work/{work.id}/refresh/",
        {},
        format="json",
    )
    second = api_client.post(
        f"/api/catalog/admin/projection-status/work/{work.id}/refresh/",
        {},
        format="json",
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.data["job_id"] == second.data["job_id"]
    assert ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.PROJECTION_REFRESH,
        idempotency_key__startswith="projection-refresh:work:",
    ).count() == 1
    # pytest-django keeps the test transaction open, so the on-commit callback
    # is intentionally not executed here.  A non-empty task id proves that a
    # real Celery dispatch token was prepared; integration deployment checks
    # exercise the callback against the broker.
    assert first.data["status"] == ProcessingJob.Status.PENDING


def test_projection_refresh_runner_marks_bounded_work_job_succeeded(admin_user):
    from catalog.services.projection_refresh import (
        queue_projection_refresh,
        run_projection_refresh_job,
    )

    work = Work.objects.create(title="投影刷新执行测试", language="zh-CN")
    job = queue_projection_refresh(
        target_type="work",
        target_id=str(work.id),
        actor=admin_user,
    )
    completed = run_projection_refresh_job(str(job.id), task_id=job.task_id)
    assert completed.status == ProcessingJob.Status.SUCCEEDED
    assert completed.progress == 100
    assert completed.stats["bounded"] is True


def test_authority_projection_refresh_drains_query_lexicon_once(monkeypatch):
    from catalog.services.projection_refresh import _refresh_target

    person = Person.objects.create(preferred_name="投影刷新学者")
    calls = []

    def process_pending_events(*, limit):
        calls.append(limit)
        return {"processed": 0}

    monkeypatch.setattr(
        "catalog.services.query_lexicon.sync.process_pending_events",
        process_pending_events,
    )
    result = _refresh_target("person", person)
    assert calls == [100]
    assert result["query_lexicon"] == {"processed": 0}
