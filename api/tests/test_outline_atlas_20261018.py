"""Final-atlas 112–115 contracts. Authored for the later unified acceptance run.

Only synthetic local PDFs are used. No real holdings or network providers.
"""
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest
from django.core.files.base import ContentFile

from catalog.models import Asset, DocumentOutlineRevision, DocumentRevision, Edition, Page, Work
from catalog.services.document_outline import (
    OutlineConflict, adopt_outline, edit_outline, extract_outline, outline_state,
    public_outline, queue_outline_rebuild, run_outline_job, validate_nodes,
)
from ingestion.models import ProcessingJob
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


@pytest.fixture
def outline_source(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    path = tmp_path / "atlas-outline.pdf"
    with fitz.open() as pdf:
        for _ in range(3):
            pdf.new_page()
        pdf[1].insert_text((72, 72), "Chapter One\nSection One")
        pdf[2].insert_text((72, 72), "Chapter Two")
        pdf.set_toc([[1, "Chapter One", 2], [2, "Section One", 2], [1, "Chapter Two", 3]])
        pdf.save(path)
    work = Work.objects.create(title="合成目录校准材料", document_type="book")
    edition = Edition.objects.create(work=work, state="draft")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
                                access_status="private", sha256=sha256(path.read_bytes()).hexdigest(), page_count=3)
    asset.file.save("atlas-outline.pdf", ContentFile(path.read_bytes()), save=True)
    document = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum=asset.sha256,
                                                text_checksum=sha256(b"synthetic").hexdigest())
    return asset, document, path


def _native_revision(source):
    asset, document, path = source
    nodes, diagnostics = extract_outline(asset, path)
    return DocumentOutlineRevision.objects.create(asset=asset, document_revision=document, revision=1,
                                                  source_checksum=asset.sha256, nodes=nodes, diagnostics=diagnostics)


def test_outline_reads_applied_spread_labels_and_prefixed_appendix(outline_source):
    asset, _, path = outline_source
    Page.objects.create(asset=asset, index=1, text="目錄\nChapter One .... 11\nChapter Two .... A-1")
    Page.objects.create(asset=asset, index=2, printed_label="10–11", label_segment="body", text="Chapter One")
    Page.objects.create(asset=asset, index=3, printed_label="A-1", label_segment="appendix", text="Chapter Two")
    asset.validation_details = {"page_mapping": {"pages": [{"pdf_page": 2, "labels": ["10", "11"]}]}}
    nodes, diagnostics = extract_outline(asset, path)
    printed = [candidate for node in nodes for candidate in node.get("candidate_sources", []) if candidate["source"] == "printed_contents"]
    assert {(row["printed_label"], row["pdf_page"]) for row in printed} >= {("11", 2), ("A-1", 3)}
    problem = next(row for row in diagnostics if row["code"] == "contents_label_review")
    assert problem["observed_pages"] == [2]
    assert problem["label_observations"][0]["spread"] is True
    assert problem["label_observations"][0]["label_segment"] == "body"


def test_explicit_missing_label_does_not_fall_back_to_an_unrelated_title_page(outline_source):
    asset, _, path = outline_source
    Page.objects.create(asset=asset, index=1, text="Contents\nChapter Two .... 12")
    Page.objects.create(asset=asset, index=2, printed_label="11", text="Chapter One")
    Page.objects.create(asset=asset, index=3, printed_label="A-1", text="Chapter Two")
    asset.validation_details = {"page_mapping": {"missing": [{"label": "12", "after_pdf_page": 2}]}}
    nodes, diagnostics = extract_outline(asset, path)
    candidate = next(row for row in nodes if row["source"] == "printed_contents")
    assert candidate["pdf_page"] is None and candidate["calibration_status"] == "needs_review"
    assert any(row["code"] == "contents_label_review" and row["node_id"] == candidate["id"] for row in diagnostics)


def test_single_node_save_preserves_unreviewed_siblings_and_coordinates(outline_source, admin_user):
    asset, _, _ = outline_source
    base = _native_revision(outline_source)
    rows = deepcopy(base.nodes)
    rows[1]["title"] = "手工改标题"
    rows[1]["calibration_status"] = "unverified"
    saved = edit_outline(asset.pk, nodes=rows, expected_revision=1, base_revision_id=base.pk,
                         actor=admin_user, request_id=uuid4())
    assert saved.nodes[0]["calibration_status"] == "native"
    assert saved.nodes[0]["source"] == "pdf_bookmark"
    assert saved.nodes[0]["pdf_position"] == base.nodes[0]["pdf_position"]
    assert saved.nodes[1]["calibration_status"] == "unverified"
    assert saved.nodes[1]["source"] == "manual"
    assert saved.nodes[1]["candidate_sources"][0]["title"] == "Section One"
    with pytest.raises(ValueError, match="未经明确确认"):
        adopt_outline(asset.pk, revision_id=saved.pk, expected_revision=2, actor=admin_user)
    base.refresh_from_db()
    assert base.nodes[1]["title"] == "Section One"


def test_new_nodes_require_explicit_confirmation_and_valid_landing(outline_source, admin_user):
    asset, _, _ = outline_source
    saved = edit_outline(asset.pk, nodes=[{"title": "待核对", "pdf_page": 1}], expected_revision=0, actor=admin_user)
    assert saved.nodes[0]["calibration_status"] == "unverified"
    with pytest.raises(ValueError, match="未经明确确认"):
        adopt_outline(asset.pk, revision_id=saved.pk, expected_revision=1, actor=admin_user)
    with pytest.raises(ValueError, match="物理页落点"):
        validate_nodes(asset, [{"title": "没有落点", "pdf_page": None, "calibration_status": "confirmed"}])
    with pytest.raises(ValueError, match="不能由人工编辑伪造"):
        validate_nodes(asset, [{"title": "伪造原生", "pdf_page": 1, "calibration_status": "native"}])
    with pytest.raises(ValueError, match="先选择物理页"):
        validate_nodes(asset, [{"title": "悬空坐标", "pdf_page": None, "normalized_position": [0.1, 0.2]}])


def test_changed_nodes_without_status_revert_to_unverified(outline_source):
    asset, _, _ = outline_source
    base = _native_revision(outline_source)
    row = {key: value for key, value in base.nodes[0].items() if key != "calibration_status"}
    row["title"] = "改名后需要重核对"
    assert validate_nodes(asset, [row], base_revision=base)[0]["calibration_status"] == "unverified"


def test_edit_uses_explicit_base_when_new_automatic_candidate_has_same_ids(outline_source, admin_user):
    asset, document, _ = outline_source
    base = _native_revision(outline_source)
    changed = deepcopy(base.nodes)
    changed[0]["pdf_page"] = 3
    changed[0]["source"] = "generated_heading"
    changed[0]["calibration_status"] = "needs_review"
    DocumentOutlineRevision.objects.create(asset=asset, document_revision=document, revision=2,
                                           source_checksum=asset.sha256, nodes=changed)
    rows = deepcopy(base.nodes)
    saved = edit_outline(asset.pk, nodes=rows, expected_revision=2, base_revision_id=base.pk,
                         actor=admin_user, request_id=uuid4())
    assert saved.nodes[0]["pdf_page"] == 2
    assert saved.nodes[0]["source"] == "pdf_bookmark"
    assert saved.nodes[0]["calibration_status"] == "native"


def test_manual_adoption_survives_rebuild_and_restore_creates_revision(outline_source, admin_user):
    asset, _, _ = outline_source
    first = edit_outline(asset.pk, nodes=[{"title": "人工目录", "pdf_page": 2, "calibration_status": "confirmed"}],
                         expected_revision=0, actor=admin_user)
    adopted = adopt_outline(asset.pk, revision_id=first.pk, expected_revision=1, actor=admin_user)
    with patch("catalog.services.document_outline.dispatch_outline_job"):
        job = queue_outline_rebuild(asset.pk, actor=admin_user, request_id=uuid4())
    run_outline_job(job.pk, task_id=job.task_id)
    adopted.refresh_from_db()
    assert adopted.is_active and adopted.reviewed
    restored = adopt_outline(asset.pk, revision_id=first.pk, expected_revision=3, actor=admin_user, restore=True)
    assert restored.revision == 4 and restored.restored_from_id == first.pk
    assert restored.nodes == first.nodes
    assert asset.outline_revisions.count() == 4


def test_source_replacement_blocks_old_base_and_preserves_prior_versions(outline_source, admin_user):
    asset, document, _ = outline_source
    base = _native_revision(outline_source)
    document.is_active = False
    document.save(update_fields=["is_active"])
    DocumentRevision.objects.create(asset=asset, revision=2, source_checksum=asset.sha256,
                                     text_checksum=sha256(b"changed").hexdigest())
    with pytest.raises(OutlineConflict, match="旧的正文解释"):
        edit_outline(asset.pk, nodes=base.nodes, expected_revision=1, base_revision_id=base.pk, actor=admin_user)
    with pytest.raises(OutlineConflict, match="旧的正文解释"):
        adopt_outline(asset.pk, revision_id=base.pk, expected_revision=1, actor=admin_user, restore=True)
    assert asset.outline_revisions.count() == 1


def test_same_request_replays_and_changed_base_is_not_same_request(outline_source, admin_user):
    asset, _, _ = outline_source
    base = _native_revision(outline_source)
    request_id = uuid4()
    kwargs = dict(nodes=deepcopy(base.nodes), expected_revision=1, base_revision_id=base.pk,
                  actor=admin_user, request_id=request_id)
    saved = edit_outline(asset.pk, **kwargs)
    assert edit_outline(asset.pk, **kwargs).pk == saved.pk
    with pytest.raises(OutlineConflict, match="同一个目录请求"):
        edit_outline(asset.pk, **{**kwargs, "base_revision_id": saved.pk})
    assert asset.outline_revisions.count() == 2


def test_candidates_keep_bookmark_printed_and_heading_observations(outline_source):
    asset, _, path = outline_source
    Page.objects.create(asset=asset, index=1, printed_label="i", text="Contents\nChapter One .... 1\nChapter Two .... 2")
    Page.objects.create(asset=asset, index=2, printed_label="1", text="Chapter One")
    Page.objects.create(asset=asset, index=3, printed_label="2", text="Chapter Two")
    nodes, _ = extract_outline(asset, path)
    first = next(node for node in nodes if node["title"] == "Chapter One")
    assert first["source"] == "pdf_bookmark"
    assert {row["source"] for row in first["candidate_sources"]} == {"pdf_bookmark", "printed_contents", "generated_heading"}
    printed = next(row for row in first["candidate_sources"] if row["source"] == "printed_contents")
    assert printed["contents_page"] == 1 and printed["pdf_page"] == 2 and printed["printed_label"] == "1"


def test_real_pdf_count_mismatch_cannot_produce_invalid_bookmarks(outline_source):
    asset, _, path = outline_source
    asset.page_count = 1
    with pytest.raises(OutlineConflict, match="实际 PDF 页数"):
        extract_outline(asset, path)


def test_private_admin_summary_never_advertises_public_reader(outline_source, api_client, admin_user, reader_user):
    asset, _, _ = outline_source
    url = f"/api/catalog/admin/assets/{asset.pk}/outline/"
    api_client.force_authenticate(user=reader_user)
    assert api_client.get(url).status_code == 403
    api_client.force_authenticate(user=admin_user)
    response = api_client.get(url)
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    summary = response.data["asset"]
    assert summary["title"] == "合成目录校准材料"
    assert summary["preview_url"] == f"/distribution/admin/assets/{asset.pk}/preview/"
    assert summary["reader_url"] == "" and summary["page_count"] == 3
    asset.is_current = False
    asset.save(update_fields=["is_current"])
    stale = outline_state(asset)["asset"]
    assert not stale["source_current"] and not stale["preview_url"]


def test_http_confirm_is_explicit_and_restore_does_not_mutate_original(outline_source, api_client, admin_user):
    asset, _, _ = outline_source
    api_client.force_authenticate(user=admin_user)
    url = f"/api/catalog/admin/assets/{asset.pk}/outline/"
    saved = api_client.post(url, {"action": "edit", "request_id": str(uuid4()), "expected_revision": 0,
                                  "nodes": [{"title": "人工节点", "pdf_page": 2, "calibration_status": "confirmed"}]}, format="json")
    assert saved.status_code == 200
    original = saved.data["latest"]["id"]
    adopted = api_client.post(url, {"action": "adopt", "request_id": str(uuid4()), "expected_revision": 1,
                                    "revision_id": original}, format="json")
    assert adopted.status_code == 200 and adopted.data["active"]["reviewed"]
    assert DocumentOutlineRevision.objects.get(pk=original).is_active is False
    assert ProcessingJob.objects.count() == 0


def test_public_native_navigation_does_not_expose_private_candidate_sources(outline_source):
    asset, _, _ = outline_source
    revision = _native_revision(outline_source)
    revision.nodes[0]["candidate_sources"].append({"id": str(uuid4()), "source": "generated_heading",
                                                  "title": "未采用的正文候选", "pdf_page": 2})
    revision.is_active = True
    revision.save(update_fields=["nodes", "is_active"])
    asset.access_status = "public"
    asset.save(update_fields=["access_status"])
    asset.edition.state = "published"
    asset.edition.save(update_fields=["state"])
    activate_catalog_revision(asset.edition, reader_asset=asset, fulltext_ready=False)
    asset.refresh_from_db()
    nodes = public_outline(asset)
    assert len(nodes) == 3
    assert all("candidate_sources" not in node and "candidate_sources_count" not in node for node in nodes)
    assert "未采用的正文候选" not in str(nodes)


@pytest.mark.parametrize("relative,status", [([], "unverified"), ([0.2, 0.6], "unverified"), ([0.2, 0.6], "confirmed")])
def test_clear_position_removes_hidden_source_locator_and_preserves_explicit_new_point(outline_source, api_client, admin_user, relative, status):
    asset, _, _ = outline_source
    base = _native_revision(outline_source)
    base.nodes[0].update(pdf_position=[], source="printed_contents", calibration_status="matched",
                         source_locator={"bbox": [20, 90, 80, 120], "coordinate_space": "ocr_rendered_page",
                                         "source_width": 600, "source_height": 800})
    base.save(update_fields=["nodes"])
    row = {"id": base.nodes[0]["id"], "title": base.nodes[0]["title"], "pdf_page": 2,
           "pdf_position": [], "normalized_position": relative, "clear_position": True,
           "calibration_status": status}
    api_client.force_authenticate(user=admin_user)
    response = api_client.post(f"/api/catalog/admin/assets/{asset.pk}/outline/", {
        "action": "edit", "request_id": str(uuid4()), "expected_revision": 1,
        "base_revision_id": str(base.pk), "nodes": [row]}, format="json")
    assert response.status_code == 200
    node = response.data["latest"]["nodes"][0]
    assert node["source_locator"] == {} and node["pdf_position"] == []
    assert node["normalized_position"] == relative and node["source"] == "manual"
    assert node["calibration_status"] == status
    assert node["precision"] == ("position" if relative else "page")
    base.refresh_from_db()
    assert base.nodes[0]["source_locator"]["bbox"] == [20, 90, 80, 120]
