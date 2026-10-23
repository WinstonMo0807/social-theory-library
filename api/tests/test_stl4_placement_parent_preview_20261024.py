"""Deferred acceptance: complete page previews never write or widen source visibility."""
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from catalog.models import Discipline, EditorialRevision, KnowledgeNode, TheoryTimelineEvent, TimelineEventRelation
from catalog.placement_parent_preview import PlacementParentPreviewView
from catalog.services.relation_editorial import timeline_preview_instance
from catalog.theory_serializers import NormalizedTimelineDetailSerializer
from ingestion.models import AuditEvent


@pytest.mark.django_db
def test_discipline_preview_is_owner_bound_read_only_and_version_checked(admin_user):
    discipline = Discipline.objects.create(name="预览学科", code="preview-discipline", slug="preview-discipline")
    node = KnowledgeNode.objects.create(canonical_name_zh="正式条目", slug="preview-node", node_type="theory_tradition", status="published", primary_discipline=discipline)
    factory = APIRequestFactory()
    view = PlacementParentPreviewView.as_view()
    initial = (EditorialRevision.objects.count(), AuditEvent.objects.count())
    def load(owner, version):
        request = factory.get("/api/catalog/admin/content-placements/discipline/parent-preview/", {"expected_revision":version}, HTTP_X_EDITOR_OWNER=owner)
        force_authenticate(request, user=admin_user)
        return view(request, page_type="discipline", page_id=discipline.pk)
    assert load("another-account", "0").status_code == 403
    assert load(str(admin_user.pk), "stale").status_code == 409
    response = load(str(admin_user.pk), "0")
    assert response.status_code == 200
    page = response.data["page"]["perspective"]["data"]["page_projection"]
    assert str(node.pk) in {str(row["id"]) for row in page["nodes"]}
    assert (EditorialRevision.objects.count(), AuditEvent.objects.count()) == initial


@pytest.mark.django_db
def test_timeline_preview_projects_draft_relations_through_public_filters():
    old = KnowledgeNode.objects.create(canonical_name_zh="原关联", slug="preview-old", node_type="concept", status="published")
    current = KnowledgeNode.objects.create(canonical_name_zh="草稿新关联", slug="preview-new", node_type="concept", status="published")
    hidden = KnowledgeNode.objects.create(canonical_name_zh="未公开关联", slug="preview-hidden", node_type="concept", status="draft")
    event = TheoryTimelineEvent.objects.create(title="原事件", event_type="concept_proposed")
    TimelineEventRelation.objects.create(event=event, node=old)
    revision = SimpleNamespace(materialized_preview={"title":"已保存草稿", "timeline_relations":[{"node":str(current.pk)}, {"node":str(hidden.pk)}]})
    draft = timeline_preview_instance(event, revision)
    data = NormalizedTimelineDetailSerializer(draft, context={}).data
    assert data["title"] == "已保存草稿"
    assert {str(row["id"]) for row in data["relations"]} == {str(current.pk)}
    event.refresh_from_db()
    assert event.title == "原事件" and list(event.normalized_relations.values_list("node_id", flat=True)) == [old.pk]
