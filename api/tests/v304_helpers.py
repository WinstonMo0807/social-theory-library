from __future__ import annotations

import json
from hashlib import sha256

from django.db.models import Max
from django.utils import timezone

from catalog.models import (
    Asset,
    CatalogPublicationRevision,
    DocumentRevision,
    Edition,
    IntelligenceStatus,
    PublicationState,
)
from catalog.services.knowledge_publication import catalog_snapshot


def activate_catalog_revision(
    edition: Edition,
    *,
    reader_asset: Asset | None = None,
    document_revision: DocumentRevision | None = None,
    fulltext_ready: bool = True,
) -> CatalogPublicationRevision:
    """Give a published test edition an explicit activated serving snapshot.

    Public consumers in 3.0.4 no longer infer eligibility from
    ``Edition.state`` alone.  Tests that model a formally published holding use
    this helper so reader and full-text access point to one exact immutable
    catalog/document revision.
    """

    if edition.state != PublicationState.PUBLISHED:
        raise ValueError("only published test editions can be activated")

    reader_asset = reader_asset or (
        edition.assets.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        )
        .order_by("-version", "-created_at")
        .first()
    )
    if reader_asset is None:
        raise ValueError("an activated test edition requires a ready normalized asset")

    if fulltext_ready and document_revision is None:
        document_revision = (
            reader_asset.document_revisions.filter(is_active=True)
            .order_by("-revision", "-created_at")
            .first()
        )
        if document_revision is None:
            page_text = "\n".join(
                reader_asset.pages.order_by("index").values_list("text", flat=True)
            )
            next_revision = (
                reader_asset.document_revisions.aggregate(value=Max("revision"))["value"]
                or 0
            ) + 1
            document_revision = DocumentRevision.objects.create(
                asset=reader_asset,
                revision=next_revision,
                source_checksum=reader_asset.sha256,
                text_checksum=sha256(page_text.encode("utf-8")).hexdigest(),
                parser_name="test-fixture",
                parser_version="3.0.4",
                extraction_method=reader_asset.extraction_method or "test",
                extraction_version="3.0.4",
                is_active=True,
            )

    snapshot, related_entities = catalog_snapshot(edition)
    revision_number = (
        edition.catalog_revisions.aggregate(value=Max("revision"))["value"] or 0
    ) + 1
    fingerprint = sha256(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    now = timezone.now()
    revision = CatalogPublicationRevision.objects.create(
        edition=edition,
        revision=revision_number,
        status=CatalogPublicationRevision.Status.ACTIVE,
        snapshot=snapshot,
        changed_fields=["catalog_publish"],
        related_entities=related_entities,
        document_revision=document_revision if fulltext_ready else None,
        reader_asset=reader_asset,
        metadata_ready=True,
        fulltext_ready=bool(fulltext_ready and document_revision is not None),
        provenance={"source": "test_fixture"},
        content_fingerprint=fingerprint,
        activated_at=now,
    )
    edition.active_catalog_revision = revision
    edition.metadata_ready_at = now
    edition.fulltext_ready_at = now if revision.fulltext_ready else None
    edition.intelligence_status = IntelligenceStatus.ACTIVE
    edition.save(
        update_fields=[
            "active_catalog_revision",
            "metadata_ready_at",
            "fulltext_ready_at",
            "intelligence_status",
            "updated_at",
        ]
    )
    return revision
