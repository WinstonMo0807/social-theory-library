"""Deferred acceptance for immutable, adopted-only PDF bookmark exports."""
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest

from catalog.models import Asset, DocumentOutlineRevision
from catalog.services.document_outline import OutlineConflict, adopt_outline, extract_outline
from catalog.services.outline_exports import queue_export, run_export, write_bookmarked_copy
from .test_outline_atlas_20261018 import outline_source  # noqa: F401


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_export_preserves_original_and_roundtrips_rotated_cropped_target(tmp_path, rotation):
    source, output = tmp_path / "source.pdf", tmp_path / "export.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page(width=500, height=700)
        page.set_cropbox(fitz.Rect(20, 40, 460, 650))
        page.set_rotation(rotation)
        pdf.save(source)
    original = source.read_bytes()
    node = {"id": str(uuid4()), "parent_id": None, "level": 1, "title": "校准标题", "pdf_page": 1,
            "normalized_position": [.2, .3], "calibration_status": "confirmed"}
    write_bookmarked_copy(source, output, [node], page_count=1, heartbeat=lambda *_: None)
    assert source.read_bytes() == original
    with fitz.open(output) as pdf:
        row = pdf.get_toc(simple=False)[0]
        assert row[:3] == [1, "校准标题", 1]
        assert abs(row[3]["to"].x / pdf[0].rect.width - .2) < .003
        assert abs(row[3]["to"].y / pdf[0].rect.height - .3) < .003


@pytest.mark.django_db
def test_export_requires_adoption_and_reuses_original_request(outline_source, admin_user):
    asset, document, path = outline_source
    nodes, diagnostics = extract_outline(asset, path)
    draft = DocumentOutlineRevision.objects.create(asset=asset, document_revision=document, revision=1,
        source_checksum=asset.sha256, nodes=nodes, diagnostics=diagnostics)
    with pytest.raises(OutlineConflict):
        queue_export(asset.pk, revision_id=draft.pk, request_id=uuid4(), actor=admin_user)
    adopted = adopt_outline(asset.pk, revision_id=draft.pk, expected_revision=1, actor=admin_user)
    request_id = uuid4()
    with patch("catalog.services.outline_exports.dispatch_export"):
        job = queue_export(asset.pk, revision_id=adopted.pk, request_id=request_id, actor=admin_user)
        replay = queue_export(asset.pk, revision_id=adopted.pk, request_id=request_id, actor=admin_user)
    assert replay.pk == job.pk
    before = sha256(asset.file.read()).hexdigest(); asset.file.close()
    result = run_export(job.pk, task_id=job.task_id)
    artifact = Asset.objects.get(pk=result.stats["result_asset_id"])
    asset.refresh_from_db()
    assert result.status == "succeeded" and artifact.source_asset_id == asset.pk
    assert artifact.access_status == "private" and not artifact.is_current
    assert artifact.validation_details["outline_revision_id"] == str(adopted.pk)
    assert sha256(asset.file.read()).hexdigest() == before; asset.file.close()
    with patch("catalog.services.outline_exports.dispatch_export"):
        stale = queue_export(asset.pk, revision_id=adopted.pk, request_id=uuid4(), actor=admin_user)
    asset.sha256 = "f" * 64; asset.save(update_fields=["sha256"])
    with pytest.raises(OutlineConflict):
        run_export(stale.pk, task_id=stale.task_id)
    assert Asset.objects.filter(source_asset=asset, processor="adopted-outline-export").count() == 1
