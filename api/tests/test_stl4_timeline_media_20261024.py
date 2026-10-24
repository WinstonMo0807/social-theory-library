"""Deferred M23 evidence-image acceptance; not run during implementation."""
from uuid import uuid4

import pytest
from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import ValidationError

from catalog.models import EditorialRevisionMedia, Person, ScholarProfile, TheoryTimelineEvent
from catalog.serializers import AdminTheoryTimelineEventSerializer
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.editorial_revision import publish_editorial_revision
from catalog.services.media import build_rendition, ingest_image, media_reference_inventory, update_media_metadata
from catalog.services.timeline_media import primary_image_media
from catalog.timeline_editor import validate_timeline_details
from .test_media_v305 import picture

pytestmark = pytest.mark.django_db


@pytest.fixture
def evidence(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    settings.THEORY_SYSTEM_ENABLED = True
    media, _ = ingest_image(picture(size=(900, 1200)), actor=admin_user, metadata={"alt_text": "原核对图", "license": "已记录许可"})
    first = build_rendition(media.pk, width=640, kind="hero")
    update_media_metadata(media.pk, actor=admin_user, metadata={"alt_text": "下一图版本"})
    second = build_rendition(media.pk, width=640, kind="hero")
    person = Person.objects.create(preferred_name="合成事件人物")
    profile = ScholarProfile.objects.create(person=person, slug=f"image-{uuid4()}")
    event = TheoryTimelineEvent.objects.create(title="合成出生事件", scholar=profile, event_type="birth", start_year=1900, date_precision="year", source="合成主要出处", description="人工核对说明")
    return event, media, first, second


def details(primary, supplemental=None):
    return {"confirmed": True, "primary_image_rendition_id": str(primary.pk) if primary else None,
            "sources": [{"id": str(uuid4()), "citation": "合成辅助出处", "image_rendition_id": str(supplemental.pk)}] if supplemental else []}


def test_image_validation_and_canonical_unpublished_reference(evidence):
    event, _media, first, second = evidence
    for invalid in ("https://example.test/private.png", str(uuid4()), ""):
        with pytest.raises(ValidationError):
            validate_timeline_details({"primary_image_rendition_id": invalid})
    editor = AdminTheoryTimelineEventSerializer(event, data={"editorial_details": details(first, second)}, partial=True)
    assert editor.is_valid(), editor.errors
    editor.save()
    assert event.evidence_images.count() == 2
    with pytest.raises(ProtectedError), transaction.atomic():
        first.delete()
    assert first.file.storage.exists(first.file.name)


def test_staged_replacement_private_supplement_and_retained_history(evidence, admin_user, api_client):
    event, media, first, second = evidence
    editor = AdminTheoryTimelineEventSerializer(event, data={"editorial_details": details(first, second)}, partial=True)
    assert editor.is_valid(), editor.errors
    editor.save()
    event.review_status = "approved"
    event.save(update_fields=["review_status"])
    url = f"/api/catalog/theory-system/timeline/{event.pk}/image/"
    response = api_client.get(url)
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    response.close()
    assert api_client.get(url, {"rendition": second.pk}).status_code == 404
    draft = save_object_editorial_patch("timeline_event", event.pk, {"editorial_details": details(second)}, actor=admin_user)
    event.refresh_from_db()
    assert primary_image_media(event)["primary_rendition_id"] == str(first.pk)
    assert set(EditorialRevisionMedia.objects.filter(editorial_revision=draft).values_list("rendition_id", flat=True)) >= {first.pk, second.pk}
    publish_editorial_revision(draft.pk, actor=admin_user)
    event.refresh_from_db()
    assert primary_image_media(event)["primary_rendition_id"] == str(second.pk)
    assert event.evidence_images.count() == 1
    assert api_client.get(url, {"rendition": first.pk}).status_code == 404
    assert any("timeline" in row["editor_url"] for row in media_reference_inventory(media.pk, actor=admin_user)["results"])
    assert first.file.storage.exists(first.file.name)
    event.review_status = "rejected"
    event.save(update_fields=["review_status"])
    assert api_client.get(url).status_code == 404
