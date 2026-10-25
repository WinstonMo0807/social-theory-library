"""Deferred comparison lifecycle acceptance. No provider or production requests."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from reading import research
from reading.research_comparison import start_draft, validate_candidates
from reading.tasks import collect_research_turn
from reading.models import ResearchTurn
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def prepared(user):
    edition, _, spans, _ = fixture_source(count=1)
    project = research.create_project(user, {"request_id": str(uuid4()), "title": "合成比较任务"})
    project = research.change_selection(user, project.id, {"expected_revision": project.revision,
        "action": "add", "references": [{"evidence_span_id": str(spans[0].pk)}]})
    project = research.save_comparison(user, project.id, {"expected_revision": project.revision,
        "dimensions": ["适用条件"], "cells": [{"dimension": "适用条件", "note": "本人原有判断"}]})
    key = research.reference_identity(research.unpack(project)["selections"][0])
    data = {"request_id": str(uuid4()), "expected_revision": project.revision, "dimension": "适用条件", "reference_ids": [key]}
    return project, data, edition


def model_answer(**kwargs):
    evidence = kwargs["payload"]["evidence"]
    row = evidence[0]
    return {"rows": [{"column_id": row["column_id"], "reference_ids": [row["reference_id"]],
                      "note": "合成模型候选，需核对", "evidence_state": "insufficient"}]}, {"provider": "fixture", "model": "fixture"}


def test_reject_invented_cross_column_or_missing_sources():
    evidence = [{"column_id": "edition:a", "reference_id": "one"}, {"column_id": "edition:b", "reference_id": "two"}]
    row = {"column_id": "edition:a", "reference_ids": ["one"], "note": "候选判断", "evidence_state": "candidate"}
    assert validate_candidates({"rows": [row]}, evidence) == [row]
    for change in [{"reference_ids": ["two"]}, {"reference_ids": ["invented"]}, {"reference_ids": []}, {"column_id": "invented"}, {"note": ""}]:
        assert validate_candidates({"rows": [{**row, **change}]}, evidence) == []


def test_generation_keeps_manual_notes_and_exact_request(api_client, reader_user, admin_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args: None)
    monkeypatch.setattr("reading.local_analysis.generate_local", model_answer)
    project, body, _ = prepared(reader_user)
    before = research.unpack(project)["comparison"]
    api_client.force_authenticate(reader_user)
    endpoint = f"/api/reading/research-projects/{project.pk}/comparison-draft/"
    first = api_client.post(endpoint, body, format="json")
    again = api_client.post(endpoint, body, format="json")
    assert first.status_code == again.status_code == 202 and first.data["id"] == again.data["id"]
    turn = project.turns.get(pk=first.data["id"])
    collect_research_turn(str(turn.pk), turn.generation, turn.task_id)
    turn.refresh_from_db()
    assert turn.status == "completed" and research.unpack(turn)["comparison_draft"]["rows"][0]["evidence_state"] == "insufficient"
    project.refresh_from_db()
    assert research.unpack(project)["comparison"] == before
    api_client.force_authenticate(admin_user)
    assert api_client.post(endpoint, body, format="json").status_code == 404


def test_cancel_during_inference_rejects_late_candidate(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args: None)
    project, data, _ = prepared(reader_user)
    turn = start_draft(SimpleNamespace(user=reader_user), project.id, data)

    def cancel_then_answer(**kwargs):
        research.cancel_turn(reader_user, turn.id)
        return model_answer(**kwargs)

    monkeypatch.setattr("reading.local_analysis.generate_local", cancel_then_answer)
    collect_research_turn(str(turn.id), turn.generation, turn.task_id)
    turn.refresh_from_db()
    assert turn.status == "canceled" and research.unpack(turn)["comparison_draft"]["rows"] == []


def test_withdrawal_hides_all_generated_text_but_keeps_private_notes(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args: None)
    monkeypatch.setattr("reading.local_analysis.generate_local", model_answer)
    project, data, edition = prepared(reader_user)
    turn = start_draft(SimpleNamespace(user=reader_user), project.id, data)
    collect_research_turn(str(turn.id), turn.generation, turn.task_id)
    turn.refresh_from_db()
    edition.active_catalog_revision.fulltext_ready = False
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    output = research.serialize_record(turn, reader_user)["data"]["comparison_draft"]
    assert output["source_status"] == "unavailable" and all(row["note"] == "" for row in output["rows"])
    project.refresh_from_db()
    assert research.unpack(project)["comparison"]["cells"][0]["note"] == "本人原有判断"


def test_retry_remains_a_generation_job(api_client, reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args: None)
    project, data, _ = prepared(reader_user)
    turn = start_draft(SimpleNamespace(user=reader_user), project.id, data)
    research.cancel_turn(reader_user, turn.id)
    project.refresh_from_db()
    api_client.force_authenticate(reader_user)
    result = api_client.post(f"/api/reading/research-turns/{turn.id}/retry/", {"request_id": str(uuid4()),
        "expected_revision": project.revision}, format="json")
    assert result.status_code == 202 and result.data["data"]["return_context"]["kind"] == "comparison_draft"
    assert result.data["data"]["comparison_draft"]["reference_ids"] == data["reference_ids"]
    assert result.data["parent_id"] == str(turn.id)


def test_new_generation_obeys_active_task_budget(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args: None)
    project, data, _ = prepared(reader_user)
    for _ in range(3):
        ResearchTurn.objects.create(project=project, status="queued", data_ciphertext=research.pack({}))
    with pytest.raises(research.ResearchConflict):
        start_draft(SimpleNamespace(user=reader_user), project.id, data)
