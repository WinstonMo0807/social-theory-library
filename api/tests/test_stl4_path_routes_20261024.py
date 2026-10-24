"""M24 candidate acceptance definitions; deliberately not run during development."""
from uuid import uuid4
import pytest
from rest_framework.test import APIClient

from catalog.editorial_read import current_editorial_version
from catalog.models import EditorialRevision, Topic, WorkTopicRelation
from catalog.services.path_route_candidates import arrangements, candidates_for
from catalog.services.research.candidate_adoption import decide_reading_path_candidate
from .test_reading_paths_20261021 import path_with_items, source
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def issue(path, actor, operation="generate", candidate=None, key=None):
    client = APIClient(); client.force_authenticate(user=actor)
    payload = {"operation": operation, "edit_version": current_editorial_version("reading_path", path.pk)}
    if candidate:
        response = client.get(f"/api/catalog/admin/theory-system/reading-paths/{path.pk}/routes/{candidate.pk}/", HTTP_X_EDITOR_OWNER=str(actor.pk))
        assert response.status_code == 200
        payload.update(candidate_id=str(candidate.pk), candidate_version=response.data["candidate_version"])
    key = key or uuid4()
    return client.post(f"/api/catalog/admin/theory-system/reading-paths/{path.pk}/routes/", payload,
        format="json", HTTP_X_EDITOR_OWNER=str(actor.pk), HTTP_IDEMPOTENCY_KEY=str(key)), payload, key


def test_generation_is_recoverable_and_adoption_only_stages_original_draft(admin_user):
    path, stage, items, _ = path_with_items()
    items[0].dependencies = [{"item_id": str(items[1].pk), "kind": "learning_order", "reason": "合成先修关系"}]
    items[0].save(update_fields=["dependencies"])
    response, body, key = issue(path, admin_user)
    assert response.status_code == 200
    assert candidates_for(path.pk).count() == 4
    client = APIClient(); client.force_authenticate(user=admin_user)
    again = client.post(f"/api/catalog/admin/theory-system/reading-paths/{path.pk}/routes/", body,
        format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk), HTTP_IDEMPOTENCY_KEY=str(key))
    assert again.status_code == 200 and candidates_for(path.pk).count() == 4
    assert not EditorialRevision.objects.filter(target_type="reading_path", target_id=path.pk).exists()
    candidate = candidates_for(path.pk).get(title="先修优先")
    adopted, _, _ = issue(path, admin_user, "adopt", candidate)
    assert adopted.status_code == 200
    candidate.refresh_from_db(); path.refresh_from_db()
    assert candidate.status == "adopted" and candidate.adopted_reading_path_id == path.pk
    assert path.status == "published" and path.stages.get().pk == stage.pk
    assert list(path.items.order_by("reading_order").values_list("pk", flat=True)) == [item.pk for item in items]
    draft = EditorialRevision.objects.get(target_type="reading_path", target_id=path.pk, status="draft")
    assert [row["id"] for row in draft.materialized_preview["stage_groups"][0]["items"]] == [str(items[1].pk), str(items[0].pk)]


def test_original_stage_fields_and_identity_survive_ordering_and_cycles_are_visible():
    first, second = str(uuid4()), str(uuid4())
    stages = [{"id": str(uuid4()), "name": "原阶段", "description": "人工说明", "learning_questions": ["人工问题"], "items": [
        {"id": first, "dependencies": [{"kind": "learning_order", "item_id": second}]},
        {"id": second, "dependencies": []}]}]
    plans = list(arrangements(stages, {first: {"publication_year": 1900}, second: {"publication_year": 2000}}))
    assert plans[1][2][0]["description"] == "人工说明" and plans[1][2][0]["learning_questions"] == ["人工问题"]
    assert [row["id"] for row in plans[1][2][0]["items"]] == [second, first]
    stages[0]["items"][1]["dependencies"] = [{"kind": "learning_order", "item_id": first}]
    assert list(arrangements(stages, {first: {}, second: {}}))[1][3]


def test_stale_sources_and_legacy_adoption_cannot_bypass_original_route(admin_user):
    path, _, _, edition = path_with_items()
    response, _, _ = issue(path, admin_user); assert response.status_code == 200
    candidate = candidates_for(path.pk).get(title="先修优先")
    with pytest.raises(ValueError, match="原阅读路径"):
        decide_reading_path_candidate(candidate=candidate, decision="accept", actor=admin_user)
    edition.state = "withdrawn"; edition.save(update_fields=["state"])
    response, _, _ = issue(path, admin_user, "adopt", candidate)
    assert response.status_code == 400
    candidate.refresh_from_db(); assert candidate.status == "pending"


def test_cancel_receipt_blocks_late_generation_and_anonymous_access(admin_user):
    path, _, _, _ = path_with_items(); key = uuid4()
    client = APIClient(); client.force_authenticate(user=admin_user)
    response = client.post(f"/api/catalog/admin/theory-system/reading-paths/routes/commands/{key}/", {"action": "cancel_pending"},
        format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and response.data["state"] == "cancelled"
    response, _, _ = issue(path, admin_user, key=key)
    assert response.status_code == 409 and not candidates_for(path.pk).exists()
    assert APIClient().get(f"/api/catalog/admin/theory-system/reading-paths/{path.pk}/routes/").status_code in (401, 403)


def test_topic_expansion_requires_both_confirmed_relation_and_activated_snapshot(admin_user):
    path, _, _, _ = path_with_items()
    topic = Topic.objects.create(name="合成分类", slug=f"route-topic-{uuid4()}", editorial_status="published")
    path.topics.add(topic)
    work, edition, _, _ = source(fulltext=False, title="合成主题拓展材料")
    WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
    # The live relation alone must not manufacture a public classification.
    response, _, _ = issue(path, admin_user); assert response.status_code == 200
    old = candidates_for(path.pk).filter(title="主题拓展").first()
    assert all(row.get("work") != str(work.pk) for group in old.stages for row in group["items"])
    activate_catalog_revision(edition, fulltext_ready=False)
    response, _, _ = issue(path, admin_user); assert response.status_code == 200
    candidate = candidates_for(path.pk).filter(title="主题拓展").first()
    extra = next(row for group in candidate.stages for row in group["items"] if row.get("work") == str(work.pk))
    assert extra["edition"] == str(edition.pk) and not extra["is_required"] and extra["dependencies"] == []
    assert "合成分类" in extra["recommendation_reason"]
    topic.editorial_status = "draft"; topic.save(update_fields=["editorial_status", "updated_at"])
    response, _, _ = issue(path, admin_user, "adopt", candidate)
    assert response.status_code == 400
