"""Owner-only data choices. Original library files and account identities are never erased here."""
from datetime import timedelta
import json
import logging
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, Throttled, ValidationError

from accounts.models import ReaderProfile
from . import research
from .models import (Annotation, CitationAudit, PersonalReadingPlan, ReaderDataOperation,
                     ReaderSearchRecord, ReadingHistory, ResearchMemory, ResearchProject, SavedTopic)
from .services import decrypt_private_text
from .source_models import SourceFollow

RETENTION = {"reading_history": True, "search_history": False, "personal_notes": True, "followed_topics": True, "source_follows": True}
RETENTION_LABELS = {"reading_history": "阅读历史", "search_history": "搜索记录", "personal_notes": "个人笔记", "followed_topics": "关注的主题", "source_follows": "来源订阅"}
EXPORT_GROUPS = {"research": ("research",), "notes": ("annotations", "memories"),
                 "plans": ("plans",), "audits": ("audits", "citation_sources"), "source_follows": ("source_follows",)}
ERASE_GROUPS = {"reading_history": ("reading_history",), "search_history": ("search_history",),
                "personal_notes": ("annotations", "memories"), "reading_plans": ("plans",),
                "followed_topics": ("followed_topics",), "source_follows": ("source_follows",)}
MODELS = {"research": ResearchProject, "annotations": Annotation, "memories": ResearchMemory,
          "plans": PersonalReadingPlan, "audits": CitationAudit, "citation_sources": CitationAudit,
          "reading_history": ReadingHistory, "search_history": ReaderSearchRecord, "followed_topics": SavedTopic, "source_follows": SourceFollow}
MAX_ITEMS = 500
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
ACTIVE = {"queued", "running"}
NOTICE = "仅处理本人的资料，不删除账户、登录权限或公开馆藏原件。备份按既有保留期清理；取消不会恢复已删除的项目。"
logger = logging.getLogger(__name__)


def profile_data(user):
    profile = ReaderProfile.objects.filter(user=user).first()
    return (profile.reading_preferences or {}) if profile else {}


def lock_owner(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)


def preferences(user):
    raw = profile_data(user)
    return {"revision": int(raw.get("privacy_revision", 1)),
            "retention": {key: raw.get("privacy_retention", {}).get(key, default) is True for key, default in RETENTION.items()}}


def retention_enabled(user, key):
    return preferences(user)["retention"][key]


def require_retention(user, key):
    # Call inside the writer's transaction, so turning a choice off is ordered with new saves.
    lock_owner(user)
    if not retention_enabled(user, key):
        raise ValidationError({"retention": f"已关闭保存{RETENTION_LABELS[key]}。请先在隐私与资料中开启；本次输入尚未保存。"})


@transaction.atomic
def update_preferences(user, data):
    lock_owner(user)
    profile, _ = ReaderProfile.objects.select_for_update().get_or_create(user=user)
    current = profile.reading_preferences or {}
    revision = int(current.get("privacy_revision", 1))
    if data.get("expected_revision") != revision:
        raise research.ResearchConflict("隐私设置已在其他页面修改，请重新读取后保存。")
    changed = data.get("retention")
    if not isinstance(changed, dict) or not changed or set(changed) - RETENTION.keys() or any(type(value) is not bool for value in changed.values()):
        raise ValidationError({"retention": "请选择支持的记录类型，并传入开关值。"})
    history = current.get("privacy_history", [])[-39:]
    history.append({"at": timezone.now().isoformat(), "retention": changed})
    profile.reading_preferences = {**current, "privacy_revision": revision + 1,
        "privacy_retention": {**current.get("privacy_retention", {}), **changed}, "privacy_history": history}
    profile.save(update_fields=["reading_preferences", "updated_at"])
    return privacy_summary(user)


@transaction.atomic
def remember_search(user, session_id, query, filters):
    if user is None or not user.is_authenticated:
        return
    lock_owner(user)
    if retention_enabled(user, "search_history"):
        ReaderSearchRecord.objects.get_or_create(user=user, request_id=session_id,
            defaults={"data_ciphertext": research.pack({"query": query, "filters": filters})})


def remember_search_after_commit(user, session_id, query, filters):
    try:
        remember_search(user, session_id, query, filters)
    except Exception as exc:
        # A history-write failure cannot roll back a functioning query or its dispatch.
        logger.warning("Reader search history save failed (%s)", type(exc).__name__)
        from catalog.discovery_models import DiscoverySearchSession
        try:
            with transaction.atomic():
                session = DiscoverySearchSession.objects.select_for_update().filter(pk=session_id, owner=user).first()
                if session:
                    session.warnings = [*session.warnings, {"code": "history_not_saved",
                        "message": "本次搜索记录未能保存到隐私资料，当前检索可继续使用。"}]
                    session.save(update_fields=["warnings"])
        except Exception as warning_error:
            logger.warning("Reader search history warning unavailable (%s)", type(warning_error).__name__)


def rows(user, category):
    if category not in MODELS:
        raise ValidationError({"category": "资料类型无效。"})
    result = MODELS[category].objects.filter(user=user)
    if category in {"audits", "citation_sources"}:
        result = result.filter(purpose="manuscript" if category == "audits" else "private_source").defer("original_ciphertext", "preview_ciphertext")
    return result


def version(row):
    return str(row.revision) if hasattr(row, "revision") else row.updated_at.isoformat()


def item(user, category, pk, *, lock=False):
    query = rows(user, category)
    row = (query.select_for_update() if lock else query).filter(pk=research.identifier(pk)).first()
    if row is None:
        raise NotFound("这项本人资料已不存在。")
    return row


def target_of(row, category):
    target = {"category": category, "id": str(row.id), "revision": version(row)}
    if category == "research":
        target["children"] = {str(turn.id): turn.revision for turn in row.turns.all()}
    return target


def verify_target(user, target, *, lock=False):
    row = item(user, target["category"], target["id"], lock=lock)
    if version(row) != target["revision"]:
        raise research.ResearchConflict("资料已修改，请重新预览当前版本。")
    if target.get("children") is not None and target_of(row, target["category"]).get("children") != target["children"]:
        raise research.ResearchConflict("研究轮次已修改，请重新准备导出。")
    return row


def annotation_export(user, row):
    ref = research.annotation_source(user, row)
    source = research.resolve_reference(ref, user) if ref else {"source_status": "unavailable"}
    from types import SimpleNamespace
    from .serializers import AnnotationSerializer
    original = dict(AnnotationSerializer(row, context={"request": SimpleNamespace(user=user)}).data)
    original.update(quote=row.quote if source.get("source_status") == "available" else "", source=source)
    return original


def export_item(user, category, row):
    if category == "source_follows":
        from .source_follow import output
        return output(row, export=True)
    if category == "annotations":
        return annotation_export(user, row)
    result = research.serialize_record(row, user)
    if category == "research":
        result["turns"] = [research.serialize_record(turn, user) for turn in row.turns.all()]
    return result


def linked_memories(user, annotation_id):
    # The source association lives in encrypted payload; preserve original notes and authored memory bodies independently.
    return [row for row in ResearchMemory.objects.filter(user=user).order_by("id")
            if research.unpack(row).get("origin", {}).get("annotation_id") == str(annotation_id)]


def erase_impact(user, category, row, *, contexts=None):
    related = linked_memories(user, row.id) if category == "annotations" else [row] if category == "memories" else []
    contexts = contexts if contexts is not None else research.memory_contexts(user) if related else []
    affected = []
    for memory in related:
        scopes = [{"kind": kind, "id": str(context.id)} for kind, context in contexts
                  if str(memory.id) in research.unpack(context).get("confirmed_memory_ids", [])]
        affected.append({"id": str(memory.id), "revision": memory.revision, "scopes": scopes})
    message = {"annotations": "删除原笔记，保留独立确认的认识，并撤销关联认识的使用范围。",
               "memories": "删除此条认识、修改历史与派生向量，撤销使用范围；原阅读笔记保留。",
               "plans": "删除此阅读计划与计划内建议；原文、独立研究和笔记保留，未完成计划任务将失效。",
               "reading_history": "删除此条阅读历史；阅读进度、笔记和馆藏原件保留。",
               "search_history": "删除这条主动保存的检索记录；当前检索与研究所需临时会话不受影响。",
               "followed_topics": "取消关注此主题；主题和公开馆藏保留。",
               "source_follows": "删除此来源订阅、站内更新与状态历史，停止后续检查；公开馆藏保留。"}[category]
    return {"message": message, "memories": affected, "scope_count": sum(len(value["scopes"]) for value in affected)}


def describe_item(user, category, row):
    payload = research.unpack(row) if hasattr(row, "data_ciphertext") else {}
    source = {}
    if category in {"annotations", "memories"}:
        if category == "annotations":
            ref = research.annotation_source(user, row)
            details = research.memory_source_details(user, {"sources": [ref] if ref else []})
            title = decrypt_private_text(row.body_ciphertext)[:120] or "阅读标记"
        else:
            details = research.memory_source_details(user, payload)
            title = payload.get("body", "")[:120] or "个人认识"
        source = next(iter(details.get("source_summaries", [])), {})
    elif category == "reading_history":
        from catalog.services.discovery_sources import source_queryset
        edition = source_queryset("edition", research.access_for(user)).filter(pk=row.asset.edition_id).first()
        snapshot = edition.active_catalog_revision.snapshot if edition else {}
        source = {"title": (snapshot.get("work") or {}).get("title", "来源当前不可用"),
                  "edition": (snapshot.get("edition") or {}).get("version_label", ""), "pdf_page": row.page_index}
        title = source["title"]
    elif category == "source_follows":
        from .source_follow import resolve_public_source
        source = resolve_public_source(row.path)
        title = source["title"]
    elif category == "followed_topics":
        title = row.topic.name
    else:
        title = payload.get("query") or payload.get("goal") or payload.get("title") or "未命名资料"
    return {**target_of(row, category), "title": title, "updated_at": row.updated_at.isoformat(),
            "source": source, "impact": erase_impact(user, category, row)["message"]}


def list_items(user, category, page=1):
    if category not in ERASE_GROUPS:
        raise ValidationError({"category": "请选择可以管理的资料类型。"})
    descriptors, count = [], 0
    start = (page - 1) * 20
    for leaf in ERASE_GROUPS[category]:
        query = rows(user, leaf)
        count += query.count()
        descriptors.extend((stamp, str(pk), leaf) for pk, stamp in query.order_by("-updated_at", "-id").values_list("id", "updated_at")[:start + 20])
    descriptors.sort(reverse=True)
    selected = descriptors[start:start + 20]
    return {"owner_id": str(user.pk), "count": count, "page": page, "page_size": 20,
            "results": [describe_item(user, leaf, item(user, leaf, pk)) for _, pk, leaf in selected]}


def close_stale(user):
    stale = ReaderDataOperation.objects.filter(user=user, status__in=ACTIVE,
        updated_at__lt=timezone.now() - timedelta(minutes=10))
    for pk in stale.values_list("id", flat=True)[:20]:
        with transaction.atomic():
            lock_owner(user)
            row = ReaderDataOperation.objects.select_for_update().filter(pk=pk, status__in=ACTIVE,
                updated_at__lt=timezone.now() - timedelta(minutes=10)).first()
            if row:
                payload = research.unpack(row)
                payload["error_code"] = "task_interrupted"
                row.status, row.finished_at = "partial" if payload.get("results") else "failed", timezone.now()
                research.save_data(row, payload, fields=["status", "finished_at"])


def operation_output(row):
    payload = research.unpack(row)
    results = payload.get("results", [])
    successful = sum(result["status"] == "completed" for result in results)
    failed = sum(result["status"] == "failed" for result in results)
    finished_ids = {result["id"] for result in results}
    preview = []
    if row.kind == "erase" and row.status == "preview":
        for target in payload.get("targets", []):
            if target["id"] in finished_ids:
                continue
            entry = {**target, "impact": payload.get("impacts", {}).get(target["id"], {}), "title": "已选择的资料", "current": False}
            try:
                current = item(row.user, target["category"], target["id"])
                if target["category"] == "annotations":
                    title = decrypt_private_text(current.body_ciphertext)[:120] or "阅读标记"
                elif target["category"] in {"memories", "plans", "search_history"}:
                    content = research.unpack(current)
                    title = (content.get("body") or content.get("goal") or content.get("query") or "本人资料")[:120]
                else:
                    title = describe_item(row.user, target["category"], current)["title"]
                entry.update(title=title, current=version(current) == target["revision"])
            except NotFound:
                entry["title"] = "这项资料已被删除"
            preview.append(entry)
    return {"id": str(row.id), "owner_id": str(row.user_id), "revision": row.revision, "kind": row.kind,
            "status": row.status, "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "total": len(payload.get("targets", [])), "completed": successful, "failed": failed,
            "remaining": len(payload.get("targets", [])) - successful - failed,
            "categories": payload.get("categories", []), "results": results, "error_code": payload.get("error_code", ""),
            "preview": preview,
            "download_available": row.kind == "export" and successful > 0 and row.status not in ACTIVE,
            "notice": NOTICE}


def privacy_summary(user):
    close_stale(user)
    contexts = research.memory_contexts(user)
    selected = [context for _, context in contexts if research.unpack(context).get("use_confirmed_memories") is True
                and research.plan_memory_rows(user, research.unpack(context))]
    return {"owner_id": str(user.pk), **preferences(user), "automatic_memory_use": False,
            "confirmed_notes": ResearchMemory.objects.filter(user=user, state="confirmed").count(), "authorized_contexts": len(selected),
            "export_counts": {group: sum(rows(user, leaf).count() for leaf in leaves) for group, leaves in EXPORT_GROUPS.items()},
            "erase_counts": {group: sum(rows(user, leaf).count() for leaf in leaves) for group, leaves in ERASE_GROUPS.items()},
            "operations": [operation_output(row) for row in ReaderDataOperation.objects.filter(user=user)[:6]],
            "preference_history": profile_data(user).get("privacy_history", [])[-8:][::-1],
            "max_operation_items": MAX_ITEMS, "export_formats": ["json"], "notice": NOTICE}


def admission(user):
    if ReaderDataOperation.objects.filter(user=user, status__in=ACTIVE).count() >= 2:
        raise Throttled(detail="请等待或取消当前资料任务后再继续。", wait=10)


def schedule(row):
    from .tasks import run_reader_data_operation
    args = [str(row.id), row.generation, row.task_id]
    def enqueue():
        try:
            run_reader_data_operation.apply_async(args=args, task_id=row.task_id)
        except Exception:
            with transaction.atomic():
                lock_owner(row.user)
                failed = ReaderDataOperation.objects.select_for_update().filter(pk=row.pk, generation=args[1], task_id=args[2], status="queued").first()
                if failed:
                    payload = research.unpack(failed)
                    payload["error_code"] = "queue_unavailable"
                    failed.status, failed.finished_at = "failed", timezone.now()
                    research.save_data(failed, payload, fields=["status", "finished_at"])
    transaction.on_commit(enqueue)


@transaction.atomic
def create_operation(user, data):
    lock_owner(user)
    request_id = research.identifier(data.get("request_id"), "request_id")
    fingerprint = research.request_fingerprint(data, ("kind", "categories", "targets"))
    previous = ReaderDataOperation.objects.filter(user=user, request_id=request_id).first()
    if previous:
        return research.same_request(previous, fingerprint)
    kind, targets, impacts = data.get("kind"), [], {}
    categories = data.get("categories", [])
    if kind == "export":
        if not categories or set(categories) - EXPORT_GROUPS.keys() or len(set(categories)) != len(categories):
            raise ValidationError({"categories": "请选择至少一种导出资料。"})
        for category in categories:
            for leaf in EXPORT_GROUPS[category]:
                for row in rows(user, leaf).order_by("id")[:MAX_ITEMS + 1]:
                    targets.append(target_of(row, leaf))
                    if len(targets) > MAX_ITEMS:
                        raise ValidationError({"categories": f"一次最多准备 {MAX_ITEMS} 项，请分类型导出；单项也可在对应工作台导出。"})
    elif kind == "erase":
        raw = data.get("targets", [])
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_ITEMS:
            raise ValidationError({"targets": f"请选择 1 至 {MAX_ITEMS} 项资料。"})
        allowed = {leaf for leaves in ERASE_GROUPS.values() for leaf in leaves}
        contexts = research.memory_contexts(user, lock=True) if any(target.get("category") in {"annotations", "memories"} for target in raw) else []
        seen = set()
        for target in raw:
            if target.get("category") not in allowed:
                raise ValidationError({"targets": "该资料类型不能在这里删除。"})
            row = verify_target(user, target, lock=True)
            key = (target["category"], str(row.id))
            if key in seen:
                raise ValidationError({"targets": "选中资料不能重复。"})
            seen.add(key)
            targets.append(target_of(row, target["category"]))
            impacts[str(row.id)] = erase_impact(user, target["category"], row, contexts=contexts)
        categories = sorted({target["category"] for target in targets})
    else:
        raise ValidationError({"kind": "操作类型无效。"})
    if not targets:
        raise ValidationError({"categories": "所选类别暂无可导出内容。"})
    if kind == "export":
        admission(user)
    row = ReaderDataOperation.objects.create(user=user, request_id=request_id, kind=kind,
        status="queued" if kind == "export" else "preview", task_id=str(uuid4()) if kind == "export" else "",
        data_ciphertext=research.pack({"request_fingerprint": fingerprint, "categories": categories,
            "targets": targets, "impacts": impacts, "results": [], "error_code": ""}))
    if kind == "export":
        schedule(row)
    return row


@transaction.atomic
def command_operation(user, pk, data):
    lock_owner(user)
    row = research.owned(ReaderDataOperation, user, pk, lock=True)
    research.expect(row, data.get("expected_revision"))
    payload = research.unpack(row)
    action = data.get("action")
    if action == "cancel":
        if row.status not in ACTIVE | {"preview"}:
            raise ValidationError({"action": "这项任务当前无需取消。"})
        row.status, row.finished_at = "canceled", timezone.now()
        row.generation += 1
    elif action in {"confirm", "retry"}:
        if (action == "confirm" and (row.kind != "erase" or row.status != "preview")) or (
                action == "retry" and row.status not in {"partial", "failed", "canceled"}):
            raise ValidationError({"action": "此状态不能执行所选操作。"})
        contexts = research.memory_contexts(user, lock=True) if row.kind == "erase" and any(
            target["category"] in {"annotations", "memories"} for target in payload["targets"]) else []
        if row.kind == "erase" and action == "retry":
            # Erasure retry is a new impact preview. It never silently deletes newly edited records.
            successful = {result["id"] for result in payload.get("results", []) if result["status"] == "completed"}
            pending = [target for target in payload["targets"] if target["id"] not in successful]
            unavailable = []
            for target in pending:
                try:
                    current = item(user, target["category"], target["id"], lock=True)
                except NotFound:
                    unavailable.append({"id": target["id"], "category": target["category"], "status": "failed", "error_code": "record_unavailable"})
                    continue
                target["revision"] = version(current)
                payload["impacts"][target["id"]] = erase_impact(user, target["category"], current, contexts=contexts)
            payload["results"] = [result for result in payload.get("results", []) if result["status"] == "completed"] + unavailable
            row.status = "preview" if len(pending) > len(unavailable) else "partial" if successful else "failed"
            row.finished_at = None if row.status == "preview" else timezone.now()
        else:
            if row.kind == "erase":
                successful = {result["id"] for result in payload.get("results", [])}
                for target in payload["targets"]:
                    if target["id"] in successful:
                        continue
                    current = verify_target(user, target, lock=True)
                    if erase_impact(user, target["category"], current, contexts=contexts) != payload["impacts"].get(target["id"]):
                        raise research.ResearchConflict("关联笔记或使用范围已变化，请重新预览影响。")
            admission(user)
            if row.kind == "export":
                payload["results"] = [result for result in payload.get("results", []) if result["status"] == "completed"]
            row.status, row.finished_at, row.task_id = "queued", None, str(uuid4())
            row.generation += 1
        payload["error_code"] = ""
    else:
        raise ValidationError({"action": "操作无效。"})
    research.save_data(row, payload, fields=["status", "finished_at", "task_id", "generation"])
    if row.status == "queued":
        schedule(row)
    return row


def erase_item(user, target, row, impact, *, contexts):
    if erase_impact(user, target["category"], row, contexts=contexts) != impact:
        raise research.ResearchConflict("关联内容已变化，需重新预览影响。")
    if target["category"] == "memories":
        research.revoke_memory_contexts(row, contexts)
    elif target["category"] == "annotations":
        for memory in linked_memories(user, row.id):
            research.revoke_memory_contexts(memory, contexts)
    row.delete()


def run_operation(pk, generation, task_id):
    owner_id = ReaderDataOperation.objects.filter(pk=pk).values_list("user_id", flat=True).first()
    user = get_user_model().objects.filter(pk=owner_id, is_active=True).first()
    if user is None:
        return
    with transaction.atomic():
        lock_owner(user)
        row = ReaderDataOperation.objects.select_for_update().filter(pk=pk, generation=generation, task_id=task_id, status="queued").first()
        if row is None:
            return
        row.status = "running"
        research.save_data(row, research.unpack(row), fields=["status"])
    while True:
        with transaction.atomic():
            lock_owner(user)
            row = ReaderDataOperation.objects.select_for_update().filter(pk=pk, generation=generation, task_id=task_id, status="running").first()
            if row is None:
                return
            payload = research.unpack(row)
            done = {result["id"] for result in payload["results"]}
            target = next((target for target in payload["targets"] if target["id"] not in done), None)
            if target is None:
                success = any(result["status"] == "completed" for result in payload["results"])
                failure = any(result["status"] == "failed" for result in payload["results"])
                row.status = "partial" if success and failure else "failed" if failure else "completed"
                row.finished_at = timezone.now()
                research.save_data(row, payload, fields=["status", "finished_at"])
                return
            result = {"id": target["id"], "category": target["category"], "status": "completed", "error_code": ""}
            try:
                with transaction.atomic():
                    contexts = research.memory_contexts(user, lock=True) if row.kind == "erase" and target["category"] in {"annotations", "memories"} else []
                    current = verify_target(user, target, lock=True)
                    if row.kind == "erase":
                        erase_item(user, target, current, payload["impacts"][target["id"]], contexts=contexts)
                    else:
                        size = len(json.dumps(export_item(user, target["category"], current), ensure_ascii=False, default=str).encode())
                        verify_target(user, target)
                        if size + sum(entry.get("bytes", 0) for entry in payload["results"]) > MAX_DOWNLOAD_BYTES:
                            raise ValidationError("所选内容超过单次文件限制，请按类别或单项导出。")
                        result["bytes"] = size
            except research.ResearchConflict:
                result.update(status="failed", error_code="revision_changed")
            except NotFound:
                result.update(status="failed", error_code="record_unavailable")
            except ValidationError:
                result.update(status="failed", error_code="content_limit")
            except Exception as exc:
                logger.warning("Reader data operation item failed (%s)", type(exc).__name__)
                result.update(status="failed", error_code="preparation_failed")
            payload["results"].append(result)
            research.save_data(row, payload)


def download_operation(user, pk):
    row = research.owned(ReaderDataOperation, user, pk)
    if row.kind != "export" or row.status in ACTIVE | {"preview"}:
        raise ValidationError("导出文件尚未准备完成。")
    payload = research.unpack(row)
    successful = {result["id"] for result in payload.get("results", []) if result["status"] == "completed"}
    if not successful:
        raise ValidationError("暂无可下载内容。")
    output, unavailable, total_bytes = [], [], 0
    for target in payload["targets"]:
        if target["id"] not in successful:
            continue
        try:
            current = verify_target(user, target)
            record = export_item(user, target["category"], current)
            # A turn may update without changing its parent project revision.
            # Refuse a mixed snapshot if either the record or any captured child changed.
            verify_target(user, target)
        except (NotFound, research.ResearchConflict):
            unavailable.append({"id": target["id"], "category": target["category"], "reason": "资料已修改或删除，请重新准备导出。"})
            continue
        total_bytes += len(json.dumps(record, ensure_ascii=False, default=str).encode())
        if total_bytes > MAX_DOWNLOAD_BYTES:
            raise ValidationError("文件超过单次导出限制，请重新选择较小范围。")
        output.append({"category": target["category"], "record": record})
    return {"schema_version": 1, "owner_id": str(user.pk), "operation_id": str(row.id),
            "prepared_at": row.finished_at, "downloaded_at": timezone.now(), "records": output,
            "unavailable_since_preparation": unavailable,
            "failed": [result for result in payload.get("results", []) if result["status"] == "failed"],
            "notice": "下载时重新核对来源资格和资料修订。包含本人文字与可用来源信息，不包含 PDF/DOCX 原件、派生向量或凭据。"}
