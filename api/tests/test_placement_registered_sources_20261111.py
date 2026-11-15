from uuid import uuid4
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from catalog.models import Asset, EvidenceSpan, KnowledgeNode, Person
from catalog.services import content_placements as service
from tests.test_content_placements import sources, item, run, topic

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind", ["span", "landing", "edition"])
def test_registered_placements_use_actual_viewer_and_revoke_sources(kind, sources, admin_user, reader_user, api_client):
    _, edition, asset, span = sources
    Asset.objects.filter(pk=asset.pk).update(access_status="registered", file="tests/registered-source.pdf")
    parent = topic()
    row = item(edition)
    if kind == "span":
        row["target"] = {"type": "span", "id": str(span.pk)}
    elif kind == "landing":
        row["reading_target"] = {"asset_id": str(asset.pk), "document_revision_id": str(span.document_revision_id), "pdf_page": 3}
    saved = run(parent, admin_user, "save", items=[row])
    assert saved["can_publish"] is True
    run(parent, admin_user, "publish")
    url = f"/api/catalog/content-placements/topic/{parent.pk}/"
    anonymous = api_client.get(url)
    assert anonymous.status_code == 200
    if kind == "edition":
        assert anonymous.data["items"][0]["source"]["reader_url"] == ""
    else:
        assert anonymous.data["items"] == []
    api_client.force_authenticate(reader_user)
    response = api_client.get(url)
    source = response.data["items"][0]["source"]
    assert source["reader_url"]
    assert source["document_revision_id"] == str(span.document_revision_id)
    assert response["Cache-Control"] == "private, no-store"
    assert "Cookie" in response["Vary"] and "Authorization" in response["Vary"]
    if kind == "span":
        assert source["text"] == "真实原文。"
    for restricted in ["restricted", "private"]:
        Asset.objects.filter(pk=asset.pk).update(access_status=restricted)
        hidden = api_client.get(url).data["items"]
        assert hidden[0]["source"]["reader_url"] == "" if kind == "edition" else hidden == []
    if kind != "edition":
        run(parent, admin_user, "update", item_id=row["id"], patch={"reason": "核对来源"})
        with pytest.raises(ValidationError):
            run(parent, admin_user, "publish")


def test_registered_concept_usage_keeps_exact_revision_and_draft_isolation(sources, admin_user, reader_user, api_client):
    _, _, asset, span = sources
    Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    node = KnowledgeNode.objects.create(canonical_name_zh="场域测试", node_type="concept", slug="registered-field", status="published")
    author = Person.objects.create(preferred_name="原文作者", authority_status="verified")
    row = {"id": str(uuid4()), "target": {"type": "span", "id": str(span.pk)},
           "concept_usage": {"term": "场域", "language": "中文", "usage_type": "definition",
                             "interpretation": "位置之间的关系。", "source_person_id": str(author.pk),
                             "attribution_note": "作者的直接论述", "review_status": "confirmed"}}
    def command(action, **data):
        current = service.read("node", node.pk, actor=admin_user)
        return service.command("node", node.pk, {"action": action, "request_id": str(uuid4()),
            "expected_revision": current["expected_revision"], **data}, admin_user)
    saved = command("save", items=[row])
    url = f"/api/catalog/content-placements/node/{node.pk}/"
    api_client.force_authenticate(reader_user)
    assert api_client.get(url + f"?revision={saved['revision_id']}").data["items"] == []
    command("publish", confirmed_only=True)
    assert len(api_client.get(url).data["public_detail"]["usages"]) == 1
    api_client.force_authenticate(None)
    assert api_client.get(url).data["public_detail"]["usages"] == []
    api_client.force_authenticate(reader_user)
    EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    assert api_client.get(url).data["public_detail"]["usages"] == []


def test_registered_path_material_preserves_login_boundary_and_exact_pages(admin_user, reader_user, api_client):
    from tests.test_reading_paths_20261021 import path_with_items
    from catalog.services.public_reading_paths import capture_reading_path_publication
    path, _, items, edition = path_with_items()
    Asset.objects.filter(pk=edition.active_catalog_revision.reader_asset_id).update(access_status="registered")
    capture_reading_path_publication(path, actor=admin_user)
    url = f"/api/catalog/theory-system/reading-paths/{path.slug}/"
    anonymous = api_client.get(url).data["items"][0]
    assert anonymous["reader_url"] is None
    api_client.force_authenticate(reader_user)
    response = api_client.get(url)
    assert response.data["items"][0]["source_status"] == "available"
    assert f"page=1&revision={items[0].document_revision_id}" in response.data["items"][0]["reader_url"]
    assert response["Cache-Control"] == "no-store"
    Asset.objects.filter(pk=edition.active_catalog_revision.reader_asset_id).update(access_status="restricted")
    assert api_client.get(url).data["items"][0]["reader_url"] is None


def test_registered_subdiscipline_placement_uses_viewer_context(admin_user, reader_user):
    from hashlib import sha256
    from tests.test_subdiscipline_publication_20261020 import branch, source
    from catalog.serializers import SubdisciplineSerializer
    parent = branch()
    _, _, asset, page, revision, relation = source(parent)
    relation.evidence_text = ""
    relation.save(update_fields=["evidence_text"])
    Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    span = EvidenceSpan.objects.create(document_revision=revision.document_revision, page=page, page_number=1,
        original_text=page.text, start_offset=0, end_offset=len(page.text), content_hash=sha256(page.text.encode()).hexdigest())
    saved = service.command("subdiscipline", parent.pk, {"action": "save", "request_id": str(uuid4()),
        "expected_revision": "0", "items": [{"target": {"type": "span", "id": str(span.pk)}}]}, admin_user)
    service.command("subdiscipline", parent.pk, {"action": "publish", "request_id": str(uuid4()),
        "expected_revision": saved["expected_revision"]}, admin_user)
    assert SubdisciplineSerializer(parent).data["sources"] == []
    from rest_framework.test import APIRequestFactory
    request = APIRequestFactory().get("/api/catalog/subdisciplines/")
    request.user = reader_user
    data = SubdisciplineSerializer(parent, context={"request": request}).data
    assert data["sources"][0]["source_kind"] == "placement_span"
    assert data["sources"][0]["quote"] == page.text


@pytest.mark.parametrize("break_source", [None, "inactive", "checksum", "unready"])
def test_reading_pdf_does_not_depend_on_search_index(break_source, admin_user, reader_user, api_client):
    from tests.test_reading_paths_20261021 import path_with_items
    from catalog.models import CatalogPublicationRevision, DocumentRevision
    from catalog.services.public_reading_paths import capture_reading_path_publication
    path, _, items, edition = path_with_items()
    capture_reading_path_publication(path, actor=admin_user)
    active = edition.active_catalog_revision
    CatalogPublicationRevision.objects.filter(pk=active.pk).update(fulltext_ready=False)
    if break_source == "inactive":
        DocumentRevision.objects.filter(pk=active.document_revision_id).update(is_active=False)
    elif break_source == "checksum":
        DocumentRevision.objects.filter(pk=active.document_revision_id).update(source_checksum="changed")
    elif break_source == "unready":
        Asset.objects.filter(pk=active.reader_asset_id).update(status="failed")
    api_client.force_authenticate(reader_user)
    result = api_client.get(f"/api/catalog/theory-system/reading-paths/{path.slug}/").data["items"][0]
    assert bool(result["reader_url"]) is (break_source is None)
    if break_source is None:
        assert f"revision={items[0].document_revision_id}" in result["reader_url"]
    assert CatalogPublicationRevision.objects.get(pk=active.pk).fulltext_ready is False
