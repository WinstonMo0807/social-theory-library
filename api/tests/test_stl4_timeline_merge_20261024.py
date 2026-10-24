"""Deferred M23 merge, receipt, original-link and reversal acceptance definitions."""
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import PermissionDenied

from catalog.models import KnowledgeNode, Person, ScholarProfile, TheoryTimelineEvent, TimelineEventRelation, TimelineMergeRecord
from catalog.services import content_placements as placements
from catalog.services.editorial_blocks import resolve_target
from catalog.services.person_authority import AuthorityConflict
from catalog.services.timeline_merge import merge_events, merge_preview, rollback_merge, rollback_preview

pytestmark = pytest.mark.django_db


@pytest.fixture
def pair(settings):
    settings.THEORY_SYSTEM_ENABLED = True
    profile = ScholarProfile.objects.create(person=Person.objects.create(preferred_name="合成事件主体", authority_status="verified"), slug=f"merge-{uuid4()}", editorial_status="published")
    return tuple(TheoryTimelineEvent.objects.create(title=label, scholar=profile, event_type="birth", start_year=1900, date_precision="year", source=f"{label}的合成出处", description="已人工核对的合成说明", review_status="approved", editorial_details={"confirmed": True}) for label in ("来源事件", "保留事件"))


def apply(pair, actor, request_id=None):
    source, target = pair
    preview = merge_preview(source, target)
    assert preview["can_merge"], preview["blockers"]
    kwargs = dict(actor=actor, fingerprint=preview["fingerprint"], request_id=request_id or uuid4(), confirmed=True)
    return merge_events(source.pk, target.pk, **kwargs), kwargs


def test_merge_keeps_original_rows_public_links_and_reversible_relations(pair, superadmin_user, api_client):
    source, target = pair
    node = KnowledgeNode.objects.create(canonical_name_zh="合成关联概念", slug=f"merge-node-{uuid4()}", node_type="concept", status="published")
    relation = TimelineEventRelation.objects.create(event=source, node=node, relation_type="context", description="保留原关系说明")
    record, kwargs = apply(pair, superadmin_user)
    with pytest.raises(ModelValidationError):
        TimelineMergeRecord.objects.filter(pk=record.pk).update(before={})
    with pytest.raises(ModelValidationError):
        TimelineMergeRecord.objects.filter(pk=record.pk).delete()
    source.refresh_from_db(); target.refresh_from_db()
    assert source.merged_into_id == target.pk and source.review_status == "rejected"
    assert TimelineEventRelation.objects.filter(pk=relation.pk, event=source).exists()
    assert target.normalized_relations.filter(node=node, description="保留原关系说明").exists()
    assert target.editorial_details["sources"][0]["citation"] == source.source
    assert api_client.get(f"/api/catalog/theory-system/timeline/{source.pk}/").data["id"] == str(target.pk)
    original, resolved = resolve_target({"type": "timeline", "id": str(source.pk)}, public=True)
    assert original["id"] == str(source.pk) and str(target.pk) in resolved["href"]
    from catalog.services.project_sources import reference_states
    assert reference_states([original]) == ["public"]
    assert merge_events(source.pk, target.pk, **kwargs).pk == record.pk
    state = rollback_preview(record)
    assert state["can_rollback"]
    rollback_merge(record.pk, actor=superadmin_user, fingerprint=state["fingerprint"], confirmed=True)
    source.refresh_from_db(); target.refresh_from_db()
    assert source.merged_into_id is None and source.review_status == "approved"
    assert not target.normalized_relations.filter(node=node).exists()
    assert TimelineEventRelation.objects.filter(pk=relation.pk).exists()


def test_merge_and_restore_original_page_placements(pair, superadmin_user):
    source, target = pair
    node = KnowledgeNode.objects.create(canonical_name_zh="合成编排概念", slug=f"placement-node-{uuid4()}", node_type="concept", status="published")
    placements.command("timeline_event", source.pk, {"action": "save", "request_id": str(uuid4()), "expected_revision": "0", "items": [{"id": str(uuid4()), "area": "main", "group": "原证据", "target": {"type": "node", "id": str(node.pk)}, "reason": "原编排说明"}]}, superadmin_user)
    latest = placements.revisions("timeline_event", source.pk).first()
    placements.command("timeline_event", source.pk, {"action": "publish", "request_id": str(uuid4()), "expected_revision": placements.version(latest)}, superadmin_user)
    record, _ = apply(pair, superadmin_user)
    merged = placements.revisions("timeline_event", target.pk).first()
    assert merged.materialized_preview["items"][0]["reason"] == "原编排说明"
    rollback_merge(record.pk, actor=superadmin_user, fingerprint=rollback_preview(record)["fingerprint"], confirmed=True)
    assert placements.revisions("timeline_event", source.pk).first().materialized_preview["items"][0]["reason"] == "原编排说明"
    assert placements.revisions("timeline_event", target.pk).first().materialized_preview["items"] == []


def test_permissions_stale_preview_and_post_merge_changes_never_overwritten(pair, superadmin_user, admin_user):
    source, target = pair
    preview = merge_preview(source, target)
    with pytest.raises(PermissionDenied):
        merge_events(source.pk, target.pk, actor=admin_user, fingerprint=preview["fingerprint"], request_id=uuid4(), confirmed=True)
    target.description = "另一管理员的后续说明"; target.save(update_fields=["description", "updated_at"])
    with pytest.raises(AuthorityConflict):
        merge_events(source.pk, target.pk, actor=superadmin_user, fingerprint=preview["fingerprint"], request_id=uuid4(), confirmed=True)
    record, _ = apply(pair, superadmin_user)
    target.refresh_from_db(); target.description = "归并后的新说明"; target.save(update_fields=["description", "updated_at"])
    assert not rollback_preview(record)["can_rollback"]
    with pytest.raises(AuthorityConflict):
        rollback_merge(record.pk, actor=superadmin_user, fingerprint=record.rollback_fingerprint, confirmed=True)
    target.refresh_from_db(); assert target.description == "归并后的新说明"


def test_original_receipt_stop_blocks_late_merge(pair, superadmin_user, api_client):
    source, target = pair
    request_id = uuid4()
    preview = merge_preview(source, target)
    api_client.force_authenticate(superadmin_user)
    receipt = api_client.post(f"/api/catalog/admin/theory-timeline/merges/commands/{request_id}/", {"action": "cancel_pending"}, format="json", HTTP_X_EDITOR_OWNER=str(superadmin_user.pk))
    assert receipt.status_code == 200 and receipt.data["state"] == "cancelled"
    with pytest.raises(AuthorityConflict):
        merge_events(source.pk, target.pk, actor=superadmin_user, fingerprint=preview["fingerprint"], request_id=request_id, confirmed=True)
    assert not TimelineMergeRecord.objects.filter(pk=request_id).exists()


def test_conflicting_event_types_and_same_relation_roles_are_not_guessed(pair):
    source, target = pair
    target.event_type = "death"; target.save(update_fields=["event_type", "updated_at"])
    assert not merge_preview(source, target)["can_merge"]
    target.event_type = "birth"; target.save(update_fields=["event_type", "updated_at"])
    TimelineEventRelation.objects.create(event=source, scholar=source.scholar, relation_type="subject", participant_role="subject")
    TimelineEventRelation.objects.create(event=target, scholar=source.scholar, relation_type="subject", participant_role="author")
    assert not merge_preview(source, target)["can_merge"]


def test_second_publication_failure_rolls_back_both_original_events(pair, superadmin_user, monkeypatch):
    from catalog.services import timeline_merge
    source, target = pair
    original = timeline_merge.publish_editorial_revision
    count = 0
    def interrupted(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("synthetic interruption")
        return original(*args, **kwargs)
    monkeypatch.setattr(timeline_merge, "publish_editorial_revision", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        apply(pair, superadmin_user)
    source.refresh_from_db(); target.refresh_from_db()
    assert source.merged_into_id is None and source.review_status == "approved"
    assert target.editorial_details == {"confirmed": True}
    assert not TimelineMergeRecord.objects.exists()
