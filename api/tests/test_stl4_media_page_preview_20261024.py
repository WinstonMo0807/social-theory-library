"""Deferred saved-page preview acceptance; authored only, not run in development."""
from copy import deepcopy
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from catalog.models import EditorialRevision, MediaRendition
from ingestion.models import AuditEvent
from tests.test_recommendation_media_v305 import published_with_legacy_image

pytestmark = pytest.mark.django_db


def test_saved_work_preview_keeps_publication_and_media_unchanged(api_client, admin_user, settings, tmp_path):
    _, edition, _ = published_with_legacy_image(admin_user, settings, tmp_path)
    published = deepcopy(edition.active_catalog_revision.snapshot)
    before = (EditorialRevision.objects.count(), MediaRendition.objects.count(), AuditEvent.objects.count())
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    path = f"/api/catalog/admin/editions/{edition.pk}/media-workspace/"
    version = api_client.get(path).data["version"]
    response = api_client.get(path, {"include_preview": "true", "expected_version": version})
    assert response.status_code == 200, response.data
    preview = response.data["page_preview"]
    url = urlsplit(preview["url"])
    assert preview["owner_id"] == str(admin_user.pk) and preview["object_id"] == str(edition.pk)
    assert url.path == f"/admin/preview/works/{edition.pk}"
    assert parse_qs(url.query) == {"frame": ["1"], "version": [preview["version"]], "fingerprint": [preview["fingerprint"]]}
    assert len(preview["version"]) == len(preview["fingerprint"]) == 64
    assert api_client.get(path, {"include_preview": "true", "expected_version": "old"}).status_code == 409
    duplicate = urlencode([("include_preview", "true"), ("expected_version", version), ("expected_version", version)])
    assert api_client.get(f"{path}?{duplicate}").status_code == 409
    edition.active_catalog_revision.refresh_from_db()
    assert edition.active_catalog_revision.snapshot == published
    assert (EditorialRevision.objects.count(), MediaRendition.objects.count(), AuditEvent.objects.count()) == before
