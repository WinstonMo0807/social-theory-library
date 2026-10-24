"""Deferred acceptance for original media metadata; not run during development."""
from copy import deepcopy
from uuid import uuid4

import pytest
from catalog.services.media import build_rendition, ingest_image
from ingestion.models import AuditEvent
from tests.test_media_v305 import picture

pytestmark = pytest.mark.django_db


@pytest.fixture
def media_library(settings, tmp_path, api_client, admin_user):
    settings.MEDIA_ROOT = tmp_path
    media, _ = ingest_image(picture(), actor=admin_user, metadata={"alt_text": "合成原图", "source_label": "合成来源"})
    rendition = build_rendition(media.pk, width=320, kind="thumbnail")
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    path = f"/api/catalog/admin/media/{media.pk}/workspace/"
    state = api_client.get(path)
    assert state.status_code == 200, state.data
    fields = ("alt_text", "source_label", "source_url", "rights", "license", "credit", "focal_x", "focal_y")
    command = {"request_id": str(uuid4()), "expected_updated_at": state.data["media"]["updated_at"],
        "metadata": {key: state.data["media"][key] for key in fields}}
    command["metadata"]["alt_text"] = "合成图片修正说明"
    return media, rendition, path, command


def test_saved_receipt_replays_without_changing_original_or_existing_rendition(media_library, api_client):
    media, rendition, path, command = media_library
    original = media.file.read(); media.file.close()
    snapshot = deepcopy(rendition.metadata_snapshot)
    saved = api_client.post(path, command, format="json")
    assert saved.status_code == 200, saved.data
    assert api_client.post(path, command, format="json").data == saved.data
    assert api_client.get(f"{path}commands/{command['request_id']}/").data == saved.data
    state = api_client.get(path).data
    assert state["media"]["updated_at"] == saved.data["updated_at"]
    assert state["history"]["count"] == 1
    assert state["history"]["results"][0]["before"]["alt_text"] == "合成原图"
    assert AuditEvent.objects.filter(action="media.library.command", request_id=command["request_id"]).count() == 1
    media.refresh_from_db(); rendition.refresh_from_db()
    assert media.alt_text == "合成图片修正说明" and media.renditions.count() == 1
    assert rendition.metadata_snapshot == snapshot
    assert media.file.read() == original; media.file.close()


def test_stop_stale_version_and_changed_request_are_distinct(media_library, api_client):
    media, _, path, command = media_library
    cancelled = api_client.post(f"{path}commands/{command['request_id']}/", {"action": "cancel_pending"}, format="json")
    assert cancelled.status_code == 200 and cancelled.data["state"] == "cancelled"
    assert api_client.post(path, command, format="json").data["state"] == "cancelled"
    media.refresh_from_db(); assert media.alt_text == "合成原图"
    next_command = {**command, "request_id": str(uuid4())}
    assert api_client.post(path, next_command, format="json").status_code == 200
    assert api_client.post(path, {**command, "request_id": str(uuid4())}, format="json").status_code == 409
    changed = {**next_command, "metadata": {**command["metadata"], "alt_text": "另一操作"}}
    assert api_client.post(path, changed, format="json").status_code == 409


def test_owner_reader_and_unknown_fields_cannot_change_source(media_library, api_client, reader_user):
    media, _, path, command = media_library
    wrong = {**command, "metadata": {**command["metadata"], "file": "replace.png"}}
    assert api_client.post(path, wrong, format="json").status_code == 400
    api_client.credentials(HTTP_X_EDITOR_OWNER="not-this-account")
    assert api_client.get(path).status_code == 403
    api_client.force_authenticate(reader_user); api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.post(path, command, format="json").status_code == 403
    assert api_client.get(f"{path}commands/{command['request_id']}/").status_code == 403
    media.refresh_from_db(); assert media.alt_text == "合成原图"


def test_collection_search_uses_saved_source_metadata(media_library, api_client):
    media, _, _, _ = media_library
    result = api_client.get("/api/catalog/admin/media/collection/", {"q": "合成来源"})
    assert result.status_code == 200 and [row["id"] for row in result.data["results"]] == [str(media.pk)]
    assert api_client.get("/api/catalog/admin/media/collection/", {"q": "x" * 201}).status_code == 400
