"""New recycle thumbnails read retained files behind the exact active entry."""
from hashlib import sha256
from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.models import Contribution, Edition, KnowledgeNode, Person, ScholarProfile, Work
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.editorial_revision import create_editorial_revision
from catalog.services.media import build_rendition, ingest_image
from catalog.services.recycle import recycle_object, restore_object
from catalog.services.scholar_media import save_scholar_editorial_patch

pytestmark = pytest.mark.django_db


def image_bytes(color):
    buffer = BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, "PNG")
    return buffer.getvalue()


def entry_row(client, entry):
    response = client.get("/api/catalog/admin/recycle/")
    assert response.status_code == 200
    return next(row for row in response.data["results"] if row["id"] == str(entry.pk))


def test_retained_legacy_cover_and_real_bibliography_are_private(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="封面保留核对")
    raw = image_bytes((77, 88, 99))
    work.cover.save("retained.png", ContentFile(raw))
    edition = Edition.objects.create(work=work, publisher="真实保存出版社", publication_year=1999)
    person = Person.objects.create(preferred_name="实际关联作者")
    Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
    entry = recycle_object(work, actor=admin_user, kind="work", name=work.title)
    api_client.force_authenticate(admin_user)
    row = entry_row(api_client, entry)
    assert row["subtitle"] == "实际关联作者 · 1999年版 · 真实保存出版社"
    assert row["thumbnail_url"] == f"/api/catalog/admin/recycle/{entry.pk}/image/"
    preview = api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/preview/")
    assert preview.status_code == 200 and preview.data["preview"]["work"]["cover"] == row["thumbnail_url"]
    image = api_client.get(row["thumbnail_url"])
    assert image.status_code == 200 and image["Content-Type"] == "image/png"
    assert "private" in image["Cache-Control"] and "no-store" in image["Cache-Control"]
    assert sha256(b"".join(image.streaming_content)).hexdigest() == sha256(raw).hexdigest()
    api_client.force_authenticate(None)
    assert api_client.get(row["thumbnail_url"]).status_code in {401, 403}


def test_missing_cover_is_honest_and_never_a_fabricated_image(api_client, admin_user):
    work = Work.objects.create(title="没有保存封面")
    entry = recycle_object(work, actor=admin_user, kind="work", name=work.title)
    api_client.force_authenticate(admin_user)
    row = entry_row(api_client, entry)
    assert row["thumbnail_url"] == "" and row["subtitle"] == ""
    assert api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/image/").status_code == 404


def test_restored_entry_cannot_keep_serving_a_recycle_image(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="恢复后的图像访问边界")
    work.cover.save("retained.png", ContentFile(image_bytes((12, 23, 34))))
    entry = recycle_object(work, actor=admin_user, kind="work", name=work.title)
    api_client.force_authenticate(admin_user)
    image = api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/image/")
    assert image.status_code == 200
    image.close()
    restore_object(entry.pk, actor=admin_user)
    assert api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/image/").status_code == 404


def test_scholar_thumbnail_uses_exact_saved_portrait_selection(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    renditions = []
    for color in [(23, 34, 45), (56, 67, 78)]:
        media, _ = ingest_image(SimpleUploadedFile("portrait.png", image_bytes(color), content_type="image/png"), actor=admin_user)
        renditions.append(build_rendition(media.pk, width=320, kind="portrait"))
    person = Person.objects.create(preferred_name="自有保留学者", original_name="Saved Scholar", portrait_rendition=renditions[0])
    scholar = ScholarProfile.objects.create(person=person)
    save_scholar_editorial_patch(scholar.pk, {"portrait_selection": {"person_id": str(person.pk), "rendition_id": str(renditions[1].pk), "legacy_path": ""}}, actor=admin_user)
    entry = recycle_object(scholar, actor=admin_user, kind="scholar", name=person.preferred_name)
    api_client.force_authenticate(admin_user)
    row = entry_row(api_client, entry)
    assert row["subtitle"] == "Saved Scholar"
    image = api_client.get(row["thumbnail_url"])
    assert image.status_code == 200
    assert sha256(b"".join(image.streaming_content)).hexdigest() == renditions[1].checksum
    person.refresh_from_db()
    assert person.portrait_rendition_id == renditions[0].pk


def test_unreadable_retained_file_is_reported_as_missing(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="保留图片文件缺失", cover="public/covers/missing.png")
    entry = recycle_object(work, actor=admin_user, kind="work", name=work.title)
    api_client.force_authenticate(admin_user)
    row = entry_row(api_client, entry)
    assert row["thumbnail_url"]
    assert api_client.get(row["thumbnail_url"]).status_code == 404


def test_saved_scholar_image_removal_never_reactivates_the_retained_legacy_photo(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    person = Person.objects.create(preferred_name="明确移除肖像的草稿")
    person.portrait.save("legacy-portrait.png", ContentFile(image_bytes((34, 45, 56))))
    scholar = ScholarProfile.objects.create(person=person)
    save_scholar_editorial_patch(scholar.pk, {"portrait_selection": {"person_id": str(person.pk), "rendition_id": None, "legacy_path": ""}}, actor=admin_user)
    entry = recycle_object(scholar, actor=admin_user, kind="scholar", name=person.preferred_name)
    api_client.force_authenticate(admin_user)
    assert entry_row(api_client, entry)["thumbnail_url"] == ""
    assert api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/image/").status_code == 404
    person.refresh_from_db()
    assert person.portrait and person.portrait.storage.exists(person.portrait.name)


def test_saved_knowledge_image_removal_and_real_english_name_are_preserved(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    node = KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="自有保留概念", canonical_name_en="Saved Concept", slug="saved-concept")
    node.cover_asset.save("legacy-concept.png", ContentFile(image_bytes((45, 56, 67))))
    save_object_editorial_patch("knowledge_node", node.pk, {"image_selection": {"object_type": "knowledge_node", "object_id": str(node.pk), "rendition_id": None, "legacy_path": ""}}, actor=admin_user)
    entry = recycle_object(node, actor=admin_user, kind="knowledge-node", name=node.canonical_name_zh)
    api_client.force_authenticate(admin_user)
    row = entry_row(api_client, entry)
    assert row["thumbnail_url"] == "" and row["subtitle"] == "Saved Concept"
    assert api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/image/").status_code == 404
    node.refresh_from_db()
    assert node.cover_asset and node.cover_asset.storage.exists(node.cover_asset.name)


@pytest.mark.parametrize("remove", [True, False])
def test_work_thumbnail_respects_saved_cover_selection_without_changing_original(api_client, admin_user, settings, tmp_path, remove):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="保存封面选择的回收作品")
    original = image_bytes((21, 32, 43))
    work.cover.save("original-cover.png", ContentFile(original))
    Edition.objects.create(work=work)
    rendition = None
    if not remove:
        media, _ = ingest_image(SimpleUploadedFile("new-cover.png", image_bytes((54, 65, 76)), content_type="image/png"), actor=admin_user)
        rendition = build_rendition(media.pk, width=320, kind="cover")
    create_editorial_revision(target_type="work", target_id=work.pk,
                             patch={"cover_rendition": str(rendition.pk) if rendition else None, "cover": rendition.file.name if rendition else ""},
                             actor=admin_user, idempotency_key=f"recycle-cover-{remove}")
    entry = recycle_object(work, actor=admin_user, kind="work", name=work.title)
    api_client.force_authenticate(admin_user)
    row = entry_row(api_client, entry)
    if remove:
        assert row["thumbnail_url"] == ""
        assert api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/image/").status_code == 404
    else:
        image = api_client.get(row["thumbnail_url"])
        assert image.status_code == 200
        assert sha256(b"".join(image.streaming_content)).hexdigest() == rendition.checksum
    work.refresh_from_db()
    assert work.cover and work.cover.storage.exists(work.cover.name)
    assert work.cover_rendition_id is None


def test_saved_legacy_cover_uses_exact_entry_in_the_retained_preview(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="保存旧上传封面的回收作品")
    work.cover.save("original-cover.png", ContentFile(image_bytes((21, 32, 43))))
    original_name = work.cover.name
    Edition.objects.create(work=work)
    selected_bytes = image_bytes((98, 87, 76))
    selected_name = work.cover.storage.save(f"public/covers/editorial/{work.pk}/saved.png", ContentFile(selected_bytes))
    create_editorial_revision(target_type="work", target_id=work.pk,
                             patch={"cover": selected_name, "cover_rendition": None},
                             actor=admin_user, idempotency_key="recycle-saved-legacy-cover")
    entry = recycle_object(work, actor=admin_user, kind="work", name=work.title)
    api_client.force_authenticate(admin_user)
    row = entry_row(api_client, entry)
    preview = api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/preview/")
    assert preview.status_code == 200 and preview.data["preview"]["work"]["cover"] == row["thumbnail_url"]
    image = api_client.get(row["thumbnail_url"])
    assert image.status_code == 200 and b"".join(image.streaming_content) == selected_bytes
    work.refresh_from_db()
    assert work.cover.name == original_name and work.cover.storage.exists(original_name)
