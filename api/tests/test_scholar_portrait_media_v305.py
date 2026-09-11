from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import EditorialRevision, EditorialRevisionMedia, KnowledgePublicationEvent, MediaRendition, Person, ScholarProfile
from catalog.serializers import PersonCompactSerializer
from catalog.services.editorial_revision import EditorialRevisionError, create_editorial_revision, publish_editorial_revision
from catalog.services.media import build_rendition, ingest_image, update_media_metadata
from catalog.services.scholar_media import portrait_media, portrait_selection, save_scholar_editorial_patch, select_scholar_portrait
from .test_media_v305 import picture

pytestmark = pytest.mark.django_db


@pytest.fixture
def portrait_fixture(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    actor = User.objects.create_user(username="portrait-editor", email="portrait-editor@example.test", role="editor")
    person = Person.objects.create(preferred_name="肖像学者", authority_status="verified")
    profile = ScholarProfile.objects.create(person=person, slug="portrait-scholar", editorial_status="published")
    media, _ = ingest_image(picture(), actor=actor, metadata={"alt_text": "原肖像说明", "license": "原许可"})
    return actor, profile, media


def select(profile, media, actor):
    return select_scholar_portrait(profile.pk, media.pk if media else None, actor=actor, expected_person_id=profile.person_id)


def test_portrait_selection_is_private_until_explicit_publication_and_preserves_metadata(portrait_fixture):
    actor, profile, media = portrait_fixture
    public = APIClient()
    revision = select(profile, media, actor)
    profile.person.refresh_from_db()
    assert profile.person.portrait_rendition_id is None
    assert not KnowledgePublicationEvent.objects.exists()
    assert public.get(f"/api/catalog/people/{profile.person_id}/portrait/").status_code == 404
    assert PersonCompactSerializer(profile.person).data["portrait_media"] is None
    assert EditorialRevisionMedia.objects.filter(editorial_revision=revision).count() == 3
    update_media_metadata(media.pk, actor=actor, metadata={"alt_text": "后改说明", "license": "后改许可"})
    publish_editorial_revision(revision.pk, actor=actor)
    profile.person.refresh_from_db()
    saved = portrait_media(profile.person)
    assert saved["alt_text"] == "原肖像说明" and saved["license"] == "原许可"
    response = public.get(f"/api/catalog/people/{profile.person_id}/portrait/")
    assert response.status_code == 200 and response["Content-Type"] == "image/webp"
    assert b"".join(response.streaming_content).startswith(b"RIFF")
    private_variant = build_rendition(media.pk, kind="portrait", width=320)
    assert public.get(f"/api/catalog/people/{profile.person_id}/portrait/?rendition={private_variant.pk}").status_code == 404
    event = KnowledgePublicationEvent.objects.get()
    assert event.changed_fields == ["portrait_selection"]
    assert {item for delivery in event.deliveries.all() for item in delivery.result["required_projections"]} == {"public"}


def test_portrait_replace_clear_and_reselect_preserve_original_and_prior_versions(portrait_fixture):
    actor, profile, media = portrait_fixture
    profile.person.portrait.save("old.png", picture(), save=True)
    legacy_path = profile.person.portrait.name
    storage = profile.person.portrait.storage
    with storage.open(legacy_path, "rb") as handle:
        old_bytes = handle.read()
    first = select(profile, media, actor)
    publish_editorial_revision(first.pk, actor=actor)
    profile.person.refresh_from_db()
    first_id = profile.person.portrait_rendition_id
    update_media_metadata(media.pk, actor=actor, metadata={"focal_x": 0.1})
    second = select(profile, media, actor)
    publish_editorial_revision(second.pk, actor=actor)
    clear = select(profile, None, actor)
    publish_editorial_revision(clear.pk, actor=actor)
    profile.person.refresh_from_db()
    assert profile.person.portrait_rendition_id is None and not profile.person.portrait
    assert MediaRendition.objects.filter(pk=first_id).exists()
    with storage.open(legacy_path, "rb") as handle:
        assert handle.read() == old_bytes
    with pytest.raises(ProtectedError):
        MediaRendition.objects.filter(pk=first_id).delete()
    with pytest.raises(ProtectedError):
        EditorialRevision.objects.filter(pk=first.pk).delete()


def test_metadata_and_portrait_share_one_pending_scholar_draft(portrait_fixture):
    actor, profile, media = portrait_fixture
    saved = save_scholar_editorial_patch(profile.pk, {"short_description": "未发布简介", "person": {"biography": "完整介绍草稿"}}, actor=actor)
    revision = select(profile, media, actor)
    assert revision.patch["short_description"] == "未发布简介"
    assert revision.patch["person"]["biography"] == "完整介绍草稿"
    final = save_scholar_editorial_patch(profile.pk, {"person": {"birth_year": 1930}}, actor=actor)
    assert final.patch["portrait_selection"] == revision.patch["portrait_selection"]
    assert final.patch["person"] == {"biography": "完整介绍草稿", "birth_year": 1930}
    assert final.materialized_preview["person"]["preferred_name"] == "肖像学者"
    assert final.materialized_preview["person"]["biography"] == "完整介绍草稿"
    saved.refresh_from_db()
    assert saved.status == "superseded"
    assert EditorialRevision.objects.filter(target_id=profile.pk, status="draft").count() == 1
    profile.refresh_from_db()
    assert profile.short_description == ""
    publish_editorial_revision(final.pk, actor=actor)
    profile.refresh_from_db()
    profile.person.refresh_from_db()
    assert profile.short_description == "未发布简介" and profile.person.biography == "完整介绍草稿"


def test_portrait_revision_rejects_arbitrary_paths_wrong_kind_and_different_person(portrait_fixture):
    actor, profile, media = portrait_fixture
    wrong = build_rendition(media.pk, kind="cover")
    for change in [{"legacy_path": "private/secret.png"}, {"person_id": str(media.pk)}, {"rendition_id": str(wrong.pk)}, {"rendition_id": "bad"}]:
        selection = {**portrait_selection(profile), **change}
        with pytest.raises(EditorialRevisionError):
            create_editorial_revision(target_type="scholar_profile", target_id=profile.pk, patch={"portrait_selection": selection}, actor=actor, idempotency_key="invalid-portrait")
    with pytest.raises(EditorialRevisionError):
        select_scholar_portrait(profile.pk, media.pk, actor=actor, expected_person_id=media.pk)


def test_portrait_publication_failure_does_not_change_current_selection(portrait_fixture):
    actor, profile, media = portrait_fixture
    revision = select(profile, media, actor)
    with patch("catalog.services.knowledge_publication.create_entity_publication_event", side_effect=ValueError("test failure")):
        with pytest.raises(ValueError):
            publish_editorial_revision(revision.pk, actor=actor)
    revision.refresh_from_db()
    profile.person.refresh_from_db()
    assert revision.status == "draft" and profile.person.portrait_rendition_id is None
    assert not KnowledgePublicationEvent.objects.exists()


def test_portrait_selection_api_and_legacy_upload_protect_permissions_and_public_read(portrait_fixture):
    actor, profile, media = portrait_fixture
    client = APIClient()
    client.force_authenticate(actor)
    url = f"/api/catalog/admin/scholars/{profile.pk}/portrait/"
    fingerprint = client.get(url).data["fingerprint"]
    result = client.post(url, {"media_id": str(media.pk), "expected_person_id": str(profile.person_id), "fingerprint": fingerprint}, format="json")
    assert result.status_code == 200 and result["Cache-Control"] == "private, no-store"
    assert result.data["canonical_write_deferred"]
    assert result.data["preview_url"].startswith("/api/catalog/admin/media/")
    editor = client.get(f"/api/catalog/admin/scholars/{profile.pk}/")
    assert editor.status_code == 200
    assert editor.data["portrait"] == result.data["preview_url"]
    assert editor.data["portrait_media"]["alt_text"] == "原肖像说明"
    uploaded = client.patch(f"/api/catalog/admin/scholars/{profile.pk}/", {"portrait": picture()}, format="multipart")
    assert uploaded.status_code == 202
    profile.person.refresh_from_db()
    assert profile.person.portrait_rendition_id is None
    reader = User.objects.create_user(username="portrait-reader", email="portrait-reader@example.test", role="reader")
    client.force_authenticate(reader)
    assert client.get(url).status_code == 403
    assert client.post(url, {"media_id": None, "expected_person_id": str(profile.person_id)}, format="json").status_code == 403
    client.force_authenticate(None)
    assert client.get(result.data["preview_url"]).status_code == 401


def test_stale_portrait_choice_is_rejected_without_discarding_the_newer_draft(portrait_fixture):
    actor, profile, media = portrait_fixture
    client = APIClient()
    client.force_authenticate(actor)
    url = f"/api/catalog/admin/scholars/{profile.pk}/portrait/"
    fingerprint = client.get(url).data["fingerprint"]
    selected = select(profile, media, actor)
    response = client.post(url, {"media_id": None, "expected_person_id": str(profile.person_id), "fingerprint": fingerprint}, format="json")
    assert response.status_code == 409
    selected.refresh_from_db()
    assert selected.status == "draft"
    assert selected.patch["portrait_selection"]["rendition_id"] is not None


def test_legacy_invalid_upload_and_stale_portrait_preview_remain_visible_errors(portrait_fixture):
    actor, profile, media = portrait_fixture
    client = APIClient()
    client.force_authenticate(actor)
    response = client.patch(f"/api/catalog/admin/scholars/{profile.pk}/", {"portrait": picture(name="bad.jpg", content_type="image/jpeg")}, format="multipart")
    assert response.status_code == 409
    revision = select(profile, media, actor)
    other = Person.objects.create(preferred_name="另一身份", authority_status="verified")
    profile.person = other
    profile.save(update_fields=["person"])
    result = client.get(f"/api/catalog/admin/scholars/{profile.pk}/portrait/")
    assert result.status_code == 409
    assert "已变化" in result.data["detail"]
    revision.refresh_from_db()
    assert revision.status == "draft"


def test_unpublished_scholar_and_unverified_person_cannot_expose_media(portrait_fixture):
    actor, profile, media = portrait_fixture
    revision = select(profile, media, actor)
    publish_editorial_revision(revision.pk, actor=actor)
    client = APIClient()
    profile.editorial_status = "draft"
    profile.save(update_fields=["editorial_status"])
    assert client.get(f"/api/catalog/people/{profile.person_id}/portrait/").status_code == 404
    profile.editorial_status = "published"
    profile.save(update_fields=["editorial_status"])
    profile.person.authority_status = "draft"
    profile.person.save(update_fields=["authority_status", "updated_at"])
    assert client.get(f"/api/catalog/people/{profile.person_id}/portrait/").status_code == 404


def test_rendition_group_cannot_be_changed_after_selection(portrait_fixture):
    actor, profile, media = portrait_fixture
    revision = select(profile, media, actor)
    primary = MediaRendition.objects.get(pk=revision.patch["portrait_selection"]["rendition_id"])
    with pytest.raises(ValidationError):
        MediaRendition.objects.filter(pk=primary.pk).update(group_key="different")
    primary.group_key = "different"
    with pytest.raises(ValidationError):
        primary.save()


def test_portrait_read_fingerprint_describes_the_same_revision_as_its_preview(portrait_fixture):
    from catalog.scholar_media_views import scholar_portrait_state
    from catalog.services.scholar_media import portrait_selection_fingerprint

    actor, profile, media = portrait_fixture
    selected = select(profile, media, actor)
    # A second call to the fingerprint helper must not select a newer draft
    # than the response that the editor actually sees.
    with patch("catalog.scholar_media_views.portrait_selection_fingerprint", wraps=portrait_selection_fingerprint) as fingerprint:
        state = scholar_portrait_state(profile)
    assert fingerprint.call_args.kwargs["draft"].pk == selected.pk
    assert str(state["editorial_revision_id"]) == str(selected.pk)
