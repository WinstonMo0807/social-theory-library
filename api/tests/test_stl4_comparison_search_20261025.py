"""Deferred acceptance: comparison gap retries keep their origin and old judgments."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from reading import research
from reading.models import ResearchProject, ResearchTurn

pytestmark = pytest.mark.django_db


def test_comparison_retry_retains_context_without_overwriting_notes(api_client, reader_user, admin_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "合成比较"})
    project = research.save_comparison(reader_user, project.id, {"expected_revision": project.revision,
        "dimensions": ["适用条件"], "cells": [{"dimension": "适用条件", "note": "本人待核对的判断", "reference_ids": []}]})
    before = research.unpack(project)["comparison"]
    context = {"kind": "comparison_gap", "dimension": "适用条件", "column_id": "retained:unassigned"}
    turn = research.start_turn(SimpleNamespace(user=reader_user), project.id, {"expected_revision": project.revision,
        "request_id": str(uuid4()), "question": "需要哪些支持材料", "return_context": context})
    turn.status = "failed"
    turn.save(update_fields=["status"])
    project.refresh_from_db()
    api_client.force_authenticate(reader_user)
    body = {"expected_revision": project.revision, "request_id": str(uuid4())}
    endpoint = f"/api/reading/research-turns/{turn.id}/retry/"
    first = api_client.post(endpoint, body, format="json")
    again = api_client.post(endpoint, body, format="json")
    assert first.status_code == again.status_code == 202
    assert first.data["id"] == again.data["id"]
    assert first.data["data"]["return_context"] == context
    assert first.data["parent_id"] == str(turn.id)
    assert ResearchTurn.objects.filter(project=project).count() == 2
    assert research.unpack(ResearchProject.objects.get(pk=project.pk))["comparison"] == before
    api_client.force_authenticate(admin_user)
    assert api_client.post(endpoint, body, format="json").status_code == 404


def test_retry_without_comparison_context_stays_compatible(api_client, reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    turn = research.start_turn(SimpleNamespace(user=reader_user), project.id, {"expected_revision": project.revision,
        "request_id": str(uuid4()), "question": "普通研究问题"})
    turn.status = "canceled"
    turn.save(update_fields=["status"])
    project.refresh_from_db()
    api_client.force_authenticate(reader_user)
    result = api_client.post(f"/api/reading/research-turns/{turn.id}/retry/", {
        "expected_revision": project.revision, "request_id": str(uuid4())}, format="json")
    assert result.status_code == 202 and result.data["data"]["return_context"] == {}
