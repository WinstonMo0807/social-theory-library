"""PDF 201–204 plan contracts. Authored for the later unified acceptance run."""
from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from reading import research
from reading.models import PersonalReadingPlan, ResearchMemory
from reading.plan_rules import planning_policy, schedule_plan
from reading.tasks import enhance_reading_plan
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def make_plan(user, monkeypatch, **extra):
    _, _, spans, _ = fixture_source(count=1)
    monkeypatch.setattr("reading.tasks.enqueue_plan_enhancement", lambda *args: None)
    return research.generate_plan(user, {"request_id": str(uuid4()), "goal": "比较组织关系",
        "references": [{"evidence_span_id": str(spans[0].id)}], **extra})


def test_weekly_budget_and_completed_slots_are_preserved():
    policy = planning_policy({"weekly_minutes": 45, "duration_weeks": 2, "session_minutes": 30})
    def item(key, minutes, status="pending"):
        return {"id": key, "work_id": key, "status": status, "estimated_minutes": minutes,
            "difficulty": {"level": "beginner"}, "planning_source_available": True}
    items = [item("long", 60), item("finished", 20, "completed"), item("short", 30)]
    result, schedule = schedule_plan(deepcopy(items), [], policy)
    assert [row["id"] for row in result] == ["short", "finished", "long"]
    assert result[1]["estimated_minutes"] == 20
    assert schedule["planned_minutes"] == 90 and schedule["budget_minutes"] == 90
    assert sum(row["minutes"] for row in schedule["sessions"] if row["week"] == 1) == 45
    assert sum(row["minutes"] for row in schedule["sessions"] if row["week"] == 2) == 45
    assert max(row["minutes"] for row in schedule["sessions"]) <= 30
    with pytest.raises(ValidationError):
        planning_policy({"weekly_minutes": 45})
    with pytest.raises(ValidationError):
        planning_policy({"weekly_minutes": 10080, "duration_weeks": 52})


def test_preview_has_no_persistent_effect_and_conflict_keeps_saved_plan(reader_user, admin_user, monkeypatch):
    plan = make_plan(reader_user, monkeypatch)
    before, revision = research.unpack(plan), plan.revision
    preview = research.update_plan(reader_user, plan.id, {"expected_revision": revision, "preview": True,
        "goal": "预览问题", "weekly_minutes": 60, "duration_weeks": 3, "optimize_order": True})
    assert research.unpack(preview)["planning_policy"]["budget_minutes"] == 180
    plan.refresh_from_db()
    assert research.unpack(plan) == before and plan.revision == revision
    saved = research.update_plan(reader_user, plan.id, {"expected_revision": revision, "goal": "本人更新问题"})
    with pytest.raises(research.ResearchConflict):
        research.update_plan(reader_user, plan.id, {"expected_revision": revision, "goal": "过期窗口"})
    from rest_framework.exceptions import NotFound
    with pytest.raises(NotFound):
        research.update_plan(admin_user, plan.id, {"expected_revision": saved.revision, "preview": True})
    plan.refresh_from_db()
    assert research.unpack(plan)["goal"] == "本人更新问题"


def test_completed_cannot_be_unlocked_and_replaced_in_same_patch(reader_user, monkeypatch):
    plan = make_plan(reader_user, monkeypatch)
    item = research.unpack(plan)["items"][0]
    plan = research.update_plan(reader_user, plan.id, {"expected_revision": plan.revision,
        "item_id": item["id"], "status": "completed"})
    with pytest.raises(research.ResearchConflict):
        research.update_plan(reader_user, plan.id, {"expected_revision": plan.revision,
            "item_id": item["id"], "status": "pending", "reference": item["reference"]})
    saved = research.update_plan(reader_user, plan.id, {"expected_revision": plan.revision,
        "item_id": item["id"], "note": "完成后补充的问题"})
    assert research.unpack(saved)["items"][0]["status"] == "completed"
    assert research.unpack(saved)["items"][0]["note"] == "完成后补充的问题"


def test_memories_are_opt_in_and_revoked_during_worker_never_return(reader_user, admin_user, monkeypatch):
    own = ResearchMemory.objects.create(user=reader_user, state="confirmed", data_ciphertext=research.pack({"body": "私有认识", "sources": []}))
    foreign = ResearchMemory.objects.create(user=admin_user, state="confirmed", data_ciphertext=research.pack({"body": "他人认识", "sources": []}))
    with pytest.raises(ValidationError):
        research.plan_memory_permissions(reader_user, {"use_confirmed_memories": True, "confirmed_memory_ids": [str(foreign.id)]})
    plan = make_plan(reader_user, monkeypatch)
    calls = []
    def analyze(payload, reminders):
        calls.append(reminders)
        return [], {"status": "completed"}
    monkeypatch.setattr("reading.local_analysis.propose_plan_labels", analyze)
    enhance_reading_plan(str(plan.id), plan.revision)
    assert calls == [[]]
    plan.refresh_from_db()
    plan = research.update_plan(reader_user, plan.id, {"expected_revision": plan.revision,
        "use_confirmed_memories": True, "confirmed_memory_ids": [str(own.id)]})
    payload = research.unpack(plan)
    payload["enhancement_status"] = "queued"
    plan = research.save_data(plan, payload)
    def revoke_during_analysis(payload, reminders):
        assert [row["id"] for row in reminders] == [str(own.id)]
        ResearchMemory.objects.filter(pk=own.id).update(state="ignored")
        item = payload["items"][0]
        return [{"item_id": item["id"], "stage": "候选阶段", "reason": "候选理由", "learning_goal": "候选目标"}], {"status": "completed"}
    monkeypatch.setattr("reading.local_analysis.propose_plan_labels", revoke_during_analysis)
    enhance_reading_plan(str(plan.id), plan.revision)
    plan.refresh_from_db()
    data = research.serialize_record(plan, reader_user)["data"]
    assert data["enhancement_status"] == "authorization_changed"
    assert not any(row.get("model_suggestion") for row in data["items"])
    assert PersonalReadingPlan.objects.filter(pk=plan.id, user=reader_user).exists()
