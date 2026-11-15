from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from catalog.models import Asset, CatalogPublicationRevision, DocumentRevision, KnowledgeNode, Topic
from catalog.services import shared_curation as service
from catalog.services.public_scholars import _evidence as scholar_evidence
from catalog.services.public_topics import _evidence as topic_evidence
from tests.test_v307_shared_curation import data_for, scholar, source_fixture

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind", ["topic", "scholar", "node"])
@pytest.mark.parametrize("source_kind", ["span", "passage"])
@pytest.mark.parametrize("fulltext_ready", [True, False])
def test_registered_curation_publishes_but_requires_reader_login(kind, source_kind, fulltext_ready, admin_user, reader_user, api_client):
    span, passage = source_fixture()
    Asset.objects.filter(pk=span.page.asset_id).update(file="test/curated-source.pdf")
    DocumentRevision.objects.filter(pk=span.document_revision_id).update(source_checksum=span.page.asset.sha256)
    CatalogPublicationRevision.objects.filter(edition_id=span.page.asset.edition_id).update(fulltext_ready=fulltext_ready)
    Asset.objects.filter(pk=span.page.asset_id).update(access_status="registered")
    source = span if source_kind == "span" else passage
    parent = Topic.objects.create(name="主题", slug="registered", editorial_status="published") if kind == "topic" else scholar("学者") if kind == "scholar" else KnowledgeNode.objects.create(canonical_name_zh="理论", node_type="theory_tradition", slug="registered", status="published")
    saved = service.save_curation(kind, parent.pk, data_for(source, source_kind), admin_user)
    assert saved["items"][0]["source"]["public_eligible"] is True
    service.publish_curation(kind, parent.pk, saved["edit_version"], admin_user)
    url = f"/api/catalog/evidence-curation/{kind}/{parent.pk}/"
    assert api_client.get(url).data["items"] == []
    api_client.force_authenticate(reader_user)
    response = api_client.get(url)
    assert response.data["items"][0]["source"]["text"] == "真实原文。"
    assert response["Cache-Control"] == "private, no-store"
    assert CatalogPublicationRevision.objects.get(edition_id=span.page.asset.edition_id).fulltext_ready is fulltext_ready
    if kind == "scholar":
        assert len(scholar_evidence(parent, request=SimpleNamespace(user=reader_user))) == 1
        assert scholar_evidence(parent) == []
    if kind == "topic":
        assert len(topic_evidence(parent, request=SimpleNamespace(user=reader_user))) == 1
        assert topic_evidence(parent) == []
    Asset.objects.filter(pk=span.page.asset_id).update(access_status="restricted")
    assert api_client.get(url).data["items"] == []
    if kind == "topic":
        assert topic_evidence(parent, request=SimpleNamespace(user=reader_user)) == []
    saved = service.save_curation(kind, parent.pk, data_for(source, source_kind, version=service.curation_payload(kind, parent.pk)["edit_version"]), admin_user)
    assert saved["items"][0]["source"]["public_eligible"] is False
    with pytest.raises(ValidationError, match="尚未公开"):
        service.publish_curation(kind, parent.pk, saved["edit_version"], admin_user)
