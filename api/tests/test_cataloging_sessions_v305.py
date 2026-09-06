from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from catalog.models import CatalogingSession, Edition, Work
from catalog.services.cataloging_sessions import (
    CatalogingSessionConflict, abandon_cataloging_session, open_cataloging_session,
)
from catalog.services.publication_eligibility import public_editions
from ingestion.models import AuditEvent, UploadBatch, UploadItem


pytestmark = pytest.mark.django_db


def manual_session(admin_user, **kwargs):
    return open_cataloging_session(actor=admin_user, source_type="manual", title="无文件书目", **kwargs)[0]


def test_manual_creation_creates_real_drafts_without_upload(admin_user):
    session = manual_session(admin_user)
    assert session.edition.work.title == "无文件书目"
    assert session.work_id == session.edition.work_id
    assert session.edition.state == "draft"
    assert session.status == "drafting"
    assert session.base_public_revision_id is None
    assert not UploadItem.objects.exists()
    assert not UploadBatch.objects.exists()
    assert not public_editions().exists()


def test_manual_create_retries_do_not_duplicate_catalog(admin_user):
    key = uuid4()
    first = manual_session(admin_user, request_key=key)
    second = manual_session(admin_user, request_key=key)
    assert first.pk == second.pk
    assert Work.objects.count() == Edition.objects.count() == CatalogingSession.objects.count() == 1


def test_existing_entry_reuses_same_open_process(admin_user):
    first = manual_session(admin_user)
    second, created = open_cataloging_session(actor=admin_user, edition_id=first.edition_id)
    assert second.pk == first.pk
    assert not created
    assert second.source_type == "manual"


def test_upload_entry_keeps_the_real_upload_reference(admin_user):
    batch = UploadBatch.objects.create(created_by=admin_user)
    item = UploadItem.objects.create(batch=batch, source_filename="real-upload.pdf")
    session, created = open_cataloging_session(actor=admin_user, upload_item_id=item.pk, source_type="upload")
    assert created
    assert session.upload_item_id == item.pk
    assert session.edition_id is None
    assert session.work_id is None
    assert open_cataloging_session(actor=admin_user, upload_item_id=item.pk, source_type="upload")[0].pk == session.pk


def test_abandon_preserves_draft_and_audits_once(admin_user):
    session = manual_session(admin_user)
    abandoned = abandon_cataloging_session(session.pk, actor=admin_user)
    assert abandoned.status == "abandoned"
    assert Work.objects.filter(pk=session.work_id).exists()
    assert Edition.objects.filter(pk=session.edition_id).exists()
    abandon_cataloging_session(session.pk, actor=admin_user)
    assert AuditEvent.objects.filter(action="cataloging_session.abandon").count() == 1
    reopened, created = open_cataloging_session(actor=admin_user, edition_id=session.edition_id)
    assert created and reopened.pk != session.pk


def test_upload_session_attaches_only_its_later_created_edition(admin_user):
    batch = UploadBatch.objects.create(created_by=admin_user)
    item = UploadItem.objects.create(batch=batch, source_filename="later.pdf")
    first, _created = open_cataloging_session(actor=admin_user, source_type="upload", upload_item_id=item.pk)
    edition = Edition.objects.create(work=Work.objects.create(title="上传建立的作品", document_type="book"))
    item.edition = edition
    item.save(update_fields=["edition", "updated_at"])
    attached, created = open_cataloging_session(actor=admin_user, source_type="upload", upload_item_id=item.pk)
    assert not created
    assert attached.pk == first.pk and attached.edition_id == edition.pk


def test_publishing_session_cannot_be_abandoned(admin_user):
    session = manual_session(admin_user)
    CatalogingSession.objects.filter(pk=session.pk).update(status="publishing")
    with pytest.raises(CatalogingSessionConflict):
        abandon_cataloging_session(session.pk, actor=admin_user)


def test_database_prevents_two_open_sessions_for_same_edition(admin_user):
    session = manual_session(admin_user)
    with pytest.raises(IntegrityError), transaction.atomic():
        CatalogingSession.objects.create(source_type="existing", edition=session.edition)


def test_base_public_revision_must_belong_to_session_edition(admin_user):
    from tests.test_publication_invariants_v305 import published_edition

    session = manual_session(admin_user)
    _other, revision = published_edition("其他版本")
    session.base_public_revision = revision
    with pytest.raises(ValidationError, match="公开基线"):
        session.full_clean()


def test_normal_admin_can_create_reopen_and_read_session_without_writes(api_client, admin_user):
    assert not admin_user.is_superuser
    api_client.force_authenticate(admin_user)
    payload = {"source_type": "manual", "title": "手工录入", "request_key": str(uuid4())}
    created = api_client.post("/api/catalog/admin/cataloging-sessions/", payload, format="json")
    assert created.status_code == 201
    assert created["Cache-Control"] == "private, no-store"
    assert created.data["upload_item_id"] is None
    repeat = api_client.post("/api/catalog/admin/cataloging-sessions/", payload, format="json")
    assert repeat.status_code == 200
    assert repeat.data["id"] == created.data["id"]
    before = (CatalogingSession.objects.count(), AuditEvent.objects.count())
    read = api_client.get(f"/api/catalog/admin/cataloging-sessions/{created.data['id']}/")
    assert read.status_code == 200
    assert read.data["workspace"]["context"]["work_id"] == created.data["work_id"]
    assert (CatalogingSession.objects.count(), AuditEvent.objects.count()) == before
    assert not UploadItem.objects.exists()


@pytest.mark.parametrize("authenticated", [False, True])
def test_reader_and_anonymous_cannot_access_cataloging(api_client, reader_user, authenticated):
    if authenticated:
        api_client.force_authenticate(reader_user)
    for response in (
        api_client.get("/api/catalog/admin/cataloging-sessions/"),
        api_client.post("/api/catalog/admin/cataloging-sessions/", {"source_type": "manual"}, format="json"),
        api_client.get(f"/api/catalog/admin/cataloging-sessions/{uuid4()}/"),
    ):
        assert response.status_code in {401, 403}
        assert response["Cache-Control"] == "private, no-store"
    assert not CatalogingSession.objects.exists()


def test_create_does_not_accept_forged_upload_context(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    response = api_client.post("/api/catalog/admin/cataloging-sessions/", {
        "source_type": "manual", "upload_item_id": str(uuid4()),
    }, format="json")
    assert response.status_code == 400
    assert not Work.objects.exists()
