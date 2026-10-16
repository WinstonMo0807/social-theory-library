"""Private research boundaries and recovery. Written before the unified acceptance run."""
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from accounts.models import User
from catalog.models import EvidencePack
from reading import research
from reading.citation_audit import create_audit, original_document, parse_manuscript, process_audit, update_audit
from reading.models import CitationAudit, ResearchMemory, ResearchProject, ResearchTurn
from reading.services import decrypt_private_text
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def project_for(user):
    return research.create_project(user, {"request_id": str(uuid4()), "title": "私人问题"})


def test_owner_boundary_including_staff_and_idempotent_create(api_client, reader_user, admin_user):
    request_id = str(uuid4())
    api_client.force_authenticate(reader_user)
    body = {"request_id": request_id, "title": "本人研究", "user": str(admin_user.id)}
    first = api_client.post("/api/reading/research-projects/", body, format="json")
    duplicate = api_client.post("/api/reading/research-projects/", body, format="json")
    assert first.status_code == duplicate.status_code == 201
    assert first.data["id"] == duplicate.data["id"]
    changed = api_client.post("/api/reading/research-projects/", {**body, "title": "另一问题"}, format="json")
    assert changed.status_code == 409
    stored = ResearchProject.objects.get(pk=first.data["id"])
    assert stored.user_id == reader_user.id
    assert b"\xe6\x9c\xac\xe4\xba\xba" not in bytes(stored.data_ciphertext)
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/research-projects/{stored.id}/").status_code == 404
    assert api_client.delete(f"/api/reading/research-projects/{stored.id}/").status_code == 404


def test_optimistic_revision_and_empty_scope_do_not_overwrite(reader_user):
    project = project_for(reader_user)
    research.update_project(reader_user, project.id, {"expected_revision": 1, "notes": "已保存的认识"})
    with pytest.raises(research.ResearchConflict):
        research.update_project(reader_user, project.id, {"expected_revision": 1, "notes": "过期的窗口"})
    project.refresh_from_db()
    assert research.unpack(project)["notes"] == "已保存的认识"
    with pytest.raises(ValidationError):
        research.scope_snapshot({"kind": "passages", "references": []}, reader_user)
    with pytest.raises(ValidationError):
        research.scope_snapshot({"allow_neighbors": "false"}, reader_user)


def test_multianchor_revision_and_withdrawal_revalidation(reader_user):
    edition, asset, spans, _ = fixture_source(count=2)
    raw = {"anchors": [{"evidence_span_id": str(span.id)} for span in spans]}
    ref = research.resolve_reference(raw, reader_user, strict=True)
    assert [anchor["pdf_page"] for anchor in ref["anchors"]] == [1, 2]
    assert ref["anchors"][0]["bbox_unit"] == "source_page_coordinates"
    compact = research.compact_reference(ref)
    edition.active_catalog_revision.fulltext_ready = False
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    stale = research.resolve_reference(compact, reader_user)
    assert stale["source_status"] == "unavailable"
    assert not stale["quote"]
    assert all("quote" not in row for row in stale["anchors"])


def test_selection_undo_restores_order_without_duplicate(reader_user):
    _, _, spans, _ = fixture_source(count=3)
    project = project_for(reader_user)
    project = research.change_selection(reader_user, project.id, {"expected_revision": 1, "action": "add",
        "references": [{"evidence_span_id": str(span.id)} for span in spans]})
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision, "action": "remove",
        "reference_id": str(spans[1].id)})
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision, "action": "undo"})
    assert [row["evidence_span_id"] for row in research.unpack(project)["selections"]] == [str(span.id) for span in spans]


def test_limited_turn_never_creates_a_discovery_or_public_pack(reader_user, monkeypatch):
    from catalog.discovery_models import DiscoverySearchSession
    from reading.tasks import collect_research_turn
    _, _, spans, _ = fixture_source(count=1)
    project = project_for(reader_user)
    before_packs, before_sessions = EvidencePack.objects.count(), DiscoverySearchSession.objects.count()
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: None)
    turn = research.start_turn(SimpleNamespace(user=reader_user), project.id, {
        "request_id": str(uuid4()), "expected_revision": project.revision, "question": "这段原文的限定是什么",
        "scope": {"kind": "passages", "references": [{"evidence_span_id": str(spans[0].id)}]}})
    collect_research_turn(str(turn.id), turn.generation, turn.task_id)
    turn.refresh_from_db()
    assert turn.status == "completed"
    assert len(research.unpack(turn)["result_refs"]) == 1
    assert EvidencePack.objects.count() == before_packs
    assert DiscoverySearchSession.objects.count() == before_sessions


def test_cancel_rejects_late_worker(reader_user):
    from reading.tasks import collect_research_turn
    project = project_for(reader_user)
    turn = ResearchTurn.objects.create(project=project, data_ciphertext=research.pack({"question": "私有问题"}))
    generation = turn.generation
    research.cancel_turn(reader_user, turn.id)
    collect_research_turn(str(turn.id), generation, turn.task_id)
    turn.refresh_from_db()
    assert turn.status == "canceled"
    assert research.unpack(turn) == {"question": "私有问题"}


def test_memory_revisions_owner_search_and_forget(reader_user, admin_user):
    request_id = str(uuid4())
    memory = research.create_memory(reader_user, {"request_id": request_id, "body": "制度与社会关系"})
    assert research.create_memory(reader_user, {"request_id": request_id, "body": "制度与社会关系"}).id == memory.id
    with pytest.raises(research.ResearchConflict):
        research.create_memory(reader_user, {"request_id": request_id, "body": "不同内容"})
    memory.embedding_ciphertext = research.pack([1, 0])
    memory.embedding_artifact = "old"
    memory.save(update_fields=["embedding_ciphertext", "embedding_artifact"])
    memory = research.update_memory(reader_user, memory.id, {"expected_revision": 1, "body": "制度嵌入社会关系", "state": "confirmed"})
    assert not memory.embedding_ciphertext and not memory.embedding_artifact
    assert research.unpack(memory)["history"][0]["data"]["body"] == "制度与社会关系"
    assert research.search_memories(admin_user, "制度", allowed_ids=[str(memory.id)])["results"] == []
    assert len(research.search_memories(reader_user, "制度")["results"]) == 1
    memory.delete()
    assert research.search_memories(reader_user, "制度")["results"] == []


def test_rules_are_never_marked_confirmed_counterevidence(reader_user):
    _, _, spans, _ = fixture_source(count=1)
    result = research.analyze_references({"proposition": "制度决定社会行动"}, [{"evidence_span_id": str(spans[0].id)}], reader_user)
    assert result[0]["relation"] == "insufficient_evidence"
    assert result[0]["status"] == "needs_review"
    assert result[0]["decision"] is None
    assert "confidence" not in result[0]["rule_signal"]


def test_plan_preserves_personal_completion_and_public_source(reader_user):
    _, _, spans, _ = fixture_source(count=1)
    body = {"request_id": str(uuid4()), "goal": "理解制度与行动", "references": [{"evidence_span_id": str(spans[0].id)}]}
    plan = research.generate_plan(reader_user, body)
    assert research.generate_plan(reader_user, body).id == plan.id
    item = research.unpack(plan)["items"][0]
    plan = research.update_plan(reader_user, plan.id, {"expected_revision": plan.revision, "item_id": item["id"], "status": "completed"})
    with pytest.raises(research.ResearchConflict):
        research.update_plan(reader_user, plan.id, {"expected_revision": plan.revision, "item_id": item["id"],
            "reference": {"evidence_span_id": str(spans[0].id)}})
    plan.refresh_from_db()
    assert research.unpack(plan)["items"][0]["status"] == "completed"


def test_plan_rejects_a_cycle_with_source_bound_dependencies(reader_user):
    edition, _, spans, _ = fixture_source(count=1)
    reference = {"evidence_span_id": str(spans[0].id)}
    with pytest.raises(ValidationError, match="先修关系有环"):
        research.generate_plan(reader_user, {"request_id": str(uuid4()), "goal": "学习依赖", "references": [reference],
            "prerequisites": [{"work_id": str(edition.work_id), "requires_work_id": str(edition.work_id), "reference": reference}]})


def docx_bytes():
    from docx import Document
    from docx.oxml import OxmlElement
    document = Document()
    paragraph = document.add_paragraph('这项研究指出，“制度始终嵌入具体的社会关系”。[1]')
    run = paragraph.add_run()
    field = OxmlElement("w:instrText")
    field.text = ' ADDIN ZOTERO_ITEM CSL_CITATION {"citationItems":[{"itemData":{"title":"制度研究","DOI":"10.1234/example"}}]}'
    run._r.append(field)
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "表格中的引文（作者，2020）"
    document.add_paragraph("参考文献")
    document.add_paragraph("[1] 作者. 制度研究. 2020. DOI:10.1234/example")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def test_docx_locations_fields_and_original_are_preserved():
    blob = docx_bytes()
    parsed = parse_manuscript(blob, "docx")
    assert parsed["occurrences"]
    assert any(row.get("citation_field", "").startswith(" ADDIN ZOTERO") for row in parsed["occurrences"])
    assert any(row["quote"] == "制度始终嵌入具体的社会关系" for row in parsed["occurrences"])
    assert all(row["location"]["pdf_page"] is None for row in parsed["occurrences"])
    assert all(row["location"]["part"] == "word/document.xml" for row in parsed["occurrences"])
    assert any("2020" in row["raw"] for row in parsed["bibliography"])
    assert len(blob) > 0


def test_footnote_after_body_bibliography_and_split_field_are_not_lost():
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    document = Document()
    paragraph = document.add_paragraph('“制度始终嵌入具体的社会关系”。')
    reference = OxmlElement("w:footnoteReference")
    reference.set(qn("w:id"), "1")
    paragraph.add_run()._r.append(reference)
    field_paragraph = document.add_paragraph("另见")
    for marker, value in [
        ("begin", ""), ("instruction", ' ADDIN ZOTERO_ITEM CSL_CITATION {"citationItems":['),
        ("instruction", '{"itemData":{"title":"制度研究","DOI":"10.1234/example"}}]}'),
        ("separate", ""), ("text", "[1]"), ("end", ""),
    ]:
        run = field_paragraph.add_run()
        element = OxmlElement("w:instrText" if marker == "instruction" else "w:t" if marker == "text" else "w:fldChar")
        if marker in {"begin", "separate", "end"}:
            element.set(qn("w:fldCharType"), marker)
        else:
            element.text = value
        run._r.append(element)
    document.add_paragraph("参考文献")
    document.add_paragraph("[1] 作者. 制度研究. 2020. DOI:10.1234/example")
    original = BytesIO()
    document.save(original)
    output = BytesIO()
    with ZipFile(BytesIO(original.getvalue())) as before, ZipFile(output, "w") as after:
        for member in before.infolist():
            after.writestr(member, before.read(member.filename))
        after.writestr("word/footnotes.xml", '''<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:footnote w:id="1"><w:p><w:r><w:t>作者，《制度研究》，2020，DOI:10.1234/example</w:t></w:r></w:p><w:p><w:r><w:t>进一步讨论（作者，2020）</w:t></w:r></w:p></w:footnote></w:footnotes>''')
    result = parse_manuscript(output.getvalue(), "docx")
    footnote = next(row for row in result["occurrences"] if row.get("note_reference"))
    assert footnote["entry_ids"] and footnote["quote"]
    assert "footnoteReference" in footnote["location"]["xml_node"]
    assert footnote["location"]["start"] == footnote["location"]["end"]
    assert any(row["location"]["part"] == "word/footnotes.xml" for row in result["occurrences"])
    field_occurrences = [row for row in result["occurrences"] if row.get("citation_field")]
    assert len(field_occurrences) == 1 and field_occurrences[0]["entry_ids"]
    assert not any(row["raw"] == "[1]" for row in result["occurrences"])


def test_audit_encrypted_original_owner_only_and_unknown_match(reader_user, admin_user, api_client, monkeypatch):
    blob = docx_bytes()
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    audit = create_audit(reader_user, SimpleUploadedFile("稿件.docx", blob), {"request_id": str(uuid4())})
    assert original_document(audit) == blob
    assert bytes(audit.original_ciphertext) != blob
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    assert audit.status == "partial"
    assert all(entry["identity_status"] == "not_matched_in_library" for entry in research.unpack(audit)["bibliography"])
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/citation-audits/{audit.id}/original/").status_code == 404


def test_private_analysis_rejects_remote_configuration_before_network(monkeypatch):
    from ingestion.services.ai_client import AIServiceUnavailable
    from reading.local_analysis import generate_local
    monkeypatch.setattr("reading.local_analysis.current_ai_configuration", lambda capability: SimpleNamespace(
        enabled=True, base_url="https://api.external.example", max_input_chars=1000))
    with pytest.raises(AIServiceUnavailable):
        generate_local(capability="claim_stance", task="test", prompt="test", payload={"private": "text"}, schema={})


@pytest.mark.parametrize("endpoint,allowed_name", [
    ("https://api.external.example", False),
    ("https://8.8.8.8", False),
    ("http://local-model.example", True),
])
def test_private_memory_embedding_rejects_remote_endpoint_before_sending_text(
    reader_user, settings, monkeypatch, endpoint, allowed_name,
):
    from urllib.parse import urlsplit
    memory = research.create_memory(reader_user, {"request_id": str(uuid4()), "body": "制度与私人认识"})
    research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision, "state": "confirmed"})
    host = urlsplit(endpoint).hostname
    settings.DISCOVERY_INFERENCE_URL = endpoint
    # Deliberately permissive public-service configuration must not authorize
    # sending decrypted private memories to a public address.
    settings.DISCOVERY_INFERENCE_ALLOWED_HOSTS = host
    if allowed_name:
        settings.RESEARCH_LOCAL_AI_HOSTS = [host]
        monkeypatch.setattr("reading.local_analysis.socket.getaddrinfo", lambda *args, **kwargs: [
            (2, 1, 6, "", ("8.8.8.8", 80))])
    else:
        settings.RESEARCH_LOCAL_AI_HOSTS = ["localhost"]
        monkeypatch.setattr("reading.local_analysis.socket.getaddrinfo", lambda *args, **kwargs: (
            _ for _ in ()).throw(AssertionError("Unapproved remote host must be rejected before DNS")))
    monkeypatch.setattr("catalog.services.discovery_inference.embed_texts", lambda *args, **kwargs: (
        _ for _ in ()).throw(AssertionError("Private text must not reach the embedding client")))

    result = research.search_memories(reader_user, "制度", semantic=True)

    assert result["mode"] == "local_lexical"
    assert result["warning"]
    assert len(result["results"]) == 1
    memory.refresh_from_db()
    assert not memory.embedding_ciphertext


@pytest.mark.parametrize("response_status", [200, 307])
def test_private_memory_embedding_ignores_proxy_environment_and_rejects_redirects(
    reader_user, settings, monkeypatch, response_status,
):
    import json as json_module
    from contextlib import contextmanager
    memory = research.create_memory(reader_user, {"request_id": str(uuid4()), "body": "制度与私人认识"})
    research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision, "state": "confirmed"})
    settings.DISCOVERY_INFERENCE_URL = "http://127.0.0.1:8091"
    settings.DISCOVERY_INFERENCE_ALLOWED_HOSTS = "127.0.0.1"
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(variable, "http://proxy.external.example:8080")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    calls, client_options = [], []

    class FakeResponse:
        status_code = response_status
        headers = {"Location": "https://redirect.external.example/collect-private-text"}

        def __init__(self, request_payload):
            self.payload = request_payload

        def iter_bytes(self):
            result = {"model": "fixture-local-model", "revision": "fixture-revision", "artifact_id": "fixture-artifact",
                "dimensions": 384, "vectors": [[1.0] + [0.0] * 383 for _ in self.payload["texts"]],
                "truncated": [False] * len(self.payload["texts"])}
            yield json_module.dumps(result).encode()

    class FakeClient:
        def __init__(self, **options):
            client_options.append(options)
            assert options["trust_env"] is False
            assert options["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def stream(self, method, url, *, json):
            calls.append((method, url, json))
            yield FakeResponse(json)

    # Exercise the actual catalog client contract without opening a socket.
    monkeypatch.setattr("catalog.services.discovery_inference.httpx.Client", FakeClient)
    result = research.search_memories(reader_user, "制度", semantic=True)

    assert client_options
    assert all(method == "POST" and url == "http://127.0.0.1:8091/embed" for method, url, _payload in calls)
    memory.refresh_from_db()
    if response_status == 200:
        assert result["mode"] == "local_semantic_owner_candidates"
        assert len(calls) == 2
        assert [payload["texts"] for _method, _url, payload in calls] == [["制度"], ["制度与私人认识"]]
        assert memory.embedding_ciphertext
    else:
        assert result["mode"] == "local_lexical"
        assert result["warning"]
        assert len(calls) == 1
        assert not memory.embedding_ciphertext


def test_cross_owner_turn_reference_is_not_imported(reader_user, admin_user, monkeypatch):
    from rest_framework.exceptions import NotFound
    project = project_for(reader_user)
    other = project_for(admin_user)
    parent = ResearchTurn.objects.create(project=other, status="completed", data_ciphertext=research.pack({"question": "他人的问题"}))
    with pytest.raises(NotFound):
        research.start_turn(SimpleNamespace(user=reader_user), project.id, {"request_id": str(uuid4()),
            "expected_revision": 1, "question": "窃取上一轮", "parent_id": str(parent.id)})
    assert project.turns.count() == 0


def test_scan_pdf_remains_unverified_instead_of_success():
    import fitz
    document = fitz.open()
    document.new_page()
    blob = document.tobytes()
    document.close()
    result = parse_manuscript(blob, "pdf")
    assert result["occurrences"] == []
    assert {warning["code"] for warning in result["warnings"]} >= {"text_unavailable", "no_citations_parsed"}


def test_delete_requires_revision_and_does_not_delete_source_conversation(api_client, reader_user):
    from reading.models import LibraryConversation
    conversation = LibraryConversation.objects.create(user=reader_user, title="原会话")
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "持续研究", "conversation_id": str(conversation.id)})
    api_client.force_authenticate(reader_user)
    assert api_client.delete(f"/api/reading/research-projects/{project.id}/", {"expected_revision": 99}, format="json").status_code == 409
    assert api_client.delete(f"/api/reading/research-projects/{project.id}/", {"expected_revision": 1}, format="json").status_code == 204
    assert LibraryConversation.objects.filter(pk=conversation.id).exists()


def test_canceled_before_parse_retries_all_and_duplicate_delivery_keeps_ids(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    audit = create_audit(reader_user, SimpleUploadedFile("稿件.docx", docx_bytes()), {"request_id": str(uuid4())})
    audit = update_audit(reader_user, audit.id, {"expected_revision": audit.revision, "action": "cancel"})
    audit = update_audit(reader_user, audit.id, {"expected_revision": audit.revision, "action": "retry"})
    assert research.unpack(audit)["rerun_occurrence_ids"] is None
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    identifiers = [row["id"] for row in research.unpack(audit)["occurrences"]]
    assert identifiers and audit.completed_units > 0
    revision = audit.revision
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    assert audit.revision == revision
    assert [row["id"] for row in research.unpack(audit)["occurrences"]] == identifiers


def test_cancel_resume_preserves_this_attempt_completed_units(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    audit = CitationAudit.objects.create(user=reader_user, status="running", generation=3, data_ciphertext=research.pack({
        "parsed": True, "bibliography": [], "occurrences": [{"id": "done", "checked_generation": 3}, {"id": "pending", "checked_generation": 2}],
        "rerun_occurrence_ids": ["done", "pending"]}))
    audit = update_audit(reader_user, audit.id, {"expected_revision": 1, "action": "cancel"})
    audit = update_audit(reader_user, audit.id, {"expected_revision": audit.revision, "action": "retry"})
    assert research.unpack(audit)["rerun_occurrence_ids"] == ["pending"]


def test_lost_running_worker_has_a_recoverable_terminal_state(reader_user):
    from datetime import timedelta
    from django.utils import timezone
    project = project_for(reader_user)
    turn = ResearchTurn.objects.create(project=project, status="running", data_ciphertext=research.pack({"question": "保留的问题"}))
    ResearchTurn.objects.filter(pk=turn.id).update(updated_at=timezone.now() - timedelta(minutes=31))
    turn.refresh_from_db()
    payload = research.serialize_record(turn, reader_user)
    assert payload["status"] == "failed" and payload["poll_after_ms"] is None
    assert payload["error_code"] == "task_timeout"
    assert payload["data"]["question"] == "保留的问题"


def test_ask_history_access_follows_current_viewer_without_deleting_quote(reader_user, admin_user):
    from reading.library_assistant import source_is_available
    from reading.library_serializers import LibraryMessageSourceDetailSerializer
    from reading.models import LibraryConversation, LibraryMessage, LibraryMessageSource
    from reading.services import encrypt_private_text
    edition, asset, spans, _ = fixture_source(count=1)
    conversation = LibraryConversation.objects.create(user=reader_user)
    message = LibraryMessage.objects.create(conversation=conversation, role="assistant")
    source = LibraryMessageSource.objects.create(message=message, source_key="S1", ordinal=1, work=edition.work,
        edition=edition, asset=asset, page=spans[0].page, title_snapshot="原来的来源", quote_ciphertext=encrypt_private_text("历史摘录"))
    asset.access_status = "private"
    asset.save(update_fields=["access_status"])
    source.refresh_from_db()
    assert not source_is_available(source, viewer=reader_user)
    assert source_is_available(source, viewer=admin_user)
    result = LibraryMessageSourceDetailSerializer(source, context={"request": SimpleNamespace(user=reader_user)}).data
    assert result["available"] is False and result["quote"] is None and result["reader_url"] is None
    assert decrypt_private_text(source.quote_ciphertext) == "历史摘录"


def test_ask_shared_discovery_keeps_large_scope_and_exact_file(monkeypatch):
    from reading.library_query import LibraryScope, ResolvedLibraryScope
    from reading.library_retrieval import _semantic_call
    work_ids = [str(uuid4()) for _ in range(65)]
    asset_id = str(uuid4())
    captured = {}
    def retrieve(query, channel, filters, allowed, **kwargs):
        captured.update(query=query, channel=channel, filters=filters, allowed=allowed)
        return {"rows": [], "warnings": [], "version": "generation", "index_uid": "discovery-index"}
    monkeypatch.setattr("reading.library_retrieval.retrieve_discovery_channel", retrieve)
    scope = ResolvedLibraryScope(scope=LibraryScope(context="works"), semantic_filters={
        "work_ids": work_ids, "_allowed_access_statuses": ["public", "registered"]}, asset_id=asset_id)
    result = _semantic_call("长问题" * 800, resolved_scope=scope, retrieval_profile="stable", limit=12, max_per_work=2)
    assert captured["filters"]["work_ids"] == work_ids
    assert captured["filters"]["_asset_id"] == asset_id
    assert captured["allowed"] == ["public", "registered"]
    assert captured["query"] == "长问题" * 800
    assert result["index_uid"] == "discovery-index"


def test_ask_deduplicates_discovery_windows_before_per_work_budget(monkeypatch):
    from reading.library_query import LibraryScope, ResolvedLibraryScope
    from reading.library_retrieval import _semantic_call
    first, second = str(uuid4()), str(uuid4())
    rows = [{"work_id": "one", "evidence_span_id": span, "text": value} for span, value in
            [(first, "第一段上半部"), (first, "第一段下半部"), (second, "第二段独立材料")]]
    monkeypatch.setattr("reading.library_retrieval.retrieve_discovery_channel", lambda *args, **kwargs: {
        "rows": rows, "warnings": [], "version": "v", "index_uid": "discovery-v"})
    result = _semantic_call("问题", resolved_scope=ResolvedLibraryScope(scope=LibraryScope(context="global"), semantic_filters={}),
                            retrieval_profile="stable", limit=8, max_per_work=2)
    assert [row["evidence_span_id"] for row in result["results"]] == [first, second]


def test_shared_discovery_revalidates_withdrawal_after_model_call(monkeypatch):
    from catalog.services.discovery_sessions import retrieve_discovery_channel
    edition, asset, spans, documents = fixture_source(count=1)
    monkeypatch.setattr("catalog.services.discovery_projection.discovery_candidates", lambda *args, **kwargs: {
        "sparse": [{"id": str(documents[0].id), "source_revision": documents[0].source_revision}], "dense": [],
        "warnings": [], "version": "test", "reranker_artifact": "test-model"})
    def rerank(query, rows, limit, artifact):
        asset.access_status = "private"
        asset.save(update_fields=["access_status"])
        return rows, []
    monkeypatch.setattr("catalog.services.discovery_sessions._rerank", rerank)
    result = retrieve_discovery_channel("问题", "passages", {}, ["public"])
    assert result["rows"] == []


def test_public_path_plan_does_not_follow_a_replaced_file(reader_user):
    from catalog.models import Asset, CatalogPublicationRevision, DocumentRevision, ReadingPath, ReadingPathItem
    edition, old_asset, _spans, _ = fixture_source(count=1)
    path = ReadingPath.objects.create(title="公共路径", slug="private-plan-path", status="published")
    ReadingPathItem.objects.create(reading_path=path, work=edition.work, stage_name="阅读")
    plan = research.generate_plan(reader_user, {"request_id": str(uuid4()), "goal": "版本核对", "reading_path_id": str(path.id)})
    old = edition.active_catalog_revision
    old.status = "superseded"
    old.save(update_fields=["status"])
    new_asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
        sha256="c" * 64, access_status="public")
    document = DocumentRevision.objects.create(asset=new_asset, revision=1, source_checksum="c" * 64, text_checksum="d" * 64)
    revision = CatalogPublicationRevision.objects.create(edition=edition, revision=2, status="active", metadata_ready=True,
        fulltext_ready=True, reader_asset=new_asset, document_revision=document, snapshot=old.snapshot, content_fingerprint="e" * 64)
    edition.active_catalog_revision = revision
    edition.save(update_fields=["active_catalog_revision"])
    result = research.serialize_record(plan, reader_user)
    assert result["data"]["items"][0]["available"] is False
    assert result["data"]["items"][0]["reader_url"] is None
    assert result["data"]["items"][0]["asset_id"] == str(old_asset.id)


def scanned_pdf_bytes(count=1):
    import fitz
    from PIL import Image
    raster = BytesIO()
    Image.new("RGB", (80, 100), "white").save(raster, format="PNG")
    with fitz.open() as document:
        for _ in range(count):
            page = document.new_page()
            page.insert_image(page.rect, stream=raster.getvalue())
        return document.tobytes()


def test_private_scan_checkpoint_token_resume_owner_and_original(reader_user, admin_user, api_client, settings, monkeypatch):
    from catalog.models import Asset
    settings.PADDLEOCR_SERVICE_URL = "http://127.0.0.1:8090"
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    calls = []
    def gateway(path, **options):
        assert path is None and options["pdf_bytes"].startswith(b"%PDF-")
        assert options["base_url"] == "http://127.0.0.1:8090"
        page = options["page_numbers"][0]
        calls.append(page)
        value = '“制度始终嵌入具体的社会关系”。[1]' if page < 5 else "参考文献\n[1] 作者. 制度研究. 2020."
        return {"pages": [{"index": page, "width": 600, "height": 800, "blocks": [{"text": value, "bbox": [1, 2, 20, 30]}]}]}
    monkeypatch.setattr("reading.private_ocr._request_document_gateway", gateway)
    blob = scanned_pdf_bytes(5)
    before = (Asset.objects.count(), EvidencePack.objects.count())
    audit = create_audit(reader_user, SimpleUploadedFile("私人扫描.pdf", blob), {"request_id": str(uuid4())})
    old_token = audit.task_id
    process_audit(audit.id, audit.generation, old_token)
    audit.refresh_from_db()
    assert audit.status == "queued" and audit.task_id != old_token
    assert calls == [1, 2, 3, 4]
    process_audit(audit.id, audit.generation, old_token)
    assert calls == [1, 2, 3, 4]
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    payload = research.unpack(audit)
    assert calls == [1, 2, 3, 4, 5]
    assert payload["parsed"] and len(payload["occurrences"]) == 4
    assert payload["ocr_units"]["pdf:1"]["quality_status"] == "ocr_unverified"
    assert original_document(audit) == blob
    assert (Asset.objects.count(), EvidencePack.objects.count()) == before
    assert "制度始终".encode() not in bytes(audit.data_ciphertext)
    api_client.force_authenticate(reader_user)
    response = api_client.get(f"/api/reading/citation-audits/{audit.id}/ocr/", {"unit_id": "pdf:1"})
    assert response.status_code == 200 and response.data["unit"]["text"]
    assert "no-store" in response["Cache-Control"]
    assert "text" not in research.serialize_record(audit, reader_user)["data"]["ocr_units"]["pdf:1"]
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/citation-audits/{audit.id}/ocr/").status_code == 404


def test_private_docx_image_is_derived_without_word_page_or_field_rewrite(reader_user, settings, monkeypatch):
    from docx import Document
    from PIL import Image
    import fitz
    image = BytesIO()
    Image.new("RGB", (60, 80), "white").save(image, format="PNG")
    image.seek(0)
    document = Document(BytesIO(docx_bytes()))
    # Insert before the bibliography to keep the normal section structure.
    drawing = document.add_paragraph()
    drawing.add_run().add_picture(image)
    body = document._element.body
    body.remove(drawing._p)
    body.insert(1, drawing._p)
    output = BytesIO()
    document.save(output)
    blob = output.getvalue()
    settings.PADDLEOCR_SERVICE_URL = "http://127.0.0.1:8090"
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    def gateway(path, **options):
        with fitz.open(stream=options["pdf_bytes"], filetype="pdf") as image_pdf:
            assert len(image_pdf) == 1
        return {"pages": [{"index": 1, "blocks": [{"text": '图像引文“制度始终嵌入具体的社会关系”。[1]'}]}]}
    monkeypatch.setattr("reading.private_ocr._request_document_gateway", gateway)
    audit = create_audit(reader_user, SimpleUploadedFile("图像稿件.docx", blob), {"request_id": str(uuid4())})
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    payload = research.unpack(audit)
    occurrence = next(row for row in payload["occurrences"] if row["location"].get("text_source") == "ocr")
    assert occurrence["location"]["pdf_page"] is None
    assert occurrence["location"]["media_path"].startswith("word/media/")
    assert occurrence["location"]["xml_node"]
    assert any(row.get("citation_field", "").startswith(" ADDIN ZOTERO") for row in payload["occurrences"])
    assert original_document(audit) == blob


def test_private_ocr_remote_refusal_retry_and_decision_preservation(reader_user, settings, monkeypatch):
    settings.PADDLEOCR_SERVICE_URL = "https://remote.example/"
    settings.OCR_REMOTE_API_URL = "https://other.example/"
    monkeypatch.setattr("reading.local_analysis.socket.getaddrinfo", lambda *args, **kwargs: (
        _ for _ in ()).throw(AssertionError("Unapproved OCR URL must not reach DNS")))
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    calls = []
    monkeypatch.setattr("reading.private_ocr._request_document_gateway", lambda *args, **kwargs: calls.append(kwargs) or {
        "pages": [{"index": 1, "blocks": [{"text": '“制度始终嵌入具体的社会关系”。[1]\n参考文献\n[1] 作者. 制度研究. 2020.'}]}]})
    audit = create_audit(reader_user, SimpleUploadedFile("扫描.pdf", scanned_pdf_bytes()), {"request_id": str(uuid4())})
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    assert audit.status == "partial" and not calls
    assert research.unpack(audit)["ocr_units"]["pdf:1"]["status"] == "failed"
    settings.PADDLEOCR_SERVICE_URL = "http://127.0.0.1:8090"
    audit = update_audit(reader_user, audit.id, {"expected_revision": audit.revision, "action": "retry"})
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    payload = research.unpack(audit)
    occurrence_id = payload["occurrences"][0]["id"]
    audit = update_audit(reader_user, audit.id, {"expected_revision": audit.revision, "action": "decision",
        "occurrence_id": occurrence_id, "decision": "needs_review", "note": "本人批注"})
    # Force a new parsing attempt as after another page's failure; unchanged
    # citations retain identity, decisions and old findings.
    payload = research.unpack(audit)
    payload["parsed"] = False
    research.save_data(audit, payload)
    audit = update_audit(reader_user, audit.id, {"expected_revision": audit.revision, "action": "retry"})
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    occurrence = research.unpack(audit)["occurrences"][0]
    assert occurrence["id"] == occurrence_id and occurrence["decision"]["note"] == "本人批注"
    assert len(calls) == 1


def test_private_ocr_cancellation_and_pinned_dns(settings, monkeypatch):
    from reading.private_ocr import enrich_private_manuscript
    from reading.citation_audit import parse_pdf
    settings.PADDLEOCR_SERVICE_URL = "http://ocr:8090"
    monkeypatch.setattr("reading.local_analysis.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("192.168.1.20", 8090))])
    cache, current, calls = {}, [True], []
    def gateway(path, **options):
        calls.append(options)
        from reading.local_analysis import PrivateLocalTransport
        assert options["base_url"] == "http://ocr:8090"
        assert isinstance(options["transport"], PrivateLocalTransport)
        assert options["transport"]._address == "192.168.1.20"
        assert str(options["transport"]._origin) == "http://ocr:8090"
        return {"pages": [{"index": 1, "blocks": [{"text": "完成第一页"}]}]}
    monkeypatch.setattr("reading.private_ocr._request_document_gateway", gateway)
    def checkpoint(*args):
        current[0] = False
        return True
    blob = scanned_pdf_bytes(2)
    result = enrich_private_manuscript(blob=blob, kind="pdf", paragraphs=parse_pdf(blob), cache=cache,
        generation=1, checkpoint=checkpoint, is_current=lambda: current[0])
    assert result is None and len(calls) == 1 and cache["pdf:1"]["status"] == "completed"


def test_existing_ocr_gateway_private_bytes_subset_disables_proxy_and_redirects(settings, monkeypatch):
    import fitz
    from ingestion.services.ocr_provider import _request_document_gateway
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    def post(url, **options):
        assert options["trust_env"] is False and options["follow_redirects"] is False
        assert options["files"]["file"][0] == "private-document.pdf"
        with fitz.open(stream=options["files"]["file"][1].read(), filetype="pdf") as subset:
            assert len(subset) == 1
        assert options["data"]["page_numbers"] == "1"
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"pages": [{"index": 1, "blocks": []}]})
    monkeypatch.setattr("ingestion.services.ocr_provider.httpx.post", post)
    result = _request_document_gateway(None, base_url="http://127.0.0.1:8090", pdf_bytes=scanned_pdf_bytes(3), page_numbers=[3])
    assert result["pages"][0]["index"] == 3


def test_direct_quote_matches_adjacent_pages_but_never_skipped_source_text(reader_user):
    from catalog.services.discovery_sources import fingerprint
    from reading.citation_audit import check_occurrence
    edition, _asset, spans, _docs = fixture_source(count=2)
    for span, value in zip(spans, ["制度始终嵌入", "具体的社会关系"]):
        span.page.text = value
        span.page.save(update_fields=["text"])
        span.original_text, span.content_hash, span.start_offset, span.end_offset = value, fingerprint(value), 0, len(value)
        span.save(update_fields=["original_text", "content_hash", "start_offset", "end_offset"])
    occurrence = {"entry_ids": ["entry"], "quote": "制度始终嵌入具体的社会关系", "context": "引文"}
    entries = [{"id": "entry", "selected_edition_id": str(edition.id)}]
    result = check_occurrence(occurrence, entries, reader_user)[0]
    assert result["status"] == "text_match"
    assert [anchor["pdf_page"] for anchor in result["references"][0]["anchors"]] == [1, 2]
    spans[0].page.text += "此处不能跳过的限定"
    spans[0].page.save(update_fields=["text"])
    result = check_occurrence(occurrence, entries, reader_user)[0]
    assert result["status"] == "unverified" and not result["references"]


def test_plan_budget_difficulty_dependency_and_completion_are_explainable(reader_user):
    sources = [fixture_source(count=1) for _ in range(3)]
    works = [str(source[0].work_id) for source in sources]
    refs = [{"evidence_span_id": str(source[2][0].id)} for source in sources]
    plan = research.generate_plan(reader_user, {"request_id": str(uuid4()), "goal": "可解释的预算", "references": refs,
        "budget_minutes": 45, "session_minutes": 15, "reading_level": "beginner",
        "item_estimates": [{"work_id": works[0], "minutes": 30, "difficulty": "beginner"},
            {"work_id": works[1], "minutes": 40, "difficulty": "advanced"},
            {"work_id": works[2], "minutes": 10, "difficulty": "beginner"}],
        "prerequisites": [{"work_id": works[2], "requires_work_id": works[1], "reference": refs[1]}]})
    payload = research.unpack(plan)
    by_work = {item["work_id"]: item for item in payload["items"]}
    assert by_work[works[0]]["budget_assignment"]["included"] is True
    assert by_work[works[1]]["budget_assignment"]["reason"] == "over_budget"
    assert by_work[works[2]]["budget_assignment"]["reason"] == "prerequisite_outside_budget"
    assert payload["schedule"]["planned_minutes"] == 30
    assert all(session["minutes"] <= 15 for session in payload["schedule"]["sessions"])
    assert by_work[works[0]]["difficulty"]["basis"] == "owner_estimate"
    assert by_work[works[0]]["planning_estimate"]["source"]["document_revision_id"] == str(sources[0][2][0].document_revision_id)
    completed = by_work[works[0]]
    plan = research.update_plan(reader_user, plan.id, {"expected_revision": plan.revision, "item_id": completed["id"], "status": "completed"})
    preserved = research.unpack(plan)["items"][0]["planning_estimate"]
    plan = research.update_plan(reader_user, plan.id, {"expected_revision": plan.revision, "budget_minutes": 50, "optimize_order": True,
        "reading_level": "advanced"})
    payload = research.unpack(plan)
    assert payload["items"][0]["status"] == "completed" and payload["items"][0]["planning_estimate"] == preserved
    assert payload["schedule"]["planned_minutes"] == 50
    assert len(payload["items"]) == 3


def test_plan_sampling_uses_exact_file_and_opt_out_ignores_other_history(reader_user, admin_user):
    from accounts.models import ReaderProfile
    from catalog.models import ReadingPath, ReadingPathItem
    from reading.models import ReadingProgress
    edition, asset, _spans, _ = fixture_source(count=15)
    path = ReadingPath.objects.create(title="预算路径", slug="budget-path", status="published", difficulty="intermediate")
    ReadingPathItem.objects.create(reading_path=path, work=edition.work)
    ReadingProgress.objects.create(user=admin_user, asset=asset, progress_ratio=1, current_page=15)
    body = {"goal": "阅读采样", "reading_path_id": str(path.id), "time_budget": "每周 2 小时"}
    plan = research.generate_plan(reader_user, {**body, "request_id": str(uuid4())})
    payload = research.unpack(plan)
    item = payload["items"][0]
    assert item["prior_reading"]["recorded"] is False
    assert item["difficulty"]["basis"] == "public_path_declared_level"
    assert len(item["planning_estimate"]["sampled_pages"]) == 12
    assert item["planning_estimate"]["total_pages"] == 15
    assert payload["planning_policy"]["budget_minutes"] == 120 and payload["planning_policy"]["budget_period"] == "week"
    ReadingProgress.objects.create(user=reader_user, asset=asset, progress_ratio=1, current_page=15)
    ReaderProfile.objects.update_or_create(user=reader_user, defaults={"reading_preferences": {"research_personalization": False}})
    reader_user.refresh_from_db()
    second = research.generate_plan(reader_user, {**body, "request_id": str(uuid4())})
    payload = research.unpack(second)
    assert payload["planning_policy"]["prefer_unread"] is False
    assert payload["items"][0]["prior_reading"]["recorded"] is False
    assert payload["items"][0]["status"] == "pending"
    assert payload["items"][0]["prior_reading"]["understanding"] == "not_inferred"


def test_plan_unknown_duration_and_invalid_budget_are_explicit():
    from reading.plan_rules import planning_policy, schedule_plan
    with pytest.raises(ValidationError):
        planning_policy({"time_budget": "有空时读"})
    with pytest.raises(ValidationError):
        planning_policy({"budget_minutes": True})
    with pytest.raises(ValidationError):
        planning_policy({"session_minutes": 0})
    items, schedule = schedule_plan([{"id": "one", "work_id": "one", "difficulty": {"level": "beginner"},
        "estimated_minutes": None, "status": "pending"}], [], planning_policy({"budget_minutes": 30}))
    assert items[0]["budget_assignment"]["reason"] == "duration_unknown"
    assert schedule["planned_minutes"] == 0 and not schedule["sessions"]
    _items, large = schedule_plan([{"id": "one", "work_id": "one", "difficulty": {"level": None},
        "estimated_minutes": 100000, "status": "pending"}], [], planning_policy({"session_minutes": 5}))
    assert len(large["sessions"]) == large["session_limit"] == 1000
    assert large["unscheduled_minutes"] == 95000


def test_ocr_no_text_remains_unverified_and_retries_only_after_new_generation(settings, monkeypatch):
    from reading.private_ocr import enrich_private_manuscript
    from reading.citation_audit import parse_pdf
    settings.PADDLEOCR_SERVICE_URL = "http://127.0.0.1:8090"
    calls = []
    monkeypatch.setattr("reading.private_ocr._request_document_gateway", lambda *args, **kwargs: calls.append(1) or {
        "pages": [{"index": 1, "blocks": []}]})
    blob, cache = scanned_pdf_bytes(), {}
    args = {"blob": blob, "kind": "pdf", "paragraphs": parse_pdf(blob), "cache": cache,
        "checkpoint": lambda *args: True, "is_current": lambda: True}
    _rows, warnings, remaining = enrich_private_manuscript(**args, generation=1)
    assert not remaining and warnings[0]["code"] == "private_ocr_no_text"
    enrich_private_manuscript(**args, generation=1)
    assert len(calls) == 1
    enrich_private_manuscript(**args, generation=2)
    assert len(calls) == 2


def test_pdf_wrapped_quote_retains_physical_page_and_character_position():
    parsed = parse_manuscript(b"", "pdf", paragraphs=[{"text": '“制度始终嵌入\n具体的社会关系”。[1]',
        "fields": [], "note_refs": [], "location": {"part": "pdf", "pdf_page": 3, "paragraph": None}}])
    occurrence = parsed["occurrences"][0]
    assert occurrence["quote"] == "制度始终嵌入\n具体的社会关系"
    assert occurrence["location"]["pdf_page"] == 3
    assert occurrence["location"]["end"] - occurrence["location"]["start"] == 3


def test_ocr_retry_preserves_owner_link_when_another_page_was_unavailable(reader_user, settings, monkeypatch):
    settings.PADDLEOCR_SERVICE_URL = "http://127.0.0.1:8090"
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    attempts = []
    def gateway(path, **options):
        page = options["page_numbers"][0]
        attempts.append(page)
        if page == 2 and attempts.count(2) == 1:
            raise RuntimeError("synthetic OCR unavailable")
        value = '“制度始终嵌入具体的社会关系”。[1]\n参考文献\n[1] 甲. 第一材料. 2020.\n[2] 乙. 第二材料. 2021.' if page == 1 else "结束语"
        return {"pages": [{"index": page, "blocks": [{"text": value}]}]}
    monkeypatch.setattr("reading.private_ocr._request_document_gateway", gateway)
    audit = create_audit(reader_user, SimpleUploadedFile("两页.pdf", scanned_pdf_bytes(2)), {"request_id": str(uuid4())})
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    payload = research.unpack(audit)
    occurrence_id = payload["occurrences"][0]["id"]
    selected_id = next(entry["id"] for entry in payload["bibliography"] if entry["label"] == "2")
    audit = update_audit(reader_user, audit.id, {"expected_revision": audit.revision, "action": "link",
        "occurrence_id": occurrence_id, "entry_ids": [selected_id]})
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    audit = update_audit(reader_user, audit.id, {"expected_revision": audit.revision, "action": "retry"})
    process_audit(audit.id, audit.generation, audit.task_id)
    audit.refresh_from_db()
    occurrence = research.unpack(audit)["occurrences"][0]
    assert occurrence["id"] == occurrence_id and occurrence["entry_ids"] == [selected_id]
    assert occurrence["entry_link"]["status"] == "preserved"
    assert attempts == [1, 2, 2]


def test_private_transport_pins_verified_ip_and_preserves_tls_identity(monkeypatch):
    import httpx
    from reading.local_analysis import AIServiceUnavailable, PrivateLocalTransport
    resolutions, requests = [], []

    def resolve(host, *_args, **_kwargs):
        resolutions.append(host)
        assert len(resolutions) == 1, "The transport must not resolve the hostname again."
        return [(2, 1, 6, "", ("192.168.1.4", 0))]

    def send(_transport, request):
        requests.append((str(request.url), request.headers["Host"], request.extensions["sni_hostname"]))
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr("reading.local_analysis.socket.getaddrinfo", resolve)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", send)
    with PrivateLocalTransport("https://local-model:8443", allowed_hosts=["local-model"]) as transport:
        for path in ("/embed", "/generate"):
            transport.handle_request(httpx.Request("POST", "https://local-model:8443" + path, json={"text": "private fixture"}))
        with pytest.raises(AIServiceUnavailable):
            transport.handle_request(httpx.Request("POST", "https://other-host:8443/embed"))
    assert resolutions == ["local-model"]
    assert requests == [("https://192.168.1.4:8443/embed", "local-model:8443", "local-model"),
                        ("https://192.168.1.4:8443/generate", "local-model:8443", "local-model")]


@pytest.mark.parametrize("kind", ["pdf", "docx"])
def test_native_manuscript_limit_applies_before_private_checkpoint(kind, monkeypatch):
    from io import BytesIO
    import fitz
    from docx import Document
    from reading import citation_audit
    monkeypatch.setattr(citation_audit, "MAX_TEXT_CHARS", 10)
    if kind == "pdf":
        with fitz.open() as document:
            document.new_page().insert_text((40, 40), "A deliberately long native manuscript paragraph.")
            blob = document.tobytes()
    else:
        document, output = Document(), BytesIO()
        document.add_paragraph("A deliberately long native manuscript paragraph.")
        document.save(output)
        blob = output.getvalue()
    with pytest.raises(ValidationError):
        (citation_audit.parse_pdf if kind == "pdf" else citation_audit.parse_docx)(blob)
