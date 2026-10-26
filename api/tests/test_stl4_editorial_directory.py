"""PDF73–78 acceptance definitions. Never seed or mutate a running library."""
from datetime import timedelta
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from accounts.models import User
from catalog.models import EditorialRevision, RecommendationIssue
from catalog.services import editorial_issues as issues
from catalog.services.public_editorial import article_context, metadata_input, public_directory, public_metadata, published_media_usage
from reading import issue_lists, privacy, research
from reading.models import ReadingList
from .test_v307_editorial_issues import issue_data, public_edition

pytestmark = pytest.mark.django_db


def article(actor, **values):
    row = issues.create_issue({"title": "测试专用文章", "public_byline": "测试公开署名", "items": [],
        "body_blocks": [{"type": "heading", "text": "测试章节"}, {"type": "paragraph", "text": "用于隔离验收的测试正文"}], **values}, actor)
    issues.publish_issue(row.pk, issues.edit_version("recommendation_issue", row.pk), actor)
    row.refresh_from_db()
    return row


def test_directory_reads_effective_snapshot_not_draft_or_future(admin_user):
    row = article(admin_user, title="当前公开题名")
    issues.save_issue(row.pk, {"edit_version": issues.edit_version("recommendation_issue", row.pk), "title": "未来排期题名", "display_from": (timezone.now()+timedelta(days=2)).isoformat()}, admin_user)
    issues.publish_issue(row.pk, issues.edit_version("recommendation_issue", row.pk), admin_user)
    issues.save_issue(row.pk, {"edit_version": issues.edit_version("recommendation_issue", row.pk), "title": "未发布草稿题名"}, admin_user)
    assert public_directory({"q":"当前公开题名"})["count"] == 1
    assert public_directory({"q":"未来排期题名"})["count"] == public_directory({"q":"未发布草稿题名"})["count"] == 0
    RecommendationIssue.objects.filter(pk=row.pk).update(scheduled_for=timezone.now()-timedelta(seconds=1))
    assert public_directory({"q":"未来排期题名"})["count"] == 1
    assert public_directory({"q":"当前公开题名"})["count"] == 0


def test_directory_does_not_drop_six_cards_and_preserves_scalar_filters(admin_user):
    for index in range(9):
        article(admin_user, title=f"目录测试{index}", public_byline="公开姓氏, 名字")
    data = public_directory({"curator":"公开姓氏, 名字", "page_size":"8"})
    assert data["count"] == 9 and len(data["results"]) == 8
    assert parse_qs(urlsplit(data["next"]).query)["curator"] == ["公开姓氏, 名字"]
    assert parse_qs(urlsplit(data["next"]).query)["view"] == ["directory"]


@pytest.mark.parametrize("params", [{"year_from":"0"}, {"year_to":"9999"}, {"year_from":"2001","year_to":"1900"}, {"sort":"unknown"}, {"kind":"private"}, {"page":"0"}])
def test_invalid_directory_conditions_are_explicit(params):
    with pytest.raises(ValidationError):
        public_directory(params)


def test_anonymous_curator_never_infers_account_or_returns_portrait_fields(admin_user):
    row = article(admin_user, public_byline="", article_metadata={"curator_role":"测试身份", "curator_affiliation":"测试机构"})
    card = public_directory()["results"][0]
    assert card["curator"] == {"name":"", "role":"", "affiliation":"", "portrait_url":""}
    assert card["article_metadata"]["curator_affiliation"] == ""
    assert str(admin_user.pk) not in card["curator"].values()
    assert public_metadata(issues.issue_draft_payload(row), public=False)[0]["curator_role"] == "测试身份"


def test_home_curator_uses_effective_public_identity_not_editor_or_draft(admin_user):
    from catalog.site_layout import source_card
    row = article(admin_user, public_byline="公开策划署名", article_metadata={"curator_role":"公开身份"})
    issues.save_issue(row.pk, {"edit_version":issues.edit_version("recommendation_issue", row.pk),
        "public_byline":"未发布署名", "article_metadata":{"curator_role":"私人草稿身份"}}, admin_user)
    row.refresh_from_db()
    card = source_card({"type":"issue", "id":str(row.pk)})
    assert card["curator"] == {"name":"公开策划署名", "role":"公开身份", "affiliation":"", "portrait_url":""}
    anonymous = article(admin_user, public_byline="", article_metadata={"curator_role":"不公开身份"})
    assert source_card({"type":"issue", "id":str(anonymous.pk)})["curator"] == {
        "name":"", "role":"", "affiliation":"", "portrait_url":""}


def test_article_only_publication_and_stable_section_identity(admin_user):
    row = article(admin_user)
    first = article_context(row, issues.issue_payload(row, public=True))
    draft = issues.issue_draft_payload(row)
    draft.update(edit_version=issues.edit_version("recommendation_issue", row.pk), title="下一版题名")
    issues.save_issue(row.pk, draft, admin_user)
    issues.publish_issue(row.pk, issues.edit_version("recommendation_issue", row.pk), admin_user)
    row.refresh_from_db()
    second = article_context(row, issues.issue_payload(row, public=True))
    assert first["body_blocks"][0]["id"] == second["body_blocks"][0]["id"]
    assert first["public_revision_id"] != second["public_revision_id"]


def test_missing_image_preserves_caption_and_provenance(admin_user):
    row = article(admin_user, article_metadata={"kind":"exhibition"}, body_blocks=[{"type":"image","text":"测试展项", "alt_text":"测试图像说明", "source":"测试来源，非历史材料", "image_rendition_id":None}])
    block = issues.issue_payload(row, public=True)["body_blocks"][0]
    assert block["source_status"] == "unavailable" and block["image_url"] == ""
    assert block["source"] and block["alt_text"]


def test_media_permission_follows_effective_revision_not_uuid_in_prose(admin_user):
    key = str(uuid4())
    row = article(admin_user)
    active = row.active_revision
    active.materialized_preview["cover_rendition_id"] = key
    active.save(update_fields=["materialized_preview"])
    assert published_media_usage(key)
    replacement = EditorialRevision.objects.create(target_type="recommendation_issue", target_id=row.pk, revision=2, status="published",
        materialized_preview={"title":"替换", "body_blocks":[{"type":"paragraph", "text":key}]}, idempotency_key=f"test:{uuid4()}")
    RecommendationIssue.objects.filter(pk=row.pk).update(scheduled_revision=replacement,scheduled_for=timezone.now()-timedelta(seconds=1))
    assert not published_media_usage(key)
    replacement.materialized_preview["body_blocks"] = [{"type":"image","image_rendition_id":key}]
    replacement.save(update_fields=["materialized_preview"])
    assert published_media_usage(key)


def test_metadata_rejects_unknown_identity_and_duplicate_blocks(admin_user):
    with pytest.raises(ValidationError): metadata_input({"topic_ids":[str(uuid4())]})
    block = {"id":str(uuid4()),"type":"heading","text":"重复身份"}
    with pytest.raises(ValidationError): issues.create_issue({"title":"测试", "body_blocks":[block,block]}, admin_user)


def test_work_list_uses_receipt_after_deletion_and_ignores_republication(admin_user):
    row = article(admin_user, **issue_data(public_edition()))
    data = {"request_id":uuid4(), "public_revision_id":row.active_revision_id}
    saved = issue_lists.save(admin_user, row.slug, data)
    assert saved["saved"] and saved["item_count"] == 1
    ReadingList.objects.get(pk=saved["id"]).delete()
    assert not issue_lists.save(admin_user, row.slug, data)["saved"]
    assert not issue_lists.state(admin_user, row.slug, data["public_revision_id"],data["request_id"])["saved"]
    assert ReadingList.objects.filter(user=admin_user).count() == 0


def test_work_list_commands_bind_owner_revision_and_retention(api_client, admin_user):
    row = article(admin_user, **issue_data(public_edition()))
    reader = User.objects.create_user(username="curation-private-reader",role="reader")
    api_client.force_authenticate(reader)
    url = f"/api/catalog/recommendation-issues/{row.slug}/save-list/"
    data = {"request_id":str(uuid4()),"public_revision_id":str(row.active_revision_id)}
    assert api_client.post(url,data,format="json").status_code == 403
    response = api_client.post(url,data,format="json",HTTP_X_READER_OWNER=str(reader.pk))
    assert response.status_code == 200 and response.data["owner_id"] == str(reader.pk)
    with pytest.raises(NotFound): issue_lists.state(admin_user,row.slug,data["public_revision_id"],data["request_id"])
    with pytest.raises(research.ResearchConflict): issue_lists.save(reader,row.slug,{"request_id":uuid4(),"public_revision_id":uuid4()})
    privacy.update_preferences(reader,{"expected_revision":privacy.preferences(reader)["revision"],"retention":{"saved_knowledge":False}})
    with pytest.raises(ValidationError): issue_lists.save(reader,row.slug,{"request_id":uuid4(),"public_revision_id":row.active_revision_id})


def test_private_list_export_erase_checks_membership_changes(admin_user):
    row = article(admin_user, **issue_data(public_edition()))
    saved = issue_lists.save(admin_user,row.slug,{"request_id":uuid4(),"public_revision_id":row.active_revision_id})
    record = ReadingList.objects.get(pk=saved["id"])
    assert privacy.export_item(admin_user,"reading_lists",record)["items"]
    target = privacy.target_of(record,"reading_lists")
    assert "公开馆藏保留" in privacy.erase_impact(admin_user,"reading_lists",record)["message"]
    record.items.update(order=99)
    with pytest.raises(research.ResearchConflict): privacy.verify_target(admin_user,target)


def test_exhibit_section_must_reference_real_heading_and_stays_stable(admin_user):
    section = str(uuid4())
    edition = public_edition()
    values = issue_data(edition)
    values["body_blocks"] = [{"id":section,"type":"heading","text":"测试分组"}]
    values["items"][0]["section_id"] = section
    row = article(admin_user, **values)
    assert issues.issue_payload(row, public=True)["items"][0]["section_id"] == section
    values["body_blocks"] = []
    with pytest.raises(ValidationError):
        issues.save_issue(row.pk,{**values,"edit_version":issues.edit_version("recommendation_issue",row.pk)},admin_user)


def test_unavailable_analysis_heading_keeps_group_identity(monkeypatch):
    from django.http import Http404
    from catalog.services import editorial_blocks
    key = str(uuid4())
    def unavailable(*args, **kwargs):
        raise Http404
    monkeypatch.setattr(editorial_blocks,"resolve_target",unavailable)
    blocks, problems = editorial_blocks.body_payload([{"id":key,"type":"analysis","style":"heading","text":"不能沿用的旧来源文字","references":[{"type":"node","id":str(uuid4())}]}],public=True)
    assert problems and blocks[0]["id"] == key and blocks[0]["style"] == "heading"
    assert blocks[0]["text"] == "" and blocks[0]["source_status"] == "unavailable"


def comment_data(row):
    return {"request_id":uuid4(),"public_revision_id":row.active_revision_id,"byline":"测试公开笔名","body":"测试评论，不是真实学术意见。","confirm_public":True}


def test_comments_require_consent_owner_and_publication_authority(api_client, admin_user):
    from reading import editorial_comments as comments
    row = article(admin_user)
    reader = User.objects.create_user(username="comment-owner",role="reader")
    url = f"/api/reading/article-comments/{row.pk}/"
    data = comment_data(row)
    api_client.force_authenticate(reader)
    assert api_client.post(url,data,format="json").status_code == 403
    assert api_client.post(url,{**data,"confirm_public":False},format="json",HTTP_X_READER_OWNER=str(reader.pk)).status_code == 400
    response = api_client.post(url,data,format="json",HTTP_X_READER_OWNER=str(reader.pk))
    assert response.status_code == 200 and response.data["comment"]["status"] == "pending"
    assert comments.public_page(row.pk,{})["count"] == 0
    moderate = {"id":data["request_id"],"expected_revision":1,"status":"published"}
    assert api_client.post(f"/api/reading/article-comments/admin/{row.pk}/",moderate,format="json").status_code == 403
    comments.moderate(admin_user,row.pk,moderate)
    public = comments.public_page(row.pk,{})["results"][0]
    assert public["byline"] == data["byline"] and "owner_id" not in public and "user_id" not in public and "moderation_reason" not in public
    assert comments.own_page(admin_user,row.pk,{})["count"] == 0


def test_comment_unknown_retry_does_not_recreate_erased_content(admin_user):
    from reading import editorial_comments as comments
    from reading.editorial_comment_models import EditorialComment
    row = article(admin_user)
    data = comment_data(row)
    first = comments.submit(admin_user,row.pk,data)
    assert comments.submit(admin_user,row.pk,data) == first
    with pytest.raises(research.ResearchConflict): comments.submit(admin_user,row.pk,{**data,"body":"不同内容"})
    record = EditorialComment.objects.get(pk=data["request_id"])
    assert privacy.export_item(admin_user,"article_comments",record)["body"] == data["body"]
    target = privacy.target_of(record,"article_comments")
    comments.moderate(admin_user,row.pk,{"id":record.pk,"expected_revision":1,"status":"published"})
    with pytest.raises(research.ResearchConflict): privacy.verify_target(admin_user,target)
    comments.remove(admin_user,row.pk,record.pk,2)
    assert comments.public_page(row.pk,{})["count"] == 0
    assert comments.submit(admin_user,row.pk,data)["comment"] is None
    assert comments.receipt_state(admin_user,row.pk,data["request_id"])["comment"] is None


def test_comment_public_revision_never_moves_to_rewritten_article(admin_user):
    from reading import editorial_comments as comments
    row = article(admin_user)
    data = comment_data(row)
    comments.submit(admin_user,row.pk,data)
    comments.moderate(admin_user,row.pk,{"id":data["request_id"],"expected_revision":1,"status":"published"})
    issues.save_issue(row.pk,{"edit_version":issues.edit_version("recommendation_issue",row.pk),"title":"新版本测试"},admin_user)
    issues.publish_issue(row.pk,issues.edit_version("recommendation_issue",row.pk),admin_user)
    assert comments.public_page(row.pk,{})["count"] == 0
    assert comments.own_page(admin_user,row.pk,{})["count"] == 1
    with pytest.raises(research.ResearchConflict): comments.public_page(row.pk,{"public_revision_id":data["public_revision_id"]})
    with pytest.raises(research.ResearchConflict): comments.submit(admin_user,row.pk,{**data,"request_id":uuid4()})


def test_theory_filter_uses_only_published_article_links_and_visible_traditions(admin_user):
    from catalog.models import KnowledgeNode
    theory = KnowledgeNode.objects.create(node_type="theory_tradition", canonical_name_zh="测试传统", slug="test-tradition", status="published")
    draft = KnowledgeNode.objects.create(node_type="theory_tradition", canonical_name_zh="未公开传统", slug="draft-tradition", status="draft")
    from catalog.editorial_issue_serializers import ArticleMetadataSerializer
    metadata = ArticleMetadataSerializer(data={"theory_ids":[str(theory.pk), str(draft.pk)]})
    metadata.is_valid(raise_exception=True)
    assert metadata.validated_data["theory_ids"] == [theory.pk, draft.pk]
    row = article(admin_user, article_metadata=metadata.validated_data)
    data = public_directory({"theory":theory.slug})
    assert data["count"] == 1 and data["facets"]["theories"] == [{"id":str(theory.pk),"slug":theory.slug,"name":theory.canonical_name_zh,"href":f"/theories/nodes/{theory.slug}"}]
    assert data["results"][0]["article_metadata"]["theory_ids"] == [str(theory.pk)]
    assert public_directory({"theory":draft.slug})["count"] == 0
    issues.save_issue(row.pk, {"edit_version":issues.edit_version("recommendation_issue",row.pk), "article_metadata":{"theory_ids":[]}}, admin_user)
    assert public_directory({"theory":str(theory.pk)})["count"] == 1
    issues.publish_issue(row.pk, issues.edit_version("recommendation_issue",row.pk), admin_user)
    assert public_directory({"theory":theory.slug})["count"] == 0
    concept = KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="测试概念", slug="test-concept")
    with pytest.raises(ValidationError):
        metadata_input({"theory_ids":[str(concept.pk)]})
