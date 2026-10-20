"""Synthetic reader/privacy regressions, written for unified acceptance; not run."""
from uuid import uuid4

import pytest

from catalog.models import Asset, Edition, PublicationState, Work
from reading.models import ReadingProgress, SavedItem
from reading.services import current_reader_asset_for_work, readable_progress_for_user
from .v304_helpers import activate_catalog_revision


def readable_work():
    work = Work.objects.create(title="合成资格回归文献", document_type="book")
    edition = Edition.objects.create(work=work, state=PublicationState.PUBLISHED,
        is_primary=True, public_slug="synthetic-reader-boundary")
    asset = Asset.objects.create(edition=edition, kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY, validation_status=Asset.ValidationStatus.VALID,
        access_status=Asset.AccessStatus.PUBLIC, file="synthetic/boundary.pdf", sha256="e" * 64)
    revision = activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=False)
    return work, asset, revision


@pytest.mark.django_db
@pytest.mark.parametrize("field,value", [
    ("kind", "original"), ("status", "failed"),
    ("validation_status", "pending"), ("file", ""),
    ("snapshot_identity", "missing"), ("snapshot_identity", "different"),
])
def test_saved_work_retains_metadata_without_reader_link_for_invalid_source(api_client, reader_user, field, value):
    work, asset, revision = readable_work()
    progress = ReadingProgress.objects.create(user=reader_user, asset=asset, current_page=7)
    if field == "snapshot_identity":
        revision.snapshot["document"]["asset_id"] = None if value == "missing" else str(uuid4())
        revision.save(update_fields=["snapshot"])
    else:
        Asset.objects.filter(pk=asset.pk).update(**{field: value})
    api_client.force_authenticate(reader_user)
    response = api_client.post("/api/reading/saved/", {"work": str(work.pk)}, format="json")
    assert response.status_code == 201
    assert response.data["title"] == "合成资格回归文献"
    assert response.data["work_data"]["edition"]["readable_asset"] is None
    assert response.data["reading_progress"] is None
    assert current_reader_asset_for_work(work, user=reader_user) is None
    assert not readable_progress_for_user(reader_user).exists()
    assert ReadingProgress.objects.filter(pk=progress.pk, current_page=7).exists()
    assert SavedItem.objects.filter(user=reader_user, work=work).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("role,is_staff,access,visible", [
    ("reader", False, "registered", True),
    ("reader", True, "private", False),
    ("reader", True, "restricted", False),
    ("admin", False, "private", True),
    ("editor", False, "restricted", True),
    ("reviewer", False, "private", True),
])
def test_reader_qualification_preserves_library_role_and_django_staff_difference(reader_user, role, is_staff, access, visible):
    work, asset, _ = readable_work()
    reader_user.role, reader_user.is_staff = role, is_staff
    reader_user.save(update_fields=["role", "is_staff"])
    asset.access_status = access
    asset.save(update_fields=["access_status"])
    ReadingProgress.objects.create(user=reader_user, asset=asset)
    assert bool(current_reader_asset_for_work(work, user=reader_user)) is visible
    assert readable_progress_for_user(reader_user).exists() is visible


@pytest.mark.django_db
@pytest.mark.parametrize("collection", ["saved", "lists", "research-projects", "reading-plans"])
def test_each_private_collection_request_rejects_intermediate_cookie_owner(api_client, reader_user, admin_user, collection):
    path = f"/api/reading/{collection}/"
    headers = {"HTTP_X_READER_OWNER": str(reader_user.pk)}
    api_client.force_authenticate(reader_user)
    assert api_client.get(path, **headers).status_code == 200
    api_client.force_authenticate(admin_user)
    rejected = api_client.get(path, **headers)
    assert rejected.status_code == 403
    assert rejected["Cache-Control"] == "private, no-store"
    api_client.force_authenticate(reader_user)
    assert api_client.get(path, **headers).status_code == 200
