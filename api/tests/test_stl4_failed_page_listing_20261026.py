"""Deferred acceptance only: pagination must preserve the exact failed-task boundary."""
from copy import deepcopy

import pytest

from ingestion.services.processing_commands import task_version
from .test_stl4_selected_retry_20261024 import interrupted

pytestmark = pytest.mark.django_db


def test_all_failed_pages_are_reachable_without_writing_task_or_completed_text(api_client, admin_user, settings, tmp_path):
    job, saved = interrupted(settings, tmp_path)
    job.stats.update(total_pages=407, requested_page_indexes=list(range(1, 408)),
                     active_page_indexes=list(range(1, 408)), completed_page_indexes=[1, 3])
    job.save(update_fields=["stats"])
    before = deepcopy(job.stats)
    api_client.force_authenticate(admin_user)
    url = f"/api/ingestion/processing-workspace/failed-pages/{job.pk}/"
    found = []
    for page, expected_count in ((1, 200), (2, 200), (3, 5)):
        response = api_client.get(url, {"expected_version": task_version(job), "page": page}, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
        assert response.status_code == 200
        assert response.data["owner_id"] == str(admin_user.pk)
        assert response.data["count"] == 405 and response.data["pages"] == 3
        assert len(response.data["results"]) == expected_count
        found.extend(response.data["results"])
        assert response["Cache-Control"] == "private, no-store"
    assert found == [index for index in range(1, 408) if index not in {1, 3}]
    assert api_client.get(url, {"expected_version": task_version(job), "page": 4}).status_code == 400
    job.refresh_from_db(); saved.refresh_from_db()
    assert job.stats == before and job.status == "failed"
    assert saved.text == "已保存的第一页"


def test_read_requires_queue_permission_owner_and_original_delivery(api_client, admin_user, reader_user, settings, tmp_path):
    job, _ = interrupted(settings, tmp_path)
    url = f"/api/ingestion/processing-workspace/failed-pages/{job.pk}/"
    params = {"expected_version": task_version(job), "page": 1}
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, params).status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.get(url, params, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    job.status = "running"
    job.save(update_fields=["status"])
    assert api_client.get(url, params, HTTP_X_EDITOR_OWNER=str(admin_user.pk)).status_code == 409
