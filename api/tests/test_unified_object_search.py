from uuid import uuid4
import pytest
from rest_framework.exceptions import PermissionDenied
from catalog import models as m
from catalog.services.retrieval.objects import search
from catalog.services.knowledge_core import entity_for_legacy, entity_data
from .test_stl4_scholar_relation_commands_20261024 import profiles
from .test_v307_shared_curation import source_fixture

pytestmark = pytest.mark.django_db


def test_bibliography_and_wiki_only_use_current_published_content(reader_user):
    span, _ = source_fixture(title="公开财政题名")
    span.page.asset.edition.work.title = "未发布名称"
    span.page.asset.edition.work.save(update_fields=["title"])
    block = {"id": str(uuid4()), "type": "analysis", "text": "财政阅读计划", "references": []}
    page = m.KnowledgePage.objects.create(slug="public-query", title="财政专题", status="published", body_blocks=[block])
    m.EditorialRevision.objects.create(target_type="knowledge_page", target_id=page.pk, revision=2, status="draft",
        materialized_preview={"title": "私有修改题名", "body_blocks": [{**block, "text": "未公开的特殊字符串"}]}, idempotency_key=str(uuid4()))
    m.KnowledgePage.objects.create(slug="private-query", title="财政草稿", body_blocks=[block])
    result = search("财政", reader_user, source_types=["bibliography", "knowledge_page"])
    assert len(result["groups"]["bibliography"]["results"]) == 1
    assert result["groups"]["bibliography"]["results"][0]["title"] == "公开财政题名"
    assert [v["id"] for v in result["groups"]["knowledge_page"]["results"]] == [str(page.pk)]
    assert "locator" not in result["groups"]["knowledge_page"]["results"][0]
    for text in ("未发布名称", "未公开的特殊字符串", "私有修改题名"):
        result = search(text, reader_user, source_types=["bibliography", "knowledge_page"])
        assert all(not v["results"] for v in result["groups"].values())


def test_entity_snapshot_and_confirmed_aliases_do_not_leak_pending_data(reader_user):
    first, second = profiles()
    entity = entity_for_legacy(first.person)
    m.EditorialRevision.objects.create(target_type="scholar_profile", target_id=first.pk, revision=1, status="published",
        materialized_preview={"slug": first.slug, "person": {"preferred_name": "正式人物名称", "biography": "正式人物介绍"}}, idempotency_key=str(uuid4()))
    first.person.preferred_name, first.person.biography = "秘密人物名称", "秘密人物介绍"
    first.person.save(update_fields=["preferred_name", "biography"])
    m.EntityAlias.objects.create(entity=entity, text="隐藏异名", review_status="pending")
    m.EntityAlias.objects.create(entity=entity, text="公开异名", review_status="confirmed", source={"note": "编辑内部信息"})
    m.EntityIdentifier.objects.create(entity=entity, namespace="test", value="private", review_status="pending")
    data = entity_data(entity, public=True)
    assert data["label"] == "正式人物名称" and data["definition"] == "正式人物介绍"
    assert not data["identifiers"] and [v["text"] for v in data["aliases"]] == ["公开异名"]
    assert "source" not in data["aliases"][0]
    assert search("正式人物", reader_user, source_types=["knowledge_object"])["groups"]["knowledge_object"]["results"]
    for text in ["秘密人物", "隐藏异名"]:
        assert not search(text, reader_user, source_types=["knowledge_object"])["groups"]["knowledge_object"]["results"]
    first.editorial_status = "archived"
    first.save(update_fields=["editorial_status"])
    assert not search("正式人物", reader_user, source_types=["knowledge_object"])["groups"]["knowledge_object"]["results"]


def test_withdrawn_reference_cannot_match_hidden_compilation_block(reader_user):
    entity = m.Entity.objects.create(kind="concept", label="不公开对象", status="draft")
    page = m.KnowledgePage.objects.create(slug="hidden-ref", title="普通专题", status="published", body_blocks=[{
        "id": str(uuid4()), "type": "analysis", "text": "特殊查询字符串", "references": [{"type": "entity", "id": str(entity.pk)}]}])
    result = search("特殊查询字符串", reader_user, source_types=["knowledge_page"])
    assert not result["groups"]["knowledge_page"]["results"]


def test_original_failure_is_not_zero_hits_and_does_not_discard_other_groups(reader_user, monkeypatch):
    from catalog.services.retrieval import search as recall
    from catalog.services.discovery_projection import DiscoveryIndexError
    def fail(*args, **kwargs):
        raise DiscoveryIndexError("search_unavailable", "测试服务错误")
    monkeypatch.setattr(recall, "retrieve_channel", fail)
    result = search("财政", reader_user, source_types=["original_text", "knowledge_page"])
    assert result["status"] == "partial" and result["groups"]["original_text"]["status"] == "failed"
    assert result["groups"]["knowledge_page"]["status"] == "ready"
    assert search("财政", reader_user, source_types=["original_text"])["status"] == "failed"
    with pytest.raises(PermissionDenied):
        search("财政", None)
