import io
import json
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    Page,
    Passage,
    PublicationState,
    Work,
)
from ingestion.management.commands.verify_ingestion_item import verify_item
from ingestion.models import UploadBatch, UploadItem


def _processed_item(admin_user, *, published: bool = False) -> UploadItem:
    work = Work.objects.create(document_type=DocumentType.BOOK, title="入库核验样书")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED if published else PublicationState.DRAFT,
        public_slug="ingestion-verification-book" if published else None,
        search_indexed_at=timezone.now() if published else None,
        public_asset_prepared_at=timezone.now() if published else None,
        published_at=timezone.now() if published else None,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/verification/book.pdf",
        sha256="9" * 64,
        byte_size=4096,
        page_count=1,
        status=Asset.Status.READY,
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        text="这是一段可以全文检索的社会科学原文。",
        normalized_text="这是一段可以全文检索的社会科学原文。",
        text_source=Page.TextSource.EMBEDDED,
    )
    Passage.objects.create(
        page=page,
        order=1,
        text=page.text,
        normalized_text=page.normalized_text,
        end_offset=len(page.text),
    )
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(
        batch=batch,
        source_filename="入库核验样书.pdf",
        file="incoming/verification/source.pdf",
        byte_size=4096,
        status=UploadItem.Status.PUBLISHED if published else UploadItem.Status.NEEDS_REVIEW,
        stage_progress=100 if published else 88,
        dispatch_status=UploadItem.DispatchStatus.COMPLETED,
        dispatch_kind=UploadItem.DispatchKind.REVIEWED if published else UploadItem.DispatchKind.INITIAL,
        edition=edition,
        asset=asset,
    )


@pytest.mark.django_db
def test_verify_ingestion_item_accepts_review_ready_document(admin_user):
    item = _processed_item(admin_user)

    with patch(
        "ingestion.management.commands.verify_ingestion_item._stored_file",
        return_value=(True, 4096, "stored.pdf"),
    ):
        result = verify_item(item, expected_status=UploadItem.Status.NEEDS_REVIEW)

    assert result["ok"] is True
    assert result["item"]["pages"] == 1
    assert result["item"]["passages"] == 1
    assert result["warnings"][0]["name"] == "语义分块可用"


@pytest.mark.django_db
def test_verify_ingestion_item_accepts_published_document(admin_user):
    item = _processed_item(admin_user, published=True)
    output = io.StringIO()

    with patch(
        "ingestion.management.commands.verify_ingestion_item._stored_file",
        return_value=(True, 4096, "stored.pdf"),
    ):
        call_command(
            "verify_ingestion_item",
            item_id=str(item.id),
            expect_status=UploadItem.Status.PUBLISHED,
            json=True,
            strict=True,
            stdout=output,
        )

    payload = json.loads(output.getvalue())
    assert payload["ok"] is True
    assert payload["item"]["public_slug"] == "ingestion-verification-book"


@pytest.mark.django_db
def test_verify_ingestion_item_strict_fails_when_file_is_missing(admin_user):
    item = _processed_item(admin_user)

    with patch(
        "ingestion.management.commands.verify_ingestion_item._stored_file",
        return_value=(False, 0, "missing.pdf"),
    ):
        with pytest.raises(CommandError, match="尚未完成"):
            call_command(
                "verify_ingestion_item",
                item_id=str(item.id),
                strict=True,
            )
