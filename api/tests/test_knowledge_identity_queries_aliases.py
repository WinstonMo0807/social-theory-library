from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_core import entity_data, entity_for_legacy, match_entities
from catalog.services.knowledge_entity_queries import entity_query
from catalog.services.knowledge_aliases import submit_alias
from catalog.services.knowledge_workspace import source_hash
from catalog.services.knowledge_public import page_data, publish_page, public_entities
from catalog.services.retrieval.objects import search
from catalog.services.intelligence_queries import changeset_data
from tests.test_manual_knowledge_sources import apply_all

pytestmark = pytest.mark.django_db


def identity():
    node = m.KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="原概念名称", definition="原定义", slug=str(uuid4()), status="published")
    return node, entity_for_legacy(node)


def test_profile_rename_is_shared_by_matching_http_and_search(admin_user, reader_user, api_client):
    node, entity = identity()
    node.canonical_name_zh, node.definition = "更新的概念名称", "更新的定义范围"
    node.save(update_fields=["canonical_name_zh", "definition"])
    entity.refresh_from_db()
    assert entity.label == "原概念名称"  # Historical migration copy is not a second authority.
    assert entity_data(entity)["label"] == "更新的概念名称"
    assert match_entities("更新的概念名称", "concept")[0]["id"] == str(entity.pk)
    assert not match_entities("原概念名称", "concept")
    api_client.force_authenticate(reader_user)
    result = api_client.get("/api/knowledge/entities/?q=更新的概念")
    assert result.status_code == 200 and result.data["entities"][0]["label"] == "更新的概念名称"
    assert search("更新的定义", reader_user, source_types=["knowledge_object"])["groups"]["knowledge_object"]["results"]
    assert not search("原概念名称", reader_user, source_types=["knowledge_object"])["groups"]["knowledge_object"]["results"]


def test_alias_review_save_preview_publish_and_replay(admin_user, reader_user, api_client):
    _, entity = identity()
    page = m.KnowledgePage.objects.create(entity=entity, title="异名审核", slug="alias-review", status="published")
    key = uuid4()
    payload = {"text": "测试译名", "language": "zh", "script": "Hans"}
    base = source_hash("entity", entity.pk)
    api_client.force_authenticate(reader_user)
    assert api_client.post(f"/api/knowledge/entities/{entity.pk}/aliases/", {**payload, "request_id": str(key), "base_hash": base}, format="json").status_code == 403
    draft = submit_alias(entity, payload, admin_user, request_id=key, base_hash=base)
    api_client.force_authenticate(admin_user)
    response = api_client.post(f"/api/knowledge/entities/{entity.pk}/aliases/", {**payload, "request_id": str(key), "base_hash": base}, format="json")
    assert response.status_code == 201 and response.data["id"] == str(draft.pk), response.data
    assert not m.EntityAlias.objects.filter(text=payload["text"]).exists()
    assert not apply_all(draft, admin_user)["blocked"]
    alias = m.EntityAlias.objects.get(text=payload["text"])
    assert alias.review_status == "draft"
    assert changeset_data(draft, admin_user)["items"][0]["current_status"] == "draft"
    assert not entity_query(public_entities(), query=payload["text"], public=True).exists()
    assert not page_data(page, reader_user)["identity"]["aliases"]
    preview = page_data(page, admin_user, draft=True)
    assert preview["identity"]["aliases"][0]["text"] == payload["text"]
    assert preview["publication_scope"]["aliases"][0]["language"] == "zh"
    assert publish_page(page.pk, preview["revision_id"], admin_user)["identity"]["aliases"][0]["text"] == payload["text"]
    assert publish_page(page.pk, preview["revision_id"], admin_user)["status"] == "published"
    assert entity_query(public_entities(), query=payload["text"], public=True).count() == 1
    assert search(payload["text"], reader_user, source_types=["knowledge_object"])["groups"]["knowledge_object"]["results"]
    assert submit_alias(entity, payload, admin_user, request_id=key, base_hash=base).pk == draft.pk
    assert m.EntityAlias.objects.filter(text=payload["text"]).count() == 1
    assert changeset_data(draft, admin_user)["items"][0]["current_status"] == "published"


def test_changed_alias_cannot_publish_without_new_review(admin_user):
    _, entity = identity()
    draft = submit_alias(entity, {"text": "审核时译名"}, admin_user, request_id=uuid4(), base_hash=source_hash("entity", entity.pk))
    assert not apply_all(draft, admin_user)["blocked"]
    page = m.KnowledgePage.objects.get(entity=entity)
    preview = page_data(page, admin_user, draft=True)
    m.EntityAlias.objects.filter(entity=entity).update(text="后来更改的内容")
    with pytest.raises(ValidationError, match="已变化"):
        publish_page(page.pk, preview["revision_id"], admin_user)
    assert draft.items.get().decision == "accepted"
    assert not m.EntityAlias.objects.filter(review_status="confirmed").exists()
    page.refresh_from_db()
    assert page.status == "draft"


def test_legacy_alias_edits_and_revocation_keep_history_without_stale_query():
    node, entity = identity()
    variant = m.KnowledgeNodeAlias.objects.create(node=node, alias="原已确认译名", is_verified=True, source_kind="legacy_review")
    migrated = m.EntityAlias.objects.create(entity=entity, text=variant.alias, language=variant.language, review_status="confirmed",
        source={"legacy_type": "catalog.knowledgenodealias", "legacy_id": str(variant.pk)})
    original_hash = source_hash("entity", entity.pk)
    variant.alias = "更正后的译名"
    variant.save(update_fields=["alias"])
    assert not entity_query(public_entities(), query="原已确认译名", public=True).exists()
    assert entity_query(public_entities(), query="更正后的译名", public=True).count() == 1
    assert entity_data(entity, public=True)["aliases"][0]["text"] == "更正后的译名"
    assert source_hash("entity", entity.pk) != original_hash
    m.KnowledgeNodeAlias.objects.filter(pk=variant.pk).update(is_verified=False)
    assert not entity_query(public_entities(), query="更正后的译名", public=True).exists()
    assert entity_data(entity, public=True)["aliases"] == []
    migrated.refresh_from_db()
    assert migrated.text == "原已确认译名" and migrated.review_status == "confirmed"
