from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.db import DatabaseError

from accounts.models import User
from catalog.models import Asset, CatalogPublicationRevision, Edition, EditorialRevision, KnowledgePublicationEvent, Page, Work
from catalog.services.editorial_revision import EditorialRevisionError
from ingestion.models import AuditEvent
from reading.models import Annotation, Bookmark, ReadingProgress, SavedItem


pytestmark = pytest.mark.django_db


def pair(*, with_files=False):
    work = Work.objects.create(title="作品规范记录", document_type="book", language="zh-CN")
    editions = []
    for index in (1, 2):
        edition = Edition.objects.create(work=work, state="published", is_primary=index == 1, publication_mode="document" if with_files else "bibliographic",
                                          version_label=f"第{index}版", public_slug=f"primary-v306-{uuid4()}")
        normalized = None
        if with_files:
            digest = sha256(str(edition.pk).encode()).hexdigest()
            original = Asset.objects.create(edition=edition, kind="original", status="ready", validation_status="valid",
                                            file=SimpleUploadedFile(f"original-{index}.pdf", b"%PDF-1.4 isolated-original"), sha256=digest, page_count=1)
            normalized = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
                                              file=SimpleUploadedFile(f"reader-{index}.pdf", b"%PDF-1.4 isolated-reader"), sha256=digest,
                                              source_asset=original, page_count=1)
            Page.objects.create(asset=normalized, index=1, text_source="none", printed_label="1", is_label_manual=True)
        snapshot = {"work": {"id": str(work.pk), "title": f"第{index}版已经公开的题名", "document_type": "book", "language": "zh-CN"},
                    "edition": {"id": str(edition.pk), "public_slug": edition.public_slug, "publication_mode": edition.publication_mode},
                    "contributions": [], "document": {"asset_id": str(normalized.pk), "asset_sha256": normalized.sha256, "page_count": 1} if normalized else {}}
        revision = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active", metadata_ready=True,
                                                             activated_at=timezone.now(), snapshot=snapshot,
                                                             reader_asset=normalized,
                                                             content_fingerprint=sha256(str(snapshot).encode()).hexdigest())
        edition.active_catalog_revision = revision
        edition.save(update_fields=["active_catalog_revision"])
        editions.append(edition)
    return work, *editions


def prepare(client, edition):
    result = client.get(f"/api/catalog/admin/editions/{edition.pk}/primary/")
    assert result.status_code == 200
    return result.data


def select(client, edition, prepared):
    return client.post(f"/api/catalog/admin/editions/{edition.pk}/primary/",
                       {"fingerprint": prepared["fingerprint"], "request_key": prepared["request_key"], "confirm": True}, format="json")


def test_primary_selection_preserves_public_snapshots_urls_and_separates_async_results(api_client, admin_user):
    work, old, target = pair()
    # A canonical value may differ from serving snapshots. A primary-only
    # operation is not authorization to publish that unrelated value.
    work.title = "未发布且不得泄漏的规范题名"
    work.save()
    originals = {row.pk: deepcopy(row.active_catalog_revision.snapshot) for row in (old, target)}
    pointers = {row.pk: row.active_catalog_revision_id for row in (old, target)}
    api_client.force_authenticate(admin_user)
    planned = prepare(api_client, target)
    assert planned["can_select"]
    assert not EditorialRevision.objects.filter(target_id__in=[old.work_id, old.pk, target.pk]).exists() and not KnowledgePublicationEvent.objects.exists()
    assert planned["current_primary_edition_ids"] == [str(old.pk)]
    result = select(api_client, target, planned)
    assert result.status_code == 200
    assert result.data["command_accepted"] and result.data["listing_effective"]
    assert not result.data["projections_complete"]
    assert len(result.data["events"]) == 2
    old.refresh_from_db()
    target.refresh_from_db()
    assert not old.is_primary and target.is_primary
    assert {row.pk: row.active_catalog_revision_id for row in (old, target)} == pointers
    for event in KnowledgePublicationEvent.objects.select_related("catalog_revision"):
        assert event.catalog_revision.snapshot == originals[event.catalog_revision.edition_id]
        assert event.catalog_revision.status == "preparing"
        assert event.changed_fields == ["is_primary"]
    for edition in (old, target):
        public = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
        assert public.status_code == 200
        assert public.data["title"] == originals[target.pk]["work"]["title"]
        assert "未发布且不得泄漏" not in str(public.data)
    assert select(api_client, target, planned).data["audit_id"] == result.data["audit_id"]
    assert EditorialRevision.objects.filter(target_id__in=[old.work_id, old.pk, target.pk]).count() == 2
    assert KnowledgePublicationEvent.objects.count() == 2
    assert AuditEvent.objects.filter(action="catalog.primary_selected").count() == 1


def test_primary_selection_failure_rolls_back_both_editions_and_all_new_records(api_client, admin_user, monkeypatch):
    _, old, target = pair()
    api_client.force_authenticate(admin_user)
    planned = prepare(api_client, target)
    from catalog.services import primary_editions

    real_publish = primary_editions.publish_editorial_revision
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 2:
            raise EditorialRevisionError("受控第二项发布失败")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(primary_editions, "publish_editorial_revision", fail_second)
    result = select(api_client, target, planned)
    assert result.status_code == 409
    old.refresh_from_db()
    target.refresh_from_db()
    assert old.is_primary and not target.is_primary
    assert not EditorialRevision.objects.filter(target_id__in=[old.work_id, old.pk, target.pk]).exists() and not KnowledgePublicationEvent.objects.exists()
    assert not AuditEvent.objects.filter(action="catalog.primary_selected").exists()
    assert CatalogPublicationRevision.objects.count() == 2


def test_primary_selection_rejects_stale_preview_and_unpublished_target(api_client, admin_user):
    _, old, target = pair()
    api_client.force_authenticate(admin_user)
    planned = prepare(api_client, target)
    old.version_label = "预览后变化"
    old.save(update_fields=["version_label", "updated_at"])
    assert select(api_client, target, planned).status_code == 409
    target.state = "draft"
    target.save(update_fields=["state", "updated_at"])
    fresh = prepare(api_client, target)
    assert not fresh["can_select"]
    assert select(api_client, target, fresh).status_code == 409
    assert not EditorialRevision.objects.filter(target_id__in=[old.work_id, old.pk, target.pk]).exists()


def test_primary_selection_refuses_pending_draft_and_requires_explicit_confirmation(api_client, admin_user):
    work, _, target = pair()
    api_client.force_authenticate(admin_user)
    prepared = prepare(api_client, target)
    response = api_client.post(f"/api/catalog/admin/editions/{target.pk}/primary/",
                               {"fingerprint": prepared["fingerprint"], "request_key": prepared["request_key"], "confirm": False}, format="json")
    assert response.status_code == 400
    EditorialRevision.objects.create(target_type="work", target_id=work.pk, revision=1, idempotency_key=str(uuid4()), patch={"title": "草稿"})
    blocked = prepare(api_client, target)
    assert not blocked["can_select"]
    assert any("草稿" in reason for reason in blocked["blocking"])
    assert select(api_client, target, blocked).status_code == 409


def test_primary_replay_cannot_overwrite_a_later_selection(api_client, admin_user):
    _, old, target = pair()
    api_client.force_authenticate(admin_user)
    first = prepare(api_client, target)
    assert select(api_client, target, first).status_code == 200
    back = prepare(api_client, old)
    assert select(api_client, old, back).status_code == 200
    replay = select(api_client, target, first)
    assert replay.status_code == 200
    assert not replay.data["listing_effective"]
    old.refresh_from_db()
    target.refresh_from_db()
    assert old.is_primary and not target.is_primary
    assert KnowledgePublicationEvent.objects.count() == 4


def test_primary_permission_uses_existing_publish_capability(api_client, admin_user, reader_user):
    _, old, target = pair()
    api_client.force_authenticate(admin_user)
    planned = prepare(api_client, target)
    api_client.force_authenticate(reader_user)
    assert select(api_client, target, planned).status_code == 403
    assert api_client.get(f"/api/catalog/admin/editions/{target.pk}/primary/").status_code == 403
    editor = User.objects.create_user(username="primary-editor", email="primary@v306.test", password="V306-test-only-password", role="editor")
    api_client.force_authenticate(editor)
    assert select(api_client, target, planned).status_code == 200
    old.refresh_from_db()
    assert not old.is_primary


def test_primary_selection_cannot_supersede_already_approved_pending_content(api_client, admin_user):
    _, old, target = pair()
    pending = CatalogPublicationRevision.objects.create(edition=target, revision=2, status="preparing", metadata_ready=True,
                                                         snapshot={"work": {"title": "已经批准但尚在发布的新题名"}},
                                                         changed_fields=["title"], content_fingerprint="e" * 64)
    api_client.force_authenticate(admin_user)
    planned = prepare(api_client, target)
    assert not planned["can_select"]
    assert any("尚未生效" in row for row in planned["blocking"])
    assert select(api_client, target, planned).status_code == 409
    assert not EditorialRevision.objects.filter(target_id__in=[old.work_id, old.pk, target.pk]).exists()
    pending.refresh_from_db(); old.refresh_from_db(); target.refresh_from_db()
    assert pending.status == "preparing" and old.is_primary and not target.is_primary


def test_primary_nowait_lock_conflict_has_recoverable_error(api_client, admin_user, monkeypatch):
    _, old, target = pair()
    api_client.force_authenticate(admin_user)
    planned = prepare(api_client, target)
    from django.db.models import QuerySet

    original_iter = QuerySet.__iter__
    class BusyPostgres(Exception):
        sqlstate = "55P03"
    def busy_locked_editions(queryset):
        if queryset.model is Edition and queryset.query.select_for_update:
            assert queryset.query.select_for_update_nowait
            raise DatabaseError("controlled lock_not_available") from BusyPostgres()
        return original_iter(queryset)
    monkeypatch.setattr(QuerySet, "__iter__", busy_locked_editions)
    result = select(api_client, target, planned)
    assert result.status_code == 409
    assert "其他操作" in result.data["detail"]
    assert not EditorialRevision.objects.filter(target_id__in=[old.work_id, old.pk, target.pk]).exists()
    old.refresh_from_db(); target.refresh_from_db()
    assert old.is_primary and not target.is_primary


def test_primary_selection_keeps_file_range_page_ids_and_private_relationships(api_client, admin_user, reader_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.PUBLIC_DEPLOYMENT_MODE = False
    settings.X_ACCEL_REDIRECT_ENABLED = False
    work, old, target = pair(with_files=True)
    old_asset = old.active_catalog_revision.reader_asset
    page = old_asset.pages.get()
    annotation = Annotation.objects.create(user=reader_user, asset=old_asset, page=page, kind="note", asset_sha256=old_asset.sha256,
                                           selector={"page": 1}, body_ciphertext=b"private-test-payload")
    bookmark = Bookmark.objects.create(user=reader_user, asset=old_asset, page=page, label="私人书签")
    progress = ReadingProgress.objects.create(user=reader_user, asset=old_asset, current_page=1, last_position={"page_id": str(page.pk)})
    saved = SavedItem.objects.create(user=reader_user, work=work)
    page_ids = set(Page.objects.values_list("pk", flat=True))
    asset_ids = set(Asset.objects.values_list("pk", flat=True))
    api_client.force_authenticate(admin_user)
    assert select(api_client, target, prepare(api_client, target)).status_code == 200
    annotation.refresh_from_db()
    bookmark.refresh_from_db()
    progress.refresh_from_db()
    saved.refresh_from_db()
    assert set(Page.objects.values_list("pk", flat=True)) == page_ids
    assert set(Asset.objects.values_list("pk", flat=True)) == asset_ids
    assert annotation.page_id == bookmark.page_id == page.pk
    assert annotation.asset_id == bookmark.asset_id == progress.asset_id == old_asset.pk
    assert bytes(annotation.body_ciphertext) == b"private-test-payload" and not annotation.orphaned
    assert progress.last_position == {"page_id": str(page.pk)} and saved.work_id == work.pk
    api_client.force_authenticate(None)
    ranged = api_client.get(f"/api/distribution/assets/{old_asset.pk}/file/", HTTP_RANGE="bytes=0-4")
    assert ranged.status_code == 206
    assert b"".join(ranged.streaming_content) == b"%PDF-"
    ranged.close()
