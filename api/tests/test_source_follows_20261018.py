"""Synthetic PDF 17 source-status/follow cases, authored for unified acceptance only."""
from uuid import uuid4
import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Asset, CatalogPublicationRevision, DocumentRevision
from reading import privacy, research, source_follow as sources
from reading.source_models import SourceFollow, SourceFollowEvent
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def fixture():
    edition, asset, spans, _ = fixture_source(1)
    asset.file = "synthetic/source.pdf"
    asset.save(update_fields=["file"])
    edition.public_slug = f"synthetic-{edition.pk}"
    edition.save(update_fields=["public_slug"])
    return edition, asset, spans[0]


def follow(user, path, action="subscribe", revision=0, request_id=None):
    return sources.command(user, {"path": path, "action": action, "expected_revision": revision, "request_id": request_id or uuid4()})


@pytest.mark.parametrize("path", ["https://evil.invalid/reader/a", "//evil.invalid/a", "/account/notes", "/admin/library", "/reader/%2e%2e/account", "/reader/not-an-id"])
def test_unsafe_or_nonpublic_source_has_no_metadata_or_subscription(path, reader_user):
    source = sources.resolve_public_source(path)
    assert source["status"] == "unavailable" and not source["can_subscribe"]
    assert source["authors"] == [] and not source["cover_url"]
    with pytest.raises(ValidationError):
        follow(reader_user, path)


def test_source_metadata_comes_from_active_snapshot_and_known_physical_page():
    edition, asset, span = fixture()
    revision = edition.active_catalog_revision
    revision.snapshot = {"work": {"title": "合成已公开题名"}, "edition": {"version_label": "合成正式版本"},
                         "contributions": [{"role": "author", "person": {"preferred_name": "合成公开作者"}}]}
    revision.save(update_fields=["snapshot"])
    span.page.printed_label = "ix"
    span.page.save(update_fields=["printed_label"])
    source = sources.resolve_public_source(f"/reader/{asset.pk}?page=1&token=DO_NOT_RETAIN")
    assert source["title"] == "合成已公开题名" and source["authors"] == ["合成公开作者"]
    assert source["status"] == "available" and source["location"] == "PDF 第 1 页 · 印刷页 ix"
    assert "token" not in source["path"]
    assert sources.resolve_public_source(f"/reader/{asset.pk}?page=99")["location"] == "所选 PDF 页码当前无法核对"


@pytest.mark.parametrize("mutation", ["withdrawn", "private", "original", "unpublished_asset", "invalid", "wrong_edition"])
def test_invalid_source_never_claims_current_readability(mutation):
    edition, asset, _ = fixture()
    path = f"/reader/{asset.pk}"
    if mutation == "withdrawn":
        edition.state = "withdrawn"
        edition.save(update_fields=["state"])
    elif mutation == "unpublished_asset":
        asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid", file="synthetic/draft.pdf", access_status="public", sha256="d" * 64)
        path = f"/reader/{asset.pk}"
    elif mutation == "wrong_edition":
        other, other_asset, _ = fixture()
        revision = edition.active_catalog_revision
        revision.reader_asset = other_asset
        revision.save(update_fields=["reader_asset"])
    else:
        field, value = {"private": ("access_status", "private"), "original": ("kind", "original"), "invalid": ("validation_status", "invalid")}[mutation]
        setattr(asset, field, value)
        asset.save(update_fields=[field])
    result = sources.resolve_public_source(path)
    assert result["status"] == "unavailable" and result["reader_url"] == ""
    if mutation in {"withdrawn", "private", "original", "unpublished_asset"}:
        assert result["title"] == "来源当前不可用" and result["work_id"] is None


def test_replacement_repoints_only_current_reader_and_does_not_invent_page_mapping():
    edition, old, _ = fixture()
    old_revision = edition.active_catalog_revision
    old_revision.status = "superseded"
    old_revision.save(update_fields=["status"])
    new = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid", file="synthetic/new.pdf", access_status="public", sha256="c" * 64)
    document = DocumentRevision.objects.create(asset=new, revision=1, source_checksum=new.sha256, text_checksum="e" * 64)
    revision = CatalogPublicationRevision.objects.create(edition=edition, revision=2, status="active", metadata_ready=True,
        fulltext_ready=True, reader_asset=new, document_revision=document, snapshot=old_revision.snapshot, content_fingerprint=uuid4().hex)
    edition.active_catalog_revision = revision
    edition.save(update_fields=["active_catalog_revision"])
    source = sources.resolve_public_source(f"/reader/{old.pk}?page=1")
    assert source["status"] == "replaced" and source["reader_url"] == f"/reader/{new.pk}" and source["location"] == ""
    new.access_status = "private"
    new.save(update_fields=["access_status"])
    unavailable = sources.resolve_public_source(f"/reader/{old.pk}")
    assert unavailable["status"] == "unavailable" and unavailable["asset_id"] is None


def test_subscribe_canonical_idempotency_cas_and_owner_isolation(api_client, reader_user, admin_user):
    _, asset, _ = fixture()
    path, request_id = f"/reader/{asset.pk}", uuid4()
    first = follow(reader_user, path.upper().replace("/READER/", "/reader/") + "?page=1", request_id=request_id)
    assert first["path"] == path
    assert follow(reader_user, path, request_id=request_id)["id"] == first["id"]
    assert SourceFollow.objects.count() == 1 and SourceFollowEvent.objects.count() == 1
    with pytest.raises(research.ResearchConflict):
        follow(reader_user, path, "unsubscribe", first["revision"], request_id)
    with pytest.raises(research.ResearchConflict):
        follow(reader_user, path, "unsubscribe", 0)
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/source-follows/{first['id']}/").status_code == 404
    assert api_client.get("/api/reading/source-follows/").data["count"] == 0
    with pytest.raises(NotFound):
        follow(admin_user, path, "unsubscribe")


def test_refresh_records_once_and_withdrawal_never_returns_historical_metadata(reader_user):
    edition, asset, _ = fixture()
    created = follow(reader_user, f"/reader/{asset.pk}")
    edition.state = "withdrawn"
    edition.save(update_fields=["state"])
    row = sources.refresh(created["id"], reader_user.pk)
    revision = row.revision
    sources.refresh(row.pk, reader_user.pk)
    row.refresh_from_db()
    assert row.revision == revision and row.events.filter(action="changed").count() == 1
    current = sources.output(row)
    assert current["unread_count"] == 1 and current["source"]["title"] == "来源当前不可用"
    read = follow(reader_user, row.path, "mark_read", row.revision)
    assert read["unread_count"] == 0
    canceled = follow(reader_user, row.path, "unsubscribe", read["revision"])
    assert canceled["active"] is False and canceled["history"]["count"] == 4


def test_retention_off_stops_new_follows_and_background_events_without_deleting(reader_user):
    edition, asset, _ = fixture()
    created = follow(reader_user, f"/reader/{asset.pk}")
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"], "retention": {"source_follows": False}})
    edition.state = "withdrawn"
    edition.save(update_fields=["state"])
    row = sources.refresh(created["id"], reader_user.pk)
    assert row.revision == created["revision"] and row.events.count() == 1
    assert sources.output(row)["updates_paused"] is True
    assert sources.refresh_source_follows() == 0
    with pytest.raises(ValidationError):
        follow(reader_user, row.path, revision=row.revision)
    assert SourceFollow.objects.filter(pk=row.pk).exists()
    assert follow(reader_user, row.path, "unsubscribe", row.revision)["active"] is False


def test_export_delete_reuse_existing_private_operations(reader_user):
    edition, asset, _ = fixture()
    created = follow(reader_user, f"/reader/{asset.pk}")
    row = SourceFollow.objects.get(pk=created["id"])
    assert privacy.privacy_summary(reader_user)["export_counts"]["source_follows"] == 1
    assert privacy.list_items(reader_user, "source_follows")["results"][0]["category"] == "source_follows"
    export = privacy.export_item(reader_user, "source_follows", row)
    assert export["history"]["count"] == 1 and "quote" not in str(export)
    target = privacy.target_of(row, "source_follows")
    impact = privacy.erase_impact(reader_user, "source_follows", row)
    privacy.erase_item(reader_user, target, row, impact, contexts=[])
    assert not SourceFollow.objects.exists() and not SourceFollowEvent.objects.exists()
    assert Asset.objects.filter(pk=asset.pk).exists()


def test_task_failure_is_explicit_and_does_not_fake_transition(monkeypatch, reader_user):
    _, asset, _ = fixture()
    created = follow(reader_user, f"/reader/{asset.pk}")
    monkeypatch.setattr(sources, "resolve_public_source", lambda raw: (_ for _ in ()).throw(RuntimeError("synthetic failure")))
    assert sources.refresh_source_follows() == 1
    row = SourceFollow.objects.get(pk=created["id"])
    assert row.check_error == "status_check_failed" and row.events.count() == 1 and row.last_checked_at <= timezone.now()


def test_anonymous_metadata_is_no_store_and_private_follows_require_login(api_client):
    _, asset, _ = fixture()
    public = api_client.get("/api/reading/source-status/", {"path": f"/reader/{asset.pk}"})
    assert public.status_code == 200 and "no-store" in public["Cache-Control"]
    assert api_client.get("/api/reading/source-follows/").status_code in {401, 403}


def test_background_checks_rotate_at_most_200_records(monkeypatch, reader_user):
    SourceFollow.objects.bulk_create([SourceFollow(user=reader_user, path=f"/works/synthetic-{index}",
        state_fingerprint="a" * 64, source_status="unavailable") for index in range(205)])
    checked = []
    def record(follow_id, owner_id):
        checked.append(follow_id)
        SourceFollow.objects.filter(pk=follow_id, user_id=owner_id).update(last_checked_at=timezone.now())
    monkeypatch.setattr(sources, "refresh", record)
    assert sources.refresh_source_follows() == 200
    first = set(checked)
    checked.clear()
    assert sources.refresh_source_follows() == 200
    assert len(set(checked[:5]) - first) == 5


def test_write_requires_owner_pin_even_when_cookie_has_changed(api_client, reader_user, admin_user):
    _, asset, _ = fixture()
    body = {"path": f"/reader/{asset.pk}", "action": "subscribe", "expected_revision": 0, "request_id": str(uuid4())}
    api_client.force_authenticate(admin_user)
    assert api_client.post("/api/reading/source-follows/", body, format="json").status_code == 403
    response = api_client.post("/api/reading/source-follows/", body, format="json", HTTP_X_READER_OWNER=str(reader_user.pk))
    assert response.status_code == 403 and not SourceFollow.objects.exists()
    response = api_client.post("/api/reading/source-follows/", body, format="json", HTTP_X_READER_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and response.data["owner_id"] == str(admin_user.pk)
