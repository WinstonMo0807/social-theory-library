"""Deferred booklist ordering and chapter export acceptance, synthetic only."""
from types import SimpleNamespace

import pytest

from catalog.models import Edition
from reading import booklist_exports, booklists
from reading.booklist_views import ListQuery
from reading.models import ReadingList, ReadingListItem
from tests.test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def add(row, title, author, *, kind="book", order=0):
    edition, revision = published_edition(title)
    Edition.objects.filter(pk=edition.pk).update(is_primary=True)
    revision.snapshot["work"]["document_type"] = kind
    revision.snapshot["edition"] = {"container_title": "合成论文集", "page_range": "12-34", "isbn": "9780000000000"}
    revision.snapshot["contributions"] = [{"role": "author", "name": author, "scope": {}}] if author else []
    revision.save(update_fields=["snapshot"])
    item = ReadingListItem.objects.create(reading_list=row, work=edition.work, order=order)
    return item, edition


def test_alphabetical_sort_uses_public_snapshot_and_preserves_manual_order(reader_user):
    row = ReadingList.objects.create(user=reader_user, title="合成排序书单")
    zed, _ = add(row, "Zebra", "张", order=1)
    alice, _ = add(row, "Alpha", "李", order=2)
    unknown, _ = add(row, "公开但无作者", "", order=3)
    withdrawn, edition = add(row, "不得按草稿排序", "Aardvark", order=4)
    Edition.objects.filter(pk=edition.pk).update(state="draft")
    before = list(row.items.order_by("order").values_list("pk", "order"))
    authors, _ = booklists.alphabetical_items(row.items.all(), "author")
    assert [item.pk for item in authors][:2] == [alice.pk, zed.pk]
    assert {item.pk for item in authors[-2:]} == {unknown.pk, withdrawn.pk}
    titles, _ = booklists.alphabetical_items(row.items.all(), "title")
    assert titles[0].pk == alice.pk and titles[-1].pk == withdrawn.pk
    assert list(row.items.order_by("order").values_list("pk", "order")) == before


def test_chapter_filter_is_the_existing_catalog_identity(api_client, reader_user):
    row = ReadingList.objects.create(user=reader_user, title="合成章节书单")
    chapter, _ = add(row, "合成章节", "合成作者", kind="chapter")
    add(row, "合成图书", "另一作者")
    api_client.force_authenticate(reader_user)
    api_client.credentials(HTTP_X_READER_OWNER=str(reader_user.pk))
    response = api_client.get(f"/api/reading/lists/{row.pk}/workspace/", {"kind": "chapter", "order": "oldest"})
    assert response.status_code == 200 and response.data["count"] == 1
    assert response.data["items"][0]["id"] == str(chapter.pk)
    for kind in ("chapter", "other"):
        assert ListQuery(data={"kind": kind, "order": "author"}).is_valid()


def test_chapter_exports_preserve_container_and_type(reader_user):
    row = ReadingList.objects.create(user=reader_user, title="合成章节导出")
    add(row, "合成章节", "合成作者", kind="chapter")
    data = {"expected_version": booklists.version(row), "include_notes": False, "include_progress": False, "include_covers": False}
    bibtex = booklist_exports.download(SimpleNamespace(user=reader_user), row, {**data, "format": "bibtex"}).content.decode()
    ris = booklist_exports.download(SimpleNamespace(user=reader_user), row, {**data, "format": "ris"}).content.decode()
    assert "@incollection{" in bibtex and "booktitle = {合成论文集}" in bibtex and "pages = {12-34}" in bibtex
    assert "TY  - CHAP" in ris and "T2  - 合成论文集" in ris and "SP  - 12-34" in ris
