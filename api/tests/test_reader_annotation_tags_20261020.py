"""Reader PDF39 private labels. Authored for the final unified acceptance run."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from catalog.models import Asset, Edition, Page, Work
from reading import privacy
from reading.models import Annotation
from reading.serializers import AnnotationSerializer
from reading.services import decrypt_private_text
from tests.v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


@pytest.fixture
def annotation_source():
    work = Work.objects.create(title="标签验收合成材料", document_type="book")
    edition = Edition.objects.create(work=work, state="published", is_primary=True, public_slug=uuid4().hex)
    asset = Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        file="public/annotation-tags-synthetic.pdf", sha256=uuid4().hex * 2,
        access_status="public", page_count=2,
    )
    page = Page.objects.create(asset=asset, index=1, text="合成原文", width=595, height=842)
    other_page = Page.objects.create(asset=asset, index=2, text="另一合成页", width=595, height=842)
    activate_catalog_revision(edition, reader_asset=asset)
    return asset, page, other_page


def create_note(api_client, user, source, **changes):
    asset, page, _ = source
    api_client.force_authenticate(user)
    return api_client.post("/api/reading/annotations/", {
        "asset": str(asset.id), "page": str(page.id), "kind": "note",
        "selector": {"page_index": page.index, "exact": page.text},
        "quote": page.text, "body": "合成私人思考", **changes,
    }, format="json")


def test_labels_normalize_encrypt_and_survive_body_only_update(api_client, reader_user, annotation_source):
    response = create_note(api_client, reader_user, annotation_source, tags=[" 核心概念 ", "", "核心概念", "行为空间"])
    assert response.status_code == 201
    assert response.data["tags"] == ["核心概念", "行为空间"]
    note = Annotation.objects.get(pk=response.data["id"])
    assert "核心概念".encode() not in bytes(note.tags_ciphertext)
    assert json.loads(decrypt_private_text(note.tags_ciphertext)) == response.data["tags"]
    updated = api_client.patch(f"/api/reading/annotations/{note.id}/", {"body": "修改正文"}, format="json")
    assert updated.status_code == 200
    assert updated.data["tags"] == response.data["tags"]
    assert updated.data["body_text"] == "修改正文"
    assert "tags_ciphertext" not in updated.data


def test_legacy_note_returns_empty_labels_and_explicit_clear_does_not_change_body(api_client, reader_user, annotation_source):
    created = create_note(api_client, reader_user, annotation_source)
    assert created.status_code == 201 and created.data["tags"] == []
    url = f"/api/reading/annotations/{created.data['id']}/"
    assert api_client.patch(url, {"tags": ["临时标签"]}, format="json").data["tags"] == ["临时标签"]
    cleared = api_client.patch(url, {"tags": []}, format="json")
    assert cleared.status_code == 200 and cleared.data["tags"] == []
    assert cleared.data["body_text"] == "合成私人思考"
    note = Annotation.objects.get(pk=created.data["id"])
    assert bytes(note.tags_ciphertext) == b""


@pytest.mark.parametrize("tags", [["x" * 41], [str(i) for i in range(13)], [42], [{"label": "不可用"}], None, "不是数组"])
def test_invalid_labels_do_not_create_notes(api_client, reader_user, annotation_source, tags):
    response = create_note(api_client, reader_user, annotation_source, tags=tags)
    assert response.status_code == 400 and "tags" in response.data
    assert not Annotation.objects.filter(user=reader_user).exists()


def test_labels_remain_owner_only_in_api_and_serialization(api_client, reader_user, admin_user, annotation_source):
    created = create_note(api_client, reader_user, annotation_source, tags=["本人标签"])
    note = Annotation.objects.get(pk=created.data["id"])
    api_client.force_authenticate(admin_user)
    url = f"/api/reading/annotations/{note.id}/"
    assert api_client.get(url).status_code == 404
    assert api_client.patch(url, {"tags": ["管理员标签"]}, format="json").status_code == 404
    assert AnnotationSerializer(note, context={"request": SimpleNamespace(user=admin_user)}).data["tags"] == []
    assert AnnotationSerializer(note).data["tags"] == []
    api_client.force_authenticate(reader_user)
    switched = api_client.patch(url, {"tags": ["错误账户"]}, format="json", HTTP_X_READER_OWNER=str(admin_user.id))
    assert switched.status_code == 403
    assert api_client.get(url).data["tags"] == ["本人标签"]


def test_labels_are_exported_and_deleted_with_original_note(api_client, reader_user, annotation_source):
    created = create_note(api_client, reader_user, annotation_source, tags=["导出标签"])
    note = Annotation.objects.get(pk=created.data["id"])
    exported = privacy.annotation_export(reader_user, note)
    assert exported["tags"] == ["导出标签"]
    assert "tags_ciphertext" not in exported and "body_ciphertext" not in exported
    privacy.erase_item(reader_user, privacy.target_of(note, "annotations"), note,
        privacy.erase_impact(reader_user, "annotations", note, contexts=[]), contexts=[])
    assert not Annotation.objects.filter(pk=note.pk).exists()
    assert Asset.objects.filter(pk=annotation_source[0].pk).exists()


def test_retention_off_preserves_existing_edit_and_blocks_new_tags(api_client, reader_user, annotation_source):
    created = create_note(api_client, reader_user, annotation_source, tags=["原有标签"])
    privacy.update_preferences(reader_user, {
        "expected_revision": privacy.preferences(reader_user)["revision"],
        "retention": {"personal_notes": False},
    })
    edited = api_client.patch(f"/api/reading/annotations/{created.data['id']}/", {"tags": ["本人修订"]}, format="json")
    assert edited.status_code == 200 and edited.data["tags"] == ["本人修订"]
    assert create_note(api_client, reader_user, annotation_source, tags=["新标签"]).status_code == 400
    assert Annotation.objects.filter(user=reader_user).count() == 1


@pytest.mark.parametrize("page_index", [0, 2, True, "1"])
def test_selector_page_cannot_disagree_with_page_identity(api_client, reader_user, annotation_source, page_index):
    response = create_note(api_client, reader_user, annotation_source, selector={"page_index": page_index})
    assert response.status_code == 400 and "selector" in response.data


def test_existing_note_cannot_be_moved_with_stale_selector(api_client, reader_user, annotation_source):
    created = create_note(api_client, reader_user, annotation_source, tags=["保留"])
    note = Annotation.objects.get(pk=created.data["id"])
    _, old_page, new_page = annotation_source
    response = api_client.patch(f"/api/reading/annotations/{note.id}/", {"page": str(new_page.id)}, format="json")
    assert response.status_code == 400
    response = api_client.patch(f"/api/reading/annotations/{note.id}/",
        {"page": str(new_page.id), "selector": {"page_index": new_page.index}}, format="json")
    assert response.status_code == 400
    note.refresh_from_db()
    assert note.page_id == old_page.id
    assert note.selector["page_index"] == old_page.index


def test_fixed_request_id_replays_same_normalized_note_without_new_write(api_client, reader_user, annotation_source):
    request_id = str(uuid4())
    created = create_note(api_client, reader_user, annotation_source,
        request_id=request_id, tags=[" 重试标签 ", "", "重试标签"])
    assert created.status_code == 201 and created.data["id"] == request_id
    assert "request_id" not in created.data
    note = Annotation.objects.get(pk=request_id)
    before = (note.updated_at, bytes(note.body_ciphertext), bytes(note.tags_ciphertext))
    replay = create_note(api_client, reader_user, annotation_source,
        request_id=request_id, tags=["重试标签"])
    assert replay.status_code == 201 and replay.data["id"] == request_id
    note.refresh_from_db()
    assert (note.updated_at, bytes(note.body_ciphertext), bytes(note.tags_ciphertext)) == before
    assert Annotation.objects.filter(user=reader_user).count() == 1


@pytest.mark.parametrize("change", [
    {"body": "不同私人正文"}, {"tags": ["不同标签"]}, {"kind": "highlight"},
    {"quote": "不同原文"}, {"selector": {"page_index": 1, "exact": "不同位置"}}, {"color": "sand"},
])
def test_reusing_request_for_different_payload_conflicts_without_overwrite(api_client, reader_user, annotation_source, change):
    request_id = str(uuid4())
    created = create_note(api_client, reader_user, annotation_source, request_id=request_id)
    assert created.status_code == 201
    replay = create_note(api_client, reader_user, annotation_source, request_id=request_id, **change)
    assert replay.status_code == 409
    note = Annotation.objects.get(pk=request_id)
    assert decrypt_private_text(note.body_ciphertext) == "合成私人思考"
    assert note.quote == annotation_source[1].text and note.kind == "note"
    assert Annotation.objects.filter(user=reader_user).count() == 1


def test_request_collision_with_another_owner_uses_generic_conflict(api_client, reader_user, admin_user, annotation_source):
    request_id = str(uuid4())
    created = create_note(api_client, reader_user, annotation_source, request_id=request_id, tags=["本人标签"])
    assert created.status_code == 201
    own_conflict = create_note(api_client, reader_user, annotation_source, request_id=request_id, body="另一内容")
    other_conflict = create_note(api_client, admin_user, annotation_source, request_id=request_id, body="另一内容")
    assert own_conflict.status_code == other_conflict.status_code == 409
    assert own_conflict.data == other_conflict.data
    assert not Annotation.objects.filter(user=admin_user).exists()
    assert Annotation.objects.get(pk=request_id).user_id == reader_user.id


def test_saved_request_can_replay_after_retention_off_but_new_request_cannot(api_client, reader_user, annotation_source):
    request_id = str(uuid4())
    assert create_note(api_client, reader_user, annotation_source, request_id=request_id).status_code == 201
    privacy.update_preferences(reader_user, {
        "expected_revision": privacy.preferences(reader_user)["revision"],
        "retention": {"personal_notes": False},
    })
    assert create_note(api_client, reader_user, annotation_source, request_id=request_id).status_code == 201
    assert create_note(api_client, reader_user, annotation_source, request_id=str(uuid4())).status_code == 400
    assert Annotation.objects.filter(user=reader_user).count() == 1


def test_legacy_creation_stays_supported_and_patch_cannot_change_request_identity(api_client, reader_user, annotation_source):
    first = create_note(api_client, reader_user, annotation_source)
    second = create_note(api_client, reader_user, annotation_source)
    assert first.status_code == second.status_code == 201
    assert first.data["id"] != second.data["id"]
    updated = api_client.patch(f"/api/reading/annotations/{first.data['id']}/",
        {"request_id": str(uuid4()), "body": "不应保存"}, format="json")
    assert updated.status_code == 400
    assert decrypt_private_text(Annotation.objects.get(pk=first.data["id"]).body_ciphertext) == "合成私人思考"
