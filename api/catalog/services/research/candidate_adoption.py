from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import (
    DebateCandidate,
    IntelligenceFeedback,
    KnowledgeNode,
    KnowledgePublicationStatus,
    ReadingPath,
    ReadingPathCandidate,
    ReadingPathItem,
    ReadingPathStage,
    Work,
)

from .feedback import record_intelligence_feedback


def _unique_slug(model, value: str) -> str:
    max_length = model._meta.get_field("slug").max_length
    base = slugify(value, allow_unicode=False) or "editorial-draft"
    candidate = base[:max_length]
    suffix = 2
    while model.objects.filter(slug=candidate).exists():
        marker = f"-{suffix}"
        candidate = f"{base[: max_length - len(marker)]}{marker}"
        suffix += 1
    return candidate


def _require_editor(actor) -> None:
    if not actor or not getattr(actor, "is_authenticated", False):
        raise PermissionError("候选决定必须记录真实 Editor。")


@transaction.atomic
def decide_debate_candidate(
    *,
    candidate: DebateCandidate,
    decision: str,
    actor,
    title: str = "",
    canonical_question: str = "",
    summary: str = "",
    review_note: str = "",
) -> DebateCandidate:
    _require_editor(actor)
    if decision not in IntelligenceFeedback.Decision.values:
        raise ValueError("未知的候选决定。")
    locked = DebateCandidate.objects.select_for_update().get(pk=candidate.pk)
    if locked.status != DebateCandidate.Status.PENDING:
        raise ValueError("该 DebateCandidate 已经有人工决定。")
    now = timezone.now()
    adopted_node = None
    if decision in {IntelligenceFeedback.Decision.ACCEPT, IntelligenceFeedback.Decision.ACCEPT_WITH_EDIT}:
        final_title = str(title or locked.title).strip()
        final_question = str(canonical_question or locked.canonical_question).strip()
        final_summary = str(summary or locked.summary).strip()
        if not final_title or not final_question:
            raise ValueError("采用 DebateCandidate 前必须确认标题和 canonical question。")
        adopted_node = locked.suggested_node
        if adopted_node and adopted_node.node_type != KnowledgeNode.NodeType.DEBATE:
            raise ValueError("suggested_node 必须是 Debate KnowledgeNode。")
        if adopted_node and adopted_node.status == KnowledgePublicationStatus.PUBLISHED:
            raise ValueError("已发布 Debate 必须通过 EditorialRevision 修改。")
        if adopted_node is None:
            adopted_node = KnowledgeNode.objects.create(
                node_type=KnowledgeNode.NodeType.DEBATE,
                canonical_name_zh=final_title,
                slug=_unique_slug(KnowledgeNode, final_title),
                summary=final_summary,
                core_questions=[final_question],
                status=KnowledgePublicationStatus.DRAFT,
                created_by=actor,
            )
        else:
            adopted_node.canonical_name_zh = final_title
            adopted_node.summary = final_summary
            adopted_node.core_questions = [final_question]
            adopted_node.save(update_fields=["canonical_name_zh", "summary", "core_questions", "updated_at"])
        locked.suggested_node = adopted_node
        locked.status = DebateCandidate.Status.ADOPTED
    elif decision == IntelligenceFeedback.Decision.REJECT:
        locked.status = DebateCandidate.Status.REJECTED
    else:
        locked.status = DebateCandidate.Status.DEFERRED
    locked.reviewed_by = actor
    locked.reviewed_at = now
    locked.review_note = review_note
    locked.save(update_fields=["suggested_node", "status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    record_intelligence_feedback(
        reviewer=actor,
        task_profile_key="debate_discovery",
        candidate_type="debate_candidate",
        candidate_id=str(locked.id),
        decision=decision,
        original_payload={
            "title": candidate.title,
            "canonical_question": candidate.canonical_question,
            "summary": candidate.summary,
        },
        edited_payload={
            "title": title,
            "canonical_question": canonical_question,
            "summary": summary,
            "draft_node_id": str(adopted_node.id) if adopted_node else "",
        },
    )
    return locked


@transaction.atomic
def decide_reading_path_candidate(
    *,
    candidate: ReadingPathCandidate,
    decision: str,
    actor,
    title: str = "",
    target_audience: str = "",
    learning_goal: str = "",
    stages: list | None = None,
    review_note: str = "",
) -> ReadingPathCandidate:
    _require_editor(actor)
    if decision not in IntelligenceFeedback.Decision.values:
        raise ValueError("未知的候选决定。")
    locked = ReadingPathCandidate.objects.select_for_update().get(pk=candidate.pk)
    if locked.status != ReadingPathCandidate.Status.PENDING:
        raise ValueError("该 ReadingPathCandidate 已经有人工决定。")
    now = timezone.now()
    adopted_path = None
    final_stages = list(stages if stages is not None else locked.stages)
    if decision in {IntelligenceFeedback.Decision.ACCEPT, IntelligenceFeedback.Decision.ACCEPT_WITH_EDIT}:
        final_title = str(title or locked.title).strip()
        final_audience = str(target_audience or locked.target_audience).strip()
        final_goal = str(learning_goal or locked.learning_goal).strip()
        if not final_title or not final_audience or not final_goal or not final_stages:
            raise ValueError("采用 ReadingPathCandidate 前必须确认受众、目标和完整阶段。")
        adopted_path = ReadingPath.objects.create(
            title=final_title,
            slug=_unique_slug(ReadingPath, final_title),
            introduction=final_goal,
            learning_goal=final_goal,
            audience=final_audience,
            status=KnowledgePublicationStatus.DRAFT,
            created_by=actor,
        )
        item_count = 0
        for stage_position, stage_payload in enumerate(final_stages, start=1):
            if not isinstance(stage_payload, dict):
                raise ValueError("Reading Path stage 必须是对象。")
            stage_name = str(stage_payload.get("name") or f"阶段 {stage_position}").strip()
            stage_description = str(stage_payload.get("goal") or stage_payload.get("description") or "").strip()
            stage = ReadingPathStage.objects.create(
                reading_path=adopted_path,
                name=stage_name,
                description=stage_description,
                position=stage_position,
            )
            for item_position, item in enumerate(stage_payload.get("works") or [], start=1):
                if not isinstance(item, dict) or not item.get("work_id"):
                    raise ValueError("Reading Path 的每一项必须包含真实 work_id。")
                work = Work.objects.filter(pk=item["work_id"]).first()
                if work is None:
                    raise ValueError(f"馆藏 Work 不存在：{item['work_id']}")
                item_count += 1
                ReadingPathItem.objects.create(
                    reading_path=adopted_path,
                    stage=stage,
                    stage_name=stage_name,
                    stage_description=stage_description,
                    work=work,
                    recommendation_reason=str(item.get("reason") or "").strip(),
                    prerequisite=str(item.get("prerequisite") or "").strip(),
                    position=item_position,
                    reading_order=item_count,
                    is_required=bool(item.get("required", False)),
                    editorial_note=str(item.get("prerequisite") or "").strip(),
                )
        if item_count == 0:
            raise ValueError("Reading Path 至少需要一本真实馆藏作品。")
        locked.adopted_reading_path = adopted_path
        locked.status = ReadingPathCandidate.Status.ADOPTED
    elif decision == IntelligenceFeedback.Decision.REJECT:
        locked.status = ReadingPathCandidate.Status.REJECTED
    else:
        locked.status = ReadingPathCandidate.Status.DEFERRED
    locked.reviewed_by = actor
    locked.reviewed_at = now
    locked.review_note = review_note
    locked.save(
        update_fields=[
            "adopted_reading_path",
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "updated_at",
        ]
    )
    record_intelligence_feedback(
        reviewer=actor,
        task_profile_key="reading_path_generation",
        candidate_type="reading_path_candidate",
        candidate_id=str(locked.id),
        decision=decision,
        original_payload={"title": candidate.title, "stages": candidate.stages},
        edited_payload={
            "title": title,
            "target_audience": target_audience,
            "learning_goal": learning_goal,
            "stages": stages or [],
            "draft_reading_path_id": str(adopted_path.id) if adopted_path else "",
        },
    )
    return locked
