"""Bounded, read-only aggregation for the Knowledge Studio workspace.

The studio is an editorial view over existing canonical, derived and candidate
stores.  It intentionally does not provide a second mutation path: editors
continue to use the established node, scholar, topic, relation and revision
endpoints linked from each object.
"""

from __future__ import annotations

from copy import copy
from typing import Any
from uuid import UUID

from django.db.models import Prefetch, Q, QuerySet

from catalog.models import (
    ClaimEvidence,
    CanonicalObjectRevision,
    CuratedClaim,
    DebateCandidate,
    DerivedClaim,
    Discipline,
    EditorialRevision,
    EnrichmentCandidate,
    EvidenceSnippet,
    EvidenceSpan,
    KnowledgeNode,
    KnowledgePublicationStatus,
    ProjectionState,
    PublicationState,
    ReadingPath,
    ReadingPathCandidate,
    RelationReviewStatus,
    ScholarProfile,
    Subdiscipline,
    TheorySchool,
    TheoryTimelineEvent,
    TheoryReviewTask,
    Topic,
    Work,
)
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.candidate_decision_protocol import (
    attach_candidate_action_descriptors,
)
from catalog.services.reading_paths import reading_path_stage_groups


NODE_OBJECT_TYPES = {
    "theory": KnowledgeNode.NodeType.THEORY_TRADITION,
    "concept": KnowledgeNode.NodeType.CONCEPT,
    "debate": KnowledgeNode.NodeType.DEBATE,
    "research_problem": KnowledgeNode.NodeType.RESEARCH_PROBLEM,
}
OBJECT_TYPES = (
    *NODE_OBJECT_TYPES,
    "scholar",
    "discipline",
    "subdiscipline",
    "topic",
    "reading_path",
    "work",
)
DEFAULT_DIRECTORY_LIMIT = 40
MAX_DIRECTORY_LIMIT = 50
MAX_SECTION_ROWS = 12
KNOWLEDGE_UPDATE_LIMIT = 5
GLOBAL_KNOWLEDGE_UPDATE_LIMIT = 8


PUBLIC_MODULE_FIELDS = {
    "theory": (
        ("定义", ("definition",)),
        ("核心问题", ("core_questions",)),
        ("发展脉络", ("start_year", "end_year", "period_label", "direct_relations")),
        ("主要人物", ("representative_scholars",)),
        ("核心概念", ("topic_links", "subdiscipline_links")),
        ("主要批评", ("curated_claims",)),
        ("代表作品", ("work_groups",)),
    ),
    "concept": (
        ("定义", ("definition",)),
        ("核心问题", ("core_questions",)),
        ("理论边界", ("theoretical_boundary",)),
        ("相关理论与主题", ("direct_relations", "topic_links")),
        ("代表作品", ("work_groups",)),
    ),
    "debate": (
        ("Canonical question", ("definition", "core_questions")),
        ("Support / Oppose / Qualify", ("curated_claims",)),
        ("代表作品", ("work_groups",)),
        ("原文证据", ("evidence",)),
    ),
    "research_problem": (
        ("研究问题", ("definition", "core_questions")),
        ("理论解释", ("direct_relations",)),
        ("代表作品", ("work_groups",)),
    ),
    "scholar": (
        ("身份与译名", ("person",)),
        ("学术位置", ("short_description", "affiliations", "key_concerns")),
        ("核心作品", ("works",)),
        ("核心观点与批评回应", ("curated_claims",)),
        ("理论贡献", ("knowledge_nodes",)),
        ("建议阅读顺序", ("curated",)),
    ),
    "discipline": (
        ("学科介绍", ("description", "introduction")),
        ("子学科目录", ("subdiscipline_count",)),
        ("理论与主题", ("theory_count", "topic_count")),
        ("作品与学者", ("work_count", "scholar_count")),
    ),
    "subdiscipline": (
        ("研究对象与核心问题", ("research_object", "core_questions")),
        ("形成与发展", ("formation_period",)),
        ("主要研究方向", ("research_directions",)),
        ("常用方法", ("methods",)),
        ("代表性议题", ("representative_issues", "topics")),
        ("相关理论传统", ("theories",)),
        ("精选文献导读", ("works",)),
    ),
    "topic": (
        ("范围与核心问题", ("description", "problem_statement", "core_questions")),
        ("理论视角", ("knowledge_nodes", "linked_theories")),
        ("作品与观点", ("curated", "curated_claims")),
        ("研究路径", ("research_dimensions", "methods")),
    ),
    "reading_path": (
        ("目标读者", ("audience",)),
        ("学习目标", ("learning_goal",)),
        ("阶段", ("stages",)),
        ("作品与节点", ("items",)),
        ("推荐理由与先后逻辑", ("items",)),
    ),
    "work": (
        ("书目与阅读", ("edition", "editions", "outline")),
        ("核心观点 / 批评 / 回应", ("curated_claims",)),
        ("理论与知识关系", ("theory_associations", "theories", "topics")),
        ("学科与子学科", ("disciplines", "subdisciplines")),
    ),
}


def _bounded_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_DIRECTORY_LIMIT
    return max(1, min(parsed, MAX_DIRECTORY_LIMIT))


def _valid_uuid(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _clip(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _bounded_json(value: Any, *, depth: int = 0) -> Any:
    """Keep stored preview/candidate JSON useful without returning an unbounded blob."""

    # Reading path stages and Work editions both have one meaningful nested
    # row level below their grouping object.  Keep those structured while the
    # row/count caps above still bound the response.
    if depth >= 6:
        return _clip(value, 300)
    if isinstance(value, dict):
        return {
            str(key): _bounded_json(item, depth=depth + 1)
            for key, item in list(value.items())[:30]
        }
    if isinstance(value, (list, tuple)):
        return [_bounded_json(item, depth=depth + 1) for item in list(value)[:20]]
    if isinstance(value, str):
        return _clip(value)
    return value


def _has_public_content(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    if isinstance(value, (int, float)):
        return value > 0
    return True


class KnowledgeObjectEditorAdapter:
    """Expose established public and editorial contracts through one read model."""

    TARGET_TYPES = {
        "theory": EditorialRevision.TargetType.KNOWLEDGE_NODE,
        "concept": EditorialRevision.TargetType.KNOWLEDGE_NODE,
        "debate": EditorialRevision.TargetType.KNOWLEDGE_NODE,
        "research_problem": EditorialRevision.TargetType.KNOWLEDGE_NODE,
        "scholar": EditorialRevision.TargetType.SCHOLAR_PROFILE,
        "discipline": EditorialRevision.TargetType.DISCIPLINE,
        "subdiscipline": EditorialRevision.TargetType.SUBDISCIPLINE,
        "topic": EditorialRevision.TargetType.TOPIC,
        "reading_path": EditorialRevision.TargetType.READING_PATH,
        "work": EditorialRevision.TargetType.WORK,
    }

    @classmethod
    def _serializer(cls, object_type: str):
        from catalog.serializers import (
            DisciplineSerializer,
            ScholarProfileSerializer,
            SubdisciplineSerializer,
            TopicSerializer,
            WorkDetailSerializer,
        )
        from catalog.theory_serializers import (
            KnowledgeNodeDetailSerializer,
            ReadingPathSerializer,
        )

        if object_type in NODE_OBJECT_TYPES:
            return KnowledgeNodeDetailSerializer
        return {
            "scholar": ScholarProfileSerializer,
            "discipline": DisciplineSerializer,
            "subdiscipline": SubdisciplineSerializer,
            "topic": TopicSerializer,
            "reading_path": ReadingPathSerializer,
            "work": WorkDetailSerializer,
        }[object_type]

    @classmethod
    def _is_public(cls, object_type: str, target) -> bool:
        if object_type in NODE_OBJECT_TYPES or object_type == "reading_path":
            return target.status == KnowledgePublicationStatus.PUBLISHED
        if object_type == "scholar":
            # Public Scholar endpoints require both an explicitly published
            # profile and a verified Person authority record.  Knowledge
            # Studio must use the same rule or it advertises a public URL that
            # the anonymous API correctly rejects.
            from catalog.models import Person

            return (
                target.editorial_status == KnowledgePublicationStatus.PUBLISHED
                and target.person.authority_status == Person.AuthorityStatus.VERIFIED
            )
        if object_type in {"discipline", "subdiscipline", "topic"}:
            return target.editorial_status == KnowledgePublicationStatus.PUBLISHED
        return target.editions.filter(state=PublicationState.PUBLISHED).exists()

    @classmethod
    def _draft_target(cls, target_type: str, target, revision: EditorialRevision):
        from catalog.services.editorial_revision import SPECIAL_FIELDS, TARGET_POLICIES

        preview = copy(target)
        policy = TARGET_POLICIES[target_type]
        for field_name, value in dict(revision.materialized_preview or {}).items():
            if field_name in SPECIAL_FIELDS or field_name not in policy.editable_fields:
                continue
            try:
                field = target._meta.get_field(field_name)
                if field.many_to_one:
                    setattr(preview, field.attname, value or None)
                else:
                    setattr(preview, field_name, field.to_python(value))
            except (TypeError, ValueError):
                continue
        return preview

    @classmethod
    def _related_objects(cls, model, identifiers) -> dict[str, Any]:
        normalized = [str(value or "").strip() for value in identifiers]
        if any(not value for value in normalized) or len(normalized) != len(
            set(normalized)
        ):
            raise ValueError("preview relation identifiers are empty or duplicated")
        objects = {
            str(row.pk): row
            for row in model.objects.filter(pk__in=normalized)
        }
        if len(objects) != len(normalized):
            raise ValueError("preview relation references a missing canonical object")
        return objects

    @classmethod
    def _node_special_overlay(
        cls,
        *,
        target: KnowledgeNode,
        field_name: str,
        value,
        data: dict[str, Any],
    ) -> None:
        from catalog.models import (
            KnowledgeNodeAlias,
            KnowledgeNodeDiscipline,
            KnowledgeNodeSubdiscipline,
            KnowledgeNodeTopic,
        )
        from catalog.theory_serializers import (
            KnowledgeNodeAliasSerializer,
            KnowledgeNodeDisciplineSerializer,
            KnowledgeNodeSubdisciplineSerializer,
            KnowledgeNodeTopicSerializer,
        )

        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ValueError(f"{field_name} preview is not a list of objects")

        if field_name == "aliases":
            aliases = [
                KnowledgeNodeAlias(
                    id=None,
                    node=target,
                    alias=str(row.get("alias") or "").strip(),
                    language=str(row.get("language") or "zh-CN")[:16],
                    alias_type=str(
                        row.get("alias_type") or KnowledgeNodeAlias.AliasType.ALIAS
                    ),
                    normalized_alias=" ".join(
                        str(row.get("alias") or "").casefold().split()
                    ),
                    source_kind=str(
                        row.get("source_kind")
                        or KnowledgeNodeAlias.SourceKind.EDITORIAL
                    ),
                    is_verified=bool(row.get("is_verified", True)),
                )
                for row in value
            ]
            if any(not row.alias for row in aliases):
                raise ValueError("alias preview contains an empty name")
            aliases.sort(key=lambda row: row.alias)
            data["aliases"] = list(
                KnowledgeNodeAliasSerializer(aliases, many=True, context={}).data
            )
            data["aliases_count"] = len(data["aliases"])
            return

        if field_name == "discipline_links":
            related = cls._related_objects(
                Discipline,
                [row.get("discipline_id") for row in value],
            )
            links = [
                KnowledgeNodeDiscipline(
                    id=None,
                    node=target,
                    discipline=related[str(row["discipline_id"])],
                    relation_type=str(row.get("relation_type") or "related"),
                    discipline_specific_summary=str(
                        row.get("discipline_specific_summary") or ""
                    ),
                    sort_order=int(row.get("sort_order") or 0),
                    status=str(row.get("status") or KnowledgePublicationStatus.PENDING),
                )
                for row in value
            ]
            links.sort(
                key=lambda row: (
                    row.sort_order,
                    row.discipline.sort_order,
                    row.discipline.name,
                )
            )
            published_links = [
                row
                for row in links
                if row.status == KnowledgePublicationStatus.PUBLISHED
            ]
            data["discipline_links"] = list(
                KnowledgeNodeDisciplineSerializer(
                    published_links,
                    many=True,
                    context={},
                ).data
            )
            data["related_disciplines"] = [
                row["discipline"]
                for row in data["discipline_links"]
                if row["relation_type"] != "primary"
            ]
            return

        relation_specs = {
            "subdiscipline_links": (
                Subdiscipline,
                "subdiscipline_id",
                KnowledgeNodeSubdiscipline,
                KnowledgeNodeSubdisciplineSerializer,
            ),
            "topic_links": (
                Topic,
                "topic_id",
                KnowledgeNodeTopic,
                KnowledgeNodeTopicSerializer,
            ),
        }
        related_model, id_field, relation_model, serializer_class = relation_specs[
            field_name
        ]
        related = cls._related_objects(
            related_model,
            [row.get(id_field) for row in value],
        )
        links = []
        for row in value:
            common = {
                "id": None,
                "node": target,
                id_field.removesuffix("_id"): related[str(row[id_field])],
                "source": str(row.get("source") or ""),
                "confidence": float(row.get("confidence") or 0),
                "sort_order": int(row.get("sort_order") or 0),
                "status": str(
                    row.get("status") or KnowledgePublicationStatus.PENDING
                ),
            }
            if field_name == "subdiscipline_links":
                common.update(
                    {
                        "is_primary": bool(row.get("is_primary", False)),
                        "relation_role": str(row.get("relation_role") or ""),
                    }
                )
            else:
                common["relation_label"] = str(row.get("relation_label") or "")
            links.append(relation_model(**common))
        links.sort(
            key=lambda row: (
                row.sort_order,
                getattr(
                    getattr(
                        row,
                        "subdiscipline"
                        if field_name == "subdiscipline_links"
                        else "topic",
                    ),
                    "name",
                    "",
                ),
            )
        )
        # These two public serializer methods intentionally expose only
        # published relations.  Apply the same visibility rule to the draft.
        published_links = [
            row
            for row in links
            if row.status == KnowledgePublicationStatus.PUBLISHED
        ]
        data[field_name] = list(
            serializer_class(published_links, many=True, context={}).data
        )

    @classmethod
    def _topic_special_overlay(
        cls,
        *,
        field_name: str,
        value,
        data: dict[str, Any],
    ) -> None:
        from catalog.models import RelationReviewStatus, TheorySchool

        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ValueError(f"{field_name} preview is not a list of objects")
        specs = {
            "discipline_relations": (Discipline, "discipline_id", "disciplines"),
            "theory_relations": (TheorySchool, "theory_school_id", "linked_theories"),
            "subdiscipline_relations": (
                Subdiscipline,
                "subdiscipline_id",
                "subdisciplines",
            ),
        }
        model, id_field, output_field = specs[field_name]
        related = cls._related_objects(model, [row.get(id_field) for row in value])
        output = []
        for row in value:
            item = related[str(row[id_field])]
            if (
                str(row.get("review_status") or RelationReviewStatus.SUGGESTED)
                != RelationReviewStatus.APPROVED
                or item.editorial_status != KnowledgePublicationStatus.PUBLISHED
            ):
                continue
            materialized = {
                "id": str(item.id),
                "name": item.name,
                "slug": item.slug,
            }
            if field_name == "discipline_relations":
                materialized["is_primary"] = bool(row.get("is_primary", False))
            else:
                materialized["relation_label"] = str(
                    row.get("relation_label") or ""
                )
            output.append(materialized)
        data[output_field] = output

    @classmethod
    def _reading_path_special_overlay(
        cls,
        *,
        target: ReadingPath,
        value,
        data: dict[str, Any],
    ) -> None:
        from uuid import NAMESPACE_URL, uuid5

        from catalog.models import ReadingPathItem, ReadingPathStage
        from catalog.theory_serializers import (
            ReadingPathItemSerializer,
            ReadingPathStageSerializer,
        )

        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ValueError("stage_groups preview is not a list of objects")
        if any(
            not isinstance(item, dict)
            for group in value
            for item in (group.get("items") or [])
        ):
            raise ValueError("stage_groups preview contains an invalid item")

        existing_stages = {
            str(row.pk): row
            for row in target.stages.all()
        }
        node_ids = [
            item.get("node")
            for group in value
            for item in (group.get("items") or [])
            if item.get("node")
        ]
        work_ids = [
            item.get("work")
            for group in value
            for item in (group.get("items") or [])
            if item.get("work")
        ]
        nodes = cls._related_objects(KnowledgeNode, node_ids) if node_ids else {}
        works = cls._related_objects(Work, work_ids) if work_ids else {}

        stages = []
        items = []
        reading_order = 0
        for fallback_position, group in enumerate(value):
            stage_id = str(group.get("id") or "").strip()
            if stage_id:
                canonical_stage = existing_stages.get(stage_id)
                if canonical_stage is None:
                    raise ValueError("stage_groups preview references a missing stage")
                stage = copy(canonical_stage)
            else:
                stage = ReadingPathStage(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"knowledge-preview:{target.pk}:stage:{fallback_position}",
                    ),
                    reading_path=target,
                )
                stage.created_at = None
                stage.updated_at = None
            stage.name = str(group.get("name") or "").strip()
            if not stage.name:
                raise ValueError("stage_groups preview contains an empty stage name")
            stage.description = str(group.get("description") or "")
            stage.position = int(group.get("position", fallback_position))
            stages.append((fallback_position, stage))

            source_items = list(group.get("items") or [])
            for item_fallback, row in sorted(
                enumerate(source_items),
                key=lambda entry: int(entry[1].get("position", entry[0])),
            ):
                node_id = str(row.get("node") or "").strip()
                work_id = str(row.get("work") or "").strip()
                if bool(node_id) == bool(work_id):
                    raise ValueError(
                        "stage_groups preview item must reference one canonical object"
                    )
                item = ReadingPathItem(
                    id=uuid5(
                        NAMESPACE_URL,
                        (
                            f"knowledge-preview:{target.pk}:stage:{stage.pk}:"
                            f"item:{reading_order}"
                        ),
                    ),
                    reading_path=target,
                    stage=stage,
                    stage_name=stage.name,
                    stage_description=stage.description,
                    node=nodes.get(node_id),
                    work=works.get(work_id),
                    recommendation_reason=str(
                        row.get("recommendation_reason") or ""
                    ),
                    prerequisite=str(row.get("prerequisite") or ""),
                    position=int(row.get("position", item_fallback)),
                    reading_order=reading_order,
                    is_required=bool(row.get("is_required", False)),
                    editorial_note=str(row.get("editorial_note") or ""),
                )
                items.append(item)
                reading_order += 1

        ordered_stages = [
            stage
            for _fallback, stage in sorted(
                stages,
                key=lambda entry: (entry[1].position, entry[0]),
            )
        ]
        data["stages"] = list(
            ReadingPathStageSerializer(ordered_stages, many=True, context={}).data
        )
        data["items"] = list(
            ReadingPathItemSerializer(items, many=True, context={}).data
        )
        public_items = []
        public_stage_ids = set()
        for row in data["items"]:
            work_is_public = bool(row.get("work") and row.get("work_data"))
            node_data = row.get("node_data") or {}
            node_is_public = bool(
                row.get("node")
                and node_data.get("status") == KnowledgePublicationStatus.PUBLISHED
            )
            if not (work_is_public or node_is_public):
                continue
            public_items.append(row)
            if row.get("stage"):
                public_stage_ids.add(str(row["stage"]))
        data["items"] = public_items
        data["stages"] = [
            stage
            for stage in data["stages"]
            if str(stage.get("id")) in public_stage_ids
        ]

    @classmethod
    def _special_overlay(
        cls,
        *,
        object_type: str,
        target,
        revision: EditorialRevision,
        data: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from catalog.services.editorial_revision import SPECIAL_FIELDS

        requested = (
            set(revision.changed_fields or [])
            | set((revision.patch or {}).keys())
        ) & SPECIAL_FIELDS
        preview = dict(revision.materialized_preview or {})
        patch = dict(revision.patch or {})
        supported = {
            **{
                kind: {
                    "aliases",
                    "discipline_links",
                    "subdiscipline_links",
                    "topic_links",
                }
                for kind in NODE_OBJECT_TYPES
            },
            "scholar": {"person"},
            "topic": {
                "discipline_relations",
                "theory_relations",
                "subdiscipline_relations",
            },
            "reading_path": {"stage_groups"},
        }.get(object_type, set())
        unsupported = set(requested - supported)
        materialized = dict(data)
        for field_name in sorted(requested & supported):
            if field_name in preview:
                value = preview[field_name]
            elif field_name in patch:
                value = patch[field_name]
            else:
                unsupported.add(field_name)
                continue
            try:
                if object_type in NODE_OBJECT_TYPES:
                    cls._node_special_overlay(
                        target=target,
                        field_name=field_name,
                        value=value,
                        data=materialized,
                    )
                elif object_type == "scholar":
                    if not isinstance(value, dict):
                        raise ValueError("person preview is not an object")
                    person = dict(materialized.get("person") or {})
                    for key in (
                        "preferred_name",
                        "original_name",
                        "aliases",
                        "birth_year",
                        "death_year",
                        "biography",
                    ):
                        if key in value:
                            person[key] = value[key]
                    from catalog.services.aliases import search_aliases

                    person["aliases"] = search_aliases(
                        person.get("preferred_name", ""),
                        person.get("original_name", ""),
                        *(person.get("aliases") or []),
                    )
                    materialized["person"] = person
                elif object_type == "topic":
                    cls._topic_special_overlay(
                        field_name=field_name,
                        value=value,
                        data=materialized,
                    )
                else:
                    cls._reading_path_special_overlay(
                        target=target,
                        value=value,
                        data=materialized,
                    )
            except (
                AttributeError,
                DjangoValidationError,
                KeyError,
                TypeError,
                ValueError,
            ):
                unsupported.add(field_name)
        return materialized, sorted(unsupported)

    @classmethod
    def _serialize(cls, object_type: str, target, *, revision=None) -> tuple[dict, str, list[str]]:
        serializer_class = cls._serializer(object_type)
        unsupported_fields: list[str] = []
        if revision is not None:
            if object_type == "work":
                from catalog.serializers import AdminWorkPagePreviewSerializer

                edition = (
                    target.editions.filter(is_primary=True).order_by(
                        "-published_at", "-publication_year", "-created_at"
                    ).first()
                    or target.editions.order_by("-created_at").first()
                )
                if edition is None:
                    return {}, AdminWorkPagePreviewSerializer.__name__, ["edition"]
                unsupported_fields = sorted(
                    set(revision.changed_fields or []) & {"reader"}
                )
                return (
                    dict(
                        AdminWorkPagePreviewSerializer(
                            target,
                            context={
                                "preview_edition": edition,
                                "editorial_preview": revision.materialized_preview,
                            },
                        ).data
                    ),
                    AdminWorkPagePreviewSerializer.__name__,
                    unsupported_fields,
                )
            target = cls._draft_target(cls.TARGET_TYPES[object_type], target, revision)
        serialized = dict(serializer_class(target, context={}).data)
        if revision is not None:
            serialized, unsupported_fields = cls._special_overlay(
                object_type=object_type,
                target=target,
                revision=revision,
                data=serialized,
            )
        return serialized, serializer_class.__name__, unsupported_fields

    @classmethod
    def enrich(cls, *, object_type: str, target, selection: dict[str, Any]) -> dict[str, Any]:
        from catalog.services.dependency_engine import projection_types_for
        from catalog.services.editorial_revision import TARGET_POLICIES

        target_type = cls.TARGET_TYPES.get(object_type)
        policy = TARGET_POLICIES.get(target_type)
        revision = EditorialRevision.objects.filter(
            target_type=target_type,
            target_id=target.pk,
            status=EditorialRevision.Status.DRAFT,
        ).order_by("-revision").first()
        canonical_public, serializer_name, _unsupported = cls._serialize(object_type, target)
        is_public = cls._is_public(object_type, target)
        draft_public: dict[str, Any] | None = None
        draft_serializer = serializer_name
        unsupported_fields: list[str] = []
        draft_source = "editorial_revision"
        if revision is not None:
            draft_public, draft_serializer, unsupported_fields = cls._serialize(
                object_type,
                target,
                revision=revision,
            )
        elif not is_public:
            # An unpublished canonical row is itself the current editable
            # draft.  It must remain previewable before the first revision is
            # needed, while the published perspective stays unavailable.
            draft_public = canonical_public
            draft_source = "canonical_draft"

        completeness_source = draft_public if draft_public is not None else canonical_public
        modules = []
        for label, fields in PUBLIC_MODULE_FIELDS[object_type]:
            populated = [field for field in fields if _has_public_content(completeness_source.get(field))]
            modules.append(
                {
                    "label": label,
                    "serializer_fields": list(fields),
                    "populated_fields": populated,
                    "missing_fields": [field for field in fields if field not in populated],
                    "complete": len(populated) == len(fields),
                    "available": bool(populated),
                }
            )

        draft_available = draft_public is not None and bool(draft_public)
        selection["content_completeness"] = {
            "source": "public_serializer",
            "serializer": draft_serializer if draft_available else serializer_name,
            "perspective": "draft" if draft_available else "published",
            "perspective_source": draft_source if draft_available else "published",
            "complete_module_count": sum(row["complete"] for row in modules),
            "module_count": len(modules),
            "unsupported_preview_fields": unsupported_fields,
            "modules": modules,
        }
        selection["preview_perspectives"] = {
            "published": {
                "source": "published",
                "available": is_public,
                "serializer": serializer_name,
                "data": canonical_public if is_public else None,
                "reason": "" if is_public else "object_not_published",
            },
            "draft": {
                "source": draft_source,
                "available": draft_available,
                "complete": draft_available and not unsupported_fields,
                "serializer": draft_serializer,
                "revision_id": str(revision.id) if revision else None,
                "data": draft_public if draft_available else None,
                "unsupported_preview_fields": unsupported_fields,
                "reason": (
                    "partial_preview_unsupported_fields"
                    if draft_available and unsupported_fields
                    else ""
                    if draft_available
                    else "no_draft_revision"
                    if revision is None
                    else "public_serializer_preview_unavailable"
                ),
            },
        }
        published_route = selection.get("preview_url", "") if is_public else ""
        draft_route = f"/admin/preview/knowledge/{object_type}/{target.pk}"
        if object_type == "work":
            edition = (
                target.editions.filter(is_primary=True).order_by(
                    "-published_at", "-publication_year", "-created_at"
                ).first()
                or target.editions.order_by("-created_at").first()
            )
            if edition is not None:
                draft_route = f"/admin/preview/works/{edition.pk}"
        selection["preview_perspectives"]["published"]["route"] = published_route
        selection["preview_perspectives"]["draft"]["route"] = draft_route
        selection["preview_routes"] = {
            "published": published_route,
            "draft": draft_route,
            "draft_is_protected": True,
            "uses_public_serializer": True,
        }
        selection["editor_adapter"] = {
            "name": "KnowledgeObjectEditorAdapter",
            "available": policy is not None,
            "reason": "" if policy is not None else "mature_mutation_service_unavailable",
            "target_type": target_type,
            "editable_fields": sorted(policy.editable_fields) if policy else [],
            "mutation_mode": "editorial_revision" if policy else "unavailable",
            "create_revision": (
                {"method": "POST", "url": "/catalog/admin/editorial-revisions/"}
                if policy
                else None
            ),
            "canonical_endpoint": selection.get("editor_url", ""),
        }
        projection_types = list(projection_types_for(target_type))
        impact = selection.setdefault("frontend_impact", {})
        impact["source"] = "dependency_engine_and_public_serializer"
        impact["dependency_object_type"] = target_type
        impact["projection_types"] = projection_types
        impact["public_serializer"] = serializer_name
        impact["modules"] = [row["label"] for row in modules]
        impact["module_readiness"] = modules
        if object_type in {"scholar", "theory", "topic"}:
            from catalog.services.public_knowledge_control import (
                build_public_control,
            )

            public_control = build_public_control(
                object_type=object_type,
                target=target,
                published_data=canonical_public if is_public else None,
                draft_data=draft_public if draft_available else None,
                revision=revision,
                candidate_available=bool(selection.get("ai_candidates")),
                evidence_available=bool(selection.get("evidence")),
            )
            selection["public_control"] = public_control
            impact["public_visibility"] = public_control["eligibility"]["eligible"]
            impact["targets"] = [
                {
                    "label": row["display_name"],
                    "url": row["route"],
                    "modules": [module["display_name"] for module in row["modules"]],
                    "preview_url": row["preview"]["draft_route"],
                }
                for row in public_control["page_tree"]
            ]
        return selection


def _node_directory(query: str, object_type: str, limit: int) -> list[dict[str, Any]]:
    queryset = KnowledgeNode.objects.select_related("primary_discipline").filter(
        node_type=NODE_OBJECT_TYPES[object_type]
    )
    if query:
        queryset = queryset.filter(
            Q(canonical_name_zh__icontains=query)
            | Q(canonical_name_en__icontains=query)
            | Q(slug__icontains=query)
            | Q(aliases__alias__icontains=query)
        ).distinct()
    return [
        {
            "id": str(row.id),
            "object_type": object_type,
            "label": row.canonical_name_zh,
            "secondary_label": row.canonical_name_en,
            "status": row.status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("sort_order", "canonical_name_zh")[:limit]
    ]


def _scholar_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = ScholarProfile.objects.select_related("person")
    if query:
        queryset = queryset.filter(
            Q(person__preferred_name__icontains=query)
            | Q(person__original_name__icontains=query)
            | Q(slug__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "scholar",
            "label": row.person.preferred_name,
            "secondary_label": row.person.original_name,
            "status": row.editorial_status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("person__sort_name", "person__preferred_name")[:limit]
    ]


def _topic_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = Topic.objects.all()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(slug__icontains=query)
            | Q(search_aliases__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "topic",
            "label": row.name,
            "secondary_label": "",
            "status": row.editorial_status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("name")[:limit]
    ]


def _discipline_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = Discipline.objects.all()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(foreign_name__icontains=query)
            | Q(code__icontains=query)
            | Q(slug__icontains=query)
            | Q(search_aliases__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "discipline",
            "label": row.name,
            "secondary_label": row.foreign_name or row.code,
            "status": row.editorial_status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("sort_order", "name")[:limit]
    ]


def _subdiscipline_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = Subdiscipline.objects.select_related("discipline", "parent")
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(foreign_name__icontains=query)
            | Q(slug__icontains=query)
            | Q(search_aliases__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "subdiscipline",
            "label": row.name,
            "secondary_label": row.foreign_name or row.discipline.name,
            "status": row.editorial_status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by(
            "discipline__sort_order", "discipline__name", "name"
        )[:limit]
    ]


def _reading_path_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = ReadingPath.objects.select_related("primary_discipline")
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(introduction__icontains=query)
            | Q(audience__icontains=query)
            | Q(slug__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "reading_path",
            "label": row.title,
            "secondary_label": (
                row.primary_discipline.name
                if row.primary_discipline_id
                else row.audience
            ),
            "status": row.status,
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("sort_order", "title")[:limit]
    ]


def _important_work_queryset() -> QuerySet[Work]:
    """Works with an explicit Knowledge Core or public-curation signal."""

    return Work.objects.filter(
        Q(is_featured=True)
        | Q(curated_claims__isnull=False)
        | Q(node_relations__isnull=False)
        | Q(topic_relations__isnull=False)
        | Q(reading_path_items__isnull=False)
    ).distinct()


def _work_status(work: Work) -> str:
    states = [edition.state for edition in work.editions.all()]
    if PublicationState.PUBLISHED in states:
        return PublicationState.PUBLISHED
    if PublicationState.READY in states:
        return PublicationState.READY
    return PublicationState.DRAFT


def _work_directory(query: str, limit: int) -> list[dict[str, Any]]:
    queryset = _important_work_queryset().prefetch_related("editions")
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(original_title__icontains=query)
            | Q(uniform_title__icontains=query)
            | Q(search_aliases__icontains=query)
        )
    return [
        {
            "id": str(row.id),
            "object_type": "work",
            "label": row.title,
            "secondary_label": row.original_title or row.get_document_type_display(),
            "status": _work_status(row),
            "updated_at": row.updated_at,
        }
        for row in queryset.order_by("title")[:limit]
    ]


def _directory(*, query: str, object_type: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    node_counts = {
        key: KnowledgeNode.objects.filter(node_type=node_type).count()
        for key, node_type in NODE_OBJECT_TYPES.items()
    }
    counts = {
        **node_counts,
        "scholar": ScholarProfile.objects.count(),
        "discipline": Discipline.objects.count(),
        "subdiscipline": Subdiscipline.objects.count(),
        "topic": Topic.objects.count(),
        "reading_path": ReadingPath.objects.count(),
        "work": _important_work_queryset().count(),
    }
    requested_types = [object_type] if object_type in OBJECT_TYPES else list(OBJECT_TYPES)
    rows: list[dict[str, Any]] = []
    # Each source is sliced before materialization and the combined result is
    # sliced again.  An `all` request therefore cannot fan out without bound.
    for kind in requested_types:
        if kind in NODE_OBJECT_TYPES:
            rows.extend(_node_directory(query, kind, limit))
        elif kind == "scholar":
            rows.extend(_scholar_directory(query, limit))
        elif kind == "topic":
            rows.extend(_topic_directory(query, limit))
        elif kind == "discipline":
            rows.extend(_discipline_directory(query, limit))
        elif kind == "subdiscipline":
            rows.extend(_subdiscipline_directory(query, limit))
        elif kind == "reading_path":
            rows.extend(_reading_path_directory(query, limit))
        else:
            rows.extend(_work_directory(query, limit))
    rows.sort(key=lambda row: (str(row["label"]).casefold(), row["object_type"], row["id"]))
    return rows[:limit], counts


def _evidence_payload(span) -> dict[str, Any]:
    payload = evidence_span_envelope(span).as_dict()
    payload["text"] = _clip(payload["text"], 1600)
    return payload


def _snippet_payload(snippet: EvidenceSnippet) -> dict[str, Any]:
    page = snippet.page_number
    return {
        "id": str(snippet.id),
        "kind": "collection_text_compat",
        "source": {
            "work_id": str(snippet.work_id),
            "work_title": snippet.work.title,
            "asset_id": str(snippet.file_id),
        },
        "text": _clip(snippet.quote, 1600),
        "locator": {
            "page": page,
            "printed_page_label": snippet.printed_page_label,
            "bbox": snippet.bounding_box,
        },
        "quality": {
            "ocr_confidence": snippet.ocr_confidence,
            "semantic_confidence": snippet.semantic_confidence,
            "review_status": snippet.review_status,
        },
        "provenance": {"extraction_method": snippet.extraction_method},
        "reader_url": f"/reader/{snippet.file_id}?page={page}",
        "pdf_url": f"/api/catalog/assets/{snippet.file_id}/manifest/",
    }


def _claim_evidence_prefetch() -> Prefetch:
    return Prefetch(
        "evidence_links",
        queryset=ClaimEvidence.objects.select_related(
            "evidence_span__page",
            "evidence_span__document_revision__asset__edition__work",
        ).prefetch_related(
            "evidence_span__document_revision__asset__edition__contributions__person"
        ).order_by("sort_order", "created_at")[:MAX_SECTION_ROWS],
        to_attr="studio_evidence_links",
    )


def _curated_claims(queryset: QuerySet[CuratedClaim]) -> list[dict[str, Any]]:
    rows = queryset.prefetch_related(_claim_evidence_prefetch()).order_by(
        "kind", "sort_order", "created_at"
    )[:MAX_SECTION_ROWS]
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "title": row.title,
            "proposition": _clip(row.proposition, 1600),
            "editorial_note": _clip(row.editorial_note, 800),
            "status": row.status,
            "adopted_from": str(row.adopted_from_id) if row.adopted_from_id else None,
            "evidence": [
                {
                    **_evidence_payload(link.evidence_span),
                    "claim_role": link.role,
                    "claim_confidence": link.confidence,
                }
                for link in row.studio_evidence_links
            ],
        }
        for row in rows
    ]


def _derived_claims(queryset: QuerySet[DerivedClaim]) -> list[dict[str, Any]]:
    rows = queryset.filter(status=DerivedClaim.Status.ACTIVE).select_related(
        "primary_evidence__page",
        "primary_evidence__document_revision__asset__edition__work",
    ).prefetch_related(
        "primary_evidence__document_revision__asset__edition__contributions__person"
    ).order_by("-importance_score", "-quality_score", "created_at")[:MAX_SECTION_ROWS]
    return [
        {
            "id": str(row.id),
            "proposition": _clip(row.proposition, 1600),
            "claim_type": row.claim_type,
            "attribution": row.attribution,
            "polarity": row.polarity,
            "qualifiers": _bounded_json(row.qualifiers),
            "quality_score": row.quality_score,
            "importance_score": row.importance_score,
            "shadow": row.shadow,
            "document_revision_id": str(row.document_revision_id),
            "evidence": _evidence_payload(row.primary_evidence),
        }
        for row in rows
    ]


def _claim_evidence(
    *,
    curated: list[dict[str, Any]],
    derived: list[dict[str, Any]],
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows = list(existing or [])
    for claim in curated:
        rows.extend(claim.get("evidence") or [])
    for claim in derived:
        evidence = claim.get("evidence")
        if evidence:
            rows.append(evidence)
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("kind") or ""), str(row.get("id") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= MAX_SECTION_ROWS:
            break
    return result


def _projection_payload(object_type: str, object_id) -> tuple[list[str], list[dict[str, Any]]]:
    from catalog.services.dependency_engine import projection_types_for

    projection_types = projection_types_for(object_type)
    labels = dict(ProjectionState.ProjectionType.choices)
    names = {
        ProjectionState.ProjectionType.QUERY_LEXICON: "QueryLexicon",
        ProjectionState.ProjectionType.FULLTEXT: "Fulltext",
        ProjectionState.ProjectionType.SEMANTIC: "Semantic",
        ProjectionState.ProjectionType.CLAIM_INDEX: "Claim Index",
        ProjectionState.ProjectionType.KNOWLEDGE_GRAPH: "Knowledge Graph",
        ProjectionState.ProjectionType.TIMELINE: "Timeline",
        ProjectionState.ProjectionType.RECOMMENDATION: "Recommendation",
        ProjectionState.ProjectionType.READING_PATH_SUPPORT: "Reading Path support",
        ProjectionState.ProjectionType.PUBLIC: "Public",
    }
    state_by_type = {
        row.projection_type: row
        for row in ProjectionState.objects.filter(
            object_type=object_type,
            object_id=object_id,
            projection_type__in=projection_types,
        )
    }
    rows: list[dict[str, Any]] = []
    for projection_type in projection_types:
        state = state_by_type.get(projection_type)
        rows.append(
            {
                "type": projection_type,
                "label": labels.get(projection_type, projection_type),
                "name": names.get(projection_type, projection_type),
                "status": state.status if state else "not_materialized",
                "source_revision": state.source_revision if state else 0,
                "projected_revision": state.projected_revision if state else 0,
                "lag": (
                    max(0, state.source_revision - state.projected_revision)
                    if state
                    else 0
                ),
                "last_error_code": state.last_error_code if state else "",
            }
        )
    return [names.get(value, value) for value in projection_types], rows


def _frontend_impact(
    *,
    object_type: str,
    object_id,
    public_visibility: bool,
    modules: list[str],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    projections, states = _projection_payload(object_type, object_id)
    return {
        "public_visibility": public_visibility,
        "modules": modules,
        "projections": projections,
        "projection_states": states,
        "targets": targets[:MAX_SECTION_ROWS],
    }


def _mutation_contract(
    target_type: str,
    target_id,
    *,
    published: bool,
) -> dict[str, Any]:
    current_revision = (
        CanonicalObjectRevision.objects.filter(
            object_type=target_type,
            object_id=target_id,
        )
        .values_list("current_revision", flat=True)
        .first()
        or 0
    )
    return {
        "target_type": target_type,
        "target_id": str(target_id),
        "current_revision": current_revision,
        "published_changes_require_revision": published,
        "draft_url": "/catalog/admin/editorial-revisions/",
        "revisions_url": (
            "/catalog/admin/editorial-revisions/"
            f"?target_type={target_type}&target_id={target_id}"
        ),
        "single_editor_publish": True,
        "canonical_commit_is_atomic": True,
        "dependency_propagation_on_publish": True,
    }


def _revision_rows(target_type: str, target_id) -> list[dict[str, Any]]:
    current_revision = (
        CanonicalObjectRevision.objects.filter(
            object_type=target_type,
            object_id=target_id,
        )
        .values_list("current_revision", flat=True)
        .first()
        or 0
    )
    return [
        {
            "id": str(row.id),
            "revision": row.revision,
            "base_revision": row.base_revision,
            "status": row.status,
            "changed_fields": row.changed_fields,
            "change_note": row.change_note,
            "created_at": row.created_at,
            "published_at": row.published_at,
            "patch": _bounded_json(row.patch),
            "has_conflict": (
                row.status == EditorialRevision.Status.DRAFT
                and row.base_revision != current_revision
            ),
            "publish_url": (
                f"/catalog/admin/editorial-revisions/{row.id}/publish/"
                if row.status == EditorialRevision.Status.DRAFT
                else ""
            ),
        }
        for row in EditorialRevision.objects.filter(
            target_type=target_type,
            target_id=target_id,
        ).order_by("-revision")[:MAX_SECTION_ROWS]
    ]


def _latest_preview(target_type: str, target_id, canonical: dict[str, Any]) -> dict[str, Any]:
    draft = EditorialRevision.objects.filter(
        target_type=target_type,
        target_id=target_id,
        status=EditorialRevision.Status.DRAFT,
    ).order_by("-revision").first()
    return {
        "source": "editorial_revision" if draft else "canonical",
        "revision_id": str(draft.id) if draft else None,
        "materialized": _bounded_json(draft.materialized_preview if draft else canonical),
    }


def _enrichment_candidate_payload(row: EnrichmentCandidate) -> dict[str, Any]:
    evidence = [
        {
            "id": str(item.id),
            "source_title": item.source_title,
            "canonical_url": item.canonical_url,
            "supporting_text": _clip(item.supporting_text, 1200),
            "source_class": item.source_class,
            "retrieved_at": item.retrieved_at,
        }
        for item in row.evidence_records.filter(is_current=True)[:8]
    ]
    return attach_candidate_action_descriptors(
        {
            "id": str(row.id),
            "candidate_type": "enrichment",
            "field_name": row.field_name,
            "candidate_kind": row.candidate_kind,
            "proposed_value": _bounded_json(row.proposed_value),
            "confidence": row.confidence,
            "conflicts": _bounded_json(row.conflicts),
            "status": row.status,
            "source": row.source_class,
            "evidence": evidence,
            "evidence_count": len(evidence),
            "evidence_status": "evidence" if evidence else "lead_only",
            "decision_url": f"/catalog/admin/field-enrichment/candidates/{row.id}/decision/",
            "available_actions": ["inspect", "accept", "reject"],
        }
    )


def _enrichment_candidates(target_type: str, target_id) -> list[dict[str, Any]]:
    rows = EnrichmentCandidate.objects.filter(
        target_type=target_type,
        target_id=target_id,
        status=EnrichmentCandidate.Status.PENDING,
    ).prefetch_related("evidence_records").order_by(
        "-confidence", "created_at"
    )[:MAX_SECTION_ROWS]
    return [_enrichment_candidate_payload(row) for row in rows]


def _theory_review_candidate(row: TheoryReviewTask) -> dict[str, Any]:
    pending = row.status in {
        TheoryReviewTask.TaskStatus.PENDING,
        TheoryReviewTask.TaskStatus.NEEDS_CHANGES,
        TheoryReviewTask.TaskStatus.INSUFFICIENT_EVIDENCE,
    }
    label = row.suggested_node_name or (
        row.candidate_node.canonical_name_zh if row.candidate_node_id else "知识关系"
    )
    actions = ["inspect"]
    action_payloads: dict[str, dict[str, Any]] = {}
    if pending:
        if row.task_type == TheoryReviewTask.TaskType.WORK_NODE and row.candidate_node_id:
            actions.append("accept")
            action_payloads["accept"] = {
                "action": "confirm",
                "candidate_node": str(row.candidate_node_id),
                "relation_type": row.suggested_relation_type,
            }
        elif row.task_type == TheoryReviewTask.TaskType.NEW_NODE:
            actions.append("create_draft")
            action_payloads["create_draft"] = {
                "action": "create_node",
                "canonical_name_zh": row.suggested_node_name,
            }
        actions.extend(["reject", "defer"])
    evidence = []
    if row.evidence_text or row.evidence_pages:
        evidence.append(
            {
                "supporting_text": _clip(row.evidence_text, 1200),
                "locator": {"pages": list(row.evidence_pages or [])[:20]},
                "source_class": "pdf_evidence",
            }
        )
    return attach_candidate_action_descriptors(
        {
            "id": str(row.id),
            "candidate_type": "theory_review",
            "field_name": row.task_type,
            "proposed_value": label or row.suggested_relation_type,
            "confidence": row.confidence,
            "conflicts": [],
            "status": "pending" if pending else row.status,
            "source": "library_research",
            "evidence": evidence,
            "evidence_count": len(evidence),
            "evidence_status": "evidence" if evidence else "none",
            "decision_url": f"/catalog/admin/theory-system/review-tasks/{row.id}/action/",
            "available_actions": actions,
            "action_payloads": action_payloads,
        }
    )


def _debate_candidate_payload(row: DebateCandidate) -> dict[str, Any]:
    evidence = _bounded_json(
        row.evidence_pack.envelope_snapshot[:8] if row.evidence_pack_id else []
    )
    pending = row.status == DebateCandidate.Status.PENDING
    return attach_candidate_action_descriptors(
        {
            "id": str(row.id),
            "candidate_type": "debate_discovery",
            "field_name": "canonical_question",
            "label": row.title,
            "proposed_value": _clip(row.canonical_question, 1200),
            "confidence": row.quality_score,
            "importance": row.importance_score,
            "conflicts": {"score": row.conflict_score},
            "status": row.status,
            "source": "debate_discovery",
            "evidence": evidence,
            "evidence_count": len(evidence),
            "evidence_status": "evidence" if evidence else "none",
            "decision_url": f"/catalog/admin/research/generated-candidates/debate/{row.id}/decision/",
            "available_actions": (
                ["inspect", "accept", "accept_with_edit", "defer", "reject"]
                if pending
                else ["inspect"]
            ),
            "action_payloads": {
                "accept": {
                    "title": row.title,
                    "canonical_question": row.canonical_question,
                    "summary": row.summary,
                },
                "accept_with_edit": {
                    "title": row.title,
                    "canonical_question": row.canonical_question,
                    "summary": row.summary,
                },
            },
            "action_options": {
                "accept_with_edit": {
                    "editable": True,
                    "value_field": "canonical_question",
                }
            },
        }
    )


def _reading_path_candidate_payload(row: ReadingPathCandidate) -> dict[str, Any]:
    evidence = _bounded_json(
        row.evidence_pack.envelope_snapshot[:8] if row.evidence_pack_id else []
    )
    pending = row.status == ReadingPathCandidate.Status.PENDING
    return attach_candidate_action_descriptors(
        {
            "id": str(row.id),
            "candidate_type": "reading_path_generation",
            "field_name": "stages",
            "label": row.title,
            "proposed_value": _bounded_json(row.stages),
            "confidence": row.quality_score,
            "importance": row.importance_score,
            "conflicts": [],
            "status": row.status,
            "source": "reading_path_generation",
            "evidence": evidence,
            "evidence_count": len(evidence),
            "evidence_status": "evidence" if evidence else "none",
            "decision_url": f"/catalog/admin/research/generated-candidates/reading_path/{row.id}/decision/",
            "available_actions": (
                ["inspect", "accept", "accept_with_edit", "defer", "reject"]
                if pending
                else ["inspect"]
            ),
            "action_payloads": {
                "accept": {
                    "title": row.title,
                    "target_audience": row.target_audience,
                    "learning_goal": row.learning_goal,
                    "stages": row.stages,
                },
                "accept_with_edit": {
                    "title": row.title,
                    "target_audience": row.target_audience,
                    "learning_goal": row.learning_goal,
                    "stages": row.stages,
                },
            },
            "action_options": {
                "accept_with_edit": {
                    "editable": True,
                    "value_field": "learning_goal",
                }
            },
        }
    )


def _related_work_ids(object_type: str, target) -> list[UUID]:
    if target is None:
        return []
    if object_type == "work":
        return [target.id]
    if object_type in NODE_OBJECT_TYPES:
        queryset = target.work_relations.values_list("work_id", flat=True)
    elif object_type == "scholar":
        queryset = target.person.contributions.filter(approved=True).values_list(
            "edition__work_id", flat=True
        )
    elif object_type in {"discipline", "subdiscipline", "topic"}:
        queryset = target.work_relations.values_list("work_id", flat=True)
    elif object_type == "reading_path":
        queryset = target.items.filter(work_id__isnull=False).values_list(
            "work_id", flat=True
        )
    else:
        return []
    return list(dict.fromkeys(queryset[:100]))


def _enrichment_target(object_type: str, target) -> tuple[str, UUID] | None:
    if target is None:
        return None
    if object_type in NODE_OBJECT_TYPES:
        return EnrichmentCandidate.TargetType.KNOWLEDGE_NODE, target.id
    if object_type == "scholar":
        return EnrichmentCandidate.TargetType.PERSON, target.person_id
    target_types = {
        "work": EnrichmentCandidate.TargetType.WORK,
        "discipline": EnrichmentCandidate.TargetType.DISCIPLINE,
        "subdiscipline": EnrichmentCandidate.TargetType.SUBDISCIPLINE,
        "topic": EnrichmentCandidate.TargetType.TOPIC,
        "reading_path": EnrichmentCandidate.TargetType.READING_PATH,
    }
    target_type = target_types.get(object_type)
    return (target_type, target.id) if target_type else None


def _evidence_pack_subjects(object_type: str, target) -> list[tuple[str, str]]:
    if target is None:
        return []
    subjects = [(object_type, str(target.id))]
    if object_type in NODE_OBJECT_TYPES:
        subjects.append(("knowledge_node", str(target.id)))
    elif object_type == "scholar":
        subjects.extend(
            [
                ("person", str(target.person_id)),
                ("scholar_profile", str(target.id)),
            ]
        )
    return list(dict.fromkeys(subjects))


def _evidence_pack_filter(object_type: str, target) -> Q:
    query = Q(pk__isnull=True)
    for subject_type, subject_id in _evidence_pack_subjects(object_type, target):
        query |= Q(
            evidence_pack__subject_type=subject_type,
            evidence_pack__subject_id=subject_id,
        )
    return query


def _pending_generated_candidates(object_type: str, target, work_ids: list[UUID]):
    if target is None:
        debates = DebateCandidate.objects.filter(status=DebateCandidate.Status.PENDING)
        reading_paths = ReadingPathCandidate.objects.filter(
            status=ReadingPathCandidate.Status.PENDING
        )
    else:
        debate_filter = _evidence_pack_filter(object_type, target)
        if object_type in NODE_OBJECT_TYPES:
            debate_filter |= Q(suggested_node_id=target.id)
        if work_ids:
            debate_filter |= Q(claim_links__claim__work_id__in=work_ids)
        debates = DebateCandidate.objects.filter(
            debate_filter,
            status=DebateCandidate.Status.PENDING,
        ).distinct()
        reading_paths = ReadingPathCandidate.objects.filter(
            _evidence_pack_filter(object_type, target),
            status=ReadingPathCandidate.Status.PENDING,
        ).distinct()
    return (
        debates.select_related("evidence_pack").order_by(
            "-importance_score", "-quality_score", "created_at"
        ),
        reading_paths.select_related("evidence_pack").order_by(
            "-importance_score", "-quality_score", "created_at"
        ),
    )


def _unconsumed_evidence(work_ids: list[UUID] | None = None):
    queryset = EvidenceSpan.objects.filter(
        is_stale=False,
        document_revision__is_active=True,
    ).exclude(
        primary_for_claims__status=DerivedClaim.Status.ACTIVE,
    ).exclude(
        claim_links__derived_claim__status=DerivedClaim.Status.ACTIVE,
    ).exclude(
        claim_links__curated_claim__status__in=(
            CuratedClaim.Status.DRAFT,
            CuratedClaim.Status.PUBLISHED,
        ),
    )
    if work_ids is not None:
        if not work_ids:
            return queryset.none()
        queryset = queryset.filter(
            document_revision__asset__edition__work_id__in=work_ids
        )
    return queryset.select_related(
        "page",
        "document_revision__asset__edition__work",
    ).prefetch_related(
        "document_revision__asset__edition__contributions__person"
    ).distinct().order_by("-created_at", "-quality")


def _knowledge_update_payload(
    payload: dict[str, Any],
    *,
    update_kind: str,
    signal_sources: list[str],
    why_now: str,
    priority: float,
    decision_target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = dict(payload)
    output.update(
        {
            "knowledge_update_id": f"{update_kind}:{payload.get('id', '')}",
            "knowledge_update_kind": update_kind,
            "signal_sources": signal_sources,
            "why_now": why_now,
            "knowledge_update_priority": round(max(0.0, min(float(priority), 1.0)), 6),
            "decision_target": decision_target or {},
            "canonical_write_policy": "human_decision_only",
            "derived_read_model": True,
        }
    )
    return output


def _claim_update_candidates(
    work_ids: list[UUID],
    *,
    reviewer=None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    from catalog.services.claims.curation import high_value_claim_candidates

    output: list[dict[str, Any]] = []
    works = {
        row.id: row
        for row in Work.objects.filter(pk__in=work_ids).only("id", "title")
    }
    for work_id in work_ids:
        work = works.get(work_id)
        if work is None:
            continue
        for payload in high_value_claim_candidates(
            work,
            reviewer=reviewer,
            limit=KNOWLEDGE_UPDATE_LIMIT,
        ):
            output.append(
                _knowledge_update_payload(
                    payload,
                    update_kind="claim_curation",
                    signal_sources=["derived_claim", "evidence_span"],
                    why_now="机器命题已通过原文定位、去重和重要性排序，可由 Editor 决定是否策展。",
                    priority=float(payload.get("confidence") or 0),
                    decision_target={
                        "object_type": "work",
                        "object_id": str(work.id),
                        "label": work.title,
                    },
                )
            )
    output.sort(
        key=lambda row: (-float(row.get("knowledge_update_priority") or 0), row["knowledge_update_id"])
    )
    return output[:limit]


def _evidence_update_candidates(
    work_ids: list[UUID] | None,
    *,
    limit: int = 1,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for span in _unconsumed_evidence(work_ids)[:limit]:
        envelope = _evidence_payload(span)
        payload = attach_candidate_action_descriptors(
            {
                "id": str(span.id),
                "candidate_type": "evidence_review",
                "field_name": "knowledge_evidence",
                "label": _clip(span.section, 160) or "尚未形成 Claim 的馆藏原文",
                "proposed_value": _clip(span.original_text, 1200),
                "status": "pending",
                "source": "evidence_span",
                "confidence": span.quality,
                "conflicts": [],
                "evidence": [envelope],
                "evidence_count": 1,
                "evidence_status": "evidence",
                "available_actions": ["inspect"],
            }
        )
        output.append(
            _knowledge_update_payload(
                payload,
                update_kind="evidence_review",
                signal_sources=["evidence_span"],
                why_now="该原文已有稳定页码和 provenance，但尚未被有效 Claim 消费。",
                priority=span.quality * 0.75,
                decision_target={
                    "object_type": "work",
                    "object_id": envelope["source"]["work_id"],
                    "label": envelope["source"]["work_title"],
                },
            )
        )
    return output


def _bounded_diverse_suggestions(
    buckets: list[list[dict[str, Any]]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for bucket in buckets:
        if bucket:
            chosen.append(bucket[0])
            remaining.extend(bucket[1:])
    remaining.sort(
        key=lambda row: (-float(row.get("knowledge_update_priority") or 0), row["knowledge_update_id"])
    )
    chosen.extend(remaining)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in chosen:
        identifier = str(row.get("knowledge_update_id") or "")
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        output.append(row)
        if len(output) >= limit:
            break
    return output


def _knowledge_update_bundle(
    *,
    object_type: str = "",
    target=None,
    reviewer=None,
    global_scope: bool = False,
) -> dict[str, Any]:
    work_ids = _related_work_ids(object_type, target)
    if global_scope:
        work_ids = []
        for work_id in DerivedClaim.objects.filter(
            status=DerivedClaim.Status.ACTIVE,
            document_revision__is_active=True,
            primary_evidence__is_stale=False,
        ).order_by("-importance_score", "-quality_score").values_list(
            "work_id", flat=True
        )[:100]:
            if work_id not in work_ids:
                work_ids.append(work_id)
            if len(work_ids) >= 8:
                break

    enrichment_target = _enrichment_target(object_type, target)
    enrichment_queryset = EnrichmentCandidate.objects.filter(
        status=EnrichmentCandidate.Status.PENDING,
    )
    if not global_scope:
        if enrichment_target is None:
            enrichment_queryset = enrichment_queryset.none()
        else:
            enrichment_queryset = enrichment_queryset.filter(
                target_type=enrichment_target[0],
                target_id=enrichment_target[1],
            )
    enrichment_queryset = enrichment_queryset.prefetch_related(
        "evidence_records"
    ).order_by("-confidence", "created_at")
    enrichment_updates = [
        _knowledge_update_payload(
            _enrichment_candidate_payload(row),
            update_kind="field_enrichment",
            signal_sources=["enrichment_candidate"],
            why_now="字段研究已有待处理候选；采用仍由现有字段决策端点校验证据与身份。",
            priority=row.confidence,
            decision_target={
                "object_type": row.target_type,
                "object_id": str(row.target_id),
                "field_name": row.field_name,
            },
        )
        for row in enrichment_queryset[:3]
    ]

    claim_updates = _claim_update_candidates(
        work_ids,
        reviewer=reviewer,
        limit=3,
    )
    debates, reading_paths = _pending_generated_candidates(
        "" if global_scope else object_type,
        None if global_scope else target,
        work_ids,
    )
    debate_updates = [
        _knowledge_update_payload(
            _debate_candidate_payload(row),
            update_kind="debate_discovery",
            signal_sources=["debate_candidate", "derived_claim", "evidence_span"],
            why_now="馆藏 Claim 已形成支持、相斥或限定结构，可由 Editor 决定是否建立争论草稿。",
            priority=max(row.importance_score, row.quality_score),
            decision_target={
                "object_type": "knowledge_node",
                "object_id": str(row.suggested_node_id or ""),
            },
        )
        for row in debates[:2]
    ]
    reading_updates = [
        _knowledge_update_payload(
            _reading_path_candidate_payload(row),
            update_kind="reading_path_generation",
            signal_sources=["reading_path_candidate", "evidence_span"],
            why_now="研究任务已生成完整路径草案，可整体采用为草稿后再编辑。",
            priority=max(row.importance_score, row.quality_score),
            decision_target={"object_type": "reading_path", "object_id": ""},
        )
        for row in reading_paths[:2]
    ]
    evidence_updates = _evidence_update_candidates(
        None if global_scope else work_ids,
        limit=1,
    )

    claim_queryset = DerivedClaim.objects.filter(
        status=DerivedClaim.Status.ACTIVE,
        document_revision__is_active=True,
        primary_evidence__is_stale=False,
    )
    if not global_scope:
        claim_queryset = claim_queryset.filter(work_id__in=work_ids) if work_ids else claim_queryset.none()
    counts = {
        "evidence_spans": _unconsumed_evidence(
            None if global_scope else work_ids
        ).count(),
        "derived_claims": claim_queryset.count(),
        "enrichment_candidates": enrichment_queryset.count(),
        "debate_candidates": debates.count(),
        "reading_path_candidates": reading_paths.count(),
    }
    limit = GLOBAL_KNOWLEDGE_UPDATE_LIMIT if global_scope else KNOWLEDGE_UPDATE_LIMIT
    items = _bounded_diverse_suggestions(
        [
            enrichment_updates,
            claim_updates,
            debate_updates,
            reading_updates,
            evidence_updates,
        ],
        limit=limit,
    )
    return {
        "items": items,
        "signal_counts": counts,
        "visible_count": len(items),
        "limit": limit,
        "derived_read_model": True,
        "persistent_model": None,
        "canonical_write_policy": "human_decision_only",
    }


def _node_selection(node: KnowledgeNode, object_type: str) -> dict[str, Any]:
    canonical = {
        "canonical_name_zh": node.canonical_name_zh,
        "canonical_name_en": node.canonical_name_en,
        "node_type": node.node_type,
        "slug": node.slug,
        "summary": node.summary,
        "definition": node.definition,
        "core_questions": node.core_questions,
        "basic_propositions": node.basic_propositions,
        "theoretical_boundary": node.theoretical_boundary,
        "period": {"start_year": node.start_year, "end_year": node.end_year, "label": node.period_label},
        "primary_discipline": node.primary_discipline.name if node.primary_discipline_id else None,
    }
    relations: list[dict[str, Any]] = [
        {
            "id": str(row.id),
            "kind": "node_discipline",
            "label": row.get_relation_type_display(),
            "target": row.discipline.name,
            "status": row.status,
            "description": _clip(row.discipline_specific_summary, 600),
        }
        for row in node.discipline_links.select_related("discipline").order_by(
            "sort_order", "discipline__name"
        )[:MAX_SECTION_ROWS]
    ]
    for row in node.subdiscipline_links.select_related(
        "subdiscipline__discipline"
    ).order_by("sort_order", "subdiscipline__name")[:MAX_SECTION_ROWS]:
        relations.append(
            {
                "id": str(row.id),
                "kind": "node_subdiscipline",
                "label": row.relation_role or "相关子学科",
                "target": row.subdiscipline.name,
                "status": row.status,
                "is_primary": row.is_primary,
                "description": row.source,
            }
        )
    for row in node.topic_links.select_related("topic").order_by(
        "sort_order", "topic__name"
    )[:MAX_SECTION_ROWS]:
        relations.append(
            {
                "id": str(row.id),
                "kind": "node_topic",
                "label": row.relation_label or "相关主题",
                "target": row.topic.name,
                "status": row.status,
                "description": row.source,
            }
        )
    relation_limit = MAX_SECTION_ROWS * 3
    outgoing_limit = max(0, relation_limit - len(relations))
    for row in node.outgoing_relations.select_related("target_node").order_by(
        "relation_type"
    )[:outgoing_limit]:
        relations.append({
            "id": str(row.id), "kind": "knowledge_relation", "direction": "outgoing",
            "label": row.get_relation_type_display(), "target": row.target_node.canonical_name_zh,
            "status": row.status, "description": _clip(row.description, 600),
        })
    remaining = max(0, relation_limit - len(relations))
    if remaining:
        for row in node.incoming_relations.select_related("source_node").order_by("relation_type")[:remaining]:
            relations.append({
                "id": str(row.id), "kind": "knowledge_relation", "direction": "incoming",
                "label": row.get_relation_type_display(), "target": row.source_node.canonical_name_zh,
                "status": row.status, "description": _clip(row.description, 600),
            })
    work_relations = [
        {
            "id": str(row.id), "kind": "work_node", "label": row.get_role_display(),
            "target": row.work.title, "status": row.status, "is_primary": row.is_primary,
        }
        for row in node.work_relations.select_related("work").order_by("-is_primary", "work__title")[:MAX_SECTION_ROWS]
    ]
    people = [
        {
            "id": str(row.id), "kind": "person_node", "label": row.relation_label or "相关学者",
            "target": row.person.preferred_name, "status": row.status,
            "is_representative": row.is_representative,
        }
        for row in node.person_relations.select_related("person").order_by("sort_order")[:MAX_SECTION_ROWS]
    ]
    snippets = [
        _snippet_payload(row)
        for row in node.evidence.select_related("work", "file").order_by("page_number", "created_at")[:MAX_SECTION_ROWS]
    ]
    derived = DerivedClaim.objects.filter(work__node_relations__node=node).distinct()
    curated_claims = _curated_claims(CuratedClaim.objects.filter(node=node))
    derived_claims = _derived_claims(derived)
    candidates = _enrichment_candidates(EnrichmentCandidate.TargetType.KNOWLEDGE_NODE, node.id)
    candidates.extend(
        _theory_review_candidate(row)
        for row in node.review_tasks.select_related("candidate_node").filter(
            status__in=[TheoryReviewTask.TaskStatus.PENDING, TheoryReviewTask.TaskStatus.NEEDS_CHANGES]
        ).order_by("-confidence", "created_at")[:MAX_SECTION_ROWS]
    )
    if object_type == "debate":
        candidates.extend(
            _debate_candidate_payload(row)
            for row in DebateCandidate.objects.filter(
                suggested_node=node,
                status=DebateCandidate.Status.PENDING,
            ).select_related("evidence_pack").order_by(
                "-importance_score", "created_at"
            )[:MAX_SECTION_ROWS]
        )
    target_type = EditorialRevision.TargetType.KNOWLEDGE_NODE
    public_modules = {
        "theory": ["定义", "核心问题", "发展脉络", "人物", "概念", "主要批评", "阅读路径"],
        "concept": ["定义", "相关理论", "相关作品", "原文证据"],
        "debate": ["规范问题", "支持", "相斥", "限定", "代表作品", "原文证据"],
        "research_problem": ["问题定义", "理论解释", "相关作品", "原文证据"],
    }[object_type]
    return {
        "id": str(node.id),
        "object_type": object_type,
        "label": node.canonical_name_zh,
        "status": node.status,
        "canonical": _bounded_json(canonical),
        "relations": (relations + work_relations + people)[: MAX_SECTION_ROWS * 3],
        "evidence": _claim_evidence(
            curated=curated_claims,
            derived=derived_claims,
            existing=snippets,
        ),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": candidates[:MAX_SECTION_ROWS],
        "revisions": _revision_rows(target_type, node.id),
        "preview": _latest_preview(target_type, node.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
            object_id=node.id,
            public_visibility=node.status == KnowledgePublicationStatus.PUBLISHED,
            modules=public_modules,
            targets=[
                {
                    "label": f"{node.get_node_type_display()}公开页",
                    "url": f"/theories/nodes/{node.slug}",
                    "modules": public_modules,
                },
                {
                    "label": "知识图谱",
                    "url": f"/theories/graph?center={node.slug}",
                    "modules": ["关系", "关联人物", "关联作品"],
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            EditorialRevision.TargetType.KNOWLEDGE_NODE,
            node.id,
            published=node.status == KnowledgePublicationStatus.PUBLISHED,
        ),
        "editor_url": f"/admin/theories/{node.id}",
        "preview_url": f"/theories/nodes/{node.slug}",
        "related_editor_urls": [
            {"label": "关系", "url": f"/admin/theory-relations?node={node.id}"},
            {"label": "时间轴", "url": f"/admin/theory-timeline?node={node.id}"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _scholar_selection(profile: ScholarProfile) -> dict[str, Any]:
    person = profile.person
    canonical = {
        "preferred_name": person.preferred_name,
        "original_name": person.original_name,
        "aliases": person.aliases,
        "birth_year": person.birth_year,
        "death_year": person.death_year,
        "biography": person.biography,
        "slug": profile.slug,
        "short_description": profile.short_description,
        "affiliations": profile.affiliations,
        "key_concerns": profile.key_concerns,
        "timeline": profile.timeline,
        "featured_quote": profile.featured_quote,
        "quote_source": profile.quote_source,
    }
    node_relations = [
        {
            "id": str(row.id), "kind": "person_node", "label": row.relation_label or "学术关系",
            "target": row.node.canonical_name_zh, "status": row.status,
            "is_representative": row.is_representative,
        }
        for row in person.node_relations.select_related("node").order_by("sort_order")[:MAX_SECTION_ROWS]
    ]
    topic_relations = [
        {
            "id": str(row.id), "kind": "person_topic", "label": row.relation_label or "相关主题",
            "target": row.topic.name, "status": row.review_status, "is_primary": row.is_primary,
        }
        for row in person.topic_relations.select_related("topic").order_by("-is_primary", "topic__name")[:MAX_SECTION_ROWS]
    ]
    work_ids = person.contributions.filter(approved=True).values_list("edition__work_id", flat=True)
    derived = DerivedClaim.objects.filter(work_id__in=work_ids).distinct()
    curated_claims = _curated_claims(CuratedClaim.objects.filter(scholar=profile))
    derived_claims = _derived_claims(derived)
    target_type = EditorialRevision.TargetType.SCHOLAR_PROFILE
    return {
        "id": str(profile.id),
        "object_type": "scholar",
        "label": person.preferred_name,
        "status": profile.editorial_status,
        "canonical": _bounded_json(canonical),
        "relations": (node_relations + topic_relations)[: MAX_SECTION_ROWS * 2],
        "evidence": _claim_evidence(curated=curated_claims, derived=derived_claims),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": _enrichment_candidates(EnrichmentCandidate.TargetType.PERSON, person.id),
        "revisions": _revision_rows(target_type, profile.id),
        "preview": _latest_preview(target_type, profile.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=EditorialRevision.TargetType.SCHOLAR_PROFILE,
            object_id=profile.id,
            public_visibility=profile.editorial_status == KnowledgePublicationStatus.PUBLISHED,
            modules=["学术位置", "核心作品", "核心观点", "主要贡献", "批评与回应", "建议阅读顺序"],
            targets=[
                {
                    "label": "学者公开页",
                    "url": f"/scholars/{profile.slug}",
                    "modules": ["身份与译名", "作品", "核心观点", "理论贡献", "批评与回应", "阅读顺序"],
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            EditorialRevision.TargetType.SCHOLAR_PROFILE,
            profile.id,
            published=profile.editorial_status == KnowledgePublicationStatus.PUBLISHED,
        ),
        "editor_url": f"/admin/scholars/{profile.id}",
        "preview_url": f"/scholars/{profile.slug}",
        "related_editor_urls": [
            {"label": "理论关系", "url": f"/admin/theory-relations?scholar={profile.id}"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _topic_selection(topic: Topic) -> dict[str, Any]:
    canonical = {
        "name": topic.name,
        "slug": topic.slug,
        "description": topic.description,
        "problem_statement": topic.problem_statement,
        "core_questions": topic.core_questions,
        "research_dimensions": topic.research_dimensions,
        "methods": topic.methods,
        "formation_context": topic.formation_context,
        "key_concepts": topic.key_concepts,
    }
    node_relations = [
        {
            "id": str(row.id), "kind": "node_topic", "label": row.relation_label or "相关知识节点",
            "target": row.node.canonical_name_zh, "status": row.status,
        }
        for row in topic.knowledge_node_links.select_related("node").order_by("sort_order")[:MAX_SECTION_ROWS]
    ]
    work_relations = [
        {
            "id": str(row.id), "kind": "work_topic", "label": "相关作品",
            "target": row.work.title, "status": row.review_status, "is_primary": row.is_primary,
        }
        for row in topic.work_relations.select_related("work").order_by("-is_primary", "work__title")[:MAX_SECTION_ROWS]
    ]
    derived = DerivedClaim.objects.filter(work__topic_relations__topic=topic).distinct()
    curated_claims = _curated_claims(CuratedClaim.objects.filter(topic=topic))
    derived_claims = _derived_claims(derived)
    target_type = EditorialRevision.TargetType.TOPIC
    return {
        "id": str(topic.id),
        "object_type": "topic",
        "label": topic.name,
        "status": topic.editorial_status,
        "canonical": _bounded_json(canonical),
        "relations": (node_relations + work_relations)[: MAX_SECTION_ROWS * 2],
        "evidence": _claim_evidence(curated=curated_claims, derived=derived_claims),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": _enrichment_candidates(EnrichmentCandidate.TargetType.TOPIC, topic.id),
        "revisions": _revision_rows(target_type, topic.id),
        "preview": _latest_preview(target_type, topic.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=EditorialRevision.TargetType.TOPIC,
            object_id=topic.id,
            public_visibility=topic.editorial_status == KnowledgePublicationStatus.PUBLISHED,
            modules=["核心研究问题", "不同理论解释", "相关作品", "观点", "阅读入口"],
            targets=[
                {
                    "label": "主题公开页",
                    "url": f"/topics/{topic.slug}",
                    "modules": ["问题范围", "理论视角", "学者", "作品", "Claims", "争论", "阅读路径"],
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            EditorialRevision.TargetType.TOPIC,
            topic.id,
            published=topic.editorial_status == KnowledgePublicationStatus.PUBLISHED,
        ),
        "editor_url": f"/admin/topics/{topic.id}",
        "preview_url": f"/topics/{topic.slug}",
        "related_editor_urls": [
            {"label": "关系", "url": f"/admin/theory-relations?topic={topic.id}"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _discipline_selection(discipline: Discipline) -> dict[str, Any]:
    canonical = {
        "code": discipline.code,
        "name": discipline.name,
        "foreign_name": discipline.foreign_name,
        "slug": discipline.slug,
        "description": discipline.description,
        "introduction": discipline.introduction,
        "sort_order": discipline.sort_order,
        "curation_level": discipline.curation_level,
        "editorial_status": discipline.editorial_status,
    }
    relations = [
        {
            "id": str(row.id),
            "kind": "discipline_subdiscipline",
            "label": "子学科",
            "target": row.name,
            "status": row.editorial_status,
        }
        for row in discipline.subdisciplines.order_by("name")[:MAX_SECTION_ROWS]
    ]
    target_type = EditorialRevision.TargetType.DISCIPLINE
    modules = ["学科介绍", "子学科目录", "理论与主题", "作品与学者"]
    return {
        "id": str(discipline.id),
        "object_type": "discipline",
        "label": discipline.name,
        "status": discipline.editorial_status,
        "canonical": _bounded_json(canonical),
        "relations": relations,
        "evidence": [],
        "claims": {"curated": [], "derived": [], "derived_is_machine_only": True},
        "ai_candidates": [],
        "revisions": _revision_rows(target_type, discipline.id),
        "preview": _latest_preview(target_type, discipline.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=target_type,
            object_id=discipline.id,
            public_visibility=(
                discipline.editorial_status == KnowledgePublicationStatus.PUBLISHED
            ),
            modules=modules,
            targets=[
                {
                    "label": "学科公开页",
                    "url": f"/theories/disciplines/{discipline.slug}",
                    "modules": modules,
                }
            ],
        ),
        "mutation_contract": _mutation_contract(
            target_type,
            discipline.id,
            published=(
                discipline.editorial_status == KnowledgePublicationStatus.PUBLISHED
            ),
        ),
        "editor_url": f"/admin/disciplines/{discipline.id}",
        "preview_url": f"/theories/disciplines/{discipline.slug}",
        "related_editor_urls": [
            {"label": "子学科", "url": "/admin/subdisciplines"},
            {"label": "理论节点", "url": "/admin/theory-nodes"},
        ],
    }


def _subdiscipline_selection(subdiscipline: Subdiscipline) -> dict[str, Any]:
    canonical = {
        "name": subdiscipline.name,
        "foreign_name": subdiscipline.foreign_name,
        "slug": subdiscipline.slug,
        "description": subdiscipline.description,
        "discipline": subdiscipline.discipline.name,
        "parent": subdiscipline.parent.name if subdiscipline.parent_id else None,
        "research_object": subdiscipline.research_object,
        "core_questions": subdiscipline.core_questions,
        "formation_period": subdiscipline.formation_period,
        "research_directions": subdiscipline.research_directions,
        "methods": subdiscipline.methods,
        "representative_issues": subdiscipline.representative_issues,
    }
    node_relations = [
        {
            "id": str(row.id),
            "kind": "node_subdiscipline",
            "label": row.relation_role or "相关理论或概念",
            "target": row.node.canonical_name_zh,
            "status": row.status,
            "description": row.source,
        }
        for row in subdiscipline.knowledge_node_links.select_related("node").order_by(
            "sort_order", "node__canonical_name_zh"
        )[:MAX_SECTION_ROWS]
    ]
    work_relations = [
        {
            "id": str(row.id),
            "kind": "work_subdiscipline",
            "label": "主要作品" if row.is_primary else "相关作品",
            "target": row.work.title,
            "status": row.review_status,
            "description": _clip(row.evidence_text or row.source, 600),
        }
        for row in subdiscipline.work_relations.select_related("work").order_by(
            "-is_primary", "work__title"
        )[:MAX_SECTION_ROWS]
    ]
    person_relations = [
        {
            "id": str(row.id),
            "kind": "person_subdiscipline",
            "label": row.relation_label or "相关学者",
            "target": row.person.preferred_name,
            "status": row.review_status,
            "description": row.source,
        }
        for row in subdiscipline.person_relations.select_related("person").order_by(
            "person__sort_name", "person__preferred_name"
        )[:MAX_SECTION_ROWS]
    ]
    topic_relations = [
        {
            "id": str(row.id),
            "kind": "topic_subdiscipline",
            "label": row.relation_label or "相关主题",
            "target": row.topic.name,
            "status": row.review_status,
        }
        for row in subdiscipline.topic_relations.select_related("topic").order_by(
            "topic__name"
        )[:MAX_SECTION_ROWS]
    ]
    work_ids = subdiscipline.work_relations.values_list("work_id", flat=True)
    node_ids = subdiscipline.knowledge_node_links.values_list("node_id", flat=True)
    curated_claims = _curated_claims(
        CuratedClaim.objects.filter(
            Q(work_id__in=work_ids) | Q(node_id__in=node_ids)
        ).distinct()
    )
    derived_claims = _derived_claims(
        DerivedClaim.objects.filter(work_id__in=work_ids).distinct()
    )
    target_type = EditorialRevision.TargetType.SUBDISCIPLINE
    modules = [
        "研究对象与核心问题",
        "形成与发展",
        "主要研究方向",
        "常用方法",
        "代表性议题",
        "相关理论传统",
        "精选文献导读",
    ]
    return {
        "id": str(subdiscipline.id),
        "object_type": "subdiscipline",
        "label": subdiscipline.name,
        "status": subdiscipline.editorial_status,
        "canonical": _bounded_json(canonical),
        "relations": (
            node_relations + work_relations + person_relations + topic_relations
        )[: MAX_SECTION_ROWS * 3],
        "evidence": _claim_evidence(
            curated=curated_claims,
            derived=derived_claims,
        ),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": _enrichment_candidates(
            EnrichmentCandidate.TargetType.SUBDISCIPLINE,
            subdiscipline.id,
        ),
        "revisions": _revision_rows(target_type, subdiscipline.id),
        "preview": _latest_preview(target_type, subdiscipline.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=target_type,
            object_id=subdiscipline.id,
            public_visibility=(
                subdiscipline.editorial_status
                == KnowledgePublicationStatus.PUBLISHED
            ),
            modules=modules,
            targets=[
                {
                    "label": "子学科公开页",
                    "url": f"/subdisciplines/{subdiscipline.slug}",
                    "modules": modules,
                },
                {
                    "label": "学科入口",
                    "url": f"/theories/disciplines/{subdiscipline.discipline.slug}",
                    "modules": ["子学科目录", "相关作品"],
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            target_type,
            subdiscipline.id,
            published=(
                subdiscipline.editorial_status
                == KnowledgePublicationStatus.PUBLISHED
            ),
        ),
        "editor_url": f"/admin/subdisciplines?subdiscipline={subdiscipline.id}",
        "preview_url": f"/subdisciplines/{subdiscipline.slug}",
        "related_editor_urls": [
            {"label": "关系", "url": f"/admin/theory-relations?subdiscipline={subdiscipline.id}"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _reading_path_selection(path: ReadingPath) -> dict[str, Any]:
    stage_groups = reading_path_stage_groups(path)
    canonical = {
        "title": path.title,
        "slug": path.slug,
        "introduction": path.introduction,
        "learning_goal": path.learning_goal,
        "primary_discipline": (
            path.primary_discipline.name if path.primary_discipline_id else None
        ),
        "audience": path.audience,
        "difficulty": path.difficulty,
        "estimated_reading": path.estimated_reading,
        "stages": stage_groups,
    }
    items = list(
        path.items.select_related("stage", "work", "node").order_by(
            "reading_order", "position", "created_at"
        )[: MAX_SECTION_ROWS * 3]
    )
    relations = [
        {
            "id": str(row.id),
            "kind": "reading_path_item",
            "label": row.stage.name if row.stage_id else row.stage_name,
            "target": (
                row.work.title
                if row.work_id
                else row.node.canonical_name_zh
                if row.node_id
                else "未关联对象"
            ),
            "status": "published" if path.status == "published" else "draft",
            "description": _clip(row.recommendation_reason, 600),
            "prerequisite": _clip(row.prerequisite, 600),
            "is_required": row.is_required,
        }
        for row in items
    ]
    work_ids = [row.work_id for row in items if row.work_id]
    node_ids = [row.node_id for row in items if row.node_id]
    curated_claims = _curated_claims(
        CuratedClaim.objects.filter(
            Q(work_id__in=work_ids) | Q(node_id__in=node_ids)
        ).distinct()
    )
    derived_claims = _derived_claims(
        DerivedClaim.objects.filter(work_id__in=work_ids).distinct()
    )
    candidates = _enrichment_candidates(
        EnrichmentCandidate.TargetType.READING_PATH,
        path.id,
    )
    candidates.extend(
        _reading_path_candidate_payload(row)
        for row in path.source_candidates.select_related("evidence_pack").order_by(
            "-importance_score", "created_at"
        )[:MAX_SECTION_ROWS]
    )
    target_type = EditorialRevision.TargetType.READING_PATH
    modules = ["目标读者", "学习目标", "阶段", "作品与节点", "推荐理由", "先后逻辑"]
    return {
        "id": str(path.id),
        "object_type": "reading_path",
        "label": path.title,
        "status": path.status,
        "canonical": _bounded_json(canonical),
        "relations": relations,
        "evidence": _claim_evidence(
            curated=curated_claims,
            derived=derived_claims,
        ),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": candidates[:MAX_SECTION_ROWS],
        "revisions": _revision_rows(target_type, path.id),
        "preview": _latest_preview(target_type, path.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=target_type,
            object_id=path.id,
            public_visibility=path.status == KnowledgePublicationStatus.PUBLISHED,
            modules=modules,
            targets=[
                {
                    "label": "阅读路径公开页",
                    "url": f"/theories/reading-paths/{path.slug}",
                    "modules": modules,
                },
            ],
        ),
        "mutation_contract": _mutation_contract(
            target_type,
            path.id,
            published=path.status == KnowledgePublicationStatus.PUBLISHED,
        ),
        "editor_url": f"/admin/reading-paths?path={path.id}",
        "preview_url": f"/theories/reading-paths/{path.slug}",
        "related_editor_urls": [
            {"label": "作品策展", "url": "/admin/library"},
            {"label": "理论节点", "url": "/admin/theory-nodes"},
        ],
    }


def _work_selection(work: Work) -> dict[str, Any]:
    editions = list(
        work.editions.prefetch_related("contributions__person").order_by(
            "-published_at", "-publication_year", "-created_at"
        )
    )
    published_edition = next(
        (row for row in editions if row.state == PublicationState.PUBLISHED),
        None,
    )
    primary_edition = published_edition or (editions[0] if editions else None)
    canonical = {
        "title": work.title,
        "subtitle": work.subtitle,
        "original_title": work.original_title,
        "canonical_title": work.uniform_title,
        "abstract": work.abstract,
        "document_type": work.document_type,
        "language": work.language,
        "original_language": work.original_language,
        "first_publication_date": work.first_publication_date,
        "is_featured": work.is_featured,
        "editions": [
            {
                "id": str(edition.id),
                "edition_statement": edition.version_label,
                "publication_date": edition.publication_date,
                "publication_year": edition.publication_year,
                "publisher": edition.publisher,
                "publication_place": edition.publication_place,
                "isbn10": edition.isbn10,
                "isbn13": edition.isbn13,
                "series": edition.series,
                "state": edition.state,
                "contributors": [
                    {
                        "name": contribution.person.preferred_name,
                        "role": contribution.role,
                        "approved": contribution.approved,
                    }
                    for contribution in edition.contributions.all()
                ],
            }
            for edition in editions[:MAX_SECTION_ROWS]
        ],
    }
    relations: list[dict[str, Any]] = []
    relations.extend(
        {
            "id": str(row.id),
            "kind": "work_node",
            "label": row.get_role_display(),
            "target": row.node.canonical_name_zh,
            "status": row.status,
            "description": "主要关系" if row.is_primary else "",
        }
        for row in work.node_relations.select_related("node").order_by(
            "-is_primary", "node__canonical_name_zh"
        )[:MAX_SECTION_ROWS]
    )
    for relation_name, kind, target_attr in (
        ("discipline_relations", "work_discipline", "discipline"),
        ("subdiscipline_relations", "work_subdiscipline", "subdiscipline"),
        ("topic_relations", "work_topic", "topic"),
    ):
        queryset = getattr(work, relation_name).select_related(target_attr).order_by(
            "-is_primary", f"{target_attr}__name"
        )[:MAX_SECTION_ROWS]
        relations.extend(
            {
                "id": str(row.id),
                "kind": kind,
                "label": "主要归类" if row.is_primary else "相关归类",
                "target": getattr(row, target_attr).name,
                "status": row.review_status,
                "description": _clip(row.evidence_text or row.source, 600),
            }
            for row in queryset
        )
    path_items = list(
        work.reading_path_items.select_related("reading_path", "stage").order_by(
            "reading_path__sort_order", "reading_order"
        )[:MAX_SECTION_ROWS]
    )
    relations.extend(
        {
            "id": str(row.id),
            "kind": "reading_path_item",
            "label": row.stage.name if row.stage_id else row.stage_name,
            "target": row.reading_path.title,
            "status": row.reading_path.status,
            "description": _clip(row.recommendation_reason, 600),
        }
        for row in path_items
    )
    curated_claims = _curated_claims(CuratedClaim.objects.filter(work=work))
    derived_claims = _derived_claims(DerivedClaim.objects.filter(work=work))
    candidates = _enrichment_candidates(EnrichmentCandidate.TargetType.WORK, work.id)
    candidates.extend(
        _theory_review_candidate(row)
        for row in work.theory_review_tasks.select_related("candidate_node").filter(
            status__in=[
                TheoryReviewTask.TaskStatus.PENDING,
                TheoryReviewTask.TaskStatus.NEEDS_CHANGES,
            ]
        ).order_by("-confidence", "created_at")[:MAX_SECTION_ROWS]
    )
    status_value = _work_status(work)
    public_url = (
        f"/works/{published_edition.public_slug}"
        if published_edition and published_edition.public_slug
        else ""
    )
    preview_url = public_url or (
        f"/admin/preview/works/{primary_edition.id}" if primary_edition else ""
    )
    contributor_targets: list[dict[str, Any]] = []
    seen_scholars: set[str] = set()
    for edition in editions:
        for contribution in edition.contributions.all():
            try:
                profile = contribution.person.scholar_profile
            except ScholarProfile.DoesNotExist:
                continue
            if str(profile.id) in seen_scholars:
                continue
            seen_scholars.add(str(profile.id))
            contributor_targets.append(
                {
                    "label": f"学者页 · {contribution.person.preferred_name}",
                    "url": f"/scholars/{profile.slug}",
                    "modules": ["核心作品", "核心观点", "阅读顺序"],
                }
            )
    modules = ["书目与阅读", "核心观点", "主要批评", "主要回应", "原文依据"]
    targets = [
        {
            "label": "作品公开页" if public_url else "作品认证预览",
            "url": preview_url,
            "modules": modules,
        },
        *contributor_targets,
    ]
    targets.extend(
        {
            "label": f"知识页 · {row.node.canonical_name_zh}",
            "url": f"/theories/nodes/{row.node.slug}",
            "modules": ["代表作品", "Claims", "原文证据"],
        }
        for row in work.node_relations.select_related("node").order_by(
            "-is_primary", "node__canonical_name_zh"
        )[:5]
    )
    target_type = EditorialRevision.TargetType.WORK
    return {
        "id": str(work.id),
        "object_type": "work",
        "label": work.title,
        "status": status_value,
        "canonical": _bounded_json(canonical),
        "relations": relations[: MAX_SECTION_ROWS * 3],
        "evidence": _claim_evidence(
            curated=curated_claims,
            derived=derived_claims,
        ),
        "claims": {
            "curated": curated_claims,
            "derived": derived_claims,
            "derived_is_machine_only": True,
        },
        "ai_candidates": candidates[:MAX_SECTION_ROWS],
        "revisions": _revision_rows(target_type, work.id),
        "preview": _latest_preview(target_type, work.id, canonical),
        "frontend_impact": _frontend_impact(
            object_type=target_type,
            object_id=work.id,
            public_visibility=bool(public_url),
            modules=modules,
            targets=targets,
        ),
        "mutation_contract": _mutation_contract(
            target_type,
            work.id,
            published=bool(public_url),
        ),
        "editor_url": (
            f"/admin/library/works/{work.id}"
            + (f"?edition={primary_edition.id}#work" if primary_edition else "#work")
        ),
        "preview_url": preview_url,
        "related_editor_urls": [
            {"label": "知识策展", "url": f"/admin/library/works/{work.id}#curation"},
            {"label": "阅读路径", "url": "/admin/reading-paths"},
        ],
    }


def _selection(
    object_type: str,
    object_id: str,
    *,
    reviewer=None,
) -> dict[str, Any] | None:
    identifier = _valid_uuid(object_id)
    if object_type not in OBJECT_TYPES or identifier is None:
        return None
    target = None
    selection = None
    if object_type in NODE_OBJECT_TYPES:
        node = KnowledgeNode.objects.select_related("primary_discipline").filter(
            pk=identifier,
            node_type=NODE_OBJECT_TYPES[object_type],
        ).first()
        target = node
        selection = _node_selection(node, object_type) if node else None
    elif object_type == "scholar":
        target = ScholarProfile.objects.select_related("person").filter(pk=identifier).first()
        selection = _scholar_selection(target) if target else None
    elif object_type == "discipline":
        target = Discipline.objects.filter(pk=identifier).first()
        selection = _discipline_selection(target) if target else None
    elif object_type == "topic":
        target = Topic.objects.filter(pk=identifier).first()
        selection = _topic_selection(target) if target else None
    elif object_type == "subdiscipline":
        target = Subdiscipline.objects.select_related(
            "discipline", "parent"
        ).filter(pk=identifier).first()
        selection = _subdiscipline_selection(target) if target else None
    elif object_type == "reading_path":
        target = ReadingPath.objects.select_related("primary_discipline").filter(
            pk=identifier
        ).first()
        selection = _reading_path_selection(target) if target else None
    else:
        target = Work.objects.prefetch_related(
            "editions__contributions__person",
        ).filter(pk=identifier).first()
        selection = _work_selection(target) if target else None
    if target is None or selection is None:
        return None
    selection = KnowledgeObjectEditorAdapter.enrich(
        object_type=object_type,
        target=target,
        selection=selection,
    )
    knowledge_updates = _knowledge_update_bundle(
        object_type=object_type,
        target=target,
        reviewer=reviewer,
    )
    selection["knowledge_update_suggestions"] = knowledge_updates["items"]
    selection["knowledge_update_signal_counts"] = knowledge_updates["signal_counts"]
    selection["knowledge_update_read_model"] = {
        key: knowledge_updates[key]
        for key in (
            "visible_count",
            "limit",
            "derived_read_model",
            "persistent_model",
            "canonical_write_policy",
        )
    }
    return selection


def knowledge_object_editor_snapshot(
    *,
    object_type: str,
    object_id: str,
    reviewer=None,
) -> dict[str, Any] | None:
    """Expose the same adapter used by Knowledge Studio to other admin shells.

    Workbench uses this bounded snapshot for preview and frontend-impact copy,
    so those claims cannot drift into a second hard-coded UI mapping.
    """

    return _selection(object_type, object_id, reviewer=reviewer)


def _theory_graph_preview(data: dict[str, Any]) -> dict[str, Any]:
    """Build the protected graph context from the public node serializer.

    The public graph endpoint and this preview both consume canonical,
    published relations.  The preview keeps the center node's draft-facing
    identity fields so an editor can see how the pending node copy will sit in
    that real relation context without exposing the draft anonymously.
    """

    center_id = str(data.get("id") or "")
    if not center_id:
        return {
            "center": None,
            "nodes": [],
            "edges": [],
            "depth": 1,
            "limit": 20,
            "truncated": False,
        }
    nodes: dict[str, dict[str, Any]] = {
        center_id: {
            "id": center_id,
            "kind": "knowledge_node",
            "node_type": data.get("node_type") or "theory_tradition",
            "name": data.get("canonical_name_zh") or "未命名理论",
            "foreign_name": data.get("canonical_name_en") or "",
            "slug": data.get("slug") or "",
            "summary": data.get("summary") or data.get("definition") or "",
            "period_label": data.get("period_label") or "",
            "is_center": True,
        }
    }
    edges: list[dict[str, Any]] = []
    for relation in list(data.get("direct_relations") or [])[:18]:
        source_id = str(relation.get("source_node") or "")
        target_id = str(relation.get("target_node") or "")
        if not source_id or not target_id:
            continue
        for node_id, name_key, slug_key in (
            (source_id, "source_name", "source_slug"),
            (target_id, "target_name", "target_slug"),
        ):
            if node_id == center_id or node_id in nodes:
                continue
            nodes[node_id] = {
                "id": node_id,
                "kind": "knowledge_node",
                "name": relation.get(name_key) or "未命名知识节点",
                "slug": relation.get(slug_key) or "",
                "is_center": False,
            }
        edges.append(
            {
                "id": str(relation.get("id") or f"{source_id}:{target_id}"),
                "source": source_id,
                "target": target_id,
                "relation_type": relation.get("relation_type") or "related",
                "relation_label": relation.get("relation_label") or "相关",
                "direction": relation.get("direction") or "undirected",
                "description": relation.get("description") or "",
            }
        )
    for scholar in list(data.get("representative_scholars") or []):
        if len(nodes) >= 20:
            break
        scholar_id = f"person:{scholar.get('id')}"
        if scholar_id in nodes:
            continue
        nodes[scholar_id] = {
            "id": scholar_id,
            "kind": "scholar",
            "name": scholar.get("name") or "未命名学者",
            "slug": scholar.get("scholar_slug") or "",
        }
        edges.append(
            {
                "id": f"preview-scholar:{center_id}:{scholar_id}",
                "source": center_id,
                "target": scholar_id,
                "relation_type": "representative_scholar",
                "relation_label": scholar.get("relation_label") or "代表学者",
                "direction": "undirected",
            }
        )
    for relations in (data.get("work_groups") or {}).values():
        for relation in relations or []:
            if len(nodes) >= 20:
                break
            work = relation.get("work_data") or {}
            work_id = str(work.get("id") or relation.get("work") or "")
            if not work_id:
                continue
            graph_id = f"work:{work_id}"
            if graph_id in nodes:
                continue
            nodes[graph_id] = {
                "id": graph_id,
                "kind": "work",
                "name": work.get("title") or "未命名馆藏",
                "work": work,
            }
            edges.append(
                {
                    "id": f"preview-work:{center_id}:{graph_id}",
                    "source": center_id,
                    "target": graph_id,
                    "relation_type": relation.get("role") or "related_work",
                    "relation_label": relation.get("role_label") or "相关馆藏",
                    "direction": "undirected",
                }
            )
        if len(nodes) >= 20:
            break
    return {
        "center": center_id,
        "nodes": list(nodes.values()),
        "edges": edges,
        "depth": 1,
        "limit": 20,
        "truncated": False,
    }


def _theory_secondary_preview(
    *,
    object_id: str,
    active_data: dict[str, Any],
) -> dict[str, Any]:
    """Return real secondary-page inputs for the protected Theory preview."""

    from catalog.theory_serializers import (
        NormalizedTimelineEventSerializer,
        ReadingPathSerializer,
    )

    target = KnowledgeNode.objects.filter(pk=object_id).first()
    if target is None:
        return {"graph": _theory_graph_preview(active_data), "timeline": [], "reading_paths": []}
    timeline = (
        TheoryTimelineEvent.objects.filter(
            review_status=RelationReviewStatus.APPROVED,
            normalized_relations__node=target,
        )
        .prefetch_related(
            "normalized_relations__node",
            "normalized_relations__discipline",
            "normalized_relations__scholar__person",
            "normalized_relations__work",
        )
        .distinct()
        .order_by("start_year", "display_order", "title")[:24]
    )
    paths = (
        ReadingPath.objects.filter(
            status=KnowledgePublicationStatus.PUBLISHED,
            items__node=target,
        )
        .select_related("primary_discipline")
        .prefetch_related("stages", "items__stage", "items__node", "items__work")
        .distinct()
        .order_by("sort_order", "title")[:6]
    )
    return {
        "graph": _theory_graph_preview(active_data),
        "timeline": list(
            NormalizedTimelineEventSerializer(timeline, many=True, context={}).data
        ),
        "reading_paths": list(
            ReadingPathSerializer(
                paths,
                many=True,
                context={"include_unpublished_items": True},
            ).data
        ),
    }


def _scholar_secondary_preview() -> dict[str, Any]:
    """Return the published legacy TheorySchool fallback used by public pages."""

    rows = TheorySchool.objects.filter(
        editorial_status=KnowledgePublicationStatus.PUBLISHED,
    ).order_by("name")[:50]
    return {
        "legacy_theory_schools": [
            {
                "slug": row.slug,
                "name": row.name,
                "description": row.description or "馆藏关联理论流派",
                "books": 0,
                "scholars": 0,
                "symbol": row.symbol or row.name[:2],
            }
            for row in rows
        ]
    }


def knowledge_object_preview_payload(
    *,
    object_type: str,
    object_id: str,
    reviewer=None,
) -> dict[str, Any] | None:
    """Return the protected preview contract used by the admin preview route.

    The payload is deliberately sourced from ``KnowledgeObjectEditorAdapter``.
    It therefore uses the same public serializers as the public pages and does
    not create a second preview-only knowledge representation.
    """

    selection = _selection(object_type, object_id, reviewer=reviewer)
    if selection is None:
        return None
    perspectives = selection.get("preview_perspectives") or {}
    draft = perspectives.get("draft") or {}
    published = perspectives.get("published") or {}
    active = "draft" if draft.get("available") else "published"
    active_payload = draft if active == "draft" else published
    payload = {
        "preview_mode": True,
        "protected": True,
        "object_type": selection["object_type"],
        "object_id": selection["id"],
        "label": selection["label"],
        "status": selection["status"],
        "active_perspective": active,
        "source": active_payload.get("source") or active,
        "perspective": active_payload,
        "perspectives": perspectives,
        "preview_routes": selection.get("preview_routes") or {},
        "frontend_impact": selection.get("frontend_impact") or {},
        "content_completeness": selection.get("content_completeness") or {},
        "editor_adapter": selection.get("editor_adapter") or {},
        "public_control": selection.get("public_control") or {},
    }
    if selection["object_type"] == "theory" and isinstance(
        active_payload.get("data"), dict
    ):
        payload["secondary_preview"] = _theory_secondary_preview(
            object_id=selection["id"],
            active_data=dict(active_payload["data"]),
        )
    elif selection["object_type"] == "scholar" and isinstance(
        active_payload.get("data"), dict
    ):
        payload["secondary_preview"] = _scholar_secondary_preview()
    return payload


def knowledge_studio_workspace(
    *,
    query: str = "",
    object_type: str = "",
    selected_type: str = "",
    selected_id: str = "",
    limit: Any = DEFAULT_DIRECTORY_LIMIT,
    reviewer=None,
) -> dict[str, Any]:
    """Return the Knowledge Studio directory and selected editor workspace."""

    normalized_query = _clip(query, 160)
    normalized_type = object_type if object_type in OBJECT_TYPES else "all"
    bounded = _bounded_limit(limit)
    objects, counts = _directory(
        query=normalized_query,
        object_type=normalized_type,
        limit=bounded,
    )
    explicit_selection = bool(str(selected_type).strip() or str(selected_id).strip())
    selection = _selection(selected_type, selected_id, reviewer=reviewer)
    if selection is None and objects and not explicit_selection:
        selection = _selection(
            objects[0]["object_type"],
            objects[0]["id"],
            reviewer=reviewer,
        )
    generated_candidates = [
        _debate_candidate_payload(row)
        for row in DebateCandidate.objects.filter(
            status=DebateCandidate.Status.PENDING
        ).select_related("evidence_pack").order_by(
            "-importance_score", "created_at"
        )[:10]
    ]
    generated_candidates.extend(
        _reading_path_candidate_payload(row)
        for row in ReadingPathCandidate.objects.filter(
            status=ReadingPathCandidate.Status.PENDING
        ).select_related("evidence_pack").order_by(
            "-importance_score", "created_at"
        )[:10]
    )
    knowledge_updates = _knowledge_update_bundle(
        reviewer=reviewer,
        global_scope=True,
    )
    from catalog.services.public_knowledge_control import (
        public_management_coverage,
    )

    return {
        "object_types": [
            {"value": "all", "label": "全部对象"},
            {"value": "theory", "label": "理论"},
            {"value": "concept", "label": "概念"},
            {"value": "debate", "label": "争论"},
            {"value": "research_problem", "label": "研究问题"},
            {"value": "scholar", "label": "学者"},
            {"value": "discipline", "label": "学科"},
            {"value": "subdiscipline", "label": "子学科"},
            {"value": "topic", "label": "主题"},
            {"value": "reading_path", "label": "阅读路径"},
            {"value": "work", "label": "重要作品"},
        ],
        "filters": {"query": normalized_query, "object_type": normalized_type, "limit": bounded},
        "counts": counts,
        "objects": objects,
        "selection": selection,
        "selection_error": "not_found_or_type_mismatch" if explicit_selection and selection is None else "",
        "candidate_overview": {
            "debates": DebateCandidate.objects.filter(status=DebateCandidate.Status.PENDING).count(),
            "reading_paths": ReadingPathCandidate.objects.filter(status=ReadingPathCandidate.Status.PENDING).count(),
        },
        "generated_candidates": generated_candidates,
        "knowledge_update_suggestions": knowledge_updates["items"],
        "knowledge_update_signal_counts": knowledge_updates["signal_counts"],
        "knowledge_update_read_model": {
            key: knowledge_updates[key]
            for key in (
                "visible_count",
                "limit",
                "derived_read_model",
                "persistent_model",
                "canonical_write_policy",
            )
        },
        "workspace_mode": "knowledge_control_center",
        "mutations_via_existing_adapters": True,
        "read_only_aggregation": True,
        "machine_claims_are_canonical": False,
        "public_management_coverage": public_management_coverage(),
    }
