"""Timeline sources use existing files, publication snapshots and page identities."""
import pytest
from rest_framework.test import APIClient

from catalog.models import Asset, CatalogPublicationRevision, EditorialRevision, TheoryTimelineEvent, Work
from tests.test_primary_editions_v306 import pair
from tests.test_relation_timeline_editorial_v306 import editor_object

pytestmark = pytest.mark.django_db


@pytest.fixture
def source(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    work, first, second = pair(with_files=True)
    return work, first, second, second.active_catalog_revision.reader_asset


def source_patch(work, edition, asset, page=1):
    return {"evidence_asset": str(asset.pk), "evidence_page": page,
            "evidence_work_id": str(work.pk), "evidence_edition_id": str(edition.pk)}


def save(client, url, patch):
    before = client.get(url)
    return client.patch(url, patch, format="json", HTTP_IF_MATCH=before.data["edit_version"])


def test_source_is_separate_from_event_subject_and_draft_has_exact_file(api_client, admin_user, source):
    work, _, edition, asset = source
    page_ids = list(asset.pages.values_list("id", flat=True))
    event, url = editor_object("timeline_event")
    subject = Work.objects.create(title="事件涉及的另一部作品")
    event.work = subject
    event.save()
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, source_patch(work, edition, asset))
    assert response.status_code == 202, response.data
    details = response.data["evidence_file"]
    assert details["work_id"] == str(work.pk)
    assert details["edition_id"] == str(edition.pk)
    assert details["id"] == str(asset.pk)
    assert details["reader_href"] == f"/reader/{asset.pk}?page=1"
    event.refresh_from_db()
    assert event.evidence_asset_id is None and event.work_id == subject.pk
    result = api_client.post(f"/api{response.data['editorial_revision']['publish_url']}", {}, format="json")
    assert result.status_code == 200, result.data
    event.refresh_from_db()
    assert event.evidence_asset_id == asset.pk and event.work_id == subject.pk
    assert list(asset.pages.values_list("index", flat=True)) == [1]
    assert list(asset.pages.values_list("id", flat=True)) == page_ids


@pytest.mark.parametrize("field", ["evidence_work_id", "evidence_edition_id"])
def test_selected_context_cannot_point_to_another_file(api_client, admin_user, source, field):
    work, first, edition, asset = source
    _, url = editor_object("timeline_event")
    api_client.force_authenticate(admin_user)
    patch = source_patch(work, edition, asset)
    patch[field] = str(first.pk if field == "evidence_edition_id" else Work.objects.create(title="其他出处").pk)
    response = save(api_client, url, patch)
    assert response.status_code == 400, response.data
    assert not EditorialRevision.objects.exists()


@pytest.mark.parametrize("page", [0, -1, 2, None])
def test_file_page_must_be_present_and_in_range(api_client, admin_user, source, page):
    work, _, edition, asset = source
    _, url = editor_object("timeline_event")
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, source_patch(work, edition, asset, page))
    assert response.status_code == 400, response.data
    assert not EditorialRevision.objects.exists()


@pytest.mark.parametrize("field,value", [("kind", "original"), ("validation_status", "pending"), ("validation_status", "invalid"), ("status", "failed")])
def test_unusable_reading_source_rejected_by_dedicated_and_generic_edits(api_client, admin_user, source, field, value):
    work, _, edition, asset = source
    if field == "kind":
        asset = edition.assets.get(kind="original")
    else:
        Asset.objects.filter(pk=asset.pk).update(**{field: value})
    row, url = editor_object("timeline_event")
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, source_patch(work, edition, asset))
    assert response.status_code == 400, response.data
    generic = api_client.post("/api/catalog/admin/editorial-revisions/", {
        "target_type": "timeline_event", "target_id": str(row.pk),
        "patch": {"evidence_asset": str(asset.pk), "evidence_page": 1},
    }, format="json")
    assert generic.status_code == 400, generic.data
    assert not EditorialRevision.objects.exists()


def test_publish_rechecks_file_without_overwriting_stable_event(api_client, admin_user, source):
    work, _, edition, asset = source
    row, url = editor_object("timeline_event")
    api_client.force_authenticate(admin_user)
    saved = save(api_client, url, source_patch(work, edition, asset))
    assert saved.status_code == 202, saved.data
    Asset.objects.filter(pk=asset.pk).update(validation_status="invalid")
    published = api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json")
    assert published.status_code == 400, published.data
    row.refresh_from_db()
    assert row.evidence_asset_id is None
    assert EditorialRevision.objects.get(pk=saved.data["editorial_revision"]["id"]).status == "draft"


@pytest.mark.parametrize("unavailable", ["private", "restricted", "withdrawn", "no_revision", "foreign_revision", "not_ready", "invalid", "replaced"])
def test_public_source_link_uses_current_public_reader_not_any_asset(source, unavailable):
    _, first, edition, asset = source
    row, _ = editor_object("timeline_event")
    row.evidence_asset = asset
    row.evidence_page = 1
    row.save()
    client = APIClient()
    endpoint = "/api/catalog/theory-system/timeline/"
    assert client.get(endpoint).data["results"][0]["reader_href"] == f"/reader/{asset.pk}?page=1"
    if unavailable in {"private", "restricted"}:
        Asset.objects.filter(pk=asset.pk).update(access_status=unavailable)
    elif unavailable == "withdrawn":
        edition.state = "withdrawn"
        edition.save()
    elif unavailable in {"no_revision", "foreign_revision"}:
        edition.active_catalog_revision = None if unavailable == "no_revision" else first.active_catalog_revision
        edition.save()
    elif unavailable == "not_ready":
        edition.active_catalog_revision.metadata_ready = False
        edition.active_catalog_revision.save()
    elif unavailable == "invalid":
        Asset.objects.filter(pk=asset.pk).update(validation_status="invalid")
    else:
        old = edition.active_catalog_revision
        replacement = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
            sha256="e" * 64, page_count=1, version=2, file=asset.file.name)
        old.status = "superseded"
        old.save(update_fields=["status", "updated_at"])
        edition.active_catalog_revision = CatalogPublicationRevision.objects.create(edition=edition, revision=2,
            status="active", metadata_ready=True, snapshot=old.snapshot, reader_asset=replacement)
        edition.save()
    assert client.get(endpoint).data["results"][0]["reader_href"] is None
    row.refresh_from_db()
    assert row.evidence_asset_id == asset.pk, "历史出处必须保留，不能改指新文件"


def test_public_source_link_validation_is_batched(source, django_assert_num_queries):
    from catalog.theory_serializers import NormalizedTimelineEventSerializer
    _, _, _, asset = source
    TheoryTimelineEvent.objects.bulk_create([
        TheoryTimelineEvent(title=f"事件{index}", evidence_asset=asset, evidence_page=1, review_status="approved") for index in range(30)
    ])
    events = list(TheoryTimelineEvent.objects.prefetch_related("normalized_relations"))
    with django_assert_num_queries(1):
        rows = NormalizedTimelineEventSerializer(events, many=True).data
    assert len(rows) == 30
    assert all(row["reader_href"] == f"/reader/{asset.pk}?page=1" for row in rows)


def test_text_only_source_remains_allowed(api_client, admin_user):
    row, url = editor_object("timeline_event")
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, {"source": "馆外纸质文献", "evidence_printed_label": "卷二，第35页", "evidence_asset": None})
    assert response.status_code == 202, response.data
    assert api_client.post(f"/api{response.data['editorial_revision']['publish_url']}", {}, format="json").status_code == 200


def test_exact_source_edition_does_not_fall_back_to_a_different_work(api_client, admin_user, reader_user, source):
    work, _, edition, _ = source
    api_client.force_authenticate(admin_user)
    url = "/api/catalog/admin/library/works/"
    response = api_client.get(url, {"view": "editions", "work_id": work.pk, "edition_id": edition.pk})
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(edition.pk)
    assert response["Cache-Control"] == "private, no-store"
    foreign = Work.objects.create(title="另一部书")
    assert api_client.get(url, {"view": "editions", "work_id": foreign.pk, "edition_id": edition.pk}).data["count"] == 0
    assert api_client.get(url, {"view": "editions", "edition_id": "not-an-id"}).status_code == 400
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, {"view": "editions", "edition_id": edition.pk}).status_code == 403


def test_an_invalid_old_source_does_not_block_withdrawal(api_client, admin_user, source):
    _, _, _, asset = source
    row, url = editor_object("timeline_event")
    row.evidence_asset, row.evidence_page = asset, 1
    row.save()
    Asset.objects.filter(pk=asset.pk).update(validation_status="invalid")
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, {"review_status": "rejected"})
    assert response.status_code == 202, response.data
    assert api_client.post(f"/api{response.data['editorial_revision']['publish_url']}", {}, format="json").status_code == 200


def test_new_event_rejects_out_of_range_source_before_creating_any_record(api_client, admin_user, source):
    work, _, edition, asset = source
    row, _ = editor_object("timeline_event")
    api_client.force_authenticate(admin_user)
    response = api_client.post("/api/catalog/admin/theory-timeline/", {
        "title": "不可创建的页码", "event_type": "publication", "work": str(work.pk), "review_status": "approved",
        **source_patch(work, edition, asset, 2),
    }, format="json")
    assert response.status_code == 400, response.data
    assert TheoryTimelineEvent.objects.count() == 1
    assert not EditorialRevision.objects.exists()


def test_generic_endpoint_rejects_missing_source_instead_of_crashing(api_client, admin_user):
    row, _ = editor_object("timeline_event")
    api_client.force_authenticate(admin_user)
    response = api_client.post("/api/catalog/admin/editorial-revisions/", {
        "target_type": "timeline_event", "target_id": str(row.pk),
        "patch": {"evidence_asset": "30600000-0000-4000-8000-000000000999", "evidence_page": 1},
    }, format="json")
    assert response.status_code == 400, response.data
    assert not EditorialRevision.objects.exists()
