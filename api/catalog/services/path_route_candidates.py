"""Bounded route arrangements over reviewed selections, on the existing candidate ledger."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import UUID, uuid4

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from catalog.editorial_read import current_editorial_version
from catalog.models import EditorialRevision, EvidencePack, ReadingPath, ReadingPathCandidate, Topic, Discipline, WorkTopicRelation, WorkDisciplineRelation
from catalog.path_editor import dependency_report
from catalog.scholar_commands import command_receipt
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.person_authority import AuthorityConflict
from catalog.services.public_reading_paths import _raw, preview_reading_path
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock
from catalog.services.reading_paths import normalize_reading_path_stage_groups
from catalog.services.publication_eligibility import public_editions
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent

SUBJECT = "reading_path_arrangement"
ACTION = "reading_path_route_command"
LOCK = "reading_path_route_request"
VERSION = "public-material-arrangement-v1"


def fingerprint(value):
    return sha256(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def source_fingerprint(items, raw):
    versions = list(public_editions().filter(pk__in=[row["edition_id"] for row in items if row.get("edition_id")]).order_by("pk").values_list("pk", "active_catalog_revision_id"))
    topics = list(Topic.objects.filter(pk__in=raw.get("topics") or []).order_by("pk").values_list("pk", "editorial_status", "updated_at"))
    disciplines = list(Discipline.objects.filter(pk=raw.get("primary_discipline")).values_list("pk", "editorial_status", "updated_at"))
    return fingerprint({"items": items, "catalog_versions": versions, "topics": topics, "disciplines": disciplines})


def selected_snapshot(path, request):
    revision = EditorialRevision.objects.filter(target_type="reading_path", target_id=path.pk, status="draft").order_by("-revision").first()
    raw = deepcopy(revision.materialized_preview if revision else _raw(path))
    groups = normalize_reading_path_stage_groups(path, raw.get("stage_groups") or [])
    count = sum(len(group["items"]) for group in groups)
    if count > 40:
        raise ValidationError("整条候选编排最多处理40项材料。较长路线请继续使用阶段编排与先修图。")
    raw["stage_groups"] = groups
    projection = preview_reading_path(path, snapshot=raw, request=request)
    return raw, groups, projection


def expansion_query(raw, excluded):
    topics = Topic.objects.filter(pk__in=raw.get("topics") or [], editorial_status="published")
    disciplines = Discipline.objects.filter(pk=raw.get("primary_discipline"), editorial_status="published")
    topic_works = WorkTopicRelation.objects.filter(topic__in=topics, review_status="approved").values("work_id")
    discipline_works = WorkDisciplineRelation.objects.filter(discipline__in=disciplines, review_status="approved").values("work_id")
    return public_editions().filter(Q(work_id__in=topic_works) | Q(work_id__in=discipline_works)).exclude(work_id__in=excluded).order_by("-is_primary", "work_id", "id")


def expanded_arrangement(path, raw, groups, request):
    """Reuse confirmed taxonomy and activated publication snapshots, never title similarity."""
    current = [row for group in groups for row in group["items"]]
    capacity = min(12, 40 - len(current))
    if capacity < 1 or len(groups) >= 60:
        return deepcopy(groups), ["已达到本次候选材料或阶段上限；可在原编辑器手动编排。"]
    topic_ids = set(str(value) for value in Topic.objects.filter(pk__in=raw.get("topics") or [], editorial_status="published").values_list("pk", flat=True))
    discipline_ids = set(str(value) for value in Discipline.objects.filter(pk=raw.get("primary_discipline"), editorial_status="published").values_list("pk", flat=True))
    if not topic_ids and not discipline_ids:
        return deepcopy(groups), ["尚未选择已公开的主题或学科，无法据此补充馆藏。"]
    selected, seen = [], {row["work"] for row in current if row.get("work")}
    for edition in expansion_query(raw, seen)[:120]:
        if str(edition.work_id) in seen:
            continue
        snapshot = edition.active_catalog_revision.snapshot or {}
        def matches(section, key, identifiers):
            return [str(row.get("name") or row.get("title") or "已确认分类") for row in (snapshot.get(section) or {}).get(key, []) if isinstance(row, dict) and str(row.get("id")) in identifiers]
        names = matches("knowledge", "topics", topic_ids) or matches("classification", "disciplines", discipline_ids)
        if not names:
            continue
        active = edition.active_catalog_revision
        selected.append({"id": str(uuid4()), "work": str(edition.work_id), "node": None, "edition": str(edition.pk),
            "asset": str(active.reader_asset_id) if active.fulltext_ready and active.reader_asset_id else None,
            "document_revision": str(active.document_revision_id) if active.fulltext_ready and active.document_revision_id else None,
            "material_kind": "work", "status": "active", "is_required": False, "recommendation_reason": f"当前公开书目已确认关联：{'、'.join(names)}。作为拓展选读候选，阅读目标与难度需策划者核对。",
            "learning_goal": "", "prerequisite": "", "editorial_note": "来自当前公开书目分类，未推断学术难度或先修关系。", "dependencies": [], "position": len(selected)})
        seen.add(str(edition.work_id))
        if len(selected) == capacity:
            break
    if not selected:
        return deepcopy(groups), ["本次有界馆藏选择未找到新的、正式公开且分类吻合的材料。请补充馆藏或改用原选书入口。"]
    planned = [*deepcopy(groups), {"id": str(uuid4()), "name": "主题拓展选读", "description": "依据已确认且已公开的分类关联补充，采用后请核对阅读目标、难度及阶段位置。", "position": len(groups), "items": selected}]
    return normalize_reading_path_stage_groups(path, planned), ["新增材料均为选读，尚未填写学习目标；没有推断新的先修关系或阅读时间。"]


def _ordered(items, sources, *, chronological=False):
    pending = {row["id"]: row for row in items}
    rank = {row["id"]: index for index, row in enumerate(items)}
    result = []
    while pending:
        ready = [row for row in pending.values() if not any(link["kind"] == "learning_order" and link["item_id"] in pending for link in row.get("dependencies", []))]
        if not ready:
            return None
        def priority(row):
            year = sources[row["id"]].get("publication_year")
            return (year is None, year if year is not None else 0, rank[row["id"]]) if chronological else (rank[row["id"]],)
        chosen = min(ready, key=priority)
        result.append(chosen); pending.pop(chosen["id"])
    return result


def arrangements(groups, sources):
    """No inferred prerequisite, difficulty score or invented bibliography."""
    items = [row for group in groups for row in group["items"]]
    yield "保留阶段", "保留当前阶段与材料次序，检查材料和先修关系。", deepcopy(groups), []
    for chronological, title in [(False, "先修优先"), (True, "出版线索")]:
        ordered = _ordered(items, sources, chronological=chronological)
        if ordered is None:
            yield title, "须先处理学习顺序循环，不能用排序掩盖冲突。", deepcopy(groups), ["现有学习顺序形成循环，先到先修关系中调整。"]
            continue
        # ponytail: at most 40 selected items; deterministic ordering needs no model or queue.
        # Preserve every human stage field (including empty stages), not just its heading.
        planned, start = deepcopy(groups), 0
        for group in planned:
            count = len(group["items"])
            group["items"] = [{**deepcopy(row), "position": index} for index, row in enumerate(ordered[start:start + count])]
            start += count
        gaps = []
        if chronological and any(sources[row["id"]].get("publication_year") is None for row in items):
            gaps.append("部分材料没有公开出版年份，未推断年份；排在可确定年份的材料之后，仍优先满足先修。")
        yield title, "仅调整阶段和顺序；保留材料编号、准确版本、推荐理由、目标、必读与先修关系。", planned, gaps


def candidates_for(path_id):
    return ReadingPathCandidate.objects.filter(evidence_pack__subject_type=SUBJECT, evidence_pack__subject_id=str(path_id)).select_related("evidence_pack", "reviewed_by").order_by("-created_at", "id")


def candidate_payload(candidate, path, request, *, details=True):
    pack = candidate.evidence_pack
    meta = pack.retrieval_snapshot
    original = meta["candidates"][str(candidate.pk)]
    result = {"id": str(candidate.pk), "title": candidate.title, "summary": original["summary"], "status": candidate.status,
        "created_at": candidate.created_at, "stages_count": len(candidate.stages), "items_count": sum(len(group["items"]) for group in candidate.stages),
        "method": VERSION, "gaps": original["gaps"], "edit_version": meta["edit_version"], "audience": candidate.target_audience,
        "learning_goal": candidate.learning_goal, "review_note": candidate.review_note}
    if not details:
        return result
    blockers = list(original.get("blockers", []))
    version = current_editorial_version("reading_path", path.pk)
    if candidate.status != "pending":
        blockers.append("此候选已有人工决定，保留记录，不重复采用。")
    if version != meta["edit_version"]:
        blockers.append("原路线已更新，请基于当前已保存草稿重新生成候选。")
    try:
        raw, groups, preview = selected_snapshot(path, request)
        if source_fingerprint(preview["items"], raw) != meta["source_fingerprint"]:
            blockers.append("所选材料的公开资料或原文状态已变化，请重新生成候选。")
        candidate_groups = normalize_reading_path_stage_groups(path, candidate.stages)
        report = dependency_report(candidate_groups)
        blockers.extend(problem["detail"] for problem in report["problems"])
        if report["active_count"] < 2:
            blockers.append("整条候选至少需要两项有效材料；可补充主题馆藏后重新生成。")
        proposed = preview_reading_path(path, snapshot={**raw, "stage_groups": candidate_groups}, request=request)
        if source_fingerprint(proposed["items"], raw) != original["source_fingerprint"]:
            blockers.append("候选中材料的公开版本、分类或阅读位置已变化，请重新生成。")
        if any(row["source_status"] in {"unavailable", "withdrawn", "revision_changed"} for row in proposed["items"]):
            blockers.append("候选存在当前不可用的来源，请先核对馆藏。")
        current_positions = {row["id"]: (group["name"], index) for group in groups for index, row in enumerate(group["items"])}
        moves = [{"item_id": row["id"], "from_stage": current_positions.get(row["id"], ("不在当前路线", 0))[0],
                  "to_stage": group["name"], "from_position": current_positions.get(row["id"], ("", -1))[1] + 1, "to_position": index + 1}
                 for group in candidate_groups for index, row in enumerate(group["items"])
                 if current_positions.get(row["id"]) != (group["name"], index)]
        result.update(preview=proposed, moves=moves)
    except (ValueError, ValidationError):
        blockers.append("当前来源或编排暂不能安全解析，请返回路线核对材料。")
        result.update(preview=None, moves=[])
    result.update(blockers=list(dict.fromkeys(blockers)), can_adopt=not blockers, candidate_version=fingerprint({"id": candidate.pk, "updated": candidate.updated_at, "stages": candidate.stages, "status": candidate.status, "pack": pack.fingerprint}))
    return result


def route_receipt(actor, request_id):
    return command_receipt(actor, request_id, action=ACTION, model=ReadingPath, identity="path_route_id")


@transaction.atomic
def command(path_id, data, request):
    actor = get_object_or_404(User.objects.select_for_update(), pk=request.user.pk, is_active=True)
    if request.headers.get("X-Editor-Owner") != str(actor.pk) or actor.token_version != request.user.token_version or not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
        raise PermissionDenied("账户或编辑权限已变化，请重新读取路线。")
    request.user = actor
    try:
        request_id = UUID(request.headers.get("Idempotency-Key", ""))
    except (ValueError, TypeError) as error:
        raise ValidationError("候选操作需要固定请求编号。") from error
    acquire_generation_lock(shared=True); acquire_entity_lock(LOCK, request_id)
    mark = fingerprint({"path_id": str(path_id), "data": data})
    previous = AuditEvent.objects.filter(pk=request_id).first()
    if previous:
        if previous.actor_id != actor.pk or previous.action != ACTION or previous.after.get("fingerprint") != mark:
            raise AuthorityConflict("原请求已停止或用于其他操作，请查回原回执。")
        return {"path_id": str(path_id), "save_receipt": route_receipt(actor, request_id)}
    path = get_object_or_404(ReadingPath.objects.select_for_update(), pk=path_id)
    current = current_editorial_version("reading_path", path.pk)
    if data["edit_version"] != current:
        raise AuthorityConflict("原路线已变化，请重新打开最新草稿。")
    operation = data["operation"]
    if operation in {"adopt", "dismiss"} and not has_capability(actor, Capability.REVIEW_CANDIDATE):
        raise PermissionDenied("当前账户不能决定候选，请交由具有候选审核权限的编辑处理。")
    if operation != "dismiss" and path.status == "archived":
        raise ValidationError("路线已归档，请先沿原历史记录恢复，再编排候选。")
    if operation == "generate":
        raw, groups, projection = selected_snapshot(path, request)
        items = projection["items"]
        invalid = [row for row in items if row["source_status"] in {"unavailable", "withdrawn", "revision_changed"}]
        # Keep unavailable sources visible in candidate gaps; never replace or invent them.
        blockers = ["存在撤回、不可公开或原文修订变化的材料，请先核对并保存原路线。"] if invalid else []
        sources = {row["id"]: row for row in items}
        proposals = list(arrangements(groups, sources))
        expanded, expansion_gaps = expanded_arrangement(path, raw, groups, request)
        proposals.append(("主题拓展", "根据正式公开的主题或学科关联补充选读材料，原阶段与材料完整保留。", expanded, expansion_gaps))
        identifiers = [uuid4() for _ in proposals]
        projected = [preview_reading_path(path, snapshot={**raw, "stage_groups": planned}, request=request) for _, _, planned, _ in proposals]
        metadata = {"method": VERSION, "edit_version": current, "source_fingerprint": source_fingerprint(items, raw), "candidates": {str(key): {"summary": summary, "gaps": gaps + ([f"{len(invalid)} 项材料暂不满足公开来源要求。"] if invalid else []), "blockers": blockers,
            "source_fingerprint": source_fingerprint(view["items"], raw)} for key, (_, summary, planned, gaps), view in zip(identifiers, proposals, projected)}}
        evidence = list({item["id"]: item for view in projected for item in view["items"]}.values())
        pack = EvidencePack.objects.create(task_profile_key="reading_path_generation", task_profile_version=1,
            retrieval_profile="curation", subject_type=SUBJECT, subject_id=str(path.pk),
            envelope_snapshot=evidence, retrieval_snapshot=metadata, document_revisions=list(dict.fromkeys(row["document_revision_id"] for row in evidence if row["document_revision_id"])),
            fingerprint=fingerprint({"actor": actor.pk, "request": request_id, "metadata": metadata}), created_by=actor)
        for key, (title, _, planned, _) in zip(identifiers, proposals):
            ReadingPathCandidate.objects.create(pk=key, title=title, target_audience=raw.get("audience", ""), learning_goal=raw.get("learning_goal", ""), stages=planned, evidence_pack=pack)
    else:
        candidate = get_object_or_404(candidates_for(path.pk).select_for_update(of=("self",)), pk=data.get("candidate_id"))
        payload = candidate_payload(candidate, path, request)
        if data.get("candidate_version") != payload["candidate_version"] or candidate.status != "pending":
            raise AuthorityConflict("候选已有变化或人工决定，请重新读取。")
        if operation == "adopt":
            if not payload["can_adopt"]:
                raise ValidationError(payload["blockers"])
            save_object_editorial_patch("reading_path", path.pk, {"stage_groups": candidate.stages}, actor=actor,
                request_key=f"path-route:{request_id}", change_note=f"采用候选编排：{candidate.title}，等待编辑和确认发布")
            candidate.status = "adopted"; candidate.adopted_reading_path = path
        else:
            candidate.status = "rejected"
        candidate.reviewed_by = actor; candidate.reviewed_at = timezone.now()
        candidate.review_note = "已保存到原路线草稿，尚未发布。" if operation == "adopt" else "管理员决定不采用此编排。"
        candidate.save(update_fields=["status", "adopted_reading_path", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
        from catalog.services.research.feedback import record_intelligence_feedback
        record_intelligence_feedback(reviewer=actor, task_profile_key="reading_path_generation", candidate_type="reading_path_candidate", candidate_id=str(candidate.pk),
            decision="accept" if operation == "adopt" else "reject", original_payload={"stages": candidate.stages}, edited_payload={"reading_path_id": str(path.pk)}, prompt_key=VERSION)
    AuditEvent.objects.create(pk=request_id, actor=actor, action=ACTION, object_type=ReadingPath._meta.label, object_id=str(path.pk),
        after={"fingerprint": mark, "operation": operation, "saved_version": current_editorial_version("reading_path", path.pk)})
    return {"path_id": str(path.pk), "save_receipt": route_receipt(actor, request_id)}
