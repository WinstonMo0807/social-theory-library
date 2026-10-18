"""Citation upload/report contracts; authored for the final unified acceptance run."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from reading import citation_audit, research
from reading.models import CitationAudit
from tests.test_discovery_sessions_v308 import fixture_source
from tests.test_private_research import docx_bytes, scanned_pdf_bytes

pytestmark = pytest.mark.django_db


def stored_audit(user, **extra):
    rows = [{"id": str(uuid4()), "raw": "[1]", "entry_ids": [], "findings": [], "decision": None}
            for _ in range(2)]
    payload = {"scope": "public_library", "checks": list(citation_audit.DEFAULT_CHECKS),
        "bibliography": [], "occurrences": rows, "warnings": [], "parsed": True, "stage": "report", **extra}
    return CitationAudit.objects.create(user=user, status="partial", completed_units=2, total_units=2,
        data_ciphertext=research.pack(payload)), rows


def test_capabilities_are_private_configuration_eligibility(api_client, reader_user, settings, monkeypatch):
    settings.PADDLEOCR_SERVICE_URL = "https://unapproved.example"
    monkeypatch.setattr("reading.local_analysis.current_ai_configuration", lambda *_: SimpleNamespace(enabled=False))
    assert api_client.get("/api/reading/citation-audits/capabilities/").status_code in {401, 403}
    api_client.force_authenticate(reader_user)
    response = api_client.get("/api/reading/citation-audits/capabilities/")
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    assert response.data["default_checks"] == list(citation_audit.DEFAULT_CHECKS)
    assert response.data["ocr"]["available"] is False
    assert response.data["analysis"]["available"] is False
    assert response.data["analysis"]["service_verified"] is False
    assert next(row for row in response.data["scopes"] if row["id"] == "private_materials")["available"] is True
    assert response.data["private_sources"]["max_selected"] == 4


def test_multipart_check_selection_is_enforced_and_bound_to_request(api_client, reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    api_client.force_authenticate(reader_user)
    nonce = str(uuid4())
    blob = docx_bytes()
    def upload(checks):
        return api_client.post("/api/reading/citation-audits/", {"request_id": nonce,
            "file": SimpleUploadedFile("draft.docx", blob), "scope": "public_library", "checks": checks}, format="multipart")
    response = upload(["citation_identification"])
    assert response.status_code == 202
    audit = CitationAudit.objects.get(pk=response.data["id"])
    assert response.data["data"]["scope"] == "public_library"
    assert research.unpack(audit)["checks"] == ["citation_identification"]
    assert upload(list(citation_audit.DEFAULT_CHECKS)).status_code == 409
    monkeypatch.setattr(citation_audit, "match_bibliography", lambda *_: pytest.fail("Identity scan was not selected"))
    monkeypatch.setattr(citation_audit, "check_occurrence", lambda *_: pytest.fail("Version/page check was not selected"))
    citation_audit.process_audit(audit.pk, audit.generation, audit.task_id)
    audit.refresh_from_db()
    payload = research.unpack(audit)
    assert all(row["identity_status"] == "not_requested" for row in payload["bibliography"])
    assert all(row["findings"] == [] for row in payload["occurrences"])
    assert payload["manuscript_stats"]["file_size_bytes"] > 0
    assert payload["manuscript_stats"]["pdf_page_count"] is None


def test_scope_dependencies_and_default_scan_consent(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    for options in ({"checks": ["version_page"]}, {"scope": "private_materials"}, {"checks": ["deep_analysis"]}):
        with pytest.raises(ValidationError):
            citation_audit.create_audit(reader_user, SimpleUploadedFile("draft.docx", docx_bytes()),
                {"request_id": str(uuid4()), **options})
    blob = scanned_pdf_bytes()
    audit = citation_audit.create_audit(reader_user, SimpleUploadedFile("scan.pdf", blob), {"request_id": str(uuid4())})
    monkeypatch.setattr("reading.private_ocr.enrich_private_manuscript", lambda **_: pytest.fail("OCR needs explicit consent"))
    citation_audit.process_audit(audit.pk, audit.generation, audit.task_id)
    audit.refresh_from_db()
    payload = research.unpack(audit)
    assert audit.status == "partial"
    assert "scan_ocr_not_requested" in {row["code"] for row in payload["warnings"]}
    assert payload["manuscript_stats"]["pdf_page_count"] == 1
    assert citation_audit.original_document(audit) == blob


def test_batch_decisions_are_atomic_owner_scoped_and_keep_originals(reader_user, admin_user):
    audit, rows = stored_audit(reader_user)
    ids = [row["id"] for row in rows]
    with pytest.raises(NotFound):
        citation_audit.update_audit(admin_user, audit.pk, {"expected_revision": 1,
            "action": "decision", "occurrence_ids": ids, "decision": "accepted"})
    with pytest.raises(NotFound):
        citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": 1,
            "action": "decision", "occurrence_ids": [ids[0], str(uuid4())], "decision": "accepted"})
    audit.refresh_from_db()
    assert audit.revision == 1 and all(row["decision"] is None for row in research.unpack(audit)["occurrences"])
    audit = citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": 1,
        "action": "decision", "occurrence_ids": ids, "decision": "needs_review", "note": "本人复核"})
    audit = citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": audit.revision,
        "action": "decision", "occurrence_id": ids[0], "decision": "corrected", "corrected_text": "本人另存的校正文案"})
    first = research.unpack(audit)["occurrences"][0]
    assert first["raw"] == "[1]" and first["decision"]["corrected_text"] == "本人另存的校正文案"
    assert first["decision_history"][0]["value"] == "needs_review"
    with pytest.raises(research.ResearchConflict):
        citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": 1,
            "action": "decision", "occurrence_ids": ids, "decision": "ignored"})


def test_retry_starts_fresh_progress_without_discarding_decisions(reader_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    audit, rows = stored_audit(reader_user)
    audit = citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": 1, "action": "decision",
        "occurrence_id": rows[0]["id"], "decision": "accepted"})
    audit = citation_audit.update_audit(reader_user, audit.pk, {"expected_revision": audit.revision,
        "action": "retry", "occurrence_ids": [rows[0]["id"]]})
    assert audit.status == "queued" and audit.completed_units == 0 and audit.total_units == 1
    assert research.unpack(audit)["stage"] == "queued"
    assert research.unpack(audit)["occurrences"][0]["decision"]["value"] == "accepted"


def test_active_job_ceiling_preserves_idempotency_and_owner_boundary(reader_user, admin_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: None)
    blob, nonce = docx_bytes(), str(uuid4())
    def upload(user, request_id):
        return citation_audit.create_audit(user, SimpleUploadedFile("draft.docx", blob), {"request_id": request_id})
    first = upload(reader_user, nonce)
    upload(reader_user, str(uuid4()))
    assert upload(reader_user, nonce).pk == first.pk
    with pytest.raises(research.ResearchConflict):
        upload(reader_user, str(uuid4()))
    assert upload(admin_user, str(uuid4())).user_id == admin_user.pk


def test_bibliography_and_evidence_are_revalidated_and_revision_pinned(reader_user):
    edition, _, spans, _ = fixture_source(1)
    ref = research.compact_reference(research.resolve_reference({"evidence_span_id": str(spans[0].pk)}, reader_user))
    audit, _ = stored_audit(reader_user, bibliography=[{"id": str(uuid4()), "raw": "参考文献原文", "candidates": [],
        "identity_status": "user_confirmed", "selected_edition_id": str(edition.pk)}],
        occurrences=[{"id": str(uuid4()), "findings": [{"kind": "direct_quote", "status": "text_match", "references": [ref]}]}])
    serialized = research.serialize_record(audit, reader_user)
    candidate = serialized["data"]["bibliography"][0]["candidates"][0]
    assert candidate["source_status"] == "available" and candidate["title"] == edition.work.title
    reference = serialized["data"]["occurrences"][0]["findings"][0]["references"][0]
    assert f"revision={spans[0].document_revision_id}" in reference["reader_url"]
    edition.state = "withdrawn"
    edition.save(update_fields=["state"])
    withdrawn = research.serialize_record(audit, reader_user)["data"]
    assert withdrawn["bibliography"][0]["candidates"][0]["source_status"] == "source_unavailable"
    assert withdrawn["bibliography"][0]["candidates"][0]["citation"] == ""
    assert withdrawn["occurrences"][0]["findings"][0]["status"] == "unverified"
    assert research.unpack(audit)["bibliography"][0]["identity_status"] == "user_confirmed"


def test_reparse_keeps_unmatched_previous_decisions_in_history():
    old = {"bibliography": [], "occurrences": [{"id": "old", "raw": "old OCR text", "location": {"pdf_page": 1},
        "entry_ids": [], "decision": {"value": "corrected", "corrected_text": "本人校正"}}]}
    parsed = {"bibliography": [], "occurrences": [{"id": "new", "raw": "changed OCR text",
        "location": {"pdf_page": 1}, "entry_ids": [], "decision": None}]}
    original = deepcopy(old["occurrences"])
    citation_audit._preserve_parser_decisions(parsed, old)
    assert parsed["occurrences"][0]["decision"] is None
    assert old["parse_history"][0]["occurrences"] == original


def test_recovery_waits_for_owner_capacity_without_consuming_retry_budget(reader_user, monkeypatch, django_capture_on_commit_callbacks):
    from reading.tasks import recover_private_research_tasks
    queued = [CitationAudit.objects.create(user=reader_user, status="queued", data_ciphertext=research.pack({})) for _ in range(2)]
    failed = CitationAudit.objects.create(user=reader_user, status="failed", error_code="queue_unavailable", task_id="old-lease",
        data_ciphertext=research.pack({"parsed": True, "occurrences": [], "recovery_attempts": 1}))
    stale_time = timezone.now() - timedelta(minutes=40)
    CitationAudit.objects.filter(pk=failed.pk).update(updated_at=stale_time)
    calls = []
    monkeypatch.setattr("reading.tasks.enqueue_citation_audit", lambda *args: calls.append(args))
    with django_capture_on_commit_callbacks(execute=True):
        result = recover_private_research_tasks()
    failed.refresh_from_db()
    assert result["audits"] == 0 and calls == []
    assert (failed.status, failed.generation, failed.task_id, failed.revision) == ("failed", 1, "old-lease", 1)
    assert failed.updated_at == stale_time and research.unpack(failed)["recovery_attempts"] == 1
    citation_audit.update_audit(reader_user, queued[0].pk, {"expected_revision": 1, "action": "cancel"})
    with django_capture_on_commit_callbacks(execute=True):
        resumed = recover_private_research_tasks()
    failed.refresh_from_db()
    assert resumed["audits"] == 1 and failed.status == "queued" and failed.generation == 2
    assert calls == [(failed.pk, 2, failed.task_id)]
    assert research.unpack(failed)["recovery_attempts"] == 2
    assert CitationAudit.objects.filter(user=reader_user, status__in=research.ACTIVE).count() == 2


def test_reparse_keeps_confirmed_bibliography_when_no_occurrences_were_found():
    previous = {"bibliography": [{"id": "old-entry", "raw": "原识别书目", "location": {"pdf_page": 2},
        "identity_status": "user_confirmed", "selected_edition_id": "owner-choice", "history": [{"selected_edition_id": None}]}],
        "occurrences": []}
    parsed = {"bibliography": [{"id": "new-entry", "raw": "重识别书目", "location": {"pdf_page": 2},
        "identity_status": "pending", "selected_edition_id": None}], "occurrences": []}
    original = deepcopy(previous["bibliography"])
    citation_audit._preserve_parser_decisions(parsed, previous)
    assert previous["parse_history"][0]["bibliography"] == original
    assert parsed["bibliography"][0]["selected_edition_id"] is None
    previous["bibliography"][0]["history"].append({"selected_edition_id": "later-change"})
    assert previous["parse_history"][0]["bibliography"] == original


def test_reparse_inherited_history_and_snapshots_are_independent():
    previous = {"bibliography": [{"id": "entry", "raw": "书目", "location": {"pdf_page": 2},
        "identity_status": "user_confirmed", "selected_edition_id": "edition", "history": [], "candidates": [{"title": "候选"}]}],
        "occurrences": [{"id": "occurrence", "raw": "[1]", "location": {"pdf_page": 1}, "entry_ids": ["entry"],
            "decision": {"value": "accepted"}, "decision_history": [], "findings": [], "history": [],
            "entry_link": {"entry_ids": ["entry"], "status": "confirmed"}, "link_history": []}]}
    parsed = deepcopy(previous)
    parsed["bibliography"][0]["id"] = "new-entry"
    parsed["occurrences"][0].update(id="new-occurrence", entry_ids=["new-entry"])
    original = deepcopy(previous)
    citation_audit._preserve_parser_decisions(parsed, previous)
    parsed["bibliography"][0]["history"].append({"selected_edition_id": "changed"})
    parsed["bibliography"][0]["candidates"][0]["title"] = "改变的候选"
    parsed["occurrences"][0]["history"].append({"generation": 2})
    parsed["occurrences"][0]["decision"]["value"] = "corrected"
    parsed["occurrences"][0]["entry_link"]["entry_ids"].clear()
    assert previous["bibliography"] == original["bibliography"]
    assert previous["occurrences"] == original["occurrences"]
    assert previous["parse_history"][0]["bibliography"] == original["bibliography"]
    assert previous["parse_history"][0]["occurrences"] == original["occurrences"]
