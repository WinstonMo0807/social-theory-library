"""PDF 198–200 explicit conditions and owner correction; acceptance not yet run."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from reading import research
from reading.models import ResearchMemory, ResearchTurn
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def completed_turn(user):
    edition, _, spans, _ = fixture_source(count=1)
    project = research.create_project(user, {"request_id": str(uuid4()), "title": "合成反证工作区"})
    ref = research.compact_reference(research.resolve_reference({"evidence_span_id": str(spans[0].id)}, user, strict=True))
    statement = {"proposition": "制度总能改善合作"}
    analysis = research.analyze_references(statement, [ref], user)
    turn = ResearchTurn.objects.create(project=project, status="completed", data_ciphertext=research.pack({
        "question": statement["proposition"], "mode": "counterargument", "analysis_statement": statement,
        "analysis": analysis, "result_refs": [ref]}))
    return turn, analysis[0]["id"], edition, spans[0]


def command(turn, candidate, **data):
    return {"expected_revision": turn.revision, "id": candidate, "request_id": str(uuid4()),
        "relation": "qualification", "note": "本人判断：原文只讨论特定对象。", **data}


def test_optional_statement_conditions_can_be_left_blank_or_cleared(api_client, reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    api_client.force_authenticate(reader_user)
    response = api_client.post(f"/api/reading/research-projects/{project.pk}/turns/", {
        "request_id": str(uuid4()), "expected_revision": project.revision,
        "question": "需要检验的合成判断", "mode": "counterargument",
        "statement": {"proposition": "需要检验的合成判断", "subject": "", "predicate": "",
                      "object": "", "modality": "", "geographic_scope": "", "temporal_scope": "", "qualifiers": []},
    }, format="json")
    assert response.status_code == 202
    assert response.data["data"]["query_plan"]["method"] == "original_proposition"
    assert response.data["data"]["statement"]["subject"] == ""


def test_counter_conditions_are_query_context_not_publication_filters(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    statement = {"proposition": "制度总能改善合作", "population_scope": {"label": "农村合作社"},
        "geographic_scope": {"label": "中国"}, "temporal_scope": {"label": "2015—2024"}, "qualifiers": ["自愿参与"]}
    turn = research.start_turn(SimpleNamespace(user=reader_user), project.id, {"request_id": str(uuid4()),
        "expected_revision": project.revision, "question": statement["proposition"], "mode": "counterargument", "statement": statement})
    data = research.unpack(turn)
    assert data["question"] == data["search_question"] == statement["proposition"]
    assert data["statement"] == data["analysis_statement"] == statement
    for value in ["农村合作社", "中国", "2015—2024", "自愿参与"]:
        assert value in data["query_plan"]["query"]
    assert data["query_plan"]["method"] == "explicit_conditions"
    assert not any("year" in key for key in data["scope"]["filters"])


def test_worker_uses_explicit_conditions_even_in_a_followup_branch(reader_user, monkeypatch):
    from reading.tasks import collect_research_turn
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    parent = ResearchTurn.objects.create(project=project, status="completed", data_ciphertext=research.pack({
        "question": "前一轮问题", "scope": research.unpack(project)["scope"]}))
    turn = research.start_turn(SimpleNamespace(user=reader_user), project.id, {"request_id": str(uuid4()),
        "expected_revision": project.revision, "parent_id": str(parent.id), "question": "制度总能改善合作", "mode": "counterargument",
        "statement": {"proposition": "制度总能改善合作", "qualifiers": ["自愿参与"]}})
    calls = []
    def unavailable_session(request, query, filters):
        calls.append(query)
        raise LookupError("synthetic_queue_failure")
    monkeypatch.setattr("catalog.services.discovery_sessions.create_session", unavailable_session)
    monkeypatch.setattr("reading.local_analysis.plan_followup", lambda *args: pytest.fail("Explicit counter conditions must not be rewritten"))
    collect_research_turn(str(turn.id), turn.generation, turn.task_id)
    turn.refresh_from_db()
    assert calls == [research.unpack(turn)["query_plan"]["query"]]
    assert "自愿参与" in calls[0]
    assert turn.status == "failed"  # The deliberate queue failure is not hidden as an empty result.


def test_overlong_conditions_rejected_without_truncating_or_creating_turn(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args, **kwargs: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    before = ResearchTurn.objects.count()
    with pytest.raises(ValidationError):
        research.start_turn(SimpleNamespace(user=reader_user), project.id, {"request_id": str(uuid4()),
            "expected_revision": project.revision, "question": "论" * 1190, "mode": "counterargument",
            "statement": {"proposition": "论" * 1190, "qualifiers": ["限定条件" * 10]}})
    assert ResearchTurn.objects.count() == before


def test_unrelated_decision_keeps_system_candidate_and_attribution_history(reader_user):
    turn, candidate, _, _ = completed_turn(reader_user)
    initial = research.unpack(turn)["analysis"][0]
    first = research.decide_analysis(reader_user, turn.id, command(turn, candidate, relation="unrelated",
        attribution="quoted_claim", scope_note="转引对象不同"))
    first_row = research.unpack(first)["analysis"][0]
    assert first_row["relation"] == "unrelated"
    assert first_row["decision"]["attribution"] == "quoted_claim"
    changed = research.decide_analysis(reader_user, first.id, command(first, candidate, relation="qualification"))
    row = research.unpack(changed)["analysis"][0]
    assert row["rule_signal"] == initial["rule_signal"]
    assert row["candidate_statement"] == initial["candidate_statement"]
    assert row["decision_history"][0]["decision"] == first_row["decision"]
    assert row["decision"]["relation"] == "qualification"
    assert ResearchMemory.objects.filter(user=reader_user).count() == 0


def test_explicit_note_and_decision_are_idempotent_and_note_is_not_authorized(reader_user):
    turn, candidate, _, _ = completed_turn(reader_user)
    data = command(turn, candidate, save_as_note=True)
    saved = research.decide_analysis(reader_user, turn.id, data)
    replay = research.decide_analysis(reader_user, turn.id, data)
    assert replay.revision == saved.revision
    row = research.unpack(saved)["analysis"][0]
    memory = ResearchMemory.objects.get(pk=row["decision"]["memory_id"], user=reader_user)
    assert memory.state == "proposed"
    assert research.unpack(memory)["body"] == data["note"]
    assert research.unpack(memory)["origin"]["turn_id"] == str(turn.id)
    assert research.serialize_record(memory, reader_user)["data"]["usage_scopes"] == []
    assert ResearchMemory.objects.filter(user=reader_user).count() == 1
    assert "analysis_requests" not in research.serialize_record(saved, reader_user)["data"]
    with pytest.raises(research.ResearchConflict):
        research.decide_analysis(reader_user, turn.id, {**data, "note": "不同的判断"})


def test_failed_note_save_rolls_back_decision(reader_user, monkeypatch):
    turn, candidate, _, _ = completed_turn(reader_user)
    original = research.unpack(turn)
    def rejected_note(*args, **kwargs):
        raise ValidationError("请先开启保存个人笔记")
    monkeypatch.setattr(research, "create_memory", rejected_note)
    with pytest.raises(ValidationError):
        research.decide_analysis(reader_user, turn.id, command(turn, candidate, save_as_note=True))
    turn.refresh_from_db()
    assert research.unpack(turn) == original
    assert ResearchMemory.objects.filter(user=reader_user).count() == 0


@pytest.mark.parametrize("extra", [{"note": ""}, {"attribution": "guessed_author"}, {"save_as_note": True, "request_id": None}])
def test_invalid_decision_never_saves_partial_state(reader_user, extra):
    turn, candidate, _, _ = completed_turn(reader_user)
    with pytest.raises(ValidationError):
        research.decide_analysis(reader_user, turn.id, command(turn, candidate, **extra))
    turn.refresh_from_db()
    assert research.unpack(turn)["analysis"][0]["decision"] is None


def test_decision_owner_and_stale_revision_are_enforced(reader_user, admin_user):
    turn, candidate, _, _ = completed_turn(reader_user)
    with pytest.raises(NotFound):
        research.decide_analysis(admin_user, turn.id, command(turn, candidate))
    with pytest.raises(research.ResearchConflict):
        research.decide_analysis(reader_user, turn.id, command(turn, candidate, expected_revision=turn.revision + 1))


def test_unavailable_source_cannot_confirm_but_owner_can_clear_and_keep_note(reader_user):
    turn, candidate, _, span = completed_turn(reader_user)
    saved = research.decide_analysis(reader_user, turn.id, command(turn, candidate, save_as_note=True))
    memory_id = research.unpack(saved)["analysis"][0]["decision"]["memory_id"]
    span.is_stale = True
    span.save(update_fields=["is_stale"])
    visible = research.serialize_record(saved, reader_user)["data"]["analysis"][0]
    assert visible["status"] == "source_unavailable" and "quote" not in visible["reference"]
    assert "candidate_statement" not in visible and "rule_signal" not in visible
    assert visible["decision"]["memory_id"] == memory_id
    with pytest.raises(ValidationError):
        research.decide_analysis(reader_user, saved.id, command(saved, candidate))
    cleared = research.decide_analysis(reader_user, saved.id, {"expected_revision": saved.revision,
        "id": candidate, "action": "clear", "request_id": str(uuid4())})
    data = research.unpack(cleared)["analysis"][0]
    assert data["decision"] is None and data["decision_history"][0]["decision"]["memory_id"] == memory_id
    assert ResearchMemory.objects.filter(pk=memory_id, user=reader_user).exists()


def test_public_metadata_disappears_with_withdrawn_source(reader_user):
    _, _, edition, span = completed_turn(reader_user)
    current = research.resolve_reference({"evidence_span_id": str(span.id)}, reader_user)
    assert "publication_year" in current and "cover_url" in current
    edition.active_catalog_revision.fulltext_ready = False
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    stale = research.resolve_reference(research.compact_reference(current), reader_user)
    assert stale["source_status"] == "unavailable"
    assert not any(key in stale for key in ["quote", "cover_url", "publication_year"])


def test_counter_history_filters_before_pagination_and_sorts_latest(api_client, reader_user, admin_user):
    first, _, _, _ = completed_turn(reader_user)
    for _ in range(27):
        ResearchTurn.objects.create(project=first.project, status="completed", data_ciphertext=research.pack({
            "question": "合成普通检索", "mode": "search"}))
    latest = ResearchTurn.objects.create(project=first.project, status="completed", data_ciphertext=research.pack({
        "question": "新的反证命题", "mode": "counterargument"}))
    api_client.force_authenticate(reader_user)
    url = f"/api/reading/research-projects/{first.project_id}/turns/"
    response = api_client.get(url, {"mode": "counterargument", "order": "newest"})
    assert response.status_code == 200
    assert response.data["count"] == 2
    assert [row["id"] for row in response.data["results"]] == [str(latest.id), str(first.id)]
    assert api_client.get(url, {"mode": "unknown"}).status_code == 400
    api_client.force_authenticate(admin_user)
    assert api_client.get(url, {"mode": "counterargument"}).status_code == 404
