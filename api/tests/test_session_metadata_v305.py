import pytest

from catalog.models import CatalogFieldDecision
from catalog.services.cataloging_sessions import open_cataloging_session
from catalog.services.field_assistant import FieldAssistantRequest, FieldAssistantService
from catalog.services.catalog_consistency_audit import catalog_consistency_report
from ingestion.models import MetadataCandidate, UploadItem
from ingestion.services.candidate_store import persist_metadata_candidates
from ingestion.services.metadata import Candidate


pytestmark = pytest.mark.django_db


def session(admin_user):
    return open_cataloging_session(actor=admin_user, source_type="manual", title="原题名")[0]


def test_metadata_import_is_a_candidate_until_human_adoption(api_client, admin_user):
    active = session(admin_user)
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/cataloging-sessions/{active.pk}/metadata/import/"
    response = api_client.post(url, {"source_label": "人工核对书目", "fields": {"publication_year": 2020, "title": "外部题名"}}, format="json")
    assert response.status_code == 201
    assert response.data["canonical_changed"] is False
    active.edition.refresh_from_db()
    assert active.edition.publication_year is None
    assert active.edition.work.title == "原题名"
    assert not UploadItem.objects.exists()
    service = FieldAssistantService()
    lookup = service.lookup(FieldAssistantRequest(object_type="edition", object_id=active.edition_id, field_name="publication_year"))
    assert lookup.results
    row = MetadataCandidate.objects.get(cataloging_session=active, field_name="publication_year")
    service.adopt(edition_id=active.edition_id, field_name="publication_year", source_type="metadata", source_id=row.pk, actor=admin_user)
    active.edition.refresh_from_db()
    assert active.edition.publication_year == 2020
    assert CatalogFieldDecision.objects.get(edition=active.edition, field_name="publication_year").status == "confirmed"
    detail = api_client.get(f"/api/catalog/admin/cataloging-sessions/{active.pk}/")
    assert len(detail.data["workspace"]["candidates"]["metadata"]) == 2
    assert catalog_consistency_report()["read_only"] is True


def test_same_field_in_another_session_is_not_superseded(admin_user):
    first, other = session(admin_user), session(admin_user)
    for active in (first, other):
        persist_metadata_candidates(None, [Candidate("publication_year", 2020, "manual", 0.1)], cataloging_session=active)
    service = FieldAssistantService()
    row = MetadataCandidate.objects.get(cataloging_session=other)
    service.adopt(edition_id=other.edition_id, field_name="publication_year", source_type="metadata", source_id=row.pk, actor=admin_user)
    first_row = MetadataCandidate.objects.get(cataloging_session=first)
    service.adopt(edition_id=first.edition_id, field_name="publication_year", source_type="metadata", source_id=first_row.pk, actor=admin_user)
    row.refresh_from_db()
    assert row.lifecycle == "accepted"


def test_import_retry_preserves_rejection_and_does_not_create_duplicate(admin_user):
    from ingestion.services.candidate_decisions import set_candidate_decision

    active = session(admin_user)
    values = [Candidate("title", "不采用题名", "manual", 0)]
    persist_metadata_candidates(None, values, cataloging_session=active)
    row = MetadataCandidate.objects.get(cataloging_session=active)
    set_candidate_decision(row, action="reject", actor=admin_user)
    persist_metadata_candidates(None, values, cataloging_session=active)
    row.refresh_from_db()
    assert row.lifecycle == "rejected"
    assert MetadataCandidate.objects.filter(cataloging_session=active).count() == 1


def test_metadata_candidate_requires_real_context():
    with pytest.raises(ValueError, match="真实"):
        persist_metadata_candidates(None, [Candidate("title", "不能保存", "manual", 0)])
