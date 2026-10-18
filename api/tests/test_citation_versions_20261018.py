"""PDF212 version contracts; authored for the later unified acceptance run."""
from copy import deepcopy
from io import BytesIO
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import NotFound

from reading import citation_audit, research
from reading.models import CitationAudit
from tests.test_discovery_sessions_v308 import fixture_source
from tests.test_private_research import scanned_pdf_bytes

pytestmark = pytest.mark.django_db


def manuscript(*, introduction=False, first="社会关系构成制度实践的重要条件", year="2020", duplicate=False):
    from docx import Document
    document = Document()
    if introduction:
        document.add_paragraph("新加入的导言不改变后文引文。")
    paragraph = f'这项论证认为，“{first}”。[1]'
    document.add_paragraph(paragraph)
    document.add_paragraph(paragraph if duplicate else '另一处论证指出，“不同的社会条件形成不同的制度安排”。[2]')
    document.add_paragraph("参考文献")
    document.add_paragraph(f"[1] 作者甲. 制度实践研究. {year}.")
    document.add_paragraph("[2] 作者乙. 社会条件研究. 2021.")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def finish(audit):
    citation_audit.process_audit(audit.pk, audit.generation, audit.task_id)
    audit.refresh_from_db()
    return audit


def base_report(user, monkeypatch, blob=None, *, checks=None):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    audit = citation_audit.create_audit(user, SimpleUploadedFile("v1.docx", blob or manuscript()),
        {"request_id": str(uuid4()), "checks": checks or ["citation_identification"]})
    finish(audit)
    return citation_audit.update_audit(user, audit.pk, {"expected_revision": audit.revision, "action": "decision",
        "occurrence_ids": [row["id"] for row in research.unpack(audit)["occurrences"]], "decision": "accepted", "note": "本人旧版本判断"})


def new_version(user, base, blob=None, **options):
    return citation_audit.create_audit(user, SimpleUploadedFile("v2.docx", blob or manuscript(introduction=True)),
        {"request_id": str(uuid4()), "expected_revision": base.revision, **options}, parent_id=base.pk)


def test_new_file_has_independent_original_and_reuses_only_unique_unchanged_citations(reader_user, monkeypatch):
    original, replacement = manuscript(), manuscript(introduction=True)
    base = base_report(reader_user, monkeypatch, original)
    previous = deepcopy(research.unpack(base))
    child = finish(new_version(reader_user, base, replacement))
    result = research.unpack(child)
    assert child.project_id == base.project_id and child.pk != base.pk
    assert citation_audit.original_document(base) == original
    assert citation_audit.original_document(child) == replacement
    assert result["version_lineage"]["parent_revision"] == base.revision
    assert result["manuscript_revision"] == 2
    assert result["version_comparison"]["reused_occurrences"] == 2
    assert result["version_comparison"]["rechecked_occurrences"] == 0
    assert child.total_units == 0
    for old, current in zip(previous["occurrences"], result["occurrences"]):
        assert current["id"] != old["id"]
        assert current["inherited_from"] == {"audit_id": str(base.pk), "occurrence_id": old["id"]}
        assert current["location"]["paragraph"] == old["location"]["paragraph"] + 1
        assert current["decision"] == old["decision"]
    base.refresh_from_db()
    assert research.unpack(base)["occurrences"] == previous["occurrences"]
    assert research.unpack(base)["bibliography"] == previous["bibliography"]


def test_bibliography_edit_rechecks_its_citation_without_inheriting_its_decision(reader_user, monkeypatch):
    base = base_report(reader_user, monkeypatch)
    child = finish(new_version(reader_user, base, manuscript(year="2024")))
    result = research.unpack(child)
    changed, unchanged = result["occurrences"]
    assert changed["version_change"] == "bibliography_changed" and changed["decision"] is None
    assert unchanged["version_change"] == "unchanged" and unchanged["decision"]["value"] == "accepted"
    assert result["version_comparison"]["reused_occurrences"] == 1
    assert result["version_comparison"]["rechecked_occurrences"] == 1
    assert result["version_comparison"]["changed_bibliography_entries"] == 2  # removed line + replacement line


@pytest.mark.parametrize("duplicate", [False, True])
def test_changed_context_or_duplicate_positions_never_inherit_manual_decisions(reader_user, monkeypatch, duplicate):
    base = base_report(reader_user, monkeypatch, manuscript(duplicate=duplicate))
    blob = manuscript(duplicate=True) if duplicate else manuscript(first="新的语境改变了这里对制度实践的论述")
    child = finish(new_version(reader_user, base, blob))
    result = research.unpack(child)
    assert result["occurrences"][0]["decision"] is None
    if duplicate:
        assert result["version_comparison"]["ambiguous_occurrences"] == 2
        assert result["version_comparison"]["reused_occurrences"] == 0
        assert all(row["decision"] is None for row in result["occurrences"])
    else:
        assert result["version_comparison"]["added_occurrences"] == 1
        assert result["version_comparison"]["removed_occurrences"] == 1


def test_explicit_full_check_preserves_decisions_but_checks_all_positions(reader_user, monkeypatch):
    base = base_report(reader_user, monkeypatch)
    child = finish(new_version(reader_user, base, check_changed_only=False))
    result = research.unpack(child)
    assert result["version_comparison"]["changed_occurrences"] == 0
    assert result["version_comparison"]["reused_occurrences"] == 0
    assert result["version_comparison"]["rechecked_occurrences"] == child.total_units == 2
    assert all(row["decision"]["value"] == "accepted" and row["checked_generation"] == child.generation for row in result["occurrences"])


def test_upload_replay_precedes_stale_revision_and_quota_and_rejects_different_file(reader_user, admin_user, monkeypatch):
    base = base_report(reader_user, monkeypatch)
    nonce, revision, blob = str(uuid4()), base.revision, manuscript(introduction=True)
    child = new_version(reader_user, base, blob, request_id=nonce)
    citation_audit.create_audit(reader_user, SimpleUploadedFile("other.docx", blob), {"request_id": str(uuid4())})
    assert new_version(reader_user, base, blob, request_id=nonce).pk == child.pk
    assert CitationAudit.objects.filter(user=reader_user, status__in=research.ACTIVE).count() == 2
    with pytest.raises(research.ResearchConflict):
        new_version(reader_user, base, manuscript(year="2025"), request_id=nonce)
    with pytest.raises(research.ResearchConflict):
        new_version(reader_user, base, blob, request_id=nonce, check_changed_only=False)
    with pytest.raises(research.ResearchConflict):
        new_version(reader_user, base, blob, expected_revision=revision)
    base.refresh_from_db()
    with pytest.raises(research.ResearchConflict):
        new_version(reader_user, base, blob)
    with pytest.raises(NotFound):
        new_version(admin_user, base, blob)


def test_multipart_versions_are_owner_only_and_hide_internal_baseline(api_client, reader_user, admin_user, monkeypatch):
    base = base_report(reader_user, monkeypatch)
    api_client.force_authenticate(reader_user)
    response = api_client.post(f"/api/reading/citation-audits/{base.id}/versions/", {
        "file": SimpleUploadedFile("new.docx", manuscript()), "request_id": str(uuid4()),
        "expected_revision": str(base.revision), "check_changed_only": "true"}, format="multipart")
    assert response.status_code == 202 and "no-store" in response["Cache-Control"]
    child_id = response.data["id"]
    assert "version_baseline" not in response.data["data"]
    for endpoint in (f"/api/reading/citation-audits/{child_id}/", f"/api/reading/citation-audits/{child_id}/export/"):
        exported = api_client.get(endpoint)
        assert "version_baseline" not in exported.data["data"]
    listing = api_client.get(f"/api/reading/citation-audits/{base.id}/versions/")
    assert {row["id"] for row in listing.data["versions"]} == {str(base.id), child_id}
    assert "version_children" not in api_client.get(f"/api/reading/citation-audits/{base.id}/").data["data"]
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/citation-audits/{base.id}/versions/").status_code == 404
    assert api_client.post(f"/api/reading/citation-audits/{base.id}/versions/", {
        "file": SimpleUploadedFile("private.docx", manuscript()), "request_id": str(uuid4()),
        "expected_revision": 1, "check_changed_only": "true"}, format="multipart").status_code == 404


def test_baseline_is_immutable_when_owner_changes_parent_and_child_is_canceled(reader_user, monkeypatch):
    base = base_report(reader_user, monkeypatch)
    child = new_version(reader_user, base)
    base.refresh_from_db()
    old_row = research.unpack(base)["occurrences"][0]
    citation_audit.update_audit(reader_user, base.pk, {"expected_revision": base.revision, "action": "decision",
        "occurrence_id": old_row["id"], "decision": "ignored"})
    child = citation_audit.update_audit(reader_user, child.pk, {"expected_revision": child.revision, "action": "cancel"})
    child = citation_audit.update_audit(reader_user, child.pk, {"expected_revision": child.revision, "action": "retry"})
    finish(child)
    assert research.unpack(child)["occurrences"][0]["decision"]["value"] == "accepted"
    assert research.unpack(child)["version_lineage"]["parent_audit_id"] == str(base.pk)


def test_source_withdrawal_forces_recheck_and_does_not_transfer_old_confirmation(reader_user, monkeypatch):
    edition, _, spans, _ = fixture_source(1)
    blob = manuscript(first=spans[0].original_text)
    base = base_report(reader_user, monkeypatch, blob, checks=list(citation_audit.DEFAULT_CHECKS))
    first_entry = research.unpack(base)["bibliography"][0]
    base = citation_audit.update_audit(reader_user, base.pk, {"expected_revision": base.revision, "action": "match",
        "entry_id": first_entry["id"], "edition_id": str(edition.pk)})
    finish(base)
    first = research.unpack(base)["occurrences"][0]
    assert first["findings"][0]["status"] == "text_match"
    edition.state = "withdrawn"
    edition.save(update_fields=["state"])
    child = finish(new_version(reader_user, base, blob))
    current = research.unpack(child)["occurrences"][0]
    assert current["decision"] is None and current["version_change"] == "evidence_changed"
    assert research.unpack(child)["version_comparison"]["rechecked_occurrences"] == 2
    public_result = research.serialize_record(child, reader_user)["data"]
    assert "version_baseline" not in public_result
    assert all(not finding.get("references") for finding in public_result["occurrences"][0]["findings"])


def test_ocr_chunk_resume_then_reparse_keeps_history_without_reusing_changed_context(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    monkeypatch.setattr(citation_audit, "audit_capabilities", lambda: {"ocr": {"available": True}})
    state = {"mode": "base"}
    def synthetic_ocr(**kwargs):
        mode = state["mode"]
        units = kwargs["cache"]
        units["synthetic-page"] = {"status": "failed" if mode == "partial" else "completed", "generation": kwargs["generation"]}
        assert kwargs["checkpoint"](units, 1, 1)
        wording = "识别后的新语境改变了这段引文" if mode == "improved" else "这是一段明确来自合成夹具的引文"
        rows = [{"text": f'“{wording}”。[1]\n参考文献\n[1] 合成书目. 2020.',
            "location": {"part": "pdf", "pdf_page": 1, "paragraph": None}, "fields": [], "note_refs": []}]
        return rows, ([{"code": "ocr_failed", "message": "合成局部失败"}] if mode == "partial" else []), mode == "chunk"
    monkeypatch.setattr("reading.private_ocr.enrich_private_manuscript", synthetic_ocr)
    blob = scanned_pdf_bytes()
    base = citation_audit.create_audit(reader_user, SimpleUploadedFile("v1.pdf", blob),
        {"request_id": str(uuid4()), "checks": ["citation_identification", "scan_ocr"]})
    finish(base)
    state["mode"] = "chunk"
    child = citation_audit.create_audit(reader_user, SimpleUploadedFile("v2.pdf", blob),
        {"request_id": str(uuid4()), "expected_revision": base.revision}, parent_id=base.pk)
    finish(child)
    assert child.status == "queued" and research.unpack(child)["version_comparison"]["status"] == "pending"
    state["mode"] = "partial"
    finish(child)
    row = research.unpack(child)["occurrences"][0]
    child = citation_audit.update_audit(reader_user, child.pk, {"expected_revision": child.revision, "action": "decision",
        "occurrence_id": row["id"], "decision": "corrected", "corrected_text": "当前版本本人另存的校正"})
    child = citation_audit.update_audit(reader_user, child.pk, {"expected_revision": child.revision, "action": "retry"})
    state["mode"] = "improved"
    finish(child)
    result = research.unpack(child)
    assert result["occurrences"][0]["decision"] is None
    assert result["parse_history"][-1]["occurrences"][0]["decision"]["corrected_text"] == "当前版本本人另存的校正"
    assert result["version_comparison"]["rechecked_occurrences"] == 1
    assert citation_audit.original_document(child) == blob


def test_removed_intermediate_version_does_not_recreate_private_record(reader_user, monkeypatch):
    base = base_report(reader_user, monkeypatch)
    child = finish(new_version(reader_user, base))
    grandchild = new_version(reader_user, child)
    child_id = child.pk
    child.delete()
    finish(grandchild)
    assert not CitationAudit.objects.filter(pk=child_id).exists()
    versions = citation_audit.audit_versions(grandchild, reader_user)["versions"]
    assert {row["id"] for row in versions} == {str(base.pk), str(grandchild.pk)}
    assert research.unpack(grandchild)["version_comparison"]["reused_occurrences"] == 2


def test_reparse_relocated_unchanged_text_keeps_current_version_decision(reader_user, monkeypatch):
    base = base_report(reader_user, monkeypatch)
    child = finish(new_version(reader_user, base))
    row = research.unpack(child)["occurrences"][0]
    child = citation_audit.update_audit(reader_user, child.pk, {"expected_revision": child.revision, "action": "decision",
        "occurrence_id": row["id"], "decision": "ignored", "note": "本版重新决定，不接受父版判断"})
    previous = research.unpack(child)
    parsed = citation_audit.parse_manuscript(manuscript(introduction=True), "docx")
    for item in parsed["occurrences"]:
        item["location"]["paragraph"] += 3
    citation_audit._preserve_parser_decisions(parsed, previous)
    citation_audit._compare_version(parsed, previous, reader_user, child.generation + 1)
    assert parsed["occurrences"][0]["id"] == row["id"]
    assert parsed["occurrences"][0]["decision"]["value"] == "ignored"
    assert parsed["occurrences"][0]["decision_history"][0]["value"] == "accepted"


def test_retry_revalidates_reused_sources_before_using_empty_resume_targets(reader_user, monkeypatch):
    edition, _, spans, _ = fixture_source(1)
    blob = manuscript(first=spans[0].original_text)
    base = base_report(reader_user, monkeypatch, blob, checks=list(citation_audit.DEFAULT_CHECKS))
    entry = research.unpack(base)["bibliography"][0]
    base = citation_audit.update_audit(reader_user, base.pk, {"expected_revision": base.revision, "action": "match",
        "entry_id": entry["id"], "edition_id": str(edition.pk)})
    finish(base)
    child = finish(new_version(reader_user, base, blob))
    previous = research.unpack(child)
    reused = previous["occurrences"][0]
    assert reused.get("reused_at") and reused["decision"]["value"] == "accepted"
    # A lost worker lease after the comparison has no remaining explicit targets.
    previous["rerun_occurrence_ids"] = []
    child.status = "failed"
    research.save_data(child, previous, fields=["status"])
    edition.state = "withdrawn"
    edition.save(update_fields=["state"])
    child = citation_audit.update_audit(reader_user, child.pk, {"expected_revision": child.revision, "action": "retry"})
    assert research.unpack(child)["rerun_occurrence_ids"] == []
    finish(child)
    result = research.unpack(child)
    current = result["occurrences"][0]
    assert current["version_change"] == "evidence_changed" and current["decision"] is None
    assert current["decision_history"][-1]["value"] == "accepted"
    assert current["checked_generation"] == child.generation and not current.get("reused_at")
    assert current["findings"][0]["status"] == "unverified" and child.status == "partial"
    assert result["version_comparison"]["reused_occurrences"] == 0


def test_surviving_other_page_match_does_not_keep_withdrawn_page_claim(reader_user):
    _, _, spans, _ = fixture_source(2)
    for index, span in enumerate(spans, start=10):
        span.printed_page_label = str(index)
        span.save(update_fields=["printed_page_label"])
    refs = [research.compact_reference(research.resolve_reference({"evidence_span_id": str(span.pk)}, reader_user)) for span in spans]
    audit = CitationAudit.objects.create(user=reader_user, status="completed", data_ciphertext=research.pack({
        "bibliography": [], "occurrences": [{"id": str(uuid4()), "findings": [{"kind": "direct_quote", "status": "text_match",
            "references": refs, "claimed_printed_label": "10", "page_status": "matched"}]}]}))
    spans[0].is_stale = True
    spans[0].save(update_fields=["is_stale"])
    finding = research.serialize_record(audit, reader_user)["data"]["occurrences"][0]["findings"][0]
    assert finding["status"] == "text_match" and finding["page_status"] == "needs_review"
    assert [ref["source_status"] for ref in finding["references"]] == ["source_unavailable", "available"]
