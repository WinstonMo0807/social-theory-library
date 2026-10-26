"""Review page labels without changing a served document interpretation."""
from copy import deepcopy
from hashlib import sha256
import json

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalog.models import (
    Asset, DocumentOutlineRevision, Edition, KnowledgePublicationEvent, Page, PageLabelSegment,
    PageLabelStatus, PageMappingRevision, PublicationState,
)
from catalog.services.document_outline import OutlineConflict, _source_current, outline_state
from catalog.services.page_labels import _format_label, _page_label_candidate, _parse_label


class MappingConflict(ValueError):
    pass


def _hash(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _pages(asset):
    return list(asset.pages.order_by("index"))


def source_fingerprint(asset, pages=None):
    pages = _pages(asset) if pages is None else pages
    document = asset.document_revisions.filter(is_active=True).first()
    return _hash({
        "asset": asset.pk, "sha256": asset.sha256, "updated_at": asset.updated_at,
        "current": asset.is_current, "page_count": asset.page_count, "publication_state": asset.edition.state,
        "document": document.pk if document else None,
        "text_checksum": document.text_checksum if document else None,
        "catalog": asset.edition.catalog_revisions.order_by("-revision").values_list("id", flat=True).first(),
        "pages": [(p.index, p.printed_label, p.is_label_manual, p.is_label_anchor, p.label_segment, p.label_source) for p in pages],
    })


def current_data(asset, pages=None):
    pages = _pages(asset) if pages is None else pages
    details = (asset.validation_details or {}).get("page_mapping") or {}
    prior = {row["pdf_page"]: row for row in details.get("pages", [])}
    legacy_segments = list(asset.page_label_segments.order_by("start_file_page_index"))
    return {
        "pages": [{
            "pdf_page": p.index,
            "labels": deepcopy(prior[p.index]["labels"]) if p.index in prior and "–".join(prior[p.index]["labels"]) == p.printed_label else ([p.printed_label] if p.printed_label else []),
            "page_type": prior.get(p.index, {}).get("page_type", "body"),
            "confirmed": bool(p.is_label_manual or prior.get(p.index, {}).get("confirmed")),
            "note": prior.get(p.index, {}).get("note", ""),
            "source_note": prior.get(p.index, {}).get("source_note", ""),
            "override_manual": False,
            "source": p.label_source, "confidence": p.label_confidence,
        } for p in pages],
        "segments": deepcopy(details.get("segments")) if "segments" in details else [{
            "id": str(s.pk), "name": "页码段", "start": s.start_file_page_index,
            "end": s.end_file_page_index or (legacy_segments[i + 1].start_file_page_index - 1 if i + 1 < len(legacy_segments) else pages[-1].index if pages else 0),
            "start_label": s.start_label, "style": s.style,
        } for i, s in enumerate(legacy_segments)],
        "missing": deepcopy(details.get("missing", [])),
    }


def validate_data(asset, data, pages=None):
    """Existing physical pages stay fixed; blank requests apply only to a separate copy."""
    pages = _pages(asset) if pages is None else pages
    actual = {p.index: p for p in pages}
    rows, segments, missing = deepcopy(data.get("pages", [])), deepcopy(data.get("segments", [])), deepcopy(data.get("missing", []))
    if not actual or len(actual) > 20000 or len(rows) != len(actual):
        raise ValueError("请提交完整的实际 PDF 页列表（最多 20000 页）；未解析页不能凭空补齐。")
    seen = set()
    for row in rows:
        index = row["pdf_page"]
        if index not in actual or index in seen:
            raise ValueError("页码表包含重复或不存在的 PDF 页。")
        seen.add(index)
        labels = [str(v).strip() for v in row.get("labels", [])]
        if len(labels) > 2 or any(not v for v in labels) or len(set(labels)) != len(labels) or len("–".join(labels)) > 40:
            raise ValueError("每个 PDF 页最多对应两个不同印刷页码，合并长度不能超过 40 字。")
        row.update(labels=labels, page_type=row.get("page_type", "body"), confirmed=bool(row.get("confirmed", False)),
                   note=str(row.get("note", "")).strip(), source_note=str(row.get("source_note", "")).strip(),
                   override_manual=bool(row.get("override_manual", False)))
        old = actual[index]
        changed = "–".join(labels) != old.printed_label
        row["source"] = "manual" if row["confirmed"] else row.get("source", old.label_source)
        row["confidence"] = 1.0 if row["confirmed"] else min(1, max(0, float(row.get("confidence", 0))))
        if changed and old.is_label_manual and not (row["override_manual"] and row["confirmed"] and row["note"]):
            raise ValueError(f"PDF 第 {index} 页已有人工锁定；请明确允许修改、确认新值并说明原因。")
    previous_end = 0
    segment_ids = set()
    for row in sorted(segments, key=lambda r: r["start"]):
        if row["id"] in segment_ids or row["start"] not in actual or row["end"] not in actual or row["end"] < row["start"] or row["start"] <= previous_end:
            raise ValueError("页码分段必须位于真实 PDF 页内，且段落标识、范围不得重复或重叠。")
        segment_ids.add(row["id"])
        previous_end = row["end"]
    missing_ids = set()
    for row in missing:
        if row["id"] in missing_ids or row["after_pdf_page"] not in actual:
            raise ValueError("缺页记录需要唯一标识和真实相邻 PDF 页。")
        missing_ids.add(row["id"])
        row["action"] = row.get("action", "mark")
        if row["action"] not in {"mark", "blank"}:
            raise ValueError("请选择标记缺页或在独立副本中插入空白页。")
        if not str(row["label"]).strip():
            raise ValueError("缺页记录需要印刷页码。")
    return {"pages": sorted(rows, key=lambda r: r["pdf_page"]), "segments": sorted(segments, key=lambda r: r["start"]), "missing": missing}


def diagnostics(data):
    rows = data["pages"]
    labels = {}
    for row in rows:
        for label in row["labels"]:
            labels.setdefault(label, []).append(row)
    duplicates = [{"label": label, "pdf_pages": [r["pdf_page"] for r in values],
                   "acknowledged": all(r["confirmed"] and r["note"] for r in values)}
                  for label, values in labels.items() if len(values) > 1]
    return {"unconfirmed_pages": [r["pdf_page"] for r in rows if not r["confirmed"]],
            "duplicate_labels": duplicates,
            "spreads": [r["pdf_page"] for r in rows if len(r["labels"]) == 2],
            "unconfirmed_missing": [r["id"] for r in data["missing"] if not r.get("confirmed") or not r.get("note")],
            "missing_present": [r["id"] for r in data["missing"] if r["label"] in labels]}


def revision_payload(row, *, include_data=True):
    if row is None:
        return None
    event = row.publication_event
    result = {"id": str(row.pk), "revision": row.revision, "origin": row.origin,
              "created_at": row.created_at, "created_by_id": row.created_by_id,
              "restored_from_id": str(row.restored_from_id) if row.restored_from_id else None,
              "source_fingerprint": row.source_fingerprint, "applied_at": row.applied_at,
              "applied_asset_id": str(row.applied_asset_id) if row.applied_asset_id else None,
              "publication": {"event_id": str(event.pk), "status": event.status,
                              "revision_id": str(event.catalog_revision_id),
                              "revision_status": event.catalog_revision.status,
                              "error": event.catalog_revision.failure_message} if event else None}
    if include_data:
        result["data"] = deepcopy(row.data)
        result["diagnostics"] = diagnostics(row.data)
    return result


def mapping_state(asset, *, history_page=1):
    from ingestion.models import ProcessingJob
    jobs = ProcessingJob.objects.filter(asset=asset, stats__operation="page_mapping_export").order_by("-created_at")[:10]
    pages = _pages(asset)
    latest = asset.page_mapping_revisions.select_related("publication_event__catalog_revision").first()
    count = asset.page_mapping_revisions.count()
    history_page = min(max(1, history_page), max(1, (count + 19) // 20))
    start = (history_page - 1) * 20
    # Reuse the existing, permission-scoped asset/preview identity contract.
    summary = outline_state(asset)["asset"]
    summary["publication_state"] = asset.edition.state
    summary["byte_size"] = asset.byte_size
    preceding = PageMappingRevision.objects.filter(applied_asset=asset).exclude(asset=asset).order_by("-applied_at").first()
    return {"jobs": [{"id": str(job.pk), "status": job.status, "progress": job.progress,
                "updated_at": job.updated_at, "error": job.error_message,
                "mapping_revision_id": job.stats.get("mapping_revision_id", ""),
                "download_url": f"/catalog/admin/editions/{asset.edition_id}/files/{job.stats['result_asset_id']}/content/?download=1"
                    if job.status == "succeeded" and job.stats.get("result_asset_id") else ""} for job in jobs],
            "asset": summary, "asset_id": str(asset.pk), "expected_revision": latest.revision if latest else 0,
            "source_fingerprint": source_fingerprint(asset, pages), "current": current_data(asset, pages),
            "latest": revision_payload(latest), "history": [revision_payload(r, include_data=False) for r in
                asset.page_mapping_revisions.select_related("publication_event__catalog_revision")[start:start + 20]],
            "history_count": count, "history_page": history_page,
            "preceding_revision": {"asset_id": str(preceding.asset_id), "revision_id": str(preceding.pk), "revision": preceding.revision} if preceding else None,
            "history_next_page": history_page + 1 if start + 20 < count else None}


def _guard(asset, data):
    latest = asset.page_mapping_revisions.first()
    if data["expected_revision"] != (latest.revision if latest else 0):
        raise MappingConflict("页码已有新候选；请保留输入，读取差异后再保存。")
    try:
        _source_current(asset)
    except OutlineConflict as exc:
        raise MappingConflict(str(exc)) from exc
    if data["source_fingerprint"] != source_fingerprint(asset):
        raise MappingConflict("文件、正文或发布状态已改变，请重新读取当前来源后再操作。")


def _locked_asset(identifier):
    edition_id = Asset.objects.values_list("edition_id", flat=True).get(pk=identifier)
    Edition.objects.select_for_update().get(pk=edition_id)
    return Asset.objects.select_for_update(of=("self",)).select_related("edition__work").get(pk=identifier, kind="normalized")


def _command_fingerprint(data, actor):
    return _hash({"command": data, "actor": actor.pk})


def _replay(asset, data, actor, *, applying=False):
    row = asset.page_mapping_revisions.filter(Q(request_id=data["request_id"]) | Q(apply_request_id=data["request_id"])).first()
    if row is None:
        return None
    fingerprint = row.apply_fingerprint if applying and row.apply_request_id == data["request_id"] else row.request_fingerprint
    if fingerprint != _command_fingerprint(data, actor):
        raise MappingConflict("同一请求标识已用于其他内容；请保留输入并重新提交。")
    return row


def _analyze(asset, data):
    result = deepcopy(data)
    pages = {p.index: p for p in asset.pages.prefetch_related("blocks").order_by("index")}
    candidates = {index: c for index, page in pages.items() if (c := _page_label_candidate(page)) is not None}
    for row in result["pages"]:
        if row["confirmed"] or pages[row["pdf_page"]].is_label_manual:
            continue
        index = row["pdf_page"]
        c = candidates.get(index)
        if c and any(n in candidates and candidates[n][2] == c[2] and candidates[n][1] == c[1] + delta
                     for n, delta in ((index - 1, -1), (index + 1, 1))):
            row.update(labels=[c[0]], source=c[4], confidence=c[3], confirmed=False)
    return result


def _segment(data, segment):
    result = deepcopy(data)
    segments = [s for s in result["segments"] if s["id"] != segment["id"]]
    segments.append(segment)
    result["segments"] = segments
    number, parsed_style = _parse_label(segment["start_label"])
    style = segment["style"]
    if style != "none" and (number is None or style != parsed_style):
        raise ValueError("首个页码需要与阿拉伯或罗马编号格式一致。")
    for row in result["pages"]:
        if segment["start"] <= row["pdf_page"] <= segment["end"] and not row["confirmed"]:
            value = (number or 0) + row["pdf_page"] - segment["start"]
            if style.startswith("roman") and not 1 <= value <= 3999:
                raise ValueError("罗马页码范围应为 1–3999。")
            row.update(labels=[] if style == "none" else [_format_label(value, style)], source="sequence", confidence=0.5)
    return result


@transaction.atomic
def save_mapping(identifier, *, data, actor):
    asset = _locked_asset(identifier)
    previous = _replay(asset, data, actor)
    if previous:
        return previous
    _guard(asset, data)
    latest = asset.page_mapping_revisions.first()
    action = data["action"]
    restored = None
    if action in {"analyze", "segment"} and latest and latest.source_fingerprint != source_fingerprint(asset):
        raise MappingConflict("当前候选依据旧来源；请先核对并保存当前页表，再生成新的候选。")
    content = deepcopy(latest.data if latest else current_data(asset))
    if action == "save":
        content = data["data"]
    elif action == "restore":
        restored = asset.page_mapping_revisions.filter(pk=data["revision_id"]).first()
        if restored is None:
            raise ValueError("此页码修订不属于当前文件。")
        if restored.source_fingerprint != source_fingerprint(asset):
            raise MappingConflict("旧候选依据的文件或正文已改变；请在当前页表中重新核对，不直接恢复旧结论。")
        content = deepcopy(restored.data)
    elif action == "analyze":
        content = _analyze(asset, content)
    elif action == "segment":
        content = _segment(content, data["segment"])
    content = validate_data(asset, content)
    return PageMappingRevision.objects.create(
        asset=asset, revision=(latest.revision if latest else 0) + 1,
        source_fingerprint=source_fingerprint(asset), data=content,
        origin=action, request_id=data["request_id"], request_fingerprint=_command_fingerprint(data, actor),
        restored_from=restored, created_by=actor,
    )


def prepare_mapping(asset, row):
    from catalog.services.page_mapping_exports import completed_copy, expanded_mapping
    if row.asset_id != asset.pk:
        raise ValueError("页码候选不属于当前文件。")
    current = current_data(asset)
    old = {r["pdf_page"]: r for r in current["pages"]}
    diag = diagnostics(row.data)
    expanded, positions, inserted = expanded_mapping(row.data)
    copy_asset = completed_copy(asset, row) if inserted else None
    changes = [{"pdf_page": r["pdf_page"], "new_pdf_page": positions[r["pdf_page"]], "before": old[r["pdf_page"]]["labels"], "after": r["labels"],
                "page_type_before": old[r["pdf_page"]]["page_type"], "page_type_after": r["page_type"],
                "note": r["note"], "source_note_before": old[r["pdf_page"]].get("source_note", ""),
                "source_note_after": r.get("source_note", ""), "manual_before": old[r["pdf_page"]]["confirmed"]}
               for r in row.data["pages"] if r["pdf_page"] in old and
               (positions[r["pdf_page"]] != r["pdf_page"] or
                (r["labels"], r["page_type"], r["confirmed"], r["note"], r.get("source_note", "")) !=
                (old[r["pdf_page"]]["labels"], old[r["pdf_page"]]["page_type"], old[r["pdf_page"]]["confirmed"], old[r["pdf_page"]]["note"], old[r["pdf_page"]].get("source_note", "")))]
    blockers = []
    if inserted and not copy_asset:
        blockers.append("请先生成当前已保存校准的补页副本，待回读核对完成后再确认发布。")
    try:
        _source_current(asset)
    except OutlineConflict as exc:
        blockers.append(str(exc))
    if row.source_fingerprint != source_fingerprint(asset):
        blockers.append("候选来源已改变，请基于当前文件重新保存候选。")
    if not asset.page_count or set(old) != set(range(1, asset.page_count + 1)):
        blockers.append("实际 PDF 页解析不完整，请先恢复文件解析；不能以缺印刷页代替缺失的物理页。")
    if diag["unconfirmed_pages"]:
        blockers.append("仍有未确认的实际页码（无印刷页码也需要明确确认）。")
    if any(not r["acknowledged"] for r in diag["duplicate_labels"]):
        blockers.append("重复印刷页码需要逐页确认并填写保留原因。")
    if diag["unconfirmed_missing"] or diag["missing_present"]:
        blockers.append("缺页记录需要原因和确认，并且该印刷页码不能同时存在于实际页中。")
    active = asset.edition.active_catalog_revision
    if asset.edition.state == PublicationState.WITHDRAWN:
        blockers.append("此版本已下架，请从馆藏发布流程处理。")
    if asset.edition.state == PublicationState.PUBLISHED and (not active or active.reader_asset_id != asset.pk):
        blockers.append("此文件不是当前公开阅读文件；请先完成文件上架或切换流程。")
    if asset.edition.catalog_revisions.filter(revision__gt=active.revision if active else 0, status__in=["preparing", "failed"]).exists():
        blockers.append("尚有馆藏发布等待完成或恢复，请先在发布记录处理。")
    result = {"revision_id": str(row.pk), "source_fingerprint": source_fingerprint(asset),
              "copy_asset_id": str(copy_asset.pk) if copy_asset else None,
              "inserted_pages": inserted, "new_page_count": len(expanded["pages"]),
              "changes": changes, "changed_page_count": len(changes),
              "missing_before": current["missing"], "missing_after": expanded["missing"],
              "segments_before": current["segments"], "segments_after": expanded["segments"],
              "diagnostics": diag, "blockers": blockers, "can_apply": not blockers,
              "mode": "publish" if asset.edition.state == PublicationState.PUBLISHED else "apply_draft"}
    result["prepared_fingerprint"] = _hash(result)
    return result


@transaction.atomic
def apply_mapping(identifier, *, data, actor):
    from catalog.services.document_intelligence import stage_document_asset, synchronize_document_revision
    from catalog.services.knowledge_publication import create_catalog_publication_event
    from catalog.services.page_mapping_exports import completed_copy, expanded_mapping

    asset = _locked_asset(identifier)
    replay = _replay(asset, data, actor, applying=True)
    if replay:
        return replay
    _guard(asset, data)
    row = asset.page_mapping_revisions.select_for_update().filter(pk=data["revision_id"]).first()
    if row is None:
        raise ValueError("请选择当前文件的页码候选。")
    if row.applied_at:
        raise MappingConflict("此候选已采用；请从修订记录查看结果。")
    prepared = prepare_mapping(asset, row)
    if data["prepared_fingerprint"] != prepared["prepared_fingerprint"]:
        raise MappingConflict("影响预览已改变，请重新查看差异后确认。")
    if prepared["blockers"]:
        raise ValueError(" ".join(prepared["blockers"]))
    validate_data(asset, row.data)
    document = asset.document_revisions.filter(is_active=True).first()
    expanded, positions, inserted = expanded_mapping(row.data)
    copy_asset = completed_copy(asset, row) if inserted else None
    if inserted and (not copy_asset or str(copy_asset.pk) != prepared["copy_asset_id"]):
        raise MappingConflict("补页副本已变化，请重新查看影响预览。")
    staged = stage_document_asset(asset, stage_key=f"page-mapping:{row.pk}", force_copy=bool(inserted))
    if inserted:
        originals = {page.index: page for page in _pages(staged)}
        # Descending updates preserve the existing unique (asset, index) constraint.
        for old in sorted(originals, reverse=True):
            Page.objects.filter(pk=originals[old].pk).update(index=positions[old])
        for blank in inserted:
            adjacent = originals[blank["after_pdf_page"]]
            Page.objects.create(asset=staged, index=blank["pdf_page"], text_source=Page.TextSource.EMBEDDED,
                width=adjacent.width, height=adjacent.height, confidence=1)
        staged.file = copy_asset.file.name
        staged.sha256, staged.byte_size, staged.page_count = copy_asset.sha256, copy_asset.byte_size, copy_asset.page_count
        details = dict(staged.validation_details or {})
        for key in ("ocr_required_page_indexes", "ocr_detected_page_indexes"):
            if isinstance(details.get(key), list):
                details[key] = [positions[index] for index in details[key] if index in positions]
        prior_blanks = (details.get("physical_page_mapping") or {}).get("inserted_pages", [])
        details["physical_page_mapping"] = {"copy_asset_id": str(copy_asset.pk), "source_asset_id": str(asset.pk),
            "target_asset_id": str(staged.pk), "mapping_revision_id": str(row.pk),
            "source_document_revision_id": str(document.pk) if document else "",
            "positions": {str(old): new for old, new in positions.items()},
            "inserted_pages": sorted({positions[index] for index in prior_blanks if index in positions} | {item["pdf_page"] for item in inserted})}
        staged.validation_details = details
        staged.save(update_fields=["file", "sha256", "byte_size", "page_count", "validation_details", "updated_at"])
    segments = {}
    staged.page_label_segments.all().delete()
    for s in expanded["segments"]:
        segment = PageLabelSegment.objects.create(asset=staged, start_file_page_index=s["start"], end_file_page_index=s["end"],
            start_label=s["start_label"], style=s["style"], source="manual", confidence=1, created_by=actor)
        for index in range(s["start"], s["end"] + 1):
            segments[index] = str(segment.pk)
    changed = {r["pdf_page"]: r for r in expanded["pages"]}
    pages = _pages(staged)
    for page in pages:
        item = changed[page.index]
        page.printed_label = "–".join(item["labels"])
        page.is_label_manual = True
        page.is_label_anchor = True
        page.label_source = Page.LabelSource.MANUAL
        page.label_confidence = 1
        page.label_segment = segments.get(page.index, "")
    Page.objects.bulk_update(pages, ["printed_label", "is_label_manual", "is_label_anchor", "label_source", "label_confidence", "label_segment"])
    staged.validation_details = {**(staged.validation_details or {}), "page_mapping": {**expanded, "revision_id": str(row.pk)}}
    staged.save(update_fields=["validation_details", "updated_at"])
    outline = asset.outline_revisions.filter(is_active=True, source_checksum=asset.sha256,
        document_revision=document).first() if document else None
    result = synchronize_document_revision(staged,
        parser_name=document.parser_name if document else "page-mapping",
        parser_version=document.parser_version if document else "page-mapping-v1",
        extraction_method=document.extraction_method if document else "existing-text",
        extraction_version=document.extraction_version if document else "page-mapping-v1",
        ocr_provider=document.ocr_provider if document else "", ocr_model=document.ocr_model if document else "",
        ocr_version=document.ocr_version if document else "", actor=actor, schedule_outline=not bool(outline))
    mapped_outline = None
    if outline:
        nodes = deepcopy(outline.nodes)
        for node in nodes:
            if node.get("pdf_page") in positions:
                node["pdf_page"] = positions[node["pdf_page"]]
            if node.get("pdf_page") in changed:
                node["printed_label"] = "–".join(changed[node["pdf_page"]]["labels"])
        staged.outline_revisions.filter(is_active=True).update(is_active=False)
        mapped_outline = DocumentOutlineRevision.objects.create(asset=staged,
            revision=(staged.outline_revisions.order_by("-revision").values_list("revision", flat=True).first() or 0) + 1,
            document_revision_id=result["revision_id"], source_checksum=staged.sha256,
            parser_version=outline.parser_version, nodes=nodes, diagnostics=deepcopy(outline.diagnostics),
            origin="page_mapping", is_active=True, reviewed=outline.reviewed, created_by=actor)
    if staged.pk != asset.pk:
        staged.validation_details["navigation_mapping"] = {"source_asset_id": str(asset.pk), "target_asset_id": str(staged.pk),
            "source_document_revision_id": str(document.pk) if document else "", "document_revision_id": str(result["revision_id"]),
            "source_outline_revision_id": str(outline.pk) if outline else "", "outline_revision_id": str(mapped_outline.pk) if mapped_outline else "",
            "positions": {str(old): new for old, new in positions.items()}, "page_count": staged.page_count}
        staged.save(update_fields=["validation_details", "updated_at"])
    if prepared["mode"] == "publish":
        row.publication_event = create_catalog_publication_event(asset.edition,
            event_type=KnowledgePublicationEvent.EventType.CATALOG_UPDATED,
            changed_fields=["document_revision", "fulltext_ready"], actor=actor,
            idempotency_key=f"page-mapping:{row.pk}:{data['request_id']}", content_asset_id=staged.pk,
            provenance={"source": "page_mapping", "page_mapping_revision_id": str(row.pk), "source_asset_id": str(asset.pk)})
    else:
        if inserted:
            Asset.objects.filter(edition=asset.edition, kind=Asset.Kind.NORMALIZED, is_current=True).exclude(pk=staged.pk).update(is_current=False, updated_at=timezone.now())
            staged.is_current = True
            staged.save(update_fields=["is_current", "updated_at"])
        asset.edition.page_label_status = PageLabelStatus.READY
        asset.edition.save(update_fields=["page_label_status", "updated_at"])
    row.applied_asset = staged
    row.apply_request_id = data["request_id"]
    row.apply_fingerprint = _command_fingerprint(data, actor)
    row.applied_at = timezone.now()
    row.save(update_fields=["publication_event", "applied_asset", "apply_request_id", "apply_fingerprint", "applied_at", "updated_at"])
    return row
