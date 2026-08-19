from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from catalog.models import (
    Contribution,
    Edition,
    KnowledgeNode,
    KnowledgePublicationStatus,
    OrganizationAuthority,
    OrganizationContribution,
    Person,
    PublicationState,
    PublisherAuthority,
    Work,
)
from ingestion.models import DecisionLog, EntityResolutionCandidate, ReviewTask, UploadItem

from .reconciliation import normalized_label


class ResolutionDecisionError(ValueError):
    pass


ACTION_STATUS = {
    "link_existing": EntityResolutionCandidate.Status.LINKED,
    "create_draft": EntityResolutionCandidate.Status.CREATE_DRAFT,
    "keep_unresolved": EntityResolutionCandidate.Status.UNRESOLVED,
    "reject": EntityResolutionCandidate.Status.REJECTED,
}

TARGET_MODELS = {
    "person": (Person, "person"),
    "work": (Work, "work"),
    "publisher": (PublisherAuthority, "publisher_authority"),
    "organization": (OrganizationAuthority, "organization_authority"),
    "knowledge_node": (KnowledgeNode, "knowledge_node"),
}

DRAFT_TARGETS = {"person", "work", "organization", "knowledge_node"}


@dataclass(frozen=True)
class ResolutionDecisionResult:
    candidate: EntityResolutionCandidate
    group: tuple[EntityResolutionCandidate, ...]
    review_task: ReviewTask | None
    idempotent: bool


@dataclass(frozen=True)
class ResolutionRevertResult:
    candidate: EntityResolutionCandidate
    group: tuple[EntityResolutionCandidate, ...]
    review_task: ReviewTask | None
    decision: DecisionLog
    reversal: DecisionLog
    idempotent: bool


def available_resolution_actions(candidate: EntityResolutionCandidate) -> list[str]:
    if candidate.status != EntityResolutionCandidate.Status.PROPOSED:
        return []

    actions: list[str] = []
    expected = TARGET_MODELS.get(candidate.target_type)
    if (
        expected
        and candidate.candidate_entity_id
        and candidate.candidate_entity_type == expected[1]
    ):
        actions.append("link_existing")

    is_draft_choice = candidate.candidate_entity_type == f"{candidate.target_type}_draft"
    if is_draft_choice and candidate.target_type in DRAFT_TARGETS:
        if candidate.target_type != "knowledge_node" or candidate.supporting_properties.get("node_type"):
            actions.append("create_draft")
    if is_draft_choice:
        actions.append("keep_unresolved")
    actions.append("reject")
    return actions


def _review_task_for(candidate: EntityResolutionCandidate, *, lock: bool) -> ReviewTask | None:
    queryset = ReviewTask.objects
    if lock:
        queryset = queryset.select_for_update()
    return queryset.filter(
        upload_item=candidate.upload_item,
        task_type="entity_resolution",
        target_type=candidate.target_type,
        target_id=normalized_label(candidate.source_name)[:128],
    ).order_by("created_at").first()


def _lock_upload_context(upload_item_id) -> UploadItem:
    """Serialize review mutations through their shared intake and edition."""

    item = UploadItem.objects.select_for_update(of=("self",)).get(pk=upload_item_id)
    if item.edition_id:
        edition = (
            Edition.objects.select_for_update(of=("self",))
            .select_related("work")
            .get(pk=item.edition_id)
        )
        item.edition = edition
    return item


def _unique_node_slug(name: str) -> str:
    base = slugify(name)[:140] or "knowledge-node"
    candidate = base
    counter = 1
    while KnowledgeNode.objects.filter(slug=candidate).exists():
        counter += 1
        candidate = f"{base}-{counter}"
    return candidate


def _link_existing(candidate: EntityResolutionCandidate, *, target_id: str, confirm_identity: bool):
    model_config = TARGET_MODELS.get(candidate.target_type)
    if model_config is None:
        raise ResolutionDecisionError("不支持该实体类型。")
    model, expected_entity_type = model_config
    if candidate.candidate_entity_type != expected_entity_type:
        raise ResolutionDecisionError("该候选不是可关联的馆内实体。")
    if not candidate.candidate_entity_id or str(candidate.candidate_entity_id) != str(target_id):
        raise ResolutionDecisionError("目标实体必须与当前候选一致。")
    try:
        entity = model.objects.select_for_update().get(pk=target_id)
    except (model.DoesNotExist, ValueError, TypeError):
        raise ResolutionDecisionError("目标实体不存在或类型不匹配。") from None

    if candidate.target_type == "person" and not confirm_identity:
        raise ResolutionDecisionError("人物同名不能自动合并，请明确确认这是同一人物。")

    item = candidate.upload_item
    if candidate.target_type == "person" and item.edition_id:
        contribution, created = Contribution.objects.get_or_create(
            edition_id=item.edition_id,
            person=entity,
            role=Contribution.Role.AUTHOR,
            defaults={
                "source": "entity_resolution",
                "confidence": 1,
                "approved": False,
            },
        )
        if not created and not contribution.approved:
            contribution.source = "entity_resolution"
            contribution.confidence = 1
            contribution.save(update_fields=["source", "confidence", "updated_at"])
    elif candidate.target_type == "work" and item.edition_id:
        edition = item.edition
        if edition.state == PublicationState.PUBLISHED:
            raise ResolutionDecisionError("已发布版本不能在此处改换作品，请先创建修订。")
        edition.work = entity
        edition.save(update_fields=["work", "updated_at"])
    elif candidate.target_type == "publisher" and item.edition_id:
        edition = item.edition
        edition.publisher_authority = entity
        edition.save(update_fields=["publisher_authority", "updated_at"])
    elif candidate.target_type == "organization" and item.edition_id:
        role = str(candidate.supporting_properties.get("organization_role") or "").strip()
        if role not in OrganizationContribution.Role.values:
            raise ResolutionDecisionError("机构候选缺少有效责任角色，请重新生成候选。")
        OrganizationContribution.objects.update_or_create(
            edition_id=item.edition_id,
            organization=entity,
            role=role,
            defaults={
                "verbatim_name": candidate.source_name,
                "source": "entity_resolution",
                "confidence": 1,
                "approved": False,
            },
        )
    return entity


def _create_draft(candidate: EntityResolutionCandidate, *, actor):
    if candidate.candidate_entity_type != f"{candidate.target_type}_draft":
        raise ResolutionDecisionError("当前候选不是新建草稿选项。")
    name = " ".join(candidate.source_name.split()).strip()
    if not name:
        raise ResolutionDecisionError("候选名称为空，不能创建草稿。")

    item = candidate.upload_item
    if candidate.target_type == "person":
        entity = Person.objects.create(
            preferred_name=name,
            sort_name=name,
            authority_status=Person.AuthorityStatus.DRAFT,
        )
        if item.edition_id:
            Contribution.objects.update_or_create(
                edition_id=item.edition_id,
                person=entity,
                role=Contribution.Role.AUTHOR,
                defaults={
                    "source": "entity_resolution",
                    "confidence": 1,
                    "approved": False,
                },
            )
        candidate.candidate_entity_type = "person"
        candidate.label = entity.preferred_name
    elif candidate.target_type == "work":
        if not item.edition_id:
            raise ResolutionDecisionError("上传记录尚未建立版本，不能创建作品草稿。")
        if item.edition.state == PublicationState.PUBLISHED:
            raise ResolutionDecisionError("已发布版本不能在此处创建替代作品，请先创建修订。")
        entity = item.edition.work
        candidate.candidate_entity_type = "work"
        candidate.label = entity.title
    elif candidate.target_type == "knowledge_node":
        node_type = str(candidate.supporting_properties.get("node_type") or "").strip()
        if node_type not in KnowledgeNode.NodeType.values:
            raise ResolutionDecisionError("知识实体草稿缺少有效类型，请重新生成候选。")
        entity = KnowledgeNode.objects.create(
            node_type=node_type,
            canonical_name_zh=name,
            slug=_unique_node_slug(name),
            status=KnowledgePublicationStatus.DRAFT,
            created_by=actor,
        )
        candidate.candidate_entity_type = "knowledge_node"
        candidate.label = entity.canonical_name_zh
    elif candidate.target_type == "organization":
        role = str(candidate.supporting_properties.get("organization_role") or "").strip()
        if role not in OrganizationContribution.Role.values:
            raise ResolutionDecisionError("机构候选缺少有效责任角色，请重新生成候选。")
        organization_type = str(candidate.supporting_properties.get("organization_type") or "other")
        if organization_type not in OrganizationAuthority.OrganizationType.values:
            organization_type = OrganizationAuthority.OrganizationType.OTHER
        entity = OrganizationAuthority.objects.create(
            preferred_name=name,
            organization_type=organization_type,
            authority_status=OrganizationAuthority.AuthorityStatus.DRAFT,
        )
        if item.edition_id:
            OrganizationContribution.objects.create(
                edition_id=item.edition_id,
                organization=entity,
                role=role,
                verbatim_name=name,
                source="entity_resolution",
                confidence=1,
                approved=False,
            )
        candidate.candidate_entity_type = "organization_authority"
        candidate.label = entity.preferred_name
    else:
        raise ResolutionDecisionError("该实体类型尚无可验证的草稿状态，不能直接创建。")

    candidate.candidate_entity_id = str(entity.id)
    return entity


def _resolved_status_matches(candidate: EntityResolutionCandidate, *, action: str, target_id: str) -> bool:
    if candidate.status != ACTION_STATUS[action]:
        return False
    if action == "link_existing":
        return bool(target_id) and str(candidate.candidate_entity_id) == str(target_id)
    return True


def _serialize_datetime(value):
    return value.isoformat() if value else None


def _contribution_snapshot(candidate: EntityResolutionCandidate, target_id: str) -> dict | None:
    if candidate.target_type != "person" or not candidate.upload_item.edition_id or not target_id:
        return None
    contribution = Contribution.objects.filter(
        edition_id=candidate.upload_item.edition_id,
        person_id=target_id,
        role=Contribution.Role.AUTHOR,
    ).first()
    if contribution is None:
        return None
    return {
        "id": str(contribution.id),
        "person_id": str(contribution.person_id),
        "role": contribution.role,
        "order": contribution.order,
        "source": contribution.source,
        "confidence": contribution.confidence,
        "approved": contribution.approved,
    }


def _organization_contribution_snapshot(candidate: EntityResolutionCandidate, target_id: str) -> dict | None:
    if candidate.target_type != "organization" or not candidate.upload_item.edition_id or not target_id:
        return None
    role = str(candidate.supporting_properties.get("organization_role") or "").strip()
    contribution = OrganizationContribution.objects.filter(
        edition_id=candidate.upload_item.edition_id,
        organization_id=target_id,
        role=role,
    ).first()
    if contribution is None:
        return None
    return {
        "id": str(contribution.id),
        "organization_id": str(contribution.organization_id),
        "role": contribution.role,
        "verbatim_name": contribution.verbatim_name,
        "source": contribution.source,
        "confidence": contribution.confidence,
        "approved": contribution.approved,
    }


def _decision_snapshot(
    candidate: EntityResolutionCandidate,
    group: list[EntityResolutionCandidate],
    review_task: ReviewTask | None,
    *,
    action: str,
    target_id: str,
) -> dict:
    edition = candidate.upload_item.edition if candidate.upload_item.edition_id else None
    return {
        "candidate": {
            "status": candidate.status,
            "candidate_entity_type": candidate.candidate_entity_type,
            "candidate_entity_id": candidate.candidate_entity_id,
            "label": candidate.label,
            "reviewed_by_id": str(candidate.reviewed_by_id or ""),
            "reviewed_at": _serialize_datetime(candidate.reviewed_at),
        },
        "siblings": [
            {
                "id": str(row.id),
                "status": row.status,
                "reviewed_by_id": str(row.reviewed_by_id or ""),
                "reviewed_at": _serialize_datetime(row.reviewed_at),
            }
            for row in group
            if row.pk != candidate.pk
        ],
        "review_task": (
            {
                "id": str(review_task.id),
                "status": review_task.status,
                "completed_by_id": str(review_task.completed_by_id or ""),
                "completed_at": _serialize_datetime(review_task.completed_at),
                "details": review_task.details,
            }
            if review_task
            else None
        ),
        "mutation": {
            "action": action,
            "edition_id": str(edition.id) if edition else "",
            "edition_state": edition.state if edition else "",
            "work_id": str(edition.work_id) if edition else "",
            "publisher_authority_id": str(edition.publisher_authority_id or "") if edition else "",
            "contribution": _contribution_snapshot(candidate, target_id),
            "organization_contribution": _organization_contribution_snapshot(candidate, target_id),
        },
        "source_record_id": str(candidate.source_record_id or ""),
    }


def _current_mutation_snapshot(candidate: EntityResolutionCandidate) -> dict:
    edition = candidate.upload_item.edition if candidate.upload_item.edition_id else None
    target_id = str(candidate.candidate_entity_id or "")
    return {
        "edition_id": str(edition.id) if edition else "",
        "edition_state": edition.state if edition else "",
        "work_id": str(edition.work_id) if edition else "",
        "publisher_authority_id": str(edition.publisher_authority_id or "") if edition else "",
        "contribution": _contribution_snapshot(candidate, target_id),
        "organization_contribution": _organization_contribution_snapshot(candidate, target_id),
    }


@transaction.atomic
def decide_entity_resolution(
    candidate: EntityResolutionCandidate,
    *,
    action: str,
    target_type: str,
    target_id: str = "",
    confirm_identity: bool = False,
    actor,
    reason: str = "",
    correlation_id: str = "",
) -> ResolutionDecisionResult:
    if action not in ACTION_STATUS:
        raise ResolutionDecisionError("不支持的实体消歧决定。")

    item = _lock_upload_context(candidate.upload_item_id)
    candidate = EntityResolutionCandidate.objects.select_for_update(of=("self",)).get(
        pk=candidate.pk
    )
    if candidate.upload_item_id != item.id:
        raise ResolutionDecisionError("候选所属上传记录已变化，请刷新后重试。")
    candidate.upload_item = item
    if target_type != candidate.target_type:
        raise ResolutionDecisionError("目标类型与当前候选不一致。")

    group = list(
        EntityResolutionCandidate.objects.select_for_update().filter(
            upload_item=candidate.upload_item,
            target_type=candidate.target_type,
            source_name=candidate.source_name,
        ).order_by("-match_score", "created_at")
    )
    review_task = _review_task_for(candidate, lock=True)

    if _resolved_status_matches(candidate, action=action, target_id=target_id):
        return ResolutionDecisionResult(candidate, tuple(group), review_task, True)
    if candidate.status != EntityResolutionCandidate.Status.PROPOSED:
        raise ResolutionDecisionError("该候选已经有最终决定，不能用另一种操作覆盖。")
    if action not in available_resolution_actions(candidate):
        raise ResolutionDecisionError("该候选不支持此操作。")

    before = _decision_snapshot(
        candidate,
        group,
        review_task,
        action=action,
        target_id=target_id,
    )
    entity = None
    if action == "link_existing":
        entity = _link_existing(
            candidate,
            target_id=target_id,
            confirm_identity=confirm_identity,
        )
    elif action == "create_draft":
        entity = _create_draft(candidate, actor=actor)

    now = timezone.now()
    candidate.status = ACTION_STATUS[action]
    candidate.reviewed_by = actor
    candidate.reviewed_at = now
    candidate.save(
        update_fields=[
            "candidate_entity_type",
            "candidate_entity_id",
            "label",
            "status",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )

    rejected_siblings: list[str] = []
    if action in {"link_existing", "create_draft", "keep_unresolved"}:
        for sibling in group:
            if sibling.pk == candidate.pk or sibling.status != EntityResolutionCandidate.Status.PROPOSED:
                continue
            sibling.status = EntityResolutionCandidate.Status.REJECTED
            sibling.reviewed_by = actor
            sibling.reviewed_at = now
            sibling.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
            rejected_siblings.append(str(sibling.id))
        if review_task is not None and review_task.status != ReviewTask.Status.COMPLETED:
            review_task.status = ReviewTask.Status.COMPLETED
            review_task.completed_by = actor
            review_task.completed_at = now
            review_task.details = {
                **(review_task.details or {}),
                "decision": action,
                "resolution_candidate_id": str(candidate.id),
                "resolved_entity_id": str(candidate.candidate_entity_id or ""),
            }
            review_task.save(
                update_fields=["status", "completed_by", "completed_at", "details", "updated_at"]
            )

    DecisionLog.objects.create(
        upload_item=candidate.upload_item,
        review_task=review_task,
        resolution_candidate=candidate,
        actor=actor,
        action=action,
        target_type=candidate.target_type,
        target_id=str(candidate.candidate_entity_id or target_id),
        before=before,
        after={
            "status": candidate.status,
            "candidate_entity_type": candidate.candidate_entity_type,
            "candidate_entity_id": candidate.candidate_entity_id,
            "entity_is_draft": action == "create_draft",
            "rejected_sibling_ids": rejected_siblings,
            "source_name": candidate.source_name,
            "source_record_id": str(candidate.source_record_id) if candidate.source_record_id else "",
            "resolved_model": entity.__class__.__name__ if entity is not None else "",
            "mutation": _current_mutation_snapshot(candidate),
        },
        reason=reason,
        correlation_id=correlation_id,
    )

    refreshed_group = tuple(
        EntityResolutionCandidate.objects.filter(
            upload_item=candidate.upload_item,
            target_type=candidate.target_type,
            source_name=candidate.source_name,
        ).order_by("-match_score", "created_at")
    )
    return ResolutionDecisionResult(candidate, refreshed_group, review_task, False)


def _restore_datetime(value):
    return parse_datetime(value) if value else None


def _restore_contribution(before: dict | None, after: dict | None) -> None:
    if before is None:
        if not after or not after.get("id"):
            return
        contribution = Contribution.objects.select_for_update().filter(pk=after["id"]).first()
        if contribution is None:
            return
        current = {
            "id": str(contribution.id),
            "person_id": str(contribution.person_id),
            "role": contribution.role,
            "order": contribution.order,
            "source": contribution.source,
            "confidence": contribution.confidence,
            "approved": contribution.approved,
        }
        if current != after:
            raise ResolutionDecisionError("责任者关系已被后续修改，不能自动撤销。")
        contribution.delete()
        return
    contribution = Contribution.objects.select_for_update().filter(pk=before["id"]).first()
    if contribution is None:
        raise ResolutionDecisionError("原责任者关系已经不存在，不能自动恢复。")
    contribution.person_id = before["person_id"]
    contribution.role = before["role"]
    contribution.order = before["order"]
    contribution.source = before["source"]
    contribution.confidence = before["confidence"]
    contribution.approved = before["approved"]
    contribution.save()


def _restore_organization_contribution(before: dict | None, after: dict | None) -> None:
    if before is None:
        if not after or not after.get("id"):
            return
        contribution = OrganizationContribution.objects.select_for_update().filter(pk=after["id"]).first()
        if contribution is None:
            return
        current = {
            "id": str(contribution.id),
            "organization_id": str(contribution.organization_id),
            "role": contribution.role,
            "verbatim_name": contribution.verbatim_name,
            "source": contribution.source,
            "confidence": contribution.confidence,
            "approved": contribution.approved,
        }
        if current != after:
            raise ResolutionDecisionError("机构责任关系已被后续修改，不能自动撤销。")
        contribution.delete()
        return
    contribution = OrganizationContribution.objects.select_for_update().filter(pk=before["id"]).first()
    if contribution is None:
        raise ResolutionDecisionError("原机构责任关系已经不存在，不能自动恢复。")
    contribution.organization_id = before["organization_id"]
    contribution.role = before["role"]
    contribution.verbatim_name = before["verbatim_name"]
    contribution.source = before["source"]
    contribution.confidence = before["confidence"]
    contribution.approved = before["approved"]
    contribution.save()


def _archive_created_entity(decision: DecisionLog) -> None:
    if not decision.after.get("entity_is_draft"):
        return
    target_id = str(decision.target_id or "")
    if decision.target_type == "person" and target_id:
        person = Person.objects.select_for_update().get(pk=target_id)
        if person.authority_status != Person.AuthorityStatus.DRAFT:
            raise ResolutionDecisionError("新建人物草稿已进入后续审核，不能自动撤销。")
        if hasattr(person, "scholar_profile"):
            raise ResolutionDecisionError("新建人物草稿已建立公开策展资料，不能自动撤销。")
        if person.contributions.exists():
            raise ResolutionDecisionError("新建人物草稿仍有关联作品，不能自动归档。")
        person.authority_status = Person.AuthorityStatus.ARCHIVED
        person.save(update_fields=["authority_status", "updated_at"])
    elif decision.target_type == "knowledge_node" and target_id:
        node = KnowledgeNode.objects.select_for_update().get(pk=target_id)
        if node.status != KnowledgePublicationStatus.DRAFT:
            raise ResolutionDecisionError("新建知识实体已进入后续审核，不能自动撤销。")
        node.status = KnowledgePublicationStatus.ARCHIVED
        node.save(update_fields=["status", "updated_at"])
    elif decision.target_type == "organization" and target_id:
        organization = OrganizationAuthority.objects.select_for_update().get(pk=target_id)
        if organization.authority_status != OrganizationAuthority.AuthorityStatus.DRAFT:
            raise ResolutionDecisionError("新建机构草稿已进入后续审核，不能自动撤销。")
        if organization.contributions.exists():
            raise ResolutionDecisionError("新建机构草稿仍有关联版本，不能自动归档。")
        organization.authority_status = OrganizationAuthority.AuthorityStatus.ARCHIVED
        organization.save(update_fields=["authority_status", "updated_at"])


@transaction.atomic
def revert_entity_resolution_decision(
    decision: DecisionLog,
    *,
    actor,
    reason: str,
    correlation_id: str = "",
) -> ResolutionRevertResult:
    if decision.resolution_candidate_id is None:
        raise ResolutionDecisionError("该决定不属于实体消歧，不能在此撤销。")
    candidate_hint = EntityResolutionCandidate.objects.only("upload_item_id").get(
        pk=decision.resolution_candidate_id
    )
    item = _lock_upload_context(candidate_hint.upload_item_id)
    decision = (
        DecisionLog.objects.select_for_update(of=("self",))
        .select_related("resolution_candidate__upload_item__edition", "review_task")
        .get(pk=decision.pk)
    )
    if decision.reverts_decision_id:
        raise ResolutionDecisionError("撤销记录本身不能再次撤销。")
    if decision.resolution_candidate_id is None:
        raise ResolutionDecisionError("该决定不属于实体消歧，不能在此撤销。")
    if decision.resolution_candidate.upload_item_id != item.id:
        raise ResolutionDecisionError("决定所属上传记录已变化，请刷新后重试。")
    decision.resolution_candidate.upload_item = item
    if decision.reverted_at:
        reversal = DecisionLog.objects.get(reverts_decision=decision)
        candidate = decision.resolution_candidate
        group = tuple(
            EntityResolutionCandidate.objects.filter(
                upload_item=candidate.upload_item,
                target_type=candidate.target_type,
                source_name=candidate.source_name,
            ).order_by("-match_score", "created_at")
        )
        return ResolutionRevertResult(
            candidate,
            group,
            decision.review_task,
            decision,
            reversal,
            True,
        )

    candidate = EntityResolutionCandidate.objects.select_for_update().get(
        pk=decision.resolution_candidate_id
    )
    candidate.upload_item = item
    if item.edition_id and item.edition.state == PublicationState.PUBLISHED:
        raise ResolutionDecisionError("已发布版本的实体决定不能直接撤销，请先创建修订或下架。")
    group = list(
        EntityResolutionCandidate.objects.select_for_update().filter(
            upload_item=item,
            target_type=candidate.target_type,
            source_name=candidate.source_name,
        ).order_by("-match_score", "created_at")
    )
    group_ids = [row.id for row in group]
    if DecisionLog.objects.filter(
        resolution_candidate_id__in=group_ids,
        created_at__gt=decision.created_at,
        reverts_decision__isnull=True,
    ).exclude(pk=decision.pk).exists():
        raise ResolutionDecisionError("该候选组已有后续决定，不能撤销较早记录。")
    expected_status = str(decision.after.get("status") or "")
    if expected_status and candidate.status != expected_status:
        raise ResolutionDecisionError("候选状态已被后续修改，不能自动撤销。")

    before = dict(decision.before or {})
    candidate_before = dict(before.get("candidate") or before)
    mutation_before = dict(before.get("mutation") or {})
    mutation_after = dict((decision.after or {}).get("mutation") or {})
    edition = item.edition if item.edition_id else None
    if decision.target_type == "work" and edition:
        edition.work_id = mutation_before.get("work_id") or edition.work_id
        edition.save(update_fields=["work", "updated_at"])
    elif decision.target_type == "publisher" and edition:
        edition.publisher_authority_id = mutation_before.get("publisher_authority_id") or None
        edition.save(update_fields=["publisher_authority", "updated_at"])
    elif decision.target_type == "person":
        _restore_contribution(
            mutation_before.get("contribution"),
            mutation_after.get("contribution"),
        )
    elif decision.target_type == "organization":
        _restore_organization_contribution(
            mutation_before.get("organization_contribution"),
            mutation_after.get("organization_contribution"),
        )

    _archive_created_entity(decision)

    sibling_before = {
        str(value.get("id")): value
        for value in before.get("siblings", [])
        if value.get("id")
    }
    for sibling in group:
        snapshot = sibling_before.get(str(sibling.id))
        if sibling.pk == candidate.pk or snapshot is None:
            continue
        sibling.status = snapshot.get("status", EntityResolutionCandidate.Status.PROPOSED)
        sibling.reviewed_by_id = snapshot.get("reviewed_by_id") or None
        sibling.reviewed_at = _restore_datetime(snapshot.get("reviewed_at"))
        sibling.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    candidate.status = candidate_before.get("status", EntityResolutionCandidate.Status.PROPOSED)
    candidate.candidate_entity_type = candidate_before.get(
        "candidate_entity_type", candidate.candidate_entity_type
    )
    candidate.candidate_entity_id = candidate_before.get("candidate_entity_id", "")
    candidate.label = candidate_before.get("label", candidate.label)
    candidate.reviewed_by_id = candidate_before.get("reviewed_by_id") or None
    candidate.reviewed_at = _restore_datetime(candidate_before.get("reviewed_at"))
    candidate.save(
        update_fields=[
            "status",
            "candidate_entity_type",
            "candidate_entity_id",
            "label",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )

    review_task = decision.review_task
    task_before = before.get("review_task")
    if review_task and task_before:
        review_task.status = task_before.get("status", ReviewTask.Status.PENDING)
        review_task.completed_by_id = task_before.get("completed_by_id") or None
        review_task.completed_at = _restore_datetime(task_before.get("completed_at"))
        review_task.details = task_before.get("details") or {}
        review_task.save(
            update_fields=["status", "completed_by", "completed_at", "details", "updated_at"]
        )

    now = timezone.now()
    decision.reverted_at = now
    decision.reverted_by = actor
    decision.reversal_reason = reason
    decision.save(
        update_fields=["reverted_at", "reverted_by", "reversal_reason", "updated_at"]
    )
    reversal = DecisionLog.objects.create(
        upload_item=item,
        review_task=review_task,
        resolution_candidate=candidate,
        actor=actor,
        action="revert_entity_resolution",
        target_type=decision.target_type,
        target_id=str(candidate.candidate_entity_id or ""),
        before={"decision_id": str(decision.id), "status": expected_status},
        after={"status": candidate.status, "restored": True},
        reason=reason,
        correlation_id=correlation_id,
        reverts_decision=decision,
    )
    refreshed_group = tuple(
        EntityResolutionCandidate.objects.filter(
            upload_item=item,
            target_type=candidate.target_type,
            source_name=candidate.source_name,
        ).order_by("-match_score", "created_at")
    )
    return ResolutionRevertResult(
        candidate,
        refreshed_group,
        review_task,
        decision,
        reversal,
        False,
    )
    OrganizationAuthority,
    OrganizationContribution,
