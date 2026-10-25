"""Private DOCX preview contracts; written for unified acceptance, not run during development."""
import base64
import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from datetime import timedelta
from zipfile import ZipFile

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound

from reading import document_preview as preview, research
from reading.models import CitationAudit
from reading.services import encrypt_private_text
from tests.test_private_research import docx_bytes

pytestmark = pytest.mark.django_db


def audit_for(user, purpose="manuscript"):
    blob = docx_bytes()
    return CitationAudit.objects.create(user=user, purpose=purpose, content_hash=hashlib.sha256(blob).hexdigest(),
        original_ciphertext=encrypt_private_text(base64.b64encode(blob).decode()), status="completed",
        data_ciphertext=research.pack({"filename": "synthetic.docx", "filetype": "docx", "manuscript_revision": 2,
                                      "occurrences": [], "bibliography": [], "parsed": True})), blob


def command(audit, action="generate", request_id=None, revision=None):
    return {"action": action, "request_id": request_id or uuid4(), "source_generation": audit.generation,
            "expected_preview_revision": audit.preview_state.get("revision", 0) if revision is None else revision}


@pytest.fixture(autouse=True)
def enable_preview(settings, monkeypatch):
    settings.DOCX_PREVIEW_ENABLED = True
    monkeypatch.setattr(preview, "enqueue", lambda *_: None)


@pytest.mark.parametrize("purpose,path", [("manuscript", "citation-audits"), ("private_source", "citation-sources")])
def test_private_status_file_and_command_never_expand_staff_access(api_client, reader_user, admin_user, purpose, path):
    audit, _ = audit_for(reader_user, purpose)
    url = f"/api/reading/{path}/{audit.pk}/preview/"
    api_client.force_authenticate(admin_user)
    assert api_client.get(url).status_code == 404
    assert api_client.get(url + "file/?generation=1").status_code == 404
    assert api_client.post(url, command(audit), format="json").status_code == 404
    api_client.force_authenticate(reader_user)
    result = api_client.get(url)
    assert result.status_code == 200 and "no-store" in result["Cache-Control"]
    assert result.data["status"] == "not_generated" and result.data["page_count"] is None
    assert api_client.post(url + "file/", command(audit), format="json").status_code == 405


def test_preview_preserves_original_report_and_revision_and_replays_request(reader_user, monkeypatch):
    import fitz
    audit, original = audit_for(reader_user)
    unchanged = bytes(audit.data_ciphertext), audit.revision
    with fitz.open() as document:
        document.new_page()
        pdf = document.tobytes()
    metadata = {"page_count": 1, "output_hash": hashlib.sha256(pdf).hexdigest(),
                "converter_version": "synthetic-converter", "fonts_version": "a" * 64}
    monkeypatch.setattr(preview, "convert", lambda blob, digest: (pdf, metadata))
    body = command(audit)
    audit = preview.command(reader_user, audit.pk, "manuscript", body)
    preview.render_document_preview(str(audit.pk), audit.preview_state["generation"], audit.preview_state["task_id"])
    audit.refresh_from_db()
    assert preview.status(audit)["status"] == "completed"
    assert preview.document(audit, audit.preview_state["generation"]) == pdf
    assert not bytes(audit.preview_ciphertext).startswith(b"%PDF-")
    assert unchanged == (bytes(audit.data_ciphertext), audit.revision)
    from reading.citation_audit import original_document
    assert original_document(audit) == original
    repeated = preview.command(reader_user, audit.pk, "manuscript", body)
    assert repeated.preview_state == audit.preview_state
    assert preview.status(audit)["manuscript_revision"] == 2


@pytest.mark.parametrize("change", ["cancel", "generation", "delete"])
def test_late_conversion_cannot_restore_canceled_changed_or_deleted_state(reader_user, change):
    audit, _ = audit_for(reader_user)
    audit = preview.command(reader_user, audit.pk, "manuscript", command(audit))
    pk = audit.pk
    generation, task_id = audit.preview_state["generation"], audit.preview_state["task_id"]
    if change == "cancel":
        preview.command(reader_user, audit.pk, "manuscript", command(audit, "cancel"))
    elif change == "generation":
        CitationAudit.objects.filter(pk=audit.pk).update(generation=2)
    else:
        audit.delete()
    preview.finish(pk, generation, task_id, pdf=b"%PDF-synthetic", metadata={"page_count": 1})
    current = CitationAudit.objects.filter(pk=pk).first()
    if change == "delete":
        assert current is None
    else:
        assert not current.preview_ciphertext
        assert preview.status(current)["status"] == ("canceled" if change == "cancel" else "source_changed")


def test_conflict_requires_current_preview_revision_and_source_generation(reader_user):
    audit, _ = audit_for(reader_user)
    stale = command(audit, "cancel")
    preview.command(reader_user, audit.pk, "manuscript", command(audit))
    with pytest.raises(research.ResearchConflict):
        preview.command(reader_user, audit.pk, "manuscript", stale)


def test_failed_conversion_preserves_real_parsed_text_and_original(reader_user, monkeypatch):
    audit, _ = audit_for(reader_user)
    payload = bytes(audit.data_ciphertext)
    audit = preview.command(reader_user, audit.pk, "manuscript", command(audit))
    def fail(*_args):
        raise preview.PreviewError("external_content")
    monkeypatch.setattr(preview, "convert", fail)
    preview.render_document_preview(str(audit.pk), audit.preview_state["generation"], audit.preview_state["task_id"])
    audit.refresh_from_db()
    assert preview.status(audit)["status"] == "failed" and "未联网读取" in preview.status(audit)["message"]
    assert bytes(audit.data_ciphertext) == payload and audit.original_ciphertext and not audit.preview_ciphertext


def test_invalid_socket_never_falls_back_to_http_or_environment_proxy(settings):
    settings.DOCX_PREVIEW_SOCKET = "https://external.invalid/private.docx"
    with pytest.raises(preview.PreviewError):
        preview.convert(b"synthetic", "digest")


def service_module():
    spec = importlib.util.spec_from_file_location("docx_preview_converter", Path(__file__).resolve().parents[2] / "docx_preview_service" / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name,value", [
    ("word/vbaProject.bin", b"synthetic"),
    ("word/_rels/document.xml.rels", b'<Relationships><Relationship TargetMode="External" Type="image" Target="https://external.invalid/picture"/></Relationships>'),
    ("../escape.xml", b"<root/>"),
])
def test_converter_rejects_active_external_and_traversal_packages(name, value):
    module = service_module()
    package = BytesIO()
    with ZipFile(package, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr(name, value)
    with pytest.raises(module.ConversionError):
        module.validate_docx(package.getvalue())


@pytest.mark.parametrize("xml", [
    ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:fldChar w:fldCharType="begin"/>'
     '<w:instrText>DD</w:instrText><w:instrText>EAUTO external command</w:instrText><w:fldChar w:fldCharType="end"/></w:document>').encode(),
    '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE document [<!ENTITY sample "expanded">]><document>&sample;</document>'.encode("utf-16"),
])
def test_converter_rejects_fragmented_commands_and_encoded_dtd(xml):
    module = service_module()
    package = BytesIO()
    with ZipFile(package, "w") as archive:
        archive.writestr("word/document.xml", xml)
    with pytest.raises(module.ConversionError):
        module.validate_docx(package.getvalue())


def test_expired_queued_preview_does_not_invoke_converter_after_broker_recovery(reader_user, monkeypatch):
    audit, _ = audit_for(reader_user)
    audit = preview.command(reader_user, audit.pk, "manuscript", command(audit))
    state = {**audit.preview_state, "requested_at": (timezone.now() - timedelta(minutes=11)).isoformat()}
    CitationAudit.objects.filter(pk=audit.pk).update(preview_state=state)
    invoked = []
    monkeypatch.setattr(preview, "convert", lambda *_: invoked.append(True))
    preview.render_document_preview(str(audit.pk), state["generation"], state["task_id"])
    audit.refresh_from_db()
    assert not invoked and audit.preview_state["status"] == "failed"
    assert audit.preview_state["error_code"] == "conversion_timeout" and not audit.preview_ciphertext


def test_conversion_crossing_absolute_request_deadline_cannot_store_pdf(reader_user, monkeypatch):
    audit, _ = audit_for(reader_user)
    audit = preview.command(reader_user, audit.pk, "manuscript", command(audit))
    state = dict(audit.preview_state)
    def late_convert(*_):
        record = CitationAudit.objects.get(pk=audit.pk)
        record.preview_state = {**record.preview_state, "requested_at": (timezone.now() - timedelta(minutes=11)).isoformat()}
        record.save(update_fields=["preview_state"])
        return b"%PDF-late-synthetic", {"page_count": 1, "output_hash": "a" * 64}
    monkeypatch.setattr(preview, "convert", late_convert)
    preview.render_document_preview(str(audit.pk), state["generation"], state["task_id"])
    audit.refresh_from_db()
    assert audit.preview_state["status"] == "failed"
    assert audit.preview_state["error_code"] == "conversion_timeout" and not audit.preview_ciphertext


@pytest.mark.parametrize("change", ["source", "preview", "ciphertext", "owner", "delete"])
def test_document_read_rechecks_authoritative_identity_after_decrypt(reader_user, admin_user, monkeypatch, change):
    audit, _ = audit_for(reader_user)
    audit = preview.command(reader_user, audit.pk, "manuscript", command(audit))
    state = dict(audit.preview_state)
    pdf = b"%PDF-synthetic-private"
    preview.finish(audit.pk, state["generation"], state["task_id"], pdf=pdf,
                   metadata={"page_count": 1, "output_hash": hashlib.sha256(pdf).hexdigest()})
    audit.refresh_from_db()
    decrypt = preview.decrypt_private_text
    touched = False
    def racing_decrypt(value):
        nonlocal touched
        result = decrypt(value)
        if not touched and bytes(value) == bytes(audit.preview_ciphertext):
            touched = True
            query = CitationAudit.objects.filter(pk=audit.pk)
            if change == "source":
                query.update(generation=audit.generation + 1)
            elif change == "preview":
                query.update(preview_state={**audit.preview_state, "generation": state["generation"] + 1})
            elif change == "ciphertext":
                # Even a re-encryption of equal bytes belongs to another read snapshot.
                query.update(preview_ciphertext=encrypt_private_text(base64.b64encode(pdf).decode()))
            elif change == "owner":
                query.update(user=admin_user)
            else:
                query.delete()
        return result
    monkeypatch.setattr(preview, "decrypt_private_text", racing_decrypt)
    with pytest.raises((research.ResearchConflict, NotFound)):
        preview.document(audit, state["generation"])
    assert touched


def test_document_does_not_trust_a_stale_owner_filtered_snapshot(reader_user):
    audit, _ = audit_for(reader_user)
    audit = preview.command(reader_user, audit.pk, "manuscript", command(audit))
    state = dict(audit.preview_state)
    pdf = b"%PDF-synthetic"
    preview.finish(audit.pk, state["generation"], state["task_id"], pdf=pdf,
                   metadata={"page_count": 1, "output_hash": hashlib.sha256(pdf).hexdigest()})
    audit.refresh_from_db()
    CitationAudit.objects.filter(pk=audit.pk).update(generation=audit.generation + 1)
    with pytest.raises(research.ResearchConflict):
        preview.document(audit, state["generation"])


@pytest.mark.parametrize("change", [{"is_active": False}, {"token_version": 17}])
def test_preview_command_rechecks_account_after_obtaining_lock(reader_user, change):
    from django.contrib.auth import get_user_model
    from rest_framework.exceptions import PermissionDenied
    audit, _ = audit_for(reader_user)
    get_user_model().objects.filter(pk=reader_user.pk).update(**change)
    with pytest.raises(PermissionDenied):
        preview.command(reader_user, audit.pk, "manuscript", command(audit))
    audit.refresh_from_db()
    assert not audit.preview_state and not audit.preview_ciphertext


@pytest.mark.parametrize("purpose,path", [("manuscript", "citation-audits"), ("private_source", "citation-sources")])
def test_preview_routes_reject_a_different_expected_owner(api_client, reader_user, admin_user, purpose, path):
    audit, _ = audit_for(reader_user, purpose)
    api_client.force_authenticate(reader_user)
    url = f"/api/reading/{path}/{audit.pk}/preview/"
    headers = {"HTTP_X_READER_OWNER": str(admin_user.pk)}
    assert api_client.get(url, **headers).status_code == 403
    assert api_client.post(url, command(audit), format="json", **headers).status_code == 403
    assert api_client.get(url + "file/?generation=1", **headers).status_code == 403
