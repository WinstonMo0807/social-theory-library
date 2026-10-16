"""Explainable planning estimates, never measured learning outcomes."""
from graphlib import CycleError, TopologicalSorter
import math
import re

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Asset, Page
from .models import ReadingProgress

LEVELS = {"beginner": 0, "intermediate": 1, "advanced": 2}
POLICY_VERSION = "private-reading-budget-v1"
MAX_SESSIONS = 1000


def _integer(value, field, minimum, maximum):
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValidationError({field: f"请输入 {minimum} 至 {maximum} 的整数。"})
    return value


def planning_policy(data):
    level = data.get("reading_level", "beginner")
    if not isinstance(level, str) or level not in LEVELS:
        raise ValidationError({"reading_level": "请选择入门、进阶或深入。"})
    budget = data.get("budget_minutes")
    period = "total"
    label = str(data.get("time_budget", "") or "").strip()
    if budget is None and label:
        match = re.fullmatch(r"(?:(每周|每天|总计|合计)\s*)?(\d+(?:\.\d+)?)\s*(分钟|分|minutes?|mins?|小时|hours?|hrs?|h)", label, re.I)
        if not match:
            raise ValidationError({"time_budget": "请给出明确分钟/小时，或用 budget_minutes 指定本轮预算。"})
        amount = float(match.group(2))
        budget = math.ceil(amount * (60 if match.group(3).lower() in {"小时", "hour", "hours", "hr", "hrs", "h"} else 1))
        period = {"每周": "week", "每天": "day"}.get(match.group(1), "total")
    if budget is not None:
        budget = _integer(budget, "budget_minutes", 1, 100000)
    pace = data.get("reading_pace", {})
    if not isinstance(pace, dict):
        raise ValidationError({"reading_pace": "阅读速度需要对象。"})
    prefer_unread = data.get("prefer_unread", True)
    if not isinstance(prefer_unread, bool):
        raise ValidationError({"prefer_unread": "需要布尔值。"})
    return {"version": POLICY_VERSION, "reading_level": level, "budget_minutes": budget, "budget_period": period,
        "session_minutes": _integer(data.get("session_minutes", 30), "session_minutes", 5, 480),
        "prefer_unread": prefer_unread,
        "pace": {"cjk_chars_per_minute": _integer(pace.get("cjk_chars_per_minute", 300), "cjk_chars_per_minute", 20, 3000),
                 "words_per_minute": _integer(pace.get("words_per_minute", 160), "words_per_minute", 20, 1500),
                 "fallback_minutes_per_page": _integer(pace.get("fallback_minutes_per_page", 4), "fallback_minutes_per_page", 1, 60)},
        "notice": "速度、难度系数和阅读时长是可修改的规划假设，不是经过模型评估的实际阅读表现。"}


def _counts(value):
    cjk = len(re.findall(r"[\u3400-\u9fff]", value))
    words = re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", value)
    sentences = [row for row in re.split(r"[。！？.!?]+", value) if row.strip()]
    return {"cjk_chars": cjk, "words": len(words), "sentence_count": len(sentences),
            "long_word_count": sum(len(word) >= 9 for word in words),
            "mean_sentence_units": round((cjk + len(words)) / max(1, len(sentences)), 2)}


def _difficulty(counts, declared=None):
    if declared in LEVELS:
        return {"level": declared, "basis": "public_path_declared_level", "signals": {},
                "notice": "公共路径策划者声明的层级；不等于对单本书的实测难度。"}
    if counts["cjk_chars"] + counts["words"] == 0:
        return {"level": None, "basis": "not_assessed", "signals": {}, "notice": "没有可用于难度提示的文字，请本人判断。"}
    signals = counts
    complexity = int(counts["mean_sentence_units"] > 45) + int(counts["words"] > 0 and counts["long_word_count"] / counts["words"] > 0.22)
    return {"level": ["beginner", "intermediate", "advanced"][min(2, complexity)], "basis": "text_features_heuristic",
            "signals": signals, "notice": "句长与词形的规则提示，不衡量理论难度；本人可以改写。"}


def estimate_items(items, user, policy, *, overrides=None):
    from .research import access_for, resolve_reference
    from catalog.services.discovery_sources import source_queryset
    preferences = getattr(getattr(user, "reader_profile", None), "reading_preferences", {}) or {}
    policy["personalization_enabled"] = preferences.get("research_personalization", True) is not False
    if not policy["personalization_enabled"]:
        policy["prefer_unread"] = False
    overrides = [] if overrides is None else overrides
    if not isinstance(overrides, list) or len(overrides) > 400:
        raise ValidationError({"item_estimates": "最多提供 400 项本人估计。"})
    by_work = {row["work_id"]: row for row in items}
    supplied = {}
    for override in overrides:
        if (not isinstance(override, dict) or not isinstance(override.get("work_id"), str)
                or override["work_id"] not in by_work):
            raise ValidationError({"item_estimates": "本人估计必须指向本计划材料。"})
        if override.get("difficulty") is not None and (
                not isinstance(override["difficulty"], str) or override["difficulty"] not in LEVELS):
            raise ValidationError({"difficulty": "难度层级无效。"})
        if "minutes" in override:
            _integer(override["minutes"], "minutes", 1, 100000)
        supplied[override["work_id"]] = override
    for item in items:
        if item.get("status") == "completed" and item.get("planning_estimate"):
            continue
        reference = item.get("reference")
        text_value, sampled_pages, total_pages = "", [], 0
        source = {key: item.get(key) for key in ("edition_id", "asset_id", "document_revision_id")}
        if reference:
            current = resolve_reference(reference, user)
            item["planning_source_available"] = current["source_status"] == "available"
            source.update({key: current.get(key) for key in ("asset_id", "document_revision_id", "content_hash")})
            if current["source_status"] == "available":
                text_value = current["quote"]
            method = "selected_text_counts"
            item["reading_scope"] = "selected_passage"
        else:
            item["planning_source_available"] = source_queryset("edition", access_for(user)).filter(pk=item["edition_id"],
                active_catalog_revision__reader_asset_id=item.get("asset_id"),
                active_catalog_revision__document_revision_id=item.get("document_revision_id")).exists()
            asset = Asset.objects.filter(pk=item.get("asset_id")).first() if item["planning_source_available"] else None
            total_pages = asset.page_count if asset else 0
            if not total_pages and asset:
                total_pages = asset.pages.count()
            if total_pages:
                sampled_pages = sorted({1 + round(index * (total_pages - 1) / min(11, total_pages - 1)) for index in range(min(12, total_pages))}) if total_pages > 1 else [1]
                sample_rows = list(Page.objects.filter(asset_id=item.get("asset_id"), index__in=sampled_pages).order_by("index").values_list("index", "text"))
                sampled_pages = [row[0] for row in sample_rows]
                text_value = "\n".join(row[1] for row in sample_rows)
            method = "sampled_file_pages" if text_value.strip() else "file_page_count_assumption"
            item["reading_scope"] = "whole_file"
        counts = _counts(text_value)
        difficulty = _difficulty(counts, item.get("declared_difficulty"))
        override = supplied.get(item["work_id"]) or item.get("owner_estimate", {})
        if override:
            item["owner_estimate"] = dict(override)
            if override.get("difficulty"):
                difficulty = {"level": override["difficulty"], "basis": "owner_estimate", "signals": {}, "notice": "本人的难度判断。"}
        pace = policy["pace"]
        minutes = counts["cjk_chars"] / pace["cjk_chars_per_minute"] + counts["words"] / pace["words_per_minute"]
        if not reference:
            minutes = minutes * total_pages / max(1, len(sampled_pages)) if text_value.strip() else total_pages * pace["fallback_minutes_per_page"]
        gap = max(0, LEVELS.get(difficulty["level"], LEVELS[policy["reading_level"]]) - LEVELS[policy["reading_level"]])
        multiplier = (1.0, 1.35, 1.7)[gap]
        estimated = max(1, math.ceil(minutes * multiplier)) if minutes else None
        if override.get("minutes"):
            estimated, method = override["minutes"], "owner_estimate"
        item["difficulty"] = difficulty
        item["estimated_minutes"] = estimated
        item["planning_estimate"] = {"method": method, "minutes": estimated, "counts": counts,
            "sampled_pages": sampled_pages, "total_pages": total_pages, "source": source,
            "difficulty_multiplier": multiplier, "pace_assumptions": pace, "estimated_at": timezone.now().isoformat(),
            "limits": "选段按实际字词；整本按至多12页采样外推，缺文字时按每页假设。页数、速度与难度估计都不证明阅读理解。"}
        progress = ReadingProgress.objects.filter(user=user, asset_id=source.get("asset_id")).order_by("-updated_at").first() if policy["personalization_enabled"] else None
        item["prior_reading"] = {"recorded": bool(progress), "progress_ratio": progress.progress_ratio if progress else None,
            "current_page": progress.current_page if progress else None, "updated_at": progress.updated_at.isoformat() if progress else None,
            "understanding": "not_inferred"}
    return items


def schedule_plan(items, prerequisites, policy, *, preserve_order=False):
    by_work = {row["work_id"]: row for row in items}
    graph = {key: set() for key in by_work}
    for edge in prerequisites:
        graph[edge["work_id"]].add(edge["requires_work_id"])
    sorter = TopologicalSorter(graph)
    try:
        sorter.prepare()
    except CycleError as exc:
        raise ValidationError({"prerequisites": "先修关系有环，请先修正。"}) from exc
    positions = {row["work_id"]: index for index, row in enumerate(items)}
    ready, order = [], []
    def priority(key):
        item = by_work[key]
        finished = item.get("status") == "completed"
        already_read = (item.get("prior_reading", {}).get("progress_ratio") or 0) >= 0.98
        level = LEVELS.get(item["difficulty"]["level"], LEVELS[policy["reading_level"]])
        return (not finished, already_read if policy["prefer_unread"] else False,
            abs(level - LEVELS[policy["reading_level"]]),
            level, item.get("estimated_minutes") or 100001, positions[key])
    while sorter.is_active():
        ready.extend(sorter.get_ready())
        ready.sort(key=(lambda key: positions[key]) if preserve_order else priority)
        key = ready.pop(0)
        order.append(key)
        sorter.done(key)
    ordered = [by_work[key] for key in order]
    # Completed records retain all material/progress/estimate fields and their
    # relative order; only future material is rescheduled.
    complete = [item for item in items if item.get("status") == "completed"]
    ordered = complete + [item for item in ordered if item.get("status") != "completed"]
    available = policy["budget_minutes"]
    consumed = 0
    selected, sessions, unknown, unscheduled_minutes = set(), [], 0, 0
    session_size = policy["session_minutes"]
    for item in ordered:
        key = item["work_id"]
        if item.get("status") == "completed":
            selected.add(key)
            item["budget_assignment"] = {"included": True, "reason": "completed_preserved", "planned_minutes": 0}
            continue
        minutes = item.get("estimated_minutes")
        reason = "within_budget"
        if item.get("status") == "skipped":
            reason = "owner_skipped"
        elif item.get("planning_source_available") is False:
            reason = "source_unavailable"
        elif not graph[key].issubset(selected):
            reason = "prerequisite_outside_budget"
        elif minutes is None and available is not None:
            reason = "duration_unknown"
        elif available is not None and consumed + (minutes or 0) > available:
            reason = "over_budget"
        included = reason == "within_budget"
        item["budget_assignment"] = {"included": included, "reason": reason, "planned_minutes": minutes if included else 0}
        if not included:
            continue
        selected.add(key)
        if minutes is None:
            unknown += 1
            continue
        consumed += minutes
        remaining = minutes
        while remaining:
            if not sessions or sessions[-1]["minutes"] >= session_size:
                if len(sessions) >= MAX_SESSIONS:
                    unscheduled_minutes += remaining
                    break
                sessions.append({"index": len(sessions) + 1, "minutes": 0, "items": []})
            amount = min(remaining, session_size - sessions[-1]["minutes"])
            sessions[-1]["items"].append({"item_id": item["id"], "planned_minutes": amount})
            sessions[-1]["minutes"] += amount
            remaining -= amount
    return ordered, {"version": POLICY_VERSION, "budget_minutes": available, "budget_period": policy["budget_period"],
        "planned_minutes": consumed, "unknown_duration_count": unknown,
        "deferred_item_ids": [item["id"] for item in ordered if not item["budget_assignment"]["included"]],
        "sessions": sessions, "session_limit": MAX_SESSIONS, "unscheduled_minutes": unscheduled_minutes,
        "notice": "预计时长用于安排本轮材料，超预算材料仍保留；分次明细最多1000次，余量单列。实际阅读速度可与估计不同。"}
