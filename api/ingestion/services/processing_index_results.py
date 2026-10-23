"""Export only durable passage rows from the original Discovery source job."""
from hashlib import sha256
import json
from uuid import UUID

from django.db.models import Count, Max
from django.db.models.functions import Length
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.discovery_index_models import DiscoveryDocument, DiscoverySourceState
from catalog.models import SemanticIndexVersion
from catalog.services.discovery_sources import get_source
from catalog.services.editorial_issues import EditConflict


def discovery_result_source(job, actor, data):
    stats = job.stats or {}
    if stats.get("action") != "source" or stats.get("source_type") != "edition":
        raise ValidationError("此入口导出单份文献的成功索引片段；全库构建与知识条目请从原索引维护入口查看。")
    try:
        generation_id, source_id = UUID(str(stats["generation_id"])), UUID(str(stats["source_id"]))
    except (KeyError, ValueError, TypeError):
        raise EditConflict("原任务没有可核对的索引或文献编号。")
    if job.edition_id != source_id:
        raise EditConflict("任务文献与索引来源不一致，请先核对原任务。")
    # Index workers also hold internal materials. Explicit public scope is mandatory
    # here: task-view capability alone never grants access to private source text.
    edition, header = get_source("edition", source_id, access_statuses=["public"])
    if header is None:
        raise PermissionDenied("原文献已撤下、限制访问或不再具备有效公开原文，不能导出留存的索引片段。")
    asset = edition.active_catalog_revision.reader_asset
    if job.asset_id != asset.pk or stats.get("source_revision") != header["source_revision"]:
        raise EditConflict("原文献或采用版本已变化，请打开当前材料对应的新任务。")
    generation = SemanticIndexVersion.discovery_objects.filter(pk=generation_id).first()
    state = DiscoverySourceState.objects.filter(generation_id=generation_id, source_type="edition", source_id=source_id, job=job).first()
    if generation is None or state is None:
        raise EditConflict("索引来源已转交其他任务或原索引已移除，不能将留存片段认作本任务结果。")
    if not 1 <= asset.page_count <= 20000:
        raise ValidationError("原文件页数尚未核实或超过本入口上限，请先核对材料。")
    start, end = data["page_from"], data.get("page_to", asset.page_count)
    if start > asset.page_count or end > asset.page_count:
        raise ValidationError("所选范围超出当前文件的PDF页数。")
    completed = DiscoveryDocument.objects.filter(
        generation=generation, source_type="edition", source_id=source_id, source_revision=header["source_revision"],
        edition=edition, document_revision_id=header["document_revision_id"], access_status="public", channel="passages",
        scope_token=header["scope_token"], keyword_ready=True, vector_ready=True, indexed_at__isnull=False,
        payload__asset_id=str(asset.pk), payload__pdf_page__gte=1, payload__pdf_page__lte=asset.page_count,
    )
    rows = completed.filter(payload__pdf_page__gte=start, payload__pdf_page__lte=end).order_by("payload__pdf_page", "payload__unit_id", "start_offset", "id")
    snapshot = rows.aggregate(count=Count("pk"), max_chars=Max(Length("text")))
    total = completed.count()
    if snapshot["count"] > 20000 or (snapshot["max_chars"] or 0) > 1000000:
        raise ValidationError("所选结果过多或含异常长片段，请缩小PDF页序范围后分批导出。")
    # A bounded identity walk catches removal/replacement of any selected row, not
    # merely changes to the single greatest updated_at timestamp.
    digest = sha256()
    for identity in rows.values("id", "input_hash", "updated_at", "indexed_at", "start_offset", "end_offset", "payload__pdf_page", "payload__unit_id").iterator(chunk_size=200):
        digest.update(json.dumps(identity, sort_keys=True, default=str).encode())
    version = sha256(json.dumps({"job": str(job.pk), "source": header["source_revision"], "range": [start, end],
        "generation": str(generation.pk), "generation_status": generation.status, "state": str(state.pk),
        "state_updated": state.updated_at, "task_status": job.status, "count": snapshot["count"], "total": total,
        "rows": digest.hexdigest()}, sort_keys=True, default=str).encode()).hexdigest()
    return {"owner_id": str(actor.pk), "task_id": str(job.pk), "kind": "discovery", "asset_id": str(asset.pk),
        "revision_id": header["document_revision_id"], "index_generation_id": str(generation.pk),
        "source_revision": header["source_revision"], "title": header["title"], "task_status": job.status,
        "count": snapshot["count"], "total_recorded": total, "page_count": asset.page_count,
        "version": version, "checked_at": timezone.now(), "formats": ["txt", "jsonl"] if snapshot["count"] else [],
        "notice": "仅导出原任务来源修订中已确认写入关键词和向量索引的片段。部分失败时保留成功片段；派生片段不等于完整原文，也不代表该索引已启用。字符偏移以每个原文单元为起点，未导出向量、私人笔记或未完成片段。"}, rows


def discovery_export_rows(rows):
    for row in rows.values("id", "text", "start_offset", "end_offset", "source_revision", "indexed_at", "payload").iterator(chunk_size=20):
        payload = row.pop("payload")
        # Never export the unrestricted index payload (it can grow new fields).
        yield {**row, "unit_id": payload.get("unit_id"), "pdf_page": payload.get("pdf_page"),
            "printed_page": payload.get("printed_page"), "source_start_offset": payload.get("source_start_offset"),
            "source_kind": payload.get("source_kind"), "offset_origin": "source_unit"}
