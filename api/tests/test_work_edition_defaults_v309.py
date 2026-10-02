import pytest

from catalog.models import PublicationState
from .test_primary_editions_v306 import pair


pytestmark = pytest.mark.django_db


def test_reader_and_download_defaults_are_separate_public_entry_points(api_client, admin_user):
    work, primary, secondary = pair(with_files=True)
    api_client.force_authenticate(admin_user)

    prepared = api_client.get(f"/api/catalog/admin/works/{work.pk}/edition-defaults/")
    assert prepared.status_code == 200
    assert {row["id"] for row in prepared.data["options"]} == {str(primary.pk), str(secondary.pk)}
    assert prepared.data["effective_reader_edition_id"] == str(primary.pk)

    saved = api_client.put(
        f"/api/catalog/admin/works/{work.pk}/edition-defaults/",
        {
            "reader_default_edition_id": str(secondary.pk),
            "download_default_edition_id": str(primary.pk),
            "confirmed": True,
            "request_id": "v309-defaults-test",
        },
        format="json",
    )
    assert saved.status_code == 200, saved.data
    work.refresh_from_db()
    assert work.reader_default_edition_id == secondary.pk
    assert work.download_default_edition_id == primary.pk

    public = api_client.get(f"/api/catalog/works/{primary.public_slug}/")
    assert public.status_code == 200, public.data
    assert public.data["edition"]["id"] == str(primary.pk)
    assert public.data["reader_edition"]["id"] == str(secondary.pk)
    assert public.data["download_edition"]["id"] == str(primary.pk)


def test_default_selection_requires_confirmation_and_a_valid_public_reader_file(api_client, admin_user):
    work, primary, secondary = pair(with_files=True)
    api_client.force_authenticate(admin_user)
    endpoint = f"/api/catalog/admin/works/{work.pk}/edition-defaults/"

    unconfirmed = api_client.put(endpoint, {"reader_default_edition_id": str(secondary.pk)}, format="json")
    assert unconfirmed.status_code == 400

    secondary.state = PublicationState.DRAFT
    secondary.save(update_fields=["state", "updated_at"])
    invalid = api_client.put(
        endpoint,
        {"reader_default_edition_id": str(secondary.pk), "confirmed": True},
        format="json",
    )
    assert invalid.status_code == 409
    work.refresh_from_db()
    assert work.reader_default_edition_id is None
