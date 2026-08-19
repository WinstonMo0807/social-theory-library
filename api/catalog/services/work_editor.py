from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from catalog.models import (
    Asset,
    Contribution,
    Discipline,
    Edition,
    EditionWorkflowDecision,
    KnowledgeNode,
    KnowledgePublicationStatus,
    Person,
    RelationReviewStatus,
    ReviewStatus,
    Subdiscipline,
    TheoryReviewTask,
    TheorySchool,
    Topic,
    Work,
    WorkDisciplineRelation,
    WorkKnowledgeRelation,
    WorkNodeRelation,
    WorkSubdisciplineRelation,
)
from ingestion.models import EntityResolutionCandidate, FieldLock, UploadItem
from ingestion.services.candidate_decisions import accept_candidates_from_review
from ingestion.services.files import canonical_pdf_filename

from .admin_workflow import BIBLIOGRAPHY_FIELDS, WORK_FIELDS, record_step_decision


class WorkflowEditError(ValueError):
    pass


class WorkflowEditConflict(WorkflowEditError):
    pass


@dataclass(frozen=True, slots=True)
class WorkflowSectionResult:
    edition: Edition
    decision: EditionWorkflowDecision


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _as_datetime(value):
    if value is None or hasattr(value, "tzinfo"):
        return value
    return parse_datetime(str(value))


def _check_expected(actual, expected, label: str) -> None:
    expected = _as_datetime(expected)
    if expected is not None and actual != expected:
        raise WorkflowEditConflict(f"{label}已被其他操作更新，请刷新后重试。")


def _require_all(model, identifiers, label: str) -> dict:
    identifiers = list(dict.fromkeys(identifiers))
    rows = model.objects.in_bulk(identifiers)
    missing = [str(identifier) for identifier in identifiers if identifier not in rows]
    if missing:
        raise WorkflowEditError(f"{label}包含不存在的对象：{', '.join(missing)}")
    return rows


def _approved_author_names(edition: Edition) -> list[str]:
    return list(
        edition.contributions.filter(
            role=Contribution.Role.AUTHOR,
            approved=True,
        )
        .order_by("order", "created_at")
        .values_list("person__preferred_name", flat=True)
    )


def _refresh_edition_metadata(edition: Edition) -> None:
    work = edition.work
    authors = _approved_author_names(edition)
    edition.canonical_filename = canonical_pdf_filename(
        work.title,
        authors,
        edition.publication_year,
    )
    edition.citation_data = {
        "id": str(edition.id),
        "type": {
            "book": "book",
            "journal_article": "article-journal",
            "thesis": "thesis",
            "report": "report",
        }[work.document_type],
        "title": work.title,
        "author": [{"literal": name} for name in authors],
        "issued": {"date-parts": [[edition.publication_year]]} if edition.publication_year else {},
        "publisher": edition.publisher,
        "container-title": edition.journal_title,
        "volume": edition.volume,
        "issue": edition.issue,
        "page": edition.page_range,
        "DOI": edition.doi,
        "ISBN": edition.isbn13 or edition.isbn10 or edition.isbn,
    }
    checks = [
        bool(work.title.strip()),
        bool(authors),
        bool(edition.publication_year),
        bool(edition.citation_data),
        bool(edition.canonical_filename),
    ]
    if work.document_type == "book":
        checks.append(bool(edition.publisher.strip()))
    elif work.document_type == "journal_article":
        checks.append(bool(edition.journal_title.strip()))
    elif work.document_type == "thesis":
        checks.extend([bool(edition.degree_institution.strip()), bool(edition.degree_type.strip())])
    elif work.document_type == "report":
        checks.append(bool(edition.report_institution.strip() or edition.publisher.strip()))
    edition.review_progress = round(sum(checks) / len(checks) * 100)
    edition.review_status = (
        ReviewStatus.COMPLETED
        if edition.review_progress == 100
        else ReviewStatus.IN_PROGRESS
    )


def _save_work(edition: Edition, values: dict[str, Any]) -> None:
    work = edition.work
    translation_marker = object()
    translation_id = values.pop("translation_of", translation_marker)
    editable = {field for field in WORK_FIELDS if not field.endswith("_id")}
    for field in editable:
        if field in values:
            setattr(work, field, values[field])
    if translation_id is not translation_marker:
        if translation_id is None:
            work.translation_of = None
        else:
            target = Work.objects.select_for_update().filter(pk=translation_id).first()
            if target is None:
                raise WorkflowEditError("原作 Work 不存在。")
            if target.pk == work.pk:
                raise WorkflowEditError("作品不能把自身设为原作。")
            work.translation_of = target
    if not work.title.strip():
        raise WorkflowEditError("作品题名不能为空。")
    work.clean()
    work.save()
    edition.work = work
    _refresh_edition_metadata(edition)


def _save_bibliography(edition: Edition, values: dict[str, Any]) -> None:
    for field in BIBLIOGRAPHY_FIELDS:
        if field in values:
            setattr(edition, field, values[field])
    _refresh_edition_metadata(edition)


def _save_contributors(edition: Edition, values: dict[str, Any], actor) -> None:
    pending = EntityResolutionCandidate.objects.select_for_update().filter(
        upload_item__edition=edition,
        target_type="person",
        status=EntityResolutionCandidate.Status.PROPOSED,
    )
    if pending.exists():
        raise WorkflowEditError("仍有责任者候选未决定，请先关联、创建草稿、保留未解析或拒绝。")
    rows = values.get("contributors", [])
    people = _require_all(Person, [row["person_id"] for row in rows], "责任者")
    edition.contributions.select_for_update().all().delete()
    Contribution.objects.bulk_create(
        [
            Contribution(
                edition=edition,
                person=people[row["person_id"]],
                role=row["role"],
                order=row.get("order", index),
                source="workflow_section_confirmation",
                confidence=1,
                approved=True,
            )
            for index, row in enumerate(rows)
        ]
    )
    _refresh_edition_metadata(edition)


def _reject_unselected_relations(queryset, selected_ids: set, id_field: str, actor) -> None:
    now = timezone.now()
    for relation in queryset:
        if getattr(relation, id_field) in selected_ids:
            continue
        if relation.review_status == RelationReviewStatus.SUGGESTED:
            relation.review_status = RelationReviewStatus.REJECTED
            relation.reviewed_by = actor
            relation.reviewed_at = now
            if hasattr(relation, "approved"):
                relation.approved = False
            relation.save()
        else:
            relation.delete()


def _save_classification(edition: Edition, values: dict[str, Any], actor) -> None:
    work = edition.work
    discipline_rows = values.get("disciplines", [])
    subdiscipline_rows = values.get("subdisciplines", [])
    disciplines = _require_all(Discipline, [row["id"] for row in discipline_rows], "学科")
    subdisciplines = _require_all(Subdiscipline, [row["id"] for row in subdiscipline_rows], "子学科")
    selected_disciplines = set(disciplines)
    selected_subdisciplines = set(subdisciplines)
    _reject_unselected_relations(
        list(work.discipline_relations.select_for_update()),
        selected_disciplines,
        "discipline_id",
        actor,
    )
    _reject_unselected_relations(
        list(work.subdiscipline_relations.select_for_update()),
        selected_subdisciplines,
        "subdiscipline_id",
        actor,
    )
    now = timezone.now()
    for row in discipline_rows:
        WorkDisciplineRelation.objects.update_or_create(
            work=work,
            discipline=disciplines[row["id"]],
            defaults={
                "is_primary": row.get("is_primary", False),
                "source": "workflow_section_confirmation",
                "confidence": 1,
                "evidence_page": row.get("evidence_page"),
                "evidence_printed_label": row.get("evidence_printed_label", ""),
                "evidence_text": row.get("evidence_text", ""),
                "review_status": RelationReviewStatus.APPROVED,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )
    for row in subdiscipline_rows:
        WorkSubdisciplineRelation.objects.update_or_create(
            work=work,
            subdiscipline=subdisciplines[row["id"]],
            defaults={
                "is_primary": row.get("is_primary", False),
                "strength": row.get("strength", "medium"),
                "source": "workflow_section_confirmation",
                "confidence": 1,
                "evidence_page": row.get("evidence_page"),
                "evidence_printed_label": row.get("evidence_printed_label", ""),
                "evidence_text": row.get("evidence_text", ""),
                "review_status": RelationReviewStatus.APPROVED,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )


def _save_knowledge(edition: Edition, values: dict[str, Any], actor) -> None:
    work = edition.work
    theory_rows = values.get("theories", [])
    topic_rows = values.get("topics", [])
    node_rows = values.get("nodes", [])
    theories = _require_all(TheorySchool, [row["id"] for row in theory_rows], "理论传统")
    topics = _require_all(Topic, [row["id"] for row in topic_rows], "主题")
    nodes = _require_all(KnowledgeNode, [row["id"] for row in node_rows], "知识节点")
    assets = _require_all(
        Asset,
        [row["evidence_asset"] for row in [*theory_rows, *topic_rows] if row.get("evidence_asset")],
        "证据文件",
    )
    now = timezone.now()

    existing_theories = list(
        work.knowledge_relations.select_for_update().filter(
            kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
        )
    )
    _reject_unselected_relations(existing_theories, set(theories), "theory_school_id", actor)
    for row in theory_rows:
        WorkKnowledgeRelation.objects.update_or_create(
            work=work,
            kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
            theory_school=theories[row["id"]],
            defaults={
                "source": "workflow_section_confirmation",
                "confidence": 1,
                "approved": True,
                "is_primary": row.get("is_primary", False),
                "role": row["role"],
                "strength": row["strength"],
                "evidence_asset": assets.get(row.get("evidence_asset")),
                "evidence_page": row.get("evidence_page"),
                "evidence_printed_label": row.get("evidence_printed_label", ""),
                "evidence_text": row.get("evidence_text", ""),
                "review_status": RelationReviewStatus.APPROVED,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )

    existing_topics = list(
        work.knowledge_relations.select_for_update().filter(
            kind=WorkKnowledgeRelation.Kind.TOPIC,
        )
    )
    _reject_unselected_relations(existing_topics, set(topics), "topic_id", actor)
    for row in topic_rows:
        WorkKnowledgeRelation.objects.update_or_create(
            work=work,
            kind=WorkKnowledgeRelation.Kind.TOPIC,
            topic=topics[row["id"]],
            defaults={
                "source": "workflow_section_confirmation",
                "confidence": 1,
                "approved": True,
                "is_primary": row.get("is_primary", False),
                "evidence_asset": assets.get(row.get("evidence_asset")),
                "evidence_page": row.get("evidence_page"),
                "evidence_printed_label": row.get("evidence_printed_label", ""),
                "evidence_text": row.get("evidence_text", ""),
                "review_status": RelationReviewStatus.APPROVED,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )

    selected_node_keys = {(row["id"], row["role"]) for row in node_rows}
    for relation in work.node_relations.select_for_update():
        if (relation.node_id, relation.role) in selected_node_keys:
            continue
        if relation.status in {KnowledgePublicationStatus.PENDING, KnowledgePublicationStatus.DRAFT}:
            relation.status = KnowledgePublicationStatus.REJECTED
            relation.reviewed_by = actor
            relation.reviewed_at = now
            relation.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        else:
            relation.delete()
    for row in node_rows:
        WorkNodeRelation.objects.update_or_create(
            work=work,
            node=nodes[row["id"]],
            role=row["role"],
            defaults={
                "is_primary": row.get("is_primary", False),
                "strength": row["strength"],
                "confidence": 1,
                "status": KnowledgePublicationStatus.PUBLISHED,
                "source": "workflow_section_confirmation",
                "created_by": actor,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )
    selected_node_ids = set(nodes)
    TheoryReviewTask.objects.select_for_update().filter(
        work=work,
        candidate_node_id__in=selected_node_ids,
        status__in=[TheoryReviewTask.TaskStatus.PENDING, TheoryReviewTask.TaskStatus.NEEDS_CHANGES],
    ).update(
        status=TheoryReviewTask.TaskStatus.CONFIRMED,
        reviewed_at=now,
        updated_at=now,
    )
    TheoryReviewTask.objects.select_for_update().filter(
        work=work,
        status__in=[TheoryReviewTask.TaskStatus.PENDING, TheoryReviewTask.TaskStatus.NEEDS_CHANGES],
    ).exclude(candidate_node_id__in=selected_node_ids).update(
        status=TheoryReviewTask.TaskStatus.REJECTED,
        reviewed_at=now,
        updated_at=now,
    )


def _save_reader(edition: Edition, values: dict[str, Any]) -> None:
    if "reader_rendition_policy" in values:
        edition.reader_rendition_policy = values["reader_rendition_policy"]


def _record_section_locks(edition: Edition, step_key: str, values: dict[str, Any], actor) -> None:
    fields_by_step = {
        "work": {field for field in WORK_FIELDS if not field.endswith("_id")} | {"translation_of"},
        "bibliography": set(BIBLIOGRAPHY_FIELDS),
        "contributors": {"contributors"},
        "classification": {"disciplines", "subdisciplines"},
        "knowledge": {"theories", "topics", "nodes"},
        "reader": {"reader_rendition_policy"},
    }
    for field_name in fields_by_step.get(step_key, set()).intersection(values):
        locked_value = _json_safe(values[field_name])
        if locked_value is None:
            locked_value = {"confirmed_null": True}
        FieldLock.objects.update_or_create(
            edition=edition,
            field_name=field_name,
            defaults={
                "locked_by": actor,
                "locked_value": locked_value,
                "reason": f"2.8 馆藏工作流确认 {step_key}",
            },
        )


def _accept_matching_metadata_candidates(
    edition: Edition,
    step_key: str,
    values: dict[str, Any],
    actor,
) -> None:
    if step_key not in {"work", "bibliography"}:
        return
    item = UploadItem.objects.filter(edition=edition).order_by("-updated_at", "-created_at").first()
    if item is None:
        return
    accepted_fields = {
        field for field in values if field not in {"expected_updated_at", "expected_work_updated_at", "note"}
    }
    accept_candidates_from_review(
        item,
        values,
        actor=actor,
        locked_fields=accepted_fields,
    )


@transaction.atomic
def save_workflow_section(
    edition: Edition,
    step_key: str,
    values: dict[str, Any],
    *,
    actor,
) -> WorkflowSectionResult:
    if step_key not in {
        "work",
        "bibliography",
        "contributors",
        "classification",
        "knowledge",
        "reader",
        "curation",
    }:
        raise WorkflowEditError("该步骤不能通过编辑接口保存。")
    edition = (
        Edition.objects.select_for_update(of=("self", "work"))
        .select_related("work")
        .get(pk=edition.pk)
    )
    values = dict(values)
    expected_updated_at = values.pop("expected_updated_at", None)
    expected_work_updated_at = values.pop("expected_work_updated_at", None)
    note = values.pop("note", "")
    _check_expected(edition.updated_at, expected_updated_at, "当前版本")
    _check_expected(edition.work.updated_at, expected_work_updated_at, "当前作品")

    if step_key == "work":
        _save_work(edition, values)
    elif step_key == "bibliography":
        _save_bibliography(edition, values)
    elif step_key == "contributors":
        _save_contributors(edition, values, actor)
    elif step_key == "classification":
        _save_classification(edition, values, actor)
    elif step_key == "knowledge":
        _save_knowledge(edition, values, actor)
    elif step_key == "reader":
        _save_reader(edition, values)

    edition.save()
    _record_section_locks(edition, step_key, values, actor)
    _accept_matching_metadata_candidates(edition, step_key, values, actor)
    decision_value = (
        EditionWorkflowDecision.Decision.SKIPPED
        if step_key == "curation" and values.get("skip")
        else EditionWorkflowDecision.Decision.CONFIRMED
    )
    decision = record_step_decision(
        edition,
        step_key,
        actor=actor,
        decision=decision_value,
        note=note,
    )
    return WorkflowSectionResult(edition=edition, decision=decision)


def intake_edition(item_id) -> tuple[UploadItem, Edition]:
    item = UploadItem.objects.select_related("edition__work").filter(pk=item_id).first()
    if item is None:
        raise WorkflowEditError("上架项目不存在。")
    if item.edition_id is None:
        raise WorkflowEditError("识别流程尚未建立作品和版本记录。")
    return item, item.edition


def maintenance_edition(work_id, edition_id=None) -> Edition:
    work = Work.objects.filter(pk=work_id).first()
    if work is None:
        raise WorkflowEditError("作品不存在。")
    queryset = work.editions.all()
    if edition_id:
        edition = queryset.filter(pk=edition_id).first()
    else:
        edition = queryset.order_by("-is_primary", "-publication_year", "-updated_at").first()
    if edition is None:
        raise WorkflowEditError("作品尚无可维护的版本。")
    return edition
