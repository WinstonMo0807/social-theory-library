"""Deferred acceptance for review visibility and rotated heading locations."""
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest

from catalog.models import DocumentOutlineRevision, Page, TextBlock
from catalog.services.document_outline import extract_outline, queue_outline_rebuild, run_outline_job
from catalog.services.page_geometry import native_geometry
from .test_outline_atlas_20261018 import outline_source  # noqa: F401

pytestmark = pytest.mark.django_db


def test_no_diagnostic_does_not_hide_unreviewed_outline(outline_source, admin_user, api_client):
    asset, _, _ = outline_source
    with patch("catalog.services.document_outline.dispatch_outline_job"):
        job = queue_outline_rebuild(asset.pk, actor=admin_user, request_id=uuid4())
    result = run_outline_job(job.pk, task_id=job.task_id)
    assert result.status == "succeeded" and result.stats["needs_review"] is True
    latest = DocumentOutlineRevision.objects.get(pk=result.stats["result_revision_id"])
    assert not latest.diagnostics and not latest.reviewed
    api_client.force_authenticate(admin_user)
    response = api_client.get("/api/catalog/admin/outline-rebuilds/?filter=needs_review")
    assert response.status_code == 200
    assert str(asset.pk) in {row["asset_id"] for row in response.data["items"]}


@pytest.mark.parametrize("rotation,expected", [(90, [.6, .2]), (270, [.3, .6])])
def test_rotated_heading_uses_verified_page_geometry(outline_source, tmp_path, rotation, expected):
    asset, _, _ = outline_source
    path = tmp_path / "rotated-outline.pdf"
    with fitz.open() as pdf:
        for _ in range(3):
            pdf.new_page(width=100, height=200)
        pdf[1].set_rotation(rotation)
        geometry = native_geometry(pdf[1])
        pdf.save(path)
    Page.objects.create(asset=asset, index=1, text="Contents\nA useful heading .... 1")
    page = Page.objects.create(asset=asset, index=2, printed_label="1", text="A useful heading",
        text_source="embedded", width=200, height=100, geometry=geometry)
    TextBlock.objects.create(page=page, order=1, text="A useful heading", bbox=[20, 60, 40, 80])
    nodes, _ = extract_outline(asset, path)
    node = next(row for row in nodes if row["source"] == "printed_contents")
    assert node["normalized_position"] == expected
    assert node["source_locator"]["geometry_status"] == "validated"
    page.geometry = {}; page.save(update_fields=["geometry"])
    nodes, _ = extract_outline(asset, path)
    assert nodes[0]["normalized_position"] == []
    assert nodes[0]["source_locator"]["geometry_status"] == "unknown"
