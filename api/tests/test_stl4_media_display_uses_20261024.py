"""Deferred acceptance for M08 display selection; not run during development."""
from copy import deepcopy
from uuid import uuid4

import pytest

from catalog.models import MediaRendition
from catalog.services.media import DEFAULT_MEDIA_DISPLAY_USES, ingest_image, work_media_snapshot
from tests.test_media_v305 import picture
from tests.test_recommendation_media_v305 import published_with_legacy_image

pytestmark = pytest.mark.django_db


def test_uses_are_immutable_per_selection_and_restore_without_publishing(api_client, admin_user, settings, tmp_path):
    work, edition, _ = published_with_legacy_image(admin_user, settings, tmp_path)
    published = deepcopy(edition.active_catalog_revision.snapshot)
    media, _ = ingest_image(picture(), actor=admin_user, metadata={"alt_text": "原件说明"})
    original = media.file.read(); media.file.close()
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    path = f"/api/catalog/admin/editions/{edition.pk}/media-workspace/"

    def save(slot, uses):
        state = api_client.get(path, {"slot": slot}).data
        body = {"request_id": str(uuid4()), "expected_version": state["version"], "action": "save", "slot": slot,
                "media_id": str(media.pk), "display_uses": uses,
                "transform": {"x": 0, "y": 0, "width": 1, "height": 1, "rotation": 0},
                "metadata": {"alt_text": "本次说明", "source_label": "合成图", "source_url": "", "rights": "", "license": "", "credit": ""}}
        response = api_client.post(path, body, format="json")
        assert response.status_code == 200, response.data
        assert api_client.post(path, body, format="json").data == response.data
        return api_client.get(path, {"slot": slot}).data["current"]

    first = save("cover", ["detail", "mobile"])
    other = save("recommendation", ["list", "share"])
    inactive = save("cover", [])
    assert first["id"] != inactive["id"] and inactive["display_uses"] == []
    assert api_client.get(path, {"slot": "recommendation"}).data["current"]["id"] == other["id"]
    current = api_client.get(path).data
    restored = api_client.post(path, {"request_id": str(uuid4()), "expected_version": current["version"], "action": "restore",
                                     "slot": "cover", "rendition_id": first["id"]}, format="json")
    assert restored.status_code == 200, restored.data
    assert api_client.get(path).data["current"]["display_uses"] == ["detail", "mobile"]
    primary = MediaRendition.objects.get(pk=first["id"])
    assert work_media_snapshot(work, primary=primary)["display_uses"] == ["detail", "mobile"]
    primary.refresh_from_db(); assert primary.metadata_snapshot["display_uses"] == ["detail", "mobile"]
    media.refresh_from_db(); assert media.alt_text == "原件说明"
    assert media.file.read() == original; media.file.close()
    edition.active_catalog_revision.refresh_from_db()
    assert edition.active_catalog_revision.snapshot == published


@pytest.mark.parametrize("uses", [["unknown"], ["detail", "detail"], "mobile", None])
def test_invalid_display_uses_do_not_form_a_save_command(uses):
    from catalog.media_workspace_views import MediaWorkspaceCommandSerializer
    body = {"request_id": str(uuid4()), "expected_version": "version", "slot": "cover", "action": "save", "media_id": str(uuid4()),
            "transform": {"x": 0, "y": 0, "width": 1, "height": 1, "rotation": 0}, "display_uses": uses,
            "metadata": {"alt_text": "", "source_label": "", "source_url": "", "rights": "", "license": "", "credit": ""}}
    assert not MediaWorkspaceCommandSerializer(data=body).is_valid()


def test_older_selection_keeps_display_defaults_without_opt_in_to_sharing(settings, tmp_path, admin_user):
    from catalog.services.media import build_rendition, media_rendition_snapshot
    settings.MEDIA_ROOT = tmp_path
    media, _ = ingest_image(picture(), actor=admin_user)
    primary = build_rendition(media.pk)
    assert media_rendition_snapshot(primary, lambda row: f"/public/{row.pk}")["display_uses"] == list(DEFAULT_MEDIA_DISPLAY_USES)
    assert "display_uses" not in primary.metadata_snapshot
