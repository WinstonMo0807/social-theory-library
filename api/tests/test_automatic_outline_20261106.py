"""Automatic navigation, immutable downloads and optional one-step corrections."""
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Asset, DocumentRevision
from catalog.services.document_outline import correct_outline, queue_outline_rebuild, run_outline_job
from catalog.services.outline_exports import current_download_copy, run_export, queue_download_cloud_copy
from distribution.views import _download_file_asset
from ingestion.models import ProcessingJob
from .test_outline_atlas_20261018 import outline_source  # noqa: F401


@pytest.mark.django_db
def test_no_observed_titles_does_not_claim_a_generated_outline(outline_source):
    from catalog.services.outline_automatic import automatic_nodes
    nodes, diagnostics = automatic_nodes(outline_source[0], [])
    assert nodes == [] and diagnostics[0]["code"] == "no_outline_detected"


@pytest.mark.django_db
def test_automatic_outline_download_and_correction_preserve_source(outline_source, admin_user):
    asset, document, path = outline_source
    original = path.read_bytes()
    with patch("catalog.services.document_outline.dispatch_outline_job"), patch("catalog.services.outline_exports.dispatch_export"):
        job = queue_outline_rebuild(asset.pk, automatic=True)
        assert queue_outline_rebuild(asset.pk, automatic=True).pk == job.pk
        result = run_outline_job(job.pk, task_id=job.task_id)
    active = asset.outline_revisions.get(is_active=True)
    assert result.status == "succeeded" and active.origin == "automatic" and not active.reviewed
    export = ProcessingJob.objects.get(asset=asset, stats__operation="outline_export")
    assert export.created_by_id is None
    assert run_export(export.pk, task_id=export.task_id).status == "succeeded"
    artifact = current_download_copy(asset)
    assert artifact and _download_file_asset(asset)[0].pk == artifact.pk
    with fitz.open(artifact.file.path) as pdf:
        assert pdf.get_toc() == [[1, "Chapter One", 2], [2, "Section One", 2], [1, "Chapter Two", 3]]
    assert path.read_bytes() == original and sha256(asset.file.read()).hexdigest() == asset.sha256
    asset.file.close()

    # Correcting one row does not falsely mark all automatic siblings as reviewed.
    active.nodes[1]["calibration_status"] = "matched"
    active.save(update_fields=["nodes"])
    rows = deepcopy(active.nodes)
    rows[0].update(title="Corrected chapter", calibration_status="unverified")
    request = uuid4()
    with patch("catalog.services.outline_exports.dispatch_export"):
        corrected = correct_outline(asset.pk, nodes=rows, base_revision_id=active.pk,
            expected_revision=active.revision, actor=admin_user, request_id=request)
        replay = correct_outline(asset.pk, nodes=rows, base_revision_id=active.pk,
            expected_revision=active.revision, actor=admin_user, request_id=request)
    assert replay.pk == corrected.pk and corrected.is_active and not corrected.reviewed
    assert corrected.nodes[0]["calibration_status"] == "confirmed"
    assert corrected.nodes[1]["calibration_status"] == "matched"
    # The old download is no longer current while the new copy is being built.
    assert current_download_copy(asset) is None
    export = ProcessingJob.objects.get(asset=asset, stats__outline_revision_id=str(corrected.pk))
    run_export(export.pk, task_id=export.task_id)
    assert current_download_copy(asset).pk != artifact.pk
    with patch("catalog.services.document_outline.dispatch_outline_job"), patch("catalog.services.outline_exports.dispatch_export"):
        rebuild = queue_outline_rebuild(asset.pk)
        run_outline_job(rebuild.pk, task_id=rebuild.task_id)
    assert asset.outline_revisions.get(is_active=True).pk == corrected.pk
    assert Asset.objects.filter(pk=artifact.pk).exists()
    document.is_active = False; document.save(update_fields=["is_active"])
    DocumentRevision.objects.create(asset=asset, revision=2, source_checksum=asset.sha256, text_checksum="b" * 64)
    assert current_download_copy(asset) is None


@pytest.mark.django_db
def test_correct_outline_is_not_available_to_readers(outline_source, django_user_model):
    asset, _, _ = outline_source
    client = APIClient()
    url = reverse("admin-asset-outline", kwargs={"asset_id": asset.pk})
    assert client.post(url, {"action": "correct"}, format="json").status_code == 401
    user = django_user_model.objects.create_user(username="outline-reader", role="reader")
    client.force_authenticate(user)
    assert client.post(url, {"action": "correct"}, format="json").status_code == 403
    assert not asset.outline_revisions.exists()


@pytest.mark.django_db
def test_bookmark_cloud_copy_uses_only_existing_anchor_destination(outline_source):
    from distribution.models import CloudProvider, CloudObject
    asset, _, _ = outline_source
    artifact = Asset.objects.create(edition=asset.edition, kind="web_derivative", source_asset=asset,
        sha256="a" * 64, byte_size=100, access_status="private", is_current=False)
    provider = CloudProvider.objects.create(name="Synthetic", bucket="test", enabled=True)
    with patch("catalog.services.outline_exports.current_download_copy", return_value=artifact), patch("distribution.tasks.sync_cloud_object.apply_async") as enqueue:
        queue_download_cloud_copy(asset)
        enqueue.assert_not_called()
        CloudObject.objects.create(asset=asset, provider=provider, object_key="original.pdf", sha256=asset.sha256, status="ready")
        queue_download_cloud_copy(asset)
        queue_download_cloud_copy(asset)
        assert enqueue.call_count == 1
        assert enqueue.call_args.kwargs["kwargs"] == {"resume_publication": False}
        record = CloudObject.objects.get(asset=artifact)
        assert record.provider_id == provider.pk and artifact.sha256 in record.object_key
