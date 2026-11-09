from uuid import uuid4
import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError
from catalog import models as m
from catalog.services.knowledge_workspace import open_page, submit_page_changes, page_workspace
from catalog.services.knowledge_core import page_content, export_page
from catalog.services.knowledge_public import publish_page
from catalog.services.intelligence_queries import changeset_data
from catalog.services.intelligence_changes import submit_draft
from tests.test_manual_knowledge_sources import apply_all
from tests.v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def references():
    result = []
    for title in ("隔离测试作品甲", "隔离测试作品乙"):
        work = m.Work.objects.create(title=title)
        edition = m.Edition.objects.create(work=work, state="published", public_slug=str(uuid4()))
        activate_catalog_revision(edition, fulltext_ready=False)
        result.append({"type": "work", "id": str(work.pk), "edition_id": str(edition.pk)})
    return result


def test_special_page_creation_review_publication_and_metadata_preview(admin_user, reader_user, api_client):
    key = uuid4()
    with pytest.raises(PermissionDenied):
        open_page(reader_user, title="专题", scope="两部作品", request_id=key)
    data = open_page(admin_user, title="专题原题", scope="比较两部指定作品的概念用法", request_id=key)
    assert open_page(admin_user, title="专题原题", scope="比较两部指定作品的概念用法", request_id=key)["id"] == data["id"]
    page = m.KnowledgePage.objects.get(pk=data["id"])
    public = f"/api/knowledge/special/{page.slug}/"
    assert api_client.get(public).status_code == 404
    block_id = str(uuid4())
    patches = [{"operation": "add", "block_id": block_id, "block": {"type": "analysis", "text": "隔离测试的人工编纂说明", "references": references()}},
        {"operation": "metadata", "block_id": str(page.pk), "base_hash": data["metadata_hash"], "title": "专题审定标题", "scope": "纳入甲乙两个出版版本，保留不同用法。"}]
    draft = submit_page_changes(page, None, patches, admin_user, request_id=uuid4())
    assert draft.subject_page_id == page.pk and draft.document_revision_id is None
    assert changeset_data(draft, admin_user)["title"] == "专题原题"
    result = apply_all(draft, admin_user)
    assert not result["blocked"], result
    page.refresh_from_db()
    preview = page_workspace(page, admin_user)
    assert preview["title"] == "专题审定标题" and page.title == "专题原题"
    assert api_client.get(public).status_code == 404
    assert "# 专题审定标题" in export_page(page, admin_user, draft=True)
    publish_page(page.pk, page_content(page)[1].pk, admin_user)
    assert api_client.get(public).data["title"] == "专题审定标题"
    assert api_client.get(public).data["blocks"][0]["id"] == block_id
    assert len(api_client.get(public).data["references"]) == 2
    assert all(ref["work_url"] for ref in api_client.get(public).data["references"])
    assert changeset_data(draft, admin_user)["status"] == "published"
    for origin in ("external", "intelligence"):
        with pytest.raises(ValidationError):
            submit_draft(None, [], admin_user, origin=origin, request_id=uuid4(), subject_page=page)


def test_metadata_conflict_keeps_independent_reviewed_block(admin_user):
    data = open_page(admin_user, title="标题", scope="范围", request_id=uuid4())
    page = m.KnowledgePage.objects.get(pk=data["id"])
    metadata = {"operation": "metadata", "block_id": str(page.pk), "base_hash": data["metadata_hash"], "title": "后续管理员标题", "scope": "原范围"}
    current = submit_page_changes(page, None, [metadata], admin_user, request_id=uuid4())
    assert not apply_all(current, admin_user)["blocked"]
    stale = submit_page_changes(page, None, [{**metadata, "title": "陈旧标题"},
        {"operation": "add", "block_id": str(uuid4()), "block": {"type": "analysis", "text": "独立正文修改", "references": references()}}], admin_user, request_id=uuid4())
    result = apply_all(stale, admin_user)
    assert len(result["blocked"]) == 1
    assert page_workspace(page, admin_user)["title"] == "后续管理员标题"
    assert page_content(page)[0][0]["text"] == "独立正文修改"
    assert stale.items.filter(decision="accepted").count() == 2
