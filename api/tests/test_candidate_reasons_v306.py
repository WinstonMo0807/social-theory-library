"""Explicit rejection reasons belong to the existing immutable decision trail."""
import pytest

from catalog.services.cataloging_sessions import open_cataloging_session
from ingestion.models import DecisionLog, MetadataCandidate

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("reason", ["人物不符", "版本不符", "来源不可靠", "内容不支持", "其他：原文已更正"])
def test_A15_rejection_reason_is_retained_for_manual_candidate_and_retries(api_client, admin_user, reason):
    session, _ = open_cataloging_session(actor=admin_user, source_type="manual", title="拒绝理由测试", document_type="report", language="zh-CN")
    candidate = MetadataCandidate.objects.create(cataloging_session=session, field_name="abstract", value="不能覆盖的候选简介", source="isolated_reason_test")
    api_client.force_authenticate(admin_user)
    payload = {"edition_id": str(session.edition_id), "field_name": "abstract", "source_type": "metadata", "source_id": str(candidate.pk), "reason": reason}
    first = api_client.post("/api/catalog/admin/field-assistant/reject/", payload, format="json")
    assert first.status_code == 200, first.data
    repeated = api_client.post("/api/catalog/admin/field-assistant/reject/", payload, format="json")
    assert repeated.status_code == 200
    records = DecisionLog.objects.filter(metadata_candidate=candidate, action="reject_metadata_candidate")
    assert records.count() == 1
    record = records.get()
    assert record.reason == reason
    assert record.metadata_candidate.cataloging_session_id == session.pk
    candidate.refresh_from_db()
    session.edition.work.refresh_from_db()
    assert candidate.lifecycle == "rejected"
    assert session.edition.work.title == "拒绝理由测试"
