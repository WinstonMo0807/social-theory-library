from uuid import uuid4

import pytest
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import ValidationError

from catalog.models import (Asset, CatalogPublicationRevision, DocumentRevision, Edition, EditorialRevision,
                            EvidenceCurationReference, EvidenceSpan, KnowledgeNode, Page, Passage,
                            Person, ScholarProfile, Topic, Work)
from catalog.services import shared_curation as service
from catalog.services.editorial_issues import EditConflict

pytestmark = pytest.mark.django_db


def source_fixture(*, title="准确版本", public=True, snapshot=None):
    work = Work.objects.create(document_type="book", title=title)
    edition = Edition.objects.create(work=work, version_label="指定第二版", state="published" if public else "draft")
    asset = Asset.objects.create(edition=edition, kind="normalized", sha256=uuid4().hex * 2, status="ready", validation_status="valid", access_status="public", page_count=5)
    page = Page.objects.create(asset=asset, index=3, text="前文。真实原文。后文。", text_source="native")
    doc = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum="1" * 64, text_checksum="2" * 64)
    span = EvidenceSpan.objects.create(document_revision=doc, page=page, page_number=3, original_text="真实原文。", content_hash="3" * 64, start_offset=3, end_offset=8)
    passage = Passage.objects.create(page=page, order=1, text="真实原文。", start_offset=3, end_offset=8)
    if public:
        revision = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active", metadata_ready=True, fulltext_ready=True,
            reader_asset=asset, document_revision=doc, snapshot=snapshot if snapshot is not None else {"work": {"title": title}, "edition": {"version_label": "指定第二版"}}, content_fingerprint=str(uuid4()))
        edition.active_catalog_revision = revision
        edition.save(update_fields=["active_catalog_revision"])
    return span, passage


def scholar(name, status="published"):
    return ScholarProfile.objects.create(person=Person.objects.create(preferred_name=name, authority_status="verified"), slug=f"scholar-{uuid4()}", editorial_status=status)


def data_for(source, kind="span", version="0"):
    return {"edit_version": version, "items": [{"source_type": kind, "source_id": str(source.pk), "group_title": "核心问题", "reason": "本页关联理由", "order": 0}]}


@pytest.mark.parametrize("kind", ["topic", "scholar", "node"])
def test_shared_curation_explicit_publication_and_snapshot_isolation(kind, admin_user, api_client):
    span, _ = source_fixture()
    parent = Topic.objects.create(name="策展主题", slug="curated", editorial_status="published") if kind == "topic" else scholar("策展学者") if kind == "scholar" else KnowledgeNode.objects.create(canonical_name_zh="策展理论", node_type="theory_tradition", slug="curated", status="published")
    public_url = f"/api/catalog/evidence-curation/{kind}/{parent.pk}/"
    saved = service.save_curation(kind, parent.pk, data_for(span), admin_user)
    assert api_client.get(public_url).data["configured"] is False
    assert saved["items"][0]["source"]["page_start"] == 3
    assert saved["items"][0]["source"]["edition_id"] == str(span.page.asset.edition_id)
    service.publish_curation(kind, parent.pk, saved["edit_version"], admin_user)
    published = api_client.get(public_url).data
    assert published["items"][0]["source"]["text"] == "真实原文。"
    edit = data_for(span, version=service.curation_payload(kind, parent.pk)["edit_version"])
    edit["items"][0]["reason"] = "未发布的改写说明"
    service.save_curation(kind, parent.pk, edit, admin_user)
    assert api_client.get(public_url).data["items"][0]["reason"] == "本页关联理由"
    span.refresh_from_db()
    assert span.original_text == "真实原文。"
    assert all("text" not in item for revision in EditorialRevision.objects.filter(target_type="evidence_curation") for item in revision.materialized_preview["items"])
    Asset.objects.filter(pk=span.page.asset_id).update(access_status="restricted")
    assert api_client.get(public_url).data["items"] == []


def test_curation_blocks_source_mutation_stale_tokens_and_unpublished_source(admin_user):
    span, _ = source_fixture(public=False)
    parent = Topic.objects.create(name="内部主题", slug="internal")
    saved = service.save_curation("topic", parent.pk, data_for(span), admin_user)
    with pytest.raises(ValidationError, match="尚未公开"):
        service.publish_curation("topic", parent.pk, saved["edit_version"], admin_user)
    with pytest.raises(EditConflict):
        service.save_curation("topic", parent.pk, data_for(span), admin_user)
    malicious = data_for(span, version=saved["edit_version"])
    malicious["items"][0]["text"] = "篡改原文"
    with pytest.raises(ValidationError, match="不能修改原文"):
        service.save_curation("topic", parent.pk, malicious, admin_user)
    with pytest.raises(ProtectedError):
        span.delete()


def test_curation_passage_reference_retains_exact_file_and_permission(api_client, admin_user, reader_user):
    _, passage = source_fixture()
    topic = Topic.objects.create(name="段落主题", slug="passage", editorial_status="published")
    admin_url = f"/api/catalog/admin/evidence-curation/topic/{topic.pk}/"
    api_client.force_authenticate(admin_user)
    saved = api_client.put(admin_url, data_for(passage, "passage"), format="json")
    assert saved.status_code == 200
    row = saved.data["items"][0]["source"]
    assert row["asset_id"] == str(passage.page.asset_id)
    assert row["context_before"] == "前文。"
    assert api_client.post(admin_url + "publish/", {"edit_version": saved.data["edit_version"]}, format="json").status_code == 200
    api_client.force_authenticate(reader_user)
    assert api_client.get(admin_url).status_code == 403
    assert api_client.get("/api/catalog/admin/evidence-curation/sources/").status_code == 403
    api_client.force_authenticate(None)
    assert api_client.get(admin_url).status_code in (401, 403)


def test_curation_sources_page_filters_exact_asset_before_pagination(api_client, admin_user):
    span, passage = source_fixture()
    source_fixture(title="另一个文件")
    for order in range(2, 28):
        Passage.objects.create(page=passage.page, order=order, text=f"原文 {order}")
    api_client.force_authenticate(admin_user)
    response = api_client.get(f"/api/catalog/admin/evidence-curation/sources/?asset={span.page.asset_id}&page=2")
    assert response.status_code == 200
    assert response.data["count"] == 28
    assert len(response.data["results"]) == 4
    assert {row["asset_id"] for row in response.data["results"]} == {str(span.page.asset_id)}


def test_passage_curation_does_not_follow_a_new_document_revision(api_client, admin_user):
    span, passage = source_fixture()
    topic = Topic.objects.create(name="版本绑定", slug="bound-revision", editorial_status="published")
    saved = service.save_curation("topic", topic.pk, data_for(passage, "passage"), admin_user)
    service.publish_curation("topic", topic.pk, saved["edit_version"], admin_user)
    public_url = f"/api/catalog/evidence-curation/topic/{topic.pk}/"
    assert len(api_client.get(public_url).data["items"]) == 1
    DocumentRevision.objects.filter(pk=span.document_revision_id).update(is_active=False)
    next_document = DocumentRevision.objects.create(asset=passage.page.asset, revision=2, source_checksum="4" * 64, text_checksum="5" * 64)
    CatalogPublicationRevision.objects.filter(edition=passage.page.asset.edition, status="active").update(status="superseded")
    new_publication = CatalogPublicationRevision.objects.create(edition=passage.page.asset.edition, revision=2, status="active", metadata_ready=True, fulltext_ready=True,
        reader_asset=passage.page.asset, document_revision=next_document, snapshot={"work": {"title": "新文档版本"}}, content_fingerprint=str(uuid4()))
    Edition.objects.filter(pk=passage.page.asset.edition_id).update(active_catalog_revision=new_publication)
    assert api_client.get(public_url).data["items"] == []
    reference = EvidenceCurationReference.objects.get(pk=saved["items"][0]["id"])
    assert reference.document_revision_id == span.document_revision_id


def test_public_curation_does_not_fill_missing_snapshot_label_from_live_draft(admin_user):
    span, _ = source_fixture(snapshot={"work": {"title": "公开题名"}})
    topic = Topic.objects.create(name="版本隔离", slug="label-isolation", editorial_status="published")
    saved = service.save_curation("topic", topic.pk, data_for(span), admin_user)
    service.publish_curation("topic", topic.pk, saved["edit_version"], admin_user)
    Edition.objects.filter(pk=span.page.asset.edition_id).update(version_label="后台未公开标签")
    source = service.curation_payload("topic", topic.pk, public=True)["items"][0]["source"]
    assert source["edition_label"] == "已公开版本"
    assert source["work_title"] == "公开题名"


def test_scholar_relation_shared_identity_keeps_public_draft_isolation(api_client, admin_user):
    from catalog import models as m
    from catalog.services.knowledge_workspace import submit_page_assertion, source_hash
    from catalog.services.knowledge_core import entity_for_legacy
    from .test_stl4_scholar_relation_commands_20261024 import publish
    from .test_manual_knowledge_sources import apply_all
    first, second, third = scholar("一"), scholar("二"), scholar("三")
    data = {"source_scholar": str(first.pk), "target_scholar": str(second.pk), "relation_type": "influence", "direction": "directed", "summary": "有出处的影响", "source": "馆藏第3页"}
    api_client.force_authenticate(admin_user)
    created = api_client.post("/api/catalog/admin/scholar-relations/", data, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk), HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert created.status_code == 202
    page = publish(m.ChangeSet.objects.get(pk=created.data["id"]), admin_user)
    statement = m.Assertion.objects.get()
    left = api_client.get(f"/api/catalog/scholar-relations/?scholar={first.pk}").data["results"][0]
    right = api_client.get(f"/api/catalog/scholar-relations/?scholar={second.pk}").data["results"][0]
    assert left["id"] == right["id"] == str(statement.pk)
    assert left["source_slug"] == first.slug and right["target_slug"] == second.slug
    revised = {"text": "草稿改变对象", "predicate": "influence", "expression": "editorial_judgment", "source_citation": "人工出处", "evidence": [],
        "supersedes_id": str(statement.pk), "base_hash": source_hash("assertion", statement.pk),
        "participants": [{"role": "subject", "entity_id": str(entity_for_legacy(first.person).pk)}, {"role": "object", "entity_id": str(entity_for_legacy(third.person).pk)}]}
    pending = submit_page_assertion(page, revised, admin_user, request_id=uuid4())
    assert not apply_all(pending, admin_user)["blocked"]
    assert api_client.get(f"/api/catalog/scholar-relations/?scholar={second.pk}").data["count"] == 1
    assert api_client.get(f"/api/catalog/scholar-relations/?scholar={third.pk}").data["count"] == 0
    statement.text = "同时修改"
    statement.save(update_fields=["text"])
    with pytest.raises(ValidationError):
        submit_page_assertion(page, revised, admin_user, request_id=uuid4())
    second.editorial_status = "draft"
    second.save(update_fields=["editorial_status"])
    assert api_client.get(f"/api/catalog/scholar-relations/?scholar={first.pk}").data["count"] == 0


def test_scholar_relation_requires_source_and_public_endpoints(admin_user, api_client, reader_user):
    from django.http import Http404
    from .test_stl4_scholar_relation_commands_20261024 import publish
    first, second = scholar("公开"), scholar("未公开", "draft")
    data = {"request_id": str(uuid4()), "source_scholar": str(first.pk), "target_scholar": str(second.pk), "relation_type": "comparative_reading", "direction": "undirected", "summary": "共同阅读", "source": ""}
    with pytest.raises(ValidationError):
        service.save_relation(None, data, admin_user)
    pending = service.save_relation(None, {**data, "source": "编辑阅读说明"}, admin_user)
    with pytest.raises((ValidationError, Http404)):
        publish(pending, admin_user)
    api_client.force_authenticate(reader_user)
    assert api_client.get("/api/catalog/admin/scholar-relations/").status_code == 403


def test_shared_curation_drafts_appear_in_real_queue(api_client, admin_user):
    span, _ = source_fixture()
    topic = Topic.objects.create(name="待核策展", slug="queue", editorial_status="published")
    curation = service.save_curation("topic", topic.pk, data_for(span), admin_user)
    first, second = scholar("甲"), scholar("乙")
    relation = service.save_relation(None, {"request_id": str(uuid4()), "source_scholar": str(first.pk), "target_scholar": str(second.pk), "relation_type": "cooperation", "direction": "bidirectional", "summary": "待审关系", "source": "测试人工出处"}, admin_user)
    api_client.force_authenticate(admin_user)
    rows = api_client.get("/api/catalog/admin/curation-drafts/").data["results"]
    assert any(row["object_id"] == curation["id"] and row["edit_url"] == f"/admin/topics/{topic.pk}?section=passages" for row in rows)
    from catalog.services.academic_relations import relation_directory
    queue = relation_directory(admin_user, entity_id=relation.subject_entity_id)
    assert any(row["id"] == str(relation.pk) for row in queue["pending_changesets"])


def test_scholar_relation_archive_hides_both_ends_preserves_history_and_conflicts(api_client, admin_user, reader_user):
    from catalog import models as m
    from catalog.services.knowledge_migration import migrate_relation, migrate_assertion_page
    from catalog.services.knowledge_workspace import source_hash
    from .test_stl4_scholar_relation_sources_20261024 import historical, material
    from .test_stl4_scholar_relation_commands_20261024 import publish
    first, second = scholar("归档甲"), scholar("归档乙")
    span, _, _ = material()
    row = historical(first, second, span)
    statement = m.Assertion.objects.get(pk=migrate_relation(row).target_id)
    migrate_assertion_page(statement)
    public_revision = row.active_revision_id
    url = f"/api/catalog/admin/scholar-relations/{row.pk}/archive/"
    body = {"base_hash": source_hash("assertion", statement.pk), "reason": "审核后撤回"}
    api_client.force_authenticate(reader_user)
    assert api_client.post(url, body, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk), HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code == 403
    api_client.force_authenticate(admin_user)
    archived = api_client.post(url, body, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk), HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert archived.status_code == 202, archived.data
    assert api_client.get(f"/api/catalog/scholar-relations/?scholar={first.pk}").data["count"] == 1
    publish(m.ChangeSet.objects.get(pk=archived.data["id"]), admin_user)
    for person in (first, second):
        assert api_client.get(f"/api/catalog/scholar-relations/?scholar={person.pk}").data["count"] == 0
    assert m.EditorialRevision.objects.get(pk=public_revision).status == "published"
    assert m.ScholarRelation.objects.get(pk=row.pk).status == "published"
    assert api_client.post(url, body, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk), HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code in {400, 409}
    from ingestion.models import AuditEvent
    assert AuditEvent.objects.filter(action="knowledge.assertion_withdrawn", object_id=str(statement.pk)).exists()
