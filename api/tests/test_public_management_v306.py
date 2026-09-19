from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from catalog.models import (
    Contribution, Edition, EditorialRevision, EditorialRevisionMedia, EnrichmentCandidate,
    HealthCheckRun, MediaAsset, Person, ScholarProfile, Work,
)
from catalog.services.knowledge_studio import _assistance_usage
from catalog.services.media import build_rendition, ingest_image
from catalog.services.person_merges import prepare_person_merge
from catalog.services.query_lexicon.sync import ensure_query_lexicon_state
from catalog.services.system_health import HEALTH_CHECKS, functional_health_snapshot
from ingestion.models import AuditEvent
from .test_media_v305 import picture

pytestmark = pytest.mark.django_db


def test_all_health_surfaces_use_the_same_expired_observation():
    now = timezone.now()
    for probe in HEALTH_CHECKS.all():
        HealthCheckRun.objects.create(probe_key=probe.key, capability=probe.capability, status="healthy", source="manual",
                                      configured=True, reachable=True, functional=True, productive=True,
                                      started_at=now - timedelta(seconds=2 * probe.interval_seconds + 1))
    with patch("catalog.services.processing_center_diagnostics.processing_center_diagnostics", return_value={}), patch("catalog.services.system_health.run_health_probe") as run:
        snapshot = functional_health_snapshot()
    assert snapshot["overall_status"] == "unknown"
    assert all(row["status"] == "unknown" for row in snapshot["layers"])
    for capability in snapshot["capabilities"]:
        assert capability["status"] == "unknown"
        assert capability["functional"] is None and capability["productive"] is None
        for observation in capability["dependencies"]:
            assert observation["status"] == "unknown" and observation["stale"] is True
            assert observation["error_code"] == "stale_probe" and observation["observation_id"]
    run.assert_not_called()


def test_fresh_failed_probe_remains_actionable_and_is_not_replaced_by_fresh_response_time():
    probe = HEALTH_CHECKS.get("database")
    HealthCheckRun.objects.create(probe_key=probe.key, capability=probe.capability, status="failed", source="manual",
                                  functional=False, productive=False, error_code="database_unavailable", started_at=timezone.now())
    with patch("catalog.services.processing_center_diagnostics.processing_center_diagnostics", return_value={}):
        snapshot = functional_health_snapshot()
    database = next(dependency for capability in snapshot["capabilities"] for dependency in capability["dependencies"] if dependency["probe_key"] == "database")
    assert database["status"] == "failed" and database["functional"] is False
    assert database["fresh"] is True and database["stale"] is False
    assert snapshot["overall_status"] == "failed"


def candidate(target, number, status):
    return EnrichmentCandidate.objects.create(target_type="person", target_id=target.pk, field_name="biography",
                                               candidate_kind="interpretive", proposed_value=f"候选{number}",
                                               status=status, fingerprint=f"{number:064x}", conflict_group=f"v306-{number}",
                                               accepted_authority_model="catalog.Person" if status == "accepted" else "",
                                               accepted_authority_id=target.pk if status == "accepted" else None)


def test_usage_denominator_and_events_are_scoped_and_do_not_invent_quality_cost_or_time(admin_user):
    person = Person.objects.create(preferred_name="当前人物")
    other = Person.objects.create(preferred_name="别的人物")
    accepted = candidate(person, 1, "accepted")
    rejected = candidate(person, 2, "rejected")
    candidate(person, 3, "pending")
    foreign = candidate(other, 4, "accepted")
    for row in (accepted, rejected, foreign):
        AuditEvent.objects.create(actor=admin_user, object_type="catalog.EnrichmentCandidate", object_id=str(row.pk),
                                  action="reject_field_enrichment_candidate" if row == rejected else "accept_field_enrichment_candidate")
    usage = _assistance_usage("person", person.pk)
    assert usage["total"] == 3 and usage["reviewed"] == 2
    assert usage["acceptance"] == {"numerator": 1, "denominator": 2, "is_accuracy": False}
    assert usage["event_count"] == 2
    assert {row["candidate_id"] for row in usage["events"]} == {str(accepted.pk), str(rejected.pk)}
    assert usage["verified_cost"] is None and usage["active_time_seconds"] is None
    assert usage["modified_adoptions"] == 0 and usage["withdrawals"] is None
    assert usage["page_load_performs_live_probes"] is False


def test_usage_empty_is_no_data_not_a_failed_lookup():
    person = Person.objects.create(preferred_name="没有运行候选")
    usage = _assistance_usage("person", person.pk)
    assert usage["total"] == 0 and usage["events"] == []
    assert usage["acceptance"]["denominator"] == 0
    assert usage["period_start"] is None


def test_manual_recommendation_selection_requires_active_public_identity():
    from catalog.knowledge_views import _resolve_manual_target
    work = Work.objects.create(title="只有发布标志", document_type="book")
    Edition.objects.create(work=work, state="published", is_primary=True)
    assert _resolve_manual_target("work", str(work.pk)) is None
    person = Person.objects.create(preferred_name="未核验公开档案", authority_status="draft")
    scholar = ScholarProfile.objects.create(person=person, slug="v306-no-authority", editorial_status="published")
    assert _resolve_manual_target("scholar", str(scholar.pk)) is None


def test_main_studio_payload_includes_public_control_usage_and_broad_single_registry(api_client, admin_user):
    person = Person.objects.create(preferred_name="真实Studio人物", authority_status="verified")
    scholar = ScholarProfile.objects.create(person=person, slug="studio-v306", editorial_status="published", short_description="旧公开简介")
    EditorialRevision.objects.create(target_type="scholar_profile", target_id=scholar.pk, revision=1, base_revision=0,
                                     status="draft", patch={"short_description": "新草稿简介"},
                                     materialized_preview={"short_description": "新草稿简介"}, changed_fields=["short_description"], idempotency_key="v306-studio-draft")
    api_client.force_authenticate(admin_user)
    response = api_client.get("/api/catalog/admin/knowledge-workspace/", {"selected_type": "scholar", "selected_id": scholar.pk})
    assert response.status_code == 200
    studio = response.data["studio"]
    selection = studio["selection"]
    assert selection["id"] == str(scholar.pk)
    assert selection["public_control"]["contract_version"] == "3.0.6"
    assert selection["public_control"]["draft_published_diff"][0]["draft"] == "新草稿简介"
    assert selection["assistance_usage"]["target_id"] == str(person.pk)
    assert {row["object_type"] for row in studio["public_management_coverage"]["public_surfaces"]} >= {"work", "site", "media", "reader", "reading_path", "recommendation"}
    assert api_client.get("/api/catalog/scholars/studio-v306/").data["short_description"] == "旧公开简介"


def test_topic_preview_uses_actual_public_detail_producer_not_only_the_base_serializer(api_client, admin_user):
    from catalog.models import Topic, WorkTopicRelation
    from .test_publication_invariants_v305 import published_edition
    edition, _revision = published_edition("主题实际读取作品")
    topic = Topic.objects.create(name="主题真实来源", slug="v306-topic-source", editorial_status="published")
    WorkTopicRelation.objects.create(work=edition.work, topic=topic, review_status="approved")
    api_client.force_authenticate(admin_user)
    workspace = api_client.get("/api/catalog/admin/knowledge-workspace/", {"selected_type": "topic", "selected_id": topic.pk})
    assert workspace.status_code == 200
    selection = workspace.data["studio"]["selection"]
    public = api_client.get(f"/api/catalog/topics/{topic.slug}/")
    assert public.status_code == 200
    assert [row["id"] for row in selection["preview_perspectives"]["published"]["data"]["works"]] == [row["id"] for row in public.data["works"]]
    module = next(row for row in selection["public_control"]["modules"] if row["module_id"] == "topic-works")
    assert module["available"] is True and "works" in module["populated_fields"]


def test_person_business_impact_preserves_guard_and_shows_actual_role_and_no_false_public_url(api_client, superadmin_user):
    source = Person.objects.create(preferred_name="译者来源", authority_status="verified")
    target = Person.objects.create(preferred_name="译者保留", authority_status="verified")
    work = Work.objects.create(title="真实受影响作品", document_type="book")
    edition = Edition.objects.create(work=work, state="published", publication_mode="bibliographic", publication_year=2026, publisher="测试出版社")
    contribution = Contribution.objects.create(edition=edition, person=source, role="translator", approved=True)
    ensure_query_lexicon_state()
    fingerprint = prepare_person_merge(source, target)["fingerprint"]
    api_client.force_authenticate(superadmin_user)
    response = api_client.get(f"/api/catalog/admin/people/{source.pk}/merge-preview/", {"target_person": target.pk})
    assert response.status_code == 200
    assert response.data["fingerprint"] == fingerprint
    impact = response.data["business_impact"]["editions"][0]
    assert impact["title"] == work.title and impact["edition_label"] == "测试出版社 · 2026"
    assert impact["roles"][0]["role"] == "translator" and impact["roles"][0]["role_label"] == "译者"
    assert impact["publication"]["public_url"] == ""
    assert f"edition={edition.pk}" in impact["editor_url"]
    contribution.refresh_from_db()
    assert contribution.role == "translator" and contribution.person_id == source.pk


def test_media_collection_can_reach_every_image_and_preserves_legacy_endpoint(api_client, admin_user):
    for index in range(61):
        MediaAsset.objects.create(file=f"private/test/{index}.png", media_type="image/png", width=1, height=1,
                                  checksum=f"{index:064x}", byte_size=1)
    api_client.force_authenticate(admin_user)
    seen = []
    for page in (1, 2, 3):
        response = api_client.get("/api/catalog/admin/media/collection/", {"page": page})
        assert response.status_code == 200
        assert response.data["count"] == 61 and response.data["pages"] == 3
        seen.extend(row["id"] for row in response.data["results"])
    assert len(seen) == len(set(seen)) == 61
    assert len(api_client.get("/api/catalog/admin/media/").data) == 60
    assert api_client.get("/api/catalog/admin/media/collection/", {"page": "bad"}).status_code == 404


def test_media_detail_reports_draft_and_actual_public_references_without_file_mutation(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    media, _ = ingest_image(picture(), actor=admin_user)
    rendition = build_rendition(media.pk, kind="portrait")
    person = Person.objects.create(preferred_name="引用肖像", authority_status="verified", portrait_rendition=rendition)
    scholar = ScholarProfile.objects.create(person=person, slug="v306-media-reference", editorial_status="published")
    revision = EditorialRevision.objects.create(target_type="scholar_profile", target_id=scholar.pk, revision=1,
                                                base_revision=0, status="draft", idempotency_key="v306-media-draft")
    EditorialRevisionMedia.objects.create(editorial_revision=revision, rendition=rendition)
    before = (media.checksum, media.file.name)
    api_client.force_authenticate(admin_user)
    response = api_client.get(f"/api/catalog/admin/media/{media.pk}/")
    assert response.status_code == 200
    refs = response.data["references"]
    assert {row["kind"] for row in refs["results"]} == {"draft", "current_public"}
    assert any(row["public_url"] == f"/scholars/{scholar.slug}" for row in refs["results"])
    assert refs["reader_private_data"] == "not_read"
    media.refresh_from_db()
    assert (media.checksum, media.file.name) == before
