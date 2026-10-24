"""Deferred acceptance of recorded legacy media. Not run during development."""
from copy import deepcopy
from uuid import uuid4

import pytest

from catalog.models import EditorialRevision, MediaAsset
from tests.test_media_v305 import picture
from tests.test_recommendation_media_v305 import published_with_legacy_image
from tests.test_stl4_object_media_workspace_20261024 import media_context  # noqa: F401

pytestmark = pytest.mark.django_db


def choice(row):
    return {"legacy_source": row["source"], "legacy_record_id": row["record_id"], "legacy_fingerprint": row["fingerprint"]}


def test_work_history_is_scoped_and_preparation_does_not_publish(api_client, admin_user, settings, tmp_path):
    work, edition, original = published_with_legacy_image(admin_user, settings, tmp_path)
    snapshot = deepcopy(edition.active_catalog_revision.snapshot)
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    path = f"/api/catalog/admin/editions/{edition.pk}/media-workspace/"
    history_path = f"/api/catalog/admin/media-legacy/edition/{edition.pk}/"
    before = MediaAsset.objects.count()
    response = api_client.get(history_path, {"slot": "recommendation"})
    assert response.status_code == 200, response.data
    assert MediaAsset.objects.count() == before
    row = next(row for row in response.data["results"] if row["source"] == "publication")
    image = api_client.get(row["url"])
    assert image.status_code == 200 and b"".join(image.streaming_content) == original
    image.close()
    state = api_client.get(path, {"slot": "recommendation"}).data
    body = {"request_id": str(uuid4()), "action": "legacy_history", "slot": "recommendation",
        "expected_version": state["version"], **choice(row)}
    prepared = api_client.post(path, body, format="json")
    assert prepared.status_code == 200, prepared.data
    assert api_client.post(path, body, format="json").data == prepared.data
    assert api_client.get(path, {"slot": "recommendation"}).data["current"] is None
    assert not EditorialRevision.objects.filter(target_type="work", target_id=work.pk, status="draft").exists()
    edition.active_catalog_revision.refresh_from_db()
    assert edition.active_catalog_revision.snapshot == snapshot
    assert api_client.post(path, {**body, "request_id": str(uuid4()), "legacy_record_id": str(uuid4())}, format="json").status_code == 404
    assert api_client.post(path, {**body, "request_id": str(uuid4()), "legacy_fingerprint": "0" * 64}, format="json").status_code == 409


def test_object_history_survives_change_and_prepares_only_a_candidate(media_context, api_client, reader_user):
    kind, target, _, path, _ = media_context
    file = target.person.portrait if kind == "scholar_profile" else target.cover_asset
    file.save("old.png", picture(), save=True)
    before_name = file.name
    history_path = f"/api/catalog/admin/media-legacy/{kind}/{target.pk}/"
    history = api_client.get(history_path).data
    row = next(row for row in history["results"] if row["source"] == "current")
    state = api_client.get(path).data
    body = {"request_id": str(uuid4()), "action": "legacy_history", "slot": state["slot"],
        "expected_version": state["version"], **choice(row)}
    prepared = api_client.post(path, body, format="json")
    assert prepared.status_code == 200, prepared.data
    assert prepared.data["media"]["id"]
    assert api_client.get(path).data["current"] is None
    assert not EditorialRevision.objects.filter(target_type=kind, target_id=target.pk).exists()
    assert file.storage.exists(before_name)
    # A recorded path changed after listing cannot be silently prepared under the old choice.
    file.save("replacement.png", picture(size=(600, 600)), save=True)
    state = api_client.get(path).data
    assert api_client.post(path, {**body, "request_id": str(uuid4()), "expected_version": state["version"]}, format="json").status_code == 409
    api_client.force_authenticate(reader_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.get(history_path).status_code == 403
    assert api_client.get(row["url"]).status_code == 403
