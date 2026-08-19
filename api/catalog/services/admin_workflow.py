from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from catalog.models import (
    Asset,
    Edition,
    EditionWorkflowDecision,
    EnrichmentCandidate,
    KnowledgePublicationStatus,
    PublicationState,
    ReadingPathItem,
    RecommendationOverride,
    RelationReviewStatus,
    ReviewStatus,
    TheoryReviewTask,
    WorkKnowledgeRelation,
)
from ingestion.models import EntityResolutionCandidate, MetadataCandidate, UploadItem
from ingestion.services.prerequisites import (
    initial_ingestion_block_message,
    initial_ingestion_block_reason,
    is_r2_pre_import_block,
)


WORKFLOW_STEPS = (
    ("file", "文件与识别"),
    ("work", "作品识别"),
    ("bibliography", "书目与出版"),
    ("contributors", "责任者与身份"),
    ("classification", "社科分类"),
    ("knowledge", "理论、主题与知识关系"),
    ("reader", "文本与阅读文件"),
    ("curation", "策展定位"),
    ("publication", "发布检查与上架"),
)

WORK_FIELDS = (
    "document_type",
    "title",
    "subtitle",
    "original_title",
    "uniform_title",
    "language",
    "original_language",
    "first_publication_date",
    "translation_of_id",
    "abstract",
)

BIBLIOGRAPHY_FIELDS = (
    "version_label",
    "publication_year",
    "publisher",
    "publication_place",
    "journal_title",
    "volume",
    "issue",
    "page_range",
    "degree_institution",
    "degree_type",
    "report_institution",
    "isbn",
    "isbn10",
    "isbn13",
    "doi",
    "series",
    "extent",
    "responsibility_statement",
)

METADATA_FIELDS_BY_STEP = {
    "work": {
        "title",
        "subtitle",
        "document_type",
        "language",
        "abstract",
        "original_title",
        "uniform_title",
        "original_language",
        "first_publication_date",
    },
    "bibliography": set(BIBLIOGRAPHY_FIELDS),
    "contributors": {"authors", "contributors"},
    "classification": {"disciplines", "subdisciplines"},
    "knowledge": {"theory_schools", "topics", "concepts", "knowledge_nodes"},
}

ACTIVE_UPLOAD_STATUSES = {
    UploadItem.Status.RECEIVED,
    UploadItem.Status.VALIDATING,
    UploadItem.Status.DEDUPLICATING,
    UploadItem.Status.EXTRACTING,
    UploadItem.Status.OCR,
    UploadItem.Status.METADATA,
    UploadItem.Status.LINKING,
    UploadItem.Status.INDEXING,
    UploadItem.Status.PREPARING_PUBLIC_ASSET,
    UploadItem.Status.SYNCING_CLOUD,
}


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _fingerprint(payload: Any) -> str:
    serialized = json.dumps(
        _json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _metadata_candidate_rows(edition: Edition, fields: set[str]) -> list[dict[str, Any]]:
    return list(
        MetadataCandidate.objects.filter(
            upload_item__edition=edition,
            field_name__in=fields,
        )
        .order_by("field_name", "id")
        .values("id", "field_name", "lifecycle", "value", "is_locked")
    )


def step_fingerprint(edition: Edition, step_key: str) -> str:
    work = edition.work
    if step_key == "work":
        payload = {
            "work": {field: getattr(work, field) for field in WORK_FIELDS},
            "candidates": _metadata_candidate_rows(edition, METADATA_FIELDS_BY_STEP[step_key]),
            "catalog_reconciliation": list(
                UploadItem.objects.filter(edition=edition)
                .order_by("id")
                .values_list("preflight_summary", flat=True)
            ),
        }
    elif step_key == "bibliography":
        payload = {
            "edition": {field: getattr(edition, field) for field in BIBLIOGRAPHY_FIELDS},
            "candidates": _metadata_candidate_rows(edition, METADATA_FIELDS_BY_STEP[step_key]),
        }
    elif step_key == "contributors":
        payload = {
            "contributions": list(
                edition.contributions.order_by("order", "id").values(
                    "person_id",
                    "role",
                    "order",
                    "approved",
                    "source",
                )
            ),
            "candidates": list(
                EntityResolutionCandidate.objects.filter(
                    upload_item__edition=edition,
                    target_type="person",
                )
                .order_by("source_name", "id")
                .values("id", "source_name", "candidate_entity_id", "status")
            ),
        }
    elif step_key == "classification":
        payload = {
            "disciplines": list(
                work.discipline_relations.order_by("discipline_id").values(
                    "discipline_id",
                    "is_primary",
                    "review_status",
                )
            ),
            "subdisciplines": list(
                work.subdiscipline_relations.order_by("subdiscipline_id").values(
                    "subdiscipline_id",
                    "is_primary",
                    "strength",
                    "review_status",
                )
            ),
            "candidates": _metadata_candidate_rows(edition, METADATA_FIELDS_BY_STEP[step_key]),
        }
    elif step_key == "knowledge":
        payload = {
            "legacy": list(
                work.knowledge_relations.order_by("kind", "id").values(
                    "id",
                    "kind",
                    "theory_school_id",
                    "topic_id",
                    "concept_id",
                    "role",
                    "strength",
                    "is_primary",
                    "approved",
                    "review_status",
                )
            ),
            "nodes": list(
                work.node_relations.order_by("node_id", "role", "id").values(
                    "id",
                    "node_id",
                    "role",
                    "strength",
                    "is_primary",
                    "status",
                )
            ),
            "tasks": list(
                TheoryReviewTask.objects.filter(work=work)
                .order_by("id")
                .values("id", "task_type", "candidate_node_id", "status")
            ),
            "candidates": _metadata_candidate_rows(edition, METADATA_FIELDS_BY_STEP[step_key]),
        }
    elif step_key == "reader":
        payload = {
            "edition": {
                "reader_rendition_policy": edition.reader_rendition_policy,
                "ocr_status": edition.ocr_status,
                "page_label_status": edition.page_label_status,
                "semantic_index_status": edition.semantic_index_status,
                "search_indexed_at": edition.search_indexed_at,
            },
            "assets": list(
                edition.assets.order_by("kind", "version", "id").values(
                    "id",
                    "kind",
                    "status",
                    "validation_status",
                    "is_current",
                    "version",
                    "page_count",
                )
            ),
        }
    elif step_key == "curation":
        payload = {
            "reading_paths": list(
                ReadingPathItem.objects.filter(work=work)
                .order_by("reading_path_id", "position", "id")
                .values(
                    "id",
                    "reading_path_id",
                    "stage_id",
                    "stage_name",
                    "recommendation_reason",
                    "position",
                    "reading_order",
                    "is_required",
                    "editorial_note",
                )
            ),
            "recommendations": list(
                RecommendationOverride.objects.filter(work=work)
                .order_by("policy_id", "position", "id")
                .values("id", "policy_id", "action", "position", "active", "note")
            ),
        }
    else:
        raise ValueError(f"步骤 {step_key} 不支持人工确认。")
    return _fingerprint(payload)


def record_step_decision(
    edition: Edition,
    step_key: str,
    *,
    actor,
    decision: str = EditionWorkflowDecision.Decision.CONFIRMED,
    note: str = "",
) -> EditionWorkflowDecision:
    allowed_steps = set(EditionWorkflowDecision.Step.values)
    if step_key not in allowed_steps:
        raise ValueError("该步骤不支持人工确认。")
    if decision == EditionWorkflowDecision.Decision.SKIPPED and step_key != EditionWorkflowDecision.Step.CURATION:
        raise ValueError("只有策展步骤可以跳过。")
    fingerprint = step_fingerprint(edition, step_key)
    row, _created = EditionWorkflowDecision.objects.update_or_create(
        edition=edition,
        step_key=step_key,
        defaults={
            "decision": decision,
            "content_fingerprint": fingerprint,
            "note": note,
            "confirmed_by": actor,
            "confirmed_at": timezone.now(),
        },
    )
    return row


def _issue(code: str, message: str, step: str, *, severity: str = "warning", field: str = "") -> dict[str, Any]:
    target = f"#{step}"
    if field:
        target = f"{target}:{field}"
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "step": step,
        "field": field,
        "action_target": target,
    }


def _decision_state(edition: Edition, step_key: str) -> tuple[str, EditionWorkflowDecision | None]:
    decision = edition.workflow_decisions.filter(step_key=step_key).first()
    if decision is None:
        return "missing", None
    if decision.content_fingerprint != step_fingerprint(edition, step_key):
        return "stale", decision
    return decision.decision, decision


def _step_payload(
    key: str,
    label: str,
    status: str,
    issues: list[dict[str, Any]],
    summary: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "issues": issues,
        "summary": summary,
        "next_action": {
            "label": next_action,
            "step": key,
            "action_target": f"#{key}",
        },
    }


def _file_step(item: UploadItem | None, edition: Edition) -> dict[str, Any]:
    if item is None:
        return _step_payload(
            "file",
            "文件与识别",
            "skipped",
            [],
            "维护模式沿用当前版本文件，不要求存在上传记录。",
            "查看当前文件",
        )
    issues: list[dict[str, Any]] = []
    block_reason = (
        ""
        if item.asset_id and item.status not in ACTIVE_UPLOAD_STATUSES
        else initial_ingestion_block_reason(item)
    )
    staging_waiting = is_r2_pre_import_block(block_reason)
    if block_reason and block_reason != "staging_not_ready":
        issues.append(
            _issue(
                block_reason,
                initial_ingestion_block_message(block_reason),
                "file",
                severity="blocker",
            )
        )
    if item.status == UploadItem.Status.FAILED and not staging_waiting:
        issues.append(
            _issue(
                item.error_code or "upload_failed",
                item.error_message or "文件处理失败。",
                "file",
                severity="blocker",
            )
        )
    original = edition.assets.filter(kind=Asset.Kind.ORIGINAL, is_current=True).order_by("-version").first()
    normalized = edition.assets.filter(kind=Asset.Kind.NORMALIZED, is_current=True).order_by("-version").first()
    if original is None:
        issues.append(_issue("original_asset_missing", "原始 PDF 尚未建立。", "file", severity="blocker"))
    elif original.validation_status == Asset.ValidationStatus.INVALID:
        issues.append(_issue("original_asset_invalid", "原始 PDF 验证失败。", "file", severity="blocker"))
    if normalized is None and item.status not in ACTIVE_UPLOAD_STATUSES:
        issues.append(_issue("normalized_asset_missing", "规范阅读文件尚未建立。", "file", severity="blocker"))
    if any(row["severity"] == "blocker" for row in issues):
        status = "blocked"
    elif item.status in ACTIVE_UPLOAD_STATUSES or block_reason == "staging_not_ready":
        status = "working"
    else:
        status = "complete"
    summary_status = (
        item.get_staging_status_display()
        if staging_waiting
        else item.get_status_display()
    )
    summary = f"{item.source_filename} · {summary_status}"
    return _step_payload("file", "文件与识别", status, issues, summary, "处理文件问题")


def _confirmed_step(
    edition: Edition,
    key: str,
    label: str,
    issues: list[dict[str, Any]],
    summary: str,
    action: str,
) -> dict[str, Any]:
    decision_state, _decision = _decision_state(edition, key)
    blockers = [row for row in issues if row["severity"] == "blocker"]
    if blockers:
        status = "blocked"
    elif decision_state == EditionWorkflowDecision.Decision.SKIPPED:
        status = "skipped"
    elif decision_state == EditionWorkflowDecision.Decision.CONFIRMED:
        status = "complete"
    elif decision_state == "stale":
        issues.append(_issue("confirmation_stale", "本节内容已变化，需要重新确认。", key))
        status = "attention"
    elif issues:
        status = "attention"
    else:
        status = "available"
    return _step_payload(key, label, status, issues, summary, action)


def _work_step(edition: Edition) -> dict[str, Any]:
    work = edition.work
    issues = []
    if not work.title.strip():
        issues.append(_issue("title_required", "请填写作品题名。", "work", severity="blocker", field="title"))
    if work.document_type not in {"book", "journal_article", "thesis", "report"}:
        issues.append(
            _issue(
                "document_type_required",
                "请选择受支持的文献类型。",
                "work",
                severity="blocker",
                field="document_type",
            )
        )
    ambiguous_items = UploadItem.objects.filter(
        edition=edition,
        preflight_summary__catalog_reconciliation__requires_review=True,
    )
    ambiguous = any(
        item.entity_resolution_candidates.filter(
            target_type="work",
            status=EntityResolutionCandidate.Status.PROPOSED,
        ).exists()
        for item in ambiguous_items
    )
    if ambiguous:
        issues.append(
            _issue(
                "work_identity_review_required",
                "该作品可能对应馆内已有 Work 或新 Edition，请确认身份。",
                "work",
                severity="blocker",
            )
        )
    return _confirmed_step(edition, "work", "作品识别", issues, work.title or "未命名作品", "确认作品并继续")


def _bibliography_step(edition: Edition) -> dict[str, Any]:
    work = edition.work
    issues = []
    if edition.publication_year is None:
        issues.append(_issue("publication_year_missing", "出版或完成年份尚未补全。", "bibliography", field="publication_year"))
    if work.document_type == "book" and not edition.publisher.strip():
        issues.append(_issue("publisher_missing", "图书出版者尚未补全。", "bibliography", field="publisher"))
    elif work.document_type == "journal_article" and not edition.journal_title.strip():
        issues.append(_issue("journal_title_missing", "期刊名尚未补全。", "bibliography", field="journal_title"))
    elif work.document_type == "thesis":
        if not edition.degree_institution.strip():
            issues.append(_issue("degree_institution_missing", "学位授予单位尚未补全。", "bibliography", field="degree_institution"))
        if not edition.degree_type.strip():
            issues.append(_issue("degree_type_missing", "学位类型尚未补全。", "bibliography", field="degree_type"))
    elif work.document_type == "report" and not (edition.report_institution.strip() or edition.publisher.strip()):
        issues.append(_issue("report_institution_missing", "研究报告责任机构尚未补全。", "bibliography", field="report_institution"))
    summary = f"{edition.publication_year or '未定年'} · {edition.publisher or edition.journal_title or edition.degree_institution or edition.report_institution or '出版信息待补'}"
    return _confirmed_step(edition, "bibliography", "书目与出版", issues, summary, "确认书目并继续")


def _contributors_step(edition: Edition) -> dict[str, Any]:
    pending = EntityResolutionCandidate.objects.filter(
        upload_item__edition=edition,
        target_type="person",
        status=EntityResolutionCandidate.Status.PROPOSED,
    ).count()
    issues = []
    if pending:
        issues.append(
            _issue(
                "contributors_unresolved",
                f"仍有 {pending} 组责任者候选需要人工决定。",
                "contributors",
                severity="blocker",
            )
        )
    approved = edition.contributions.filter(approved=True).count()
    if not approved:
        issues.append(_issue("contributors_empty", "尚未确认正式责任者。", "contributors"))
    return _confirmed_step(
        edition,
        "contributors",
        "责任者与身份",
        issues,
        f"已确认 {approved} 位责任者",
        "确认责任者并继续",
    )


def _classification_step(edition: Edition) -> dict[str, Any]:
    work = edition.work
    suggested = work.discipline_relations.filter(review_status=RelationReviewStatus.SUGGESTED).count()
    suggested += work.subdiscipline_relations.filter(review_status=RelationReviewStatus.SUGGESTED).count()
    issues = []
    if suggested:
        issues.append(
            _issue(
                "classification_suggestions_pending",
                f"仍有 {suggested} 条分类建议需要人工决定。",
                "classification",
                severity="blocker",
            )
        )
    approved = work.discipline_relations.filter(review_status=RelationReviewStatus.APPROVED)
    if not approved.filter(is_primary=True).exists():
        issues.append(
            _issue(
                "primary_discipline_missing",
                "尚未确认主要学科。",
                "classification",
                severity="blocker",
            )
        )
    return _confirmed_step(
        edition,
        "classification",
        "社科分类",
        issues,
        f"{approved.count()} 个已确认学科",
        "确认分类并继续",
    )


def _knowledge_step(edition: Edition) -> dict[str, Any]:
    work = edition.work
    legacy_pending = work.knowledge_relations.filter(
        Q(approved=False) | Q(review_status=RelationReviewStatus.SUGGESTED)
    ).exclude(review_status=RelationReviewStatus.REJECTED).count()
    node_pending = work.node_relations.filter(
        status__in=[KnowledgePublicationStatus.PENDING, KnowledgePublicationStatus.DRAFT]
    ).count()
    task_pending = TheoryReviewTask.objects.filter(
        work=work,
        status__in=[
            TheoryReviewTask.TaskStatus.PENDING,
            TheoryReviewTask.TaskStatus.NEEDS_CHANGES,
        ],
    ).count()
    pending = legacy_pending + node_pending + task_pending
    issues = []
    if pending:
        issues.append(
            _issue(
                "knowledge_review_pending",
                f"仍有 {pending} 条知识建议或关系需要人工决定。",
                "knowledge",
                severity="blocker",
            )
        )
    confirmed = work.knowledge_relations.filter(approved=True).count()
    confirmed += work.node_relations.filter(status=KnowledgePublicationStatus.PUBLISHED).count()
    return _confirmed_step(
        edition,
        "knowledge",
        "理论、主题与知识关系",
        issues,
        f"{confirmed} 条正式知识关系",
        "确认知识关系并继续",
    )


def _reader_step(edition: Edition) -> dict[str, Any]:
    issues = []
    normalized = edition.assets.filter(
        kind=Asset.Kind.NORMALIZED,
        is_current=True,
        status=Asset.Status.READY,
    ).first()
    if normalized is None:
        issues.append(_issue("reader_asset_missing", "规范阅读文件尚未就绪。", "reader", severity="blocker"))
    elif normalized.validation_status == Asset.ValidationStatus.INVALID:
        issues.append(_issue("reader_asset_invalid", "规范阅读文件验证失败。", "reader", severity="blocker"))
    if edition.ocr_status == "failed":
        issues.append(_issue("ocr_failed", "全文文字层生成失败，当前仍可使用原始 PDF 阅读。", "reader"))
    if edition.page_label_status != "ready":
        issues.append(_issue("page_labels_pending", "引用页码尚未完成校对。", "reader"))
    if edition.semantic_index_status != "ready":
        issues.append(_issue("semantic_index_pending", "观点检索尚未就绪，将使用关键词降级。", "reader"))
    summary = f"阅读文件 {'已就绪' if normalized else '待处理'} · {edition.get_reader_rendition_policy_display()}"
    return _confirmed_step(edition, "reader", "文本与阅读文件", issues, summary, "确认阅读文件并继续")


def _curation_step(edition: Edition) -> dict[str, Any]:
    work = edition.work
    paths = ReadingPathItem.objects.filter(work=work).values("reading_path_id").distinct().count()
    overrides = RecommendationOverride.objects.filter(work=work, active=True).count()
    issues = []
    if not paths:
        issues.append(_issue("reading_path_missing", "尚未加入阅读路径，可选择暂不策展。", "curation"))
    return _confirmed_step(
        edition,
        "curation",
        "策展定位",
        issues,
        f"阅读路径 {paths} 条 · 推荐规则 {overrides} 条",
        "确认策展或暂不策展",
    )


def publication_issue_target(message: str) -> tuple[str, str]:
    if any(token in message for token in ("原始 PDF", "阅读锚点文件", "云端阅读副本")):
        return "file", "validation"
    if "题名" in message:
        return "work", "title"
    if "语言" in message:
        return "work", "language"
    if "出版或完成年份" in message:
        return "bibliography", "publication_year"
    if "图书出版者" in message:
        return "bibliography", "publisher"
    if "期刊名" in message:
        return "bibliography", "journal_title"
    if "学位授予单位" in message:
        return "bibliography", "degree_institution"
    if "学位类型" in message:
        return "bibliography", "degree_type"
    if "研究报告责任机构" in message:
        return "bibliography", "report_institution"
    if any(token in message for token in ("OCR", "页码", "语义索引", "全文索引")):
        return "reader", ""
    if "人工复核" in message:
        return "contributors", ""
    return "bibliography", ""


def _publication_step(edition: Edition) -> tuple[dict[str, Any], dict[str, list[str]]]:
    from ingestion.services.publication import publication_preflight

    preflight = publication_preflight(edition)
    issues = []
    for index, message in enumerate(preflight["blockers"], start=1):
        target_step, target_field = publication_issue_target(message)
        issues.append(
            _issue(
                f"publication_blocker_{index}",
                message,
                target_step,
                severity="blocker",
                field=target_field,
            )
        )
    for index, message in enumerate(preflight["warnings"], start=1):
        target_step, target_field = publication_issue_target(message)
        issues.append(
            _issue(
                f"publication_warning_{index}",
                message,
                target_step,
                field=target_field,
            )
        )
    if edition.state == PublicationState.PUBLISHED:
        status = "complete"
        action = "管理已发布版本"
    elif preflight["blockers"]:
        status = "blocked"
        action = "定位必须解决的问题"
    elif preflight["warnings"]:
        status = "attention"
        action = "检查警告并发布"
    else:
        status = "available"
        action = "发布馆藏"
    summary = f"必须解决 {len(preflight['blockers'])} · 建议处理 {len(preflight['warnings'])} · 后台任务 {len(preflight['background_tasks'])}"
    return _step_payload("publication", "发布检查与上架", status, issues, summary, action), preflight


def build_edition_workflow(edition: Edition, *, upload_item: UploadItem | None = None) -> dict[str, Any]:
    edition = (
        Edition.objects.select_related("work")
        .prefetch_related("workflow_decisions")
        .get(pk=edition.pk)
    )
    steps = [
        _file_step(upload_item, edition),
        _work_step(edition),
        _bibliography_step(edition),
        _contributors_step(edition),
        _classification_step(edition),
        _knowledge_step(edition),
        _reader_step(edition),
        _curation_step(edition),
    ]
    publication, preflight = _publication_step(edition)
    steps.append(publication)
    unresolved = [row for row in steps if row["status"] not in {"complete", "skipped"}]
    current_step = unresolved[0]["key"] if unresolved else "publication"
    current_index = next(index for index, row in enumerate(steps) if row["key"] == current_step)
    suggested_next = next(
        (row["key"] for row in steps[current_index + 1 :] if row["status"] not in {"complete", "skipped"}),
        None,
    )
    blockers_count = sum(
        issue["severity"] == "blocker"
        for step in steps
        for issue in step["issues"]
    )
    warnings_count = sum(
        issue["severity"] == "warning"
        for step in steps
        for issue in step["issues"]
    )
    if edition.state == PublicationState.PUBLISHED:
        overall_status = "published"
    elif any(row["status"] == "blocked" for row in steps):
        overall_status = "blocked"
    elif any(row["status"] == "working" for row in steps):
        overall_status = "working"
    elif warnings_count:
        overall_status = "attention"
    elif unresolved:
        overall_status = "draft"
    else:
        overall_status = "complete"
    return {
        "overall_status": overall_status,
        "current_step": current_step,
        "suggested_next_step": suggested_next,
        "steps": steps,
        "unresolved_count": blockers_count + warnings_count,
        "warnings_count": warnings_count,
        "blockers_count": blockers_count,
        "publication_preflight": preflight,
    }


def build_intake_workflow(item: UploadItem) -> dict[str, Any]:
    item = UploadItem.objects.select_related("edition__work").get(pk=item.pk)
    if item.edition_id is None:
        file_issues = []
        block_reason = initial_ingestion_block_reason(item)
        staging_waiting = is_r2_pre_import_block(block_reason)
        if block_reason and block_reason != "staging_not_ready":
            file_issues.append(
                _issue(
                    block_reason,
                    initial_ingestion_block_message(block_reason),
                    "file",
                    severity="blocker",
                )
            )
        if item.status == UploadItem.Status.FAILED and not staging_waiting:
            file_issues.append(
                _issue(
                    item.error_code or "upload_failed",
                    item.error_message or "文件处理失败。",
                    "file",
                    severity="blocker",
                )
            )
        file_status = "blocked" if file_issues else "working"
        file_summary = (
            f"{item.source_filename} · {item.get_staging_status_display()}"
            if staging_waiting
            else item.source_filename
        )
        steps = [
            _step_payload("file", "文件与识别", file_status, file_issues, file_summary, "等待或重试文件处理")
        ]
        steps.extend(
            _step_payload(key, label, "pending", [], "等待建立作品与版本记录。", "查看前置条件")
            for key, label in WORKFLOW_STEPS[1:]
        )
        blockers = len(file_issues)
        return {
            "overall_status": "blocked" if blockers else "working",
            "current_step": "file",
            "suggested_next_step": "work",
            "steps": steps,
            "unresolved_count": blockers,
            "warnings_count": 0,
            "blockers_count": blockers,
            "publication_preflight": {"blockers": ["文献记录尚未建立"], "warnings": [], "background_tasks": []},
        }
    return build_edition_workflow(item.edition, upload_item=item)


def _serialize_work(edition: Edition) -> dict[str, Any]:
    work = edition.work
    return {
        "id": str(work.id),
        "document_type": work.document_type,
        "title": work.title,
        "subtitle": work.subtitle,
        "original_title": work.original_title,
        "uniform_title": work.uniform_title,
        "language": work.language,
        "original_language": work.original_language,
        "first_publication_date": work.first_publication_date,
        "translation_of": str(work.translation_of_id) if work.translation_of_id else None,
        "abstract": work.abstract,
        "updated_at": work.updated_at,
    }


def _serialize_bibliography(edition: Edition) -> dict[str, Any]:
    return {
        "id": str(edition.id),
        **{field: getattr(edition, field) for field in BIBLIOGRAPHY_FIELDS},
        "state": edition.state,
        "public_slug": edition.public_slug,
        "is_primary": edition.is_primary,
        "updated_at": edition.updated_at,
    }


def _serialize_candidates(edition: Edition) -> dict[str, Any]:
    metadata_rows = []
    metadata = (
        MetadataCandidate.objects.filter(upload_item__edition=edition)
        .select_related("upload_item")
        .prefetch_related("evidence_records")
        .order_by("field_name", "-confidence", "created_at")
    )
    for row in metadata:
        metadata_rows.append(
            {
                "id": str(row.id),
                "upload_item_id": str(row.upload_item_id),
                "field_name": row.field_name,
                "value": row.value,
                "source": row.source,
                "confidence": row.confidence,
                "lifecycle": row.lifecycle,
                "selected": row.selected,
                "is_locked": row.is_locked,
                "conflicts": row.conflict_group,
                "evidence": list(
                    row.evidence_records.values(
                        "id",
                        "asset_id",
                        "page_number",
                        "text_quote",
                        "source_kind",
                        "external_identifier",
                    )
                ),
            }
        )
    entity_rows = list(
        EntityResolutionCandidate.objects.filter(upload_item__edition=edition)
        .order_by("target_type", "source_name", "-match_score", "created_at")
        .values(
            "id",
            "upload_item_id",
            "target_type",
            "source_name",
            "candidate_entity_type",
            "candidate_entity_id",
            "label",
            "match_score",
            "match_reasons",
            "conflicts",
            "preview_data",
            "status",
        )
    )
    enrichment_rows = list(
        EnrichmentCandidate.objects.filter(
            Q(target_type=EnrichmentCandidate.TargetType.WORK, target_id=edition.work_id)
            | Q(target_type=EnrichmentCandidate.TargetType.EDITION, target_id=edition.id)
        )
        .prefetch_related("evidence_records")
        .order_by("field_name", "-confidence", "created_at")
        .values(
            "id",
            "target_type",
            "target_id",
            "field_name",
            "candidate_kind",
            "proposed_value",
            "current_value",
            "source_class",
            "confidence",
            "conflicts",
            "identity_status",
            "status",
        )
    )
    theory_rows = list(
        TheoryReviewTask.objects.filter(work=edition.work)
        .order_by("-confidence", "created_at")
        .values(
            "id",
            "task_type",
            "candidate_node_id",
            "suggested_node_name",
            "suggested_relation_type",
            "confidence",
            "evidence_pages",
            "evidence_text",
            "status",
        )
    )
    return {
        "metadata": metadata_rows,
        "entities": entity_rows,
        "enrichment": enrichment_rows,
        "theory": theory_rows,
    }


def _serialize_upload_file(item: UploadItem) -> dict[str, Any]:
    preflight = dict(item.preflight_summary or {})
    block_reason = initial_ingestion_block_reason(item)
    staging_owns_status = is_r2_pre_import_block(block_reason)
    can_retry = block_reason == "staging_import_failed" or (
        not staging_owns_status and item.status == UploadItem.Status.FAILED
    )
    return {
        "id": str(item.id),
        "source_filename": item.source_filename,
        "filename": item.source_filename,
        "status": item.staging_status if staging_owns_status else item.status,
        "ingestion_status": item.status,
        "workflow_state": item.workflow_state,
        "stage_progress": item.stage_progress,
        "error_code": (
            item.staging_error_code if staging_owns_status else item.error_code
        ),
        "error_message": (
            item.staging_error_message if staging_owns_status else item.error_message
        ),
        "preflight_summary": preflight,
        "validation": preflight.get("mime_type") or "pending",
        "page_count": preflight.get("page_count") or 0,
        "text_profile": preflight.get("text_profile") or "",
        "ocr_strategy": preflight.get("ocr_strategy") or item.batch.ocr_strategy,
        "exact_duplicate": bool(preflight.get("exact_duplicate")),
        "staging_backend": item.staging_backend,
        "staging_status": item.staging_status,
        "staging_block_reason": block_reason,
        "can_retry": can_retry,
        "retry_label": "重新导入" if block_reason == "staging_import_failed" else "重试",
        "can_resume": False,
        "can_replace": False,
    }


def _workspace_data(edition: Edition, item: UploadItem | None, workflow: dict[str, Any]) -> dict[str, Any]:
    work = edition.work
    contributions = list(
        edition.contributions.select_related("person")
        .order_by("order", "created_at")
        .values(
            "id",
            "person_id",
            "person__preferred_name",
            "person__authority_status",
            "role",
            "order",
            "approved",
            "source",
        )
    )
    disciplines = list(
        work.discipline_relations.select_related("discipline")
        .order_by("-is_primary", "discipline__name")
        .values(
            "id",
            "discipline_id",
            "discipline__name",
            "is_primary",
            "review_status",
            "evidence_page",
            "evidence_printed_label",
            "evidence_text",
        )
    )
    subdisciplines = list(
        work.subdiscipline_relations.select_related("subdiscipline")
        .order_by("-is_primary", "subdiscipline__name")
        .values(
            "id",
            "subdiscipline_id",
            "subdiscipline__name",
            "is_primary",
            "strength",
            "review_status",
            "evidence_page",
            "evidence_printed_label",
            "evidence_text",
        )
    )
    legacy_relations = list(
        work.knowledge_relations.select_related("theory_school", "topic", "concept")
        .order_by("kind", "-is_primary", "id")
        .values(
            "id",
            "kind",
            "theory_school_id",
            "theory_school__name",
            "topic_id",
            "topic__name",
            "concept_id",
            "concept__name",
            "role",
            "strength",
            "is_primary",
            "approved",
            "review_status",
            "evidence_asset_id",
            "evidence_page",
            "evidence_printed_label",
            "evidence_text",
        )
    )
    node_relations = list(
        work.node_relations.select_related("node")
        .order_by("role", "node__canonical_name_zh")
        .values(
            "id",
            "node_id",
            "node__canonical_name_zh",
            "node__node_type",
            "role",
            "strength",
            "is_primary",
            "confidence",
            "status",
            "source",
        )
    )
    assets = list(
        edition.assets.order_by("kind", "-version", "created_at").values(
            "id",
            "kind",
            "original_filename",
            "mime_type",
            "byte_size",
            "page_count",
            "text_layer_quality",
            "access_status",
            "status",
            "validation_status",
            "validation_details",
            "is_current",
            "version",
        )
    )
    reading_paths = list(
        ReadingPathItem.objects.filter(work=work)
        .select_related("reading_path", "stage")
        .order_by("reading_path__sort_order", "stage__position", "position", "created_at")
        .values(
            "id",
            "reading_path_id",
            "reading_path__title",
            "reading_path__status",
            "stage_id",
            "stage__name",
            "stage_name",
            "recommendation_reason",
            "position",
            "reading_order",
            "is_required",
            "editorial_note",
        )
    )
    recommendations = list(
        RecommendationOverride.objects.filter(work=work)
        .select_related("policy")
        .order_by("policy__placement", "position", "created_at")
        .values(
            "id",
            "policy_id",
            "policy__placement",
            "policy__title",
            "action",
            "position",
            "active",
            "note",
        )
    )
    return {
        "file": {
            "item": _serialize_upload_file(item) if item else None,
            "assets": assets,
        },
        "work": _serialize_work(edition),
        "bibliography": _serialize_bibliography(edition),
        "contributors": contributions,
        "classification": {
            "disciplines": disciplines,
            "subdisciplines": subdisciplines,
        },
        "knowledge": {
            "relations": legacy_relations,
            "node_relations": node_relations,
        },
        "reader": {
            "reader_rendition_policy": edition.reader_rendition_policy,
            "ocr_status": edition.ocr_status,
            "page_label_status": edition.page_label_status,
            "semantic_index_status": edition.semantic_index_status,
            "search_indexed_at": edition.search_indexed_at,
            "assets": assets,
        },
        "curation": {
            "reading_paths": reading_paths,
            "recommendations": recommendations,
        },
        "publication": {
            "state": edition.state,
            "published_at": edition.published_at,
            "first_published_at": edition.first_published_at,
            "last_published_at": edition.last_published_at,
            "preflight": workflow["publication_preflight"],
        },
        "revisions": {
            "work_updated_at": work.updated_at,
            "edition_updated_at": edition.updated_at,
            "section_fingerprints": {
                key: step_fingerprint(edition, key)
                for key in EditionWorkflowDecision.Step.values
            },
        },
    }


def _workspace_queue(item: UploadItem | None) -> dict[str, Any]:
    scope = UploadItem.objects.filter(
        status__in=[
            UploadItem.Status.NEEDS_REVIEW,
            UploadItem.Status.READY,
            UploadItem.Status.FAILED,
        ]
    ).exclude(status=UploadItem.Status.DELETED)
    if item is not None:
        scope = scope.exclude(pk=item.pk)
    next_item = scope.select_related("edition__work").order_by("-priority", "created_at").first()
    return {
        "pending_count": scope.count(),
        "next_item": (
            {
                "item_id": str(next_item.id),
                "title": next_item.edition.work.title if next_item.edition_id else next_item.source_filename,
                "source_filename": next_item.source_filename,
            }
            if next_item
            else None
        ),
    }


def build_workspace_payload(
    edition: Edition,
    *,
    mode: str,
    upload_item: UploadItem | None = None,
    permissions: dict[str, bool] | None = None,
) -> dict[str, Any]:
    edition = Edition.objects.select_related("work").get(pk=edition.pk)
    workflow = build_edition_workflow(edition, upload_item=upload_item)
    return {
        "mode": mode,
        "context": {
            "item_id": str(upload_item.id) if upload_item else None,
            "work_id": str(edition.work_id),
            "edition_id": str(edition.id),
            "title": edition.work.title,
            "document_type": edition.work.document_type,
            "publication_state": edition.state,
            "updated_at": edition.updated_at,
        },
        "workflow": workflow,
        "data": _workspace_data(edition, upload_item, workflow),
        "candidates": _serialize_candidates(edition),
        "permissions": permissions or {},
        "queue": _workspace_queue(upload_item),
    }


def build_intake_workspace_payload(
    item: UploadItem,
    *,
    permissions: dict[str, bool] | None = None,
) -> dict[str, Any]:
    item = UploadItem.objects.select_related("edition__work").get(pk=item.pk)
    if item.edition_id is None:
        return {
            "mode": "intake",
            "context": {
                "item_id": str(item.id),
                "work_id": None,
                "edition_id": None,
                "title": item.source_filename,
                "document_type": item.document_type_hint,
                "publication_state": None,
                "updated_at": item.updated_at,
            },
            "workflow": build_intake_workflow(item),
            "data": {
                "file": {
                    "item": _serialize_upload_file(item),
                    "assets": [],
                }
            },
            "candidates": {
                "metadata": [],
                "entities": [],
                "enrichment": [],
                "theory": [],
            },
            "permissions": permissions or {},
            "queue": _workspace_queue(item),
        }
    return build_workspace_payload(
        item.edition,
        mode="intake",
        upload_item=item,
        permissions=permissions,
    )


def _queue_row(item: UploadItem) -> dict[str, Any]:
    workflow = build_intake_workflow(item)
    current = next(
        (row for row in workflow["steps"] if row["key"] == workflow["current_step"]),
        None,
    )
    return {
        "item_id": str(item.id),
        "title": item.edition.work.title if item.edition_id else item.source_filename,
        "source_filename": item.source_filename,
        "document_type": item.edition.work.document_type if item.edition_id else item.document_type_hint,
        "current_step": workflow["current_step"],
        "current_step_label": current["label"] if current else "",
        "overall_status": workflow["overall_status"],
        "unresolved_count": workflow["unresolved_count"],
        "warnings_count": workflow["warnings_count"],
        "blockers_count": workflow["blockers_count"],
        "updated_at": item.updated_at,
    }


def workflow_queue_payload(*, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    queryset = (
        UploadItem.objects.select_related("edition__work")
        .exclude(status__in=[UploadItem.Status.DELETED, UploadItem.Status.WITHDRAWN])
        .order_by("-priority", "-updated_at")[:limit]
    )
    rows = [_queue_row(item) for item in queryset]
    continue_items = [row for row in rows if row["overall_status"] not in {"published"}][:12]
    attention_items = [row for row in rows if row["warnings_count"] and not row["blockers_count"]][:12]
    exception_items = [row for row in rows if row["blockers_count"]][:12]
    publication_ready = [
        row
        for row in rows
        if row["current_step"] == "publication" and row["blockers_count"] == 0
    ][:12]
    candidate_review_count = (
        MetadataCandidate.objects.filter(lifecycle=MetadataCandidate.Lifecycle.PROPOSED).count()
        + EntityResolutionCandidate.objects.filter(status=EntityResolutionCandidate.Status.PROPOSED).count()
        + TheoryReviewTask.objects.filter(status=TheoryReviewTask.TaskStatus.PENDING).count()
        + EnrichmentCandidate.objects.filter(status=EnrichmentCandidate.Status.PENDING).count()
    )
    return {
        "continue_items": continue_items,
        "attention_items": attention_items,
        "exception_items": exception_items,
        "exceptions": exception_items,
        "publication_ready": publication_ready,
        "recent_items": rows[:12],
        "candidate_review_count": candidate_review_count,
    }


def work_library_payload(*, query: str = "", document_type: str = "", state: str = "", limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    queryset = Edition.objects.select_related("work").prefetch_related(
        "contributions__person",
        "assets",
        "work__knowledge_relations",
        "work__node_relations",
        "work__reading_path_items",
    )
    if query:
        queryset = queryset.filter(
            Q(work__title__icontains=query)
            | Q(work__original_title__icontains=query)
            | Q(contributions__person__preferred_name__icontains=query)
        )
    if document_type:
        queryset = queryset.filter(work__document_type=document_type)
    if state:
        queryset = queryset.filter(state=state)
    edition_ids = (
        queryset.order_by("work_id", "-is_primary", "-publication_year", "-updated_at")
        .values_list("id", flat=True)
        .distinct()
    )
    editions = list(
        Edition.objects.filter(id__in=list(edition_ids[:limit]))
        .select_related("work")
        .prefetch_related("contributions__person", "assets")
        .order_by("work__title", "-is_primary", "-publication_year")
    )
    primary_by_work: dict[Any, Edition] = {}
    for edition in editions:
        primary_by_work.setdefault(edition.work_id, edition)
    rows = []
    for work_id, edition in primary_by_work.items():
        work = edition.work
        contributors = [
            row.person.preferred_name
            for row in edition.contributions.all()
            if row.approved
        ]
        current_assets = [row for row in edition.assets.all() if row.is_current]
        asset_state = "ready" if any(row.status == Asset.Status.READY for row in current_assets) else "attention"
        knowledge_count = work.knowledge_relations.filter(approved=True).count()
        knowledge_count += work.node_relations.filter(status=KnowledgePublicationStatus.PUBLISHED).count()
        rows.append(
            {
                "work_id": str(work_id),
                "title": work.title,
                "document_type": work.document_type,
                "language": work.language,
                "contributors": contributors,
                "edition_count": work.editions.count(),
                "primary_edition_id": str(edition.id),
                "publication_state": edition.state,
                "asset_state": asset_state,
                "knowledge_status": "complete" if knowledge_count else "attention",
                "curation_status": "complete" if work.reading_path_items.exists() else "draft",
                "updated_at": max(work.updated_at, edition.updated_at),
            }
        )
    return {"count": len(rows), "results": rows}
