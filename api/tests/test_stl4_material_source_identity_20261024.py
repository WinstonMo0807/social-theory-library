"""Deferred M07 source-identity acceptance; not executed during development."""
from hashlib import sha256
import pytest
from catalog.models import Work, Edition, Asset, CatalogingSession
from catalog.services.catalog_candidates import _metadata_evidence
from catalog.services.edition_file_workspace import state
from catalog.services.edition_files import EditionFileError
from ingestion.models import MetadataCandidate, CandidateEvidence

pytestmark=pytest.mark.django_db


def source(admin_user):
    work=Work.objects.create(title="具备明确原文件的来源")
    edition=Edition.objects.create(work=work,publication_mode="bibliographic")
    session=CatalogingSession.objects.create(work=work,edition=edition,created_by=admin_user,source_type="manual")
    old=Asset.objects.create(edition=edition,kind="original",status="ready",mime_type="application/pdf",version=1,
        is_current=False,page_count=10,sha256=sha256(b"synthetic old source identity").hexdigest())
    candidate=MetadataCandidate.objects.create(cataloging_session=session,field_name="title",source="pdf_metadata",value=work.title)
    return work,edition,old,candidate


def test_evidence_preserves_original_identity_after_more_file_versions(admin_user,settings):
    settings.REQUIRE_CLOUD_FOR_PUBLICATION=False
    work,edition,old,candidate=source(admin_user)
    CandidateEvidence.objects.create(metadata_candidate=candidate,asset=old,page_number=4,text_quote="合成的来源摘录",source_kind="pdf_metadata")
    for number in range(2,24):
        Asset.objects.create(edition=edition,kind="original",status="ready",mime_type="application/pdf",version=number,
            is_current=False,sha256=sha256(f"synthetic source {number}".encode()).hexdigest())
    locator=_metadata_evidence(candidate)[0]["locator"]
    assert locator=={"asset_id":str(old.pk),"edition_id":str(edition.pk),"work_id":str(work.pk),"title":work.title,"page":4}
    result=state(work.pk,admin_user,edition_id=edition.pk,asset_id=old.pk)
    assert all(row["id"]!=str(old.pk) for row in result["files"]["results"])
    assert result["inspected_file"]["id"]==str(old.pk)
    assert not result["inspected_file"]["can_adopt"]


def test_cross_version_file_is_not_replaced_with_current_reader(admin_user,settings):
    settings.REQUIRE_CLOUD_FOR_PUBLICATION=False
    work,edition,old,_=source(admin_user)
    other=Edition.objects.create(work=work,publication_mode="bibliographic")
    with pytest.raises(EditionFileError):state(work.pk,admin_user,edition_id=other.pk,asset_id=old.pk)


def test_local_record_and_external_source_keep_their_locators(admin_user):
    work,edition,_,candidate=source(admin_user)
    candidate.source="local_catalog"
    candidate.evidence={"catalog_work_id":str(work.pk),"catalog_edition_id":str(edition.pk),"source_url":"https://example.org/metadata"}
    candidate.save()
    locator=_metadata_evidence(candidate)[0]["locator"]
    assert locator["work_id"]==str(work.pk) and locator["edition_id"]==str(edition.pk)
    assert locator["url"]=="https://example.org/metadata" and "asset_id" not in locator
