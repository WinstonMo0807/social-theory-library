"""PDF208–215 private source contracts; authored, not run before unified acceptance."""
from copy import deepcopy
from io import BytesIO
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Asset, Edition, EvidencePack
from reading import citation_audit, citation_sources, research
from reading.models import CitationAudit
from tests.test_citation_versions_20261018 import finish, manuscript, new_version
from tests.test_private_research import scanned_pdf_bytes
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db
QUOTE = "社会关系构成制度实践的重要条件"


def source_blob(*paragraphs):
    from docx import Document
    document = Document()
    for value in paragraphs or (QUOTE,):
        document.add_paragraph(value)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


@pytest.fixture(autouse=True)
def no_queue(monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)


def source_for(user, *, blob=None, **options):
    return finish(citation_audit.create_audit(user, SimpleUploadedFile("source.docx", blob or source_blob()),
        {"request_id": str(uuid4()), "title": "合成私人材料", **options}, purpose="private_source"))


def report_for(user, source=None, **options):
    return finish(citation_audit.create_audit(user, SimpleUploadedFile("draft.docx", manuscript()),
        {"request_id": str(uuid4()), "scope": "private_materials" if source else "public_library",
            "private_source_ids": [str(source.pk)] if source else [], **options}))


def confirm_first(user, audit, source):
    entry = research.unpack(audit)["bibliography"][0]
    return finish(citation_audit.update_audit(user, audit.pk, {"expected_revision": audit.revision,
        "action": "match_private", "entry_id": entry["id"], "source_id": str(source.pk)}))


def first_private(payload):
    return next(row for row in payload["occurrences"][0]["findings"] if row["kind"] == "private_quote")


def test_source_routes_owner_purpose_and_encrypted_storage(api_client, reader_user, admin_user):
    counts = [model.objects.count() for model in (Asset, Edition, EvidencePack)]
    api_client.force_authenticate(reader_user)
    blob = source_blob()
    response = api_client.post("/api/reading/citation-sources/", {"request_id": str(uuid4()),
        "file": SimpleUploadedFile("source.docx", blob), "scan_ocr": "false"}, format="multipart")
    assert response.status_code == 202 and "no-store" in response["Cache-Control"]
    source = finish(CitationAudit.objects.get(pk=response.data["id"]))
    assert source.purpose == "private_source" and source.file_size_bytes == len(blob)
    assert QUOTE.encode() not in bytes(source.data_ciphertext)
    assert citation_audit.original_document(source) == blob
    data = api_client.get(f"/api/reading/citation-sources/{source.pk}/").data["data"]
    assert data["segment_count"] == 1 and "text_units" not in data and "source_paragraphs" not in data
    assert api_client.get("/api/reading/citation-audits/").data["count"] == 0
    assert api_client.get("/api/reading/research-account/").data["counts"]["audits"] == 0
    assert api_client.get(f"/api/reading/citation-audits/{source.pk}/").status_code == 404
    assert api_client.get(f"/api/reading/citation-sources/{source.pk}/versions/").status_code == 404
    assert api_client.post(f"/api/reading/citation-audits/{source.pk}/versions/", {
        "request_id": str(uuid4()), "expected_revision": source.revision,
        "file": SimpleUploadedFile("new.docx", blob)}, format="multipart").status_code == 404
    assert api_client.post(f"/api/reading/citation-audits/{source.pk}/command/", {
        "action": "retry", "expected_revision": source.revision}, format="json").status_code == 404
    exported = research.research_export(reader_user)
    assert exported["audits"] == [] and len(exported["citation_sources"]) == 1
    api_client.force_authenticate(admin_user)
    for suffix in ("", "original/", "segments/", "ocr/", "export/"):
        assert api_client.get(f"/api/reading/citation-sources/{source.pk}/{suffix}").status_code == 404
    assert api_client.delete(f"/api/reading/citation-sources/{source.pk}/", {
        "expected_revision": source.revision}, format="json").status_code == 404
    assert [model.objects.count() for model in (Asset, Edition, EvidencePack)] == counts


def test_source_idempotency_shared_active_quota_and_total_storage(reader_user, monkeypatch):
    nonce, blob = str(uuid4()), source_blob()
    def upload(**extra):
        return citation_audit.create_audit(reader_user, SimpleUploadedFile("source.docx", blob),
            {"request_id": nonce, **extra}, purpose="private_source")
    first = upload()
    citation_audit.create_audit(reader_user, SimpleUploadedFile("draft.docx", manuscript()), {"request_id": str(uuid4())})
    assert upload().pk == first.pk  # Replay precedes quota checks.
    with pytest.raises(research.ResearchConflict):
        upload(title="different identity")
    with pytest.raises(research.ResearchConflict):
        citation_audit.create_audit(reader_user, SimpleUploadedFile("source.docx", blob),
            {"request_id": str(uuid4())}, purpose="private_source")
    finish(first)
    monkeypatch.setattr(citation_sources, "MAX_SOURCE_BYTES", len(blob) * 2 - 1)
    with pytest.raises(ValidationError):
        citation_audit.create_audit(reader_user, SimpleUploadedFile("source.docx", blob),
            {"request_id": str(uuid4())}, purpose="private_source")
    monkeypatch.setattr(citation_sources, "MAX_SOURCE_BYTES", 128 * 1024 * 1024)
    monkeypatch.setattr(citation_sources, "MAX_SOURCE_FILES", 1)
    with pytest.raises(ValidationError):
        citation_audit.create_audit(reader_user, SimpleUploadedFile("source.docx", blob),
            {"request_id": str(uuid4())}, purpose="private_source")
    assert CitationAudit.objects.filter(purpose="private_source").count() == 1


def test_explicit_selection_is_owner_scoped_and_can_expand_public_audit(reader_user, admin_user):
    source, other = source_for(reader_user), source_for(admin_user)
    for options in ({"scope": "private_materials"},
                    {"scope": "private_materials", "private_source_ids": [str(other.pk)]},
                    {"scope": "public_library", "private_source_ids": [str(source.pk)]}):
        with pytest.raises(ValidationError):
            citation_audit.create_audit(reader_user, SimpleUploadedFile("draft.docx", manuscript()),
                {"request_id": str(uuid4()), **options})
    audit = report_for(reader_user)
    with pytest.raises(ValidationError):
        citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": audit.revision, "action": "sources"})
    with pytest.raises(ValidationError):
        citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": audit.revision,
            "action": "match_private", "entry_id": research.unpack(audit)["bibliography"][0]["id"], "source_id": str(source.pk)})
    audit = finish(citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": audit.revision,
        "action": "sources", "private_source_ids": [str(source.pk)]}))
    assert research.unpack(audit)["scope"] == "private_materials"
    assert first_private(research.unpack(audit))["identity_status"] == "needs_review"
    with pytest.raises(ValidationError):
        citation_sources.ready_sources(reader_user, [str(audit.pk)], strict=True)
    with pytest.raises(NotFound):
        citation_audit.update_audit(admin_user, audit.pk, {"expected_revision": audit.revision,
            "action": "sources", "private_source_ids": []})


def test_exact_private_match_has_real_cross_paragraph_locator_and_no_public_reference(reader_user):
    source = source_for(reader_user, blob=source_blob("社会关系构成", "制度实践的重要条件"))
    audit = confirm_first(reader_user, report_for(reader_user, source), source)
    stored = first_private(research.unpack(audit))
    assert stored["status"] == "text_match" and stored["identity_status"] == "owner_confirmed"
    assert stored["page_status"] == "needs_review" and "references" not in stored
    raw = stored["private_references"][0]
    assert "quote" not in raw and len(raw["unit_ids"]) == 2
    reference = first_private(research.serialize_record(audit, reader_user)["data"])["private_references"][0]
    assert reference["source_status"] == "available" and reference["quote"] == "社会关系构成\n制度实践的重要条件"
    assert reference["location"]["paragraph"] == 0 and reference["location"]["pdf_page"] is None
    assert reference["original_url"] == f"/api/reading/citation-sources/{source.pk}/original/"
    forged = {**raw, "content_hash": "0" * 64}
    assert citation_sources.resolve_private_reference(forged, reader_user, [str(source.pk)])["quote"] == ""
    assert citation_sources.resolve_private_reference(raw, reader_user, [])["quote"] == ""


@pytest.mark.parametrize("action", ["match_private", "match", "link"])
def test_changed_identity_or_link_archives_decision_but_identical_choice_keeps_it(reader_user, action):
    source, alternative = source_for(reader_user), source_for(reader_user, blob=source_blob("另一个版本的合成文字，不包含原有引文"))
    audit = report_for(reader_user, source, private_source_ids=[str(source.pk), str(alternative.pk)])
    audit = confirm_first(reader_user, audit, source)
    row = research.unpack(audit)["occurrences"][0]
    audit = citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": audit.revision,
        "action": "decision", "occurrence_id": row["id"], "decision": "accepted", "note": "依据来源 A"})
    audit = confirm_first(reader_user, audit, source)
    payload = research.unpack(audit)
    assert payload["occurrences"][0]["decision"]["note"] == "依据来源 A"
    entry = payload["bibliography"][0]
    body = {"action": action, "expected_revision": audit.revision, "entry_id": entry["id"]}
    if action == "match_private":
        body["source_id"] = str(alternative.pk)
    elif action == "match":
        edition, _, _, _ = fixture_source(1)
        body["edition_id"] = str(edition.pk)
    else:
        body.update(occurrence_id=row["id"], entry_ids=[payload["bibliography"][1]["id"]])
    audit = finish(citation_audit.update_audit(reader_user, audit.pk, body))
    current = research.unpack(audit)["occurrences"][0]
    assert current["decision"] is None and current["decision_history"][-1]["note"] == "依据来源 A"
    assert current["version_change"] == "evidence_changed"
    if action == "match_private":
        assert first_private(research.unpack(audit))["status"] == "unverified"


@pytest.mark.parametrize("change", ["delete", "reparse", "remove"])
def test_source_changes_scrub_current_and_historical_quotes_without_erasing_owner_history(reader_user, change):
    source = source_for(reader_user)
    audit = confirm_first(reader_user, report_for(reader_user, source), source)
    original = citation_audit.original_document(audit)
    payload = research.unpack(audit)
    payload["parse_history"] = [deepcopy({"bibliography": payload["bibliography"], "occurrences": payload["occurrences"]})]
    row = payload["occurrences"][0]
    row["history"] = [{"findings": deepcopy(row["findings"])}]
    row["decision"] = {"value": "accepted", "note": "本人判断", "at": "2026-10-18"}
    research.save_data(audit, payload)
    if change == "delete":
        source.delete()
    elif change == "reparse":
        finish(citation_audit.update_audit(reader_user, source.pk, {"expected_revision": source.revision,
            "action": "retry"}, purpose="private_source"))
    else:
        audit = citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": audit.revision,
            "action": "sources", "private_source_ids": []})
    serialized = research.serialize_record(audit, reader_user)["data"]
    for report in [serialized, *serialized["parse_history"]]:
        occurrence = report["occurrences"][0]
        for snapshot in [occurrence, *occurrence.get("history", [])]:
            refs = [ref for finding in snapshot["findings"] for ref in finding.get("private_references", [])]
            assert refs and all(ref["source_status"] == "source_unavailable" and not ref["quote"] and ref["original_url"] is None for ref in refs)
    if change == "remove":
        assert serialized["scope"] == "public_library"
        assert serialized["occurrences"][0]["decision_history"][-1]["note"] == "本人判断"
    else:
        assert serialized["bibliography"][0]["selected_private_source_status"] == "source_unavailable"
    assert citation_audit.original_document(audit) == original


def test_private_version_reuse_and_empty_resume_targets_revalidate_source(reader_user):
    source = source_for(reader_user)
    base = confirm_first(reader_user, report_for(reader_user, source), source)
    first = research.unpack(base)["occurrences"][0]
    base = citation_audit.update_audit(reader_user, base.pk, {"expected_revision": base.revision, "action": "decision",
        "occurrence_id": first["id"], "decision": "accepted", "note": "原版判断"})
    child = finish(new_version(reader_user, base))
    payload = research.unpack(child)
    assert payload["occurrences"][0]["reused_at"] and payload["version_comparison"]["reused_occurrences"] == 1
    payload["rerun_occurrence_ids"] = []
    child.status = "failed"
    research.save_data(child, payload, fields=["status"])
    source.delete()
    child = finish(citation_audit.update_audit(reader_user, child.pk, {"expected_revision": child.revision, "action": "retry"}))
    current = research.unpack(child)
    assert current["occurrences"][0]["checked_generation"] == child.generation
    assert current["occurrences"][0]["decision"] is None and current["occurrences"][0]["decision_history"][-1]["note"] == "原版判断"
    assert current["version_comparison"]["reused_occurrences"] == 0
    assert child.status == "partial"
    # A deleted source also cannot regain authority from an immutable baseline.
    base.refresh_from_db()
    fresh = finish(new_version(reader_user, base))
    assert research.unpack(fresh)["occurrences"][0]["decision"] is None
    assert "version_baseline" not in research.serialize_record(fresh, reader_user)["data"]


def test_source_cancel_resume_stale_delete_and_original_are_preserved(api_client, reader_user):
    blob = source_blob()
    source = citation_audit.create_audit(reader_user, SimpleUploadedFile("source.docx", blob),
        {"request_id": str(uuid4())}, purpose="private_source")
    old_generation, old_task = source.generation, source.task_id
    source = citation_audit.update_audit(reader_user, source.pk, {"expected_revision": source.revision,
        "action": "cancel"}, purpose="private_source")
    citation_audit.process_audit(source.pk, old_generation, old_task)
    source.refresh_from_db()
    assert source.status == "canceled" and "text_units" not in research.unpack(source)
    old_revision = source.revision
    source = finish(citation_audit.update_audit(reader_user, source.pk, {"expected_revision": source.revision,
        "action": "retry"}, purpose="private_source"))
    api_client.force_authenticate(reader_user)
    endpoint = f"/api/reading/citation-sources/{source.pk}/"
    assert api_client.delete(endpoint, {"expected_revision": old_revision}, format="json").status_code == 409
    assert api_client.get(endpoint + "original/").content == blob
    assert api_client.delete(endpoint, {"expected_revision": source.revision}, format="json").status_code == 204
    citation_audit.process_audit(source.pk, source.generation, source.task_id)
    assert not CitationAudit.objects.filter(pk=source.pk).exists()


def test_paginated_units_keep_real_offsets_and_strip_parser_internals(reader_user, api_client):
    source = source_for(reader_user, blob=source_blob("甲" * 4500, QUOTE))
    units = research.unpack(source)["text_units"]
    api_client.force_authenticate(reader_user)
    response = api_client.get(f"/api/reading/citation-sources/{source.pk}/segments/", {"page_size": 1, "unit_id": units[1]["id"]})
    assert response.status_code == 200 and response.data["page"] == 2 and response.data["count"] == 3
    assert response.data["units"][0]["location"]["start"] == 4000
    assert "xml_node" not in response.data["units"][0]["location"]
    audit = report_for(reader_user)
    occurrence = research.unpack(audit)["occurrences"][1]
    located = api_client.get(f"/api/reading/citation-audits/{audit.pk}/manuscript/", {"page_size": 1, "occurrence_id": occurrence["id"]})
    assert located.status_code == 200 and located.data["page"] == occurrence["location"]["paragraph"] + 1
    assert "pdf_page" in located.data["units"][0]["location"] and located.data["units"][0]["location"]["pdf_page"] is None
    pending = citation_audit.update_audit(reader_user, source.pk, {"expected_revision": source.revision, "action": "retry"}, purpose="private_source")
    assert citation_sources.paginated_units(pending, {})["generation"] < pending.generation


def test_scan_consent_and_private_matching_follow_selected_checks(reader_user, monkeypatch):
    monkeypatch.setattr("reading.private_ocr.enrich_private_manuscript", lambda **_: pytest.fail("OCR requires explicit consent"))
    source = finish(citation_audit.create_audit(reader_user, SimpleUploadedFile("scan.pdf", scanned_pdf_bytes()),
        {"request_id": str(uuid4())}, purpose="private_source"))
    assert source.status == "partial" and research.unpack(source)["segment_count"] == 1
    with pytest.raises(ValidationError):
        citation_sources.ready_sources(reader_user, [str(source.pk)], strict=True)
    readable = source_for(reader_user)
    monkeypatch.setattr(citation_sources, "check_private_occurrence", lambda *_: pytest.fail("Version/page check not selected"))
    audit = report_for(reader_user, readable, checks=["citation_identification"])
    assert all(not row["findings"] for row in research.unpack(audit)["occurrences"])


def test_source_partial_ocr_retry_reuses_completed_pages(reader_user, settings, monkeypatch):
    settings.RAPIDOCR_SERVICE_URL = "http://127.0.0.1:8090"
    calls, fail = [], {"page_two": True}
    def gateway(path, **options):
        page = options["page_numbers"][0]
        calls.append(page)
        if page == 2 and fail["page_two"]:
            raise RuntimeError("synthetic page failure")
        return {"pages": [{"index": page, "width": 600, "height": 800,
            "blocks": [{"text": QUOTE, "bbox": [1, 2, 20, 30]}]}]}
    monkeypatch.setattr("reading.private_ocr._request_document_gateway", gateway)
    blob = scanned_pdf_bytes(2)
    source = finish(citation_audit.create_audit(reader_user, SimpleUploadedFile("scan.pdf", blob),
        {"request_id": str(uuid4()), "scan_ocr": True}, purpose="private_source"))
    assert source.status == "partial" and calls == [1, 2]
    assert citation_sources.ready_sources(reader_user, [str(source.pk)], strict=True)
    fail["page_two"] = False
    source = finish(citation_audit.update_audit(reader_user, source.pk, {"expected_revision": source.revision,
        "action": "retry"}, purpose="private_source"))
    assert source.status == "completed" and calls == [1, 2, 2]
    assert citation_audit.original_document(source) == blob


def test_cross_part_matches_and_unit_quota_are_rejected(reader_user, monkeypatch):
    source = source_for(reader_user)
    payload = research.unpack(source)
    payload["text_units"] = citation_sources.text_units([
        {"text": "社会关系构成", "location": {"part": "word/document.xml", "paragraph": 0}},
        {"text": "制度实践的重要条件", "location": {"part": "word/footnotes.xml", "paragraph": 0, "note_id": "1"}}])
    assert citation_sources.private_matches(QUOTE, {str(source.pk): (source, payload)}) == []
    monkeypatch.setattr(citation_sources, "MAX_TEXT_UNITS", 1)
    with pytest.raises(ValidationError):
        citation_sources.text_units([{"text": "甲" * 4001, "location": {"part": "pdf", "pdf_page": 1}}])


@pytest.mark.parametrize("gap", ["pdf", "docx"])
def test_unknown_scanned_page_or_inline_image_cannot_be_skipped_in_exact_match(reader_user, gap):
    source = source_for(reader_user)
    part = "pdf" if gap == "pdf" else "word/document.xml"
    rows = [
        {"text": "社会关系构成", "location": {"part": part, "pdf_page": 1, "paragraph": 0}},
        {"text": "", "needs_ocr": gap == "pdf", "embedded_images": [{"id": "synthetic"}] if gap == "docx" else [],
            "location": {"part": part, "pdf_page": 2, "paragraph": 1}},
        {"text": "制度实践的重要条件", "location": {"part": part, "pdf_page": 3, "paragraph": 2}}]
    payload = {"text_units": citation_sources.text_units(rows)}
    assert payload["text_units"][1]["coverage_status"] == "unread_content"
    assert citation_sources.private_matches(QUOTE, {str(source.pk): (source, payload)}) == []
    # An actually known blank native unit may be crossed; an unrecognized scan may not.
    rows[1].update(needs_ocr=False, embedded_images=[])
    payload = {"text_units": citation_sources.text_units(rows)}
    matches = citation_sources.private_matches(QUOTE, {str(source.pk): (source, payload)})
    assert matches and len(matches[0]["unit_ids"]) == 3
