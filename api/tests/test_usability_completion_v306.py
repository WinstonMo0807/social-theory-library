from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import Discipline, Subdiscipline, KnowledgeNode, ReadingPath, EditorialRevision, EditorialRevisionMedia, EnrichmentCandidate, HealthCheckRun, RecommendationPolicy
from catalog.services.field_assistant.curation import lookup_curation_field
from catalog.services.editorial_revision import publish_editorial_revision
from catalog.services.knowledge_studio import _assistance_usage
from ingestion.models import AuditEvent
from .editorial_fixtures import editorial_request
from .test_media_v305 import picture
from .test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind", ["discipline", "subdiscipline"])
def test_taxonomy_image_upload_preview_publish_clear_and_history(api_client, admin_user, settings, tmp_path, kind):
    settings.MEDIA_ROOT = tmp_path
    settings.THEORY_SYSTEM_ENABLED = True
    discipline = Discipline.objects.create(name="图片学科", code="image-test", slug="image-test", editorial_status="published")
    target = discipline if kind == "discipline" else Subdiscipline.objects.create(name="图片子学科", slug="image-sub", discipline=discipline, editorial_status="published")
    target.hero_image.save("original.png", picture(), save=True)
    original = target.hero_image.name
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/{kind}s/{target.pk}/"
    saved = editorial_request(api_client, "patch", url, {"hero_image": picture(size=(1200, 800))}, format="multipart")
    assert saved.status_code == 202, saved.data
    assert saved.data["hero_image"].startswith("/api/catalog/admin/media/")
    target.refresh_from_db()
    assert target.hero_image.name == original and target.hero_rendition_id is None
    revision = EditorialRevision.objects.get(target_type=kind, target_id=target.pk, status="draft")
    assert EditorialRevisionMedia.objects.filter(editorial_revision=revision).exists()
    assert api_client.get(f"/api/catalog/knowledge-media/{kind}/{target.pk}/file/").status_code == 404
    publish_editorial_revision(revision.pk, actor=admin_user)
    target.refresh_from_db()
    assert target.hero_rendition_id and target.hero_image.storage.exists(original)
    api_client.force_authenticate(None)
    assert api_client.get(f"/api/catalog/knowledge-media/{kind}/{target.pk}/file/").status_code == 200
    from catalog.serializers import DisciplineSerializer, SubdisciplineSerializer
    data = (DisciplineSerializer if kind == "discipline" else SubdisciplineSerializer)(target).data
    assert "/knowledge-media/" in data["hero_image"] and "/admin/" not in data["hero_image"]
    if kind == "discipline":
        public = api_client.get(f"/api/catalog/theory-system/disciplines/{target.slug}/")
        assert public.status_code == 200, public.data
        assert "/knowledge-media/" in public.data["discipline"]["hero_image"]
        assert "/admin/" not in public.data["discipline"]["hero_image"]
    from catalog.services.knowledge_media import select_knowledge_image
    from catalog.knowledge_media_views import image_state
    clearing = select_knowledge_image(kind, target.pk, None, actor=admin_user, fingerprint=image_state(target, kind)["fingerprint"])
    target.refresh_from_db()
    assert target.hero_rendition_id
    publish_editorial_revision(clearing.pk, actor=admin_user)
    target.refresh_from_db()
    assert target.hero_rendition_id is None and target.hero_image.storage.exists(original)


def test_curation_lookup_filters_old_inputs_and_explicit_lookup_refreshes(admin_user):
    node = KnowledgeNode.objects.create(canonical_name_zh="原理论", slug="context-node", node_type="theory_tradition")
    EnrichmentCandidate.objects.create(target_type="knowledge_node", target_id=node.pk, field_name="alias", conflict_group="alias:old", proposed_value={"alias": "旧条件候选"}, fingerprint="a" * 64, refresh_after=timezone.now() + timedelta(days=1))
    def enrich(request, actor):
        candidate = EnrichmentCandidate.objects.create(target_type="knowledge_node", target_id=node.pk, field_name="alias", conflict_group="alias:current", proposed_value={"alias": request.form_context["curation_context"]["name"] + "译名"}, fingerprint=uuid4().hex * 2, request_context={"curation_fingerprint": request.form_context["curation_fingerprint"]}, refresh_after=timezone.now() + timedelta(days=1))
        assert "private_notes" not in request.form_context and "private_notes" not in request.form_context["curation_context"]
        return SimpleNamespace(candidates=[candidate], errors=[])
    arguments = dict(object_type="knowledge_node", object_id=node.pk, field_name="alias", current_value=[], actor=admin_user)
    with patch("catalog.services.field_assistant.curation.FieldEnrichmentService.enrich", side_effect=enrich) as run:
        first = lookup_curation_field(**arguments, query="新理论", form_context={"name": "新理论", "private_notes": "not sent"}, allow_external=True)
        assert first["results"][0]["label"] == "新理论译名"
        same = lookup_curation_field(**arguments, query="新理论", form_context={"name": "新理论"})
        assert same["results"][0]["label"] == "新理论译名"
        changed = lookup_curation_field(**arguments, query="另一理论", form_context={"name": "另一理论"})
        assert changed["results"] == [] and changed["state"] == "not_run"
        updated = lookup_curation_field(**arguments, query="另一理论", form_context={"name": "另一理论"}, allow_external=True)
        assert updated["results"][0]["label"] == "另一理论译名"
        assert run.call_count == 2


@pytest.mark.parametrize("kind", ["disciplines", "subdisciplines", "theory-system/nodes", "theory-system/reading-paths"])
def test_knowledge_collection_can_be_traversed_beyond_first_page(api_client, admin_user, settings, kind):
    settings.THEORY_SYSTEM_ENABLED = True
    discipline = Discipline.objects.create(name="分页所属", slug="page-parent", code="page-parent")
    ids = set()
    for index in range(26):
        name, slug = f"分页资料{index:02}", f"paged-{index}"
        if kind == "disciplines":
            target = Discipline.objects.create(name=name, slug=slug, code=slug)
        elif kind == "subdisciplines":
            target = Subdiscipline.objects.create(name=name, slug=slug, discipline=discipline)
        elif kind == "theory-system/nodes":
            target = KnowledgeNode.objects.create(canonical_name_zh=name, slug=slug)
        else:
            target = ReadingPath.objects.create(title=name, slug=slug)
        ids.add(str(target.pk))
    api_client.force_authenticate(admin_user)
    found, page, total = [], 1, None
    while True:
        response = api_client.get(f"/api/catalog/admin/{kind}/", {"page": page})
        assert response.status_code == 200, response.data
        total = response.data["count"]
        found.extend(str(row["id"]) for row in response.data["results"])
        if not response.data["next"]:
            break
        page += 1
    assert page >= 2 and len(found) == total and len(set(found)) == len(found) and ids <= set(found)


def test_recommendation_preview_keeps_public_snapshot_and_publishes_exact_list(api_client, admin_user):
    for index in range(5):
        published_edition(f"预览推荐{index}")
    policy = RecommendationPolicy.objects.get(placement="home_featured")
    api_client.force_authenticate(admin_user)
    base = "/api/catalog/admin/recommendations/home_featured/"
    count = policy.snapshots.count()
    preview = api_client.post(base + "preview/", {}, format="json")
    assert preview.status_code == 200 and preview.data["public_unchanged"]
    from catalog.serializers import RecommendationPolicySerializer
    assert preview.data["expected_updated_at"] == RecommendationPolicySerializer(policy).data["updated_at"]
    assert policy.snapshots.count() == count
    body = {key: preview.data[key] for key in ("preview_token", "expected_snapshot_id", "expected_updated_at")}
    body.update(confirm=True, request_key=str(uuid4()))
    invalid = api_client.post(base + "refresh/", {**body, "preview_token": body["preview_token"] + "x"}, format="json")
    assert invalid.status_code == 409 and policy.snapshots.count() == count
    published = api_client.post(base + "refresh/", body, format="json")
    assert published.status_code == 200, published.data
    assert [row["target"]["id"] for row in published.data["current"]["items"]] == [row["id"] for row in preview.data["items"]]
    replay = api_client.post(base + "refresh/", body, format="json")
    assert replay.status_code == 200 and replay.data["replayed"] and policy.snapshots.count() == count + 1


def test_queue_read_has_no_live_probes_and_expired_checks_are_unknown(api_client, admin_user, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    api_client.force_authenticate(admin_user)
    with patch("ingestion.services.health.http_service_health", side_effect=AssertionError("GET cannot probe")), patch("ingestion.services.health.celery_broker_health", side_effect=AssertionError("GET cannot probe")):
        unknown = api_client.get("/api/ingestion/queue-health/")
        assert unknown.status_code == 200 and unknown.data["healthy"] is None
        for key in ("cache", "worker", "ocr", "semantic"):
            HealthCheckRun.objects.create(probe_key=key, capability="test", reachable=True, functional=True, configured=True, productive=True, status="healthy")
        fresh = api_client.get("/api/ingestion/queue-health/")
        assert fresh.data["healthy"] is True and fresh.data["checked_at"]
        HealthCheckRun.objects.update(started_at=timezone.now() - timedelta(days=1))
        stale = api_client.get("/api/ingestion/queue-health/")
        assert stale.data["healthy"] is None and stale.data["stale"] and stale.data["ocr"]["reachable"] is None


def test_usage_includes_modified_removed_and_unclassified_events(admin_user):
    from .test_public_management_v306 import candidate
    from catalog.models import Person
    person = Person.objects.create(preferred_name="使用统计")
    row = candidate(person, 918, "accepted")
    for action in ("field_prefill_modified_adoption", "field_prefill_removed", "field_prefill_removed_or_edited", "field_prefill_modified_adoption"):
        AuditEvent.objects.create(actor=admin_user, object_type="catalog.EnrichmentCandidate", object_id=str(row.pk), action=action)
    usage = _assistance_usage("person", person.pk)
    assert usage["event_count"] == 4 and usage["modified_adoptions"] == 1
    assert usage["removed_prefills"] == 1 and usage["unclassified_prefill_changes"] == 1
    assert usage["verified_cost"] is None and usage["active_time_seconds"] is None
