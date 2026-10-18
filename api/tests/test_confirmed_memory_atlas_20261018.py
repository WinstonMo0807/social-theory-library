"""PDF 205–207 owner authorization and source contracts; unified acceptance pending."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from reading import research
from reading.models import Annotation, PersonalReadingPlan, ResearchMemory
from reading.services import encrypt_private_text
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def memory_for(user, *, state="confirmed", **data):
    memory = research.create_memory(user, {"request_id": str(uuid4()), "body": "制度与社会关系", **data})
    return research.update_memory(user, memory.id, {"expected_revision": memory.revision, "state": state})


def project_for(user):
    return research.create_project(user, {"request_id": str(uuid4()), "title": "本人的研究"})


def grant(user, memory, target, kind="project"):
    return research.update_memory_usage(user, memory.id, {"expected_revision": memory.revision, "action": "grant",
        "targets": [{"kind": kind, "id": str(target.id), "expected_revision": target.revision}]})


def test_confirmation_does_not_grant_and_unscoped_search_is_empty(reader_user):
    memory = memory_for(reader_user)
    project = project_for(reader_user)
    assert research.serialize_record(memory, reader_user)["data"]["usage_scopes"] == []
    assert research.unpack(project)["use_confirmed_memories"] is False
    assert research.search_memories(reader_user, "制度")["results"] == []
    assert research.search_memories(reader_user, "制度", context={"kind": "project", "id": str(project.id)})["results"] == []
    assert len(research.search_memories(reader_user, "制度", allowed_ids=[str(memory.id)])["results"]) == 1


def test_usage_requires_confirmed_owner_and_current_target_revision(reader_user, admin_user):
    memory = memory_for(reader_user, state="proposed")
    project = project_for(reader_user)
    with pytest.raises(ValidationError):
        grant(reader_user, memory, project)
    memory = research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision, "state": "confirmed"})
    foreign = project_for(admin_user)
    with pytest.raises(NotFound):
        grant(reader_user, memory, foreign)
    with pytest.raises(NotFound):
        grant(admin_user, memory, foreign)
    research.update_project(reader_user, project.id, {"expected_revision": project.revision, "notes": "另一处修改"})
    with pytest.raises(research.ResearchConflict):
        grant(reader_user, memory, project)
    project.refresh_from_db()
    assert research.unpack(project)["confirmed_memory_ids"] == []


def test_grant_scope_is_exact_and_revoke_does_not_remove_other_memory(reader_user):
    first, second = memory_for(reader_user), memory_for(reader_user, body="另一条本人认识")
    chosen, other = project_for(reader_user), project_for(reader_user)
    first = grant(reader_user, first, chosen)
    chosen.refresh_from_db()
    second = grant(reader_user, second, chosen)
    assert research.search_memories(reader_user, "制度", context={"kind": "project", "id": str(other.id)})["results"] == []
    assert len(research.search_memories(reader_user, "制度", context={"kind": "project", "id": str(chosen.id)})["results"]) == 1
    research.update_memory_usage(reader_user, first.id, {"expected_revision": first.revision, "action": "revoke_all"})
    chosen.refresh_from_db()
    assert research.unpack(chosen)["confirmed_memory_ids"] == [str(second.id)]


@pytest.mark.parametrize("changes", [{"body": "重新确认的不同认识"}, {"kind": "method"}])
def test_confirming_edited_content_does_not_reuse_previous_scope_grant(reader_user, changes):
    memory = memory_for(reader_user)
    project = project_for(reader_user)
    memory = grant(reader_user, memory, project)
    memory = research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision,
        "body": "制度与社会关系", "kind": "understanding", "state": "confirmed"})
    project.refresh_from_db()
    assert research.unpack(project)["confirmed_memory_ids"] == [str(memory.id)]
    memory = research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision,
        **changes, "state": "confirmed"})
    project.refresh_from_db()
    assert memory.state == "confirmed"
    assert research.unpack(project)["confirmed_memory_ids"] == []
    assert research.serialize_record(memory, reader_user)["data"]["usage_scopes"] == []


@pytest.mark.parametrize("action", ["edit", "ignore", "delete"])
def test_edit_ignore_delete_remove_authority_without_touching_original_note(reader_user, action):
    _, asset, spans, _ = fixture_source(count=1)
    note = Annotation.objects.create(user=reader_user, asset=asset, page=spans[0].page, kind="note",
        body_ciphertext=encrypt_private_text("原始本人笔记"), quote=spans[0].original_text, asset_sha256=asset.sha256)
    memory = memory_for(reader_user, annotation_id=str(note.id))
    project = project_for(reader_user)
    memory = grant(reader_user, memory, project)
    if action == "delete":
        research.delete_memory(reader_user, memory.id, memory.revision)
    else:
        values = {"body": "修改后的本人判断"} if action == "edit" else {"state": "ignored"}
        memory = research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision, **values})
        if action == "edit":
            assert memory.state == "proposed"
        memory = research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision, "state": "confirmed"})
    project.refresh_from_db()
    assert research.unpack(project)["confirmed_memory_ids"] == []
    assert Annotation.objects.filter(pk=note.id).exists()


def test_source_withdrawal_hides_quote_and_keeps_own_body_and_history(reader_user):
    edition, asset, spans, _ = fixture_source(count=1)
    note = Annotation.objects.create(user=reader_user, asset=asset, page=spans[0].page, kind="note",
        body_ciphertext=encrypt_private_text("本人原笔记"), quote=spans[0].original_text, asset_sha256=asset.sha256)
    memory = memory_for(reader_user, annotation_id=str(note.id), kind="concept")
    current = research.serialize_record(memory, reader_user)["data"]
    assert current["origin_note"]["quote"] == note.quote
    assert current["sources"][0]["document_revision_id"] == str(edition.active_catalog_revision.document_revision_id)
    edition.active_catalog_revision.fulltext_ready = False
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    current = research.serialize_record(memory, reader_user)["data"]
    assert current["source_status"] == "unavailable"
    assert current["body"] == "制度与社会关系"
    assert current["origin_note"]["body"] == "本人原笔记"
    assert current["origin_note"]["quote"] == "" and current["origin_note"]["reader_url"] is None
    assert "quote" not in current["sources"][0]
    assert all("quote" not in ref for entry in current["history"] for ref in entry["data"]["sources"])
    with pytest.raises(ValidationError):
        research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision, "refresh_origin": True})


def test_annotation_cannot_be_taken_from_another_owner(reader_user, admin_user):
    _, asset, spans, _ = fixture_source(count=1)
    note = Annotation.objects.create(user=admin_user, asset=asset, page=spans[0].page, kind="note",
        body_ciphertext=encrypt_private_text("别人的笔记"), asset_sha256=asset.sha256)
    with pytest.raises(NotFound):
        memory_for(reader_user, annotation_id=str(note.id))


def test_source_update_requires_explicit_refresh_and_preserves_old_identity(reader_user):
    _, asset, spans, _ = fixture_source(count=2)
    note = Annotation.objects.create(user=reader_user, asset=asset, page=spans[0].page, kind="note",
        body_ciphertext=encrypt_private_text("本人原笔记"), quote=spans[0].original_text, asset_sha256=asset.sha256)
    memory = memory_for(reader_user, annotation_id=str(note.id), sources=[{"evidence_span_id": str(spans[1].id)}])
    project = project_for(reader_user)
    memory = grant(reader_user, memory, project)
    original_hash = research.unpack(memory)["sources"][0]["content_hash"]
    page = spans[0].page
    page.text += " 补入校准后的文字。"
    page.save(update_fields=["text"])
    current = research.serialize_record(memory, reader_user)["data"]
    assert current["source_status"] == "updated" and current["origin_note"]["quote"] == ""
    memory = research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision,
        "refresh_origin": True, "state": "confirmed"})
    current = research.serialize_record(memory, reader_user)["data"]
    assert current["source_status"] == "available"
    assert current["sources"][0]["content_hash"] != original_hash
    assert len(current["sources"]) == 2
    assert current["sources"][1]["evidence_span_id"] == str(spans[1].id)
    assert len(current["history"][-1]["data"]["sources"]) == 2
    assert current["history"][-1]["data"]["sources"][0]["content_hash"] == original_hash
    project.refresh_from_db()
    assert memory.state == "confirmed" and research.unpack(project)["confirmed_memory_ids"] == []


def test_scope_revocation_before_embedding_batch_never_sends_private_body(reader_user, monkeypatch):
    from contextlib import nullcontext
    memory = memory_for(reader_user)
    project = project_for(reader_user)
    memory = grant(reader_user, memory, project)
    monkeypatch.setattr("reading.local_analysis.PrivateLocalTransport", lambda *args, **kwargs: nullcontext(None))
    calls = []
    def encode(texts, **kwargs):
        calls.extend(texts)
        if kwargs.get("kind") == "query":
            research.update_memory_usage(reader_user, memory.id, {"expected_revision": memory.revision, "action": "revoke_all"})
        return {"artifact_id": "test-model", "vectors": [[1.0, 0.0] for _ in texts]}
    monkeypatch.setattr("catalog.services.discovery_inference.embed_texts", encode)
    result = research.search_memories(reader_user, "制度", semantic=True,
        context={"kind": "project", "id": str(project.id)})
    assert calls == ["制度"] and result["results"] == []
    memory.refresh_from_db()
    assert not memory.embedding_ciphertext


def test_list_counts_are_server_wide_before_state_filter(api_client, reader_user, admin_user):
    for state in ("confirmed", "confirmed", "proposed", "ignored"):
        memory_for(reader_user, state=state, kind="method")
    memory_for(reader_user, kind="observation")
    memory_for(admin_user, kind="method")
    api_client.force_authenticate(reader_user)
    response = api_client.get("/api/reading/research-memories/", {"q": "制度", "kind": "method", "state": "confirmed", "order": "newest"})
    assert response.status_code == 200
    assert response.data["count"] == 2
    assert response.data["counts"] == {"total": 4, "confirmed": 2, "proposed": 1, "ignored": 1}
    assert all(row["data"]["kind"] == "method" for row in response.data["results"])
    assert response["Cache-Control"] == "private, no-store"


def test_delete_requires_revision_and_staff_has_no_private_access(api_client, reader_user, admin_user):
    memory = memory_for(reader_user)
    path = f"/api/reading/research-memories/{memory.id}/"
    api_client.force_authenticate(reader_user)
    assert api_client.delete(path, {"expected_revision": 1}, format="json").status_code == 409
    api_client.force_authenticate(admin_user)
    assert api_client.get(path + "usage/").status_code == 404
    assert api_client.delete(path, {"expected_revision": memory.revision}, format="json").status_code == 404
    assert ResearchMemory.objects.filter(pk=memory.id).exists()


def test_research_turn_reminders_disappear_on_revoke_without_changing_public_scope(reader_user, monkeypatch):
    memory = memory_for(reader_user)
    project = project_for(reader_user)
    memory = grant(reader_user, memory, project)
    project.refresh_from_db()
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: None)
    turn = research.start_turn(SimpleNamespace(user=reader_user), project.id, {
        "request_id": str(uuid4()), "expected_revision": project.revision, "question": "社会关系是什么"})
    current = research.serialize_record(turn, reader_user)["data"]
    assert [item["id"] for item in current["memory_reminders"]] == [str(memory.id)]
    assert current["scope"]["kind"] == "library" and current["search_question"] == "社会关系是什么"
    research.update_memory_usage(reader_user, memory.id, {"expected_revision": memory.revision, "action": "revoke_all"})
    current = research.serialize_record(turn, reader_user)["data"]
    assert current["memory_reminders"] == [] and current["memory_reminders_status"] == "authorization_changed"


def test_plan_suggestions_invalidated_and_other_private_content_kept(reader_user):
    memory = memory_for(reader_user)
    plan = PersonalReadingPlan.objects.create(user=reader_user, data_ciphertext=research.pack({
        "goal": "私人目标", "items": [], "use_confirmed_memories": False, "confirmed_memory_ids": []}))
    memory = grant(reader_user, memory, plan, "plan")
    plan.refresh_from_db()
    payload = research.unpack(plan)
    payload.update(memory_reminder_ids=[str(memory.id)], memory_reminder_revisions={str(memory.id): memory.revision}, enhancement_status="candidate")
    plan = research.save_data(plan, payload)
    assert research.plan_suggestions_current(reader_user, research.unpack(plan))
    research.update_memory_usage(reader_user, memory.id, {"expected_revision": memory.revision, "action": "revoke_all"})
    plan.refresh_from_db()
    current = research.serialize_record(plan, reader_user)["data"]
    assert current["goal"] == "私人目标"
    assert current["enhancement_status"] == "authorization_changed"
    assert not current.get("memory_reminder_ids")


def test_legacy_global_off_revokes_all_but_does_not_block_explicit_new_scope(api_client, reader_user):
    memory = memory_for(reader_user)
    project = project_for(reader_user)
    memory = grant(reader_user, memory, project)
    api_client.force_authenticate(reader_user)
    assert api_client.patch("/api/reading/research-account/", {"research_personalization": False}, format="json").status_code == 200
    project.refresh_from_db()
    assert research.unpack(project)["confirmed_memory_ids"] == []
    memory = grant(reader_user, memory, project)
    project.refresh_from_db()
    assert [row.id for row in research.plan_memory_rows(reader_user, research.unpack(project))] == [memory.id]
