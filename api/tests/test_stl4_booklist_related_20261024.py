"""Deferred owner/source/pagination acceptance; no real library fixtures."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound

from catalog.models import Asset, Edition, Page, Person, ScholarProfile, Topic
from reading import booklist_related, booklists, notebook, research
from reading.models import Annotation, PersonalReadingPlan, ReadingList, ReadingListItem
from tests.test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def source(user):
    edition, revision = published_edition("合成书单关联来源")
    Edition.objects.filter(pk=edition.pk).update(is_primary=True)
    row = ReadingList.objects.create(user=user, title="合成关联书单")
    item = ReadingListItem.objects.create(reading_list=row, work=edition.work)
    return row, item, edition, revision


def query(row, section, page=1):
    return {"expected_version": booklists.version(row), "section": section, "page": page}


def test_plans_only_follow_the_owners_original_booklist_and_paginate(reader_user, admin_user):
    row, *_ = source(reader_user)
    payload = {"goal": "合成计划", "items": [], "origin": {"type": "booklist_copy", "booklist_id": str(row.pk)}}
    for _ in range(21):
        PersonalReadingPlan.objects.create(user=reader_user, data_ciphertext=research.pack(payload))
    PersonalReadingPlan.objects.create(user=admin_user, data_ciphertext=research.pack(payload))
    PersonalReadingPlan.objects.create(user=reader_user, data_ciphertext=research.pack({**payload, "origin": {"type": "booklist_copy", "booklist_id": str(uuid4())}}))
    first = booklist_related.related(SimpleNamespace(user=reader_user), row.pk, query(row, "plans"))
    last = booklist_related.related(SimpleNamespace(user=reader_user), row.pk, query(row, "plans", 2))
    assert first["count"] == 21 and len(first["plans"]) == 20 and len(last["plans"]) == 1
    assert not {value["id"] for value in first["plans"]} & {value["id"] for value in last["plans"]}


def test_notes_filter_original_owner_records_and_removed_items(reader_user, admin_user):
    row, item, edition, _ = source(reader_user)
    asset = Asset.objects.create(edition=edition, kind="normalized", sha256="a" * 64, file="synthetic/unused.pdf")
    page = Page.objects.create(asset=asset, index=1)
    mine = Annotation.objects.create(user=reader_user, asset=asset, page=page, kind="note", orphaned=True, asset_sha256=asset.sha256)
    Annotation.objects.create(user=admin_user, asset=asset, page=page, kind="note", orphaned=True, asset_sha256=asset.sha256)
    options = {"booklist": row.pk, "page": 1, "q": "", "kind": "all", "order": "newest"}
    assert [entry["id"] for entry in notebook.listing(reader_user, options)["results"]] == [str(mine.pk)]
    item.removed_at = timezone.now()
    item.save(update_fields=["removed_at"])
    assert notebook.listing(reader_user, options)["count"] == 0
    assert Annotation.objects.filter(pk=mine.pk).exists()
    with pytest.raises(NotFound):
        notebook.listing(admin_user, options)


def test_public_links_use_snapshot_membership_and_current_visibility(reader_user):
    row, _, _, revision = source(reader_user)
    topic = Topic.objects.create(name="合成正式主题", slug="synthetic-related-topic", editorial_status="published")
    unrelated = Topic.objects.create(name="没有正式关联", slug="synthetic-unrelated-topic", editorial_status="published")
    person = Person.objects.create(preferred_name="合成署名", authority_status="verified")
    profile = ScholarProfile.objects.create(person=person, slug="synthetic-related-scholar", editorial_status="published")
    revision.snapshot.update(knowledge={"topics": [{"id": str(topic.pk)}]}, contributions=[{"person_id": str(person.pk), "role": "author"}])
    revision.save(update_fields=["snapshot"])
    result = booklist_related.related(SimpleNamespace(user=reader_user), row.pk, query(row, "topics"))
    assert [value["id"] for value in result["topics"]] == [str(topic.pk)]
    assert all(value["id"] != str(unrelated.pk) for value in result["topics"])
    assert booklist_related.related(SimpleNamespace(user=reader_user), row.pk, query(row, "scholars"))["scholars"][0]["id"] == str(profile.pk)
    topic.editorial_status = "draft"
    topic.save(update_fields=["editorial_status"])
    person.authority_status = "archived"
    person.save(update_fields=["authority_status"])
    assert booklist_related.related(SimpleNamespace(user=reader_user), row.pk, query(row, "topics"))["count"] == 0
    assert booklist_related.related(SimpleNamespace(user=reader_user), row.pk, query(row, "scholars"))["count"] == 0


def test_related_endpoint_checks_owner_version_and_never_creates_records(api_client, reader_user, admin_user):
    row, *_ = source(reader_user)
    path = f"/api/reading/lists/{row.pk}/related/"
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_READER_OWNER=str(admin_user.pk))
    assert api_client.get(path, query(row, "notes")).status_code == 404
    api_client.force_authenticate(reader_user)
    api_client.credentials(HTTP_X_READER_OWNER=str(admin_user.pk))
    assert api_client.get(path, query(row, "notes")).status_code == 403
    api_client.credentials(HTTP_X_READER_OWNER=str(reader_user.pk))
    assert api_client.get(path, {**query(row, "notes"), "expected_version": "outdated"}).status_code == 409
    response = api_client.get(path, query(row, "notes"))
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    assert response.data["count"] == 0 and PersonalReadingPlan.objects.count() == 0
