from unittest.mock import patch

import pytest
from django.db.models.deletion import ProtectedError
from rest_framework.test import APIClient

from accounts.models import User
from catalog.knowledge_media_views import image_state
from catalog.models import EditorialRevision, EditorialRevisionMedia, KnowledgeNode, KnowledgePublicationEvent, MediaRendition, ReadingPath, ReadingPathStage
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.editorial_revision import EditorialRevisionError, create_editorial_revision, publish_editorial_revision
from catalog.services.knowledge_media import image_media, image_selection, image_target_type, select_knowledge_image
from catalog.services.media import build_rendition, ingest_image, update_media_metadata
from .test_media_v305 import picture

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["knowledge_node", "reading_path"])
def fixture(request, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.THEORY_SYSTEM_ENABLED = True
    actor = User.objects.create_user(username="knowledge-media-editor", email="knowledge-media-editor@example.test", role="editor")
    if request.param == "knowledge_node":
        target = KnowledgeNode.objects.create(canonical_name_zh="理论图片", slug="knowledge-media-node", node_type="theory_tradition", status="published")
    else:
        target = ReadingPath.objects.create(title="路径图片", slug="knowledge-media-path", status="published")
        ReadingPathStage.objects.create(reading_path=target, name="已有阅读阶段", position=0)
    media, _ = ingest_image(picture(size=(1200, 800)), actor=actor, metadata={"alt_text": "已核对图片", "license": "原许可"})
    return actor, target, media


def select(actor, target, media):
    object_type = image_target_type(target)
    return select_knowledge_image(object_type, target.pk, media.pk if media else None, actor=actor, fingerprint=image_state(target, object_type)["fingerprint"])


def test_knowledge_image_stays_private_until_publication_and_clear_keeps_files(fixture):
    actor, target, media = fixture
    object_type = image_target_type(target)
    target.cover_asset.save("old.png", picture(), save=True)
    legacy_file = target.cover_asset.name
    storage = target.cover_asset.storage
    with storage.open(legacy_file, "rb") as handle:
        original = handle.read()
    revision = select(actor, target, media)
    target.refresh_from_db()
    assert target.cover_rendition_id is None
    assert target.cover_asset.name == legacy_file
    assert not KnowledgePublicationEvent.objects.exists()
    url = f"/api/catalog/knowledge-media/{object_type}/{target.pk}/file/"
    client = APIClient()
    assert client.get(url).status_code == 404
    update_media_metadata(media.pk, actor=actor, metadata={"alt_text": "后改内容"})
    publish_editorial_revision(revision.pk, actor=actor)
    target.refresh_from_db()
    assert image_media(target)["alt_text"] == "已核对图片"
    response = client.get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"RIFF")
    old_id = target.cover_rendition_id
    newer = build_rendition(media.pk, kind="hero", width=640)
    assert client.get(url, {"rendition": str(newer.pk)}).status_code == 404
    event = KnowledgePublicationEvent.objects.get()
    assert event.changed_fields == ["image_selection"]
    assert {item for delivery in event.deliveries.all() for item in delivery.result["required_projections"]} == {"public"}
    clear = select(actor, target, None)
    assert client.get(url).status_code == 200
    publish_editorial_revision(clear.pk, actor=actor)
    target.refresh_from_db()
    assert target.cover_rendition_id is None and not target.cover_asset
    assert client.get(url).status_code == 404
    with storage.open(legacy_file, "rb") as handle:
        assert handle.read() == original
    assert EditorialRevisionMedia.objects.filter(editorial_revision=revision, rendition_id=old_id).exists()
    with pytest.raises(ProtectedError):
        MediaRendition.objects.filter(pk=old_id).delete()


def test_image_and_text_are_combined_without_replacing_original_relations(fixture):
    actor, target, media = fixture
    object_type = image_target_type(target)
    field = "summary" if object_type == "knowledge_node" else "introduction"
    first = save_object_editorial_patch(object_type, target.pk, {field: "先保存的草稿"}, actor=actor)
    image_revision = select(actor, target, media)
    assert image_revision.patch[field] == "先保存的草稿"
    last = save_object_editorial_patch(object_type, target.pk, {field: "最后确认的说明"}, actor=actor)
    assert last.patch["image_selection"] == image_revision.patch["image_selection"]
    first.refresh_from_db()
    assert first.status == "superseded"
    if object_type == "reading_path":
        stage_id = target.stages.get().pk
    publish_editorial_revision(last.pk, actor=actor)
    target.refresh_from_db()
    assert getattr(target, field) == "最后确认的说明"
    if object_type == "reading_path":
        stage = target.stages.get()
        assert stage.pk == stage_id and stage.name == "已有阅读阶段"


def test_media_http_selection_rejects_old_fingerprint_and_reader_and_feature_off(fixture, settings):
    actor, target, media = fixture
    object_type = image_target_type(target)
    url = f"/api/catalog/admin/knowledge-media/{object_type}/{target.pk}/"
    client = APIClient()
    client.force_authenticate(actor)
    before = client.get(url)
    assert before.status_code == 200 and before["Cache-Control"] == "private, no-store"
    response = client.post(url, {"media_id": str(media.pk), "fingerprint": before.data["fingerprint"]}, format="json")
    assert response.status_code == 200 and response.data["canonical_write_deferred"]
    assert response.data["preview_url"].startswith("/api/catalog/admin/media/")
    assert client.post(url, {"media_id": None, "fingerprint": before.data["fingerprint"]}, format="json").status_code == 409
    revision = EditorialRevision.objects.get(pk=response.data["editorial_revision_id"])
    assert revision.patch["image_selection"]["rendition_id"]
    reader = User.objects.create_user(username="knowledge-media-reader", email="knowledge-media-reader@example.test", role="reader")
    client.force_authenticate(reader)
    assert client.get(url).status_code == 403
    assert client.post(url, {"media_id": None, "fingerprint": before.data["fingerprint"]}, format="json").status_code == 403
    settings.THEORY_SYSTEM_ENABLED = False
    client.force_authenticate(actor)
    assert client.get(url).status_code == 404


def test_wrong_identity_path_or_image_kind_is_rejected(fixture):
    actor, target, media = fixture
    object_type = image_target_type(target)
    wrong = build_rendition(media.pk, kind="portrait")
    for change in [{"object_id": str(media.pk)}, {"object_type": "scholar_profile"}, {"legacy_path": "private/not-authorized.png"}, {"rendition_id": str(wrong.pk)}, {"rendition_id": "bad"}]:
        with pytest.raises(EditorialRevisionError):
            create_editorial_revision(target_type=object_type, target_id=target.pk, patch={"image_selection": {**image_selection(target), **change}}, actor=actor, idempotency_key="bad-knowledge-image")


def test_image_publication_failure_preserves_the_current_picture(fixture):
    actor, target, media = fixture
    revision = select(actor, target, media)
    with patch("catalog.services.knowledge_publication.create_entity_publication_event", side_effect=ValueError("controlled failure")):
        with pytest.raises(ValueError):
            publish_editorial_revision(revision.pk, actor=actor)
    target.refresh_from_db()
    revision.refresh_from_db()
    assert target.cover_rendition_id is None and revision.status == "draft"


def test_legacy_image_patch_and_admin_preview_share_the_new_draft(fixture):
    actor, target, media = fixture
    object_type = image_target_type(target)
    endpoint = "nodes" if object_type == "knowledge_node" else "reading-paths"
    url = f"/api/catalog/admin/theory-system/{endpoint}/{target.pk}/"
    client = APIClient()
    client.force_authenticate(actor)
    response = client.patch(url, {"cover_asset": picture()}, format="multipart")
    assert response.status_code == 202
    assert response.data["cover_url"].startswith("/api/catalog/admin/media/")
    assert response.data["cover_media"]["renditions"]
    field = "summary" if object_type == "knowledge_node" else "introduction"
    updated = client.patch(url, {field: "随后保存说明"}, format="json")
    assert updated.status_code == 202 and updated.data["cover_url"] == response.data["cover_url"]
    assert updated.data[field] == "随后保存说明"
    target.refresh_from_db()
    assert target.cover_rendition_id is None
