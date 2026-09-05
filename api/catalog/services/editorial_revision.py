from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from catalog.models import (
    Asset,
    CanonicalObjectRevision,
    Discipline,
    Edition,
    EditorialRevision,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeNodeSubdiscipline,
    KnowledgeNodeTopic,
    KnowledgePublicationStatus,
    Person,
    PersonNameVariant,
    PublisherAuthority,
    PublicationState,
    ReadingPath,
    RelationReviewStatus,
    ScholarProfile,
    Subdiscipline,
    TheorySchool,
    Topic,
    TopicDisciplineRelation,
    TopicSubdisciplineRelation,
    TopicTheoryRelation,
    Work,
)


class EditorialRevisionError(ValueError):
    pass


class EditorialRevisionConflict(EditorialRevisionError):
    pass


@dataclass(frozen=True, slots=True)
class EditorialTargetPolicy:
    model: type
    editable_fields: frozenset[str]


TARGET_POLICIES = {
    EditorialRevision.TargetType.WORK: EditorialTargetPolicy(
        Work,
        frozenset(
            {
                "title",
                "document_type",
                "subtitle",
                "original_title",
                "uniform_title",
                "abstract",
                "cover",
                "language",
                "original_language",
                "first_publication_date",
                "translation_of",
                "search_aliases",
                "is_featured",
                "classification",
                "knowledge",
                "bibliography",
                "contributors",
                "reader",
            }
        ),
    ),
    EditorialRevision.TargetType.EDITION: EditorialTargetPolicy(
        Edition,
        frozenset(
            {
                "version_label",
                "publication_year",
                "publication_date",
                "publisher",
                "publication_place",
                "publisher_authority",
                "distribution_place",
                "distributor",
                "manufacture_place",
                "manufacturer",
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
                "citation_data",
                "reader_rendition_policy",
                "is_primary",
            }
        ),
    ),
    EditorialRevision.TargetType.KNOWLEDGE_NODE: EditorialTargetPolicy(
        KnowledgeNode,
        frozenset(
            {
                "canonical_name_zh",
                "canonical_name_en",
                "node_type",
                "slug",
                "summary",
                "definition",
                "core_questions",
                "basic_propositions",
                "theoretical_boundary",
                "start_year",
                "end_year",
                "period_label",
                "parent",
                "primary_discipline",
                "sort_order",
                "status",
                "aliases",
                "discipline_links",
                "subdiscipline_links",
                "topic_links",
            }
        ),
    ),
    EditorialRevision.TargetType.SCHOLAR_PROFILE: EditorialTargetPolicy(
        ScholarProfile,
        frozenset(
            {
                "slug",
                "short_description",
                "affiliations",
                "key_concerns",
                "timeline",
                "featured_quote",
                "quote_source",
                "curation",
                "editorial_status",
                "person",
            }
        ),
    ),
    EditorialRevision.TargetType.DISCIPLINE: EditorialTargetPolicy(
        Discipline,
        frozenset(
            {
                "code",
                "name",
                "foreign_name",
                "slug",
                "search_aliases",
                "description",
                "introduction",
                "sort_order",
                "curation_level",
                "editorial_status",
            }
        ),
    ),
    EditorialRevision.TargetType.SUBDISCIPLINE: EditorialTargetPolicy(
        Subdiscipline,
        frozenset(
            {
                "name",
                "foreign_name",
                "slug",
                "search_aliases",
                "description",
                "discipline",
                "parent",
                "research_object",
                "core_questions",
                "formation_period",
                "research_directions",
                "methods",
                "representative_issues",
                "curation_level",
                "editorial_status",
            }
        ),
    ),
    EditorialRevision.TargetType.TOPIC: EditorialTargetPolicy(
        Topic,
        frozenset(
            {
                "name",
                "slug",
                "search_aliases",
                "description",
                "problem_statement",
                "core_questions",
                "research_dimensions",
                "methods",
                "formation_context",
                "key_concepts",
                "timeline",
                "curation",
                "editorial_status",
                "discipline_relations",
                "theory_relations",
                "subdiscipline_relations",
            }
        ),
    ),
    EditorialRevision.TargetType.PUBLISHER: EditorialTargetPolicy(
        PublisherAuthority,
        frozenset(
            {
                "canonical_name",
                "aliases",
                "possible_places",
                "country",
                "valid_from",
                "valid_to",
                "notes",
            }
        ),
    ),
    EditorialRevision.TargetType.READING_PATH: EditorialTargetPolicy(
        ReadingPath,
        frozenset(
            {
                "title",
                "slug",
                "introduction",
                "learning_goal",
                "primary_discipline",
                "audience",
                "difficulty",
                "estimated_reading",
                "sort_order",
                "status",
                "stage_groups",
            }
        ),
    ),
}


SPECIAL_FIELDS = frozenset(
    {
        "aliases",
        "discipline_links",
        "subdiscipline_links",
        "topic_links",
        "classification",
        "knowledge",
        "bibliography",
        "contributors",
        "reader",
        "person",
        "stage_groups",
        "discipline_relations",
        "theory_relations",
        "subdiscipline_relations",
    }
)


def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if hasattr(value, "storage") and hasattr(value, "name"):
        return str(value.name or "")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "pk"):
        return str(value.pk)
    return str(value)


def _work_classification_snapshot(work: Work) -> dict[str, Any]:
    return {
        "disciplines": [
            {
                "id": str(row.discipline_id),
                "is_primary": row.is_primary,
                "evidence_page": row.evidence_page,
                "evidence_printed_label": row.evidence_printed_label,
                "evidence_text": row.evidence_text,
            }
            for row in work.discipline_relations.order_by(
                "-is_primary", "discipline_id", "created_at"
            )
        ],
        "subdisciplines": [
            {
                "id": str(row.subdiscipline_id),
                "is_primary": row.is_primary,
                "strength": row.strength,
                "evidence_page": row.evidence_page,
                "evidence_printed_label": row.evidence_printed_label,
                "evidence_text": row.evidence_text,
            }
            for row in work.subdiscipline_relations.order_by(
                "-is_primary", "subdiscipline_id", "created_at"
            )
        ],
    }


def _work_knowledge_snapshot(work: Work) -> dict[str, Any]:
    return {
        # Legacy TheorySchool input remains an ingestion/workflow adapter. The
        # canonical snapshot is the normalized WorkNodeRelation set.
        "theories": [],
        "topics": [
            {
                "id": str(row.topic_id),
                "is_primary": row.is_primary,
                "strength": row.strength,
                "evidence_asset": str(row.evidence_asset_id)
                if row.evidence_asset_id
                else None,
                "evidence_page": row.evidence_page,
                "evidence_printed_label": row.evidence_printed_label,
                "evidence_text": row.evidence_text,
            }
            for row in work.topic_relations.order_by(
                "-is_primary", "topic_id", "created_at"
            )
        ],
        "nodes": [
            _work_node_relation_snapshot(row)
            for row in work.node_relations.order_by(
                "-is_primary", "node_id", "role", "created_at"
            )
        ],
    }


def _work_node_relation_snapshot(relation) -> dict[str, Any]:
    evidence = relation.evidence.filter(
        review_status=RelationReviewStatus.APPROVED,
    ).order_by("page_number", "created_at").first()
    return {
        "id": str(relation.node_id),
        "role": relation.role,
        "strength": relation.strength,
        "is_primary": relation.is_primary,
        "evidence_asset": str(evidence.file_id) if evidence else None,
        "evidence_page": evidence.page_number if evidence else None,
        "evidence_page_end": evidence.page_end if evidence else None,
        "evidence_printed_label": evidence.printed_page_label if evidence else "",
        "evidence_text": evidence.quote if evidence else "",
    }


def _scholar_person_snapshot(profile: ScholarProfile) -> dict[str, Any]:
    person = profile.person
    return {
        "preferred_name": person.preferred_name,
        "original_name": person.original_name,
        "aliases": list(person.aliases or []),
        "birth_year": person.birth_year,
        "death_year": person.death_year,
        "biography": person.biography,
        "name_variants": [
            {"name": row.name, "language": row.language, "variant_type": row.variant_type,
             "source_kind": row.source_kind, "source_note": row.source_note,
             "displayable": row.displayable, "is_verified": row.is_verified}
            for row in person.name_variants.order_by("normalized_name", "pk")
        ],
    }


def topic_relation_snapshot(topic: Topic) -> dict[str, Any]:
    return {
        "discipline_relations": [
            {
                "discipline_id": str(row.discipline_id),
                "is_primary": row.is_primary,
                "review_status": row.review_status,
            }
            for row in topic.discipline_relations.order_by("discipline_id")
        ],
        "theory_relations": [
            {
                "theory_school_id": str(row.theory_school_id),
                "relation_label": row.relation_label,
                "review_status": row.review_status,
            }
            for row in topic.theory_relations.order_by("theory_school_id")
        ],
        "subdiscipline_relations": [
            {
                "subdiscipline_id": str(row.subdiscipline_id),
                "relation_label": row.relation_label,
                "review_status": row.review_status,
            }
            for row in topic.subdiscipline_relations.order_by("subdiscipline_id")
        ],
    }


def _special_snapshot(target) -> dict[str, Any]:
    if isinstance(target, Work):
        return {
            "classification": _work_classification_snapshot(target),
            "knowledge": _work_knowledge_snapshot(target),
        }
    if isinstance(target, KnowledgeNode):
        return {
            "aliases": [
                {
                    "alias": row.alias,
                    "language": row.language,
                    "alias_type": row.alias_type,
                    "source_kind": row.source_kind,
                    "is_verified": row.is_verified,
                }
                for row in target.aliases.order_by("alias", "id")
            ],
            "discipline_links": [
                {
                    "discipline_id": str(row.discipline_id),
                    "relation_type": row.relation_type,
                    "discipline_specific_summary": row.discipline_specific_summary,
                    "sort_order": row.sort_order,
                    "status": row.status,
                }
                for row in target.discipline_links.order_by(
                    "sort_order", "created_at", "id"
                )
            ],
            "subdiscipline_links": [
                {
                    "subdiscipline_id": str(row.subdiscipline_id),
                    "is_primary": row.is_primary,
                    "relation_role": row.relation_role,
                    "source": row.source,
                    "confidence": row.confidence,
                    "sort_order": row.sort_order,
                    "status": row.status,
                }
                for row in target.subdiscipline_links.order_by(
                    "sort_order", "created_at", "id"
                )
            ],
            "topic_links": [
                {
                    "topic_id": str(row.topic_id),
                    "relation_label": row.relation_label,
                    "source": row.source,
                    "confidence": row.confidence,
                    "sort_order": row.sort_order,
                    "status": row.status,
                }
                for row in target.topic_links.order_by(
                    "sort_order", "created_at", "id"
                )
            ],
        }
    if isinstance(target, ScholarProfile):
        return {"person": _scholar_person_snapshot(target)}
    if isinstance(target, Topic):
        return topic_relation_snapshot(target)
    if isinstance(target, PublisherAuthority):
        return {"aliases": list(target.aliases or [])}
    if isinstance(target, ReadingPath):
        from catalog.services.reading_paths import reading_path_stage_groups

        return {"stage_groups": reading_path_stage_groups(target)}
    return {}


def _policy(target_type: str) -> EditorialTargetPolicy:
    try:
        return TARGET_POLICIES[target_type]
    except KeyError as exc:
        raise EditorialRevisionError("该对象类型尚不支持编辑草稿。") from exc


def _missing_ids(model, identifiers, *, queryset=None) -> list[str]:
    values = {str(value) for value in identifiers if value}
    if not values:
        return []
    source = queryset if queryset is not None else model.objects.all()
    found = {str(value) for value in source.filter(pk__in=values).values_list("pk", flat=True)}
    return sorted(values - found)


def _validated_work_relation_patch(target: Work, field_name: str, value) -> dict[str, Any]:
    from catalog.workflow_serializers import (
        ClassificationSectionSerializer,
        KnowledgeSectionSerializer,
    )

    serializer_class = (
        ClassificationSectionSerializer
        if field_name == "classification"
        else KnowledgeSectionSerializer
    )
    serializer = serializer_class(data=value)
    if not serializer.is_valid():
        raise EditorialRevisionError(
            f"{field_name} 草稿无效：{serializer.errors}"
        )
    values = {
        key: row
        for key, row in serializer.validated_data.items()
        if key not in {"expected_updated_at", "expected_work_updated_at", "note"}
    }
    if field_name == "classification":
        missing = _missing_ids(
            Discipline,
            [row["id"] for row in values.get("disciplines", [])],
        )
        if missing:
            raise EditorialRevisionError(f"学科包含不存在的对象：{', '.join(missing)}")
        missing = _missing_ids(
            Subdiscipline,
            [row["id"] for row in values.get("subdisciplines", [])],
        )
        if missing:
            raise EditorialRevisionError(f"子学科包含不存在的对象：{', '.join(missing)}")
    else:
        theory_ids = [row["id"] for row in values.get("theories", [])]
        missing = _missing_ids(TheorySchool, theory_ids)
        if missing:
            raise EditorialRevisionError(f"理论传统包含不存在的对象：{', '.join(missing)}")
        if theory_ids:
            from catalog.services.canonical_identity import (
                CanonicalIdentityError,
                mapped_node_for_legacy,
            )

            for theory_id in theory_ids:
                try:
                    mapped_node_for_legacy("TheorySchool", theory_id)
                except CanonicalIdentityError as exc:
                    raise EditorialRevisionError(str(exc)) from exc
        missing = _missing_ids(
            Topic,
            [row["id"] for row in values.get("topics", [])],
        )
        if missing:
            raise EditorialRevisionError(f"主题包含不存在的对象：{', '.join(missing)}")
        missing = _missing_ids(
            KnowledgeNode,
            [row["id"] for row in values.get("nodes", [])],
        )
        if missing:
            raise EditorialRevisionError(f"知识节点包含不存在的对象：{', '.join(missing)}")
        evidence_ids = [
            row.get("evidence_asset")
            for row in [
                *values.get("theories", []),
                *values.get("topics", []),
                *values.get("nodes", []),
            ]
            if row.get("evidence_asset")
        ]
        missing = _missing_ids(
            Asset,
            evidence_ids,
            queryset=Asset.objects.filter(edition__work=target),
        )
        if missing:
            raise EditorialRevisionError(
                f"证据文件不属于当前作品或已不存在：{', '.join(missing)}"
            )
    return _json_value(values)


def _work_edition_section_snapshot(edition: Edition, field_name: str) -> dict[str, Any]:
    from catalog.services.admin_workflow import BIBLIOGRAPHY_FIELDS

    if field_name == "bibliography":
        from catalog.services.journal_issues import journal_contents_snapshot

        return _json_value(
            {**{field: getattr(edition, field) for field in BIBLIOGRAPHY_FIELDS}, "journal_contents": journal_contents_snapshot(edition)}
        )
    if field_name == "contributors":
        return {
            "contributors": [
                {
                    "person_id": str(row.person_id),
                    "role": row.role,
                    "order": row.order,
                }
                for row in edition.contributions.order_by("order", "created_at", "id")
            ]
        }
    if field_name == "reader":
        return {"reader_rendition_policy": edition.reader_rendition_policy}
    raise EditorialRevisionError("未知的版本编辑草稿分区。")


def _validated_work_edition_patch(
    target: Work,
    field_name: str,
    value,
    *,
    document_type=None,
) -> dict[str, Any] | None:
    from catalog.workflow_serializers import (
        BibliographySectionSerializer,
        ContributorsSectionSerializer,
        ReaderSectionSerializer,
    )

    if not isinstance(value, dict):
        raise EditorialRevisionError(f"{field_name} 必须是 JSON 对象。")
    edition_id = str(value.get("edition_id") or "").strip()
    raw_values = value.get("values")
    if not edition_id or not isinstance(raw_values, dict):
        raise EditorialRevisionError(
            f"{field_name} 草稿必须包含当前 edition_id 和 values。"
        )
    edition = target.editions.filter(pk=edition_id).first()
    if edition is None:
        raise EditorialRevisionError("编辑草稿引用的版本不属于当前作品。")
    serializer_class = {
        "bibliography": BibliographySectionSerializer,
        "contributors": ContributorsSectionSerializer,
        "reader": ReaderSectionSerializer,
    }[field_name]
    serializer = serializer_class(data=raw_values, partial=True)
    if not serializer.is_valid():
        raise EditorialRevisionError(
            f"{field_name} 草稿无效：{serializer.errors}"
        )
    values = {
        key: row
        for key, row in serializer.validated_data.items()
        if key not in {"expected_updated_at", "expected_work_updated_at", "note"}
    }
    if field_name == "contributors":
        normalized_rows = []
        for index, row in enumerate(values.get("contributors", [])):
            normalized_rows.append(
                {
                    "person_id": str(row["person_id"]),
                    "role": row["role"],
                    "order": row.get("order", index),
                }
            )
        missing = _missing_ids(
            Person,
            [row["person_id"] for row in normalized_rows],
        )
        if missing:
            raise EditorialRevisionError(
                f"责任者包含不存在的人物：{', '.join(missing)}"
            )
        values["contributors"] = normalized_rows
    values = _json_value(values)
    if field_name == "bibliography" and "journal_contents" in values:
        from catalog.services.journal_issues import normalize_journal_contents

        try:
            values["journal_contents"] = normalize_journal_contents(edition, values["journal_contents"], document_type=document_type)
        except ValueError as error:
            raise EditorialRevisionError(str(error)) from error
    current = _work_edition_section_snapshot(edition, field_name)
    if all(current.get(key) == row for key, row in values.items()):
        return None
    return {"edition_id": edition_id, "values": values}


def _validated_scholar_person_patch(target: ScholarProfile, value) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EditorialRevisionError("person 必须是 JSON 对象。")
    allowed = {
        "preferred_name",
        "original_name",
        "aliases",
        "birth_year",
        "death_year",
        "biography",
        "name_variants",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise EditorialRevisionError(f"学者草稿包含不可编辑人物字段：{', '.join(unknown)}")
    clean: dict[str, Any] = {}
    for field_name, raw_value in value.items():
        if field_name == "name_variants":
            if not isinstance(raw_value, list):
                raise EditorialRevisionError("人物名称列表格式无效。")
            from catalog.services.query_lexicon.normalization import normalize_term

            clean_rows = []
            identifiers = set()
            allowed_variant_fields = {"name", "language", "variant_type", "source_kind", "source_note", "displayable", "is_verified"}
            for row in raw_value:
                if not isinstance(row, dict) or set(row) - allowed_variant_fields:
                    raise EditorialRevisionError("人物名称包含不可编辑字段。")
                values = {"language": "und", "variant_type": "alias", "source_kind": "editorial", "source_note": "", "displayable": False, "is_verified": False, **row}
                name = str(values.get("name") or "").strip()
                normalized = normalize_term(name)
                if not normalized or normalized in identifiers:
                    raise EditorialRevisionError("人物名称不能为空或重复。")
                identifiers.add(normalized)
                values["name"] = name
                instance = PersonNameVariant(person=target.person, **values)
                try:
                    cleaned = {key: _json_value(PersonNameVariant._meta.get_field(key).clean(item, instance)) for key, item in values.items()}
                except ValidationError as exc:
                    raise EditorialRevisionError("人物名称的语言、类型或来源无效。") from exc
                if cleaned["displayable"] and not cleaned["is_verified"]:
                    raise EditorialRevisionError("公开显示的人物名称必须人工确认。")
                clean_rows.append(cleaned)
            clean[field_name] = clean_rows
            continue
        field = Person._meta.get_field(field_name)
        try:
            clean[field_name] = _json_value(field.clean(raw_value, target.person))
        except ValidationError as exc:
            raise EditorialRevisionError(
                f"person.{field_name} 的草稿值无效：{'；'.join(exc.messages)}"
            ) from exc
    aliases = clean.get("aliases")
    if aliases is not None and (
        not isinstance(aliases, list)
        or any(not isinstance(row, str) or not row.strip() for row in aliases)
    ):
        raise EditorialRevisionError("学者别名必须是非空字符串列表。")
    birth = clean.get("birth_year", target.person.birth_year)
    death = clean.get("death_year", target.person.death_year)
    if birth is not None and death is not None and birth > death:
        raise EditorialRevisionError("学者生年不能晚于卒年。")
    return clean


TOPIC_RELATION_POLICIES = {
    "discipline_relations": {
        "model": Discipline,
        "id_field": "discipline_id",
        "allowed_fields": {"discipline_id", "is_primary", "review_status"},
    },
    "theory_relations": {
        "model": TheorySchool,
        "id_field": "theory_school_id",
        "allowed_fields": {"theory_school_id", "relation_label", "review_status"},
    },
    "subdiscipline_relations": {
        "model": Subdiscipline,
        "id_field": "subdiscipline_id",
        "allowed_fields": {
            "subdiscipline_id",
            "relation_label",
            "review_status",
        },
    },
}


def _validated_topic_relation_patch(field_name: str, value) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise EditorialRevisionError(f"{field_name} 必须是列表。")
    policy = TOPIC_RELATION_POLICIES[field_name]
    id_field = policy["id_field"]
    allowed_fields = policy["allowed_fields"]
    allowed_statuses = set(RelationReviewStatus.values)
    identifiers: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            raise EditorialRevisionError(f"{field_name} 的每一项都必须是 JSON 对象。")
        unknown = sorted(set(row) - allowed_fields)
        if unknown:
            raise EditorialRevisionError(
                f"{field_name} 包含不可编辑字段：{', '.join(unknown)}"
            )
        identifier = str(row.get(id_field) or "").strip()
        if not identifier:
            raise EditorialRevisionError(f"{field_name} 的每一项都必须包含 {id_field}。")
        if identifier in identifiers:
            raise EditorialRevisionError(f"{field_name} 不能重复引用同一对象。")
        identifiers.add(identifier)
        review_status = str(
            row.get("review_status") or RelationReviewStatus.SUGGESTED
        )
        if review_status not in allowed_statuses:
            raise EditorialRevisionError(f"{field_name} 的审核状态无效。")
        clean_row: dict[str, Any] = {
            id_field: identifier,
            "review_status": review_status,
        }
        if field_name == "discipline_relations":
            is_primary = row.get("is_primary", False)
            if not isinstance(is_primary, bool):
                raise EditorialRevisionError("主题的主要学科标记必须是布尔值。")
            clean_row["is_primary"] = is_primary
        else:
            relation_label = str(row.get("relation_label") or "").strip()
            if len(relation_label) > 120:
                raise EditorialRevisionError("主题关系说明不能超过 120 个字符。")
            clean_row["relation_label"] = relation_label
        normalized.append(clean_row)
    missing = _missing_ids(policy["model"], identifiers)
    if missing:
        raise EditorialRevisionError(
            f"{field_name} 引用了不存在的对象：{', '.join(missing)}"
        )
    return sorted(normalized, key=lambda row: row[id_field])


def _validate_special_patch(target_type: str, target, patch: dict[str, Any]) -> None:
    if isinstance(target, Work):
        if "cover" in patch:
            cover = str(patch["cover"] or "")
            current = str(target.cover.name or "")
            allowed_prefix = f"public/covers/editorial/{target.pk}/"
            if cover and cover != current and (
                not cover.startswith(allowed_prefix)
                or ".." in cover.split("/")
                or "\\" in cover
                or not target.cover.storage.exists(cover)
            ):
                raise EditorialRevisionError("封面必须来自当前作品已保存的封面建议。")
            patch["cover"] = cover
        for field_name in ("classification", "knowledge"):
            if field_name in patch:
                if not isinstance(patch[field_name], dict):
                    raise EditorialRevisionError(f"{field_name} 必须是 JSON 对象。")
                patch[field_name] = _validated_work_relation_patch(
                    target,
                    field_name,
                    patch[field_name],
                )
        for field_name in ("bibliography", "contributors", "reader"):
            if field_name not in patch:
                continue
            normalized = _validated_work_edition_patch(
                target,
                field_name,
                patch[field_name],
                document_type=patch.get("document_type", target.document_type),
            )
            if normalized is None:
                patch.pop(field_name, None)
            else:
                patch[field_name] = normalized
    if isinstance(target, ScholarProfile) and "person" in patch:
        patch["person"] = _validated_scholar_person_patch(target, patch["person"])
    if isinstance(target, Subdiscipline):
        discipline_id = str(patch.get("discipline") or target.discipline_id)
        if not Discipline.objects.filter(pk=discipline_id).exists():
            raise EditorialRevisionError("子学科草稿引用了不存在的所属学科。")
        parent_id = str(patch.get("parent") or target.parent_id or "")
        if parent_id:
            if parent_id == str(target.id):
                raise EditorialRevisionError("子学科不能以自身作为上级。")
            parent = Subdiscipline.objects.select_related("parent").filter(
                pk=parent_id
            ).first()
            if parent is None:
                raise EditorialRevisionError("子学科草稿引用了不存在的上级子学科。")
            if str(parent.discipline_id) != discipline_id:
                raise EditorialRevisionError("上级子学科必须属于同一学科。")
            seen = {str(target.id)}
            current = parent
            while current is not None:
                if str(current.id) in seen:
                    raise EditorialRevisionError("子学科层级不能形成循环。")
                seen.add(str(current.id))
                current = current.parent
    if isinstance(target, Topic):
        for field_name in TOPIC_RELATION_POLICIES:
            if field_name in patch:
                patch[field_name] = _validated_topic_relation_patch(
                    field_name,
                    patch[field_name],
                )
    if isinstance(target, ReadingPath) and "stage_groups" in patch:
        from catalog.services.reading_paths import (
            ReadingPathStructureError,
            normalize_reading_path_stage_groups,
        )

        try:
            patch["stage_groups"] = normalize_reading_path_stage_groups(
                target,
                patch["stage_groups"],
            )
        except ReadingPathStructureError as exc:
            raise EditorialRevisionError(str(exc)) from exc


def _validated_patch(
    target_type: str,
    target,
    policy: EditorialTargetPolicy,
    patch: dict[str, Any],
) -> dict[str, Any]:
    unknown = sorted(set(patch) - policy.editable_fields)
    if unknown:
        raise EditorialRevisionError(f"草稿包含不可编辑字段：{', '.join(unknown)}")
    clean = {key: _json_value(value) for key, value in patch.items()}
    _validate_special_patch(target_type, target, clean)
    return clean


def _target_snapshot(target, policy: EditorialTargetPolicy) -> dict[str, Any]:
    scalar_fields = [
        field_name
        for field_name in policy.editable_fields
        if field_name not in SPECIAL_FIELDS
    ]
    snapshot = {
        key: _json_value(value)
        for key, value in model_to_dict(target, fields=scalar_fields).items()
    }
    snapshot.update(_special_snapshot(target))
    return snapshot


def editorial_target_snapshot(*, target_type: str, target) -> dict[str, Any]:
    """Return the JSON-safe canonical snapshot used to materialize previews."""

    policy = _policy(target_type)
    if not isinstance(target, policy.model):
        raise EditorialRevisionError("编辑草稿目标类型与对象不一致。")
    return _target_snapshot(target, policy)


def changed_editorial_patch(
    *,
    target_type: str,
    target,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Validate a JSON-safe patch and discard values equal to canonical data."""

    policy = _policy(target_type)
    clean_patch = _validated_patch(
        target_type,
        target,
        policy,
        dict(patch or {}),
    )
    current = _target_snapshot(target, policy)
    return {
        key: value
        for key, value in clean_patch.items()
        if current.get(key) != value
    }


def editorial_idempotency_key(
    *,
    target_type: str,
    target_id,
    base_revision: int,
    patch: dict[str, Any],
) -> str:
    payload = json.dumps(patch, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"editorial:{target_type}:{target_id}:{int(base_revision)}:{digest}"


def serialize_editorial_revision(revision: EditorialRevision) -> dict[str, Any]:
    canonical_revision = (
        CanonicalObjectRevision.objects.filter(
            object_type=revision.target_type,
            object_id=revision.target_id,
        )
        .values_list("current_revision", flat=True)
        .first()
        or 0
    )
    return {
        "id": str(revision.id),
        "target_type": revision.target_type,
        "target_id": str(revision.target_id),
        "base_revision": revision.base_revision,
        "current_revision": canonical_revision,
        "revision": revision.revision,
        "patch": revision.patch,
        "materialized_preview": revision.materialized_preview,
        "changed_fields": revision.changed_fields,
        "status": revision.status,
        "change_note": revision.change_note,
        "created_by": str(revision.created_by_id) if revision.created_by_id else None,
        "published_by": str(revision.published_by_id) if revision.published_by_id else None,
        "created_at": revision.created_at,
        "updated_at": revision.updated_at,
        "published_at": revision.published_at,
        "has_conflict": (
            revision.status == EditorialRevision.Status.DRAFT
            and canonical_revision != revision.base_revision
        ),
        "publish_url": f"/catalog/admin/editorial-revisions/{revision.id}/publish/",
    }


def _validate_knowledge_node_relations(target: KnowledgeNode, patch: dict[str, Any]) -> None:
    from catalog.services.canonical_identity import validate_canonical_node_type

    if "node_type" in patch:
        validate_canonical_node_type(patch["node_type"])
    aliases = patch.get("aliases")
    if aliases is not None:
        if not isinstance(aliases, list):
            raise EditorialRevisionError("aliases 必须是列表。")
        allowed_types = set(KnowledgeNodeAlias.AliasType.values)
        allowed_sources = set(KnowledgeNodeAlias.SourceKind.values)
        normalized_aliases: set[str] = set()
        for row in aliases:
            if not isinstance(row, dict) or not str(row.get("alias") or "").strip():
                raise EditorialRevisionError("每条别名都必须包含名称。")
            if str(row.get("alias_type") or KnowledgeNodeAlias.AliasType.ALIAS) not in allowed_types:
                raise EditorialRevisionError("别名类型不在受控范围内。")
            if str(row.get("source_kind") or KnowledgeNodeAlias.SourceKind.EDITORIAL) not in allowed_sources:
                raise EditorialRevisionError("别名来源类型不在受控范围内。")
            normalized_alias = " ".join(str(row["alias"]).casefold().split())
            if normalized_alias in normalized_aliases:
                raise EditorialRevisionError("同一节点的别名不能重复。")
            normalized_aliases.add(normalized_alias)
    links = patch.get("discipline_links")
    if links is not None:
        if not isinstance(links, list):
            raise EditorialRevisionError("discipline_links 必须是列表。")
        allowed_relations = set(KnowledgeNodeDiscipline.RelationType.values)
        allowed_statuses = {value for value, _label in KnowledgeNodeDiscipline._meta.get_field("status").choices}
        discipline_ids: set[str] = set()
        for row in links:
            if not isinstance(row, dict) or not row.get("discipline_id"):
                raise EditorialRevisionError("每条学科关系都必须包含 discipline_id。")
            if str(row.get("relation_type") or "") not in allowed_relations:
                raise EditorialRevisionError("学科关系类型不在受控范围内。")
            if str(row.get("status") or "pending") not in allowed_statuses:
                raise EditorialRevisionError("学科关系状态不在受控范围内。")
            discipline_id = str(row["discipline_id"])
            if discipline_id in discipline_ids:
                raise EditorialRevisionError("同一节点的学科关系不能重复。")
            discipline_ids.add(discipline_id)
        if Discipline.objects.filter(pk__in=discipline_ids).count() != len(discipline_ids):
            raise EditorialRevisionError("编辑草稿引用了不存在的学科。")
    normalized_links = (
        (
            "subdiscipline_links",
            "subdiscipline_id",
            Subdiscipline,
            {
                "subdiscipline_id",
                "is_primary",
                "relation_role",
                "source",
                "confidence",
                "sort_order",
                "status",
            },
        ),
        (
            "topic_links",
            "topic_id",
            Topic,
            {
                "topic_id",
                "relation_label",
                "source",
                "confidence",
                "sort_order",
                "status",
            },
        ),
    )
    allowed_statuses = set(KnowledgePublicationStatus.values)
    for field_name, id_field, model, allowed_fields in normalized_links:
        rows = patch.get(field_name)
        if rows is None:
            continue
        if not isinstance(rows, list):
            raise EditorialRevisionError(f"{field_name} 必须是列表。")
        identifiers: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise EditorialRevisionError(f"{field_name} 的每一项都必须是 JSON 对象。")
            unknown = sorted(set(row) - allowed_fields)
            if unknown:
                raise EditorialRevisionError(
                    f"{field_name} 包含不可编辑字段：{', '.join(unknown)}"
                )
            identifier = str(row.get(id_field) or "").strip()
            if not identifier or identifier in identifiers:
                raise EditorialRevisionError(f"{field_name} 引用为空或重复。")
            identifiers.add(identifier)
            if str(row.get("status") or "pending") not in allowed_statuses:
                raise EditorialRevisionError(f"{field_name} 的状态无效。")
            try:
                confidence = float(row.get("confidence") or 0)
                sort_order = int(row.get("sort_order") or 0)
            except (TypeError, ValueError) as exc:
                raise EditorialRevisionError(
                    f"{field_name} 的置信度或排序无效。"
                ) from exc
            if confidence < 0 or confidence > 1 or sort_order < 0:
                raise EditorialRevisionError(
                    f"{field_name} 的置信度或排序超出范围。"
                )
        if model.objects.filter(pk__in=identifiers).count() != len(identifiers):
            raise EditorialRevisionError(f"{field_name} 引用了不存在的规范对象。")


def _apply_knowledge_node_relations(target: KnowledgeNode, patch: dict[str, Any], actor) -> None:
    aliases = patch.get("aliases")
    if aliases is not None:
        existing = {row.normalized_alias: row for row in target.aliases.select_for_update()}
        retained = []
        for row in aliases:
            values = {"alias": str(row["alias"]).strip(), "language": str(row.get("language") or "zh-CN")[:16],
                      "alias_type": str(row.get("alias_type") or KnowledgeNodeAlias.AliasType.ALIAS),
                      "source_kind": str(row.get("source_kind") or KnowledgeNodeAlias.SourceKind.OTHER),
                      "is_verified": bool(row.get("is_verified", True))}
            normalized = " ".join(values["alias"].casefold().split())
            previous = existing.get(normalized)
            changed = previous is None or any(getattr(previous, key) != value for key, value in values.items())
            if changed:
                if values["is_verified"]:
                    values["source_kind"] = KnowledgeNodeAlias.SourceKind.EDITORIAL
                alias, _created = KnowledgeNodeAlias.objects.update_or_create(
                    node=target, normalized_alias=normalized, defaults={**values, "created_by": actor},
                )
            else:
                alias = previous
            retained.append(alias.pk)
        target.aliases.exclude(pk__in=retained).delete()
    links = patch.get("discipline_links")
    if links is not None:
        target.discipline_links.all().delete()
        for row in links:
            KnowledgeNodeDiscipline.objects.create(
                node=target,
                discipline_id=row["discipline_id"],
                relation_type=row["relation_type"],
                discipline_specific_summary=str(row.get("discipline_specific_summary") or ""),
                sort_order=max(0, int(row.get("sort_order") or 0)),
                status=str(row.get("status") or "pending"),
                reviewed_by=actor if row.get("status") == "published" else None,
                reviewed_at=timezone.now() if row.get("status") == "published" else None,
            )
    normalized_models = (
        (
            "subdiscipline_links",
            KnowledgeNodeSubdiscipline,
            "subdiscipline_id",
            ("is_primary", "relation_role", "source", "confidence", "sort_order"),
        ),
        (
            "topic_links",
            KnowledgeNodeTopic,
            "topic_id",
            ("relation_label", "source", "confidence", "sort_order"),
        ),
    )
    for field_name, model, id_field, value_fields in normalized_models:
        if field_name not in patch:
            continue
        getattr(target, field_name).all().delete()
        for row in patch[field_name]:
            status_value = str(row.get("status") or "pending")
            defaults = {
                "is_primary": False,
                "relation_role": "",
                "relation_label": "",
                "source": "",
                "confidence": 0,
                "sort_order": 0,
            }
            model.objects.create(
                node=target,
                **{id_field: row[id_field]},
                **{
                    field: row.get(field, defaults[field])
                    for field in value_fields
                },
                status=status_value,
                reviewed_by=actor if status_value == "published" else None,
                reviewed_at=timezone.now() if status_value == "published" else None,
            )


def _apply_scholar_person(target: ScholarProfile, values: dict[str, Any], actor=None) -> None:
    person = Person.objects.select_for_update().get(pk=target.person_id)
    previous_aliases = set(person.aliases or [])
    for field_name, value in values.items():
        if field_name != "name_variants":
            setattr(person, field_name, value)
    if "preferred_name" in values and not person.sort_name:
        person.sort_name = values["preferred_name"]
    try:
        person.full_clean()
    except ValidationError as exc:
        message = "；".join(
            f"{field}: {','.join(messages)}"
            for field, messages in getattr(
                exc,
                "message_dict",
                {"detail": exc.messages},
            ).items()
        )
        raise EditorialRevisionError(f"学者人物草稿不能发布：{message}") from exc
    person.save()
    if "name_variants" in values:
        from catalog.services.query_lexicon.normalization import normalize_term

        retained = []
        existing = {row.normalized_name: row for row in person.name_variants.select_for_update()}
        for row in values["name_variants"]:
            defaults = dict(row)
            normalized = normalize_term(row["name"])
            previous = existing.get(normalized)
            changed = previous is None or any(getattr(previous, key) != value for key, value in defaults.items())
            if changed:
                if defaults.get("is_verified"):
                    defaults["source_kind"] = PersonNameVariant.SourceKind.EDITORIAL
                variant, _created = PersonNameVariant.objects.update_or_create(
                    person=person, normalized_name=normalized, defaults={**defaults, "created_by": actor},
                )
            else:
                variant = previous
            retained.append(variant.pk)
        person.name_variants.exclude(pk__in=retained).delete()
    if "aliases" in values:
        from catalog.services.query_lexicon.normalization import normalize_term

        # A full Scholar form can carry legacy search aliases unchanged. Only
        # newly supplied aliases are an explicit editorial assertion here.
        for name in set(values["aliases"]) - previous_aliases:
            PersonNameVariant.objects.update_or_create(
                person=person, normalized_name=normalize_term(name),
                defaults={"name": name, "language": "und", "variant_type": PersonNameVariant.VariantType.ALIAS,
                          "source_kind": PersonNameVariant.SourceKind.EDITORIAL, "is_verified": True,
                          "displayable": True, "created_by": actor},
            )
    target.person = person


def _apply_topic_relations(target: Topic, patch: dict[str, Any], actor) -> None:
    now = timezone.now()
    relation_models = {
        "discipline_relations": (
            TopicDisciplineRelation,
            "discipline_id",
            {"is_primary"},
        ),
        "theory_relations": (
            TopicTheoryRelation,
            "theory_school_id",
            {"relation_label"},
        ),
        "subdiscipline_relations": (
            TopicSubdisciplineRelation,
            "subdiscipline_id",
            {"relation_label"},
        ),
    }
    for field_name, (model, id_field, value_fields) in relation_models.items():
        if field_name not in patch:
            continue
        rows = patch[field_name]
        selected_ids = {str(row[id_field]) for row in rows}
        existing = list(model.objects.select_for_update().filter(topic=target))
        stale_ids = [
            relation.pk
            for relation in existing
            if str(getattr(relation, id_field)) not in selected_ids
        ]
        if stale_ids:
            model.objects.filter(pk__in=stale_ids).delete()
        for row in rows:
            defaults = {
                field: row[field]
                for field in value_fields
            }
            defaults.update(
                {
                    "review_status": row["review_status"],
                    "reviewed_by": actor,
                    "reviewed_at": now,
                }
            )
            model.objects.update_or_create(
                topic=target,
                **{id_field: row[id_field]},
                defaults=defaults,
            )


def _apply_special_fields(target, patch: dict[str, Any], actor) -> None:
    if isinstance(target, Work):
        from catalog.services.work_editor import (
            WorkflowEditError,
            apply_work_classification,
            apply_work_knowledge,
        )

        try:
            if "classification" in patch:
                apply_work_classification(target, patch["classification"], actor)
            if "knowledge" in patch:
                apply_work_knowledge(target, patch["knowledge"], actor)
            for field_name in ("bibliography", "contributors", "reader"):
                if field_name not in patch:
                    continue
                section = patch[field_name]
                edition = target.editions.select_for_update().filter(
                    pk=section["edition_id"]
                ).first()
                if edition is None:
                    raise EditorialRevisionError(
                        "编辑草稿引用的版本不属于当前作品。"
                    )
                from catalog.services.work_editor import save_workflow_section
                from catalog.workflow_serializers import SECTION_SERIALIZERS

                serializer = SECTION_SERIALIZERS[field_name](
                    data=section["values"],
                    partial=True,
                )
                if not serializer.is_valid():
                    raise EditorialRevisionError(
                        f"{field_name} 草稿无效：{serializer.errors}"
                    )

                save_workflow_section(
                    edition,
                    field_name,
                    serializer.validated_data,
                    actor=actor,
                    confirm_section=True,
                    publishing_revision=True,
                )
        except WorkflowEditError as exc:
            raise EditorialRevisionError(str(exc)) from exc
    if isinstance(target, KnowledgeNode):
        _apply_knowledge_node_relations(target, patch, actor)
    if isinstance(target, ScholarProfile) and "person" in patch:
        _apply_scholar_person(target, patch["person"], actor)
    if isinstance(target, Topic):
        _apply_topic_relations(target, patch, actor)
    if isinstance(target, PublisherAuthority) and "aliases" in patch:
        target.aliases = list(patch["aliases"] or [])
        target.save(update_fields=["aliases", "updated_at"])
    if isinstance(target, ReadingPath) and "stage_groups" in patch:
        from catalog.services.reading_paths import (
            ReadingPathStructureError,
            sync_reading_path_stage_groups,
        )

        try:
            sync_reading_path_stage_groups(target, patch["stage_groups"])
        except ReadingPathStructureError as exc:
            raise EditorialRevisionError(str(exc)) from exc


def _work_catalog_edition(work: Work, patch: dict[str, Any]) -> Edition | None:
    """Resolve the one Edition snapshot owned by this Work revision.

    Workbench edition sections carry their exact ``edition_id``.  Pure Work
    changes use the primary published edition, matching the existing public
    Work route.  Mixed edition section patches are rejected before mutation so
    one EditorialRevision cannot create an ambiguous catalog snapshot.
    """

    referenced = {
        str(section.get("edition_id"))
        for field_name in ("bibliography", "contributors", "reader")
        if isinstance((section := patch.get(field_name)), dict)
        and section.get("edition_id")
    }
    if len(referenced) > 1:
        raise EditorialRevisionError("同一作品草稿不能同时修改多个版本。")
    published = work.editions.select_for_update().filter(
        state=PublicationState.PUBLISHED,
    )
    if referenced:
        exact = published.filter(pk=next(iter(referenced))).first()
        if exact is not None:
            return exact
    return published.order_by(
        "-is_primary",
        "-last_published_at",
        "-published_at",
        "id",
    ).first()


@transaction.atomic
def create_editorial_revision(
    *,
    target_type: str,
    target_id,
    patch: dict[str, Any],
    actor,
    idempotency_key: str,
    change_note: str = "",
) -> EditorialRevision:
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise EditorialRevisionError("编辑草稿必须记录实际操作人。")
    policy = _policy(target_type)
    target = policy.model.objects.select_for_update().filter(pk=target_id).first()
    if target is None:
        raise EditorialRevisionError("目标对象不存在。")
    clean_patch = changed_editorial_patch(
        target_type=target_type,
        target=target,
        patch=patch,
    )
    if not clean_patch:
        raise EditorialRevisionError("草稿没有实际变更。")
    idempotency_key = str(idempotency_key or "").strip()
    if not idempotency_key:
        raise EditorialRevisionError("编辑草稿必须提供幂等键。")
    if len(idempotency_key) > 160:
        raise EditorialRevisionError("编辑草稿幂等键过长。")
    if isinstance(target, KnowledgeNode):
        _validate_knowledge_node_relations(target, clean_patch)

    existing = EditorialRevision.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        if (
            existing.target_type != target_type
            or existing.target_id != target.pk
            or existing.patch != clean_patch
        ):
            raise EditorialRevisionConflict("幂等键已用于另一份编辑草稿。")
        return existing

    canonical, _created = CanonicalObjectRevision.objects.select_for_update().get_or_create(
        object_type=target_type,
        object_id=target.pk,
        defaults={"current_revision": 0},
    )
    next_revision = (
        EditorialRevision.objects.filter(target_type=target_type, target_id=target.pk)
        .order_by("-revision")
        .values_list("revision", flat=True)
        .first()
        or 0
    ) + 1
    preview = _target_snapshot(target, policy)
    preview.update(clean_patch)
    return EditorialRevision.objects.create(
        target_type=target_type,
        target_id=target.pk,
        base_revision=canonical.current_revision,
        revision=next_revision,
        patch=clean_patch,
        materialized_preview=preview,
        changed_fields=sorted(clean_patch),
        status=EditorialRevision.Status.DRAFT,
        idempotency_key=idempotency_key,
        change_note=str(change_note or "")[:500],
        created_by=actor,
    )


@transaction.atomic
def save_workflow_editorial_revision(
    *,
    work_id,
    section_patch: dict[str, Any],
    actor,
    idempotency_key: str = "",
    change_note: str = "",
) -> EditorialRevision | None:
    """Merge one Workbench section into the single current Work draft.

    Workbench saves sections independently.  Keeping the latest draft as a
    complete union prevents a later section save from silently superseding an
    earlier unsaved section.  The published Work remains unchanged until the
    merged revision is confirmed.
    """

    work = Work.objects.select_for_update().filter(pk=work_id).first()
    if work is None:
        raise EditorialRevisionError("作品不存在。")
    canonical, _created = CanonicalObjectRevision.objects.select_for_update().get_or_create(
        object_type=EditorialRevision.TargetType.WORK,
        object_id=work.id,
        defaults={"current_revision": 0},
    )
    latest = (
        EditorialRevision.objects.select_for_update()
        .filter(
            target_type=EditorialRevision.TargetType.WORK,
            target_id=work.id,
            status=EditorialRevision.Status.DRAFT,
        )
        .order_by("-revision")
        .first()
    )
    if latest is not None and latest.base_revision != canonical.current_revision:
        raise EditorialRevisionConflict("正式内容已变化，请基于最新内容重新建立草稿。")
    combined = dict(latest.patch or {}) if latest is not None else {}
    combined.update(dict(section_patch or {}))
    clean_patch = changed_editorial_patch(
        target_type=EditorialRevision.TargetType.WORK,
        target=work,
        patch=combined,
    )
    if not clean_patch:
        if latest is not None:
            latest.status = EditorialRevision.Status.SUPERSEDED
            latest.save(update_fields=["status", "updated_at"])
        return None
    if latest is not None and latest.patch == clean_patch:
        return latest
    revision_number = (
        EditorialRevision.objects.filter(
            target_type=EditorialRevision.TargetType.WORK,
            target_id=work.id,
        )
        .order_by("-revision")
        .values_list("revision", flat=True)
        .first()
        or 0
    )
    resolved_key = str(idempotency_key or "").strip() or (
        f"{editorial_idempotency_key(target_type=EditorialRevision.TargetType.WORK, target_id=work.id, base_revision=canonical.current_revision, patch=clean_patch)}"
        f":workflow:{revision_number}"
    )
    revision = create_editorial_revision(
        target_type=EditorialRevision.TargetType.WORK,
        target_id=work.id,
        patch=clean_patch,
        actor=actor,
        idempotency_key=resolved_key,
        change_note=change_note,
    )
    if revision.status != EditorialRevision.Status.DRAFT:
        raise EditorialRevisionConflict("该幂等键对应的编辑草稿已经失效。")
    if latest is not None and latest.pk != revision.pk:
        latest.status = EditorialRevision.Status.SUPERSEDED
        latest.save(update_fields=["status", "updated_at"])
        from catalog.models import CatalogFieldDecision

        for decision in CatalogFieldDecision.objects.select_for_update().filter(
            edition__work=work,
            provenance__editorial_revision_id=str(latest.pk),
        ):
            decision.provenance = {**decision.provenance, "editorial_revision_id": str(revision.pk)}
            decision.save(update_fields=["provenance", "updated_at"])
    return revision


@transaction.atomic
def publish_editorial_revision(revision_id, *, actor) -> EditorialRevision:
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise EditorialRevisionError("发布必须记录实际操作人。")
    revision = EditorialRevision.objects.select_for_update().filter(pk=revision_id).first()
    if revision is None:
        raise EditorialRevisionError("编辑草稿不存在。")
    if revision.status == EditorialRevision.Status.PUBLISHED:
        return revision
    if revision.status != EditorialRevision.Status.DRAFT:
        raise EditorialRevisionConflict("该草稿已经失效。")

    policy = _policy(revision.target_type)
    target = policy.model.objects.select_for_update().filter(pk=revision.target_id).first()
    if target is None:
        raise EditorialRevisionError("目标对象不存在。")
    canonical = CanonicalObjectRevision.objects.select_for_update().get(
        object_type=revision.target_type,
        object_id=revision.target_id,
    )
    if canonical.current_revision != revision.base_revision:
        raise EditorialRevisionConflict("正式内容已变化，请基于最新内容重新建立草稿。")

    patch = _validated_patch(
        revision.target_type,
        target,
        policy,
        dict(revision.patch or {}),
    )
    catalog_edition = (
        _work_catalog_edition(target, patch)
        if isinstance(target, Work)
        else target
        if isinstance(target, Edition) and target.state == PublicationState.PUBLISHED
        else None
    )
    relation_fields = SPECIAL_FIELDS
    if isinstance(target, KnowledgeNode):
        _validate_knowledge_node_relations(target, patch)
    previous_status = getattr(target, "status", getattr(target, "editorial_status", None))
    for field_name, value in patch.items():
        if field_name in relation_fields:
            continue
        field = target._meta.get_field(field_name)
        try:
            clean_value = field.clean(value, target)
        except ValidationError as exc:
            raise EditorialRevisionError(
                f"{field_name} 的草稿值无效：{'；'.join(exc.messages)}"
            ) from exc
        if field.many_to_one:
            setattr(target, field.attname, clean_value)
        else:
            setattr(target, field_name, clean_value)

    next_status = getattr(target, "status", getattr(target, "editorial_status", None))
    if hasattr(target, "published_at") and next_status is not None:
        if next_status == "published" and previous_status != "published":
            target.published_at = timezone.now()
        elif next_status != "published":
            target.published_at = None
    if hasattr(target, "reviewed_by") and next_status == "published":
        target.reviewed_by = actor
    try:
        target.full_clean()
    except ValidationError as exc:
        message = "；".join(
            f"{field}: {','.join(messages)}"
            for field, messages in getattr(exc, "message_dict", {"detail": exc.messages}).items()
        )
        raise EditorialRevisionError(f"草稿不能发布：{message}") from exc
    target.save()
    _apply_special_fields(target, patch, actor)
    if isinstance(target, ScholarProfile) and next_status == "published":
        from catalog.services.scholar_publication import (
            ScholarPublicationError,
            ensure_scholar_public_authority,
        )

        try:
            ensure_scholar_public_authority(target, actor=actor)
        except ScholarPublicationError as exc:
            raise EditorialRevisionError(str(exc)) from exc
    if isinstance(target, KnowledgeNode):
        from catalog.services.knowledge_nodes import record_node_version

        record_node_version(target, actor, revision.change_note or "发布编辑草稿")

    revision.status = EditorialRevision.Status.PUBLISHED
    revision.published_by = actor
    revision.published_at = timezone.now()
    revision.save(update_fields=["status", "published_by", "published_at", "updated_at"])
    EditorialRevision.objects.filter(
        target_type=revision.target_type,
        target_id=revision.target_id,
        status=EditorialRevision.Status.DRAFT,
    ).exclude(pk=revision.pk).update(
        status=EditorialRevision.Status.SUPERSEDED,
        updated_at=timezone.now(),
    )

    change_kind = (
        "withdraw"
        if previous_status == "published" and next_status in {"archived", "withdrawn"}
        else "publish"
    )
    if catalog_edition is not None:
        from catalog.models import CatalogFieldDecision, KnowledgePublicationEvent
        from catalog.services.field_decisions import field_value_present, formal_field_values, record_edition_field_decision, SECTION_FIELDS
        from catalog.services.knowledge_publication import (
            create_catalog_publication_event,
        )

        try:
            # Final publication confirms the reviewed patch, not unrelated
            # draft fields. Clear staged provenance only for this revision.
            catalog_edition.refresh_from_db()
            actual, _ = formal_field_values(catalog_edition, include_editorial_draft=False)
            confirmed_fields = set(revision.changed_fields).intersection(actual)
            for section in ("classification", "knowledge"):
                if section in patch:
                    confirmed_fields.update(SECTION_FIELDS[section])
            confirmed_fields.update(CatalogFieldDecision.objects.filter(
                edition=catalog_edition, provenance__editorial_revision_id=str(revision.pk),
            ).values_list("field_name", flat=True))
            for name in confirmed_fields:
                value = _json_value(actual.get(name))
                old_decision = catalog_edition.field_decisions.filter(field_name=name).first()
                record_edition_field_decision(
                    catalog_edition, name,
                    status="confirmed" if field_value_present(value) else "not_applicable",
                    value=value, actor=actor,
                    provenance={**(old_decision.provenance if old_decision else {}), "editorial_revision_id": str(revision.pk), "canonical_write_deferred": False},
                    reason="正式发布已确认的编辑修订",
                )
            knowledge_event = create_catalog_publication_event(
                catalog_edition,
                event_type=KnowledgePublicationEvent.EventType.CATALOG_UPDATED,
                changed_fields=revision.changed_fields,
                actor=actor,
                idempotency_key=f"editorial-catalog:{revision.pk}",
                source_object_type=revision.target_type,
                source_object_id=revision.target_id,
                source_changed_fields=revision.changed_fields,
                expected_source_base_revision=revision.base_revision,
                provenance={
                    "editorial_revision_id": str(revision.pk),
                    "editorial_revision_number": revision.revision,
                },
            )
            if isinstance(target, Work):
                # Work metadata and knowledge relations are shared by every
                # published Edition. Edition-specific sections remain owned
                # by the one catalog_edition selected above.
                shared_fields = sorted(set(patch) - {"bibliography", "contributors", "reader"})
                if shared_fields:
                    siblings = target.editions.select_for_update().filter(
                        state=PublicationState.PUBLISHED,
                    ).exclude(pk=catalog_edition.pk).order_by("pk")
                    for sibling in siblings:
                        sibling_actual, _ = formal_field_values(sibling, include_editorial_draft=False)
                        sibling_confirmed = set(shared_fields).intersection(sibling_actual)
                        for section in ("classification", "knowledge"):
                            if section in shared_fields:
                                sibling_confirmed.update(SECTION_FIELDS[section])
                        for name in sibling_confirmed:
                            value = _json_value(sibling_actual.get(name))
                            old_decision = sibling.field_decisions.filter(field_name=name).first()
                            record_edition_field_decision(
                                sibling, name,
                                status="confirmed" if field_value_present(value) else "not_applicable",
                                value=value, actor=actor,
                                provenance={**(old_decision.provenance if old_decision else {}), "editorial_revision_id": str(revision.pk), "canonical_write_deferred": False},
                                reason="正式发布作品共享字段",
                            )
                        create_catalog_publication_event(
                            sibling,
                            event_type=KnowledgePublicationEvent.EventType.CATALOG_UPDATED,
                            changed_fields=shared_fields,
                            actor=actor,
                            idempotency_key=f"editorial-catalog:{revision.pk}:edition:{sibling.pk}",
                            # The Work canonical counter was advanced once by
                            # knowledge_event. Each sibling owns its derived
                            # Edition publication counter, never a second Work
                            # mutation for the same editorial action.
                            source_object_type="edition",
                            source_object_id=sibling.pk,
                            source_changed_fields=shared_fields,
                            provenance={
                                "source": "shared_work_publication",
                                "editorial_revision_id": str(revision.pk),
                                "editorial_revision_number": revision.revision,
                                "shared_work_publication_event_id": str(knowledge_event.pk),
                            },
                        )
        except ValueError as exc:
            raise EditorialRevisionConflict(
                f"正式内容发布事件建立失败：{exc}"
            ) from exc
        event = knowledge_event.domain_event
    else:
        from catalog.services.dependency_engine import record_canonical_change
        from catalog.services.canonical_mutations import ENTITY_PUBLICATION_TYPES, _is_published

        if revision.target_type in ENTITY_PUBLICATION_TYPES and (_is_published(target, revision.target_type) or change_kind == "withdraw"):
            from catalog.models import KnowledgePublicationEvent
            from catalog.services.knowledge_publication import create_entity_publication_event

            entity_event = create_entity_publication_event(
                object_type=revision.target_type, object_id=revision.target_id,
                event_type=KnowledgePublicationEvent.EventType.ENTITY_PUBLISHED if previous_status != "published" and next_status == "published" else KnowledgePublicationEvent.EventType.ENTITY_UPDATED,
                changed_fields=revision.changed_fields, actor=actor,
                idempotency_key=f"editorial-publish:{revision.pk}",
                provenance={"editorial_revision_id": str(revision.pk), "withdrawal": change_kind == "withdraw"},
            )
            event = entity_event.domain_event
        else:
            # Applying an editorial draft without an explicit public state
            # only advances concurrency bookkeeping, with no shared consumers.
            event = record_canonical_change(
            object_type=revision.target_type,
            object_id=revision.target_id,
            change_kind=change_kind,
            changed_fields=revision.changed_fields,
            actor=actor,
            idempotency_key=f"editorial-publish:{revision.pk}",
            resolve=False,
            )
            event.processed_at = timezone.now()
            event.save(update_fields=["processed_at", "updated_at"])
    if event.canonical_revision != revision.base_revision + 1:
        raise EditorialRevisionConflict("正式内容版本推进异常，事务已回滚。")
    return revision
