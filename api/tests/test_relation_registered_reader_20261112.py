"""Reader rights propagate to exact original anchors across relation surfaces."""
from uuid import uuid4
import pytest

from catalog.models import Asset, EvidenceSpan, KnowledgeNode, KnowledgeRelation, PersonNodeRelation
from catalog.services import shared_curation as service
from .test_stl4_person_node_sources_20261024 import setup
from .test_stl4_scholar_relation_commands_20261024 import profiles
from .test_stl4_scholar_relation_sources_20261024 import payload

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("signed_in", [False, True])
@pytest.mark.parametrize("damage", ["none", "private", "stale"])
def test_native_relation_material_respects_reader_across_public_surfaces(api_client, admin_user, reader_user, signed_in, damage):
    span, asset, _, scholar, node, _ = setup()
    Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    target = KnowledgeNode.objects.create(canonical_name_zh="理论关系终点", node_type="concept", slug=f"reader-{uuid4()}", status="published")
    KnowledgeRelation.objects.create(source_node=node, target_node=target, relation_type="influences", status="published", evidence_span=span, source_document_revision=span.document_revision)
    PersonNodeRelation.objects.create(person=scholar.person, node=node, relation_label="原文依据", status="published", evidence_span=span, source_document_revision=span.document_revision)
    first, second = profiles()
    saved = service.save_relation(None, payload(first, second, span), admin_user)
    service.publish_relation(saved["id"], saved["edit_version"], admin_user)
    if damage == "private":
        Asset.objects.filter(pk=asset.pk).update(access_status="restricted")
    elif damage == "stale":
        EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    api_client.force_authenticate(reader_user if signed_in else None)
    available = signed_in and damage == "none"
    node_response = api_client.get(f"/api/catalog/theory-system/nodes/{node.slug}/")
    assert node_response.status_code == 200
    material = node_response.data["direct_relations"][0]["source_material"]
    assert bool(material) is available
    if available:
        assert material["quote"] == span.original_text
        assert f"passage={span.pk}" in material["reader_href"]
    for center in ({"center": str(node.pk)}, {"center_kind": "scholar", "center": str(first.pk)}):
        graph = api_client.get("/api/catalog/theory-system/graph/", center)
        assert graph.status_code == 200
        assert graph.data["edges"]
        assert all(bool(edge["evidence"]) is available for edge in graph.data["edges"])
    relations = api_client.get("/api/catalog/scholar-relations/", {"scholar": str(first.pk)})
    assert relations.status_code == 200
    assert bool(relations.data["results"][0]["source_material"]) is available
    profile = api_client.get(f"/api/catalog/scholars/{first.slug}/", {"section": "relations"})
    assert profile.status_code == 200
    assert bool(profile.data["relations"]["results"][0]["source_material"]) is available
