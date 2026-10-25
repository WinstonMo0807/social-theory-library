"""Deferred multi-source grant acceptance. Synthetic records; not run during development."""
import json
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Edition, RecommendationIssue
from catalog.services.editorial_issues import issue_draft_payload
from reading import privacy, reader_shares, research, share_scope, sharing_privacy
from reading.models import ReadingList, ReadingListItem, ResearchProject
from reading.sharing_models import ReaderShare
from reading.sharing_views import SharePreviewInput
from tests.test_publication_invariants_v305 import published_edition
from tests.test_stl4_reader_proposal_editorial_20261024 import account, command, preview, PATH

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_key(settings):
    settings.PRIVATE_DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()


def project(user, suffix="甲"):
    row = ResearchProject.objects.create(user=user, data_ciphertext=research.pack({
        "title": f"合成私人研究{suffix}", "question": f"主动选择的问题{suffix}",
        "notes": f"未选择的私人正文{suffix}", "selections": []}))
    return row, {"source_kind": "research", "source_id": row.pk, "expected_version": privacy.version(row),
        "questions": ["project"], "materials": [], "notes": []}


def booklist(user):
    edition, _ = published_edition("合成多对象公开书目")
    Edition.objects.filter(pk=edition.pk).update(is_primary=True)
    row = ReadingList.objects.create(user=user, title="合成私人书单")
    item = ReadingListItem.objects.create(reading_list=row, work=edition.work)
    return row, edition, {"source_kind": "booklist", "source_id": row.pk, "expected_version": privacy.version(row),
        "questions": [], "materials": [str(item.pk)], "notes": []}


def create(user, first, *additional, destination="public"):
    body = {**first, "message": "显式选择的合成附言", "destination": destination, "expires_days": 7}
    if additional:
        body["additional_sources"] = list(additional)
    body.update(request_id=uuid4(), confirmed=True, preview_hash=share_scope.preview(user, body)[0]["preview_hash"])
    receipt = reader_shares.create(user, body)
    return ReaderShare.objects.get(pk=receipt["share"]["id"]), receipt, body


def test_mixed_scope_public_projection_and_original_receipt(reader_user):
    first, a = project(reader_user)
    second, edition, b = booklist(reader_user)
    row, receipt, body = create(reader_user, a, b)
    value = reader_shares.read(row, token=receipt["token"])
    assert receipt["share"]["source_count"] == 2
    assert value["sources"] == [{"kind": "research", "title": "合成私人研究甲"}, {"kind": "booklist", "title": "合成私人书单"}]
    assert value["sections"]["questions"][0]["origin_kind"] == "research"
    assert value["sections"]["materials"][0]["origin_kind"] == "booklist"
    assert value["sections"]["materials"][0]["work"]["id"] == str(edition.work_id)
    encoded = json.dumps(value, default=str, ensure_ascii=False)
    assert str(first.pk) not in encoded and str(second.pk) not in encoded
    assert "未选择的私人正文" not in encoded
    assert encoded.count("显式选择的合成附言") == 1
    assert all("id" not in item and "version" not in item for items in value["sections"].values() for item in items)
    assert reader_shares.create(reader_user, body)["share"]["id"] == str(row.pk)
    assert ReaderShare.objects.count() == 1


@pytest.mark.parametrize("mutation", ["change", "delete"])
def test_secondary_change_or_removal_invalidates_entire_grant(reader_user, mutation):
    _, a = project(reader_user)
    second, b = project(reader_user, "乙")
    row, receipt, _ = create(reader_user, a, b)
    if mutation == "delete":
        second.delete()
    else:
        second.revision += 1
        second.data_ciphertext = research.pack({"title": "新题名", "question": "未授权的新内容", "notes": "", "selections": []})
        second.save()
    with pytest.raises(NotFound):
        reader_shares.read(row, token=receipt["token"])


def test_foreign_duplicate_and_total_limits_are_rejected(reader_user, admin_user):
    _, a = project(reader_user)
    _, foreign = project(admin_user)
    base = {**a, "message": "", "destination": "proposal", "expires_days": 7}
    with pytest.raises(NotFound):
        share_scope.preview(reader_user, {**base, "additional_sources": [foreign]})
    with pytest.raises(ValidationError):
        share_scope.preview(reader_user, {**base, "additional_sources": [a]})
    sources = [{**a, "source_id": uuid4(), "questions": [str(i) for i in range(11)]} for _ in range(2)]
    serializer = SharePreviewInput(data={**base, **sources[0], "additional_sources": sources[1:]})
    assert not serializer.is_valid()
    too_many = [{**a, "source_id": uuid4()} for _ in range(5)]
    assert not SharePreviewInput(data={**base, "additional_sources": too_many}).is_valid()
    _, empty = project(reader_user, "乙")
    with pytest.raises(ValidationError):
        share_scope.content(reader_user, {**base, "additional_sources": [{**empty, "questions": []}]})


def test_directory_uses_public_bibliography_and_keeps_private_text_out(reader_user):
    row, edition, _ = booklist(reader_user)
    value = share_scope.directory_source(row, 'booklist')
    assert value['material_count'] == 1 and value['first_material']['title'] == '合成多对象公开书目'
    Edition.objects.filter(pk=edition.pk).update(state='withdrawn')
    assert share_scope.directory_source(row, 'booklist')['first_material'] is None
    project_row, _ = project(reader_user)
    assert '主动选择的问题' not in json.dumps(share_scope.directory_source(project_row, 'research'), ensure_ascii=False)


def test_single_source_encoding_and_owner_export_revoke(reader_user):
    _, a = project(reader_user)
    row, receipt, body = create(reader_user, a)
    content, bindings = share_scope.single_content(reader_user, body)
    saved = research.unpack(row)
    assert "sources" not in content and "additional_sources" not in saved["specification"]
    assert saved["content_hash"] == share_scope.digest(content) and saved["bindings"] == bindings
    _, b = project(reader_user, "乙")
    multi, receipt, _ = create(reader_user, a, b)
    exported = sharing_privacy.export(reader_user, "reader_shares", multi)
    assert exported["selection"]["additional_sources"][0]["source_id"] == str(b["source_id"])
    reader_shares.revoke(reader_user, multi.pk, multi.revision)
    multi.refresh_from_db()
    assert "specification" not in research.unpack(multi) and not multi.token_ciphertext
    with pytest.raises(NotFound):
        reader_shares.read(multi, token=receipt["token"])


def test_mixed_proposal_only_seeds_explicit_public_bibliography(api_client, reader_user, admin_user):
    _, a = project(reader_user)
    _, edition, b = booklist(reader_user)
    row, _, _ = create(reader_user, a, b, destination="proposal")
    account(api_client, admin_user)
    result = api_client.post(PATH, command(preview(api_client, row)), format="json")
    assert result.status_code == 201, result.data
    draft = issue_draft_payload(RecommendationIssue.objects.get(pk=result.data["issue_id"]))
    assert len(draft["items"]) == 1 and draft["items"][0]["edition_id"] == str(edition.pk)
    assert draft["body_blocks"] == []
    assert "合成私人" not in json.dumps(draft, ensure_ascii=False)
    assert "主动选择的问题" not in json.dumps(draft, ensure_ascii=False)
