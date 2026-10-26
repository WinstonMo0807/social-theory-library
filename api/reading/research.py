"""Private research commands shared by API and Celery. All reads recheck ownership."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import math
import re
from types import SimpleNamespace
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from catalog.models import EvidenceSpan, Page
from catalog.services.discovery_sources import source_queryset
from catalog.services.discovery_sessions import normalize_filters, request_access
from catalog.services.media import snapshot_cover

from .models import (Annotation, LibraryConversation, PersonalReadingPlan, ResearchImportReceipt, ResearchMemory,
                     ResearchProject, ResearchTurn)
from .services import decrypt_private_text, encrypt_private_text

ACTIVE = {"queued", "running"}
ANALYSIS_VERSION = "private-claims-v1"
MAX_REFS = 400
PLAN_POLICY_FIELDS = ("time_budget", "budget_minutes", "session_minutes", "reading_level", "reading_pace", "prefer_unread",
    "item_estimates", "weekly_minutes", "duration_weeks", "language_preference", "read_book_count")
PLAN_MEMORY_FIELDS = ("use_confirmed_memories", "confirmed_memory_ids")
MEMORY_KINDS = {"concept", "understanding", "question", "method", "observation", "contradiction"}
PLAN_REQUEST_FIELDS = ("goal", "background", "project_id", "turn_id", "reading_path_id", "references",
    "prerequisites", "scope", *PLAN_POLICY_FIELDS, *PLAN_MEMORY_FIELDS)


class ResearchConflict(APIException):
    status_code = 409
    default_detail = "内容已更新，请保留输入并读取最新版本后再保存。"


def pack(data):
    return encrypt_private_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def request_fingerprint(data, keys):
    return hashlib.sha256(json.dumps({key: data[key] for key in keys if key in data},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def same_request(record, fingerprint):
    if unpack(record).get("request_fingerprint") != fingerprint:
        raise ResearchConflict("该请求标识已用于不同内容；请为新的操作生成新标识。")
    return record


def unpack(record):
    value = decrypt_private_text(record.data_ciphertext)
    return json.loads(value) if value else {}


def identifier(value, field="id"):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError({field: "需要有效的记录标识。"}) from exc


def text(value, field, limit=4000, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValidationError({field: f"请输入{'非空' if required else ''}文字，最多 {limit} 字符。"})
    return value.strip()


def bounded_list(value, field, maximum=MAX_REFS):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValidationError({field: f"需要列表，最多 {maximum} 项。"})
    return value


def owned(model, user, pk, *, lock=False):
    rows = model.objects.select_for_update() if lock else model.objects
    filters = {"project__user": user} if model is ResearchTurn else {"user": user}
    record = rows.filter(pk=identifier(pk), **filters).first()
    if record is None:
        raise NotFound("私人记录不存在。")
    return record


def expect(record, revision):
    if isinstance(revision, bool) or not isinstance(revision, int) or revision != record.revision:
        raise ResearchConflict({"detail": "内容已更新，请保留输入并读取最新版本。", "current_revision": record.revision})


def save_data(record, data, *, fields=()):
    record.data_ciphertext = pack(data)
    record.revision += 1
    if isinstance(record, PersonalReadingPlan):
        record.task_pending = (data.get("generation_status") in ACTIVE
            or data.get("enhancement_status") in ACTIVE | {"queue_unavailable"})
        fields = (*fields, "task_pending")
    record.save(update_fields=["data_ciphertext", "revision", "updated_at", *fields])
    return record


def access_for(user):
    return request_access(SimpleNamespace(user=user))


def resolve_reference(raw, user, *, strict=False):
    """Return current text only for the exact serving file and document revision."""
    if not isinstance(raw, dict):
        raise ValidationError({"reference": "原文引用需要对象。"})
    if "anchors" in raw:
        anchors = bounded_list(raw["anchors"], "anchors", 20)
        if not anchors or any(not isinstance(anchor, dict) or "anchors" in anchor for anchor in anchors):
            raise ValidationError({"anchors": "跨页引用须有 1 至 20 个单页锚点，不能嵌套。"})
        resolved = [resolve_reference(anchor, user, strict=strict) for anchor in anchors]
        identities = {(item.get("asset_id"), item.get("document_revision_id")) for item in resolved}
        if len(identities) != 1:
            raise ValidationError({"anchors": "跨页引文须来自同一文件和文字修订；不同版本请分别选择。"})
        available = all(item["source_status"] == "available" for item in resolved)
        digest = hashlib.sha256("|".join(item.get("content_hash", "") for item in resolved).encode()).hexdigest()
        if raw.get("content_hash") and raw["content_hash"] != digest:
            available = False
        if strict and not available:
            raise ValidationError({"anchors": "部分原文已变化或失效，请重新选择。"})
        first = resolved[0]
        return {**compact_reference(first), "anchors": resolved, "content_hash": digest,
                "reference_id": reference_identity({"anchors": resolved}),
                "source_status": "available" if available else "unavailable", "locator_precision": "multi_anchor",
                "quote": "\n".join(item["quote"] for item in resolved) if available else "",
                **{key: first.get(key) for key in ("title", "authors", "publication_year", "document_type", "language", "cover_url", "cover_media", "citation")},
                "reader_url": first.get("reader_url") if available else None}
    span_id = raw.get("evidence_span_id")
    stale = {"schema_version": 1, "source_kind": "catalog", "source_status": "unavailable",
             "reference_id": reference_identity(raw),
             **{key: raw[key] for key in ("evidence_span_id", "document_revision_id", "asset_id", "pdf_page", "content_hash",
                                         "work_id", "edition_id", "selection_start", "selection_end") if key in raw}}
    span = None
    if span_id:
        span = EvidenceSpan.objects.select_related("document_revision__asset", "page").filter(
            pk=identifier(span_id), is_stale=False).first()
        if span:
            asset_id = str(span.document_revision.asset_id)
            revision_id = str(span.document_revision_id)
            page_number = span.page_number
        else:
            asset_id, revision_id, page_number = None, None, None
    else:
        asset_id = identifier(raw.get("asset_id"), "asset_id")
        revision_id = identifier(raw.get("document_revision_id"), "document_revision_id")
        page_number = raw.get("pdf_page")
        if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1:
            raise ValidationError({"pdf_page": "PDF 页序从 1 开始。"})
    edition = source_queryset("edition", access_for(user)).filter(
        active_catalog_revision__reader_asset_id=asset_id,
        active_catalog_revision__document_revision_id=revision_id).first() if asset_id else None
    page = span.page if span else Page.objects.filter(asset_id=asset_id, index=page_number).first() if edition else None
    digest = span.content_hash if span else hashlib.sha256(page.text.encode()).hexdigest() if page else ""
    expected_ids = {"asset_id": asset_id, "document_revision_id": revision_id, "pdf_page": page_number,
                    "edition_id": str(edition.id) if edition else None, "work_id": str(edition.work_id) if edition else None}
    identity_mismatch = any(raw.get(key) is not None and str(raw[key]) != str(value) for key, value in expected_ids.items())
    if (not edition or not page or (span and (page.asset_id != span.document_revision.asset_id or span.page_number != page.index))
            or identity_mismatch
            or (raw.get("content_hash") and raw["content_hash"] != digest)
            or (raw.get("document_revision_id") and str(raw["document_revision_id"]) != revision_id)):
        if strict:
            raise ValidationError({"reference": "原文已变化、撤回或不可访问，请重新选择。"})
        return stale
    source_text = span.original_text if span else page.text
    selected_range = {}
    if "selection_start" in raw or "selection_end" in raw:
        start, end = raw.get("selection_start"), raw.get("selection_end")
        if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int)
                or not isinstance(end, int) or not 0 <= start < end <= len(source_text)
                or end - start > 20000 or not raw.get("content_hash")):
            if strict:
                raise ValidationError({"reference": "选文范围无效，请从当前原文重新选择。"})
            return stale
        selected_range = {"selection_start": start, "selection_end": end}
        source_text = source_text[start:end]
    snapshot = edition.active_catalog_revision.snapshot or {}
    from catalog.services.page_label_metadata import structured_page_labels
    from catalog.services.page_geometry import locator_geometry, validated_geometry
    from catalog.services.text import page_text_range
    geometry = validated_geometry((span.ocr_provenance or {}).get("geometry") if span else page.geometry)
    from catalog.services.citations import format_gbt_7714_2025
    authors = [str((item.get("person") or {}).get("preferred_name") or item.get("name") or "")
               for item in snapshot.get("contributions", []) if isinstance(item, dict) and item.get("role") == "author"]
    return {"schema_version": 1, "source_kind": "catalog", "source_status": "available",
            "reference_id": reference_identity({"evidence_span_id": str(span.id) if span else None,
                "asset_id": asset_id, "pdf_page": page_number, **selected_range}), **selected_range,
            "evidence_span_id": str(span.id) if span else None,
            "work_id": str(edition.work_id), "edition_id": str(edition.id), "asset_id": asset_id,
            "document_revision_id": revision_id, "pdf_page": page_number,
            "printed_label": span.printed_page_label if span else page.printed_label,
            **structured_page_labels(page),
            "content_hash": digest, "title": (snapshot.get("work") or {}).get("title", ""),
            "authors": [value for value in authors if value],
            "document_type": (snapshot.get("work") or {}).get("document_type", ""),
            "language": (snapshot.get("work") or {}).get("language", ""),
            "publication_year": (snapshot.get("edition") or {}).get("publication_year"), **snapshot_cover(edition),
            "citation": format_gbt_7714_2025(edition, page.printed_label, snapshot=snapshot),
            "quote": source_text,
            "start_offset": (span.start_offset if span else 0) + selected_range.get("selection_start", 0),
            "end_offset": ((span.start_offset if span else 0) + selected_range["selection_end"] if selected_range
                else span.end_offset if span else len(page.text)),
            "page_text_range": page_text_range(page.text, source_text,
                (span.start_offset if span else 0) + selected_range.get("selection_start", 0),
                (span.start_offset if span else 0) + selected_range["selection_end"] if selected_range else span.end_offset if span else len(page.text)),
            "bbox": span.bbox if span else [], "bbox_unit": "source_page_coordinates",
            "geometry": geometry, **locator_geometry(span.bbox if span else [], geometry),
            "coordinate_space": {"width": page.width, "height": page.height, "text_source": page.text_source,
                "rotation": None, "crop_box": None, "requires_reader_transform": True},
            "locator_precision": "span" if span else "page",
            "reader_url": f"/reader/{asset_id}?page={page_number}&revision={revision_id}" + (f"&passage={span.passage_id or span.id}" if span else "")}


def reference_identity(reference):
    if reference.get("anchors"):
        return "anchors:" + hashlib.sha256("|".join(reference_identity(row) for row in reference["anchors"]).encode()).hexdigest()
    identity = str(reference.get("evidence_span_id") or f"{reference.get('asset_id')}:{reference.get('pdf_page')}")
    if "selection_start" in reference and "selection_end" in reference:
        identity += f":range:{reference['selection_start']}:{reference['selection_end']}"
    return identity


def compact_reference(reference):
    # Identity only: future reads must rehydrate rather than leak cached withdrawn text.
    output = {key: reference[key] for key in ("schema_version", "source_kind", "evidence_span_id", "work_id",
            "edition_id", "asset_id", "document_revision_id", "pdf_page", "content_hash", "selection_start", "selection_end") if key in reference}
    if reference.get("anchors"):
        output["anchors"] = [compact_reference(row) for row in reference["anchors"]]
        output.pop("evidence_span_id", None)
    return output


def references(values, user):
    output, seen = [], set()
    for raw in bounded_list(values, "references"):
        ref = resolve_reference(raw, user, strict=True)
        key = reference_identity(ref)
        if key not in seen:
            output.append(compact_reference(ref))
            seen.add(key)
    return output


def scope_snapshot(raw, user):
    if not isinstance(raw, dict):
        raise ValidationError({"scope": "范围需要对象。"})
    kind = raw.get("kind", "library")
    if kind not in {"library", "works", "passages", "filtered"}:
        raise ValidationError({"scope": "范围类型无效。"})
    filters = normalize_filters(raw.get("filters", {}))
    refs = references(raw.get("references", []), user) if kind == "passages" else []
    if kind == "passages" and not refs:
        raise ValidationError({"scope": "限定原文时至少选择一段，不会自动扩大到全馆。"})
    if kind == "works" and not filters.get("work_ids"):
        raise ValidationError({"scope": "限定文献时至少选择一部作品。"})
    if "allow_neighbors" in raw and not isinstance(raw["allow_neighbors"], bool):
        raise ValidationError({"allow_neighbors": "需要布尔值，不能传文字。"})
    return {"kind": kind, "filters": filters, "references": refs,
            "allow_neighbors": bool(raw.get("allow_neighbors", False)) if kind != "passages" else False}


@transaction.atomic
def create_project(user, data):
    if "expected_owner_id" in data and (type(data["expected_owner_id"]) is not int or data["expected_owner_id"] != user.pk):
        raise PermissionDenied("登录账户已变化，请重新选择本人研究。")
    request_id = identifier(data.get("request_id"), "request_id")
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=user.pk)
    existing = ResearchProject.objects.filter(user=user, request_id=request_id).first()
    fingerprint = request_fingerprint(data, ("title", "question", "conversation_id", "scope"))
    if existing:
        return same_request(existing, fingerprint)
    conversation = None
    if data.get("conversation_id"):
        conversation = LibraryConversation.objects.filter(pk=identifier(data["conversation_id"]), user=user).first()
        if conversation is None:
            raise NotFound("会话不存在。")
        existing = ResearchProject.objects.filter(conversation=conversation, user=user).first()
        if existing:
            return existing
    payload = {"request_fingerprint": fingerprint, "title": text(data.get("title", "新的研究"), "title", 240, True),
               "question": text(data.get("question", ""), "question"),
               "scope": scope_snapshot(data.get("scope", {}), user), "selections": [],
               "removed_selections": [], "comparison": {"dimensions": [], "cells": []}, "notes": "", "layout": {},
               "use_confirmed_memories": False, "confirmed_memory_ids": []}
    return ResearchProject.objects.create(user=user, request_id=request_id, conversation=conversation, data_ciphertext=pack(payload))


@transaction.atomic
def import_project(user, data):
    """Explicit guest transfer. Rehydrate identities; never trust browser text or task ownership."""
    from django.contrib.auth import get_user_model
    from .research_serializers import ProjectImportInput
    ProjectImportInput(data=data).is_valid(raise_exception=True)
    if data.get("conversation_id"):
        raise ValidationError({"conversation_id": "本机转存创建独立研究，不能绑定已有私人会话。"})
    request_id = identifier(data.get("request_id"), "request_id")
    get_user_model().objects.select_for_update().get(pk=user.pk)
    fingerprint = request_fingerprint(data, ("schema_version", "local_id", "title", "question", "scope",
        "selections", "notes", "layout", "comparison", "turns"))
    receipt = ResearchImportReceipt.objects.filter(user=user, request_id=request_id).first()
    if receipt:
        if receipt.fingerprint != fingerprint:
            raise ResearchConflict("原转存请求的内容已变化，请先核对已保存的研究。")
        if not receipt.project_id:
            raise ResearchConflict("原转存研究已删除，旧请求不能重新创建该资料。")
        return owned(ResearchProject, user, receipt.project_id)
    existing = ResearchProject.objects.filter(user=user, request_id=request_id).first()
    if existing:
        same_request(existing, fingerprint)
        ResearchImportReceipt.objects.create(user=user, project=existing, request_id=request_id, fingerprint=fingerprint)
        return existing
    warnings = []

    def imported_references(values):
        output, seen = [], set()
        for raw in bounded_list(values, "references"):
            current = resolve_reference(raw, user)
            ref = compact_reference(current)
            key = reference_identity(ref)
            if key not in seen:
                seen.add(key)
                output.append(ref)
                if current["source_status"] != "available":
                    warnings.append({"code": "source_unavailable", "reference_id": key,
                        "message": "保留原文身份，但该来源当前不可读；浏览器缓存正文未转存。"})
        return output

    def imported_scope(raw):
        if raw.get("kind") != "passages":
            return scope_snapshot(raw, user)
        refs = imported_references(raw.get("references", []))
        if not refs:
            raise ValidationError({"scope": "限定原文需要至少一个来源，不会自动扩大到全馆。"})
        return {"kind": "passages", "references": refs, "filters": normalize_filters(raw.get("filters", {})),
                "allow_neighbors": False}

    # Import creates its own record; it cannot attach or overwrite an existing private conversation.
    project = create_project(user, {key: data[key] for key in ("request_id", "title", "question") if key in data})
    payload = unpack(project)
    payload.update(request_fingerprint=fingerprint, scope=imported_scope(data.get("scope", {})),
        selections=imported_references(data.get("selections", [])),
        notes=text(data.get("notes", ""), "notes", 20000),
        import_origin={"kind": "guest_transfer", "local_id": data["local_id"], "at": timezone.now().isoformat()})
    layout = data.get("layout", {})
    if not isinstance(layout, dict) or len(json.dumps(layout)) > 2000:
        raise ValidationError({"layout": "布局偏好过大或无效。"})
    payload["layout"] = layout
    save_data(project, payload)
    if "comparison" in data:
        save_comparison(user, project.id, {**data["comparison"], "expected_revision": project.revision})
        project.refresh_from_db()
        payload = unpack(project)
    imported, pending_parents = {}, []
    for row in bounded_list(data.get("turns", []), "turns", 100):
        local_id = text(row["local_id"], "local_id", 160, True)
        if local_id in imported:
            raise ValidationError({"turns": "每轮本机标识必须唯一。"})
        refs = imported_references(row.get("references", []))
        original_status = row.get("status", "completed")
        # A copied active state is an interrupted history entry, not a submitted server job.
        state = ("partial" if refs else "canceled") if original_status in ACTIVE else original_status
        turn = ResearchTurn.objects.create(project=project, status=state, finished_at=timezone.now(),
            data_ciphertext=pack({"question": row["question"], "scope": imported_scope(row.get("scope", data.get("scope", {}))),
                "mode": "search", "statement": {"proposition": row["question"]}, "result_refs": refs,
                "selected_refs": imported_references(row.get("selected_references", [])), "analysis": [], "warnings": [],
                "notes": text(row.get("notes", ""), "notes", 20000), "return_context": {},
                "import_origin": {"local_id": local_id, "created_at": row.get("created_at"), "status": original_status},
                "branch_id": local_id}))
        imported[local_id] = turn
        pending_parents.append((turn, row.get("parent_local_id")))
    for turn, parent_id in pending_parents:
        if not parent_id:
            continue
        if parent_id not in imported or imported[parent_id].id == turn.id:
            raise ValidationError({"turns": "分支父轮次必须是本次转存的其他轮次。"})
        turn.parent = imported[parent_id]
        turn.save(update_fields=["parent"])
    for turn in imported.values():
        ancestors, parent = {turn.id}, turn.parent
        while parent:
            if parent.id in ancestors:
                raise ValidationError({"turns": "研究分支不能循环引用。"})
            ancestors.add(parent.id)
            parent = parent.parent
    payload["import_warnings"] = list({row["reference_id"]: row for row in warnings}.values())
    payload["imported_turns"] = {local_id: str(turn.id) for local_id, turn in imported.items()}
    if imported:
        payload["last_turn_id"] = str(next(reversed(imported.values())).id)
    save_data(project, payload)
    ResearchImportReceipt.objects.create(user=user, project=project, request_id=request_id, fingerprint=fingerprint)
    return project


@transaction.atomic
def update_project(user, pk, data):
    project = owned(ResearchProject, user, pk, lock=True)
    expect(project, data.get("expected_revision"))
    payload = unpack(project)
    for key, limit in (("title", 240), ("question", 4000), ("notes", 20000)):
        if key in data:
            payload[key] = text(data[key], key, limit, key == "title")
    if "scope" in data:
        payload["scope"] = scope_snapshot(data["scope"], user)
    if "archived" in data:
        if not isinstance(data["archived"], bool):
            raise ValidationError({"archived": "需要布尔值。"})
        project.archived = data["archived"]
    if "layout" in data:
        if not isinstance(data["layout"], dict) or len(json.dumps(data["layout"])) > 2000:
            raise ValidationError({"layout": "布局偏好过大或无效。"})
        payload["layout"] = data["layout"]
    return save_data(project, payload, fields=["archived"])


@transaction.atomic
def change_selection(user, pk, data):
    if "expected_owner_id" in data and (type(data["expected_owner_id"]) is not int or data["expected_owner_id"] != user.pk):
        raise PermissionDenied("登录账户已变化，请重新选择本人研究。")
    project = owned(ResearchProject, user, pk, lock=True)
    payload = unpack(project)
    request_id = identifier(data["request_id"], "request_id") if data.get("request_id") else None
    fingerprint = request_fingerprint(data, ("action", "references", "reference_id", "order", "note", "notes", "additions", "removals"))
    if request_id:
        previous = next((row for row in payload.get("selection_requests", []) if row["id"] == request_id), None)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise ResearchConflict("该选材请求标识已用于不同内容。请保留输入，使用新操作标识。")
            return project
    expect(project, data.get("expected_revision"))
    selected = payload.setdefault("selections", [])
    preserve_selection_note_sources(payload, [*selected, *(row["reference"] for row in payload.get("removed_selections", []))])
    action = data.get("action")
    if action == "apply":
        if not request_id or data.get("expected_owner_id") != user.pk:
            raise ValidationError({"request_id": "整批同步需要原请求标识与账户标识。"})
        # Validate the complete intent before changing membership or saving a receipt.
        additions = references(data.get("additions", []), user)
        removals = bounded_list(data.get("removals", []), "removals")
        if not additions and not removals or len(additions) + len(removals) > MAX_REFS:
            raise ValidationError({"selections": "每批需要 1 至 400 项修改。"})
        if any(not isinstance(key, str) or not key or len(key) > 240 for key in removals) or len(set(removals)) != len(removals):
            raise ValidationError({"removals": "移除身份无效或重复。"})
        existing_ids = {reference_identity(row) for row in selected}
        addition_ids = {reference_identity(row) for row in additions}
        removal_ids = set(removals)
        if removal_ids - existing_ids or addition_ids & removal_ids:
            raise ResearchConflict("选材已经变化或同一材料既加入又移除，请保留整批修改并核对最新选材。")
        removed = [{"position": index, "reference": row} for index, row in enumerate(selected) if reference_identity(row) in removal_ids]
        kept = [row for row in selected if reference_identity(row) not in removal_ids]
        kept_ids = {reference_identity(row) for row in kept}
        merged = [*kept, *(row for row in additions if reference_identity(row) not in kept_ids)]
        bounded_list(merged, "selections")
        payload["selections"] = merged
        payload["removed_selections"] = [*payload.get("removed_selections", []), *removed][-50:]
    elif action == "add":
        new_refs = references(data.get("references", []), user)
        seen = {reference_identity(row) for row in selected}
        added = [row for row in new_refs if reference_identity(row) not in seen]
        selected.extend(added)
        note = text(data.get("note", ""), "note", 200)
        item_notes = data.get("notes", {})
        if not isinstance(item_notes, dict) or len(item_notes) > MAX_REFS or any(key not in {reference_identity(row) for row in new_refs} for key in item_notes):
            raise ValidationError({"notes": "备注只能对应本次选材。"})
        item_notes = {key: text(value, "note", 200) for key, value in item_notes.items()}
        if note or item_notes:
            notes = payload.setdefault("selection_notes", {})
            for row in added:
                key = reference_identity(row)
                notes[key] = item_notes.get(key, note)
                payload.setdefault("selection_note_sources", {})[key] = compact_reference(row)
        bounded_list(selected, "selections")
    elif action == "remove":
        key = str(data.get("reference_id", ""))
        match = next(((i, ref) for i, ref in enumerate(selected) if reference_identity(ref) == key), None)
        if match is None:
            raise NotFound("选材不存在。")
        position, ref = match
        selected.pop(position)
        payload["removed_selections"] = [*payload.get("removed_selections", []), {"position": position, "reference": ref}][-50:]
    elif action == "undo":
        removed = payload.get("removed_selections", [])
        if removed:
            key = data.get("reference_id")
            position = next((i for i in reversed(range(len(removed))) if not key or reference_identity(removed[i]["reference"]) == key), None)
            if position is None:
                raise NotFound("该选材的移除记录已不存在。")
            previous = removed.pop(position)
            resolve_reference(previous["reference"], user, strict=True)
            if reference_identity(previous["reference"]) not in {reference_identity(row) for row in selected}:
                if len(selected) >= MAX_REFS:
                    raise ValidationError({"selections": "选材已达到 400 项，请先移除一项再撤销。"})
                selected.insert(min(previous["position"], len(selected)), previous["reference"])
    elif action == "reorder":
        order = bounded_list(data.get("order"), "order")
        by_id = {reference_identity(row): row for row in selected}
        if len(order) != len(by_id) or set(order) != set(by_id):
            raise ValidationError({"order": "必须恰好包含全部选材，每项一次。"})
        payload["selections"] = [by_id[key] for key in order]
    else:
        raise ValidationError({"action": "支持 add/remove/undo/reorder/apply。"})
    if request_id:
        payload["selection_requests"] = [*payload.get("selection_requests", []), {"id": request_id, "fingerprint": fingerprint}][-100:]
    # Undo history is bounded; reader-authored notes are not disposable undo metadata.
    preserve_selection_note_sources(payload, payload.get("selections", []))
    return save_data(project, payload)


def preserve_selection_note_sources(payload, refs):
    notes = payload.get("selection_notes", {})
    if not notes:
        return
    sources = payload.setdefault("selection_note_sources", {})
    for reference in refs:
        key = reference_identity(reference)
        if notes.get(key):
            sources.setdefault(key, compact_reference(reference))


def selection_note_source(project, user, reference_id):
    if project.user_id != user.pk:
        raise NotFound("该私人选材备注不存在。")
    payload = unpack(project)
    if not payload.get("selection_notes", {}).get(reference_id):
        raise NotFound("该私人选材备注不存在。")
    raw = payload.get("selection_note_sources", {}).get(reference_id)
    if not raw:
        raise NotFound("这条旧备注没有保存原始定位，备注文字仍保留。")
    return note_source_metadata(resolve_reference(raw, user))


def note_source_metadata(source):
    return {name: source[name] for name in ("reference_id", "source_status", "asset_id", "document_revision_id", "pdf_page", "title", "citation", "reader_url") if name in source}


@transaction.atomic
def save_comparison(user, pk, data):
    project = owned(ResearchProject, user, pk, lock=True)
    expect(project, data.get("expected_revision"))
    payload = unpack(project)
    dimensions = [text(value, "dimension", 160, True) for value in bounded_list(data.get("dimensions"), "dimensions", 20)]
    if len(set(dimensions)) != len(dimensions):
        raise ValidationError({"dimensions": "比较维度不能重复。"})
    allowed = {reference_identity(row): row for row in payload.get("selections", [])}
    retained = {reference_identity(row["reference"]): row["reference"]
                for row in payload.get("removed_selections", [])}
    previous = payload.get("comparison", {}).get("cells", [])

    def column_ids(ref):
        return {f"{kind}:{ref[f'{kind}_id']}" for kind in ("edition", "work", "asset") if ref.get(f"{kind}_id")}

    current_columns = {key for ref in allowed.values() for key in column_ids(ref)}
    cells = []
    for cell in bounded_list(data.get("cells", []), "cells", 200):
        if not isinstance(cell, dict) or cell.get("dimension") not in dimensions:
            raise ValidationError({"cells": "比较维度无效。"})
        ids = bounded_list(cell.get("reference_ids", []), "reference_ids")
        if any(not isinstance(key, str) for key in ids):
            raise ValidationError({"cells": "原文标识需要文字。"})
        author = text(cell.get("author", ""), "author", 160)
        column_id = text(cell.get("column_id", ""), "column_id", 160)
        old_cells = [old for old in previous if old.get("dimension") == cell["dimension"] and (
            old.get("column_id", "") == column_id if column_id else
            not old.get("column_id") and old.get("author", "") == author)]
        # Legacy cells can acquire a source column only from their own recorded identities.
        if column_id:
            old_cells += [old for old in previous if old.get("dimension") == cell["dimension"]
                and not old.get("column_id") and old.get("author", "") == author
                and set(old.get("reference_ids", [])) == set(ids)
                and any(column_id in column_ids(allowed.get(key, retained.get(key, {}))) for key in ids)]
            if column_id not in current_columns and not old_cells:
                raise ValidationError({"column_id": "文献列必须来自当前选材或已保存的比较格。"})
        retained_ids = {key for old in old_cells for key in old.get("reference_ids", [])}
        if any(key not in allowed and key not in retained_ids for key in ids):
            raise ValidationError({"cells": "比较只能引用当前研究已选材料。"})
        if column_id and any(key not in retained_ids and column_id not in column_ids(allowed[key]) for key in ids):
            raise ValidationError({"cells": "新增原文必须属于该比较格的文献或版本。"})
        cells.append({"dimension": cell["dimension"], "author": author,
                      **({"column_id": column_id} if column_id else {}),
                      "reference_ids": ids, "note": text(cell.get("note", ""), "note", 8000),
                      "evidence_status": "selected" if ids else "missing"})
    payload["comparison"] = {"dimensions": dimensions, "cells": cells}
    return save_data(project, payload)


def counterargument_query(statement, question):
    """Explicit subject/time/place describe the query, never publication filters."""
    parts = [question]
    for key, label in (("subject", "对象"), ("object", "涉及内容"), ("population_scope", "研究对象"),
                       ("geographic_scope", "地区"), ("temporal_scope", "研究时间"), ("qualifiers", "条件")):
        value = statement.get(key)
        if value in (None, "", [], {}):
            continue
        value = value.strip() if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
        if value:
            parts.append(f"{label}：{value}")
    query = "\n".join(parts)
    if len(query) > 1200:
        raise ValidationError({"statement": "原命题与检索条件合计不能超过1200字符，请缩短条件后再检索；输入不会被自动截断。"})
    return {"query": query, "method": "explicit_conditions" if len(parts) > 1 else "original_proposition",
        "notice": "对象、地区、时间和条件用于检索语境与原文比较，不是出版年份过滤，也不证明结果符合条件。"}


@transaction.atomic
def start_turn(request, project_id, data):
    project = owned(ResearchProject, request.user, project_id, lock=True)
    request_id = identifier(data.get("request_id"), "request_id")
    existing = project.turns.filter(request_id=request_id).first()
    question = text(data.get("question"), "question", 1200, True)
    fingerprint = request_fingerprint(data, ("question", "parent_id", "scope", "mode", "statement", "subclaims",
        "active_subclaim_id", "expand_from_parent", "return_context"))
    if len(question) < 2:
        raise ValidationError({"question": "至少输入 2 个字符。"})
    if existing:
        return same_request(existing, fingerprint)
    expect(project, data.get("expected_revision"))
    if project.archived:
        raise ResearchConflict("请先恢复已归档研究。")
    parent = owned(ResearchTurn, request.user, data["parent_id"]) if data.get("parent_id") else None
    if parent and parent.project_id != project.id:
        raise ValidationError({"parent_id": "分支必须属于当前研究。"})
    payload = unpack(project)
    scope = scope_snapshot(data.get("scope", unpack(parent).get("scope") if parent else payload["scope"]), request.user)
    mode = data.get("mode", "search")
    if mode not in {"search", "counterargument"}:
        raise ValidationError({"mode": "研究模式无效。"})
    statement = data.get("statement", {"proposition": question})
    if not isinstance(statement, dict) or len(json.dumps(statement)) > 8000:
        raise ValidationError({"statement": "命题结构无效或过长。"})
    statement = {key: statement[key] for key in ("proposition", "subject", "predicate", "object", "polarity",
                 "modality", "qualifiers", "temporal_scope", "geographic_scope", "population_scope") if key in statement}
    statement["proposition"] = text(statement.get("proposition", question), "proposition", 1200, True)
    parent_data = unpack(parent) if parent else {}
    subclaims = normalize_subclaims(data.get("subclaims", parent_data.get("subclaims", [])))
    active_subclaim_id = data.get("active_subclaim_id", parent_data.get("active_subclaim_id") if mode == "counterargument" else None)
    if active_subclaim_id is not None:
        active_subclaim_id = identifier(active_subclaim_id, "active_subclaim_id")
        chosen = next((row for row in subclaims if row["id"] == active_subclaim_id), None)
        if chosen is None or mode != "counterargument":
            raise ValidationError({"active_subclaim_id": "请选择本轮反证研究中本人明确保存的子命题。"})
        statement = {key: value for key, value in chosen.items() if key != "id"}
    reminders = plan_memory_rows(request.user, payload)
    search_question = statement["proposition"] if active_subclaim_id else question
    query_plan = counterargument_query(statement, search_question) if mode == "counterargument" else None
    turn = ResearchTurn.objects.create(project=project, parent=parent, request_id=request_id,
        task_id=str(uuid4()), data_ciphertext=pack({"request_fingerprint": fingerprint, "question": question, "scope": scope, "mode": mode,
        "statement": statement, "subclaims": subclaims, "active_subclaim_id": active_subclaim_id,
        "search_question": search_question, **({"query_plan": query_plan} if query_plan else {}),
        "analysis_statement": statement, "input_revision": project.revision, "selected_refs": payload.get("selections", []),
        "project_snapshot": {"title": payload.get("title", ""), "notes": payload.get("notes", "")},
        "result_refs": unpack(parent).get("result_refs", []) if parent and data.get("expand_from_parent") is True else [],
        "analysis": [], "warnings": [], "parent_id": str(parent.id) if parent else None,
        "memory_reminder_revisions": {str(row.id): row.revision for row in reminders},
        "branch_id": str(parent.id) if parent else str(uuid4()), "return_context": data.get("return_context", {})}))
    payload["last_turn_id"] = str(turn.id)
    save_data(project, payload)
    from .tasks import enqueue_research_turn
    transaction.on_commit(lambda: enqueue_research_turn(turn.id, turn.generation, turn.task_id))
    return turn


def normalize_subclaims(values):
    from .research_serializers import SubclaimInput
    output, seen = [], set()
    for row in bounded_list(values, "subclaims", 12):
        serializer = SubclaimInput(data=row)
        serializer.is_valid(raise_exception=True)
        claim = dict(serializer.validated_data)
        claim["id"] = str(claim["id"])
        if claim["id"] in seen:
            raise ValidationError({"subclaims": "每个子命题的标识必须唯一。"})
        if len(json.dumps(claim)) > 8000:
            raise ValidationError({"subclaims": "单个子命题范围说明过长。"})
        seen.add(claim["id"])
        output.append(claim)
    return output


@transaction.atomic
def save_subclaims(user, pk, data):
    turn = owned(ResearchTurn, user, pk, lock=True)
    expect(turn, data.get("expected_revision"))
    if turn.status in ACTIVE:
        raise ResearchConflict("请先等待本轮结束或取消；旧分析所用命题不会被修改。")
    payload = unpack(turn)
    if payload.get("mode") != "counterargument":
        raise ValidationError({"subclaims": "只有反证研究轮次可以保存子命题。"})
    values = normalize_subclaims(data.get("subclaims"))
    payload.setdefault("subclaims_history", []).append({"revision": turn.revision,
        "at": timezone.now().isoformat(), "subclaims": payload.get("subclaims", [])})
    payload["subclaims"] = values
    if payload.get("active_subclaim_id") not in {row["id"] for row in values}:
        payload["active_subclaim_id"] = None
    payload["subclaim_notice"] = "子命题由本人明确拆分；修改用于后续分支，本轮既有分析仍对应 analysis_statement。"
    payload.setdefault("analysis_statement", payload["statement"])
    return save_data(turn, payload)


@transaction.atomic
def cancel_turn(user, pk):
    turn = owned(ResearchTurn, user, pk, lock=True)
    if turn.status in ACTIVE:
        from catalog.discovery_models import DiscoverySearchSession
        from catalog.services.discovery_sessions import cancel_session
        session = DiscoverySearchSession.objects.filter(pk=turn.discovery_session_id, owner=user).first()
        if session:
            cancel_session(session)
        turn.status, turn.finished_at = "canceled", timezone.now()
        turn.generation += 1
        turn.save(update_fields=["status", "finished_at", "generation", "updated_at"])
    return turn


def analyze_references(statement, refs, user):
    """Reuse claim rules, retaining them as signals rather than verified support."""
    from catalog.models import DerivedClaim
    from catalog.services.claims.attribution import infer_attribution
    from catalog.services.claims.stance import classify_stance
    output = []
    for ref in refs[:MAX_REFS]:
        current = resolve_reference(ref, user)
        if current["source_status"] != "available":
            continue
        claim = DerivedClaim.objects.filter(primary_evidence_id=current.get("evidence_span_id"),
            document_revision_id=current["document_revision_id"], status="active").order_by("-quality_score").first()
        candidate = ({key: getattr(claim, key) for key in ("proposition", "subject", "predicate", "object", "polarity",
                     "modality", "qualifiers", "temporal_scope", "geographic_scope", "population_scope", "attribution", "claim_type")}
                     if claim else {"proposition": current["quote"], "attribution": infer_attribution(current["quote"]).attribution})
        signal = classify_stance(statement, candidate).as_dict()
        # Lexical criticism can target somebody else. It must never certify counterevidence.
        output.append({"id": reference_identity(ref), "reference": ref, "candidate_statement": candidate,
                       "rule_signal": {key: signal[key] for key in ("stance", "reasons", "query_polarity", "candidate_polarity")},
                       "relation": "insufficient_evidence", "status": "needs_review", "decision": None,
                       "reason": "规则仅标出可能的关系；需核对论断对象、范围和转引归属。",
                       "claim_id": str(claim.id) if claim else None, "analysis_version": ANALYSIS_VERSION})
    return output


@transaction.atomic
def decide_analysis(user, pk, data):
    # Same user -> project -> turn order as deletion and explicit note creation.
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=user.pk)
    owner_turn = owned(ResearchTurn, user, pk)
    owned(ResearchProject, user, owner_turn.project_id, lock=True)
    turn = owned(ResearchTurn, user, pk, lock=True)
    payload = unpack(turn)
    request_id = identifier(data["request_id"], "request_id") if data.get("request_id") else None
    fingerprint = request_fingerprint(data, ("id", "action", "relation", "note", "attribution", "scope_note", "save_as_note"))
    receipt = next((item for item in payload.get("analysis_requests", []) if item["request_id"] == request_id), None) if request_id else None
    if receipt:
        if receipt["fingerprint"] != fingerprint:
            raise ResearchConflict("该请求标识已用于其他分类决定，请为新决定使用新标识。")
        return turn
    expect(turn, data.get("expected_revision"))
    if turn.status in ACTIVE:
        raise ResearchConflict("请等待本轮结束后确认，已得到的材料会保留。")
    action = data.get("action", "confirm")
    if action not in {"confirm", "clear"}:
        raise ValidationError({"action": "支持确认或撤销本人决定。"})
    row = next((row for row in payload.get("analysis", []) if row["id"] == data.get("id")), None)
    if row is None:
        raise NotFound("分析候选不存在。")
    memory_id = None
    decision = None
    relation = "insufficient_evidence"
    if action == "confirm":
        from catalog.models import DerivedClaim
        relation = data.get("relation")
        if relation not in {"support", "different_conclusion", "qualification", "reframe", "insufficient_evidence", "unrelated"}:
            raise ValidationError({"relation": "关系类型无效。"})
        current = resolve_reference(row["reference"], user, strict=True)
        note = text(data.get("note", ""), "note", 4000, True)
        attribution = data.get("attribution", "uncertain")
        if attribution not in DerivedClaim.Attribution.values:
            raise ValidationError({"attribution": "归属类型无效。"})
        scope_note = text(data.get("scope_note", ""), "scope_note", 4000)
        if "save_as_note" in data and not isinstance(data["save_as_note"], bool):
            raise ValidationError({"save_as_note": "需要布尔值。"})
        if data.get("save_as_note"):
            if not request_id:
                raise ValidationError({"request_id": "同时保存本人笔记须提供幂等请求标识。"})
            memory = create_memory(user, {"request_id": request_id, "body": note, "kind": "observation",
                "project_id": str(turn.project_id), "turn_id": str(turn.id), "sources": [compact_reference(current)]})
            memory_id = str(memory.id)
        decision = {"by": "owner", "at": timezone.now().isoformat(), "relation": relation,
            "note": note, "attribution": attribution, "scope_note": scope_note,
            **({"memory_id": memory_id} if memory_id else {})}
    elif data.get("save_as_note"):
        raise ValidationError({"save_as_note": "撤销分类不会新建笔记；已有本人笔记独立保留。"})
    if row.get("decision"):
        row.setdefault("decision_history", []).append({"revision": turn.revision, "at": timezone.now().isoformat(),
            "relation": row.get("relation"), "decision": row["decision"], "action": action})
    row.update(relation=relation, status="user_confirmed" if decision else "needs_review", decision=decision)
    if request_id:
        payload.setdefault("analysis_requests", []).append({"request_id": request_id, "fingerprint": fingerprint, "memory_id": memory_id})
    return save_data(turn, payload)


def serialize_record(record, user, *, memory_context_rows=None):
    if hasattr(record, "status") and record.status in ACTIVE and timezone.now() - record.updated_at > timedelta(minutes=30):
        type(record).objects.filter(pk=record.id, generation=record.generation, status__in=ACTIVE,
            updated_at__lt=timezone.now() - timedelta(minutes=30)).update(
            status="failed", error_code="task_timeout", finished_at=timezone.now())
        record.refresh_from_db()
    payload = unpack(record)
    if isinstance(record, PersonalReadingPlan) and payload.get("origin", {}).get("type") in {"path_follow", "public_path_copy"}:
        from .path_plans import record_output
        result = record_output(record, user)
        return {**{key: result[key] for key in ("id", "revision", "data", "created_at", "updated_at")},
            "status": "completed", "enhancement_status": "not_requested", "poll_after_ms": None,
            "project_id": str(record.project_id) if record.project_id else None}
    payload.pop("source_paragraphs", None)
    # Immutable input for incremental processing, not a second report/export.
    payload.pop("version_baseline", None)
    payload.pop("version_children", None)
    payload.pop("text_units", None)
    payload.pop("analysis_requests", None)
    selection_requests = payload.pop("selection_requests", [])
    if isinstance(record, ResearchProject):
        payload["selection_receipts"] = [row["id"] for row in selection_requests][-100:]
    if "ocr_units" in payload:
        payload["ocr_units"] = {key: {name: value for name, value in unit.items() if name not in {"text", "blocks"}}
                                for key, unit in payload["ocr_units"].items()}
    for key in ("selections", "result_refs", "selected_refs", "sources"):
        if key in payload:
            payload[key] = [resolve_reference(ref, user) for ref in payload[key]]
    if "selection_note_sources" in payload:
        current = {reference_identity(ref): ref for ref in payload.get("selections", [])}
        note_sources = {}
        for key, raw in payload["selection_note_sources"].items():
            if not payload.get("selection_notes", {}).get(key):
                continue
            candidate = current.get(key)
            # Ordinary polling must not re-read every historical note's original source.
            source = candidate if candidate and compact_reference(candidate) == raw else {"reference_id": key, "source_status": "unverified"}
            note_sources[key] = note_source_metadata(source)
        payload["selection_note_sources"] = note_sources
    if "comparison" in payload:
        available = {reference_identity(ref) for ref in payload.get("selections", [])
                     if ref["source_status"] == "available"}
        for cell in payload["comparison"].get("cells", []):
            ids = set(cell.get("reference_ids", []))
            readable = ids & available
            # A saved judgment survives removal or withdrawal; its evidence status does not.
            cell["evidence_status"] = ("missing" if not ids else "selected" if readable == ids
                                       else "partial" if readable else "unavailable")
    if isinstance(payload.get("scope"), dict):
        payload["scope"] = {**payload["scope"], "references": [resolve_reference(ref, user) for ref in payload["scope"].get("references", [])]}
    if "comparison_draft" in payload:
        from .research_comparison import project_draft
        project_draft(payload)
    for row in payload.get("analysis", []):
        current = resolve_reference(row["reference"], user)
        row["reference"] = current
        if current["source_status"] != "available":
            row.pop("candidate_statement", None)
            row.pop("rule_signal", None)
            row.pop("model_suggestion", None)
            row["status"] = "source_unavailable"
    # Source text and embeddings never belong in revision snapshots or export.
    payload.pop("removed_selections", None)
    output = {"id": str(record.id), "revision": record.revision, "data": payload,
              "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat()}
    for key in ("status", "state", "archived", "generation", "error_code", "completed_units", "total_units"):
        if hasattr(record, key):
            output[key] = getattr(record, key)
    if hasattr(record, "status"):
        output["poll_after_ms"] = 2000 if record.status in ACTIVE else None
    if hasattr(record, "finished_at"):
        output["finished_at"] = record.finished_at.isoformat() if record.finished_at else None
    if isinstance(record, ResearchTurn):
        output.update(project_id=str(record.project_id), request_id=str(record.request_id), parent_id=str(record.parent_id) if record.parent_id else None,
                      discovery_session_id=str(record.discovery_session_id) if record.discovery_session_id else None)
    elif hasattr(record, "project_id"):
        output["project_id"] = str(record.project_id) if record.project_id else None
    if isinstance(record, ResearchProject):
        output["conversation_id"] = str(record.conversation_id) if record.conversation_id else None
        payload.setdefault("use_confirmed_memories", False)
        payload.setdefault("confirmed_memory_ids", [])
    if isinstance(record, ResearchTurn):
        # Rehydrate only the original revision still authorized in this project now.
        project = ResearchProject.objects.filter(pk=record.project_id, user=user).first()
        current = {str(row.id): row for row in plan_memory_rows(user, unpack(project))} if project else {}
        versions = payload.get("memory_reminder_revisions", {})
        payload["memory_reminders"] = [{"id": key, "revision": row.revision,
            "body": unpack(row).get("body", ""), "kind": unpack(row).get("kind", "understanding"),
            "notice": "本人已确认的私人笔记提醒，不是公开文献证据。"}
            for key, row in current.items() if versions.get(key) == row.revision]
        payload["memory_reminders_status"] = ("current" if len(payload["memory_reminders"]) == len(versions)
            else "authorization_changed") if versions else "not_requested"
    if isinstance(record, PersonalReadingPlan):
        payload.setdefault("use_confirmed_memories", False)
        payload.setdefault("confirmed_memory_ids", [])
        if not plan_suggestions_current(user, payload):
            invalidate_plan_suggestions(payload, "authorization_changed")
        if payload.get("generation_status") == "queued":
            source_turn = ResearchTurn.objects.filter(pk=payload.get("origin", {}).get("turn_id"), project__user=user).first()
            if (source_turn is None or source_turn.status in {"failed", "canceled"}
                    or timezone.now() - record.updated_at > timedelta(minutes=35)):
                payload["generation_status"] = "failed"
                payload["error_code"] = "source_research_incomplete"
        for edge in payload.get("prerequisites", []):
            edge["reference"] = resolve_reference(edge["reference"], user)
        editions = {str(edition.id): edition for edition in source_queryset("edition", access_for(user)).filter(
            pk__in=[item["edition_id"] for item in payload.get("items", [])]).select_related("active_catalog_revision")}
        for item in payload.get("items", []):
            edition = editions.get(item["edition_id"])
            current_edition = bool(edition and str(edition.active_catalog_revision.reader_asset_id) == item.get("asset_id")
                and str(edition.active_catalog_revision.document_revision_id) == item.get("document_revision_id"))
            if item.get("reference"):
                item["reference"] = resolve_reference(item["reference"], user)
                item["available"] = item["reference"]["source_status"] == "available"
                item["reader_url"] = item["reference"].get("reader_url") if item["available"] else None
            else:
                item["available"] = current_edition
                item["reader_url"] = (f"/reader/{item['asset_id']}?page=1&revision={item['document_revision_id']}"
                    if current_edition else None)
            snapshot = edition.active_catalog_revision.snapshot if current_edition and item["available"] else {}
            snapshot = snapshot or {}
            work = snapshot.get("work") or {}
            item["authors"] = [str(row.get("name") or (row.get("person") or {}).get("preferred_name") or "")
                for row in (snapshot.get("contributions", snapshot.get("contributors")) or [])
                if isinstance(row, dict) and row.get("role") == "author"]
            item["publication_year"] = (snapshot.get("edition") or {}).get("publication_year")
            item.update(snapshot_cover(edition if current_edition and item["available"] else None))
            if not item["available"]:
                item["reader_url"] = None
                item.pop("model_suggestion", None)
        output["status"] = payload.get("generation_status", "completed")
        output["poll_after_ms"] = 2000 if output["status"] in ACTIVE else None
        output["enhancement_status"] = payload.get("enhancement_status", "not_requested")
        if output["enhancement_status"] in ACTIVE:
            output["poll_after_ms"] = 2000
            if timezone.now() - record.updated_at > timedelta(minutes=10):
                payload["enhancement_status"] = "unavailable"
                output.update(enhancement_status="unavailable", poll_after_ms=None)
    if isinstance(record, ResearchMemory):
        payload.update(memory_source_details(user, payload))
        payload["usage_scopes"] = [row for row in memory_usage_targets(user, record, contexts=memory_context_rows) if row["selected"]]
        for snapshot in payload.get("history", []):
            snapshot["data"]["sources"] = [resolve_reference(ref, user) for ref in snapshot["data"].get("sources", [])]
            snapshot["data"].update(memory_source_details(user, snapshot["data"]))
    if hasattr(record, "content_hash"):
        from .citation_audit import UPLOAD_CHECKS, refresh_bibliography_sources
        from .citation_sources import refresh_private_sources
        payload["purpose"] = record.purpose
        if record.purpose == "private_source":
            payload["source_generation"] = record.generation
        payload.setdefault("checks", list(UPLOAD_CHECKS))
        payload.setdefault("scope", "public_library")
        refresh_bibliography_sources(payload)
        if record.purpose == "manuscript":
            refresh_private_sources(payload, user)
        occurrences = [*payload.get("occurrences", []), *(row for report in payload.get("parse_history", []) for row in report.get("occurrences", []))]
        for occurrence in occurrences:
            for version in [occurrence, *occurrence.get("history", [])]:
                for finding in version.get("findings", []):
                    if "references" in finding:
                        finding["references"] = [resolve_reference(ref, user) for ref in finding["references"]]
                        available = [ref for ref in finding["references"] if ref["source_status"] == "available"]
                        if finding["references"] and not available:
                            finding.update(status="unverified", source_status="source_unavailable",
                                page_status="needs_review", message="原文已变化、撤回或不可访问；原匹配记录保留，当前需重新核对。")
                        elif finding.get("claimed_printed_label"):
                            # A different surviving text match cannot support the old page claim.
                            from catalog.services.page_label_metadata import claimed_page_status
                            finding["page_status"] = claimed_page_status(available, finding["claimed_printed_label"])
                            if any(anchor.get("printed_label_precision") == "spread" for ref in available for anchor in ref.get("anchors", [ref])):
                                finding["message"] = "原文位于双页扫描的同一PDF页；尚不能确定所引文字属于哪一印刷页，请查看原件核对。"
                analysis = version.get("support_analysis")
                if analysis:
                    analysis["reference"] = resolve_reference(analysis["reference"], user)
                    if analysis["reference"]["source_status"] != "available":
                        analysis["suggestions"] = []
                        analysis["status"] = "source_unavailable"
    payload.pop("request_fingerprint", None)
    return output


def source_project(user, data):
    return owned(ResearchProject, user, data["project_id"]) if data.get("project_id") else None


def annotation_source(user, note):
    if note.orphaned or note.asset_sha256 != note.asset.sha256 or note.page.asset_id != note.asset_id:
        return None
    saved = note.selector.get("citation_reference") if isinstance(note.selector, dict) else None
    if saved:
        # Citation-drawer excerpts retain the exact file, text revision and range;
        # old annotations continue through their original page-based resolver.
        from django.contrib.auth.models import AnonymousUser
        try:
            current = resolve_reference(saved, AnonymousUser())
        except ValidationError:
            return None
        if (current.get("source_status") != "available" or current.get("asset_id") != str(note.asset_id)
                or current.get("pdf_page") != note.page.index or current.get("quote") != note.quote):
            return None
        return compact_reference(current)
    edition = source_queryset("edition", access_for(user)).filter(
        active_catalog_revision__reader_asset_id=note.asset_id).first()
    if edition is None:
        return None
    ref = resolve_reference({"asset_id": str(note.asset_id), "pdf_page": note.page.index,
        "document_revision_id": str(edition.active_catalog_revision.document_revision_id)}, user)
    if note.quote and note.quote not in ref.get("quote", ""):
        return None
    return compact_reference(ref) if ref["source_status"] == "available" else None


def memory_source_details(user, payload):
    """Resolve live public sources; private authored text survives source withdrawal."""
    statuses, summaries = [], []
    for raw in payload.get("sources", []):
        current = resolve_reference(raw, user)
        edition = source_queryset("edition", access_for(user)).filter(pk=current.get("edition_id")).first() if current.get("edition_id") else None
        status = current["source_status"]
        if status != "available" and edition is not None:
            revision = edition.active_catalog_revision
            if (str(revision.document_revision_id) != str(current.get("document_revision_id"))
                    or str(revision.reader_asset_id) != str(current.get("asset_id"))):
                status = "updated"
            elif current.get("content_hash"):
                # An exact locator/hash no longer resolves on the serving revision.
                status = "updated"
        statuses.append(status)
        summary = {"source_status": status, "reference_id": reference_identity(raw),
            "asset_id": current.get("asset_id"), "edition_id": current.get("edition_id"),
            "pdf_page": current.get("pdf_page"), "reader_url": current.get("reader_url")}
        if edition is not None:
            snapshot = edition.active_catalog_revision.snapshot or {}
            work, version = snapshot.get("work") or {}, snapshot.get("edition") or {}
            summary.update(title=work.get("title", ""),
                authors=[str(item.get("name") or (item.get("person") or {}).get("preferred_name") or "")
                    for item in snapshot.get("contributions", []) if isinstance(item, dict) and item.get("role") == "author"],
                edition=version.get("version_label") or version.get("publisher") or "",
                publication_year=version.get("publication_year"),
                printed_label=current.get("printed_label") if status == "available" else None,
                **snapshot_cover(edition),
                current_reader_url=f"/reader/{edition.active_catalog_revision.reader_asset_id}?revision={edition.active_catalog_revision.document_revision_id}")
        summaries.append(summary)
    origin = payload.get("origin", {})
    origin_note = None
    if origin.get("annotation_id"):
        note = Annotation.objects.select_related("asset", "page").filter(pk=origin["annotation_id"], user=user).first()
        origin_note = {"id": origin["annotation_id"], "available": note is not None, "source_status": "unavailable"}
        if note:
            current = annotation_source(user, note)
            saved = resolve_reference(origin["source"], user) if origin.get("source") else None
            readable = (current is not None and saved is not None and saved["source_status"] == "available"
                and all(str(current.get(key)) == str(saved.get(key)) for key in
                    ("asset_id", "document_revision_id", "pdf_page", "content_hash")))
            origin_note.update(body=decrypt_private_text(note.body_ciphertext), kind=note.kind,
                asset_id=str(note.asset_id), pdf_page=note.page.index,
                quote=note.quote if readable else "", reader_url=saved.get("reader_url") if readable else None,
                source_status="available" if readable else "updated" if current else "unavailable",
                created_at=note.created_at.isoformat(), updated_at=note.updated_at.isoformat())
            if summaries:
                origin_note.update({key: value for key, value in summaries[0].items()
                    if key in {"title", "authors", "edition", "publication_year", "cover_url", "cover_media", "printed_label"}})
        if not statuses:
            statuses.append(origin_note["source_status"])
    source_status = ("unavailable" if "unavailable" in statuses else "updated" if "updated" in statuses
        else "available" if statuses else "no_source")
    return {"source_status": source_status, "source_summaries": summaries, "origin_note": origin_note}


def memory_contexts(user, *, lock=False):
    # ponytail: owner-local encrypted scan; add indexed grant records only if account scale requires it.
    if lock:
        from django.contrib.auth import get_user_model
        # Serialize scope creation with revoke-all; lock contexts before any memory.
        get_user_model().objects.select_for_update().get(pk=user.pk)
    output = []
    for kind, model in (("project", ResearchProject), ("plan", PersonalReadingPlan)):
        rows = model.objects.filter(user=user).order_by("id")
        output.extend((kind, row) for row in (rows.select_for_update() if lock else rows))
    return output


def memory_usage_targets(user, memory, *, contexts=None):
    targets = []
    for kind, record in contexts if contexts is not None else memory_contexts(user):
        payload = unpack(record)
        enabled = payload.get("use_confirmed_memories") is True
        targets.append({"kind": kind, "id": str(record.id), "revision": record.revision,
            "title": (payload.get("title") if kind == "project" else payload.get("goal")) or "未命名",
            "enabled": enabled, "selected": enabled and memory.state == "confirmed"
                and str(memory.id) in payload.get("confirmed_memory_ids", []),
            "archived": bool(getattr(record, "archived", False))})
    return targets


def revoke_memory_contexts(memory, contexts):
    for _, record in contexts:
        payload = unpack(record)
        ids = payload.get("confirmed_memory_ids", [])
        if str(memory.id) not in ids:
            continue
        payload["confirmed_memory_ids"] = [key for key in ids if key != str(memory.id)]
        payload["use_confirmed_memories"] = bool(payload["confirmed_memory_ids"])
        if isinstance(record, PersonalReadingPlan):
            invalidate_plan_suggestions(payload, "authorization_changed")
        save_data(record, payload)


@transaction.atomic
def update_memory_usage(user, pk, data):
    # Contexts precede memories, matching plan workers' lock order.
    contexts = memory_contexts(user, lock=True)
    memory = owned(ResearchMemory, user, pk, lock=True)
    expect(memory, data.get("expected_revision"))
    action = data.get("action")
    if action not in {"grant", "revoke", "revoke_all"}:
        raise ValidationError({"action": "授权操作无效。"})
    if action == "grant" and memory.state != "confirmed":
        raise ValidationError({"state": "请先由本人确认笔记，再明确选择使用范围。"})
    targets = bounded_list(data.get("targets", []), "targets", 100)
    if action != "revoke_all" and not targets:
        raise ValidationError({"targets": "请明确选择研究或阅读计划。"})
    selected, seen = [], set()
    available = {(kind, str(record.id)): record for kind, record in contexts}
    for target in targets:
        key = (target.get("kind"), identifier(target.get("id")))
        if key not in available:
            raise NotFound("使用范围不存在。")
        if key in seen:
            raise ValidationError({"targets": "使用范围不能重复。"})
        seen.add(key)
        record = available[key]
        expect(record, target.get("expected_revision"))
        if action == "grant" and getattr(record, "archived", False):
            raise ValidationError({"targets": "已归档研究不能新增授权，请先恢复。"})
        selected.append(record)
    if action == "revoke_all":
        seen = {(kind, str(record.id)) for kind, record in contexts
            if str(memory.id) in unpack(record).get("confirmed_memory_ids", [])}
        revoke_memory_contexts(memory, contexts)
    else:
        for record in selected:
            payload = unpack(record)
            ids = list(payload.get("confirmed_memory_ids", []))
            if action == "grant":
                if payload.get("use_confirmed_memories") is not True:
                    ids = []
                ids = list(dict.fromkeys([*ids, str(memory.id)]))
                if len(ids) > 40:
                    raise ValidationError({"targets": "每个研究或计划最多授权 40 条笔记。"})
            else:
                ids = [key for key in ids if key != str(memory.id)]
            payload.update(confirmed_memory_ids=ids, use_confirmed_memories=bool(ids))
            if isinstance(record, PersonalReadingPlan):
                invalidate_plan_suggestions(payload, "authorization_changed")
            save_data(record, payload)
    payload = unpack(memory)
    payload.setdefault("usage_history", []).append({"at": timezone.now().isoformat(), "action": action,
        "targets": [{"kind": kind, "id": key} for kind, key in sorted(seen)]})
    return save_data(memory, payload)


@transaction.atomic
def delete_memory(user, pk, revision):
    contexts = memory_contexts(user, lock=True)
    memory = owned(ResearchMemory, user, pk, lock=True)
    expect(memory, revision)
    revoke_memory_contexts(memory, contexts)
    memory.delete()


def list_memories(user, filters):
    """Exact encrypted owner search, counted before state filter, never page-local counts."""
    query = filters.get("q", "").casefold().strip()
    rows = ResearchMemory.objects.filter(user=user).order_by("-created_at" if filters.get("order") == "newest" else "-updated_at", "id")
    matches, counts = [], {"total": 0, "confirmed": 0, "proposed": 0, "ignored": 0, "needs_revision": 0, "revised": 0}
    for row in rows.iterator(chunk_size=100):
        payload = unpack(row)
        if filters.get("kind", "all") != "all" and payload.get("kind") != filters["kind"]:
            continue
        if query and query not in payload.get("body", "").casefold():
            continue
        source_status = memory_source_details(user, payload)["source_status"]
        revised = bool(payload.get("history"))
        needs_revision = source_status in {"updated", "unavailable"} or row.state == "proposed" and revised
        if filters.get("source_status", "all") != "all" and source_status != filters["source_status"]:
            continue
        counts["total"] += 1
        counts[row.state] = counts.get(row.state, 0) + 1
        counts["needs_revision"] += int(needs_revision)
        counts["revised"] += int(revised)
        state = filters.get("state", "all")
        if state in {"all", row.state} or state == "needs_revision" and needs_revision or state == "revised" and revised:
            matches.append(row)
    return matches, counts


@transaction.atomic
def create_memory(user, data):
    request_id = identifier(data.get("request_id"), "request_id")
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=user.pk)
    existing = ResearchMemory.objects.filter(user=user, request_id=request_id).first()
    fingerprint = request_fingerprint(data, ("body", "kind", "project_id", "turn_id", "annotation_id", "sources"))
    if existing:
        return same_request(existing, fingerprint)
    from .privacy import require_retention
    require_retention(user, "personal_notes")
    project = source_project(user, data)
    kind = data.get("kind", "understanding")
    if kind not in MEMORY_KINDS:
        raise ValidationError({"kind": "认识类型无效。"})
    body = text(data.get("body", ""), "body", 20000, True)
    sources = references(data.get("sources", []), user)
    origin = {}
    if data.get("annotation_id"):
        note = Annotation.objects.select_related("asset", "page").filter(pk=identifier(data["annotation_id"]), user=user).first()
        if note is None:
            raise NotFound("笔记不存在。")
        origin["annotation_id"] = str(note.id)
        ref = annotation_source(user, note)
        if ref:
            origin["source"] = ref
            sources = [ref, *[item for item in sources if reference_identity(item) != reference_identity(ref)]]
    if data.get("turn_id"):
        turn = owned(ResearchTurn, user, data["turn_id"])
        if project and turn.project_id != project.id:
            raise ValidationError({"turn_id": "轮次不属于当前研究。"})
        project = project or turn.project
        origin["turn_id"] = str(turn.id)
    return ResearchMemory.objects.create(user=user, request_id=request_id, project=project, state="proposed", data_ciphertext=pack({
        "request_fingerprint": fingerprint, "kind": kind, "body": body, "sources": sources, "origin": origin, "authorship": "user",
        "model_suggestion": "", "history": [], "notice": "保存认识不表示赞同来源作者。"}))


@transaction.atomic
def update_memory(user, pk, data):
    contexts = memory_contexts(user, lock=True)
    memory = owned(ResearchMemory, user, pk, lock=True)
    expect(memory, data.get("expected_revision"))
    payload = unpack(memory)
    if "refresh_origin" in data and not isinstance(data["refresh_origin"], bool):
        raise ValidationError({"refresh_origin": "需要布尔值。"})
    old = {"body": payload.get("body", ""), "kind": payload.get("kind", "understanding"),
        "sources": payload.get("sources", []), "origin": payload.get("origin", {})}
    old["state"] = memory.state
    if "body" in data:
        payload["body"] = text(data["body"], "body", 20000, True)
    if "sources" in data:
        payload["sources"] = references(data["sources"], user)
    if "kind" in data:
        if data["kind"] not in MEMORY_KINDS:
            raise ValidationError({"kind": "认识类型无效。"})
        payload["kind"] = data["kind"]
    if data.get("refresh_origin") is True:
        note = Annotation.objects.select_related("asset", "page").filter(
            pk=payload.get("origin", {}).get("annotation_id"), user=user).first()
        ref = annotation_source(user, note) if note else None
        if not ref:
            raise ValidationError({"refresh_origin": "原笔记来源当前不可用，不能自动改指其他版本。"})
        old_origin_source = payload.get("origin", {}).get("source")
        replaced = {reference_identity(ref)}
        if old_origin_source:
            replaced.add(reference_identity(old_origin_source))
        payload["sources"] = [ref, *[item for item in payload.get("sources", [])
            if reference_identity(item) not in replaced]]
        payload["origin"] = {**payload.get("origin", {}), "source": ref}
    content_changed = any(payload.get(key, old[key]) != old[key] for key in ("body", "kind", "sources", "origin"))
    state = data.get("state", "proposed" if content_changed else memory.state)
    if state not in {"proposed", "confirmed", "ignored"}:
        raise ValidationError({"state": "状态无效；遗忘请使用删除操作。"})
    # Confirmation applies to this content revision; it does not grant the edited
    # body/source to contexts authorized for the previous revision.
    if content_changed or state != "confirmed":
        revoke_memory_contexts(memory, contexts)
    payload.setdefault("history", []).append({"revision": memory.revision, "state": memory.state,
        "at": timezone.now().isoformat(), "data": old})
    memory.state, memory.embedding_ciphertext, memory.embedding_artifact = state, b"", ""
    return save_data(memory, payload, fields=["state", "embedding_ciphertext", "embedding_artifact"])


def search_memories(user, query, *, semantic=False, allowed_ids=None, context=None):
    query = text(query, "q", 1200, True)
    if context is not None:
        model = {"project": ResearchProject, "plan": PersonalReadingPlan}.get(context.get("kind"))
        if model is None:
            raise ValidationError({"context": "使用范围无效。"})
        scope_record = owned(model, user, context.get("id"))
        authorized = {str(row.id) for row in plan_memory_rows(user, unpack(scope_record))}
        allowed_ids = list(authorized if allowed_ids is None else authorized & set(map(str, allowed_ids)))
    if not allowed_ids:
        return {"results": [], "mode": "disabled", "notice": "尚未明确授权此轮使用任何已确认笔记。"}
    rows = ResearchMemory.objects.filter(user=user, state="confirmed")
    if allowed_ids is not None:
        rows = rows.filter(pk__in=[identifier(value) for value in bounded_list(allowed_ids, "allowed_ids")])

    def current_rows():
        if context is None:
            return rows
        latest_scope = owned(model, user, context.get("id"))
        ids = [row.id for row in plan_memory_rows(user, unpack(latest_scope))]
        return rows.filter(pk__in=ids)
    # ponytail: exact owner-local scan; use a private ANN index only after measured scale warrants it.
    tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", query.casefold()))
    candidates = []
    for memory in rows.iterator(chunk_size=100):
        payload = unpack(memory)
        body = payload.get("body", "")
        words = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", body.casefold()))
        overlap = len(tokens & words) / max(1, len(tokens))
        if overlap:
            candidates.append((overlap, memory))
    mode, warning = "local_lexical", ""
    semantic_scope_count, semantic_evaluated_count, semantic_excluded_count = rows.count(), 0, 0
    if semantic and semantic_scope_count:
        from catalog.services.discovery_inference import DiscoveryInferenceError, embed_texts
        from django.conf import settings
        from .local_analysis import AIServiceError, PrivateLocalTransport
        try:
            with PrivateLocalTransport(getattr(settings, "DISCOVERY_INFERENCE_URL", "http://discovery-inference:8091")) as transport:
                query_embedding = embed_texts([query], kind="query", transport=transport)
                artifact = query_embedding["artifact_id"]
                query_vector = query_embedding["vectors"][0]
                scored, pending = [], []
                # Exact owner-local vector scan, independent of lexical overlap. A visible recent-record cap bounds cold inference.
                for memory in rows.order_by("-updated_at", "id")[:100]:
                    if memory.embedding_artifact != artifact or not memory.embedding_ciphertext:
                        pending.append(memory)
                    else:
                        vector = json.loads(decrypt_private_text(memory.embedding_ciphertext))
                        if (not isinstance(vector, list) or len(vector) != len(query_vector)
                                or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector)):
                            pending.append(memory)
                        else:
                            scored.append((sum(a * b for a, b in zip(query_vector, vector)), memory))
                for offset in range(0, len(pending), 8):
                    batch = pending[offset:offset + 8]
                    fresh = {row.id: row for row in current_rows().filter(pk__in=[row.id for row in batch])}
                    batch = [fresh[row.id] for row in batch if row.id in fresh and fresh[row.id].revision == row.revision]
                    if not batch:
                        continue
                    try:
                        result = embed_texts([unpack(memory)["body"] for memory in batch], expected_artifact=artifact, transport=transport)
                        encoded = list(zip(batch, result["vectors"]))
                    except DiscoveryInferenceError as exc:
                        if exc.code != "input_too_long":
                            raise
                        encoded = []
                        for memory in batch:
                            if not current_rows().filter(pk=memory.id, revision=memory.revision).exists():
                                continue
                            try:
                                result = embed_texts([unpack(memory)["body"]], expected_artifact=artifact, transport=transport)
                                encoded.append((memory, result["vectors"][0]))
                            except DiscoveryInferenceError as individual:
                                if individual.code != "input_too_long":
                                    raise
                                semantic_excluded_count += 1
                    for memory, vector in encoded:
                        ResearchMemory.objects.filter(pk=memory.id, user=user, state="confirmed", revision=memory.revision).update(
                            embedding_ciphertext=pack(vector), embedding_artifact=artifact)
                        scored.append((sum(a * b for a, b in zip(query_vector, vector)), memory))
            candidates, mode = scored, "local_semantic_owner_candidates"
            semantic_evaluated_count = len(scored)
            if semantic_scope_count > 100 or semantic_excluded_count:
                warning = (f"本轮独立比较本人最近 100 条以内已确认记录，实际编码或复用 {len(scored)} 条；"
                    f"{semantic_excluded_count} 条超出模型输入上限，原记录保留且未截断。可用 allowed_ids 缩小范围。")
        except (DiscoveryInferenceError, AIServiceError):
            warning = "本地语义模型不可用，已使用本人范围的文字匹配。"
    # Recheck state/revision after inference so a concurrent forget/rewrite cannot return an old understanding.
    current = {row.id: row for row in current_rows().filter(pk__in=[memory.id for _, memory in candidates])}
    candidates = [(score, current[memory.id]) for score, memory in candidates
                  if memory.id in current and current[memory.id].revision == memory.revision]
    return {"results": [{**serialize_record(memory, user), "match_reason": "与当前问题存在文字或语义联系；不代表观点一致。"}
                         for _, memory in sorted(candidates, key=lambda pair: -pair[0])[:20]],
            "mode": mode, "warning": warning, "semantic_candidate_limit": 100 if semantic else None,
            "semantic_scope_count": semantic_scope_count if semantic else None,
            "semantic_evaluated_count": semantic_evaluated_count if semantic else None,
            "semantic_excluded_count": semantic_excluded_count if semantic else None,
            "semantic_scope_complete": mode == "local_semantic_owner_candidates" and semantic_evaluated_count == semantic_scope_count}


def plan_memory_permissions(user, data, previous=None):
    previous = previous or {}
    enabled = data.get("use_confirmed_memories", previous.get("use_confirmed_memories", False))
    if not isinstance(enabled, bool):
        raise ValidationError({"use_confirmed_memories": "需要布尔值。"})
    ids = list(dict.fromkeys(identifier(value, "confirmed_memory_ids") for value in bounded_list(
        data.get("confirmed_memory_ids", previous.get("confirmed_memory_ids", [])), "confirmed_memory_ids", 40)))
    if enabled and ResearchMemory.objects.filter(user=user, state="confirmed", pk__in=ids).count() != len(ids):
        raise ValidationError({"confirmed_memory_ids": "仅能选择本人仍处于已确认状态的笔记。"})
    return {"use_confirmed_memories": enabled, "confirmed_memory_ids": ids if enabled else []}


def plan_memory_rows(user, payload, *, lock=False):
    """An explicit owner-confirmed allowlist; never search all private memories."""
    if payload.get("use_confirmed_memories") is not True:
        return []
    ids = payload.get("confirmed_memory_ids", [])
    if not isinstance(ids, list) or len(ids) > 40:
        return []
    rows = ResearchMemory.objects.filter(user=user, state="confirmed", pk__in=ids).order_by("id")
    return list(rows.select_for_update() if lock else rows)


def plan_suggestions_current(user, payload, *, lock=False):
    used = payload.get("memory_reminder_ids", [])
    if not used:
        return True
    versions = payload.get("memory_reminder_revisions", {})
    current = {str(row.id): row.revision for row in plan_memory_rows(user, payload, lock=lock)}
    return all(key in current and current[key] == versions.get(key) for key in used)


def invalidate_plan_suggestions(payload, status="skipped_after_edit"):
    for item in payload.get("items", []):
        item.pop("model_suggestion", None)
    payload.pop("enhancement_model", None)
    payload.pop("memory_reminder_ids", None)
    payload.pop("memory_reminder_revisions", None)
    payload["enhancement_status"] = status


def plan_policy_inputs(data, previous=None):
    inputs = {**(previous or {}), **{key: data[key] for key in PLAN_POLICY_FIELDS if key in data}}
    if any(key in data for key in ("weekly_minutes", "duration_weeks")):
        inputs.pop("budget_minutes", None)
        inputs.pop("time_budget", None)
    elif "budget_minutes" in data or "time_budget" in data:
        inputs.pop("weekly_minutes", None)
        inputs.pop("duration_weeks", None)
        # A new human-readable budget must not be shadowed by the old numeric one.
        if "time_budget" in data and "budget_minutes" not in data:
            inputs.pop("budget_minutes", None)
        elif "budget_minutes" in data and "time_budget" not in data:
            inputs.pop("time_budget", None)
    return inputs


@transaction.atomic
def generate_plan(user, data, *, existing=None):
    from .plan_rules import estimate_items, planning_policy, schedule_plan
    request_id = existing.request_id if existing else identifier(data.get("request_id"), "request_id")
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=user.pk)
    if not existing:
        previous = PersonalReadingPlan.objects.filter(user=user, request_id=request_id).first()
        fingerprint = request_fingerprint(data, PLAN_REQUEST_FIELDS)
        if previous:
            return same_request(previous, fingerprint)
    else:
        fingerprint = unpack(existing).get("request_fingerprint")
    previous_payload = unpack(existing) if existing else {}
    planning_inputs = previous_payload.get("planning_inputs", {}) if existing else plan_policy_inputs(data)
    memory_permissions = ({"use_confirmed_memories": previous_payload.get("use_confirmed_memories", False),
        "confirmed_memory_ids": previous_payload.get("confirmed_memory_ids", [])} if existing else plan_memory_permissions(user, data))
    policy = planning_policy(planning_inputs)
    project = source_project(user, data)
    goal = text(data.get("goal", ""), "goal", 4000, True)
    items, origin, seen = [], {}, set()
    if data.get("reading_path_id"):
        raise ValidationError({"reading_path_id": "请在公开路径页使用另存为私人计划，按已确认的公开版本保留阶段、章节与知识条目。"})
    ref_values = data.get("references", [])
    if data.get("turn_id"):
        turn = owned(ResearchTurn, user, data["turn_id"])
        if turn.status in ACTIVE:
            raise ResearchConflict("检索尚在进行，请在材料就绪后生成计划。")
        if project and turn.project_id != project.id:
            raise ValidationError({"turn_id": "轮次不属于当前研究。"})
        project = project or turn.project
        origin["turn_id"] = str(turn.id)
        ref_values = [*ref_values, *unpack(turn).get("result_refs", [])]
    for ref in references(ref_values, user):
        current = resolve_reference(ref, user, strict=True)
        if current["work_id"] in seen:
            continue
        items.append({"id": str(uuid4()), "work_id": current["work_id"], "edition_id": current["edition_id"],
            "asset_id": current["asset_id"], "document_revision_id": current["document_revision_id"],
            "title": current["title"], "stage": "围绕问题阅读", "reason": "包含本次问题选择或检索到的原文。",
            "status": "pending", "estimated_minutes": None, "reference": ref, "reader_url": current["reader_url"]})
        seen.add(current["work_id"])
    if not items:
        raise ValidationError({"sources": "没有当前可读的材料，请先检索、选择原文或选择公开阅读路径。"})
    prerequisites = [dict(row) if isinstance(row, dict) else row for row in bounded_list(data.get("prerequisites", []), "prerequisites", 200)]
    work_ids = {row["work_id"] for row in items}
    for edge in prerequisites:
        if not isinstance(edge, dict) or edge.get("work_id") not in work_ids or edge.get("requires_work_id") not in work_ids:
            raise ValidationError({"prerequisites": "先修关系的两端必须在计划材料中。"})
        if not edge.get("reference"):
            raise ValidationError({"prerequisites": "结构化先修关系必须提供来源；文字说明不会自动变成依赖。"})
        edge["reference"] = compact_reference(resolve_reference(edge["reference"], user, strict=True))
    estimate_items(items, user, policy, overrides=planning_inputs.get("item_estimates", []))
    ordered, schedule = schedule_plan(items, prerequisites, policy)
    payload = {"request_fingerprint": fingerprint, "goal": goal, "background": text(data.get("background", ""), "background", 4000),
        "time_budget": text(planning_inputs.get("time_budget", ""), "time_budget", 160), "origin": origin, **memory_permissions,
        "items": ordered, "prerequisites": prerequisites, "planning_policy": policy, "planning_inputs": planning_inputs,
        "schedule": schedule,
        "method": "public_path_and_selected_discovery_material", "generation_status": "completed", "enhancement_status": "queued",
        "notice": "阅读完成由本人记录，不等于理解或赞同。"}
    if existing is not None:
        with transaction.atomic():
            plan = owned(PersonalReadingPlan, user, existing.id, lock=True)
            previous = unpack(plan)
            if previous.get("generation_status") != "queued" or plan.revision != existing.revision:
                return plan
            plan.project = project
            save_data(plan, payload, fields=["project"])
    else:
        plan = PersonalReadingPlan.objects.create(user=user, request_id=request_id, project=project, task_pending=True, data_ciphertext=pack(payload))
    from .tasks import enqueue_plan_enhancement
    transaction.on_commit(lambda: enqueue_plan_enhancement(plan.id, plan.revision))
    return plan


@transaction.atomic
def request_plan(request, data):
    if data.get("references") or data.get("turn_id") or data.get("reading_path_id"):
        return generate_plan(request.user, data)
    from .plan_rules import planning_policy
    inputs = plan_policy_inputs(data)
    policy = planning_policy(inputs)
    memory_permissions = plan_memory_permissions(request.user, data)
    goal = text(data.get("goal"), "goal", 1200, True)
    request_id = identifier(data.get("request_id"), "request_id")
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    existing_turn = ResearchTurn.objects.filter(project__user=request.user, request_id=request_id).first()
    fingerprint = request_fingerprint(data, PLAN_REQUEST_FIELDS)
    if existing_turn:
        existing_payload = unpack(existing_turn)
        if existing_payload.get("question") != goal or not existing_payload.get("plan_id"):
            raise ResearchConflict("该请求标识已用于另一任务。")
        return same_request(owned(PersonalReadingPlan, request.user, existing_payload["plan_id"]), fingerprint)
    project = source_project(request.user, data) or create_project(request.user, {"request_id": request_id, "title": goal[:240], "question": goal})
    turn = start_turn(request, project.id, {"request_id": data.get("request_id"), "expected_revision": project.revision,
        "question": goal, "scope": data.get("scope", {"kind": "library"})})
    payload = unpack(turn)
    if payload.get("plan_id"):
        return owned(PersonalReadingPlan, request.user, payload["plan_id"])
    plan = PersonalReadingPlan.objects.create(user=request.user, request_id=request_id, project=project, task_pending=True, data_ciphertext=pack({
        "request_fingerprint": fingerprint, "goal": goal, "background": text(data.get("background", ""), "background", 4000),
        "time_budget": text(data.get("time_budget", ""), "time_budget", 160), "items": [],
        "prerequisites": data.get("prerequisites", []),
        "planning_policy": policy, "planning_inputs": inputs, **memory_permissions,
        "origin": {"turn_id": str(turn.id)}, "generation_status": "queued"}))
    payload["plan_id"] = str(plan.id)
    save_data(turn, payload)
    return plan


@transaction.atomic
def update_plan(user, pk, data):
    current = owned(PersonalReadingPlan, user, pk)
    if current.public_path_id is not None:
        raise ValidationError("公共路径跟读使用专用进度接口，不是私人计划副本。")
    if unpack(current).get("origin", {}).get("type") == "public_path_copy":
        from .path_plans import update_copy
        return update_copy(user, pk, data)
    plan = owned(PersonalReadingPlan, user, pk, lock=True)
    expect(plan, data.get("expected_revision"))
    for flag in ("optimize_order", "preview", "adopt_suggestion", "remove_related_prerequisites"):
        if flag in data and not isinstance(data[flag], bool):
            raise ValidationError({flag: "需要布尔值。"})
    payload = unpack(plan)
    if payload.get("generation_status") in ACTIVE:
        raise ResearchConflict("计划正在收集材料，暂不能修改。")
    if not plan_suggestions_current(user, payload):
        invalidate_plan_suggestions(payload, "authorization_changed")
    if payload.get("enhancement_status") in ACTIVE or any(key in data for key in (
            "goal", "background", *PLAN_POLICY_FIELDS, *PLAN_MEMORY_FIELDS, "reference")):
        invalidate_plan_suggestions(payload)
    for field in ("goal", "background"):
        if field in data:
            payload[field] = text(data[field], field, 4000, field == "goal")
    if any(key in data for key in PLAN_MEMORY_FIELDS):
        payload.update(plan_memory_permissions(user, data, payload))
    by_id = {row["id"]: row for row in payload["items"]}
    if "order" in data:
        order = bounded_list(data["order"], "order")
        if len(order) != len(by_id) or set(order) != set(by_id):
            raise ValidationError({"order": "必须恰好包含全部计划项，每项一次。"})
        if any(row.get("status") == "completed" and order[index] != row["id"] for index, row in enumerate(payload["items"])):
            raise ResearchConflict("已完成的计划项保留原位置，请仅调整未完成材料。")
        positions = {by_id[key]["work_id"]: index for index, key in enumerate(order)}
        completed_work_ids = {row["work_id"] for row in by_id.values() if row.get("status") == "completed"}
        if any(positions[edge["requires_work_id"]] > positions[edge["work_id"]]
                for edge in payload.get("prerequisites", [])
                if edge["requires_work_id"] not in completed_work_ids and edge["work_id"] not in completed_work_ids):
            raise ValidationError({"order": "此顺序违反已确认先修关系，请先修改依赖。"})
        payload["items"] = [by_id[key] for key in order]
    if "item_id" in data:
        item = by_id.get(data["item_id"])
        if item is None:
            raise NotFound("计划项不存在。")
        if item.get("status") == "completed" and ("reference" in data or data.get("adopt_suggestion") is True
                or ("status" in data and data["status"] != "completed")):
            raise ResearchConflict("已完成的计划项保留历史；可补充笔记，请仅调整未完成材料。")
        if "status" in data:
            if data["status"] not in {"pending", "reading", "completed", "skipped"}:
                raise ValidationError({"status": "阅读进度无效。"})
            item["status"] = data["status"]
        if "note" in data:
            item["note"] = text(data["note"], "note", 4000)
        if data.get("adopt_suggestion") is True:
            if not item.get("model_suggestion"):
                raise ResearchConflict("建议已失效或尚未生成，请重新生成导读后再采纳。")
            if item.get("reference"):
                resolve_reference(item["reference"], user, strict=True)
            elif not source_queryset("edition", access_for(user)).filter(pk=item["edition_id"],
                    active_catalog_revision__reader_asset_id=item.get("asset_id"),
                    active_catalog_revision__document_revision_id=item.get("document_revision_id")).exists():
                raise ResearchConflict("材料当前不可用，不能采纳旧导读建议。")
            suggestion = item["model_suggestion"]
            item.update(stage=suggestion["stage"], reason=suggestion["reason"], learning_goal=suggestion["learning_goal"])
            item["suggestion_adopted_at"] = timezone.now().isoformat()
        if "reference" in data:
            if item["status"] == "completed":
                raise ResearchConflict("已完成的计划项保留历史，请新增计划后再替换。")
            ref = resolve_reference(data["reference"], user, strict=True)
            if any(row["id"] != item["id"] and row["work_id"] == ref["work_id"] for row in payload["items"]):
                raise ValidationError({"reference": "该作品已在本计划中，请调整已有计划项。"})
            old_work_id = item["work_id"]
            related = [edge for edge in payload.get("prerequisites", []) if old_work_id in (edge["work_id"], edge["requires_work_id"])]
            if related and data.get("remove_related_prerequisites") is not True:
                raise ResearchConflict("此材料有关联先修关系。替换前请明确确认移除这些关系，不会把旧依据套用到新材料。")
            if related:
                payload["prerequisites"] = [edge for edge in payload["prerequisites"] if edge not in related]
                item["replaced_prerequisites"] = related
            item["replaced_from"] = {key: item.get(key) for key in ("work_id", "edition_id", "asset_id", "document_revision_id", "reference")}
            for field in ("owner_estimate", "declared_difficulty", "difficulty_origin", "planning_estimate",
                    "model_suggestion", "learning_goal", "suggestion_adopted_at"):
                item.pop(field, None)
            if "planning_inputs" in payload:
                payload["planning_inputs"]["item_estimates"] = [row for row in payload["planning_inputs"].get("item_estimates", []) if row.get("work_id") != old_work_id]
            item.update(reference=compact_reference(ref), work_id=ref["work_id"], edition_id=ref["edition_id"],
                        asset_id=ref["asset_id"], document_revision_id=ref["document_revision_id"],
                        title=ref["title"], reader_url=ref["reader_url"], status="pending", reason="本人替换的阅读材料。")
    if (not payload.get("planning_policy") or any(key in data for key in (*PLAN_POLICY_FIELDS, "order", "status", "reference", "optimize_order"))):
        from .plan_rules import estimate_items, planning_policy, schedule_plan
        inputs = plan_policy_inputs(data, payload.get("planning_inputs"))
        policy = planning_policy(inputs)
        estimate_items(payload["items"], user, policy, overrides=inputs.get("item_estimates", []))
        payload["items"], payload["schedule"] = schedule_plan(payload["items"], payload.get("prerequisites", []), policy,
            preserve_order=data.get("optimize_order") is not True)
        payload.update(planning_inputs=inputs, planning_policy=policy, time_budget=inputs.get("time_budget", ""))
    if data.get("preview") is True:
        plan.data_ciphertext = pack(payload)
        return plan
    return save_data(plan, payload)


@transaction.atomic
def command_plan(request, pk, data):
    """Restart a failed private task on the same plan, preserving independently recorded progress."""
    # Match generate_plan's user -> project/turn -> plan lock ordering.
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    plan = owned(PersonalReadingPlan, request.user, pk)
    expect(plan, data.get("expected_revision"))
    payload = unpack(plan)
    action = data.get("action")
    if payload.get("origin", {}).get("type") in {"path_follow", "public_path_copy"}:
        raise ValidationError("公共路径及其副本按正式阶段保存，不执行自动生成或模型导读任务。")
    source_turn = None
    if payload.get("origin", {}).get("turn_id"):
        source_turn = ResearchTurn.objects.filter(pk=payload["origin"]["turn_id"], project__user=request.user).first()
    project = owned(ResearchProject, request.user, source_turn.project_id, lock=True) if source_turn else None
    if action == "cancel" and source_turn and source_turn.status in ACTIVE:
        cancel_turn(request.user, source_turn.id)
    plan = owned(PersonalReadingPlan, request.user, pk, lock=True)
    expect(plan, data.get("expected_revision"))
    if (payload.get("generation_status") in ACTIVE and (source_turn is None
            or source_turn.status in {"failed", "canceled"}
            or timezone.now() - plan.updated_at > timedelta(minutes=35))):
        payload.update(generation_status="failed", error_code="source_research_incomplete")
    if action == "cancel":
        if payload.get("generation_status") in ACTIVE:
            payload["generation_status"] = "canceled"
        if payload.get("enhancement_status") in ACTIVE | {"queue_unavailable"}:
            payload["enhancement_status"] = "canceled"
        return save_data(plan, payload)
    if action == "enhance":
        if payload.get("generation_status") != "completed" or not payload.get("items"):
            raise ResearchConflict("请先收集可读材料并完成计划。")
        if payload.get("enhancement_status") in ACTIVE:
            raise ResearchConflict("计划建议正在处理中。")
        invalidate_plan_suggestions(payload, "queued")
        payload["recovery_attempts"] = 0
        save_data(plan, payload)
        from .tasks import enqueue_plan_enhancement
        transaction.on_commit(lambda: enqueue_plan_enhancement(plan.id, plan.revision))
        return plan
    if action != "retry":
        raise ValidationError({"action": "支持 cancel/retry/enhance。"})
    if payload.get("generation_status") in ACTIVE:
        raise ResearchConflict("计划仍在收集材料，请等待或先取消。")
    if payload.get("items"):
        raise ResearchConflict("已有计划材料会保留；如需重新生成导读，请使用 enhance。")
    if source_turn is None:
        raise ResearchConflict("原研究已删除，请从当前材料创建新计划。")
    previous = unpack(source_turn)
    goal = text(payload.get("goal", previous["question"]), "goal", 1200, True)
    turn = start_turn(request, project.id, {"request_id": str(uuid4()), "expected_revision": project.revision,
        "parent_id": str(source_turn.id), "question": goal, "scope": previous["scope"],
        "mode": "search", "statement": {"proposition": goal},
        "expand_from_parent": True})
    turn_data = unpack(turn)
    turn_data["plan_id"] = str(plan.id)
    save_data(turn, turn_data)
    payload.update(origin={"turn_id": str(turn.id)}, generation_status="queued", error_code="", recovery_attempts=0)
    return save_data(plan, payload)


@transaction.atomic
def delete_project(user, pk, expected_revision):
    from .privacy import lock_owner
    lock_owner(user)
    project = owned(ResearchProject, user, pk, lock=True)
    expect(project, expected_revision)
    payload = unpack(project)
    if payload.get("import_origin", {}).get("kind") == "guest_transfer":
        ResearchImportReceipt.objects.get_or_create(user=user, request_id=project.request_id,
            defaults={"project": project, "fingerprint": payload.get("request_fingerprint", "")})
    for turn in project.turns.filter(status__in=ACTIVE):
        cancel_turn(user, turn.id)
    from catalog.discovery_models import DiscoverySearchSession
    # Remove only ephemeral searches owned by this project; other reader searches remain intact.
    session_ids = list(project.turns.exclude(discovery_session_id=None).values_list("discovery_session_id", flat=True))
    DiscoverySearchSession.objects.filter(pk__in=session_ids, owner=user).delete()
    # Memory, plan and manuscript are independently owned. SET_NULL preserves them.
    project.delete()


def research_export(user):
    from .models import CitationAudit
    return {"schema_version": 1, "research": [serialize_record(row, user) for row in ResearchProject.objects.filter(user=user)],
        "turns": [serialize_record(row, user) for row in ResearchTurn.objects.filter(project__user=user)],
        "plans": [serialize_record(row, user) for row in PersonalReadingPlan.objects.filter(user=user)],
        "memories": [serialize_record(row, user) for row in ResearchMemory.objects.filter(user=user)],
        "audits": [serialize_record(row, user) for row in CitationAudit.objects.filter(user=user, purpose="manuscript")],
        "citation_sources": [serialize_record(row, user) for row in CitationAudit.objects.filter(user=user, purpose="private_source")],
        "notice": "不包含 PDF 原件或向量；删除不立即移除受既有保留期管理的备份。"}
