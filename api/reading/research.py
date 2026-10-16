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
from rest_framework.exceptions import APIException, NotFound, ValidationError

from catalog.models import EvidenceSpan, Page
from catalog.services.discovery_sources import source_queryset
from catalog.services.discovery_sessions import normalize_filters, request_access

from .models import (Annotation, LibraryConversation, PersonalReadingPlan, ResearchMemory,
                     ResearchProject, ResearchTurn)
from .services import decrypt_private_text, encrypt_private_text

ACTIVE = {"queued", "running"}
ANALYSIS_VERSION = "private-claims-v1"
MAX_REFS = 400
PLAN_REQUEST_FIELDS = ("goal", "background", "time_budget", "project_id", "turn_id", "reading_path_id", "references",
    "prerequisites", "scope", "budget_minutes", "session_minutes", "reading_level", "reading_pace", "prefer_unread", "item_estimates")
PLAN_POLICY_FIELDS = ("time_budget", "budget_minutes", "session_minutes", "reading_level", "reading_pace", "prefer_unread", "item_estimates")


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
                "title": first.get("title", ""), "reader_url": first.get("reader_url") if available else None}
    span_id = raw.get("evidence_span_id")
    stale = {"schema_version": 1, "source_kind": "catalog", "source_status": "unavailable",
             "reference_id": reference_identity(raw),
             **{key: raw[key] for key in ("evidence_span_id", "document_revision_id", "asset_id", "pdf_page", "content_hash",
                                         "work_id", "edition_id") if key in raw}}
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
    snapshot = edition.active_catalog_revision.snapshot or {}
    from catalog.services.page_geometry import locator_geometry, validated_geometry
    from catalog.services.text import page_text_range
    geometry = validated_geometry((span.ocr_provenance or {}).get("geometry") if span else page.geometry)
    from catalog.services.citations import format_gbt_7714_2025
    authors = [str((item.get("person") or {}).get("preferred_name") or item.get("name") or "")
               for item in snapshot.get("contributions", []) if isinstance(item, dict) and item.get("role") == "author"]
    return {"schema_version": 1, "source_kind": "catalog", "source_status": "available",
            "reference_id": str(span.id) if span else f"{asset_id}:{page_number}",
            "evidence_span_id": str(span.id) if span else None,
            "work_id": str(edition.work_id), "edition_id": str(edition.id), "asset_id": asset_id,
            "document_revision_id": revision_id, "pdf_page": page_number,
            "printed_label": span.printed_page_label if span else page.printed_label,
            "content_hash": digest, "title": (snapshot.get("work") or {}).get("title", ""),
            "authors": [value for value in authors if value],
            "citation": format_gbt_7714_2025(edition, page.printed_label, snapshot=snapshot),
            "quote": span.original_text if span else page.text,
            "start_offset": span.start_offset if span else 0, "end_offset": span.end_offset if span else len(page.text),
            "page_text_range": page_text_range(page.text, span.original_text if span else page.text,
                span.start_offset if span else 0, span.end_offset if span else len(page.text)),
            "bbox": span.bbox if span else [], "bbox_unit": "source_page_coordinates",
            "geometry": geometry, **locator_geometry(span.bbox if span else [], geometry),
            "coordinate_space": {"width": page.width, "height": page.height, "text_source": page.text_source,
                "rotation": None, "crop_box": None, "requires_reader_transform": True},
            "locator_precision": "span" if span else "page",
            "reader_url": f"/reader/{asset_id}?page={page_number}" + (f"&passage={span.passage_id or span.id}" if span else "")}


def reference_identity(reference):
    if reference.get("anchors"):
        return "anchors:" + hashlib.sha256("|".join(reference_identity(row) for row in reference["anchors"]).encode()).hexdigest()
    return str(reference.get("evidence_span_id") or f"{reference.get('asset_id')}:{reference.get('pdf_page')}")


def compact_reference(reference):
    # Identity only: future reads must rehydrate rather than leak cached withdrawn text.
    output = {key: reference[key] for key in ("schema_version", "source_kind", "evidence_span_id", "work_id",
            "edition_id", "asset_id", "document_revision_id", "pdf_page", "content_hash") if key in reference}
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
               "removed_selections": [], "comparison": {"dimensions": [], "cells": []}, "notes": "", "layout": {}}
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
    existing = ResearchProject.objects.filter(user=user, request_id=request_id).first()
    if existing:
        return same_request(existing, fingerprint)
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
    return save_data(project, payload)


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
    project = owned(ResearchProject, user, pk, lock=True)
    expect(project, data.get("expected_revision"))
    payload = unpack(project)
    selected = payload.setdefault("selections", [])
    action = data.get("action")
    if action == "add":
        new_refs = references(data.get("references", []), user)
        seen = {reference_identity(row) for row in selected}
        selected.extend(row for row in new_refs if reference_identity(row) not in seen)
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
            previous = removed.pop()
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
        raise ValidationError({"action": "支持 add/remove/undo/reorder。"})
    return save_data(project, payload)


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
    turn = ResearchTurn.objects.create(project=project, parent=parent, request_id=request_id,
        task_id=str(uuid4()), data_ciphertext=pack({"request_fingerprint": fingerprint, "question": question, "scope": scope, "mode": mode,
        "statement": statement, "subclaims": subclaims, "active_subclaim_id": active_subclaim_id,
        "search_question": statement["proposition"] if active_subclaim_id else question,
        "analysis_statement": statement, "input_revision": project.revision, "selected_refs": payload.get("selections", []),
        "result_refs": unpack(parent).get("result_refs", []) if parent and data.get("expand_from_parent") is True else [],
        "analysis": [], "warnings": [], "parent_id": str(parent.id) if parent else None,
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
    turn = owned(ResearchTurn, user, pk, lock=True)
    expect(turn, data.get("expected_revision"))
    if turn.status in ACTIVE:
        raise ResearchConflict("请等待本轮结束后确认，已得到的材料会保留。")
    payload = unpack(turn)
    relation = data.get("relation")
    if relation not in {"support", "different_conclusion", "qualification", "reframe", "insufficient_evidence"}:
        raise ValidationError({"relation": "关系类型无效。"})
    row = next((row for row in payload.get("analysis", []) if row["id"] == data.get("id")), None)
    if row is None:
        raise NotFound("分析候选不存在。")
    resolve_reference(row["reference"], user, strict=True)
    row.update(relation=relation, status="user_confirmed", decision={"by": "owner", "at": timezone.now().isoformat(),
        "note": text(data.get("note", ""), "note", 4000)})
    return save_data(turn, payload)


def serialize_record(record, user):
    if hasattr(record, "status") and record.status in ACTIVE and timezone.now() - record.updated_at > timedelta(minutes=30):
        type(record).objects.filter(pk=record.id, generation=record.generation, status__in=ACTIVE,
            updated_at__lt=timezone.now() - timedelta(minutes=30)).update(
            status="failed", error_code="task_timeout", finished_at=timezone.now())
        record.refresh_from_db()
    payload = unpack(record)
    payload.pop("source_paragraphs", None)
    if "ocr_units" in payload:
        payload["ocr_units"] = {key: {name: value for name, value in unit.items() if name not in {"text", "blocks"}}
                                for key, unit in payload["ocr_units"].items()}
    for key in ("selections", "result_refs", "selected_refs", "sources"):
        if key in payload:
            payload[key] = [resolve_reference(ref, user) for ref in payload[key]]
    if "comparison" in payload:
        available = {reference_identity(ref) for ref in payload.get("selections", [])
                     if ref["source_status"] == "available"}
        for cell in payload["comparison"].get("cells", []):
            ids = set(cell.get("reference_ids", []))
            readable = ids & available
            # A saved judgment survives removal or withdrawal; its evidence status does not.
            cell["evidence_status"] = ("missing" if not ids else "selected" if readable == ids
                                       else "partial" if readable else "unavailable")
    if "scope" in payload:
        payload["scope"] = {**payload["scope"], "references": [resolve_reference(ref, user) for ref in payload["scope"].get("references", [])]}
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
    if isinstance(record, ResearchTurn):
        output.update(project_id=str(record.project_id), parent_id=str(record.parent_id) if record.parent_id else None,
                      discovery_session_id=str(record.discovery_session_id) if record.discovery_session_id else None)
    elif hasattr(record, "project_id"):
        output["project_id"] = str(record.project_id) if record.project_id else None
    if isinstance(record, ResearchProject):
        output["conversation_id"] = str(record.conversation_id) if record.conversation_id else None
    if isinstance(record, PersonalReadingPlan):
        if payload.get("generation_status") == "queued":
            source_turn = ResearchTurn.objects.filter(pk=payload.get("origin", {}).get("turn_id"), project__user=user).first()
            if (source_turn is None or source_turn.status in {"failed", "canceled"}
                    or timezone.now() - record.updated_at > timedelta(minutes=35)):
                payload["generation_status"] = "failed"
                payload["error_code"] = "source_research_incomplete"
        for item in payload.get("items", []):
            if item.get("reference"):
                item["reference"] = resolve_reference(item["reference"], user)
                item["available"] = item["reference"]["source_status"] == "available"
            else:
                item["available"] = source_queryset("edition", access_for(user)).filter(pk=item["edition_id"],
                    active_catalog_revision__reader_asset_id=item.get("asset_id"),
                    active_catalog_revision__document_revision_id=item.get("document_revision_id")).exists()
            if not item["available"]:
                item["reader_url"] = None
        output["status"] = payload.get("generation_status", "completed")
        output["poll_after_ms"] = 2000 if output["status"] in ACTIVE else None
        output["enhancement_status"] = payload.get("enhancement_status", "not_requested")
        if output["enhancement_status"] in ACTIVE:
            output["poll_after_ms"] = 2000
            if timezone.now() - record.updated_at > timedelta(minutes=10):
                payload["enhancement_status"] = "unavailable"
                output.update(enhancement_status="unavailable", poll_after_ms=None)
    if isinstance(record, ResearchMemory):
        for snapshot in payload.get("history", []):
            snapshot["data"]["sources"] = [resolve_reference(ref, user) for ref in snapshot["data"].get("sources", [])]
    if hasattr(record, "content_hash"):
        occurrences = [*payload.get("occurrences", []), *(row for report in payload.get("parse_history", []) for row in report.get("occurrences", []))]
        for occurrence in occurrences:
            for version in [occurrence, *occurrence.get("history", [])]:
                for finding in version.get("findings", []):
                    if "references" in finding:
                        finding["references"] = [resolve_reference(ref, user) for ref in finding["references"]]
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


@transaction.atomic
def create_memory(user, data):
    request_id = identifier(data.get("request_id"), "request_id")
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=user.pk)
    existing = ResearchMemory.objects.filter(user=user, request_id=request_id).first()
    fingerprint = request_fingerprint(data, ("body", "kind", "project_id", "turn_id", "annotation_id", "sources"))
    if existing:
        return same_request(existing, fingerprint)
    project = source_project(user, data)
    kind = data.get("kind", "understanding")
    if kind not in {"understanding", "question", "contradiction"}:
        raise ValidationError({"kind": "认识类型无效。"})
    body = text(data.get("body", ""), "body", 20000, True)
    sources = references(data.get("sources", []), user)
    origin = {}
    if data.get("annotation_id"):
        note = Annotation.objects.filter(pk=identifier(data["annotation_id"]), user=user).first()
        if note is None:
            raise NotFound("笔记不存在。")
        origin["annotation_id"] = str(note.id)
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
    memory = owned(ResearchMemory, user, pk, lock=True)
    expect(memory, data.get("expected_revision"))
    payload = unpack(memory)
    state = data.get("state", memory.state)
    if state not in {"proposed", "confirmed", "ignored"}:
        raise ValidationError({"state": "状态无效；遗忘请使用删除操作。"})
    old = {key: payload[key] for key in ("body", "kind", "sources")}
    if "body" in data:
        payload["body"] = text(data["body"], "body", 20000, True)
    if "sources" in data:
        payload["sources"] = references(data["sources"], user)
    payload["history"].append({"revision": memory.revision, "at": timezone.now().isoformat(), "data": old})
    memory.state, memory.embedding_ciphertext, memory.embedding_artifact = state, b"", ""
    return save_data(memory, payload, fields=["state", "embedding_ciphertext", "embedding_artifact"])


def search_memories(user, query, *, semantic=False, allowed_ids=None):
    query = text(query, "q", 1200, True)
    preference = getattr(getattr(user, "reader_profile", None), "reading_preferences", {}) or {}
    if preference.get("research_personalization", True) is False:
        return {"results": [], "mode": "disabled", "notice": "已关闭私人记忆提醒。"}
    rows = ResearchMemory.objects.filter(user=user, state="confirmed")
    if allowed_ids is not None:
        rows = rows.filter(pk__in=[identifier(value) for value in bounded_list(allowed_ids, "allowed_ids")])
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
                    try:
                        result = embed_texts([unpack(memory)["body"] for memory in batch], expected_artifact=artifact, transport=transport)
                        encoded = list(zip(batch, result["vectors"]))
                    except DiscoveryInferenceError as exc:
                        if exc.code != "input_too_long":
                            raise
                        encoded = []
                        for memory in batch:
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
    current = {row.id: row for row in rows.filter(pk__in=[memory.id for _, memory in candidates])}
    candidates = [(score, current[memory.id]) for score, memory in candidates
                  if memory.id in current and current[memory.id].revision == memory.revision]
    return {"results": [{**serialize_record(memory, user), "match_reason": "与当前问题存在文字或语义联系；不代表观点一致。"}
                         for _, memory in sorted(candidates, key=lambda pair: -pair[0])[:20]],
            "mode": mode, "warning": warning, "semantic_candidate_limit": 100 if semantic else None,
            "semantic_scope_count": semantic_scope_count if semantic else None,
            "semantic_evaluated_count": semantic_evaluated_count if semantic else None,
            "semantic_excluded_count": semantic_excluded_count if semantic else None,
            "semantic_scope_complete": mode == "local_semantic_owner_candidates" and semantic_evaluated_count == semantic_scope_count}


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
    planning_inputs = {**(unpack(existing).get("planning_inputs", {}) if existing else {}),
                       **{key: data[key] for key in PLAN_POLICY_FIELDS if key in data}}
    policy = planning_policy(planning_inputs)
    project = source_project(user, data)
    goal = text(data.get("goal", ""), "goal", 4000, True)
    items, origin, seen = [], {}, set()
    if data.get("reading_path_id"):
        path = source_queryset("reading_path").filter(pk=identifier(data["reading_path_id"])).first()
        if path is None:
            raise NotFound("公开阅读路径不存在。")
        origin = {"reading_path_id": str(path.id), "revision_at": path.updated_at.isoformat()}
        for row in path.items.select_related("work", "stage").all():
            if not row.work_id or str(row.work_id) in seen:
                continue
            edition = source_queryset("edition", access_for(user)).filter(work_id=row.work_id).first()
            if not edition:
                continue
            snapshot = edition.active_catalog_revision.snapshot or {}
            items.append({"id": str(uuid4()), "work_id": str(row.work_id), "edition_id": str(edition.id),
                "asset_id": str(edition.active_catalog_revision.reader_asset_id),
                "document_revision_id": str(edition.active_catalog_revision.document_revision_id),
                "title": (snapshot.get("work") or {}).get("title", ""), "stage": row.stage.name if row.stage else row.stage_name,
                "declared_difficulty": path.difficulty, "difficulty_origin": {"reading_path_id": str(path.id), "revision_at": path.updated_at.isoformat()},
                "reason": row.recommendation_reason, "prerequisite_text": row.prerequisite,
                "status": "pending", "estimated_minutes": None, "reference": None,
                "reader_url": f"/reader/{edition.active_catalog_revision.reader_asset_id}?page=1"})
            seen.add(str(row.work_id))
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
        "time_budget": text(data.get("time_budget", ""), "time_budget", 160), "origin": origin,
        "items": ordered, "prerequisites": prerequisites, "planning_policy": policy, "planning_inputs": planning_inputs,
        "schedule": schedule,
        "method": "public_path_and_selected_discovery_material", "generation_status": "completed", "enhancement_status": "queued",
        "notice": "阅读完成由本人记录，不等于理解或赞同。"}
    if existing is not None:
        with transaction.atomic():
            plan = owned(PersonalReadingPlan, user, existing.id, lock=True)
            previous = unpack(plan)
            if previous.get("generation_status") != "queued":
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
    policy = planning_policy(data)
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
        "planning_policy": policy, "planning_inputs": {key: data[key] for key in PLAN_POLICY_FIELDS if key in data},
        "origin": {"turn_id": str(turn.id)}, "generation_status": "queued"}))
    payload["plan_id"] = str(plan.id)
    save_data(turn, payload)
    return plan


@transaction.atomic
def update_plan(user, pk, data):
    plan = owned(PersonalReadingPlan, user, pk, lock=True)
    expect(plan, data.get("expected_revision"))
    if "optimize_order" in data and not isinstance(data["optimize_order"], bool):
        raise ValidationError({"optimize_order": "需要布尔值。"})
    payload = unpack(plan)
    if payload.get("generation_status") in ACTIVE:
        raise ResearchConflict("计划正在收集材料，暂不能修改。")
    if payload.get("enhancement_status") in ACTIVE:
        payload["enhancement_status"] = "skipped_after_edit"
    by_id = {row["id"]: row for row in payload["items"]}
    if "order" in data:
        order = bounded_list(data["order"], "order")
        if len(order) != len(by_id) or set(order) != set(by_id):
            raise ValidationError({"order": "必须恰好包含全部计划项，每项一次。"})
        positions = {by_id[key]["work_id"]: index for index, key in enumerate(order)}
        if any(positions[edge["requires_work_id"]] > positions[edge["work_id"]] for edge in payload.get("prerequisites", [])):
            raise ValidationError({"order": "此顺序违反已确认先修关系，请先修改依赖。"})
        payload["items"] = [by_id[key] for key in order]
    if "item_id" in data:
        item = by_id.get(data["item_id"])
        if item is None:
            raise NotFound("计划项不存在。")
        if "status" in data:
            if data["status"] not in {"pending", "reading", "completed", "skipped"}:
                raise ValidationError({"status": "阅读进度无效。"})
            item["status"] = data["status"]
        if "note" in data:
            item["note"] = text(data["note"], "note", 4000)
        if data.get("adopt_suggestion") is True and item.get("model_suggestion"):
            suggestion = item["model_suggestion"]
            item.update(stage=suggestion["stage"], reason=suggestion["reason"], learning_goal=suggestion["learning_goal"])
            item["suggestion_adopted_at"] = timezone.now().isoformat()
        if "reference" in data:
            if item["status"] == "completed":
                raise ResearchConflict("已完成的计划项保留历史，请新增计划后再替换。")
            ref = resolve_reference(data["reference"], user, strict=True)
            if any(row["id"] != item["id"] and row["work_id"] == ref["work_id"] for row in payload["items"]):
                raise ValidationError({"reference": "该作品已在本计划中，请调整已有计划项。"})
            if payload.get("prerequisites"):
                raise ResearchConflict("有关联先修关系时不能直接替换材料，请重新生成计划。")
            old_work_id = item["work_id"]
            item["replaced_from"] = {key: item.get(key) for key in ("work_id", "edition_id", "asset_id", "document_revision_id", "reference")}
            for field in ("owner_estimate", "declared_difficulty", "difficulty_origin", "planning_estimate"):
                item.pop(field, None)
            if "planning_inputs" in payload:
                payload["planning_inputs"]["item_estimates"] = [row for row in payload["planning_inputs"].get("item_estimates", []) if row.get("work_id") != old_work_id]
            item.update(reference=compact_reference(ref), work_id=ref["work_id"], edition_id=ref["edition_id"],
                        asset_id=ref["asset_id"], document_revision_id=ref["document_revision_id"],
                        title=ref["title"], reader_url=ref["reader_url"])
    if (not payload.get("planning_policy") or any(key in data for key in (*PLAN_POLICY_FIELDS, "order", "status", "reference", "optimize_order"))):
        from .plan_rules import estimate_items, planning_policy, schedule_plan
        inputs = {**payload.get("planning_inputs", {}), **{key: data[key] for key in PLAN_POLICY_FIELDS if key in data}}
        policy = planning_policy(inputs)
        estimate_items(payload["items"], user, policy, overrides=inputs.get("item_estimates", []))
        payload["items"], payload["schedule"] = schedule_plan(payload["items"], payload.get("prerequisites", []), policy,
            preserve_order=data.get("optimize_order") is not True)
        payload.update(planning_inputs=inputs, planning_policy=policy, time_budget=inputs.get("time_budget", payload.get("time_budget", "")))
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
        payload["enhancement_status"] = "queued"
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
    turn = start_turn(request, project.id, {"request_id": str(uuid4()), "expected_revision": project.revision,
        "parent_id": str(source_turn.id), "question": previous["question"], "scope": previous["scope"],
        "mode": previous.get("mode", "search"), "statement": previous.get("statement", {"proposition": previous["question"]}),
        "expand_from_parent": True})
    turn_data = unpack(turn)
    turn_data["plan_id"] = str(plan.id)
    save_data(turn, turn_data)
    payload.update(origin={"turn_id": str(turn.id)}, generation_status="queued", error_code="", recovery_attempts=0)
    return save_data(plan, payload)


@transaction.atomic
def delete_project(user, pk, expected_revision):
    project = owned(ResearchProject, user, pk, lock=True)
    expect(project, expected_revision)
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
        "audits": [serialize_record(row, user) for row in CitationAudit.objects.filter(user=user)],
        "notice": "不包含 PDF 原件或向量；删除不立即移除受既有保留期管理的备份。"}
