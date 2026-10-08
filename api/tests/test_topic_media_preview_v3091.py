from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
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
    assert preview.data["perspective"]["data"]["hero_image"] == topic.hero_image.url
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
    api_client.force_authenticate(user=None)
    public = api_client.get(f"/api/catalog/topics/{topic.slug}/", HTTP_HOST="library.test")
    assert public.status_code == (200 if status == "published" else 404)
    if status == "published":
        assert public.data["hero_image"] == f"http://library.test{topic.hero_image.url}"
