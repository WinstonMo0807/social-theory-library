"""Workspace permissions, draft boundary and targeted freshness, using test data."""
from uuid import uuid4

import pytest
from django.core.management import call_command
from rest_framework.exceptions import PermissionDenied, ValidationError

from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services import intelligence_changes as changes
from catalog.services.dependency_engine import record_canonical_change
from catalog.services.knowledge_core import apply_page_patch, page_content
from catalog.services.knowledge_sources import digest
from catalog.services.knowledge_workspace import page_directory, page_workspace, submit_page_changes


def add_block(page, reference, actor, *, text="测试编纂文字"):
    key = str(uuid4())
    apply_page_patch({"page_id": str(page.pk), "operation": "add", "block_id": key,
        "block": {"id": key, "type": "analysis", "text": text, "references": [reference]}},
        actor, request_key=str(uuid4()))
    return key


def notify(kind, key, field):
    record_canonical_change(object_type=kind, object_id=key, change_kind="update",
        changed_fields=[field], idempotency_key=str(uuid4()), resolve=False)


@pytest.mark.django_db
def test_human_page_edit_uses_review_and_idempotent_draft_boundary(source, admin_user, reader_user):
    page = m.KnowledgePage.objects.create(work=source.asset.edition.work, slug="manual", title="人工编纂")
    key = str(uuid4())
    patch = {"operation": "add", "block_id": key, "block": {"type": "analysis", "text": "人工导读",
        "references": [{"type": "work", "id": str(page.work_id), "edition_id": str(source.asset.edition_id)}]}}
    request = uuid4()
    draft = submit_page_changes(page, source, [patch], admin_user, request_id=request)
    assert submit_page_changes(page, source, [patch], admin_user, request_id=request).pk == draft.pk
    assert page_content(page)[0] == []
    assert draft.items.get().decision == "pending"
    with pytest.raises(PermissionDenied):
        submit_page_changes(page, source, [patch], reader_user, request_id=uuid4())
    with pytest.raises(ValidationError):
        submit_page_changes(page, source, [{**patch, "reason": "different"}], admin_user, request_id=request)
    item = draft.items.get()
    draft = changes.review(draft.pk, [{"id": str(item.pk), "decision": "accepted"}], admin_user, expected_version=1)
    result = changes.apply(draft.pk, [str(item.pk)], admin_user, request_id=uuid4(), expected_version=draft.version)
    assert set(result["saved"]) == {str(item.pk)}, result
    page.refresh_from_db()
    assert page.body_blocks == [] and page.status == "draft"
    assert page_content(page)[0][0]["human_edited"] is True
    assert page.dependencies.exists()


@pytest.mark.django_db
def test_new_draft_on_published_page_is_not_reported_as_published(source,admin_user):
    from catalog.services.intelligence_queries import changeset_data
    page=m.KnowledgePage.objects.create(work=source.asset.edition.work,slug="already-public",title="已有发布版",status="published")
    key=str(uuid4())
    patch={"operation":"add","block_id":key,"block":{"type":"analysis","text":"尚未发布的新增段落",
        "references":[{"type":"work","id":str(page.work_id),"edition_id":str(source.asset.edition_id)}]}}
    draft=submit_page_changes(page,source,[patch],admin_user,request_id=uuid4())
    item=draft.items.get()
    draft=changes.review(draft.pk,[{"id":str(item.pk),"decision":"accepted"}],admin_user,expected_version=1)
    changes.apply(draft.pk,[str(item.pk)],admin_user,request_id=uuid4(),expected_version=draft.version)
    draft.refresh_from_db()
    assert changeset_data(draft,admin_user)["items"][0]["current_status"]=="draft"
    assert page.body_blocks==[]


@pytest.mark.django_db
def test_entity_page_uses_existing_identity_and_editorial_revision(admin_user):
    entity = m.Entity.objects.create(kind="concept", label="有语境的概念")
    key = str(uuid4())
    result = apply_page_patch({"entity_id": str(entity.pk), "operation": "add", "block_id": key,
        "block": {"type": "analysis", "text": "定义的解释", "references": [{"type": "entity", "id": str(entity.pk)}]}},
        admin_user, request_key=str(uuid4()))
    page = m.KnowledgePage.objects.get(entity=entity)
    assert result.target_id == page.pk
    assert page.body_blocks == [] and m.Entity.objects.count() == 1
    assert page_content(page)[0][0]["id"] == key


@pytest.mark.django_db
def test_semantic_change_marks_only_referencing_blocks_and_preserves_stale_baseline(admin_user):
    person = m.Person.objects.create(preferred_name="测试人物", biography="原简介")
    entity = m.Entity.objects.create(kind="person", label=person.preferred_name, person=person)
    other = m.Entity.objects.create(kind="concept", label="不相关概念")
    page = m.KnowledgePage.objects.create(slug="two-blocks", title="两处来源")
    affected = add_block(page, {"type": "entity", "id": str(entity.pk)}, admin_user)
    unaffected = add_block(page, {"type": "entity", "id": str(other.pk)}, admin_user)
    m.Person.objects.filter(pk=person.pk).update(portrait="fixture-portrait.jpg")
    notify("person", person.pk, "portrait")
    assert not page.dependencies.filter(stale=True).exists()
    m.Person.objects.filter(pk=person.pk).update(biography="人工修订后的简介")
    notify("person", person.pk, "biography")
    assert set(str(v) for v in page.dependencies.filter(stale=True).values_list("block_id", flat=True)) == {affected}
    current = next(b for b in page_content(page)[0] if b["id"] == unaffected)
    apply_page_patch({"page_id": str(page.pk), "operation": "replace", "block_id": unaffected,
        "base_hash": digest(current), "block": {**current, "text": "只修改另一段"}, "human_edited": True},
        admin_user, request_key=str(uuid4()))
    assert page.dependencies.get(block_id=affected).stale
    assert not page.dependencies.get(block_id=unaffected).stale
    assert not m.CurationRun.objects.exists()


@pytest.mark.django_db
def test_backlinks_directory_permissions_and_page_local_invalidation(admin_user, reader_user, api_client):
    source_page = m.KnowledgePage.objects.create(slug="origin", title="被引用页")
    target = m.KnowledgePage.objects.create(slug="target", title="引用此页")
    block_id = add_block(target, {"type": "knowledge_page", "id": str(source_page.pk)}, admin_user)
    assert page_workspace(source_page, admin_user)["backlinks"] == [
        {"page_id": str(target.pk), "title": target.title, "block_id": block_id}]
    entity = m.Entity.objects.create(kind="concept", label="更新来源")
    add_block(source_page, {"type": "entity", "id": str(entity.pk)}, admin_user)
    assert target.dependencies.get(block_id=block_id).stale
    assert [p["id"] for p in page_directory(admin_user, state="stale")["pages"]] == [str(target.pk)]
    with pytest.raises(PermissionDenied):
        page_directory(reader_user)
    api_client.force_authenticate(reader_user)
    assert api_client.get("/api/knowledge/workspace/").status_code == 403
    assert api_client.get(f"/api/knowledge/pages/{source_page.pk}/workspace/").status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.get("/api/knowledge/workspace/").status_code == 200
    assert api_client.get(f"/api/knowledge/pages/{source_page.pk}/workspace/").data["backlinks"][0]["block_id"] == block_id


@pytest.mark.django_db
def test_single_reference_block_and_typed_topic_change_are_tracked(admin_user):
    person = m.Person.objects.create(preferred_name="单引用")
    topic = m.Topic.objects.create(name="议题", slug="test-topic", problem_statement="旧问题")
    entity = m.Entity.objects.create(kind="topic", label=topic.name, topic=topic)
    page = m.KnowledgePage.objects.create(slug="legacy-ref", title="旧组件引用")
    key = str(uuid4())
    apply_page_patch({"page_id": str(page.pk), "operation": "add", "block_id": key,
        "block": {"type": "person", "target": {"type": "person", "id": str(person.pk)}}},
        admin_user, request_key=str(uuid4()))
    topic_block = add_block(page, {"type": "entity", "id": str(entity.pk)}, admin_user)
    m.Person.objects.filter(pk=person.pk).update(biography="新资料")
    notify("person", person.pk, "biography")
    assert page.dependencies.get(block_id=key).stale
    m.Topic.objects.filter(pk=topic.pk).update(problem_statement="新问题")
    notify("topic", topic.pk, "problem_statement")
    assert page.dependencies.get(block_id=topic_block).stale


@pytest.mark.django_db
def test_backfill_retains_existing_stale_baselines(admin_user):
    from io import StringIO
    entity = m.Entity.objects.create(kind="concept", label="旧定义", definition="旧义")
    page = m.KnowledgePage.objects.create(slug="baseline", title="保留基准")
    key = add_block(page, {"type": "entity", "id": str(entity.pk)}, admin_user)
    baseline = page.dependencies.get(block_id=key).source_hash
    m.Entity.objects.filter(pk=entity.pk).update(definition="新义")
    notify("entity", entity.pk, "definition")
    call_command("backfill_knowledge_core", page_dependencies=True, batch_size=1, stdout=StringIO())
    row = page.dependencies.get(block_id=key)
    assert row.stale and row.source_hash == baseline
