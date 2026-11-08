from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.models import Asset, CapabilityDemand, DocumentRevision, Edition, EvidenceSpan, Page, Work
from common.task_runtime import _reconciliation_demands, reconcile_capability_runtime

pytestmark = pytest.mark.django_db


def test_claim_backlog_reads_provenance_in_batches_and_preserves_live_waiting_work():
    work = Work.objects.create(title="Batch reconciliation fixture")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(edition=edition, file="fixture.pdf", sha256="a" * 64, byte_size=1)
    revision = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum="a" * 64, text_checksum="b" * 64)
    page = Page.objects.create(asset=asset, index=1, text_source="embedded")
    span = EvidenceSpan.objects.create(document_revision=revision, page=page, page_number=1,
                                       original_text="Original evidence remains unchanged.", content_hash="c" * 64)
    demands = [CapabilityDemand(owner_type="EvidenceSpan", owner_key=str(span.id),
                capability="llm_small", state="waiting_for_capability", idempotency_key=f"batch:{n}",
                payload={"task_kind": "claim_extraction", "evidence_span_id": str(span.id)}) for n in range(401)]
    CapabilityDemand.objects.bulk_create(demands)
    with CaptureQueriesContext(connection) as queries:
        rows = list(_reconciliation_demands(CapabilityDemand.objects.order_by("id")))
    assert len(rows) == 401
    assert all(reason == "" for _, reason in rows)
    # One demand query plus three provenance batches, not 401 point lookups.
    assert len(queries) == 4
    reconcile_capability_runtime()
    assert CapabilityDemand.objects.filter(state="waiting_for_capability").count() == 401
    span.refresh_from_db()
    assert span.original_text == "Original evidence remains unchanged."


@pytest.mark.parametrize("invalidity", ["stale", "inactive_revision", "missing"])
def test_batch_keeps_invalid_source_cancellation(invalidity):
    work = Work.objects.create(title="Invalid source fixture")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(edition=edition, file="fixture.pdf", sha256="d" * 64, byte_size=1)
    revision = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum="d" * 64,
                    text_checksum="e" * 64, is_active=invalidity != "inactive_revision")
    page = Page.objects.create(asset=asset, index=1, text_source="embedded")
    span = EvidenceSpan.objects.create(document_revision=revision, page=page, page_number=1,
                    original_text="Evidence", content_hash="f" * 64, is_stale=invalidity == "stale")
    span_id = str(uuid4()) if invalidity == "missing" else str(span.id)
    demand = CapabilityDemand.objects.create(owner_type="EvidenceSpan", owner_key=span_id,
                capability="llm_small", state="waiting_for_capability", idempotency_key="invalid-source",
                payload={"task_kind": "claim_extraction", "evidence_span_id": span_id})
    reconcile_capability_runtime()
    demand.refresh_from_db()
    assert demand.state == "canceled"
    assert demand.last_error_code == "source_superseded"
