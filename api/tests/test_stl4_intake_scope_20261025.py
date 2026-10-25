"""Deferred acceptance for intake pagination and exact saved-version recovery."""
from uuid import uuid4

import pytest

from catalog.models import Asset, Edition, Work
from ingestion import intake_confirmation as intake
from ingestion.models import AuditEvent, UploadBatch, UploadItem

pytestmark = pytest.mark.django_db


def sample(actor):
    batch = UploadBatch.objects.create(created_by=actor, expected_count=1)
    return UploadItem.objects.create(batch=batch, source_filename="synthetic-intake.pdf", sha256="a" * 64,
                                     status="ready", recognized_metadata={"title": "合成验收题名"})


def edition(title="合成验收题名"):
    return Edition.objects.create(work=Work.objects.create(title=title))


def get(client, actor, item, **query):
    client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return client.get(f"/api/ingestion/items/{item.pk}/confirmation/", query)


def test_duplicate_is_filtered_before_pagination(api_client, admin_user):
    item, target = sample(admin_user), edition()
    Asset.objects.create(edition=target, kind="original", file="synthetic/source.pdf", sha256=item.sha256)
    for _ in range(18):
        edition()
    initial = get(api_client, admin_user, item)
    assert initial.status_code == 200 and initial.data["count"] == 19
    assert str(target.pk) not in {row["id"] for row in initial.data["candidates"]}
    filtered = get(api_client, admin_user, item, scope="duplicate")
    assert filtered.status_code == 200 and filtered.data["count"] == 1
    assert filtered.data["candidates"][0]["id"] == str(target.pk)
    assert filtered.data["candidates"][0]["exact_duplicate"]
    assert get(api_client, admin_user, item, scope="duplicate", q="无匹配内容").data["count"] == 0
    assert get(api_client, admin_user, item, scope="duplicate", work=str(edition().work_id)).data["count"] == 0


def test_same_title_excludes_other_titles_and_preserves_real_count(api_client, admin_user):
    item = sample(admin_user)
    targets = [edition(), edition()]
    for index in range(18):
        edition(f"合成验收题名补充{index}")
    response = get(api_client, admin_user, item, scope="same", page=999)
    assert response.status_code == 200 and response.data["scope"] == "same"
    assert response.data["count"] == 2 and response.data["page"] == 1
    assert {row["id"] for row in response.data["candidates"]} == {str(row.pk) for row in targets}
    assert response.data["match_title"] == "合成验收题名"


def test_missing_source_identity_does_not_match_blank_database_values(api_client, admin_user):
    item = sample(admin_user)
    item.sha256, item.recognized_metadata = "", {}
    item.save()
    edition()
    for scope in ("same", "duplicate"):
        assert get(api_client, admin_user, item, scope=scope).data["count"] == 0


def test_same_title_uses_existing_canonical_title_without_approximate_search_gate(api_client, admin_user):
    item = sample(admin_user)
    item.recognized_metadata = {"title": "  Straße  "}
    item.save()
    target = edition("STRASSE")
    response = get(api_client, admin_user, item, scope="same")
    assert response.status_code == 200 and response.data["count"] == 1
    assert response.data["candidates"][0]["id"] == str(target.pk)


def test_saved_candidate_is_independent_of_page_and_keeps_original_version(api_client, admin_user):
    item, target = sample(admin_user), edition()
    old_version = intake.edition_version(target)
    choice = {"mode": "use_edition", "edition_id": str(target.pk), "candidate_version": old_version,
              "document_type": "book", "title": target.work.title, "note": "仅当前管理员的核对说明"}
    AuditEvent.objects.create(actor=admin_user, action=intake.ACTION, object_type="UploadItem", object_id=str(item.pk),
                              request_id=str(uuid4()), after={"choice": choice, "operation": "save"})
    target.version_label = "修改后的真实版次"
    target.save()
    response = get(api_client, admin_user, item, q="不存在的检索词", scope="duplicate")
    assert response.status_code == 200 and response.data["count"] == 0
    assert response.data["selected_candidate"]["id"] == str(target.pk)
    assert response.data["selected_candidate"]["version"] != old_version
    assert response.data["draft"]["candidate_version"] == old_version
    other = edition("另一本合成材料")
    changed = get(api_client, admin_user, item, selected=str(other.pk))
    assert changed.data["selected_candidate"]["id"] == str(other.pk)
    assert changed.data["draft"] == choice
    target.delete()
    assert get(api_client, admin_user, item).data["selected_candidate"] is None


def test_owner_and_current_permissions_are_checked_after_projection(api_client, admin_user, reader_user, monkeypatch):
    item = sample(admin_user)
    edition()
    assert get(api_client, reader_user, item).status_code == 403
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.get(f"/api/ingestion/items/{item.pk}/confirmation/").status_code == 403
    original = intake.candidate_row

    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        type(admin_user).objects.filter(pk=admin_user.pk).update(token_version=admin_user.token_version + 1)
        return result

    monkeypatch.setattr(intake, "candidate_row", revoke)
    assert get(api_client, admin_user, item).status_code == 403


def test_receipt_carries_original_item_and_remains_scoped(api_client, admin_user):
    item, other, request_id = sample(admin_user), sample(admin_user), uuid4()
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    path = f"/api/ingestion/items/{item.pk}/confirmation/commands/{request_id}/"
    result = api_client.post(path, {"action": "cancel_pending"}, format="json")
    assert result.status_code == 200 and result.data["item_id"] == str(item.pk)
    assert result.data["state"] == "cancelled"
    assert "no-store" in result["Cache-Control"]
    assert api_client.get(f"/api/ingestion/items/{other.pk}/confirmation/commands/{request_id}/").status_code == 404


def test_invalid_scope_and_selected_identity_are_rejected(api_client, admin_user):
    item = sample(admin_user)
    assert get(api_client, admin_user, item, scope="unrecognized").status_code == 400
    assert get(api_client, admin_user, item, selected="not-an-id").status_code == 400
