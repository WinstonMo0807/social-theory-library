"""Synthetic cases for final PDF24–27. Written during development; not executed."""
import pytest

from catalog.models import Asset, Edition, PublicationState, Work
from reading.models import ReadingList, ReadingListItem, ReadingProgress, SavedItem
from .v304_helpers import activate_catalog_revision


def metadata_work():
    work = Work.objects.create(title="合成公开书目", document_type="book")
    edition = Edition.objects.create(work=work, state=PublicationState.PUBLISHED,
                                     is_primary=True, public_slug="synthetic-metadata-work")
    activate_catalog_revision(edition, fulltext_ready=False)
    return work, edition


@pytest.mark.django_db
def test_public_metadata_can_be_saved_without_a_fabricated_reading_position(api_client, reader_user):
    work, _ = metadata_work()
    api_client.force_authenticate(reader_user)
    first = api_client.post("/api/reading/saved/", {"work": str(work.pk)}, format="json")
    second = api_client.post("/api/reading/saved/", {"work": str(work.pk)}, format="json")
    assert first.status_code == second.status_code == 201
    assert first.data["id"] == second.data["id"]
    assert first.data["reading_progress"] is None
    assert SavedItem.objects.filter(user=reader_user, work=work).count() == 1
    assert not ReadingProgress.objects.filter(user=reader_user).exists()


@pytest.mark.django_db
def test_favorites_keep_published_title_until_next_activation_and_mask_withdrawal(api_client, reader_user):
    work, edition = metadata_work()
    saved = SavedItem.objects.create(user=reader_user, work=work)
    work.title = "未公开的编辑稿题名"
    work.save(update_fields=["title"])
    api_client.force_authenticate(reader_user)
    response = api_client.get(f"/api/reading/saved/{saved.pk}/")
    assert response.data["title"] == "合成公开书目"
    assert response.data["work_data"]["title"] == "合成公开书目"
    edition.state = PublicationState.WITHDRAWN
    edition.save(update_fields=["state"])
    response = api_client.get(f"/api/reading/saved/{saved.pk}/")
    assert response.data["work_data"] is None
    assert "未公开" not in str(response.data)
    assert api_client.delete(f"/api/reading/saved/{saved.pk}/").status_code == 204


@pytest.mark.django_db
def test_list_add_is_idempotent_public_only_and_private_to_owner(api_client, reader_user, admin_user):
    work, edition = metadata_work()
    reading_list = ReadingList.objects.create(user=reader_user, title="合成书单")
    api_client.force_authenticate(reader_user)
    path = f"/api/reading/lists/{reading_list.pk}/add_item/"
    first = api_client.post(path, {"work": str(work.pk)}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk))
    second = api_client.post(path, {"work": str(work.pk)}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk))
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.data["id"] == second.data["id"]
    assert ReadingListItem.objects.filter(reading_list=reading_list).count() == 1
    api_client.force_authenticate(admin_user)
    assert api_client.post(path, {"work": str(work.pk)}, format="json").status_code == 404
    api_client.force_authenticate(reader_user)
    edition.state = PublicationState.WITHDRAWN
    edition.save(update_fields=["state"])
    assert api_client.post(path, {"work": str(work.pk)}, format="json").status_code == 400
    detail = api_client.get(f"/api/reading/lists/{reading_list.pk}/")
    assert detail.data["items"][0]["title"] == "来源暂不可用"


@pytest.mark.django_db
def test_cookie_owner_change_rejects_saved_and_list_mutations(api_client, reader_user, admin_user):
    work, _ = metadata_work()
    reading_list = ReadingList.objects.create(user=admin_user, title="另一账户书单")
    api_client.force_authenticate(admin_user)
    assert api_client.post("/api/reading/saved/", {"work": str(work.pk)}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 403
    assert api_client.post(f"/api/reading/lists/{reading_list.pk}/add_item/", {"work": str(work.pk)}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 403
    assert not SavedItem.objects.exists()
    assert not ReadingListItem.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("access,visible", [("public", True), ("registered", True), ("private", False), ("restricted", False)])
def test_saved_progress_respects_current_reader_file_access(api_client, reader_user, access, visible):
    work, edition = metadata_work()
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready",
        validation_status=Asset.ValidationStatus.VALID,
        access_status=access, file="synthetic/reference.pdf", sha256="a" * 64, page_count=2)
    activate_catalog_revision(edition, reader_asset=asset)
    ReadingProgress.objects.create(user=reader_user, asset=asset, current_page=2)
    api_client.force_authenticate(reader_user)
    response = api_client.post("/api/reading/saved/", {"work": str(work.pk)}, format="json")
    assert response.status_code == 201
    assert bool(response.data["reading_progress"]) is visible
    assert api_client.get("/api/reading/progress/").data["count"] == int(visible)
    # Access changes hide the link without deleting the owner's original progress.
    asset.access_status = "private"
    asset.save(update_fields=["access_status"])
    assert api_client.get(f"/api/reading/saved/{response.data['id']}/").data["reading_progress"] is None
    assert ReadingProgress.objects.filter(user=reader_user, asset=asset, current_page=2).exists()


@pytest.mark.django_db
def test_saved_batch_is_bounded_and_owner_filtered(api_client, reader_user, admin_user):
    work, _ = metadata_work()
    own = SavedItem.objects.create(user=reader_user, work=work)
    SavedItem.objects.create(user=admin_user, work=work)
    api_client.force_authenticate(reader_user)
    response = api_client.get(f"/api/reading/saved/?work_ids={work.pk}")
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(own.pk)
    assert api_client.get("/api/reading/saved/?work_ids=not-a-uuid").status_code == 400
    assert api_client.get("/api/reading/saved/?work_ids=" + ",".join([str(work.pk)] * 51)).status_code == 400
