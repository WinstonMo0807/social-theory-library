from hashlib import sha256
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Asset,
    CuratedClaim,
    Edition,
    KnowledgeNode,
    OcrStatus,
    PageLabelStatus,
    PublicationEvent,
    PublicationState,
    PublicationBundle,
    PublicationBundleItem,
    Person,
    PublisherAuthority,
    RecommendationPolicy,
    RecommendationSnapshot,
    ScholarProfile,
    SemanticIndexStatus,
    TheorySchool,
    Topic,
)
from catalog.services.claims.curation import publish_work_curated_claims
from catalog.services.field_decisions import publication_field_check
from catalog.services.knowledge_publication import confirmed_bundle_links, create_catalog_publication_event
from distribution.models import CloudObject


class PublicationBlocked(RuntimeError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("；".join(reasons))


class PublicationWarningsRequireConfirmation(RuntimeError):
    def __init__(self, warnings: list[str]):
        self.warnings = warnings
        super().__init__("；".join(warnings))


def _asset_storage_readable(asset: Asset | None) -> bool:
    if asset is None or not asset.file.name or asset.status != Asset.Status.READY:
        return False
    try:
        return bool(asset.file.storage.exists(asset.file.name))
    except Exception:
        return False


_FIELD_LABELS = {
    "file": "文件", "title": "作品名称", "document_type": "资源类型",
    "language": "正文语言", "authors": "作者", "translators": "译者",
    "publisher": "出版社", "publication_year": "出版年份", "journal_title": "期刊名",
    "volume": "卷", "issue": "期", "degree_institution": "学位授予单位",
    "report_institution": "报告机构", "disciplines": "学科", "subdisciplines": "分支学科",
    "topics": "主题", "theories": "理论传统", "abstract": "简介", "cover": "封面",
}


def _publication_bundle_check(edition: Edition) -> dict[str, Any]:
    """Check the actual entities as well as the saved publication checklist."""
    bundles = edition.publication_bundles.filter(status=PublicationBundle.Status.DRAFT)
    items = list(PublicationBundleItem.objects.filter(bundle__in=bundles).order_by("created_at"))
    blockers: list[str] = []
    summary: list[dict[str, str]] = []
    confirmed_links = confirmed_bundle_links(edition, include_editorial_draft=True)
    models = {
        "person": (Person, "preferred_name", "学者"),
        "topic": (Topic, "name", "主题"),
        "knowledge_node": (KnowledgeNode, "canonical_name_zh", "理论节点"),
        "theory_school": (TheorySchool, "name", "理论传统"),
        "publisher": (PublisherAuthority, "canonical_name", "出版社"),
    }
    for item in items:
        if item.action == PublicationBundleItem.Action.CREATE and (item.object_type, str(item.object_id)) not in confirmed_links:
            continue
        label = item.label or "未命名对象"
        if item.blockers:
            blockers.append(f"{label}仍有待处理的发布问题")
        if item.action != PublicationBundleItem.Action.CREATE:
            continue
        target = models.get(str(item.object_type).casefold())
        if target is None:
            blockers.append(f"{label}无法随本次馆藏发布，请先完成对象资料")
            continue
        model, name_field, kind_label = target
        entity = model.objects.filter(pk=item.object_id).first()
        name = str(getattr(entity, name_field, "") or "").strip()
        if isinstance(entity, KnowledgeNode):
            name = name or entity.canonical_name_en.strip()
        if entity is None or not name or not item.minimum_complete:
            blockers.append(f"新增{kind_label}{label}尚未达到最低完整性要求")
            continue
        entity_status = getattr(entity, "editorial_status", getattr(entity, "status", "draft"))
        if not isinstance(entity, Person) and entity_status not in {"draft", "pending", "published"}:
            blockers.append(f"新增{kind_label}{name}已下线或拒绝，不能自动恢复")
        if isinstance(entity, Person):
            if entity.authority_status in {
                Person.AuthorityStatus.REJECTED,
                Person.AuthorityStatus.MERGED,
                Person.AuthorityStatus.ARCHIVED,
            }:
                blockers.append(f"新增学者{name}当前状态不能发布")
            if not ScholarProfile.objects.filter(person=entity).exists():
                blockers.append(f"新增学者{name}缺少学者资料")
            elif ScholarProfile.objects.filter(person=entity).exclude(editorial_status__in=["draft", "pending", "published"]).exists():
                blockers.append(f"新增学者{name}的资料已下线，不能自动恢复")
        summary.append({"kind": kind_label, "label": name, "object_id": str(item.object_id)})
    bundled = {(row.object_type, str(row.object_id)) for row in items if row.action == PublicationBundleItem.Action.CREATE}
    for object_type, identifier in confirmed_links:
        if (object_type, identifier) in bundled or object_type not in models:
            continue
        model, name_field, kind_label = models[object_type]
        entity = model.objects.filter(pk=identifier).first()
        if entity is None:
            continue
        state = entity.authority_status if isinstance(entity, Person) else getattr(entity, "editorial_status", getattr(entity, "status", "draft"))
        if state not in {"verified", "published"}:
            blockers.append(f"关联的{kind_label}{getattr(entity, name_field, '')}尚未加入本次新增对象，请在对应字段重新确认关联")
    return {"items": summary, "new_entities_count": len(summary), "blockers": blockers}


def publication_preflight(edition: Edition) -> dict[str, Any]:
    """Derive publication readiness from fields, relations, files and the bundle.

    Optional OCR and intelligence processing can finish after publication.
    Neither task completion nor visited workflow steps can confirm a field.
    """

    blockers: list[str] = []
    warnings: list[str] = []
    background_tasks: list[str] = []
    work = edition.work
    field_check = publication_field_check(edition)
    for problem in field_check["blockers"]:
        label = _FIELD_LABELS.get(problem["field"], "馆藏字段")
        blockers.append(
            f"{label}存在冲突，请先处理"
            if problem["code"] == "field_conflict"
            else f"{label}尚未填写或确认"
        )
    for problem in field_check["warnings"]:
        label = _FIELD_LABELS.get(problem["field"], "馆藏字段")
        warnings.append(f"{label}的相关信息已变化，建议重新检查")
    bundle_check = _publication_bundle_check(edition)
    blockers.extend(bundle_check["blockers"])
    original = edition.assets.filter(
        kind=Asset.Kind.ORIGINAL,
        status=Asset.Status.READY,
        is_current=True,
    ).order_by("-version", "-created_at").first()
    normalized = edition.assets.filter(
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
        is_current=True,
    ).order_by("-version", "-created_at").first()

    if not _asset_storage_readable(original):
        blockers.append("原始 PDF 不存在或当前无法读取")
    if not _asset_storage_readable(normalized):
        blockers.append("公开阅读锚点文件不存在或当前无法读取")
    elif normalized.validation_status == Asset.ValidationStatus.INVALID:
        blockers.append("公开阅读锚点文件验证失败")
    elif settings.REQUIRE_CLOUD_FOR_PUBLICATION and not normalized.cloud_objects.filter(
        status=CloudObject.Status.READY,
    ).exists():
        blockers.append("当前部署要求云端阅读副本，但副本尚未就绪")

    if not work.title.strip():
        warnings.append("题名尚未补全")
    if work.language not in {"zh-CN", "zh-TW", "en"}:
        warnings.append("正文语言尚未确认")
    if edition.publication_year is None:
        warnings.append("出版或完成年份尚未补全")
    if work.document_type == "book" and not edition.publisher.strip():
        warnings.append("图书出版者尚未补全")
    if work.document_type == "journal_article" and not edition.journal_title.strip():
        warnings.append("期刊名尚未补全")
    if work.document_type == "thesis":
        if not edition.degree_institution.strip():
            warnings.append("学位授予单位尚未补全")
        if not edition.degree_type.strip():
            warnings.append("学位类型尚未补全")
    if work.document_type == "report" and not (
        edition.report_institution.strip() or edition.publisher.strip()
    ):
        warnings.append("研究报告责任机构尚未补全")
    if not edition.citation_data:
        warnings.append("引用数据尚未生成")
    if not edition.canonical_filename:
        warnings.append("规范文件名尚未生成")
    if edition.ocr_status in {OcrStatus.PENDING, OcrStatus.RUNNING}:
        warnings.append("OCR 尚未完成，扫描件暂时不能选择文字")
        background_tasks.append("OCR")
    elif edition.ocr_status == OcrStatus.FAILED:
        warnings.append("OCR 失败，当前仍使用原始 PDF 阅读")
    elif edition.ocr_status == OcrStatus.DISABLED:
        warnings.append("该扫描文献已按批次策略停用 OCR，当前不能选择或检索正文文字")
    if edition.page_label_status != PageLabelStatus.READY:
        warnings.append("引用页码尚未完成校对")
        background_tasks.append("页码识别")
    if edition.semantic_index_status != SemanticIndexStatus.READY:
        warnings.append("正文智能检索尚未就绪，作品仍可正常阅读")
        background_tasks.append("正文智能检索")
    if edition.search_indexed_at is None:
        warnings.append("全文索引尚未确认就绪")
        background_tasks.append("全文索引")

    return {
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "background_tasks": list(dict.fromkeys(background_tasks)),
        "publication_bundle": bundle_check,
    }


def publication_readiness(
    edition: Edition,
    *,
    allow_low_confidence: bool = False,
) -> list[str]:
    # Compatibility entry point retained for the ingestion and existing admin
    # serializers.  Its meaning is now deliberately limited to hard blockers.
    return publication_preflight(edition)["blockers"]


def invalidate_public_recommendations() -> None:
    placements = [
        RecommendationPolicy.Placement.HOME_FEATURED,
        RecommendationPolicy.Placement.HOME_RANDOM,
        RecommendationPolicy.Placement.THEORY_WEEKLY,
    ]
    RecommendationSnapshot.objects.filter(
        policy__placement__in=placements,
        is_current=True,
    ).update(is_current=False, updated_at=timezone.now())


def _publication_event_key(value: str) -> str:
    """Fit a deterministic business key into PublicationEvent.max_length."""

    max_length = PublicationEvent._meta.get_field("idempotency_key").max_length
    if len(value) <= max_length:
        return value
    digest = sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{value[: max_length - len(digest) - 1]}:{digest}"


@transaction.atomic
def publish_edition(
    edition: Edition,
    actor=None,
    idempotency_key: str | None = None,
    *,
    allow_low_confidence: bool = False,
    confirm_warnings: bool = False,
    force_update: bool = False,
    changed_fields: list[str] | tuple[str, ...] | None = None,
) -> Edition:
    edition = Edition.objects.select_for_update().select_related("work").get(pk=edition.pk)
    has_curated_drafts = CuratedClaim.objects.filter(
        work=edition.work,
        status=CuratedClaim.Status.DRAFT,
        evidence_links__evidence_span__is_stale=False,
        evidence_links__evidence_span__document_revision__is_active=True,
    ).exists()
    if (
        edition.state == PublicationState.PUBLISHED
        and not has_curated_drafts
        and not force_update
    ):
        return edition
    preflight = publication_preflight(edition)
    if preflight["blockers"]:
        raise PublicationBlocked(preflight["blockers"])
    if preflight["warnings"] and not confirm_warnings:
        raise PublicationWarningsRequireConfirmation(preflight["warnings"])
    is_public_update = edition.state == PublicationState.PUBLISHED
    is_republication = edition.state == PublicationState.WITHDRAWN
    event_type = (
        PublicationEvent.EventType.REPUBLISH
        if is_republication
        else PublicationEvent.EventType.UPDATE
        if is_public_update
        else PublicationEvent.EventType.PUBLISH
    )
    event_key = idempotency_key or f"publish:{edition.id}:{edition.updated_at.isoformat()}"
    if is_republication:
        event_key = f"{event_key}:republish:{edition.updated_at.isoformat()}"
    elif is_public_update:
        event_key = f"{event_key}:curated-update:{edition.updated_at.isoformat()}"
    event_key = _publication_event_key(event_key)
    event, created = PublicationEvent.objects.get_or_create(
        idempotency_key=event_key,
        defaults={
            "edition": edition,
            "event_type": event_type,
            "actor": actor,
        },
    )
    now = timezone.now()
    edition.state = PublicationState.PUBLISHED
    edition.published_at = now
    if edition.first_published_at is None:
        edition.first_published_at = now
    edition.last_published_at = now
    edition.withdrawn_at = None
    edition.save(
        update_fields=[
            "state",
            "published_at",
            "first_published_at",
            "last_published_at",
            "withdrawn_at",
            "updated_at",
        ]
    )
    published_claims = publish_work_curated_claims(work=edition.work, actor=actor)
    publication_fields = list(changed_fields) if changed_fields is not None else ["catalog_publish"]
    if published_claims:
        publication_fields = sorted(set(publication_fields) | {"curated_claims"})
    try:
        knowledge_event = create_catalog_publication_event(
            edition,
            event_type=(
                "catalog_updated" if is_public_update else "catalog_published"
            ),
            changed_fields=publication_fields,
            actor=actor,
            idempotency_key=f"catalog-publication:{event.id}",
        )
    except ValueError as exc:
        raise PublicationBlocked([str(exc)]) from exc
    event.completed_at = now
    event.payload = {
        "state": PublicationState.PUBLISHED,
        "preflight": preflight,
        "warnings_confirmed": bool(preflight["warnings"]),
        "curated_claim_ids": [str(claim.id) for claim in published_claims],
        "knowledge_event_id": str(knowledge_event.id),
        "catalog_revision_id": str(knowledge_event.catalog_revision_id),
    }
    event.save(update_fields=["completed_at", "payload", "updated_at"])
    transaction.on_commit(invalidate_public_recommendations)
    edition.refresh_from_db()
    return edition


@transaction.atomic
def withdraw_edition(edition: Edition, actor=None, reason: str = "") -> Edition:
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    if edition.state == PublicationState.WITHDRAWN:
        return edition
    now = timezone.now()
    event = PublicationEvent.objects.create(
        edition=edition,
        event_type=PublicationEvent.EventType.WITHDRAW,
        idempotency_key=f"withdraw:{edition.id}:{now.timestamp()}",
        actor=actor,
        payload={"reason": reason},
        completed_at=now,
    )
    edition.state = PublicationState.WITHDRAWN
    edition.withdrawn_at = now
    edition.save(update_fields=["state", "withdrawn_at", "updated_at"])
    knowledge_event = create_catalog_publication_event(
        edition,
        event_type="catalog_withdrawn",
        changed_fields=["catalog_withdraw"],
        actor=actor,
        idempotency_key=f"catalog-publication:{event.id}",
    )
    event.payload = {
        **dict(event.payload or {}),
        "knowledge_event_id": str(knowledge_event.id),
        "catalog_revision_id": str(knowledge_event.catalog_revision_id),
    }
    event.save(update_fields=["payload", "updated_at"])
    transaction.on_commit(invalidate_public_recommendations)
    edition.refresh_from_db()
    return edition
