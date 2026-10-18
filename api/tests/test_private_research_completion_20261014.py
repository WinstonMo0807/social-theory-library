"""Guest transfer and killed-worker recovery. Run only during unified acceptance."""
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from reading import research
from reading.models import CitationAudit, PersonalReadingPlan, ResearchProject, ResearchTurn
from reading.tasks import collect_research_turn, recover_private_research_tasks
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def imported_body(span):
    reference = {"evidence_span_id": str(span.id)}
    return {"schema_version": 1, "request_id": str(uuid4()), "local_id": "guest-project",
        "title": "农业组织化", "question": "如何理解农业组织化", "selections": [reference],
        "notes": "需要比较合作关系与国家组织。", "layout": {"materials": True},
        "comparison": {"dimensions": ["解释对象"], "cells": [{"dimension": "解释对象",
            "reference_ids": [str(span.id)], "note": "我的比较"}]},
        "turns": [{"local_id": "first", "question": "如何理解农业组织化", "references": [reference]},
            {"local_id": "followup", "parent_local_id": "first", "question": "其中的合作条件是什么",
                "references": [reference], "status": "running"}]}


def test_explicit_guest_transfer_is_encrypted_idempotent_and_owner_only(api_client, reader_user, admin_user, monkeypatch):
    _, _, spans, _ = fixture_source(count=1)
    dispatched = []
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: dispatched.append(args))
    body = imported_body(spans[0])
    api_client.force_authenticate(reader_user)
    first = api_client.post("/api/reading/research-projects/import/", body, format="json")
    second = api_client.post("/api/reading/research-projects/import/", body, format="json")
    assert first.status_code == second.status_code == 201
    assert first.data["id"] == second.data["id"] and not dispatched
    assert first["Cache-Control"] == "private, no-store"
    project = ResearchProject.objects.get(pk=first.data["id"])
    payload = research.unpack(project)
    assert payload["notes"] == body["notes"] and payload["comparison"]["cells"][0]["note"] == "我的比较"
    assert body["notes"].encode() not in bytes(project.data_ciphertext)
    mapping = payload["imported_turns"]
    turn = project.turns.get(pk=mapping["followup"])
    assert str(turn.parent_id) == mapping["first"] and turn.status == "partial" and not turn.task_id
    assert project.turns.count() == 2
    assert api_client.post("/api/reading/research-projects/import/", {**body, "notes": "另一份内容"}, format="json").status_code == 409
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/research-projects/{project.id}/").status_code == 404


def test_guest_transfer_rechecks_withdrawn_source_and_never_stores_cached_quote(reader_user):
    edition, _, spans, _ = fixture_source(count=1)
    body = imported_body(spans[0])
    body["selections"][0]["quote"] = "不可信的浏览器缓存正文"
    edition.active_catalog_revision.fulltext_ready = False
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    project = research.import_project(reader_user, body)
    saved = research.unpack(project)
    assert saved["selections"] == [{"schema_version": 1, "source_kind": "catalog", "evidence_span_id": str(spans[0].id)}]
    assert saved["import_warnings"][0]["code"] == "source_unavailable"
    assert "不可信的浏览器缓存正文" not in str(saved)
    assert research.serialize_record(project, reader_user)["data"]["selections"][0]["source_status"] == "unavailable"


def test_guest_transfer_rejects_branch_cycles_without_partial_records(reader_user):
    _, _, spans, _ = fixture_source(count=1)
    body = imported_body(spans[0])
    body["turns"][0]["parent_local_id"] = "followup"
    before = ResearchProject.objects.count()
    with pytest.raises(ValidationError):
        research.import_project(reader_user, body)
    assert ResearchProject.objects.count() == before
    assert not ResearchTurn.objects.exists()


def test_guest_transfer_never_silently_truncates_history(reader_user):
    _, _, spans, _ = fixture_source(count=1)
    body = imported_body(spans[0])
    body["turns"] = [{"local_id": str(index), "question": "保留研究问题"} for index in range(101)]
    with pytest.raises(ValidationError):
        research.import_project(reader_user, body)
    assert not ResearchProject.objects.filter(request_id=body["request_id"]).exists()


def stale_record(model, **kwargs):
    record = model.objects.create(**kwargs)
    model.objects.filter(pk=record.id).update(updated_at=timezone.now() - timedelta(minutes=40))
    record.refresh_from_db()
    return record


def test_recovery_requeues_with_new_lease_and_rejects_late_worker(reader_user, monkeypatch, django_capture_on_commit_callbacks):
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "待恢复研究"})
    turn = stale_record(ResearchTurn, project=project, status="running", task_id="old-token", data_ciphertext=research.pack({
        "question": "如何理解农业组织化", "result_refs": [], "scope": {"kind": "library", "filters": {}}}))
    calls = []
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: calls.append(args))
    with django_capture_on_commit_callbacks(execute=True):
        result = recover_private_research_tasks()
    turn.refresh_from_db()
    assert result["research"] == 1 and turn.status == "queued" and turn.generation == 2
    assert turn.task_id != "old-token" and calls == [(turn.id, 2, turn.task_id)]
    revision = turn.revision
    collect_research_turn(str(turn.id), 1, "old-token")
    turn.refresh_from_db()
    assert turn.revision == revision
    assert research.unpack(turn)["question"] == "如何理解农业组织化"


def test_recovery_keeps_completed_audit_units_and_human_decisions(reader_user, monkeypatch):
    audit = stale_record(CitationAudit, user=reader_user, status="running", generation=3, task_id="old-audit",
        data_ciphertext=research.pack({"parsed": True, "occurrences": [
            {"id": "done", "checked_generation": 3, "decision": {"value": "accepted"}},
            {"id": "pending", "checked_generation": 2}], "rerun_occurrence_ids": None}))
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    recover_private_research_tasks()
    audit.refresh_from_db()
    assert audit.generation == 4 and audit.status == "queued"
    payload = research.unpack(audit)
    assert payload["rerun_occurrence_ids"] == ["pending"]
    assert payload["occurrences"][0]["decision"] == {"value": "accepted"}


def test_recovery_is_bounded_and_never_restarts_canceled_jobs(reader_user):
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "研究"})
    exhausted = stale_record(ResearchTurn, project=project, status="running", data_ciphertext=research.pack({"recovery_attempts": 3}))
    canceled = stale_record(ResearchTurn, project=project, status="canceled", data_ciphertext=research.pack({"question": "已取消"}))
    result = recover_private_research_tasks()
    exhausted.refresh_from_db()
    canceled.refresh_from_db()
    assert result["exhausted"] == 1 and exhausted.status == "failed" and exhausted.error_code == "recovery_exhausted"
    assert canceled.status == "canceled" and canceled.generation == 1


def test_plan_recovery_persists_failure_instead_of_only_changing_response(reader_user):
    plan = stale_record(PersonalReadingPlan, user=reader_user, task_pending=True, data_ciphertext=research.pack({
        "generation_status": "queued", "items": [], "origin": {"turn_id": str(uuid4())}}))
    recover_private_research_tasks()
    plan.refresh_from_db()
    assert research.unpack(plan)["generation_status"] == "failed" and plan.task_pending is False


def test_plan_retry_preserves_id_and_old_turn_then_cancel_invalidates_job(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "原研究"})
    turn = ResearchTurn.objects.create(project=project, status="failed", data_ciphertext=research.pack({
        "question": "如何理解农业组织化", "scope": {"kind": "library", "filters": {}}, "result_refs": []}))
    plan = PersonalReadingPlan.objects.create(user=reader_user, project=project, data_ciphertext=research.pack({
        "goal": "如何理解农业组织化", "generation_status": "failed", "items": [], "origin": {"turn_id": str(turn.id)}}))
    renewed = research.command_plan(SimpleNamespace(user=reader_user), plan.id, {"expected_revision": 1, "action": "retry"})
    next_turn = ResearchTurn.objects.get(pk=research.unpack(renewed)["origin"]["turn_id"])
    assert renewed.id == plan.id and next_turn.parent_id == turn.id and next_turn.status == "queued"
    assert turn.status == "failed" and research.unpack(next_turn)["plan_id"] == str(plan.id)
    canceled = research.command_plan(SimpleNamespace(user=reader_user), plan.id,
        {"expected_revision": renewed.revision, "action": "cancel"})
    next_turn.refresh_from_db()
    assert research.unpack(canceled)["generation_status"] == "canceled" and canceled.task_pending is False
    assert next_turn.status == "canceled" and next_turn.generation == 2


def test_plan_enhancement_recovery_preserves_reading_progress(reader_user, monkeypatch):
    plan = stale_record(PersonalReadingPlan, user=reader_user, task_pending=True, data_ciphertext=research.pack({
        "generation_status": "completed", "enhancement_status": "running", "goal": "理解组织化",
        "items": [{"id": "one", "status": "completed", "note": "本人已读笔记"}]}))
    monkeypatch.setattr("reading.tasks.enqueue_plan_enhancement", lambda *args: None)
    recover_private_research_tasks()
    plan.refresh_from_db()
    payload = research.unpack(plan)
    assert payload["enhancement_status"] == "queued" and payload["recovery_attempts"] == 1
    assert payload["items"][0] == {"id": "one", "status": "completed", "note": "本人已读笔记"}


def test_reader_identity_follows_exact_active_revision(api_client):
    edition, asset, spans, _ = fixture_source(count=1)
    manifest = api_client.get(f"/api/catalog/assets/{asset.id}/manifest/")
    page = api_client.get(f"/api/catalog/assets/{asset.id}/pages/1/")
    assert manifest.status_code == page.status_code == 200
    assert manifest.data["document_revision_id"] == page.data["document_revision_id"] == str(spans[0].document_revision_id)
    assert page.data["asset_id"] == str(asset.id)
    edition.active_catalog_revision.fulltext_ready = False
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    assert api_client.get(f"/api/catalog/assets/{asset.id}/manifest/").data["document_revision_id"] is None
    hidden = api_client.get(f"/api/catalog/assets/{asset.id}/pages/1/").data
    assert hidden["document_revision_id"] is None and hidden["text"] == "" and hidden["blocks"] == []


def test_semantic_memory_can_recall_without_shared_words_and_respects_owner(reader_user, admin_user, monkeypatch):
    from contextlib import nullcontext
    from reading.models import ResearchMemory
    target = research.create_memory(reader_user, {"request_id": str(uuid4()), "body": "农户通过合作社共同采购"})
    research.update_memory(reader_user, target.id, {"expected_revision": 1, "state": "confirmed"})
    outsider = research.create_memory(admin_user, {"request_id": str(uuid4()), "body": "private forbidden"})
    research.update_memory(admin_user, outsider.id, {"expected_revision": 1, "state": "confirmed"})
    calls = []
    monkeypatch.setattr("reading.local_analysis.PrivateLocalTransport", lambda *args, **kwargs: nullcontext(None))
    def encode(texts, **kwargs):
        calls.extend(texts)
        assert "private forbidden" not in texts
        return {"artifact_id": "test-model", "vectors": [[1.0, 0.0] for _ in texts]}
    monkeypatch.setattr("catalog.services.discovery_inference.embed_texts", encode)
    assert research.search_memories(reader_user, "collective action", allowed_ids=[str(target.id)])["results"] == []
    result = research.search_memories(reader_user, "collective action", semantic=True, allowed_ids=[str(target.id)])
    assert result["mode"] == "local_semantic_owner_candidates" and result["semantic_scope_complete"]
    assert [row["id"] for row in result["results"]] == [str(target.id)]
    assert len(calls) == 2 and ResearchMemory.objects.get(pk=target.id).embedding_ciphertext
    assert not ResearchMemory.objects.get(pk=outsider.id).embedding_ciphertext
    assert research.search_memories(reader_user, "collective action", semantic=True, allowed_ids=[str(outsider.id)])["results"] == []


def test_semantic_memory_ignores_record_forgotten_during_inference(reader_user, monkeypatch):
    from contextlib import nullcontext
    from reading.models import ResearchMemory
    memory = research.create_memory(reader_user, {"request_id": str(uuid4()), "body": "本人旧认识"})
    research.update_memory(reader_user, memory.id, {"expected_revision": 1, "state": "confirmed"})
    monkeypatch.setattr("reading.local_analysis.PrivateLocalTransport", lambda *args, **kwargs: nullcontext(None))
    def encode(texts, **kwargs):
        if kwargs.get("kind") != "query":
            ResearchMemory.objects.filter(pk=memory.id).delete()
        return {"artifact_id": "test-model", "vectors": [[1.0, 0.0] for _ in texts]}
    monkeypatch.setattr("catalog.services.discovery_inference.embed_texts", encode)
    assert research.search_memories(reader_user, "制度", semantic=True, allowed_ids=[str(memory.id)])["results"] == []


def citation_candidate(author, year, version="第二版", doi=""):
    return SimpleNamespace(id=uuid4(), work_id=uuid4(), active_catalog_revision=SimpleNamespace(snapshot={
        "work": {"title": "社会组织研究", "document_type": "book"},
        "edition": {"publication_year": year, "version_label": version, "doi": doi},
        "contributions": [{"role": "author", "person": {"preferred_name": author, "aliases": []}}]}))


def test_citation_identity_ranks_authors_years_and_versions_without_confirming_title():
    from reading.citation_audit import match_bibliography
    expected = citation_candidate("张三", 2020)
    wrong = citation_candidate("李四", 1999, "第一版")
    entry = {"raw": "张三. 社会组织研究. 第二版. 2020", "doi": "", "identity_status": "pending",
        "field_item": {"author": [{"literal": "张三"}], "issued": {"date-parts": [[2020]]}, "edition": "第二版"}}
    match_bibliography(entry, [wrong, expected])
    assert entry["identity_status"] == "needs_review" and entry["selected_edition_id"] is None
    best, other = entry["candidates"]
    assert best["edition_id"] == str(expected.id) and best["review_fields"] == []
    assert other["identity_signals"]["author"]["status"] == "conflict"
    assert other["identity_signals"]["year"]["status"] == "conflict"
    assert other["identity_signals"]["version"]["status"] == "needs_review"


def test_citation_identifier_conflict_needs_review_and_human_choice_is_unchanged():
    from reading.citation_audit import match_bibliography
    candidate = citation_candidate("张三", 1999, doi="10.1234/example")
    entry = {"raw": "社会组织研究. 2020", "doi": "10.1234/example", "identity_status": "pending"}
    match_bibliography(entry, [candidate])
    assert entry["identity_status"] == "needs_review" and entry["selected_edition_id"] is None
    assert entry["candidates"][0]["review_fields"] == ["year"]
    entry.update(identity_status="user_confirmed", selected_edition_id=str(candidate.id))
    match_bibliography(entry, [])
    assert entry["identity_status"] == "user_confirmed" and entry["selected_edition_id"] == str(candidate.id)


def test_explicit_subclaims_drive_only_selected_branch_and_keep_previous_analysis(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "反证研究"})
    first_id, second_id = str(uuid4()), str(uuid4())
    claims = [{"id": first_id, "proposition": "合作社降低交易成本", "qualifiers": ["自愿参与"]},
        {"id": second_id, "proposition": "组织化总能改善农户收入", "polarity": "positive"}]
    turn = research.start_turn(SimpleNamespace(user=reader_user), project.id, {"request_id": str(uuid4()),
        "expected_revision": project.revision, "question": "农业组织化有何后果", "mode": "counterargument",
        "subclaims": claims, "active_subclaim_id": first_id})
    original = research.unpack(turn)
    assert original["question"] == "农业组织化有何后果" and original["search_question"] == claims[0]["proposition"]
    assert original["statement"]["qualifiers"] == ["自愿参与"]
    turn = research.cancel_turn(reader_user, turn.id)
    changed = research.save_subclaims(reader_user, turn.id, {"expected_revision": turn.revision,
        "subclaims": [{**claims[0], "proposition": "合作社在特定条件下降低交易成本"}, claims[1]]})
    saved = research.unpack(changed)
    assert saved["analysis_statement"] == original["statement"]
    assert saved["subclaims"][0]["proposition"] != saved["analysis_statement"]["proposition"]
    assert saved["subclaims_history"][0]["subclaims"] == claims


def test_reader_never_serves_ocr_from_another_source_in_same_edition():
    from catalog.models import Asset
    from distribution.views import _download_file_asset, _reader_file_asset
    edition, anchor, _, _ = fixture_source(count=1)
    other = Asset.objects.create(edition=edition, kind="normalized", status="ready", sha256="x" * 64, is_current=False)
    derivative = Asset.objects.create(edition=edition, kind="ocr_pdf", status="ready", validation_status="valid",
        source_asset=other, sha256="y" * 64, version=9, is_current=True)
    edition.reader_rendition_policy, edition.ocr_status = "ocr", "succeeded"
    anchor.edition = edition
    assert _reader_file_asset(anchor)[0].id == anchor.id
    assert _download_file_asset(anchor)[0].id == anchor.id
    correct = Asset.objects.create(edition=edition, kind="ocr_pdf", status="ready", validation_status="valid",
        source_asset=anchor, sha256="z" * 64, version=1, is_current=True,
        validation_details={"source_normalized_asset_id": str(anchor.id), "visual_source_sha256": anchor.sha256})
    assert _reader_file_asset(anchor)[0].id == correct.id
    assert _download_file_asset(anchor)[0].id == correct.id
    derivative.refresh_from_db()
    assert derivative.is_current  # Read-time protection does not delete or rewrite old files.


def test_comparison_rechecks_evidence_without_erasing_owner_judgment(reader_user):
    _, _, spans, _ = fixture_source(count=2)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision,
        "action": "add", "references": [{"evidence_span_id": str(span.id)} for span in spans]})
    project = research.save_comparison(reader_user, project.id, {"expected_revision": project.revision,
        "dimensions": ["解释对象", "证据缺口"], "cells": [
            {"dimension": "解释对象", "reference_ids": [str(span.id) for span in spans], "note": "本人暂定的比较判断"},
            {"dimension": "证据缺口", "reference_ids": [], "note": "尚需材料"}]})
    cells = research.serialize_record(project, reader_user)["data"]["comparison"]["cells"]
    assert [cell["evidence_status"] for cell in cells] == ["selected", "missing"]
    spans[1].is_stale = True
    spans[1].save(update_fields=["is_stale"])
    payload = research.serialize_record(project, reader_user)["data"]
    assert payload["comparison"]["cells"][0]["evidence_status"] == "partial"
    assert "quote" not in payload["selections"][1]
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision,
        "action": "remove", "reference_id": str(spans[0].id)})
    cells = research.serialize_record(project, reader_user)["data"]["comparison"]["cells"]
    assert cells[0]["evidence_status"] == "unavailable"
    assert cells[0]["note"] == "本人暂定的比较判断"
    assert cells[0]["reference_ids"] == [str(span.id) for span in spans]


def test_research_adopts_discovery_final_order_and_keeps_prior_material(reader_user, monkeypatch):
    from catalog.discovery_models import DiscoverySearchSession
    _, _, spans, _ = fixture_source(count=3)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    session = DiscoverySearchSession.objects.create(owner=reader_user, token_hash="unused", query="研究问题",
        status="completed", access_statuses=research.access_for(reader_user), expires_at=timezone.now() + timedelta(hours=1))
    old = [research.compact_reference(research.resolve_reference({"evidence_span_id": str(span.id)}, reader_user))
           for span in spans]
    # The selected-material limit must not truncate durable results already retained by a previous round.
    retained = [{"evidence_span_id": str(uuid4())} for _ in range(400)]
    turn = ResearchTurn.objects.create(project=project, discovery_session_id=session.id, task_id="final-order",
        data_ciphertext=research.pack({"question": "研究问题", "mode": "search", "scope": {"kind": "library", "filters": {}},
            "result_refs": [*old, *retained]}))
    calls = []

    def final_passages(current, access_statuses):
        calls.append((current.id, access_statuses))
        return [old[2], old[0]]

    monkeypatch.setattr("catalog.services.discovery_sessions.rehydrate_passages", final_passages)
    collect_research_turn(str(turn.id), turn.generation, turn.task_id)
    turn.refresh_from_db()
    saved = research.unpack(turn)["result_refs"]
    assert turn.status == "completed" and calls == [(session.id, sorted(session.access_statuses))]
    assert [row["evidence_span_id"] for row in saved[:3]] == [str(spans[2].id), str(spans[0].id), str(spans[1].id)]
    assert saved[3:] == retained and len(saved) == 403


def test_comparison_column_keeps_removed_evidence_but_rejects_new_unselected_sources(reader_user):
    edition, _, spans, _ = fixture_source(count=2)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision,
        "action": "add", "references": [{"evidence_span_id": str(spans[0].id)}]})
    cell = {"dimension": "作用机制", "column_id": f"edition:{edition.id}", "author": "",
            "reference_ids": [str(spans[0].id)], "note": "原有判断"}
    project = research.save_comparison(reader_user, project.id, {"expected_revision": project.revision,
        "dimensions": ["作用机制"], "cells": [cell]})
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision,
        "action": "remove", "reference_id": str(spans[0].id)})
    project = research.save_comparison(reader_user, project.id, {"expected_revision": project.revision,
        "dimensions": ["作用机制"], "cells": [{**cell, "note": "原文已移除，保留我的判断"}]})
    saved = research.serialize_record(project, reader_user)["data"]["comparison"]["cells"][0]
    assert saved["column_id"] == cell["column_id"] and saved["evidence_status"] == "unavailable"
    assert saved["note"] == "原文已移除，保留我的判断"
    with pytest.raises(ValidationError):
        research.save_comparison(reader_user, project.id, {"expected_revision": project.revision,
            "dimensions": ["作用机制"], "cells": [{**cell, "reference_ids": [str(spans[1].id)]}]})
    with pytest.raises(ValidationError):
        research.save_comparison(reader_user, project.id, {"expected_revision": project.revision,
            "dimensions": ["作用机制"], "cells": [{**cell, "column_id": f"edition:{uuid4()}"}]})


def test_composite_reference_id_survives_source_withdrawal(reader_user):
    edition, _, spans, _ = fixture_source(count=2)
    reference = research.resolve_reference({"anchors": [{"evidence_span_id": str(span.id)} for span in spans]}, reader_user)
    key = research.reference_identity(reference)
    assert reference["reference_id"] == key and key.startswith("anchors:")
    assert all(anchor["reference_id"] == str(span.id) for anchor, span in zip(reference["anchors"], spans))
    edition.active_catalog_revision.fulltext_ready = False
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    withdrawn = research.resolve_reference(research.compact_reference(reference), reader_user)
    assert withdrawn["reference_id"] == key and withdrawn["source_status"] == "unavailable"
    assert not withdrawn["quote"] and not withdrawn["reader_url"]
