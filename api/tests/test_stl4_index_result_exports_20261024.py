"""Deferred acceptance: index export provenance, readiness and current access."""
import json

import pytest
from django.utils import timezone

from catalog.discovery_index_models import DiscoverySourceState
from ingestion.models import ProcessingJob
from .test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def index_job():
    edition, asset, spans, documents = fixture_source(3)
    job = ProcessingJob.objects.create(job_type="discovery_index", status="failed", edition=edition, asset=asset,
        stats={"action": "source", "source_type": "edition", "source_id": str(edition.pk),
            "generation_id": str(documents[0].generation_id), "source_revision": documents[0].source_revision})
    state = DiscoverySourceState.objects.create(generation_id=documents[0].generation_id,
        source_type="edition", source_id=edition.pk, job=job)
    for span, doc in zip(spans, documents):
        doc.indexed_at = timezone.now()
        doc.payload = {**doc.payload, "unit_id": str(span.pk), "private_note": "must never be exported"}
        doc.save(update_fields=["indexed_at", "payload", "updated_at"])
    documents[1].vector_ready = False
    documents[1].save(update_fields=["vector_ready", "updated_at"])
    return job, state, asset, documents


def test_only_confirmed_original_fragments_are_exported(api_client, admin_user):
    job, _, _, docs = index_job()
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    path = f"/api/ingestion/processing-workspace/results/{job.pk}/"
    manifest = api_client.get(path, {"page_to": 2}, **headers)
    assert manifest.status_code == 200 and manifest.data["count"] == 1
    assert manifest.data["total_recorded"] == 2 and manifest.data["kind"] == "discovery"
    response = api_client.get(path, {"page_to": 2, "download": "jsonl", "expected_version": manifest.data["version"]}, **headers)
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    content = b"".join(response.streaming_content).decode()
    rows = [json.loads(line) for line in content.splitlines()]
    assert len(rows) == 2 and rows[1]["id"] == str(docs[0].pk) and rows[1]["text"] == docs[0].text
    assert rows[1]["offset_origin"] == "source_unit" and "private_note" not in content
    docs[0].delete()
    assert api_client.get(path, {"page_to": 2, "download": "txt", "expected_version": manifest.data["version"]}, **headers).status_code == 409


def test_withdrawal_and_job_replacement_block_saved_index_export(api_client, admin_user):
    job, state, asset, _ = index_job()
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    path = f"/api/ingestion/processing-workspace/results/{job.pk}/"
    assert api_client.get(path, HTTP_X_EDITOR_OWNER="another-account").status_code == 403
    state.job = None; state.save(update_fields=["job", "updated_at"])
    assert api_client.get(path, **headers).status_code == 409
    state.job = job; state.save(update_fields=["job", "updated_at"])
    asset.access_status = "private"; asset.save(update_fields=["access_status", "updated_at"])
    assert api_client.get(path, **headers).status_code == 403


def test_access_is_checked_again_after_spooling(api_client, admin_user, monkeypatch):
    from ingestion import processing_result_views as views
    job, _, asset, _ = index_job()
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    path = f"/api/ingestion/processing-workspace/results/{job.pk}/"
    manifest = api_client.get(path, **headers).data
    original = views.export_file
    files = []
    def withdraw_after_export(*args):
        output = original(*args); files.append(output)
        asset.access_status = "private"; asset.save(update_fields=["access_status", "updated_at"])
        return output
    monkeypatch.setattr(views, "export_file", withdraw_after_export)
    response = api_client.get(path, {"download": "txt", "expected_version": manifest["version"]}, **headers)
    assert response.status_code == 403 and files and files[0].closed


def test_revoked_session_cannot_receive_prepared_export(api_client, admin_user, monkeypatch):
    from ingestion import processing_result_views as views
    job, _, _, _ = index_job()
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    path = f"/api/ingestion/processing-workspace/results/{job.pk}/"
    manifest = api_client.get(path, **headers).data
    original = views.export_file
    files = []
    def revoke_after_export(*args):
        output = original(*args); files.append(output)
        type(admin_user).objects.filter(pk=admin_user.pk).update(token_version=admin_user.token_version + 1)
        return output
    monkeypatch.setattr(views, "export_file", revoke_after_export)
    response = api_client.get(path, {"download": "jsonl", "expected_version": manifest["version"]}, **headers)
    assert response.status_code == 403 and files and files[0].closed
