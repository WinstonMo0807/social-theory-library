"""Exercise real editorial services on an isolated test DB, never the NAS."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

from catalog.models import Work, Edition, EditorialRevision, CatalogFieldDecision
from catalog.services.workspace_edits import workspace_edit_version
from ingestion.models import AuditEvent, FieldLock

pytestmark = pytest.mark.django_db

spec = importlib.util.spec_from_file_location("stl_mcp_domain", Path(__file__).resolve().parents[2] / "tools/stl_mcp/domain.py")
domain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(domain)


def setup(admin_user):
    work = Work.objects.create(title="MCP合成测试作品", abstract="原正式简介")
    edition = Edition.objects.create(work=work, publication_mode="bibliographic")
    domain.CONFIG = {"actor_id": admin_user.pk, "token_version": admin_user.token_version, "allowed_work_ids": [str(work.pk)]}
    op = {"key": "summary", "kind": "editorial", "work_id": str(work.pk), "target_type": "work", "target_id": str(work.pk),
          "edition_id": str(edition.pk), "expected_version": workspace_edit_version(edition), "request_id": str(uuid4()), "data": {"abstract": "有来源的机器建议"}}
    return work, edition, op, EditorialRevision.objects.count()


def test_draft_only_and_durable_replay_after_reconnect(admin_user):
    work, edition, op, baseline = setup(admin_user)
    assert domain.prepare({"operations": [op]}, domain.actor())["ok"]
    result = domain.save({"operations": [op]}, domain.actor())
    assert result["ok"], result
    work.refresh_from_db()
    assert work.abstract == "原正式简介"
    revision = EditorialRevision.objects.get(target_type="work", target_id=work.pk)
    assert revision.status == "draft" and "未作人工确认" in revision.change_note
    assert not CatalogFieldDecision.objects.exists() and not FieldLock.objects.exists()
    assert domain.receipts({"operations": [op]}, domain.actor())["all_saved"]
    retry = domain.save({"operations": [deepcopy(op)]}, domain.actor())
    assert retry["ok"] and retry["results"][0]["replayed"]
    assert EditorialRevision.objects.count() == baseline + 1
    assert AuditEvent.objects.get(action="mcp.draft.saved").before["human_reviewed"] is False


def test_partial_save_stale_version_and_only_original_request_replays(admin_user):
    work, edition, op, baseline = setup(admin_user)
    stale = {**op, "key": "title", "request_id": str(uuid4()), "data": {"subtitle": "不得覆盖"}}
    result = domain.save({"operations": [op, stale]}, domain.actor())
    assert not result["ok"] and result["state"] == "partial"
    assert result["results"][0]["ok"] and not result["results"][1]["ok"]
    tampered = {**op, "data": {"abstract": "不同载荷"}}
    replay = domain.save({"operations": [tampered]}, domain.actor())
    assert not replay["ok"] and EditorialRevision.objects.count() == baseline + 1


def test_reject_lock_other_editor_and_revoked_identity(admin_user, reader_user):
    work, edition, op, baseline = setup(admin_user)
    FieldLock.objects.create(edition=edition, field_name="abstract", locked_by=admin_user, locked_value=work.abstract)
    op["expected_version"] = workspace_edit_version(edition)
    assert not domain.save({"operations": [op]}, domain.actor())["ok"]
    assert EditorialRevision.objects.count() == baseline
    admin_user.token_version += 1
    admin_user.save(update_fields=["token_version"])
    with pytest.raises(PermissionError):
        domain.actor()


@pytest.mark.parametrize("field", ["status", "published_at", "confirm_sections", "field_locks", "approved", "actor"])
def test_forbidden_commands_and_out_of_scope_writes(admin_user, field):
    work, edition, op, baseline = setup(admin_user)
    op["data"][field] = "published"
    assert not domain.prepare({"operations": [op]}, domain.actor())["ok"]
    assert not domain.save({"operations": [op]}, domain.actor())["ok"]
    domain.CONFIG["allowed_work_ids"] = []
    with pytest.raises(PermissionError):
        domain.scope(str(work.pk))
    assert EditorialRevision.objects.count() == baseline


def test_collection_replacement_cannot_drop_existing_identity():
    with pytest.raises(ValueError):
        domain.preserve_collections({"contributors": [{"person_id": "a", "role": "author"}]}, {"contributors": [{"person_id": "b", "role": "translator"}]})
    domain.preserve_collections({"contributors": [{"person_id": "a", "role": "author"}]}, {"contributors": [{"person_id": "a", "role": "author"}, {"person_id": "b", "role": "translator"}]})


def test_reader_identity_and_unrelated_target_are_rejected(admin_user, reader_user):
    work, edition, op, baseline = setup(admin_user)
    domain.CONFIG["actor_id"] = reader_user.pk
    domain.CONFIG["token_version"] = reader_user.token_version
    with pytest.raises(PermissionError):
        domain.actor()
    domain.CONFIG["actor_id"] = admin_user.pk
    domain.CONFIG["token_version"] = admin_user.token_version
    other = Work.objects.create(title="不可修改的另一本书")
    op["target_id"] = str(other.pk)
    assert not domain.save({"operations": [op]}, domain.actor())["ok"]
    other.refresh_from_db()
    assert other.abstract == "" and EditorialRevision.objects.count() == baseline


def test_other_editors_pending_draft_is_not_absorbed(admin_user, reader_user):
    from catalog.services.editorial_revision import create_editorial_revision
    work, edition, op, baseline = setup(admin_user)
    create_editorial_revision(target_type="work", target_id=work.pk, patch={"abstract": "其他编辑者的稿件"}, actor=reader_user, idempotency_key=str(uuid4()))
    op["expected_version"] = workspace_edit_version(edition)
    assert not domain.save({"operations": [op]}, domain.actor())["ok"]
    assert EditorialRevision.objects.count() == baseline + 1


def test_new_concept_uses_original_serializer_and_stays_draft(admin_user):
    from catalog.models import KnowledgeNode
    work, edition, op, baseline = setup(admin_user)
    op.update(kind="node_create", data={"canonical_name_zh": "MCP合成概念", "slug": "mcp-synthetic-concept", "node_type": "concept", "summary": "仅用于隔离检查"})
    prepared = domain.prepare({"operations": [op]}, domain.actor())
    assert prepared["ok"], prepared
    result = domain.save({"operations": [op]}, domain.actor())
    assert result["ok"], result
    node = KnowledgeNode.objects.get(pk=result["results"][0]["result"]["id"])
    assert node.status == "draft" and node.published_at is None


def test_uuid_in_prose_cannot_expand_write_scope(admin_user):
    from catalog.models import Topic
    from catalog.editorial_read import current_editorial_version
    work, edition, op, baseline = setup(admin_user)
    topic = Topic.objects.create(name="无关主题", slug="mcp-unrelated-topic")
    op["data"] = {"abstract": "引用一个编号并不能授权修改：" + str(topic.pk)}
    assert domain.save({"operations": [op]}, domain.actor())["ok"]
    unrelated = {**op, "key": "unrelated", "request_id": str(uuid4()), "target_type": "topic", "target_id": str(topic.pk),
                 "expected_version": current_editorial_version("topic", topic.pk), "data": {"description": "越界改动"}}
    assert not domain.save({"operations": [unrelated]}, domain.actor())["ok"]
    topic.refresh_from_db()
    assert topic.description == ""


def test_dependent_new_object_uses_creation_version_receipt(admin_user):
    from catalog.models import KnowledgeNode
    work, edition, op, baseline = setup(admin_user)
    op.update(key="create", kind="node_create", data={"canonical_name_zh": "MCP依赖概念", "slug": "mcp-dependent-concept", "node_type": "concept"})
    follow = {"key": "describe", "kind": "editorial", "work_id": str(work.pk), "target_type": "knowledge_node",
              "target_id": {"$ref": "create", "path": "entity.id"}, "expected_version": "$after_create", "depends_on": ["create"],
              "request_id": str(uuid4()), "data": {"summary": "附加待核说明"}}
    result = domain.save({"operations": [op, follow]}, domain.actor())
    assert result["ok"], result
    retry = domain.save({"operations": [op, follow]}, domain.actor())
    assert retry["ok"] and all(row["replayed"] for row in retry["results"])
    assert KnowledgeNode.objects.filter(canonical_name_zh="MCP依赖概念").count() == 1


@pytest.mark.parametrize("change", ["stale_span", "changed_text", "changed_file"])
def test_invalid_source_cannot_be_saved_as_evidence(admin_user, change):
    from catalog.models import Asset, Page, DocumentRevision, EvidenceSpan, Topic, WorkTopicRelation, EvidenceCuration
    work, edition, op, baseline = setup(admin_user)
    asset = Asset.objects.create(edition=edition, kind="normalized", file="mcp-synthetic.pdf", is_current=True,
        status="ready", validation_status="valid", access_status="registered", sha256="a" * 64, page_count=1)
    page = Page.objects.create(asset=asset, index=1, text="准确原文")
    revision = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum=asset.sha256, text_checksum="b" * 64)
    span = EvidenceSpan.objects.create(page=page, document_revision=revision, page_number=1, start_offset=0, end_offset=4,
        original_text="准确原文", content_hash="c" * 64)
    topic = Topic.objects.create(name="合成来源主题", slug="mcp-source-topic")
    WorkTopicRelation.objects.create(work=work, topic=topic)
    if change == "stale_span":
        span.is_stale = True
        span.save(update_fields=["is_stale"])
    elif change == "changed_text":
        page.text = "已经变化"
        page.save(update_fields=["text"])
    else:
        asset.sha256 = "d" * 64
        asset.save(update_fields=["sha256"])
    op.update(kind="evidence_curation", target_type="topic", target_id=str(topic.pk), expected_version="0",
              data={"items": [{"source_type": "span", "source_id": str(span.pk), "reason": "不能保存旧原文"}]})
    result = domain.save({"operations": [op]}, domain.actor())
    assert not result["ok"] and "来源的当前修订或原文定位已失效" in result["results"][0]["detail"]
    assert not EvidenceCuration.objects.filter(object_id=topic.pk).exists()


def test_source_read_rejects_revision_file_hash_mismatch(admin_user):
    from catalog.models import Asset, DocumentRevision
    work, edition, op, baseline = setup(admin_user)
    asset = Asset.objects.create(edition=edition, kind="normalized", file="mcp-hash.pdf", is_current=True,
        status="ready", validation_status="valid", access_status="registered", sha256="d" * 64)
    DocumentRevision.objects.create(asset=asset, revision=1, source_checksum="a" * 64, text_checksum="b" * 64)
    with pytest.raises(ValueError, match="哈希不一致"):
        domain.sources({"requests": [{"edition_id": str(edition.pk), "pages": [1]}]}, domain.actor())


def test_person_lookup_tolerates_middle_initial_without_confirming_identity(admin_user):
    from catalog.models import Person
    person = Person.objects.create(preferred_name="詹姆斯·C.斯科特", original_name="James C. Scott")
    result = domain.resolve({"queries": [{"kind": "person", "query": "詹姆斯·斯科特"}]}, admin_user)
    assert str(person.pk) in [row["id"] for row in result["queries"][0]["results"]]
    assert result["queries"][0]["identity_decision"] == "unreviewed"
    assert not result["queries"][0]["results"][0]["exact_label"]


def test_keyword_lookup_does_not_duplicate_matching_span_as_full_pages(admin_user):
    from catalog.models import Asset, Page, DocumentRevision, EvidenceSpan
    work, edition, op, baseline = setup(admin_user)
    asset = Asset.objects.create(edition=edition, kind="normalized", file="mcp-keyword.pdf", is_current=True,
        status="ready", validation_status="valid", access_status="registered", sha256="a" * 64, page_count=1)
    page = Page.objects.create(asset=asset, index=1, text="准确原文")
    revision = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum=asset.sha256, text_checksum="b" * 64)
    span = EvidenceSpan.objects.create(page=page, document_revision=revision, page_number=1, start_offset=0, end_offset=4,
        original_text="准确原文", content_hash="c" * 64)
    result = domain.sources({"requests": [{"edition_id": str(edition.pk), "query": "原文"}]}, admin_user)
    assert result["ok"] and result["requests"][0]["results"][0]["span_id"] == str(span.pk)
    assert result["requests"][0]["pages"] == []
