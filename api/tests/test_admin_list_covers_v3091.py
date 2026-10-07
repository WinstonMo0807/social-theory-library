from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile

from catalog.models import Edition, EditorialRevision, Work
from catalog.services.admin_queue import load_admin_editions, saved_cover_url


pytestmark = pytest.mark.django_db


def test_list_and_queue_return_saved_private_cover_without_cover_state(api_client, admin_user, reader_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="列表封面")
    work.cover.save("canonical.jpg", ContentFile(b"canonical cover"))
    edition = Edition.objects.create(work=work, publication_mode="bibliographic")
    draft_name = work.cover.storage.save("draft.jpg", ContentFile(b"saved draft cover"))
    EditorialRevision.objects.create(target_type="work", target_id=work.pk, revision=1,
        idempotency_key=f"cover-{work.pk}", patch={"cover": draft_name}, materialized_preview={"cover": draft_name})
    api_client.force_authenticate(admin_user)
    with patch("catalog.cover_views.cover_state", side_effect=AssertionError("list must not read cover editor state")), \
         patch("catalog.services.covers.generate_cover_candidates", side_effect=AssertionError("list must not prepare covers")):
        library = api_client.get(f"/api/catalog/admin/library/works/?work_id={work.pk}")
        editions = api_client.get(f"/api/catalog/admin/library/works/?view=editions&work_id={work.pk}")
        queue = api_client.get("/api/catalog/admin/workflows/queue/")
        for response in (library, editions, queue):
            assert response.status_code == 200, response.data
            assert response["Cache-Control"] == "private, no-store"
        urls = [response.data["results"][0]["cover_url"] for response in (library, editions, queue)]
        assert len(set(urls)) == 1
        url = urls[0]
        assert url.startswith(f"/api/catalog/admin/works/{work.pk}/recommendation-image/?slot=cover&v=")
        image = api_client.get(url)
        assert image.status_code == 200
        assert b"".join(image.streaming_content) == b"saved draft cover"
        assert image["Cache-Control"] == "private, no-store"
        image.close()
    work.refresh_from_db()
    assert work.cover.read() == b"canonical cover"
    work.cover.close()
    assert not work.cover_candidates.exists()
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    api_client.force_authenticate(None)
    assert api_client.get(url).status_code in (401, 403)


def test_batched_cover_fields_add_no_queries_and_removed_cover_stays_empty(django_assert_num_queries, api_client, admin_user):
    missing = Work.objects.create(title="无封面")
    removed = Work.objects.create(title="已移除封面", cover="old.jpg")
    present = Work.objects.create(title="已有封面", cover="saved.jpg")
    orphan = Work.objects.create(title="尚无版本的封面草稿", cover="old.jpg")
    for work in (removed, orphan):
        EditorialRevision.objects.create(target_type="work", target_id=work.pk, revision=1,
            idempotency_key=f"cover-{work.pk}", patch={"cover": ""}, materialized_preview={"cover": ""})
    for work in (missing, removed, present):
        Edition.objects.create(work=work, publication_mode="bibliographic")
    editions = load_admin_editions(Edition.objects.all())
    with django_assert_num_queries(0):
        urls = {row.work_id: saved_cover_url(row.work) for row in editions}
    assert urls[missing.pk] == urls[removed.pk] == ""
    assert urls[present.pk].startswith(f"/api/catalog/admin/works/{present.pk}/")
    api_client.force_authenticate(admin_user)
    library = api_client.get("/api/catalog/admin/library/works/")
    assert library.status_code == 200
    covers = {row["id"]: row["cover_url"] for row in library.data["results"]}
    assert covers[str(missing.pk)] == covers[str(removed.pk)] == covers[str(orphan.pk)] == ""
    assert covers[str(present.pk)] == urls[present.pk]
    # A missing saved file remains an explicit failure, not a generated/default image.
    assert api_client.get(urls[present.pk]).status_code == 404
