"""Deferred acceptance; never run during the implementation-only phase."""
from uuid import uuid4

import pytest

from catalog.visual_review_views import local_path
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/visual-review/"


def test_visual_review_is_owner_scoped_idempotent_and_disabled_publicly(api_client, admin_user, settings):
    settings.STL_VISUAL_REVIEW_ENABLED, settings.PUBLIC_DEPLOYMENT_MODE = True, False
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    body = {"request_id": str(uuid4()), "review_id": str(uuid4()), "expected_version": "0", "atlas_id": "R01-main",
        "path": "/", "viewport": {"width": 1280, "height": 800, "scroll_x": 0, "scroll_y": 100},
        "strokes": [{"color": "#B44C3D", "points": [{"x": .2, "y": .5}]}], "note": "对齐此处", "status": "open"}
    result = api_client.post(URL, body, format="json", **headers)
    assert result.status_code == 201, result.data
    assert api_client.post(URL, body, format="json", **headers).data == result.data
    assert AuditEvent.objects.filter(action="visual_review.save").count() == 1
    assert api_client.get(URL, **headers).data["results"][0]["note"] == "对齐此处"
    assert api_client.get(URL, HTTP_X_EDITOR_OWNER="another-owner").status_code == 403
    changed = {**body, "request_id": str(uuid4()), "note": "保留输入"}
    assert api_client.post(URL, changed, format="json", **headers).status_code == 409
    stop_id = str(uuid4())
    stop = api_client.post(f"{URL}commands/{stop_id}/", {"action": "cancel_pending"}, format="json", **headers)
    assert stop.status_code == 200
    assert api_client.post(URL, {**body, "request_id": stop_id}, format="json", **headers).data["state"] == "cancelled"
    settings.PUBLIC_DEPLOYMENT_MODE = True
    assert api_client.get(URL, **headers).status_code == 404
    assert api_client.get(f"{URL}references/10/", **headers).status_code == 404


@pytest.mark.parametrize("path", ["https://example.invalid/", "//example.invalid", "/api/reading/", "/reader/[id]", "/reset-password?token=private", "/#access_token=private"])
def test_review_paths_cannot_store_credentials_or_external_targets(path):
    from rest_framework.exceptions import ValidationError
    with pytest.raises(ValidationError):
        local_path(path)
