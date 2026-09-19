"""v3.0.6 real ORM/API checks; external processing is not exercised here."""
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import User
from catalog.models import Asset, CatalogPublicationRevision, CatalogingSession, Edition, EditorialRevision, PublicationEvent, Work
from catalog.services.admin_queue import edition_summary, load_admin_editions
from catalog.services.admin_workspace import _file_data
from catalog.services.field_decisions import field_readiness
from catalog.services.publication_commands import catalog_publication_state
from common.capabilities import Capability, has_capability
from ingestion.models import FieldLock, MetadataCandidate, UploadBatch, UploadItem
from ingestion.serializers import UploadItemSerializer
from ingestion.services.publication import publication_preflight
from .test_catalog_contracts_v305 import _manual_ready
from .test_publication_invariants_v305 import published_edition
from .test_resilient_publication_v260 import create_item_with_files
from .test_admin_workflow_v280 import confirm_required_catalog_fields


pytestmark = pytest.mark.django_db
QUEUE = "/api/catalog/admin/workflows/queue/"
LIBRARY = "/api/catalog/admin/library/works/"


def upload(admin, edition=None, *, failed=False):
    batch = UploadBatch.objects.create(created_by=admin, expected_count=1)
    return UploadItem.objects.create(batch=batch, edition=edition, source_filename=f"v306-{uuid4()}.pdf",
                                     status="failed" if failed else "ready", error_code="validation_failed" if failed else "")


@pytest.mark.parametrize("invalid", ["missing", "foreign", "superseded", "not_ready"])
def test_A01_A02_all_admin_consumers_use_actual_active_revision(api_client, admin_user, invalid):
    edition, revision = published_edition(f"状态一致-{invalid}")
    if invalid == "missing":
        edition.active_catalog_revision = None
    elif invalid == "foreign":
        _, foreign = published_edition("别的作品")
        edition.active_catalog_revision = foreign
    else:
        if invalid == "superseded":
            revision.status = "superseded"
        else:
            revision.metadata_ready = False
        revision.save(update_fields=["status", "metadata_ready"])
    edition.save(update_fields=["active_catalog_revision"])
    edition.refresh_from_db()
    item = upload(admin_user, edition)
    api_client.force_authenticate(admin_user)
    state = catalog_publication_state(edition)
    assert state["public_state"] == "unpublished"
    assert state["command_accepted"]
    assert state["active_revision_id"] is None
    assert state["public_url"] == ""
    assert not state["catalog_revision_active"]
    review = UploadItemSerializer().get_review_data(item)
    listed = api_client.get(LIBRARY, {"q": edition.work.title}).data["results"][0]
    queue = api_client.get(QUEUE, {"scope": "publication", "q": edition.work.title}).data["results"][0]
    workspace = api_client.get(f"{LIBRARY}{edition.work_id}/?edition={edition.pk}").data
    preview = api_client.get(f"/api/catalog/admin/page-preview/editions/{edition.pk}/")
    assert preview.status_code == 200
    assert preview.data["public_url"] == ""
    assert preview.data["return_url"].endswith(f"?edition={edition.pk}")
    for value in (review["publication"], listed["publication"], queue["publication"], workspace["publication"], preview.data["publication"]):
        assert value["public_state"] == state["public_state"]
        assert not value["listed_publicly"]
        assert value["public_url"] == ""
    assert workspace["workflow"]["overall_status"] != "published"
    assert api_client.get(LIBRARY, {"q": edition.work.title, "view": "published"}).data["count"] == 0


def test_A03_nonprimary_revision_and_real_edition_rows(api_client, admin_user):
    primary, _ = published_edition("同一作品多版本")
    second = Edition.objects.create(work=primary.work, is_primary=False, state="published", version_label="第二版", publication_year=2025)
    revision = CatalogPublicationRevision.objects.create(edition=second, revision=1, status="active", metadata_ready=True,
                                                         content_fingerprint="a" * 64, snapshot={"work": {"title": primary.work.title}})
    second.active_catalog_revision = revision
    second.save(update_fields=["active_catalog_revision"])
    api_client.force_authenticate(admin_user)
    result = api_client.get(LIBRARY, {"view": "editions", "work_id": primary.work_id})
    assert result.status_code == 200
    assert result.data["count"] == 2
    rows = {row["edition_id"]: row for row in result.data["results"]}
    assert set(rows) == {str(primary.pk), str(second.pk)}
    row = rows[str(second.pk)]
    assert row["id"] == str(second.pk) and row["row_type"] == "edition"
    assert row["publication"]["public_state"] == "published"
    assert row["publication"]["catalog_revision_active"]
    assert not row["publication"]["listed_publicly"]
    assert row["publication"]["public_url"] == ""
    assert f"edition={second.pk}" in row["workbench_url"]
    wrong = api_client.get(f"{LIBRARY}{primary.work_id}/?edition={uuid4()}")
    assert wrong.status_code == 400


def test_A03_edition_scoped_draft_does_not_mark_another_version_pending(api_client, admin_user):
    first, _ = published_edition("版本修订范围")
    second = Edition.objects.create(work=first.work, is_primary=False, state="published", publication_mode="bibliographic")
    revision = CatalogPublicationRevision.objects.create(edition=second, revision=1, status="active", metadata_ready=True,
                                                         content_fingerprint="b" * 64, snapshot={"work": {"title": first.work.title}})
    second.active_catalog_revision = revision
    second.save(update_fields=["active_catalog_revision"])
    EditorialRevision.objects.create(target_type="work", target_id=first.work_id, revision=1, idempotency_key=str(uuid4()),
                                      patch={"bibliography": {"edition_id": str(second.pk), "values": {"publisher": "仅第二版出版社"}}})
    rows = {row.pk: edition_summary(row, user=admin_user) for row in load_admin_editions(Edition.objects.filter(work=first.work))}
    assert rows[first.pk]["health"]["publication"] == "published"
    assert rows[first.pk]["editing"]["draft_revision_id"] is None
    assert rows[second.pk]["health"]["publication"] == "changes_pending"
    assert rows[second.pk]["editing"]["draft_revision_id"] is not None
    api_client.force_authenticate(admin_user)
    workspace = api_client.get(f"{LIBRARY}{first.work_id}/?edition={first.pk}")
    assert workspace.status_code == 200
    assert workspace.data["editorial_revision"] is None
    assert workspace.data["other_edition_draft"] is not None
    preview = api_client.get(f"/api/catalog/admin/page-preview/editions/{first.pk}/")
    assert preview.status_code == 200 and preview.data["editorial_revision"] is None
    before = CatalogPublicationRevision.objects.count()
    wrong_publish = api_client.post(f"{LIBRARY}{first.work_id}/publication/?edition={first.pk}",
                                     {"confirm_warnings": True}, format="json")
    assert wrong_publish.status_code == 409
    assert "另一个出版版本" in str(wrong_publish.data)
    assert CatalogPublicationRevision.objects.count() == before
    assert EditorialRevision.objects.get(target_type="work", target_id=first.work_id).status == "draft"


@pytest.mark.parametrize("validation", ["pending", "valid", "invalid"])
def test_A04_pdf_three_states_drive_data_fields_preflight_and_workflow(api_client, admin_user, settings, tmp_path, validation):
    work, edition, original, normalized = create_item_with_files(settings, tmp_path, title=f"三态-{validation}")
    confirm_required_catalog_fields(edition, admin_user)
    normalized.validation_status = validation
    normalized.save(update_fields=["validation_status"])
    data = _file_data(None, edition)
    assert data["validation"] == validation
    assert data["is_valid_pdf"] is (validation == "valid")
    file_value = next(row for row in field_readiness(edition) if row.field_name == "file").value
    assert bool(file_value) is (validation == "valid")
    checks = publication_preflight(edition)
    assert bool(checks["blockers"]) is (validation != "valid")
    if validation != "valid":
        assert any(("等待验证" if validation == "pending" else "验证失败") in value for value in checks["blockers"])
    api_client.force_authenticate(admin_user)
    response = api_client.get(f"{LIBRARY}{work.pk}/?edition={edition.pk}")
    assert response.status_code == 200
    steps = {row["key"]: row for row in response.data["workflow"]["steps"]}
    assert (steps["file"]["status"] == "blocked") is (validation != "valid")
    assert response.data["data"]["file"]["is_valid_pdf"] is (validation == "valid")
    assert (response.data["data"]["publication"]["reader_state"] == "ready") is (validation == "valid")


@pytest.mark.parametrize("validation", ["missing", "pending", "valid", "invalid"])
def test_A04_replacement_file_never_inherits_validation_from_old_reader(admin_user, settings, tmp_path, validation):
    _, edition, old_original, old_reader = create_item_with_files(settings, tmp_path)
    item = upload(admin_user, edition)
    item.status = "received"
    item.sha256 = "a" * 64
    item.replacement_of_asset = old_reader
    item.save()
    if validation != "missing":
        original = Asset.objects.create(edition=edition, kind="original", version=2, is_current=False,
                                        sha256=item.sha256, validation_status=validation)
        Asset.objects.create(edition=edition, kind="normalized", version=2, is_current=False,
                             source_asset=original, sha256=item.sha256, validation_status=validation)
        item.asset = original
        item.save(update_fields=["asset"])
    data = _file_data(None, edition)
    assert data["filename"] == item.source_filename
    assert data["validation"] == ("pending" if validation == "missing" else validation)
    assert data["is_valid_pdf"] is (validation == "valid")
    assert data["original_asset_id"] != str(old_original.pk)
    assert data["normalized_asset_id"] != str(old_reader.pk)
    assert {str(old_original.pk), str(old_reader.pk)}.issubset({row["id"] for row in data["file_history"]})


def test_A04_first_pdf_waiting_for_processing_is_not_a_no_pdf_bibliography(admin_user):
    work = Work.objects.create(title="已补充文件待处理")
    edition = Edition.objects.create(work=work, publication_mode="bibliographic")
    item = upload(admin_user, edition)
    item.status = "received"
    item.save(update_fields=["status"])
    data = _file_data(None, edition)
    assert data["can_supplement"] is False
    assert data["validation"] == "pending"
    assert data["is_valid_pdf"] is False


def test_A05_A10_A12_complete_sources_old_failures_and_server_counts(api_client, admin_user):
    old = upload(admin_user, failed=True)
    UploadItem.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(days=100))
    for _ in range(34):
        upload(admin_user)
    manual = _manual_ready(admin_user)
    published, _ = published_edition("维护中的真实旧版")
    draft = EditorialRevision.objects.create(target_type="work", target_id=published.work_id, revision=1,
                                            idempotency_key=f"v306:{uuid4()}", patch={"title": "新的维护草稿"})
    api_client.force_authenticate(admin_user)
    first = api_client.get(QUEUE)
    assert first.status_code == 200
    assert first.data["count"] == 37
    assert first.data["counts"]["all"] == 37
    assert first.data["results"][0]["item_id"] == str(old.pk)
    identifiers = {row["id"] for row in first.data["results"]}
    second = api_client.get(first.data["next"])
    assert second.data["previous"]
    assert not identifiers.intersection(row["id"] for row in second.data["results"])
    identifiers.update(row["id"] for row in second.data["results"])
    assert len(identifiers) == 37
    assert {f"edition:{manual.pk}", f"edition:{published.pk}", f"upload:{old.pk}"} <= identifiers
    exceptional = api_client.get(QUEUE, {"category": "exception"})
    assert exceptional.data["count"] == exceptional.data["counts"]["exception"]
    assert any(row["item_id"] == str(old.pk) for row in exceptional.data["results"])
    only_manual = api_client.get(QUEUE, {"source": "manual"})
    assert only_manual.data["count"] == 1
    assert only_manual.data["results"][0]["edition_id"] == str(manual.pk)
    assert only_manual.data["results"][0]["source_type"] == "manual"
    assert UploadItem.objects.filter(edition=manual).count() == 0
    assert EditorialRevision.objects.get(pk=draft.pk).status == "draft"


def test_A11_library_traversal_filter_sort_and_edition_scope(api_client, admin_user):
    ids = set()
    for index in range(43):
        work = Work.objects.create(title=f"馆藏{index:03}", document_type="report")
        ids.add(str(work.pk))
        Edition.objects.create(work=work, publication_mode="bibliographic", report_institution="测试机构")
    api_client.force_authenticate(admin_user)
    first = api_client.get(LIBRARY, {"q": "馆藏", "document_type": "report", "ordering": "-title"})
    assert first.status_code == 200 and first.data["count"] == 43
    assert first.data["results"][0]["title"] == "馆藏042"
    assert first.data["page"] == 1 and first.data["total_pages"] == 2
    assert "ordering=-title" in first.data["next"] and "document_type=report" in first.data["next"]
    second = api_client.get(first.data["next"])
    all_ids = [row["id"] for row in [*first.data["results"], *second.data["results"]]]
    assert len(all_ids) == len(set(all_ids)) == 43
    assert set(all_ids) == ids
    assert api_client.get(LIBRARY, {"view": "editions", "work_id": next(iter(ids))}).data["count"] == 1


def test_A12_publication_scope_paginates_beyond_upload_sources(api_client, admin_user):
    ids = set()
    for index in range(64):
        edition, _ = published_edition(f"已公开{index:03}")
        ids.add(str(edition.pk))
    api_client.force_authenticate(admin_user)
    url = f"{QUEUE}?scope=publication&publication=published"
    seen = []
    while url:
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.data["count"] == 64
        seen.extend(row["edition_id"] for row in response.data["results"])
        url = response.data["next"]
    assert len(seen) == len(set(seen)) == 64 and set(seen) == ids


def test_queue_batch_load_is_bounded_and_never_checks_external_storage(api_client, admin_user, monkeypatch):
    monkeypatch.setattr("ingestion.services.publication._asset_storage_readable", lambda asset: pytest.fail("queue must not probe NAS"))
    api_client.force_authenticate(admin_user)
    for index in range(3):
        Edition.objects.create(work=Work.objects.create(title=f"批量{index}"), publication_mode="bibliographic")
    with CaptureQueriesContext(connection) as small:
        assert api_client.get(QUEUE).status_code == 200
    for index in range(42):
        Edition.objects.create(work=Work.objects.create(title=f"新增{index}"), publication_mode="bibliographic")
    with CaptureQueriesContext(connection) as large:
        response = api_client.get(QUEUE)
    assert response.status_code == 200
    assert response.data["count"] == 45
    assert len(large) <= len(small) + 2
    assert len(large) <= 36


def test_batched_fields_match_single_object_and_are_read_only(admin_user):
    edition = _manual_ready(admin_user)
    expected = [(row.field_name, row.status, row.value, row.required) for row in field_readiness(edition)]
    loaded = load_admin_editions(Edition.objects.filter(pk=edition.pk))[0]
    with CaptureQueriesContext(connection) as captured:
        actual = [(row.field_name, row.status, row.value, row.required) for row in field_readiness(loaded)]
        summary = edition_summary(loaded, user=admin_user)
    assert actual == expected
    assert len(captured) == 0
    assert summary["publication"]["public_state"] == "unpublished"
    assert not CatalogPublicationRevision.objects.filter(edition=edition).exists()


def test_A05_manual_queue_is_also_the_workspace_next_item_source(api_client, admin_user):
    current = _manual_ready(admin_user)
    following = _manual_ready(admin_user)
    api_client.force_authenticate(admin_user)
    workspace = api_client.get(f"{LIBRARY}{current.work_id}/?edition={current.pk}")
    assert workspace.status_code == 200
    queue = workspace.data["queue"]
    assert queue["remaining_count"] == 1
    assert queue["next_item_id"] is None
    assert queue["next_edition_id"] == str(following.pk)
    assert queue["next_session_id"] == str(following.cataloging_sessions.get().pk)
    assert queue["next_workbench_url"] == f"/admin/cataloging/{queue['next_session_id']}"
    assert workspace.data["data"]["publication"]["reader_state"] == "not_applicable"
    assert not UploadItem.objects.exists()


def test_A15_candidate_conflict_is_traceable_without_overwriting_manual_value(api_client, admin_user):
    edition = _manual_ready(admin_user)
    original = edition.work.title
    lock = FieldLock.objects.create(edition=edition, field_name="title", locked_value=original, locked_by=admin_user, reason="人工确认")
    session = edition.cataloging_sessions.get()
    candidate = MetadataCandidate.objects.create(cataloging_session=session, field_name="title", value="不能覆盖的候选",
                                                source="isolated_fixture", conflict_group="same-field-different-source")
    api_client.force_authenticate(admin_user)
    response = api_client.get(QUEUE, {"source": "manual", "category": "attention"})
    assert response.status_code == 200
    assert response.data["results"][0]["candidate_conflicts"][0]["candidate_id"] == str(candidate.pk)
    edition.work.refresh_from_db()
    lock.refresh_from_db()
    assert edition.work.title == lock.locked_value == original
    candidate.refresh_from_db()
    assert candidate.lifecycle == "proposed"


def test_A26_editor_retains_actual_publication_api_permission(api_client, admin_user):
    edition = _manual_ready(admin_user)
    editor = User.objects.create_user(username="v306-publisher", email="publisher@v306.test", password="V306-test-only-password", role="editor")
    api_client.force_authenticate(editor)
    response = api_client.post(f"{LIBRARY}{edition.work_id}/publication/?edition={edition.pk}",
                               {"confirm_warnings": True}, format="json")
    assert response.status_code == 200
    edition.refresh_from_db()
    assert edition.state == "published"
    assert CatalogPublicationRevision.objects.filter(edition=edition).exists()
    assert response.data["permissions"]["can_publish"]
    assert not response.data["permissions"]["can_withdraw"]


@pytest.mark.parametrize("role", ["editor", "admin", "owner", "reader", "anonymous"])
def test_A26_withdraw_permission_is_same_for_maintenance_and_upload(api_client, admin_user, superadmin_user, role):
    if role == "owner":
        actor = superadmin_user
    elif role == "admin":
        actor = admin_user
    elif role == "anonymous":
        actor = None
    else:
        actor = User.objects.create_user(username=f"v306-{role}", email=f"{role}@v306.test", password="V306-test-only-password", role=role)
    api_client.force_authenticate(actor)
    assert has_capability(actor, Capability.WITHDRAW_WORK) is (role in {"owner", "admin"})
    assert has_capability(actor, Capability.PUBLISH_WORK) is (role in {"owner", "admin", "editor"})
    for entry in ("maintenance", "upload"):
        edition, revision = published_edition(f"撤回-{role}-{entry}")
        item = upload(admin_user, edition)
        url = f"{LIBRARY}{edition.work_id}/publication/?edition={edition.pk}" if entry == "maintenance" else f"/api/ingestion/items/{item.pk}/withdraw/"
        response = api_client.post(url, {"action": "withdraw", "reason": "隔离测试"}, format="json")
        if role in {"admin", "owner"}:
            assert response.status_code == 200
            assert api_client.post(url, {"action": "withdraw", "reason": "重试"}, format="json").status_code == 200
            assert PublicationEvent.objects.filter(edition=edition, event_type="withdraw").count() == 1
        else:
            assert response.status_code in {401, 403}
            assert not PublicationEvent.objects.filter(edition=edition).exists()
        edition.refresh_from_db()
        assert (edition.state == "withdrawn") is (role in {"admin", "owner"})
        assert CatalogPublicationRevision.objects.filter(pk=revision.pk).exists()
