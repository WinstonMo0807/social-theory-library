"""Synthetic R34 contracts. Written for the later unified acceptance run."""
from uuid import uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import PermissionDenied, ValidationError

from reading import research
from reading.shared_citation_views import selection_range
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def raw_page(asset, span):
    return {"asset_id": str(asset.id), "document_revision_id": str(span.document_revision_id), "pdf_page": span.page_number}


def test_public_preview_resolves_exact_selection_and_not_client_title(api_client):
    _, asset, spans, _ = fixture_source(count=1)
    selected = "来自同一正式修订"
    response = api_client.post("/api/reading/citation-preview/", {"reference": raw_page(asset, spans[0]),
        "selected_text": selected, "title": "不可信标题"}, format="json")
    assert response.status_code == 200
    assert response.data["reference"]["quote"] == selected
    assert ":range:" in response.data["reference"]["reference_id"]
    assert response.data["source"]["title"] == "正式检索材料"
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("selected", ["不存在的文字", "", "同同"])
def test_unmatched_or_ambiguous_selection_never_guessed(selected):
    with pytest.raises(ValidationError):
        selection_range("同同同", selected)


def test_whitespace_matching_preserves_canonical_offsets_and_unicode():
    source = "😀 原文\n段落。"
    start, end = selection_range(source, "原文 段落。")
    assert source[start:end] == "原文\n段落。"


def test_two_selections_on_same_page_keep_separate_identities(reader_user):
    _, asset, spans, _ = fixture_source(count=1)
    ref = research.resolve_reference(raw_page(asset, spans[0]), reader_user, strict=True)
    first = {**research.compact_reference(ref), "selection_start": 0, "selection_end": 4}
    second = {**research.compact_reference(ref), "selection_start": 5, "selection_end": 9}
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "选文"})
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision, "action": "add", "references": [first, second]})
    selected = research.serialize_record(project, reader_user)["data"]["selections"]
    assert len(selected) == 2
    assert selected[0]["reference_id"] != selected[1]["reference_id"]
    assert selected[0]["quote"] == spans[0].page.text[:4]


def test_range_needs_exact_revision_hash_and_bounds(reader_user):
    _, asset, spans, _ = fixture_source(count=1)
    raw = raw_page(asset, spans[0])
    for extra in [{"selection_start": 0, "selection_end": 2}, {"selection_start": -1, "selection_end": 2, "content_hash": "a" * 64}]:
        with pytest.raises(ValidationError):
            research.resolve_reference({**raw, **extra}, reader_user, strict=True)


def test_changed_page_invalidates_saved_range_without_old_quote(reader_user):
    _, asset, spans, _ = fixture_source(count=1)
    reference = research.resolve_reference(raw_page(asset, spans[0]), reader_user, strict=True)
    compact = {**research.compact_reference(reference), "selection_start": 0, "selection_end": 4}
    page = spans[0].page
    page.text = "不同的新正文"
    page.save(update_fields=["text"])
    result = research.resolve_reference(compact, reader_user)
    assert result["source_status"] == "unavailable"
    assert "quote" not in result


def test_admin_preview_still_uses_public_permissions(api_client, admin_user):
    _, asset, spans, _ = fixture_source(count=1)
    asset.access_status = "private"
    asset.save(update_fields=["access_status"])
    api_client.force_authenticate(admin_user)
    response = api_client.post("/api/reading/citation-preview/", {"reference": raw_page(asset, spans[0])}, format="json")
    assert response.status_code == 400
    assert "真实夹具文本" not in str(response.data)


def test_metadata_citation_remains_available_without_fulltext(api_client):
    edition, _, _, _ = fixture_source(count=1)
    edition.active_catalog_revision.fulltext_ready = False
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    response = api_client.post("/api/reading/citation-preview/", {"edition_id": str(edition.id)}, format="json")
    assert response.status_code == 200
    assert response.data["reference"] is None
    assert response.data["source"]["pdf_page"] is None


@pytest.mark.parametrize("printed", ["", "xv"])
def test_pdf_position_is_not_exported_as_a_printed_page(api_client, printed):
    _, asset, spans, _ = fixture_source(count=1)
    page = spans[0].page
    page.printed_label = printed
    page.save(update_fields=["printed_label"])
    response = api_client.post("/api/reading/citation-preview/", {"reference": raw_page(asset, spans[0])}, format="json")
    assert response.status_code == 200
    assert response.data["reference"]["quote"] == page.text
    assert response.data["source"]["printed_label"] == printed
    citations = response.data["citations"]
    for key in ["gbt7714-2025", "apa", "mla", "chicago", "harvard"]:
        if printed:
            assert printed in citations[key] and "PDF 第" not in citations[key]
        else:
            assert citations[key].endswith("（PDF 第 1 页）")
            assert "：1." not in citations[key] and "p. 1." not in citations[key]
    assert "page" not in citations["csl"]


def test_retry_request_is_idempotent_and_changed_body_conflicts(reader_user):
    _, _, spans, _ = fixture_source(count=1)
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "选材重试"})
    body = {"request_id": str(uuid4()), "expected_revision": 1, "action": "add", "references": [{"evidence_span_id": str(spans[0].id)}], "note": "本人备注"}
    first = research.change_selection(reader_user, project.id, body)
    repeated = research.change_selection(reader_user, project.id, body)
    assert first.revision == repeated.revision
    assert len(research.unpack(repeated)["selections"]) == 1
    with pytest.raises(research.ResearchConflict):
        research.change_selection(reader_user, project.id, {**body, "note": "不同内容"})


def test_duplicate_does_not_replace_old_note_and_undo_preserves_order(reader_user):
    _, _, spans, _ = fixture_source(count=2)
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "去重撤销"})
    refs = [{"evidence_span_id": str(row.id)} for row in spans]
    project = research.change_selection(reader_user, project.id, {"expected_revision": 1, "action": "add", "references": refs, "note": "原备注"})
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision, "action": "add", "references": refs, "note": "不覆盖"})
    assert research.unpack(project)["selection_notes"][str(spans[0].id)] == "原备注"
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision, "action": "remove", "reference_id": str(spans[0].id)})
    project = research.change_selection(reader_user, project.id, {"expected_revision": project.revision, "action": "undo", "reference_id": str(spans[0].id)})
    assert [row["evidence_span_id"] for row in research.unpack(project)["selections"]] == [str(row.id) for row in spans]


def test_public_range_rejects_missing_identity_and_edition_mismatch(api_client):
    _, asset, spans, _ = fixture_source(count=1)
    for body in [{"selected_text": "无来源"}, {"reference": raw_page(asset, spans[0]), "edition_id": str(uuid4())}]:
        response = api_client.post("/api/reading/citation-preview/", body, format="json")
        assert response.status_code == 400


def test_anonymous_resolve_still_checks_withdrawal():
    edition, asset, spans, _ = fixture_source(count=1)
    raw = raw_page(asset, spans[0])
    edition.state = "withdrawn"
    edition.save(update_fields=["state"])
    with pytest.raises(ValidationError):
        research.resolve_reference(raw, AnonymousUser(), strict=True)


def test_expected_owner_rejects_cookie_account_switch_before_writes(reader_user, admin_user):
    with pytest.raises(PermissionDenied):
        research.create_project(admin_user, {"expected_owner_id": reader_user.pk, "request_id": str(uuid4()), "title": "旧账户草稿"})
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "本人资料"})
    with pytest.raises(PermissionDenied):
        research.change_selection(reader_user, project.id, {"expected_owner_id": admin_user.pk, "expected_revision": 1, "action": "add", "references": []})
