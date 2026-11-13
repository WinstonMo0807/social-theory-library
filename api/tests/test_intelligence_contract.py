"""Service/transport regressions; deterministic fixtures do not claim model analysis."""
from dataclasses import replace
from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError, PermissionDenied
from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services import intelligence_changes as changes
from catalog.services.knowledge_sources import snapshot_revision, digest
from catalog.services.knowledge_core import apply_page_patch, page_content


def proposals():
    return [{"id": str(uuid4()), "kind": "entity", "payload": {"kind": "person", "label": "同名人物"}, "dependencies": []}]


@pytest.mark.django_db
def test_review_and_idempotent_application(source, admin_user, reader_user):
    items = proposals()
    key = uuid4()
    c = changes.submit_draft(source, items, admin_user, request_id=key)
    assert not m.Entity.objects.exists()
    assert changes.submit_draft(source, items, admin_user, request_id=key).pk == c.pk
    with pytest.raises(PermissionDenied):
        changes.review(c.pk, [{"id": items[0]["id"], "decision": "accepted"}], reader_user, expected_version=1)
    c = changes.review(c.pk, [{"id": items[0]["id"], "decision": "accepted"}], admin_user, expected_version=1)
    save = uuid4()
    first = changes.apply(c.pk, [items[0]["id"]], admin_user, request_id=save, expected_version=c.version)
    second = changes.apply(c.pk, [items[0]["id"]], admin_user, request_id=save, expected_version=c.version)
    assert first == second
    assert len(first["saved"]) == m.Entity.objects.count() == 1
    assert m.Entity.objects.get().status == "draft"


@pytest.mark.django_db
def test_bad_dependency_group_rolls_back_without_losing_other_decisions(source, admin_user):
    snapshot_revision(source)
    entity, independent = proposals()[0], proposals()[0]
    independent["payload"]["context"] = "另一个来源语境"
    invalid = {"id": str(uuid4()), "kind": "assertion", "dependencies": [entity["id"]], "payload": {
        "text": "错误引文", "participants": [{"role": "subject", "entity_id": {"change_item": entity["id"]}}],
        "evidence": [{"stance": "supports", "segments": [{"page_number": 1, "start": 0, "end": 2, "exact": "伪造"}]}]}}
    items = [entity, invalid, independent]
    c = changes.submit_draft(source, items, admin_user, request_id=uuid4())
    c = changes.review(c.pk, [{"id": i["id"], "decision": "accepted"} for i in items], admin_user, expected_version=1)
    result = changes.apply(c.pk, [i["id"] for i in items], admin_user, request_id=uuid4(), expected_version=c.version)
    assert set(result["saved"]) == {independent["id"]}
    assert len(result["blocked"]) == 2
    assert m.Entity.objects.count() == 1
    assert m.Assertion.objects.count() == 0
    assert c.items.filter(decision="accepted").count() == 3


@pytest.mark.django_db
def test_rejected_same_source_not_resubmitted(source, admin_user):
    items = proposals()
    c = changes.submit_draft(source, items, admin_user, request_id=uuid4())
    changes.review(c.pk, [{"id": items[0]["id"], "decision": "rejected", "note": "不同人物"}], admin_user, expected_version=1)
    items[0]["id"] = str(uuid4())
    second = changes.submit_draft(source, items, admin_user, request_id=uuid4())
    assert second.items.get().decision == "rejected"


@pytest.mark.django_db
def test_old_patch_conflicts_after_human_change(source, admin_user):
    page = m.KnowledgePage.objects.create(work=source.asset.edition.work, slug="fixture", title="测试")
    entity = m.Entity.objects.create(kind="concept", label="测试概念")
    block_id = str(uuid4())
    block = {"id": block_id, "type": "analysis", "text": "第一稿", "references": [{"type": "entity", "id": str(entity.pk)}]}
    apply_page_patch({"page_id": str(page.pk), "operation": "add", "block_id": block_id, "block": block}, admin_user, request_key="first")
    original = page_content(page)[0][0]
    from catalog.services.editorial_revision import create_editorial_revision
    create_editorial_revision(target_type="knowledge_page", target_id=page.pk,
        patch={"body_blocks": [{**original, "text": "人工修改", "human_edited": True}]}, actor=admin_user, idempotency_key="human")
    with pytest.raises(ValidationError):
        apply_page_patch({"page_id": str(page.pk), "operation": "replace", "block_id": block_id,
            "base_hash": digest(original), "block": block}, admin_user, request_key="stale")
    assert page_content(page)[0][0]["text"] == "人工修改"


@pytest.mark.django_db
@pytest.mark.parametrize("reason,target", [("human", "page"), ("stale", "work"), ("human", "candidate_entity")])
def test_local_block_conflict_does_not_roll_back_shared_source_dependencies(source, admin_user, reason, target):
    snapshot_revision(source)
    existing = m.Entity.objects.create(kind="concept", label="已有概念")
    page = m.KnowledgePage.objects.create(slug="shared-review", title="已有正文",
        **({"entity": existing} if target == "candidate_entity" else {"work": source.asset.edition.work}))
    block_id = str(uuid4())
    apply_page_patch({"page_id": str(page.pk), "operation": "add", "block_id": block_id,
        "block": {"type": "analysis", "text": "人工正文", "references": [{"type": "entity", "id": str(existing.pk)}]}},
        admin_user, request_key="human-source", origin="human")
    original = page_content(page)[0][0]
    entity = proposals()[0]
    if target == "candidate_entity":
        entity["payload"] = {"kind": "concept", "label": existing.label, "existing_id": str(existing.pk)}
    assertion = {"id": str(uuid4()), "kind": "assertion", "payload": {"text": "测试原文陈述",
        "participants": [{"role": "subject", "entity_id": {"change_item": entity["id"]}}],
        "evidence": [{"stance": "supports", "segments": [{"page_number": 2, "start": 0, "end": 6, "exact": "跨页引文后半"}]}]}}
    destination = {"page_id": str(page.pk)} if target == "page" else {"work_id": str(source.asset.edition.work_id)} if target == "work" else {"entity_id": {"change_item": entity["id"]}}
    proposed = {"type": "analysis", "text": "有来源的新增正文", "references": [{"type": "assertion", "id": {"change_item": assertion["id"]}}]}
    stale = {"id": str(uuid4()), "kind": "wiki_patch", "payload": {**destination, "operation": "replace",
        "block_id": block_id, "base_hash": digest(original) if reason == "human" else "old-hash", "block": proposed}}
    sibling = {"id": str(uuid4()), "kind": "wiki_patch", "payload": {**destination, "operation": "add", "block_id": str(uuid4()), "block": proposed}}
    dependent = {"id": str(uuid4()), "kind": "wiki_patch", "dependencies": [stale["id"]],
        "payload": {**destination, "operation": "add", "block_id": str(uuid4()), "block": {**proposed, "text": "依赖冲突区块的下一段"}}}
    items = [entity, assertion, stale, sibling, dependent]
    changeset = changes.submit_draft(source, items, admin_user, request_id=uuid4())
    changeset = changes.review(changeset.pk, [{"id": item["id"], "decision": "accepted"} for item in items], admin_user, expected_version=1)
    request = uuid4()
    result = changes.apply(changeset.pk, [i["id"] for i in items], admin_user, request_id=request, expected_version=changeset.version)
    assert set(result["saved"]) == {entity["id"], assertion["id"], sibling["id"]}
    assert set(result["blocked"]) == {stale["id"], dependent["id"]}
    assert result["blocked"][stale["id"]]["block_id"] == block_id
    assert result["blocked"][dependent["id"]]["dependencies"] == [stale["id"]]
    assert original in page_content(page)[0] and len(page_content(page)[0]) == 2
    assert changeset.items.filter(decision="accepted").count() == len(items)
    assert m.Assertion.objects.get().status == "draft"
    assert changes.apply(changeset.pk, [i["id"] for i in items], admin_user, request_id=request, expected_version=changeset.version) == result


def test_installed_docetl_operator_delegates_once_without_truncation(monkeypatch, settings):
    pytest.importorskip("docetl")
    from ingestion.services.ai_client import AIClient, AIConfiguration, AIResult
    from catalog.services.intelligence_provider import map_analysis
    config = AIConfiguration(provider="openai_compatible", base_url="http://127.0.0.1:1/v1", api_key="", metadata_model="fixture",
        classifier_model="", vision_model="", timeout=5, max_concurrency=1, max_input_chars=16000, allowed_hosts=("127.0.0.1",), model="fixture")
    calls = []
    def transport(self, **kwargs):
        calls.append(kwargs)
        return AIResult({"summary": "contract only"}, config.provider, config.model, "fixture", 1, 1)
    monkeypatch.setattr(AIClient, "generate_json", transport)
    data = "开头" + "中间" * 1000 + "结尾"
    result = map_analysis(config, "分析", data, {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]})
    assert result.data["summary"] == "contract only"
    assert len(calls) == 1 and calls[0]["strict"] is True
    assert data in calls[0]["document_text"]


def test_mcp_official_version_registers_only_bounded_tools():
    pytest.importorskip("mcp")
    import asyncio
    from catalog.services.knowledge_mcp import build_server
    tools = asyncio.run(build_server(1).list_tools())
    names = {tool.name for tool in tools}
    assert {"catalog_search", "knowledge_search", "original_search", "source_context", "create_run", "run_status", "submit_draft"} <= names
    assert not any(word in name for name in names for word in ("publish", "apply", "credential", "lease"))


@pytest.mark.django_db(transaction=True)
def test_mcp_permission_failure_keeps_actionable_business_error(source, reader_user):
    pytest.importorskip("mcp")
    import asyncio
    from mcp.server.mcpserver.exceptions import ToolError
    from catalog.services.knowledge_mcp import build_server
    with pytest.raises(ToolError, match="403: 当前账户不能编辑知识草稿"):
        asyncio.run(build_server(reader_user.pk).call_tool("submit_draft", {
            "document_revision_id": str(source.pk), "request_id": str(uuid4()), "items": proposals()}))


@pytest.mark.django_db
def test_console_provider_uses_encrypted_existing_service(superadmin_user, settings, monkeypatch):
    from io import StringIO
    from django.core.management import call_command
    from cryptography.fernet import Fernet
    from common.ai_runtime import current_profile_document
    from catalog.services.provider_secrets import resolve_provider_secret
    settings.PRIVATE_DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda _: "fixture-only-secret")
    monkeypatch.setattr("common.ai_endpoints.public_endpoint", lambda value: (value, ["93.184.216.34"]))
    out = StringIO()
    call_command("configure_intelligence_provider", actor=superadmin_user.username,
        base_url="https://example.test/v1", model="fixture-model", stdout=out)
    profile = next(p for p in current_profile_document()["profiles"] if p["capability"] == "curation_reasoning")
    assert profile["model"] == "fixture-model" and profile["enabled"] is False
    assert resolve_provider_secret(profile["credential_alias"]) == "fixture-only-secret"
    assert "fixture-only-secret" not in out.getvalue()
