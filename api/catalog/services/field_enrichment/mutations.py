from __future__ import annotations

from dataclasses import dataclass
import json

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from catalog.models import (
    Discipline,
    Edition,
    EnrichmentCandidate,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeRelation,
    PersonNameVariant,
    ReadingPathItem,
    ReadingPathStage,
    RelationReviewStatus,
    TimelineEventRelation,
    TheoryTimelineEvent,
    TopicDisciplineRelation,
    Work,
)
from catalog.services.knowledge_nodes import record_relation_version
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.relation_registry import relation_policy, relation_would_create_cycle
from ingestion.models import AuditEvent

from .policies import FIELD_POLICIES
from .targets import current_field_value, get_target
from .values import normalize_candidate_value, stable_json


@dataclass(frozen=True)
class MutationResult:
    authority_model: str
    authority_id: object
    created: bool
    changed: bool
    idempotent: bool = False


class FieldMutationRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, name: str):
        def decorator(function):
            if name in self._adapters:
                raise RuntimeError(f"重复的 field mutation adapter：{name}")
            self._adapters[name] = function
            return function
        return decorator

    def mutate(self, name: str, *, target, value, candidate, actor) -> MutationResult:
        try:
            adapter = self._adapters[name]
        except KeyError as exc:
            raise ValueError("该字段尚未配置 authority mutation adapter。") from exc
        return adapter(target=target, value=value, candidate=candidate, actor=actor)


FIELD_MUTATIONS = FieldMutationRegistry()


def _evidence_urls(candidate) -> list[str]:
    return list(
        candidate.evidence_records.filter(is_current=True)
        .order_by("canonical_url")
        .values_list("canonical_url", flat=True)
        .distinct()[:20]
    )


def _source_note(candidate) -> str:
    return json.dumps(
        {
            "source": "field_enrichment",
            "candidate_id": str(candidate.id),
            "evidence_urls": _evidence_urls(candidate),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


@FIELD_MUTATIONS.register("person_external_identifier")
def _person_external_identifier(*, target, value, candidate, actor):
    identifiers = dict(target.external_ids or {})
    existing = str(identifiers.get(value["scheme"]) or "").strip()
    if existing and existing.casefold() != value["value"].casefold():
        raise ValueError("该人物已有不同的同类型标识符，需先解决来源冲突。")
    if existing:
        return MutationResult("catalog.Person", target.id, False, False)
    identifiers[value["scheme"]] = value["value"]
    target.external_ids = identifiers
    target.save(update_fields=["external_ids", "updated_at"])
    return MutationResult("catalog.Person", target.id, False, True)


@FIELD_MUTATIONS.register("person_affiliation")
def _person_affiliation(*, target, value, candidate, actor):
    profile = getattr(target, "scholar_profile", None)
    if profile is None:
        raise ValueError("该 Person 尚无 ScholarProfile，不能写入 affiliation。")
    rows = list(profile.affiliations or [])
    names = {
        normalize_term(row.get("name") if isinstance(row, dict) else row)
        for row in rows
    }
    if normalize_term(value["name"]) in names:
        return MutationResult("catalog.ScholarProfile", profile.id, False, False)
    # ScholarProfile.affiliations is currently edited as a string list in the
    # existing Admin UI. Full provenance remains on EnrichmentCandidate.
    rows.append(value["name"])
    profile.affiliations = rows
    profile.save(update_fields=["affiliations", "updated_at"])
    return MutationResult("catalog.ScholarProfile", profile.id, False, True)


@FIELD_MUTATIONS.register("person_name_variant")
def _person_name_variant(*, target, value, candidate, actor):
    normalized = normalize_term(value["name"])
    if normalized in {normalize_term(target.preferred_name), normalize_term(target.original_name)}:
        return MutationResult("catalog.Person", target.id, False, False)
    variant = PersonNameVariant.objects.select_for_update().filter(
        person=target,
        normalized_name=normalized,
    ).first()
    if variant:
        changed_fields = []
        if not variant.is_verified:
            variant.is_verified = True
            changed_fields.append("is_verified")
        if not variant.source_note:
            variant.source_note = _source_note(candidate)
            changed_fields.append("source_note")
        if changed_fields:
            variant.save(update_fields=[*changed_fields, "updated_at"])
        return MutationResult("catalog.PersonNameVariant", variant.id, False, bool(changed_fields))
    variant = PersonNameVariant.objects.create(
        person=target,
        name=value["name"],
        language=value["language"],
        variant_type=value["variant_type"],
        source_kind=(
            PersonNameVariant.SourceKind.AUTHORITY_IMPORT
            if not candidate.evidence_records.filter(is_current=True).exclude(
                extraction_method="structured_provider"
            ).exists()
            else PersonNameVariant.SourceKind.OTHER
        ),
        source_note=_source_note(candidate),
        displayable=False,
        is_verified=True,
        created_by=actor,
    )
    return MutationResult("catalog.PersonNameVariant", variant.id, True, True)


def _locked_edition_value(edition, field_name: str):
    lock = edition.field_locks.filter(field_name=field_name).first()
    return lock.locked_value if lock else None


def _edition_field(target, field_name: str, value) -> MutationResult:
    locked = _locked_edition_value(target, field_name)
    if locked is not None and stable_json(locked) != stable_json(value):
        raise ValueError("该书目字段已人工锁定，联网候选不能覆盖。")
    if getattr(target, field_name) == value:
        return MutationResult("catalog.Edition", target.id, False, False)
    setattr(target, field_name, value)
    target.save(update_fields=[field_name, "updated_at"])
    return MutationResult("catalog.Edition", target.id, False, True)


@FIELD_MUTATIONS.register("edition_publication_year")
def _edition_publication_year(*, target, value, candidate, actor):
    return _edition_field(target, "publication_year", value)


@FIELD_MUTATIONS.register("edition_publisher")
def _edition_publisher(*, target, value, candidate, actor):
    return _edition_field(target, "publisher", value)


@FIELD_MUTATIONS.register("edition_isbn")
def _edition_isbn(*, target, value, candidate, actor):
    return _edition_field(target, "isbn", value)


@FIELD_MUTATIONS.register("work_first_publication_date")
def _work_first_publication_date(*, target, value, candidate, actor):
    from datetime import date

    parsed = date.fromisoformat(value)
    if target.first_publication_date == parsed:
        return MutationResult("catalog.Work", target.id, False, False)
    target.first_publication_date = parsed
    target.save(update_fields=["first_publication_date", "updated_at"])
    return MutationResult("catalog.Work", target.id, False, True)


def _named_foreign_name(target, value, model_label):
    if target.foreign_name == value:
        return MutationResult(model_label, target.id, False, False)
    target.foreign_name = value
    target.save(update_fields=["foreign_name", "updated_at"])
    return MutationResult(model_label, target.id, False, True)


@FIELD_MUTATIONS.register("discipline_foreign_name")
def _discipline_foreign_name(*, target, value, candidate, actor):
    return _named_foreign_name(target, value, "catalog.Discipline")


@FIELD_MUTATIONS.register("subdiscipline_foreign_name")
def _subdiscipline_foreign_name(*, target, value, candidate, actor):
    return _named_foreign_name(target, value, "catalog.Subdiscipline")


@FIELD_MUTATIONS.register("knowledge_node_alias")
def _knowledge_node_alias(*, target, value, candidate, actor):
    normalized = " ".join(value["alias"].casefold().split())
    if normalize_term(value["alias"]) in {
        normalize_term(target.canonical_name_zh),
        normalize_term(target.canonical_name_en),
    }:
        return MutationResult("catalog.KnowledgeNode", target.id, False, False)
    alias = KnowledgeNodeAlias.objects.select_for_update().filter(
        node=target,
        normalized_alias=normalized,
    ).first()
    if alias:
        return MutationResult("catalog.KnowledgeNodeAlias", alias.id, False, False)
    alias = KnowledgeNodeAlias.objects.create(
        node=target,
        alias=value["alias"],
        language=value["language"],
        alias_type=value["alias_type"],
        created_by=actor,
        source_kind=KnowledgeNodeAlias.SourceKind.WEB_EVIDENCE,
        is_verified=True,
    )
    return MutationResult("catalog.KnowledgeNodeAlias", alias.id, True, True)


@FIELD_MUTATIONS.register("knowledge_node_discipline")
def _knowledge_node_discipline(*, target, value, candidate, actor):
    discipline = Discipline.objects.get(pk=value["discipline_id"])
    relation, created = KnowledgeNodeDiscipline.objects.get_or_create(
        node=target,
        discipline=discipline,
        defaults={
            "relation_type": value["relation_type"],
            "status": "pending",
        },
    )
    if not created and relation.relation_type != value["relation_type"]:
        raise ValueError("该节点已有不同类型的学科关系，需先处理冲突。")
    return MutationResult("catalog.KnowledgeNodeDiscipline", relation.id, created, created)


@FIELD_MUTATIONS.register("knowledge_node_subdiscipline")
def _knowledge_node_subdiscipline(*, target, value, candidate, actor):
    parent = KnowledgeNode.objects.get(
        pk=value["subdiscipline_node_id"],
        node_type=KnowledgeNode.NodeType.SUBDISCIPLINE,
    )
    if target.parent_id == parent.id:
        return MutationResult("catalog.KnowledgeNode", target.id, False, False)
    target.parent = parent
    target.full_clean()
    target.save(update_fields=["parent", "updated_at"])
    return MutationResult("catalog.KnowledgeNode", target.id, False, True)


@FIELD_MUTATIONS.register("knowledge_relation")
def _knowledge_relation(*, target, value, candidate, actor):
    other = KnowledgeNode.objects.get(pk=value["target_node_id"])
    if other.pk == target.pk:
        raise ValueError("理论关系不能指向自身。")
    policy = relation_policy(value["relation_type"])
    if target.node_type not in policy.allowed_subject_types or other.node_type not in policy.allowed_object_types:
        raise ValueError("该 relation type 不允许当前节点类型组合。")
    if relation_would_create_cycle(
        source_node_id=target.pk,
        target_node_id=other.pk,
        predicate=value["relation_type"],
    ):
        raise ValueError("该关系会形成循环。")
    source_url = candidate.evidence_records.filter(is_current=True).order_by("-confidence").values_list("canonical_url", flat=True).first() or ""
    relation, created = KnowledgeRelation.objects.get_or_create(
        source_node=target,
        target_node=other,
        relation_type=value["relation_type"],
        defaults={
            "direction": (
                KnowledgeRelation.Direction.DIRECTED
                if policy.directed
                else KnowledgeRelation.Direction.UNDIRECTED
            ),
            "description": value.get("description", ""),
            "evidence_source": source_url[:300],
            "confidence": candidate.confidence,
            "status": "pending",
            "created_by": actor,
        },
    )
    if created:
        record_relation_version(relation, actor, "接受联网理论关系候选")
    return MutationResult("catalog.KnowledgeRelation", relation.id, created, created)


def _timeline_mutation(*, target, value, candidate, actor):
    evidence = candidate.evidence_records.filter(is_current=True).order_by("-confidence").first()
    event = TheoryTimelineEvent.objects.create(
        title=value["title"],
        description=value.get("description", ""),
        event_type=value["event_type"],
        start_year=value.get("start_year"),
        end_year=value.get("end_year"),
        date_label=value.get("date_label", ""),
        source=(evidence.canonical_url if evidence else "")[:120],
        evidence_text=(evidence.supporting_text if evidence else ""),
        confidence=candidate.confidence,
        review_status=RelationReviewStatus.SUGGESTED,
    )
    TimelineEventRelation.objects.create(
        event=event,
        node=target,
        relation_type=TimelineEventRelation.RelationType.SUBJECT,
        description="联网 enrichment 候选，待时间线审核",
    )
    return MutationResult("catalog.TheoryTimelineEvent", event.id, True, True)


@FIELD_MUTATIONS.register("knowledge_node_timeline_fact")
def _knowledge_node_timeline_fact(*, target, value, candidate, actor):
    return _timeline_mutation(target=target, value=value, candidate=candidate, actor=actor)


@FIELD_MUTATIONS.register("knowledge_node_timeline_interpretation")
def _knowledge_node_timeline_interpretation(*, target, value, candidate, actor):
    return _timeline_mutation(target=target, value=value, candidate=candidate, actor=actor)


@FIELD_MUTATIONS.register("topic_discipline")
def _topic_discipline(*, target, value, candidate, actor):
    discipline = Discipline.objects.get(pk=value["discipline_id"])
    relation, created = TopicDisciplineRelation.objects.get_or_create(
        topic=target,
        discipline=discipline,
        defaults={"review_status": RelationReviewStatus.SUGGESTED},
    )
    return MutationResult("catalog.TopicDisciplineRelation", relation.id, created, created)


@FIELD_MUTATIONS.register("reading_path_item")
def _reading_path_item(*, target, value, candidate, actor):
    node = KnowledgeNode.objects.get(pk=value["node_id"]) if value.get("node_id") else None
    work = Work.objects.get(pk=value["work_id"]) if value.get("work_id") else None
    existing = target.items.filter(node=node, work=work).first()
    if existing:
        return MutationResult("catalog.ReadingPathItem", existing.id, False, False)
    next_order = (target.items.aggregate(value=Max("reading_order"))["value"] or 0) + 1
    stage_name = value["stage_name"]
    stage = target.stages.filter(name=stage_name).order_by("position", "created_at").first()
    if stage is None:
        next_stage_position = (target.stages.aggregate(value=Max("position"))["value"] or -1) + 1
        stage = ReadingPathStage.objects.create(
            reading_path=target,
            name=stage_name,
            description=value.get("stage_description", ""),
            position=next_stage_position,
        )
    next_position = (stage.items.aggregate(value=Max("position"))["value"] or -1) + 1
    item = ReadingPathItem.objects.create(
        reading_path=target,
        stage=stage,
        stage_name=stage.name,
        stage_description=stage.description,
        node=node,
        work=work,
        recommendation_reason=value.get("recommendation_reason", ""),
        position=next_position,
        reading_order=next_order,
        is_required=value.get("is_required", False),
        editorial_note=f"来源候选 {candidate.id}",
    )
    return MutationResult("catalog.ReadingPathItem", item.id, True, True)


def _validate_evidence(candidate: EnrichmentCandidate, policy) -> None:
    evidence = candidate.evidence_records.filter(is_current=True)
    if evidence.count() < policy.evidence_min_count:
        raise ValueError("候选证据数量不足。")
    independent = evidence.values_list("canonical_url", flat=True).distinct().count()
    if independent < policy.independent_source_min:
        raise ValueError("候选缺少足够的独立来源。")
    disallowed = evidence.exclude(source_class__in=policy.allowed_source_classes)
    if disallowed.exists():
        raise ValueError("候选包含当前字段不允许的来源类别。")
    if policy.required_source_classes and not evidence.filter(
        source_class__in=policy.required_source_classes
    ).exists():
        raise ValueError("候选缺少该字段要求的学术或官方来源。")
    if evidence.filter(supporting_text="").exists():
        raise ValueError("候选存在没有 supporting passage 的来源。")


@transaction.atomic
def accept_enrichment_candidate(candidate: EnrichmentCandidate, *, actor, reason: str = "") -> MutationResult:
    candidate = EnrichmentCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status == EnrichmentCandidate.Status.ACCEPTED:
        if not candidate.accepted_authority_model or not candidate.accepted_authority_id:
            raise ValueError("已接受候选缺少 authority 审计引用。")
        return MutationResult(
            candidate.accepted_authority_model,
            candidate.accepted_authority_id,
            False,
            False,
            True,
        )
    if candidate.status != EnrichmentCandidate.Status.PENDING:
        raise ValueError("只有待审核 enrichment candidate 可以接受。")
    policy = FIELD_POLICIES.get(candidate.target_type, candidate.field_name)
    if candidate.candidate_kind != policy.candidate_kind:
        raise ValueError("候选类型与当前 FieldPolicy 不一致。")
    if candidate.policy_version != policy.policy_version:
        raise ValueError("FieldPolicy 已更新，请重新生成候选后再审核。")
    if candidate.refresh_after and candidate.refresh_after < timezone.now():
        raise ValueError("候选来源已超过当前字段的刷新期限。")
    if candidate.identity_status not in {
        EnrichmentCandidate.IdentityStatus.CONFIRMED,
        EnrichmentCandidate.IdentityStatus.NOT_REQUIRED,
    }:
        raise ValueError("目标身份仍不稳定，不能接受字段候选。")
    _validate_evidence(candidate, policy)
    value = normalize_candidate_value(policy.mutation_adapter, candidate.proposed_value)
    target = get_target(candidate.target_type, candidate.target_id, for_update=True)
    current = current_field_value(candidate.target_type, target, candidate.field_name)
    if stable_json(current) != stable_json(candidate.current_value):
        raise ValueError("authority 字段已在候选生成后变化，请重新核对。")
    result = FIELD_MUTATIONS.mutate(
        policy.mutation_adapter,
        target=target,
        value=value,
        candidate=candidate,
        actor=actor,
    )
    candidate.proposed_value = value
    candidate.normalized_value = value
    candidate.status = EnrichmentCandidate.Status.ACCEPTED
    candidate.reviewed_by = actor
    candidate.reviewed_at = timezone.now()
    candidate.review_reason = str(reason or "")[:4000]
    candidate.accepted_authority_model = result.authority_model
    candidate.accepted_authority_id = result.authority_id
    candidate.save(
        update_fields=[
            "proposed_value",
            "normalized_value",
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "accepted_authority_model",
            "accepted_authority_id",
            "updated_at",
        ]
    )
    AuditEvent.objects.create(
        actor=actor,
        action="accept_field_enrichment_candidate",
        object_type="catalog.EnrichmentCandidate",
        object_id=str(candidate.id),
        before={"status": EnrichmentCandidate.Status.PENDING},
        after={
            "status": candidate.status,
            "authority_model": result.authority_model,
            "authority_id": str(result.authority_id),
            "authority_changed": result.changed,
            "reason": str(reason or "")[:400],
        },
        request_id=str(candidate.request_id),
    )
    return result


@transaction.atomic
def reject_enrichment_candidate(candidate: EnrichmentCandidate, *, actor, reason: str = "") -> tuple[EnrichmentCandidate, bool]:
    candidate = EnrichmentCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status == EnrichmentCandidate.Status.REJECTED:
        return candidate, True
    if candidate.status != EnrichmentCandidate.Status.PENDING:
        raise ValueError("只有待审核 enrichment candidate 可以拒绝。")
    candidate.status = EnrichmentCandidate.Status.REJECTED
    candidate.reviewed_by = actor
    candidate.reviewed_at = timezone.now()
    candidate.review_reason = str(reason or "")[:4000]
    candidate.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "updated_at",
        ]
    )
    AuditEvent.objects.create(
        actor=actor,
        action="reject_field_enrichment_candidate",
        object_type="catalog.EnrichmentCandidate",
        object_id=str(candidate.id),
        before={"status": EnrichmentCandidate.Status.PENDING},
        after={"status": candidate.status, "reason": str(reason or "")[:400]},
        request_id=str(candidate.request_id),
    )
    return candidate, False
