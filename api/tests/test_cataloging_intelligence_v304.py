from __future__ import annotations

from hashlib import sha256

import pytest
from django.utils import timezone

from catalog.models import (
    Asset,
    CatalogPublicationRevision,
    DocumentQualityAssessment,
    DocumentRevision,
    Edition,
    IntelligenceStatus,
    KnowledgeProjectionDelivery,
    KnowledgePublicationEvent,
    ProjectionState,
    PublicationState,
    Work,
)
from catalog.services.knowledge_publication import (
    create_catalog_publication_event,
    process_knowledge_event,
)
from catalog.serializers import WorkCardSerializer
from catalog.services.publication_eligibility import (
    active_asset_q,
    active_document_q,
)
from catalog.services.scoped_search import (
    SearchContext,
    SearchService,
    public_work_queryset,
)


pytestmark = pytest.mark.django_db


def _edition(*, title: str = "3.0.4 发布边界") -> Edition:
    work = Work.objects.create(
        document_type="book",
        title=title,
        language="zh-CN",
    )
    return Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug=f"v304-{work.id}",
    )


def _active_revision(edition: Edition, *, revision: int = 1):
    row = CatalogPublicationRevision.objects.create(
        edition=edition,
        revision=revision,
        status=CatalogPublicationRevision.Status.ACTIVE,
        snapshot={"work": {"title": edition.work.title}},
        changed_fields=["catalog_publish"],
        content_fingerprint=sha256(
            f"{edition.id}:{revision}".encode("utf-8")
        ).hexdigest(),
        metadata_ready=True,
        activated_at=timezone.now(),
    )
    edition.active_catalog_revision = row
    edition.metadata_ready_at = timezone.now()
    edition.intelligence_status = IntelligenceStatus.ACTIVE
    edition.save(
        update_fields=[
            "active_catalog_revision",
            "metadata_ready_at",
            "intelligence_status",
            "updated_at",
        ]
    )
    return row


def _publish_event(
    edition: Edition,
    *,
    event_type: str = KnowledgePublicationEvent.EventType.CATALOG_UPDATED,
    changed_fields=("cover",),
    key: str = "v304:test:event",
):
    return create_catalog_publication_event(
        edition,
        event_type=event_type,
        changed_fields=changed_fields,
        idempotency_key=key,
    )


def test_initial_publish_creates_immutable_revision_and_durable_deliveries():
    edition = _edition()

    event = _publish_event(
        edition,
        event_type=KnowledgePublicationEvent.EventType.CATALOG_PUBLISHED,
        changed_fields=("title",),
        key="v304:initial-publish",
    )

    edition.refresh_from_db()
    event.refresh_from_db()
    revision = event.catalog_revision
    assert revision.status == CatalogPublicationRevision.Status.PREPARING
    assert revision.revision == 1
    assert revision.snapshot["work"]["title"] == edition.work.title
    assert "catalog_publish" in revision.changed_fields
    assert edition.active_catalog_revision_id is None
    assert edition.intelligence_status == IntelligenceStatus.PROCESSING
    assert event.domain_event.catalog_revision_id == revision.id
    assert event.domain_event.canonical_revision == 1

    deliveries = {row.consumer: row for row in event.deliveries.all()}
    assert deliveries[KnowledgeProjectionDelivery.Consumer.FULLTEXT].status == (
        KnowledgeProjectionDelivery.Status.SKIPPED
    )
    assert deliveries[KnowledgeProjectionDelivery.Consumer.SEMANTIC].status == (
        KnowledgeProjectionDelivery.Status.SKIPPED
    )
    assert deliveries[KnowledgeProjectionDelivery.Consumer.VIEWPOINT].status == (
        KnowledgeProjectionDelivery.Status.SKIPPED
    )
    assert deliveries[KnowledgeProjectionDelivery.Consumer.RAG].status == (
        KnowledgeProjectionDelivery.Status.PENDING
    )
    assert set(
        ProjectionState.objects.filter(
            object_type="edition", object_id=edition.id
        ).values_list("projection_type", flat=True)
    ) == set(ProjectionState.ProjectionType.values)


def test_catalog_publication_idempotency_does_not_advance_revision_twice():
    edition = _edition(title="幂等发布")

    first = _publish_event(
        edition,
        event_type=KnowledgePublicationEvent.EventType.CATALOG_PUBLISHED,
        changed_fields=("title",),
        key="v304:idempotent-publish",
    )
    second = _publish_event(
        edition,
        event_type=KnowledgePublicationEvent.EventType.CATALOG_PUBLISHED,
        changed_fields=("title",),
        key="v304:idempotent-publish",
    )

    assert second.id == first.id
    assert CatalogPublicationRevision.objects.filter(edition=edition).count() == 1
    assert KnowledgePublicationEvent.objects.filter(object_id=edition.id).count() == 1


def test_cover_only_update_does_not_schedule_fulltext_or_semantic_projection():
    edition = _edition(title="只换封面")
    previous = _active_revision(edition)

    event = _publish_event(
        edition,
        changed_fields=("cover",),
        key="v304:cover-only",
    )

    edition.refresh_from_db()
    previous.refresh_from_db()
    assert edition.active_catalog_revision_id == previous.id
    assert previous.status == CatalogPublicationRevision.Status.ACTIVE
    assert event.catalog_revision.status == CatalogPublicationRevision.Status.PREPARING
    assert set(
        event.deliveries.values_list("consumer", flat=True)
    ) == {
        KnowledgeProjectionDelivery.Consumer.BIBLIOGRAPHIC_SEARCH,
        KnowledgeProjectionDelivery.Consumer.PUBLIC_CACHE,
        KnowledgeProjectionDelivery.Consumer.RAG,
    }
    assert set(
        ProjectionState.objects.filter(
            object_type="edition", object_id=edition.id
        ).values_list("projection_type", flat=True)
    ) == {ProjectionState.ProjectionType.PUBLIC}


def test_completed_update_atomically_activates_new_revision():
    edition = _edition(title="稳定版本切换")
    previous = _active_revision(edition)
    event = _publish_event(
        edition,
        changed_fields=("cover",),
        key="v304:activate-update",
    )
    ProjectionState.objects.filter(
        object_type="edition", object_id=edition.id
    ).update(
        projected_revision=event.domain_event.canonical_revision,
        status=ProjectionState.Status.CURRENT,
    )

    processed = process_knowledge_event(event.id)

    edition.refresh_from_db()
    previous.refresh_from_db()
    processed.catalog_revision.refresh_from_db()
    assert processed.status == KnowledgePublicationEvent.Status.COMPLETED
    assert previous.status == CatalogPublicationRevision.Status.SUPERSEDED
    assert edition.active_catalog_revision_id == processed.catalog_revision_id
    assert processed.catalog_revision.status == CatalogPublicationRevision.Status.ACTIVE
    assert edition.intelligence_status == IntelligenceStatus.ACTIVE
    assert set(processed.deliveries.values_list("status", flat=True)) == {
        KnowledgeProjectionDelivery.Status.COMPLETED
    }


def test_failed_update_preserves_previous_active_revision(settings):
    settings.KNOWLEDGE_EVENT_MAX_ATTEMPTS = 1
    edition = _edition(title="失败时保留旧版")
    previous = _active_revision(edition)
    event = _publish_event(
        edition,
        changed_fields=("cover",),
        key="v304:failed-update",
    )
    ProjectionState.objects.filter(
        object_type="edition", object_id=edition.id
    ).update(status=ProjectionState.Status.FAILED)

    processed = process_knowledge_event(event.id)

    edition.refresh_from_db()
    previous.refresh_from_db()
    processed.catalog_revision.refresh_from_db()
    assert processed.status == KnowledgePublicationEvent.Status.DEAD_LETTER
    assert processed.catalog_revision.status == CatalogPublicationRevision.Status.FAILED
    assert edition.active_catalog_revision_id == previous.id
    assert previous.status == CatalogPublicationRevision.Status.ACTIVE
    assert edition.intelligence_status == IntelligenceStatus.FAILED


def test_quality_gate_controls_fulltext_delivery_without_blocking_metadata():
    edition = _edition(title="正文质量门槛")
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/v304-quality.pdf",
        sha256=sha256(str(edition.id).encode("utf-8")).hexdigest(),
        byte_size=100,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        source_checksum=asset.sha256,
        text_checksum=sha256(b"verified text").hexdigest(),
        is_active=True,
    )
    DocumentQualityAssessment.objects.create(
        document_revision=revision,
        assessor_version="v304-test",
        reader_quality=0.9,
        fulltext_quality=0.8,
        semantic_quality=0.7,
        claim_quality=0.6,
        structure_quality=0.7,
        ocr_quality=0.8,
    )

    event = _publish_event(
        edition,
        event_type=KnowledgePublicationEvent.EventType.CATALOG_PUBLISHED,
        changed_fields=("document_revision",),
        key="v304:quality-ready",
    )

    assert event.catalog_revision.document_revision_id == revision.id
    assert event.payload["requested_fulltext_ready"] is True
    assert event.deliveries.get(
        consumer=KnowledgeProjectionDelivery.Consumer.FULLTEXT
    ).status == KnowledgeProjectionDelivery.Status.PENDING
    assert event.deliveries.get(
        consumer=KnowledgeProjectionDelivery.Consumer.SEMANTIC
    ).status == KnowledgeProjectionDelivery.Status.PENDING
    assert event.deliveries.get(
        consumer=KnowledgeProjectionDelivery.Consumer.VIEWPOINT
    ).status == KnowledgeProjectionDelivery.Status.PENDING


def test_withdrawal_switches_to_withdrawn_revision_and_emits_all_removals():
    edition = _edition(title="撤回传播")
    previous = _active_revision(edition)
    edition.state = PublicationState.WITHDRAWN
    edition.save(update_fields=["state", "updated_at"])

    event = _publish_event(
        edition,
        event_type=KnowledgePublicationEvent.EventType.CATALOG_WITHDRAWN,
        changed_fields=(),
        key="v304:withdraw",
    )

    edition.refresh_from_db()
    previous.refresh_from_db()
    assert event.catalog_revision.status == CatalogPublicationRevision.Status.WITHDRAWN
    assert edition.active_catalog_revision_id == event.catalog_revision_id
    assert edition.intelligence_status == IntelligenceStatus.WITHDRAWN
    assert previous.status == CatalogPublicationRevision.Status.SUPERSEDED
    assert "catalog_withdraw" in event.changed_fields
    assert {
        KnowledgeProjectionDelivery.Consumer.QUERY_LEXICON,
        KnowledgeProjectionDelivery.Consumer.FULLTEXT,
        KnowledgeProjectionDelivery.Consumer.SEMANTIC,
        KnowledgeProjectionDelivery.Consumer.RAG,
        KnowledgeProjectionDelivery.Consumer.VIEWPOINT,
        KnowledgeProjectionDelivery.Consumer.BIBLIOGRAPHIC_SEARCH,
        KnowledgeProjectionDelivery.Consumer.RECOMMENDATION,
    }.issubset(set(event.deliveries.values_list("consumer", flat=True)))


def test_public_catalog_uses_active_snapshot_and_hides_unactivated_rows():
    hidden = _edition(title="尚未激活的馆藏")
    assert public_work_queryset().filter(pk=hidden.work_id).exists() is False

    edition = _edition(title="已激活旧标题")
    _active_revision(edition)
    work = edition.work
    work.title = "仍在处理的新标题"
    work.save(update_fields=["title", "updated_at"])

    public_work = public_work_queryset().get(pk=work.id)
    payload = WorkCardSerializer(public_work).data
    assert payload["title"] == "已激活旧标题"
    assert SearchService().queryset(
        SearchContext.WORKS,
        "已激活旧标题",
    ).filter(pk=work.id).exists()
    assert SearchService().queryset(
        SearchContext.WORKS,
        "仍在处理的新标题",
    ).filter(pk=work.id).exists() is False


def test_reader_and_fulltext_predicates_use_active_revision_assets():
    edition = _edition(title="活动文件边界")
    active_asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/v304-active.pdf",
        sha256=sha256(b"v304-active").hexdigest(),
        byte_size=100,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    preparing_asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/v304-preparing.pdf",
        sha256=sha256(b"v304-preparing").hexdigest(),
        byte_size=100,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    document_revision = DocumentRevision.objects.create(
        asset=active_asset,
        revision=1,
        source_checksum=active_asset.sha256,
        text_checksum=sha256(b"active text").hexdigest(),
        is_active=True,
    )
    revision = _active_revision(edition)
    revision.reader_asset = active_asset
    revision.document_revision = document_revision
    revision.fulltext_ready = True
    revision.save(
        update_fields=[
            "reader_asset",
            "document_revision",
            "fulltext_ready",
            "updated_at",
        ]
    )

    assert set(
        Asset.objects.filter(active_asset_q(asset_prefix="")).values_list(
            "id", flat=True
        )
    ) == {active_asset.id}
    assert set(
        Asset.objects.filter(active_document_q(asset_prefix="")).values_list(
            "id", flat=True
        )
    ) == {active_asset.id}
    assert preparing_asset.id not in set(
        Asset.objects.filter(active_document_q(asset_prefix="")).values_list(
            "id", flat=True
        )
    )
