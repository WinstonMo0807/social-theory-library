"""Run in the final isolated acceptance phase; no production records required."""
from uuid import uuid4

import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import (Asset, CatalogPublicationRevision, DocumentRevision, Edition,
                            EvidenceSpan, KnowledgeNode, Page, Person, SiteSetting, Topic, Work)
from catalog.services import content_placements as service
from catalog.services.editorial_issues import EditConflict
from catalog.curation_queue_views import draft_inventory
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def sources():
    work = Work.objects.create(title="馆藏正式题名", document_type="book")
    edition = Edition.objects.create(work=work, version_label="第二版", state="published", public_slug="placement-book")
    asset = Asset.objects.create(edition=edition, kind="normalized", sha256="a" * 64,
                                 status="ready", validation_status="valid", access_status="public", page_count=8)
    page = Page.objects.create(asset=asset, index=3, text="前文。真实原文。后文。", text_source="native")
    document = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum="a" * 64, text_checksum="b" * 64)
    span = EvidenceSpan.objects.create(document_revision=document, page=page, page_number=3,
                                      original_text="真实原文。", content_hash="c" * 64, start_offset=3, end_offset=8)
    published = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active",
        metadata_ready=True, fulltext_ready=True, reader_asset=asset, document_revision=document,
        snapshot={"work": {"title": "馆藏正式题名"}, "edition": {"version_label": "第二版"}}, content_fingerprint=str(uuid4()))
    edition.active_catalog_revision = published
    edition.save(update_fields=["active_catalog_revision"])
    return work, edition, asset, span


def topic(name="策展主题"):
    return Topic.objects.create(name=name, slug=str(uuid4()), editorial_status="published")


def run(parent, actor, action, **data):
    current = service.read("topic", parent.pk, actor=actor)
    return service.command("topic", parent.pk, {"action": action, "request_id": str(uuid4()),
                           "expected_revision": current["expected_revision"], **data}, actor)


def item(edition, group="第一组", reason="本页推荐语"):
    return {"id": str(uuid4()), "target": {"type": "edition", "id": str(edition.pk)},
            "area": "main", "group": group, "reason": reason}


def test_local_move_remove_undo_retains_catalog_and_public_snapshot(admin_user, sources):
    work, edition, _, _ = sources
    parent = topic()
    first, second = item(edition), item(edition, "第二组", "同书另一组说明")
    saved = run(parent, admin_user, "save", items=[first, second])
    assert service.read("topic", parent.pk, public=True)["items"] == []
    run(parent, admin_user, "publish")
    moved = run(parent, admin_user, "move", item_id=first["id"], group="第二组", position=1)
    assert [(row["id"], row["position"]) for row in moved["items"]] == [(second["id"], 0), (first["id"], 1)]
    run(parent, admin_user, "remove", item_id=second["id"])
    restored = run(parent, admin_user, "undo")
    assert [(row["id"], row["position"]) for row in restored["items"]] == [(second["id"], 0), (first["id"], 1)]
    run(parent, admin_user, "update", item_id=first["id"], patch={"reason": "只改当前页"})
    assert service.read("topic", parent.pk, public=True)["items"][0]["reason"] == "本页推荐语"
    work.refresh_from_db()
    assert work.title == "馆藏正式题名" and Edition.objects.filter(pk=edition.pk).exists()
    preview = service.read("topic", parent.pk, actor=admin_user, revision_id=saved["revision_id"])
    assert preview["items"][0]["group"] == "第一组"


def test_idempotent_receipt_version_conflict_and_reused_request(admin_user, sources):
    parent = topic()
    data = {"action": "save", "request_id": str(uuid4()), "expected_revision": "0", "items": [item(sources[1])]}
    first = service.command("topic", parent.pk, data, admin_user)
    replay = service.command("topic", parent.pk, data, admin_user)
    assert replay["replayed"] is True and replay["applied_revision_id"] == first["applied_revision_id"]
    assert service.revisions("topic", parent.pk).count() == 1
    assert AuditEvent.objects.filter(action="content_placement.command").count() == 1
    with pytest.raises(EditConflict):
        service.command("topic", parent.pk, {**data, "items": []}, admin_user)
    with pytest.raises(EditConflict):
        service.command("topic", parent.pk, {**data, "request_id": str(uuid4())}, admin_user)


def test_exact_document_public_eligibility_and_stale_draft_cleanup(admin_user, sources):
    _, edition, asset, span = sources
    parent = topic()
    source_item = {"id": str(uuid4()), "target": {"type": "span", "id": str(span.pk)}, "group": "原文"}
    run(parent, admin_user, "save", items=[source_item, item(edition)])
    run(parent, admin_user, "publish")
    assert service.read("topic", parent.pk, public=True)["items"][0]["source"]["page_start"] == 3
    Asset.objects.filter(pk=asset.pk).update(access_status="restricted")
    public = service.read("topic", parent.pk, public=True)
    assert len(public["items"]) == 1 and public["items"][0]["target"]["type"] == "edition"
    run(parent, admin_user, "update", item_id=source_item["id"], patch={"local_text": "待重新核对来源"})
    with pytest.raises(ValidationError):
        run(parent, admin_user, "publish")
    EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    cleaned = run(parent, admin_user, "remove", item_id=source_item["id"])
    assert len(cleaned["items"]) == 1
    assert EvidenceSpan.objects.filter(pk=span.pk).exists()
    run(parent, admin_user, "publish")


def test_permission_no_draft_leak_and_withdraw_restore(api_client, admin_user, reader_user, sources):
    parent = topic()
    url = f"/api/catalog/admin/content-placements/topic/{parent.pk}/"
    public_url = f"/api/catalog/content-placements/topic/{parent.pk}/"
    with pytest.raises(PermissionDenied):
        service.command("topic", parent.pk, {"action": "save"}, reader_user)
    saved = run(parent, admin_user, "save", items=[item(sources[1])])
    assert api_client.get(public_url + f"?revision={saved['revision_id']}").data["items"] == []
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.get(url).status_code == 200
    run(parent, admin_user, "publish")
    run(parent, admin_user, "withdraw")
    assert service.read("topic", parent.pk, public=True)["withdrawn"] is True
    run(parent, admin_user, "restore", revision_id=saved["revision_id"])
    assert service.read("topic", parent.pk, public=True)["items"] == []
    run(parent, admin_user, "publish")
    assert len(service.read("topic", parent.pk, public=True)["items"]) == 1


def test_bad_source_writes_are_atomic_and_queue_is_a_real_draft(admin_user, sources):
    parent = topic()
    wrong = Work.objects.create(title="另一作品", document_type="book")
    invalid = {"target": {"type": "work", "id": str(wrong.pk), "edition_id": str(sources[1].pk)}}
    with pytest.raises(ValidationError):
        run(parent, admin_user, "save", items=[item(sources[1]), invalid])
    assert service.revisions("topic", parent.pk).count() == 0
    saved = run(parent, admin_user, "save", items=[item(sources[1])])
    assert any(row["q_type"] == "content_placement" and str(row["q_object_id"]) == str(parent.pk)
               for row in draft_inventory(admin_user))
    payload = [{key: value for key, value in row.items() if key != "source"} for row in saved["items"]]
    payload[0]["target"] = {"type": "work", "id": str(sources[0].pk), "edition_id": str(sources[1].pk)}
    with pytest.raises(ValidationError, match="改绑"):
        run(parent, admin_user, "save", items=payload)
    assert service.revisions("topic", parent.pk).count() == 1
    site, _ = SiteSetting.objects.update_or_create(key="site_config", defaults={"value": {}, "public": True})
    assert service.read("site", site.pk, actor=admin_user)["configured"] is False


def test_public_labels_never_fall_back_to_unpublished_catalog_edits(admin_user, sources):
    work, edition, _, _ = sources
    parent = topic()
    run(parent, admin_user, "save", items=[item(edition)])
    run(parent, admin_user, "publish")
    Work.objects.filter(pk=work.pk).update(title="未发布书名")
    Edition.objects.filter(pk=edition.pk).update(version_label="未发布版次")
    source = service.read("topic", parent.pk, public=True)["items"][0]["source"]
    assert source["title"] == "馆藏正式题名" and source["edition_label"] == "第二版"
    assert "edit_url" not in source


def test_reading_landing_is_bound_to_exact_file_revision_and_page(admin_user, sources):
    from copy import deepcopy

    from catalog.models import DocumentQualityAssessment, ProjectionState
    from catalog.services.knowledge_publication import create_catalog_publication_event, process_knowledge_event

    _, edition, asset, span = sources
    parent = topic()
    selected = item(edition)
    selected["reading_target"] = {"asset_id": str(asset.pk), "document_revision_id": str(span.document_revision_id), "pdf_page": 3}
    saved = run(parent, admin_user, "save", items=[selected])
    assert saved["items"][0]["source"]["reader_url"].endswith("?page=3")
    run(parent, admin_user, "publish")
    previous_publication = edition.active_catalog_revision
    previous_snapshot = deepcopy(previous_publication.snapshot)
    DocumentRevision.objects.filter(pk=span.document_revision_id).update(is_active=False)
    newer = DocumentRevision.objects.create(asset=asset, revision=2, source_checksum=asset.sha256, text_checksum="e" * 64)
    DocumentQualityAssessment.objects.create(
        document_revision=newer, assessor_version="placement-fixture", reader_quality=0.9,
        fulltext_quality=0.9, semantic_quality=0.9, claim_quality=0.9, structure_quality=0.9, ocr_quality=0.9,
    )
    event = create_catalog_publication_event(
        edition, event_type="catalog_updated", changed_fields=["document_revision", "fulltext_ready"],
        content_asset_id=asset.pk, actor=admin_user, idempotency_key=f"placement-document:{newer.pk}",
        provenance={"source": "ocr_completion"},
    )
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == previous_publication.pk
    assert event.catalog_revision.status == "preparing"
    # Supply isolated projection completion evidence; the real publication
    # service owns superseding the old revision and activating its replacement.
    ProjectionState.objects.filter(object_type=event.object_type, object_id=event.object_id).update(
        status="current", projected_revision=event.domain_event.canonical_revision,
    )
    assert process_knowledge_event(event.pk).status == "completed"
    edition.refresh_from_db()
    replacement = edition.active_catalog_revision
    previous_publication.refresh_from_db()
    assert replacement.pk != previous_publication.pk
    assert replacement.document_revision_id == newer.pk and replacement.fulltext_ready is True
    assert CatalogPublicationRevision.objects.filter(edition=edition, status="active").count() == 1
    assert previous_publication.status == "superseded"
    assert previous_publication.document_revision_id == span.document_revision_id
    assert previous_publication.snapshot == previous_snapshot
    assert service.read("topic", parent.pk, public=True)["items"] == []
    current = service.read("topic", parent.pk, actor=admin_user)
    assert current["items"][0]["reading_target"]["document_revision_id"] == str(span.document_revision_id)
    assert current["source_problems"][0]["code"] == "reading_target_not_public"


def test_site_draft_cannot_leak_through_generic_revision_endpoints(api_client, admin_user, sources):
    from django.contrib.auth import get_user_model
    editor = get_user_model().objects.create_user(username="placement-editor", email="placement-editor@example.org", role="editor")
    site, _ = SiteSetting.objects.update_or_create(key="site_config", defaults={"value": {}, "public": True})
    api_client.force_authenticate(admin_user)
    saved = api_client.post(f"/api/catalog/admin/content-placements/site/{site.pk}/", {
        "action": "save", "request_id": str(uuid4()), "expected_revision": "0", "items": [item(sources[1])],
    }, format="json")
    assert saved.status_code == 200
    api_client.force_authenticate(editor)
    assert api_client.get(f"/api/catalog/admin/content-placements/site/{site.pk}/").status_code == 403
    assert api_client.get(f"/api/catalog/admin/editorial-revisions/{saved.data['revision_id']}/").status_code == 404
    rows = api_client.get("/api/catalog/admin/editorial-revisions/?target_type=content_placement").data
    assert rows["count"] == 0


def test_concept_usage_keeps_original_interpretation_and_attribution_separate(admin_user, sources):
    node = KnowledgeNode.objects.create(canonical_name_zh="概念", node_type="concept", slug="placement-concept", status="published")
    person = Person.objects.create(preferred_name="原文作者", authority_status="verified")
    span = sources[3]
    selected = {"target": {"type": "span", "id": str(span.pk)}, "concept_usage": {
        "term": "原文术语", "language": "zh", "usage_type": "definition", "interpretation": "编辑对概念用法的解释",
        "source_person_id": str(person.pk), "attribution_note": "核对本文作者自述及原文归属", "review_status": "candidate"}}
    def change(action, **data):
        return service.command("node", node.pk, {"action": action, "request_id": str(uuid4()),
            "expected_revision": service.read("node", node.pk, actor=admin_user)["expected_revision"], **data}, admin_user)
    saved = change("save", items=[selected])
    assert saved["source_problems"][0]["code"] == "concept_usage_unconfirmed"
    with pytest.raises(ValidationError):
        change("publish")
    usage = {**selected["concept_usage"], "review_status": "confirmed"}
    change("update", item_id=saved["items"][0]["id"], patch={"concept_usage": usage})
    change("publish")
    published = service.read("node", node.pk, public=True)["items"][0]
    assert published["source"]["text"] == "真实原文。"
    assert published["concept_usage"]["interpretation"] == "编辑对概念用法的解释"
    assert published["source"]["usage_author"]["id"] == str(person.pk)
    Person.objects.filter(pk=person.pk).update(authority_status="pending")
    assert service.read("node", node.pk, public=True)["items"] == []


@pytest.mark.parametrize("field", ["usage_type", "review_status"])
@pytest.mark.parametrize("value", [[], {}, None, 1])
def test_invalid_concept_usage_types_return_400_without_saving(api_client, admin_user, sources, field, value):
    node = KnowledgeNode.objects.create(canonical_name_zh="待编辑概念", node_type="concept", slug="invalid-usage", status="published")
    saved = service.command("node", node.pk, {
        "action": "save", "request_id": str(uuid4()), "expected_revision": "0",
        "items": [{"target": {"type": "span", "id": str(sources[3].pk)},
                   "concept_usage": {"term": "原文术语"}}],
    }, admin_user)
    request_id = str(uuid4())
    api_client.force_authenticate(admin_user)
    response = api_client.post(f"/api/catalog/admin/content-placements/node/{node.pk}/", {
        "action": "update", "request_id": request_id, "expected_revision": saved["expected_revision"],
        "item_id": saved["items"][0]["id"],
        "patch": {"concept_usage": {**saved["items"][0]["concept_usage"], field: value}},
    }, format="json")
    assert response.status_code == 400
    current = service.read("node", node.pk, actor=admin_user)
    assert current["expected_revision"] == saved["expected_revision"]
    assert current["items"][0]["concept_usage"] == saved["items"][0]["concept_usage"]
    assert not AuditEvent.objects.filter(request_id=request_id).exists()
