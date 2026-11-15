from unittest.mock import patch

import httpx
import pytest
from django.test import override_settings

from ingestion.services.indexing import _wait_task


def response(status, payload=None):
    return httpx.Response(
        status, json=payload or {},
        request=httpx.Request("GET", "http://meilisearch:7700/tasks/57135"),
    )


@override_settings(MEILISEARCH_URL="http://meilisearch:7700")
def test_status_http_408_keeps_polling_original_task():
    clock = [0.0]
    with (
        patch("ingestion.services.indexing.time.monotonic", side_effect=lambda: clock[0]),
        patch("ingestion.services.indexing.time.sleep", side_effect=lambda s: clock.__setitem__(0, clock[0] + s)),
        patch("ingestion.services.indexing.httpx.get", side_effect=[
            response(408), response(200, {"status": "processing"}),
            response(200, {"status": "succeeded"}),
        ]) as poll,
        patch("ingestion.services.indexing.httpx.post") as post,
    ):
        assert _wait_task({"taskUid": 57135}, timeout=8)["status"] == "succeeded"
    assert clock[0] == 2
    assert all(c.args[0].endswith("/tasks/57135") for c in poll.call_args_list)
    post.assert_not_called()


@override_settings(MEILISEARCH_URL="http://meilisearch:7700")
def test_repeated_status_http_408_preserves_deadline():
    clock = [0.0]
    with (
        patch("ingestion.services.indexing.time.monotonic", side_effect=lambda: clock[0]),
        patch("ingestion.services.indexing.time.sleep", side_effect=lambda s: clock.__setitem__(0, clock[0] + s)),
        patch("ingestion.services.indexing.httpx.get", return_value=response(408)),
    ):
        with pytest.raises(TimeoutError, match="57135"):
            _wait_task({"taskUid": 57135}, timeout=3)
    assert clock[0] == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
@override_settings(MEILISEARCH_URL="http://meilisearch:7700")
def test_other_status_errors_remain_visible(status):
    with patch("ingestion.services.indexing.httpx.get", return_value=response(status)):
        with pytest.raises(httpx.HTTPStatusError) as error:
            _wait_task({"taskUid": 57135}, timeout=8)
    assert error.value.response.status_code == status
