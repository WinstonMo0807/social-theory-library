"""Deferred exact-version relation sources; no files or providers are contacted."""
from hashlib import sha256
from uuid import uuid4
from django.db.models.deletion import ProtectedError
import pytest

from catalog.models import Asset, Edition, EvidenceSpan, KnowledgeNode, Page, Person, PersonNodeRelation, ScholarProfile, Work
from catalog.relation_source_anchor import RelationAnchorInput
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def material():
    work = Work.objects.create(title="仅用于验收的原文材料")
    edition = Edition.objects.create(work=work, state="published", version_label="原版", public_slug=f"anchor-{uuid4()}")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
        access_status="public", file="test/relation-anchor.pdf", sha256="d" * 64, page_count=1)
    page = Page.objects.create(asset=asset, index=1, text="作为关系依据的准确原文。", width=600, height=900)
    publication = activate_catalog_revision(edition, reader_asset=asset)
    span = EvidenceSpan.objects.create(document_revision=publication.document_revision, page=page, page_number=1,
        start_offset=0, end_offset=len(page.text), original_text=page.text, content_hash=sha256(page.text.encode()).hexdigest())
    return span, asset, page


def setup():
    span, asset, page = material()
    person = Person.objects.create(preferred_name="原文验收人物", authority_status="verified")
    scholar = ScholarProfile.objects.create(person=person, slug=f"source-{uuid4()}", editorial_status="published")
    node = KnowledgeNode.objects.create(canonical_name_zh="原文验收概念", node_type="concept", slug=f"source-{uuid4()}", status="published")
    body = {"action": "save", "target_id": str(node.pk), "relation_label": "验收说明", "source": "", "featured": False, "sort_order": 0,
        "relation_type": "interprets", "direction": "directed", "node_is_source": False,
        "source_anchor": {"span_id": str(span.pk), "document_revision_id": str(span.document_revision_id)}}
    return span, asset, page, scholar, node, body


def send(client, actor, url, body):
    return client.post(url, body, format="json", HTTP_X_EDITOR_OWNER=str(actor.pk), HTTP_IDEMPOTENCY_KEY=str(uuid4()))


def test_original_quote_is_pinned_and_not_accepted_as_editable_input(api_client, admin_user):
    span, _, _, scholar, node, body = setup()
    url = f"/api/catalog/admin/scholars/{scholar.pk}/links/node/"
    api_client.force_authenticate(admin_user)
    saved = send(api_client, admin_user, url, body)
    assert saved.status_code == 200 and saved.data["source_material"]["quote"] == span.original_text
    confirmed = send(api_client, admin_user, url, {**body, "action": "confirm", "id": saved.data["id"], "edit_version": saved.data["edit_version"]})
    assert confirmed.status_code == 200 and confirmed.data["confirmed"]
    row = PersonNodeRelation.objects.get(pk=saved.data["id"])
    assert row.evidence_span_id == span.pk and row.source_document_revision_id == span.document_revision_id
    with pytest.raises(ProtectedError):
        span.delete()
    invalid = RelationAnchorInput(data={**body["source_anchor"], "quote": "不允许改写原文"})
    assert not invalid.is_valid()
    api_client.force_authenticate(None)
    public = api_client.get("/api/catalog/theory-system/graph/", {"center": str(node.pk)})
    assert public.status_code == 200
    source = public.data["edges"][0]["evidence"][0]
    assert source["quote"] == span.original_text and source["document_revision_id"] == str(span.document_revision_id)
    assert f"passage={span.pk}" in source["reader_href"] and f"revision={span.document_revision_id}" in source["reader_href"]


@pytest.mark.parametrize("damage", ["text", "offset", "stale", "checksum", "registered", "revision"])
def test_changed_or_private_material_never_escapes_through_public_relation(api_client, admin_user, damage):
    span, asset, page, scholar, node, body = setup()
    row = PersonNodeRelation.objects.create(person=scholar.person, node=node, relation_label="关系仍可见",
        evidence_span=span, source_document_revision=span.document_revision, status="published")
    if damage == "text":
        Page.objects.filter(pk=page.pk).update(text="这是已改变的页面文字")
    elif damage == "offset":
        EvidenceSpan.objects.filter(pk=span.pk).update(start_offset=1)
    elif damage == "stale":
        EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    elif damage == "checksum":
        Asset.objects.filter(pk=asset.pk).update(sha256="e" * 64)
    elif damage == "registered":
        Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    else:
        other, _, _ = material()
        PersonNodeRelation.objects.filter(pk=row.pk).update(source_document_revision=other.document_revision)
    public = api_client.get("/api/catalog/theory-system/graph/", {"center": str(node.pk)})
    assert public.status_code == 200
    edge = public.data["edges"][0]
    assert edge["evidence"] == [] and edge["source_status"] == "unverified"
    assert span.original_text not in str(edge)
    row.refresh_from_db()
    assert row.evidence_span_id == span.pk


def test_wrong_document_revision_does_not_create_or_rebind(api_client, admin_user):
    span, _, _, scholar, node, body = setup()
    other, _, _ = material()
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/scholars/{scholar.pk}/links/node/"
    bad = {**body, "source_anchor": {"span_id": str(span.pk), "document_revision_id": str(other.document_revision_id)}}
    assert send(api_client, admin_user, url, bad).status_code == 400
    assert not PersonNodeRelation.objects.filter(person=scholar.person, node=node).exists()
