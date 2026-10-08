from io import BytesIO
from urllib.parse import urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from catalog.models import Topic


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("status,perspective", [("draft", "draft"), ("published", "published")])
def test_topic_image_preview_has_no_synthetic_host_and_preserves_public_access(
    api_client, admin_user, reader_user, settings, tmp_path, status, perspective
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.MEDIA_URL = "/media/"
    settings.ALLOWED_HOSTS = ["library.test"]
    settings.DEBUG = False
    image = BytesIO()
    Image.new("RGB", (32, 18), "#ddd5c7").save(image, format="PNG")
    topic = Topic.objects.create(
        name="图片预览检查", slug=f"image-preview-{status}", editorial_status=status,
        hero_image=SimpleUploadedFile("topic-preview.png", image.getvalue(), content_type="image/png"),
        core_questions=["已保存的问题？"],
    )
    before = (topic.hero_image.name, topic.editorial_status, topic.core_questions)
    api_client.force_authenticate(user=admin_user)
    preview = api_client.get(
        f"/api/catalog/admin/knowledge-preview/topic/{topic.pk}/",
        {"perspective": perspective}, HTTP_HOST="library.test",
    )
    assert preview.status_code == 200, preview.data
    public_image_url = reverse("public-topic-image", kwargs={"topic_id": topic.pk})
    private_image_url = reverse("admin-topic-image", kwargs={"topic_id": topic.pk})
    assert urlsplit(preview.data["perspective"]["data"]["hero_image"]).path == (public_image_url if status == "published" else private_image_url)
    private_image = api_client.get(private_image_url, HTTP_HOST="library.test")
    assert private_image.status_code == 200
    assert private_image["Content-Type"] == "image/png"
    assert private_image["Cache-Control"] == "private, no-store"
    assert b"".join(private_image.streaming_content) == image.getvalue()
    # APIClient closes streaming responses on exhaustion while preserving its
    # test transaction; closing again emits a second request_finished signal.
    assert private_image.closed
    workspace = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"object_type": "topic", "selected_type": "topic", "selected_id": str(topic.pk)},
        HTTP_HOST="library.test",
    )
    assert workspace.status_code == 200, workspace.data
    topic.refresh_from_db()
    assert (topic.hero_image.name, topic.editorial_status, topic.core_questions) == before
    api_client.force_authenticate(user=reader_user)
    assert api_client.get(f"/api/catalog/admin/knowledge-preview/topic/{topic.pk}/", HTTP_HOST="library.test").status_code in {401, 403}
    assert api_client.get(private_image_url, HTTP_HOST="library.test").status_code in {401, 403}
    api_client.force_authenticate(user=None)
    public = api_client.get(f"/api/catalog/topics/{topic.slug}/", HTTP_HOST="library.test")
    assert public.status_code == (200 if status == "published" else 404)
    if status == "published":
        assert urlsplit(public.data["hero_image"]).path == public_image_url
    public_image = api_client.get(public_image_url, HTTP_HOST="library.test")
    assert public_image.status_code == (200 if status == "published" else 404)
    if status == "published":
        assert b"".join(public_image.streaming_content) == image.getvalue()
        assert public_image.closed
    api_client.force_authenticate(user=admin_user)
    detail = api_client.get(f"/api/catalog/admin/topics/{topic.pk}/", HTTP_HOST="library.test")
    before_url = detail.data["hero_image"]
    updated = BytesIO()
    Image.new("RGB", (32, 18), "#746b60").save(updated, format="PNG")
    replaced = api_client.patch(
        f"/api/catalog/admin/topics/{topic.pk}/",
        {"hero_image": SimpleUploadedFile("topic-preview.png", updated.getvalue(), content_type="image/png")},
        format="multipart", HTTP_HOST="library.test", HTTP_IF_MATCH=detail.data["edit_version"],
    )
    assert replaced.status_code == (200 if status == "draft" else 409), replaced.data
    topic.refresh_from_db()
    assert topic.hero_image.storage.exists(before[0])
    if status == "draft":
        assert replaced.data["hero_image"] != before_url
        assert topic.core_questions == before[2]
        changed_image = api_client.get(replaced.data["hero_image"], HTTP_HOST="library.test")
        assert changed_image.status_code == 200
        assert b"".join(changed_image.streaming_content) == updated.getvalue()
        assert changed_image.closed
    else:
        assert (topic.hero_image.name, topic.editorial_status, topic.core_questions) == before
