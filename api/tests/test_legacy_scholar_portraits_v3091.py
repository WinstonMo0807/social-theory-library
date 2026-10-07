from hashlib import sha256

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import EditorialRevision
from catalog.serializers import PersonCompactSerializer
from catalog.services.editorial_revision import publish_editorial_revision
from catalog.services.scholar_media import select_scholar_portrait
from .test_media_v305 import picture
from .test_scholar_portrait_media_v305 import portrait_fixture


pytestmark = pytest.mark.django_db


@pytest.fixture
def legacy_portrait(portrait_fixture, settings):
    settings.DEBUG = False
    actor, profile, media = portrait_fixture
    profile.person.portrait.save("legacy.png", picture(), save=True)
    path = profile.person.portrait.name
    with profile.person.portrait.storage.open(path, "rb") as handle:
        original = handle.read()
    return actor, profile, media, path, original


def image_bytes(response):
    # APIClient closes the stream on exhaustion; closing it twice sends another
    # request_finished signal that can close a PostgreSQL test transaction.
    return b"".join(response.streaming_content)


def test_legacy_portrait_private_url_uses_staff_permission_and_preserves_original(legacy_portrait):
    actor, profile, _media, path, original = legacy_portrait
    admin = APIClient()
    admin.force_authenticate(actor)
    state_url = f"/api/catalog/admin/scholars/{profile.pk}/portrait/"
    image_url = f"{state_url}?image=1"
    before = profile.person.updated_at
    state = admin.get(state_url)
    assert state.status_code == 200 and state.data["preview_url"] == image_url
    detail = admin.get(f"/api/catalog/admin/scholars/{profile.pk}/")
    assert detail.status_code == 200 and detail.data["portrait"] == image_url
    result = admin.get(image_url)
    assert result.status_code == 200
    assert result["Cache-Control"] == "private, no-store"
    assert result["Content-Type"] == "image/png"
    assert result["X-Content-Type-Options"] == "nosniff"
    assert image_bytes(result) == original
    reader = User.objects.create_user(username="legacy-reader", role="reader")
    admin.force_authenticate(reader)
    assert admin.get(image_url).status_code == 403
    admin.force_authenticate(None)
    assert admin.get(image_url).status_code == 401
    profile.person.refresh_from_db()
    assert profile.person.portrait.name == path and profile.person.updated_at == before
    assert not EditorialRevision.objects.filter(target_id=profile.pk).exists()
    with profile.person.portrait.storage.open(path, "rb") as handle:
        assert sha256(handle.read()).digest() == sha256(original).digest()


def test_legacy_public_url_reads_only_canonical_portrait_while_draft_selects_new_media(legacy_portrait):
    actor, profile, media, _path, original = legacy_portrait
    public = APIClient()
    url = f"/api/catalog/people/{profile.person_id}/portrait/"
    assert PersonCompactSerializer(profile.person).data["portrait"] == url
    assert image_bytes(public.get(url)) == original
    draft = select_scholar_portrait(profile.pk, media.pk, actor=actor, expected_person_id=profile.person_id)
    # Draft rendition and arbitrary URL parameters cannot replace the canonical old image.
    assert public.get(f"{url}?rendition={draft.patch['portrait_selection']['rendition_id']}").status_code == 404
    assert image_bytes(public.get(f"{url}?legacy_path=private/secret.png")) == original
    admin = APIClient()
    admin.force_authenticate(actor)
    assert admin.get(f"/api/catalog/admin/scholars/{profile.pk}/portrait/?image=1").status_code == 404
    assert image_bytes(public.get(url)) == original


@pytest.mark.parametrize("field,value", [("editorial_status", "draft"), ("authority_status", "draft")])
def test_legacy_public_portrait_requires_published_scholar_and_verified_person(legacy_portrait, field, value):
    _actor, profile, _media, _path, _original = legacy_portrait
    target = profile if field == "editorial_status" else profile.person
    setattr(target, field, value)
    target.save(update_fields=[field])
    profile.person.refresh_from_db()
    public = APIClient()
    assert public.get(f"/api/catalog/people/{profile.person_id}/portrait/").status_code == 404
    assert PersonCompactSerializer(profile.person).data["portrait"] == ""


def test_clear_draft_hides_private_legacy_then_publication_removes_public_access_without_deleting_file(legacy_portrait):
    actor, profile, _media, path, original = legacy_portrait
    draft = select_scholar_portrait(profile.pk, None, actor=actor, expected_person_id=profile.person_id)
    admin = APIClient()
    admin.force_authenticate(actor)
    private_url = f"/api/catalog/admin/scholars/{profile.pk}/portrait/"
    public_url = f"/api/catalog/people/{profile.person_id}/portrait/"
    assert admin.get(private_url).data["preview_url"] == ""
    assert admin.get(f"{private_url}?image=1").status_code == 404
    assert admin.get(f"/api/catalog/admin/scholars/{profile.pk}/").data["portrait"] in (None, "")
    assert image_bytes(APIClient().get(public_url)) == original
    publish_editorial_revision(draft.pk, actor=actor)
    assert APIClient().get(public_url).status_code == 404
    with profile.person.portrait.storage.open(path, "rb") as handle:
        assert handle.read() == original


def test_legacy_missing_file_is_explicit_404_and_url_cannot_choose_another_file(legacy_portrait):
    actor, profile, _media, path, original = legacy_portrait
    admin = APIClient()
    admin.force_authenticate(actor)
    private_url = f"/api/catalog/admin/scholars/{profile.pk}/portrait/?image=1"
    assert image_bytes(admin.get(f"{private_url}&path=private/secret.png")) == original
    profile.person.portrait = "public/people/missing.png"
    profile.person.save(update_fields=["portrait"])
    assert admin.get(private_url).status_code == 404
    assert APIClient().get(f"/api/catalog/people/{profile.person_id}/portrait/").status_code == 404
    with profile.person.portrait.storage.open(path, "rb") as handle:
        assert handle.read() == original


def test_tampered_legacy_draft_never_falls_back_to_an_unvalidated_file(legacy_portrait):
    actor, profile, _media, _path, original = legacy_portrait
    draft = select_scholar_portrait(profile.pk, None, actor=actor, expected_person_id=profile.person_id)
    admin = APIClient()
    admin.force_authenticate(actor)
    url = f"/api/catalog/admin/scholars/{profile.pk}/portrait/?image=1"
    for selection in [{}, {**draft.patch["portrait_selection"], "legacy_path": "private/secret.png"}]:
        EditorialRevision.objects.filter(pk=draft.pk).update(materialized_preview={**draft.materialized_preview, "portrait_selection": selection})
        assert admin.get(url).status_code == 409
    assert image_bytes(APIClient().get(f"/api/catalog/people/{profile.person_id}/portrait/")) == original
