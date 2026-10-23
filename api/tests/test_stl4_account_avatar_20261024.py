"""Deferred avatar ownership, sanitization and receipt acceptance coverage."""
import base64
from io import BytesIO
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, PngImagePlugin
from rest_framework.test import APIClient

from accounts import avatars
from accounts.models import AccountAvatar
from ingestion.models import AuditEvent

URL = "/api/auth/me/avatar/"


def photo():
    output = BytesIO()
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "synthetic-private-camera-comment")
    Image.new("RGB", (512, 384), "#b6a28d").save(output, format="PNG", pnginfo=info)
    return output.getvalue()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    client.credentials(HTTP_X_READER_OWNER=str(user.pk))
    return client


@pytest.mark.django_db
def test_avatar_is_private_sanitized_and_old_upload_does_not_reappear(reader_user, admin_user):
    client = client_for(reader_user)
    before = client.get(URL).data
    source = photo()
    payload = {"action": "set", "confirmed": True, "request_id": str(uuid4()), "expected_version": before["expected_version"]}
    def upload():
        return client.post(URL, {**payload, "image": SimpleUploadedFile("portrait.png", source, content_type="image/png")}, format="multipart")
    saved = upload()
    assert saved.status_code == 200 and saved.data["has_avatar"]
    row = AccountAvatar.objects.get(user=reader_user)
    assert source not in bytes(row.image_ciphertext)
    response = client.get(f"/api/auth/users/{reader_user.pk}/avatar/")
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    with Image.open(BytesIO(response.content)) as image:
        assert image.size == (256, 256) and not image.info
    assert base64.b64decode(avatars.export(reader_user)["image_base64"]) == response.content
    outsider = client_for(admin_user)
    assert outsider.get(f"/api/auth/users/{reader_user.pk}/avatar/").status_code == 200
    assert client.get(f"/api/auth/users/{admin_user.pk}/avatar/").status_code == 403
    remove = client.post(URL, {"action": "remove", "confirmed": True, "request_id": str(uuid4()),
        "expected_version": saved.data["expected_version"]}, format="json")
    assert remove.status_code == 200 and not remove.data["has_avatar"]
    old = upload()
    assert old.status_code == 200 and not old.data["has_avatar"]
    row.refresh_from_db()
    assert not row.image_ciphertext and row.revision == remove.data["revision"]
    assert avatars.export(reader_user) is None
    assert len(AuditEvent.objects.filter(action="profile_avatar_set")) == 1


@pytest.mark.django_db
def test_stopped_avatar_request_cannot_arrive_late_and_input_cannot_change_owner(reader_user):
    client = client_for(reader_user)
    snapshot = client.get(URL).data
    identifier = str(uuid4())
    stopped = client.post(f"{URL}commands/{identifier}/", {"action": "cancel_pending"}, format="json")
    assert stopped.status_code == 200 and stopped.data["state"] == "cancelled"
    payload = {"action": "set", "confirmed": True, "request_id": identifier, "expected_version": snapshot["expected_version"],
        "image": SimpleUploadedFile("portrait.png", photo(), content_type="image/png")}
    late = client.post(URL, payload, format="multipart")
    assert late.status_code == 200 and late.data["state"] == "cancelled"
    assert not AccountAvatar.objects.filter(user=reader_user).exists()
    refused = client.post(URL, {"action": "remove", "confirmed": True, "request_id": str(uuid4()),
        "expected_version": snapshot["expected_version"], "user_id": reader_user.pk + 1}, format="json")
    assert refused.status_code == 400
    malformed = client.post(URL, {**payload, "request_id": str(uuid4()), "image": SimpleUploadedFile("image.svg", b"<svg/>", content_type="image/svg+xml")}, format="multipart")
    assert malformed.status_code == 400
