from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from catalog.models import Asset, Passage, PublicationState, SemanticChunk
from ingestion.models import UploadItem


def _stored_file(field_file) -> tuple[bool, int, str]:
    if not field_file or not getattr(field_file, "name", ""):
        return False, 0, "未保存文件路径"
    try:
        exists = field_file.storage.exists(field_file.name)
        size = int(field_file.storage.size(field_file.name)) if exists else 0
    except Exception as exc:
        return False, 0, f"无法读取存储：{exc.__class__.__name__}: {str(exc)[:300]}"
    return exists, size, field_file.name


def _check(name: str, ok: bool, detail, *, required: bool = True) -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "required": bool(required),
        "detail": detail,
    }


def verify_item(item: UploadItem, *, expected_status: str = "") -> dict:
    checks: list[dict] = []
    source_exists, source_size, source_name = _stored_file(item.file)
    checks.append(
        _check(
            "原始 PDF 已持久保存",
            source_exists and source_size > 0,
            {"path": source_name, "bytes": source_size},
        )
    )
    if item.byte_size:
        checks.append(
            _check(
                "原始 PDF 大小一致",
                source_size == item.byte_size,
                {"recorded": item.byte_size, "stored": source_size},
            )
        )
    if expected_status:
        checks.append(
            _check(
                "入库状态符合预期",
                item.status == expected_status,
                {"expected": expected_status, "actual": item.status},
            )
        )

    terminal_success = item.status in {
        UploadItem.Status.NEEDS_REVIEW,
        UploadItem.Status.READY,
        UploadItem.Status.PUBLISHED,
    }
    dispatch_ok = item.dispatch_status == UploadItem.DispatchStatus.COMPLETED
    checks.append(
        _check(
            "后台任务已完成派发与执行",
            dispatch_ok,
            {
                "status": item.dispatch_status,
                "kind": item.dispatch_kind,
                "attempts": item.dispatch_attempts,
                "error": item.dispatch_error,
            },
            required=terminal_success,
        )
    )

    edition = item.edition
    checks.append(
        _check(
            "书目版本记录已建立",
            edition is not None,
            str(item.edition_id or ""),
            required=terminal_success,
        )
    )

    normalized = None
    pages = passages = 0
    semantic_counts: dict[str, int] = {}
    if edition is not None:
        normalized = (
            edition.assets.filter(kind=Asset.Kind.NORMALIZED, is_current=True)
            .order_by("-version")
            .first()
        )
        checks.append(
            _check(
                "规范阅读副本已建立",
                normalized is not None,
                str(normalized.id) if normalized else "",
                required=terminal_success,
            )
        )
        if normalized is not None:
            normalized_exists, normalized_size, normalized_name = _stored_file(normalized.file)
            pages = normalized.pages.count()
            passages = Passage.objects.filter(page__asset=normalized).count()
            semantic_counts = {
                row["index_status"]: row["count"]
                for row in normalized.semantic_chunks.values("index_status")
                .order_by()
                .annotate(count=Count("id"))
            }
            checks.extend(
                [
                    _check(
                        "规范阅读 PDF 可读取",
                        normalized.status == Asset.Status.READY
                        and normalized_exists
                        and normalized_size > 0,
                        {
                            "status": normalized.status,
                            "path": normalized_name,
                            "bytes": normalized_size,
                        },
                        required=terminal_success,
                    ),
                    _check(
                        "PDF 页文本已建立",
                        pages > 0 and (not normalized.page_count or pages == normalized.page_count),
                        {"database_pages": pages, "asset_page_count": normalized.page_count},
                        required=terminal_success,
                    ),
                    _check(
                        "全文检索段落已建立",
                        passages > 0,
                        passages,
                        required=terminal_success,
                    ),
                    _check(
                        "语义分块可用",
                        semantic_counts.get(SemanticChunk.IndexStatus.READY, 0) > 0,
                        semantic_counts,
                        required=False,
                    ),
                ]
            )

    if item.status == UploadItem.Status.PUBLISHED:
        checks.extend(
            [
                _check(
                    "版本已正式发布",
                    bool(edition and edition.state == PublicationState.PUBLISHED),
                    edition.state if edition else "",
                ),
                _check(
                    "公开详情地址已生成",
                    bool(edition and edition.public_slug),
                    edition.public_slug if edition else "",
                ),
                _check(
                    "全文索引完成时间已记录",
                    bool(edition and edition.search_indexed_at),
                    edition.search_indexed_at if edition else None,
                ),
                _check(
                    "公开阅读副本完成时间已记录",
                    bool(edition and edition.public_asset_prepared_at),
                    edition.public_asset_prepared_at if edition else None,
                ),
                _check("发布进度为 100%", item.stage_progress == 100, item.stage_progress),
            ]
        )

    attempts = list(
        item.attempts.order_by("started_at").values(
            "stage",
            "attempt_number",
            "status",
            "error_code",
        )
    )
    required_failures = [row for row in checks if row["required"] and not row["ok"]]
    warnings = [row for row in checks if not row["required"] and not row["ok"]]
    return {
        "ok": not required_failures,
        "item": {
            "id": str(item.id),
            "source_filename": item.source_filename,
            "status": item.status,
            "progress": item.stage_progress,
            "updated_at": item.updated_at,
            "edition_id": str(item.edition_id or ""),
            "work_id": str(edition.work_id) if edition else "",
            "public_slug": edition.public_slug if edition else "",
            "normalized_asset_id": str(normalized.id) if normalized else "",
            "pages": pages,
            "passages": passages,
        },
        "checks": checks,
        "required_failures": required_failures,
        "warnings": warnings,
        "processing_attempts": attempts,
        "last_error": {
            "code": item.error_code,
            "message": item.error_message,
        },
    }


class Command(BaseCommand):
    help = "核验一份上传 PDF 从原始文件、文本处理到公开发布的完整状态。"

    def add_arguments(self, parser):
        selector = parser.add_mutually_exclusive_group(required=True)
        selector.add_argument("--item-id", help="上传项目 UUID。")
        selector.add_argument("--source-filename", help="完整或部分原始文件名，取最新一条。")
        parser.add_argument(
            "--expect-status",
            choices=[choice for choice, _label in UploadItem.Status.choices],
            default="",
        )
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        queryset = UploadItem.objects.select_related("edition__work").prefetch_related("attempts")
        if options["item_id"]:
            item = queryset.filter(pk=options["item_id"]).first()
        else:
            item = queryset.filter(source_filename__icontains=options["source_filename"]).order_by("-created_at").first()
        if item is None:
            raise CommandError("没有找到指定的上传记录。")

        result = verify_item(item, expected_status=options["expect_status"])
        if options["json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            self.stdout.write(
                f"{item.source_filename}：{item.status}，进度 {item.stage_progress}%，"
                f"必需检查 {'通过' if result['ok'] else '失败'}。"
            )
            for row in result["checks"]:
                level = "通过" if row["ok"] else "警告" if not row["required"] else "失败"
                self.stdout.write(f"[{level}] {row['name']}：{row['detail']}")
        if options["strict"] and not result["ok"]:
            raise CommandError("该 PDF 尚未完成可用的入库或发布流程。")
