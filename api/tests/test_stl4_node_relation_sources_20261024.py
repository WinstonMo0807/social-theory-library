"""Deferred exact-source, publication and merge acceptance; not run during implementation."""
from uuid import uuid4
import pytest
from django.db.models.deletion import ProtectedError

from catalog.models import Asset, EditorialRevision, EvidenceSpan, KnowledgeRelation
from catalog.services.knowledge_nodes import merge_nodes, rollback_merge
from catalog.theory_serializers import KnowledgeRelationSerializer
from .test_stl4_node_relations_20261024 import BASE, headers, node
from .test_stl4_person_node_sources_20261024 import material

pytestmark = pytest.mark.django_db


def reference(span):
    return {"span_id": str(span.pk), "document_revision_id": str(span.document_revision_id)}


def edit(client, actor, relation, payload):
    url = f"{BASE}{relation.pk}/"
    current = client.get(url)
    assert current.status_code == 200
    return client.patch(url, payload, format="json", HTTP_IF_MATCH=current.data["edit_version"], **headers(actor))


def test_anchor_selection_uses_existing_draft_and_only_explicit_publication_changes_public_material(api_client, admin_user):
    old, _, _ = material()
    new, _, _ = material()
    first, second = node(), node()
    relation = KnowledgeRelation.objects.create(source_node=first, target_node=second, relation_type="criticizes", status="published",
        evidence_span=old, source_document_revision=old.document_revision)
    api_client.force_authenticate(admin_user)
    saved = edit(api_client, admin_user, relation, {"source_anchor": reference(new), "description": "准确出处草稿"})
    assert saved.status_code == 202
    assert saved.data["source_anchor"] == reference(new) and saved.data["source_material"]["quote"] == new.original_text
    relation.refresh_from_db()
    assert relation.evidence_span_id == old.pk
    public = KnowledgeRelationSerializer(relation).data
    assert public["source_anchor"] is None
    assert public["source_material"]["document_revision_id"] == str(old.document_revision_id)
    result = api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json", **headers(admin_user))
    assert result.status_code == 200
    relation.refresh_from_db()
    assert relation.evidence_span_id == new.pk and relation.source_document_revision_id == new.document_revision_id
    assert relation.versions.order_by("-version_number").first().snapshot["evidence_span_id"] == str(new.pk)
    with pytest.raises(ProtectedError):
        new.delete()
    graph = api_client.get("/api/catalog/theory-system/graph/", {"center": str(first.pk)})
    source = graph.data["edges"][0]["evidence"][0]
    assert source["id"] == str(new.pk) and f"passage={new.pk}" in source["reader_href"]


@pytest.mark.parametrize("damage", ["private", "stale", "wrong_revision"])
def test_public_quotes_fail_closed_and_stale_original_can_still_be_withdrawn(api_client, admin_user, damage):
    span, asset, _ = material()
    first, second = node(), node()
    relation = KnowledgeRelation.objects.create(source_node=first, target_node=second, relation_type="criticizes", status="published",
        evidence_span=span, source_document_revision=span.document_revision)
    if damage == "private":
        Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    elif damage == "stale":
        EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    else:
        other, _, _ = material()
        relation.source_document_revision = other.document_revision
        relation.save(update_fields=["source_document_revision", "updated_at"])
    api_client.force_authenticate(admin_user)
    public = KnowledgeRelationSerializer(KnowledgeRelation.objects.get(pk=relation.pk)).data
    assert public["source_material"] is None and public["source_anchor"] is None
    graph = api_client.get("/api/catalog/theory-system/graph/", {"center": str(first.pk)})
    assert graph.data["edges"][0]["evidence"] == []
    saved = edit(api_client, admin_user, relation, {"description": "失效来源仍可保存核对意见"})
    assert saved.status_code == 202
    assert api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json", **headers(admin_user)).status_code == 400
    withdrawn = edit(api_client, admin_user, relation, {"status": "archived"})
    assert withdrawn.status_code == 202
    assert api_client.post(f"/api{withdrawn.data['editorial_revision']['publish_url']}", {}, format="json", **headers(admin_user)).status_code == 200
    relation.refresh_from_db()
    assert relation.status == "archived" and relation.evidence_span_id == span.pk


def test_private_anchor_may_be_saved_but_not_published_or_forged(api_client, admin_user):
    span, asset, _ = material()
    Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    first, second = node(), node()
    api_client.force_authenticate(admin_user)
    payload = {"source_node": str(first.pk), "target_node": str(second.pk), "relation_type": "criticizes", "direction": "directed", "status": "published", "source_anchor": reference(span)}
    saved = api_client.post(BASE, payload, format="json", **headers(admin_user))
    assert saved.status_code == 201 and saved.data["source_material"]["public_eligible"] is False
    assert api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json", **headers(admin_user)).status_code == 400
    relation = KnowledgeRelation.objects.get(pk=saved.data["id"])
    assert relation.status == "draft"
    assert EditorialRevision.objects.filter(target_id=relation.pk, status="draft").exists()
    forged = edit(api_client, admin_user, relation, {"source_anchor": {**reference(span), "quote": "伪造引文"}})
    assert forged.status_code == 400
    wrong = edit(api_client, admin_user, relation, {"source_anchor": {**reference(span), "document_revision_id": str(uuid4())}})
    assert wrong.status_code == 400


def test_merge_keeps_exact_source_and_conflicting_identity_blocks_merge(admin_user):
    first, second, other = node(), node(), node()
    span, _, _ = material()
    original = KnowledgeRelation.objects.create(source_node=first, target_node=other, relation_type="criticizes", status="published",
        evidence_span=span, source_document_revision=span.document_revision)
    conflict = KnowledgeRelation.objects.create(source_node=second, target_node=other, relation_type="criticizes", status="published")
    with pytest.raises(ValueError, match="原文版本"):
        merge_nodes(first.pk, second.pk, actor=admin_user)
    conflict.delete()
    record = merge_nodes(first.pk, second.pk, actor=admin_user)
    copied = KnowledgeRelation.objects.get(source_node=second, target_node=other)
    assert copied.evidence_span_id == span.pk and copied.source_document_revision_id == span.document_revision_id
    rollback_merge(record.pk, actor=admin_user)
    original.refresh_from_db()
    assert original.status == "published" and original.evidence_span_id == span.pk
    assert not KnowledgeRelation.objects.filter(pk=copied.pk).exists()
