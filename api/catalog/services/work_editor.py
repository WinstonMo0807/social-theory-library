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
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgePublicationStatus,
    Person,
    PublisherAuthority,
    RelationReviewStatus,
    ReviewStatus,
    Subdiscipline,
    TheoryReviewTask,
    TheorySchool,
    Topic,
    Work,
    WorkDisciplineRelation,
    WorkNodeRelation,
    WorkSubdisciplineRelation,
    WorkTopicRelation,
)
from ingestion.models import EntityResolutionCandidate, FieldLock, UploadItem
from ingestion.services.candidate_decisions import accept_candidates_from_review
from ingestion.services.files import canonical_pdf_filename

from .admin_workflow import BIBLIOGRAPHY_FIELDS, WORK_FIELDS, record_step_decision
from .canonical_identity import (
    CanonicalIdentityError,
    canonical_work_node_role,
    mapped_node_for_legacy,
)


class WorkflowEditError(ValueError):
    pass


class WorkflowEditConflict(WorkflowEditError):
    pass


@dataclass(frozen=True, slots=True)
class WorkflowSectionResult:
    edition: Edition
    decision: EditionWorkflowDecision | None


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
    fetched = {
        str(identifier): value
        for identifier, value in model.objects.in_bulk(identifiers).items()
    }
    rows = {
        identifier: fetched[str(identifier)]
        for identifier in identifiers
        if str(identifier) in fetched
    }
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
        "issued": {
            "date-parts": [[
                edition.publication_date.year,
                edition.publication_date.month,
                edition.publication_date.day,
            ]]
        } if edition.publication_date else (
            {"date-parts": [[edition.publication_year]]} if edition.publication_year else {}
        ),
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
    translation_id = values.get("translation_of", translation_marker)
    editable = {
        field
        for field in WORK_FIELDS
        if not field.endswith("_id") and field != "translation_of"
    }
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
    publisher_authority_marker = object()
    publisher_authority_id = values.get(
        "publisher_authority_id",
        publisher_authority_marker,
    )
    for field in BIBLIOGRAPHY_FIELDS:
        if field in values and field != "publisher_authority_id":
            setattr(edition, field, values[field])
    if edition.publication_date:
        if values.get("publication_year") not in (None, edition.publication_date.year):
            raise WorkflowEditError("本版本出版日期与兼容出版年份不一致。")
        edition.publication_year = edition.publication_date.year
    if publisher_authority_id is not publisher_authority_marker:
        if publisher_authority_id is None:
            edition.publisher_authority = None
        else:
            publisher_authority = PublisherAuthority.objects.select_for_update().filter(
                pk=publisher_authority_id,
            ).first()
            if publisher_authority is None:
                raise WorkflowEditError("出版社 authority 不存在。")
            edition.publisher_authority = publisher_authority
            if not str(edition.publisher or "").strip():
                edition.publisher = publisher_authority.canonical_name
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


def apply_work_classification(work: Work, values: dict[str, Any], actor) -> None:
    discipline_rows = values.get("disciplines", [])
    subdiscipline_rows = values.get("subdisciplines", [])
    disciplines = _require_all(Discipline, [row["id"] for row in discipline_rows], "学科")
    subdisciplines = _require_all(Subdiscipline, [row["id"] for row in subdiscipline_rows], "子学科")
    selected_disciplines = {row.pk for row in disciplines.values()}
    selected_subdisciplines = {row.pk for row in subdisciplines.values()}
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


def _save_classification(edition: Edition, values: dict[str, Any], actor) -> None:
    apply_work_classification(edition.work, values, actor)


def apply_work_knowledge(work: Work, values: dict[str, Any], actor) -> None:
    theory_rows = values.get("theories", [])
    topic_rows = values.get("topics", [])
    node_rows = values.get("nodes", [])
    theories = _require_all(TheorySchool, [row["id"] for row in theory_rows], "理论传统")
    topics = _require_all(Topic, [row["id"] for row in topic_rows], "主题")
    nodes = _require_all(KnowledgeNode, [row["id"] for row in node_rows], "知识节点")
    assets = _require_all(
        Asset,
        [
            row["evidence_asset"]
            for row in [*theory_rows, *topic_rows, *node_rows]
            if row.get("evidence_asset")
        ],
        "证据文件",
    )
    now = timezone.now()

    mapped_theory_rows = []
    for row in theory_rows:
        try:
            node = mapped_node_for_legacy("TheorySchool", theories[row["id"]].id)
        except CanonicalIdentityError as exc:
            raise WorkflowEditError(str(exc)) from exc
        mapped_theory_rows.append(
            {**row, "node": node, "canonical_role": canonical_work_node_role(row["role"])}
        )

    existing_topics = list(work.topic_relations.select_for_update())
    _reject_unselected_relations(
        existing_topics,
        {row.pk for row in topics.values()},
        "topic_id",
        actor,
    )
    for row in topic_rows:
        WorkTopicRelation.objects.update_or_create(
            work=work,
            topic=topics[row["id"]],
            defaults={
                "source": "workflow_section_confirmation",
                "confidence": 1,
                "is_primary": row.get("is_primary", False),
                "strength": row.get("strength", "medium"),
                "evidence_asset": assets.get(row.get("evidence_asset")),
                "evidence_page": row.get("evidence_page"),
                "evidence_printed_label": row.get("evidence_printed_label", ""),
                "evidence_text": row.get("evidence_text", ""),
                "review_status": RelationReviewStatus.APPROVED,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )

    selected_node_keys = {
        (nodes[row["id"]].pk, row["role"])
        for row in node_rows
    }
    selected_node_keys.update(
        (row["node"].id, row["canonical_role"]) for row in mapped_theory_rows
    )
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
        relation, _created = WorkNodeRelation.objects.update_or_create(
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
        evidence_asset = assets.get(row.get("evidence_asset"))
        if evidence_asset and row.get("evidence_page") and row.get("evidence_text"):
            EvidenceSnippet.objects.update_or_create(
                work=work,
                file=evidence_asset,
                node=nodes[row["id"]],
                work_node_relation=relation,
                page_number=row["evidence_page"],
                defaults={
                    "page_end": row.get("evidence_page_end"),
                    "printed_page_label": row.get(
                        "evidence_printed_label", ""
                    ),
                    "quote": row["evidence_text"],
                    "extraction_method": EvidenceSnippet.ExtractionMethod.MANUAL,
                    "semantic_confidence": 1,
                    "review_status": RelationReviewStatus.APPROVED,
                    "reviewed_by": actor,
                    "reviewed_at": now,
                },
            )
    for row in mapped_theory_rows:
        relation, _created = WorkNodeRelation.objects.update_or_create(
            work=work,
            node=row["node"],
            role=row["canonical_role"],
            defaults={
                "is_primary": row.get("is_primary", False),
                "strength": row["strength"],
                "confidence": 1,
                "status": KnowledgePublicationStatus.PUBLISHED,
                "source": "workflow_legacy_identity_adapter",
                "created_by": actor,
                "reviewed_by": actor,
                "reviewed_at": now,
            },
        )
        evidence_asset = assets.get(row.get("evidence_asset"))
        if evidence_asset and row.get("evidence_page") and row.get("evidence_text"):
            EvidenceSnippet.objects.update_or_create(
                work=work,
                file=evidence_asset,
                node=row["node"],
                work_node_relation=relation,
                page_number=row["evidence_page"],
                defaults={
                    "printed_page_label": row.get("evidence_printed_label", ""),
                    "quote": row["evidence_text"],
                    "extraction_method": EvidenceSnippet.ExtractionMethod.MANUAL,
                    "semantic_confidence": 1,
                    "review_status": RelationReviewStatus.APPROVED,
                    "reviewed_by": actor,
                    "reviewed_at": now,
                },
            )
    selected_node_ids = {row.pk for row in nodes.values()} | {
        row["node"].id for row in mapped_theory_rows
    }
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


def _save_knowledge(edition: Edition, values: dict[str, Any], actor) -> None:
    apply_work_knowledge(edition.work, values, actor)


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
    if step_key not in {"work", "bibliography", "contributors"}:
        return
    item = UploadItem.objects.filter(edition=edition).order_by("-updated_at", "-created_at").first()
    if item is None:
        return
    candidate_payload = dict(values)
    accepted_fields = {
        field for field in values if field not in {"expected_updated_at", "expected_work_updated_at", "note"}
    }
    if step_key == "contributors":
        rows = [row for row in values.get("contributors", []) if isinstance(row, dict)]
        candidate_payload = {
            "authors": [
                edition.contributions.get(
                    person_id=row["person_id"],
                    role=Contribution.Role.AUTHOR,
                ).person.preferred_name
                for row in rows
                if row.get("role") == Contribution.Role.AUTHOR and row.get("person_id")
            ],
            "translators": [
                edition.contributions.get(
                    person_id=row["person_id"],
                    role=Contribution.Role.TRANSLATOR,
                ).person.preferred_name
                for row in rows
                if row.get("role") == Contribution.Role.TRANSLATOR and row.get("person_id")
            ],
        }
        accepted_fields = {
            field_name
            for field_name, names in candidate_payload.items()
            if names
        }
    accept_candidates_from_review(
        item,
        candidate_payload,
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
    confirm_section: bool = True,
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
    decision = None
    if confirm_section:
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
