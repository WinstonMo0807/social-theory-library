from unittest.mock import patch
import uuid

import pytest

from accounts.models import User
from catalog.models import Asset, Edition, Page, SiteSetting
from ingestion.models import ProcessingJob
from ingestion.services.processing import run_ocr_job
from ingestion.services.extract import ExtractedPage
from .test_resilient_publication_v260 import create_item_with_files


pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-center/"


@pytest.fixture
def source(settings, tmp_path):
    work, edition, original, asset = create_item_with_files(settings, tmp_path)
    asset.page_count = 3
    asset.validation_details = {"ocr_required_page_indexes": []}
    asset.save()
    for index in range(1, 4):
        Page.objects.create(asset=asset, index=index, text="旧文字", normalized_text="旧文字", text_source=Page.TextSource.OCR)
    return work, edition, original, asset


def start(api_client, source, **extra):
    _, edition, _, asset = source
    return api_client.post(URL, {
        "action": "start_ocr", "edition_id": str(edition.pk), "asset_id": str(asset.pk),
        "source_version": asset.updated_at.isoformat(), "request_id": str(uuid.uuid4()),
        "confirmed": True, **extra,
    }, format="json")


def test_catalog_ocr_read_is_scoped_lightweight_and_read_only(api_client, admin_user, source):
    api_client.force_authenticate(admin_user)
    with patch("ingestion.views.paused_ocr_inventory", side_effect=AssertionError("No global inventory on polling")):
        response = api_client.get(URL, {"ocr_edition_id": str(source[1].pk)})
    assert response.status_code == 200
    assert response.data["edition_id"] == str(source[1].pk)
    assert response.data["files"][0]["id"] == str(source[3].pk)
    assert response.data["can_run"] is True
    assert not ProcessingJob.objects.exists()


@pytest.mark.parametrize("published", [False, True])
def test_catalog_ocr_start_without_upload_and_timeout_replay(api_client, admin_user, source, published):
    api_client.force_authenticate(admin_user)
    if published:
        from .v304_helpers import activate_catalog_revision
        source[1].state = "published"
        source[1].save(update_fields=["state", "updated_at"])
        activate_catalog_revision(source[1], reader_asset=source[3])
    request_id = str(uuid.uuid4())
    with patch("ingestion.services.processing.dispatch_ocr_job"):
        first = start(api_client, source, request_id=request_id)
        assert first.status_code == 202, first.data
        job = ProcessingJob.objects.get(pk=first.data["job"]["id"])
        assert job.upload_item_id is None
        assert job.stats["requested_mode"] == "all_pages"
        job.status = ProcessingJob.Status.SUCCEEDED
        job.save()
        retry = start(api_client, source, request_id=request_id)
    assert retry.status_code == 200
    assert retry.data["replayed"] is True
    assert retry.data["job"]["id"] == str(job.pk)
    assert ProcessingJob.objects.count() == 1


@pytest.mark.parametrize("reason", ["confirmation", "version", "foreign", "invalid", "pending", "historical"])
def test_catalog_ocr_rejects_unsafe_source(api_client, admin_user, source, reason):
    api_client.force_authenticate(admin_user)
    changes = {}
    if reason == "confirmation":
        changes["confirmed"] = False
    elif reason == "version":
        changes["source_version"] = "old"
    elif reason == "foreign":
        changes["edition_id"] = str(Edition.objects.create(work=source[0]).pk)
    else:
        if reason == "historical":
            source[3].is_current = False
        else:
            source[3].validation_status = reason
        source[3].save()
    response = start(api_client, source, **changes)
    assert response.status_code in {400, 409}, response.data
    assert not ProcessingJob.objects.exists()


def test_catalog_ocr_editor_can_read_but_not_start(api_client, admin_user, source):
    admin_user.role = User.Role.EDITOR
    admin_user.save()
    api_client.force_authenticate(admin_user)
    response = api_client.get(URL, {"ocr_edition_id": str(source[1].pk)})
    assert response.status_code == 200
    assert response.data["can_run"] is False
    assert start(api_client, source).status_code == 403


def test_catalog_ocr_respects_global_pause(api_client, admin_user, source):
    SiteSetting.objects.create(key="ocr_processing_paused", value=True)
    api_client.force_authenticate(admin_user)
    response = start(api_client, source)
    assert response.status_code == 202, response.data
    assert response.data["job"]["status"] == "paused"
    assert SiteSetting.objects.get(key="ocr_processing_paused").value is True


def test_catalog_ocr_full_rerun_counts_only_newly_persisted_pages(api_client, admin_user, source):
    api_client.force_authenticate(admin_user)
    response = start(api_client, source)
    assert response.status_code == 202, response.data
    job = ProcessingJob.objects.get(pk=response.data["job"]["id"])
    old_ids = list(source[3].pages.order_by("index").values_list("pk", flat=True))
    def extract(_path, indexes):
        assert indexes == [1]
        progress = api_client.get(URL, {"ocr_edition_id": str(source[1].pk)}).data["jobs"][0]
        assert progress["completed_pages"] == 0
        assert progress["active_pages"] == [1]
        return [ExtractedPage(index=1, text="新文字", width=595, height=842, source="ocr", confidence=.98, printed_label="", chapter_title="", blocks=[])], "controlled_ocr"
    with patch("ingestion.services.processing.materialize_field_file", return_value=("fixture.pdf", None)), patch("ingestion.services.processing.extract_ocr_page_batch", side_effect=extract), patch("ingestion.services.processing.dispatch_ocr_job"):
        run_ocr_job(str(job.pk), task_id=job.task_id)
    progress = api_client.get(URL, {"ocr_edition_id": str(source[1].pk)}).data["jobs"][0]
    assert progress["completed_pages"] == 1
    assert progress["total_pages"] == 3
    assert progress["percent"] == 33.3
    assert list(source[3].pages.order_by("index").values_list("pk", flat=True)) == old_ids
