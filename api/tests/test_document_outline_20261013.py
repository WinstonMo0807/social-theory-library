"""Directory extraction, exact-file public visibility and revision safeguards.

Uses generated fixture PDFs only. Run together in the final acceptance stage.
"""
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest
from django.core.files.base import ContentFile

from catalog.models import Asset, DocumentOutlineRevision, DocumentRevision, Edition, Page, TextBlock, Work
from catalog.services.document_outline import (
    OutlineConflict, adopt_outline, edit_outline, extract_outline, public_outline,
    queue_outline_rebuild, run_outline_job, validate_nodes, _tree_order,
)
from ingestion.models import ProcessingJob
from ingestion.services.extract import extract_native_pages, persist_pages
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


@pytest.fixture
def source(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    path = tmp_path / "outline-fixture.pdf"
    with fitz.open() as document:
        for heading in ["Chapter One", "Section 1.2", "Chapter Two"]:
            page = document.new_page()
            page.insert_text((72, 72), heading)
            if heading == "Chapter One":
                page.insert_text((72, 104), "Section 1.1")
        document.set_toc([[1, "Chapter One", 1], [2, "Section 1.1", 1],
                          [2, "Section 1.2", 2], [1, "Chapter Two", 3]])
        document.save(path)
    work = Work.objects.create(title="目录合成材料", document_type="book")
    edition = Edition.objects.create(work=work, state="published", public_slug=f"outline-{work.pk}")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
        access_status="public", sha256=sha256(path.read_bytes()).hexdigest(), page_count=3)
    asset.file.save("outline-fixture.pdf", ContentFile(path.read_bytes()), save=True)
    pages, _needs_ocr = extract_native_pages(path)
    persist_pages(asset, pages)
    revision = activate_catalog_revision(edition, reader_asset=asset)
    asset.refresh_from_db()
    return asset, revision.document_revision, path


def test_native_outline_preserves_hierarchy_and_same_page(source):
    asset, _, path = source
    nodes, diagnostics = extract_outline(asset, path)
    assert len(nodes) == 4 and not diagnostics
    assert [node["pdf_page"] for node in nodes] == [1, 1, 2, 3]
    assert nodes[1]["parent_id"] == nodes[0]["id"]
    assert nodes[2]["parent_id"] == nodes[0]["id"]
    assert nodes[3]["parent_id"] is None
    assert len({node["id"] for node in nodes}) == 4


def test_outline_task_is_idempotent_and_manifest_reads_adopted_tree(source, api_client):
    asset, _, _ = source
    request = uuid4()
    with patch("catalog.services.document_outline.dispatch_outline_job"):
        job = queue_outline_rebuild(asset.pk, request_id=request)
        assert queue_outline_rebuild(asset.pk, request_id=request).pk == job.pk
    result = run_outline_job(job.pk, task_id=job.task_id)
    assert result.status == "succeeded"
    assert len(public_outline(asset)) == 4
    manifest = api_client.get(f"/api/catalog/assets/{asset.pk}/manifest/")
    assert manifest.status_code == 200
    assert [row["level"] for row in manifest.data["outline"]] == [1, 2, 2, 1]
    assert DocumentOutlineRevision.objects.filter(asset=asset, is_active=True).count() == 1


def test_corrected_page_text_prevents_unverified_native_auto_activation(source):
    asset, _, path = source
    # The original PDF and machine blocks still contain these titles. A later
    # human correction is authoritative, so neither may corroborate over it.
    Page.objects.filter(asset=asset, index=1).update(is_text_manual=True, text="Corrected heading")
    nodes, diagnostics = extract_outline(asset, path)
    native = [row for row in nodes if row["source"] == "pdf_bookmark"]
    assert native[0]["pdf_page"] == native[1]["pdf_page"] == 1
    assert native[1]["parent_id"] == native[0]["id"]
    assert all(row["calibration_status"] == "needs_review" for row in native[:2])
    assert {row["node_id"] for row in diagnostics if row["code"] == "bookmark_title_unverified"} >= {native[0]["id"], native[1]["id"]}
    with patch("catalog.services.document_outline.dispatch_outline_job"):
        job = queue_outline_rebuild(asset.pk, request_id=uuid4())
    result = run_outline_job(job.pk, task_id=job.task_id)
    assert result.status == "succeeded"
    assert not asset.outline_revisions.filter(is_active=True).exists()
    assert asset.outline_revisions.latest("revision").parser_version == "outline-v8"


def test_candidates_preserve_manual_calibration_and_restore_history(source, admin_user):
    asset, _, _ = source
    first = edit_outline(asset.pk, nodes=[{"title": "人工校准", "pdf_page": 2, "calibration_status": "confirmed"}], expected_revision=0, actor=admin_user)
    adopted = adopt_outline(asset.pk, revision_id=first.pk, expected_revision=1, actor=admin_user)
    with patch("catalog.services.document_outline.dispatch_outline_job"):
        job = queue_outline_rebuild(asset.pk, request_id=uuid4())
    run_outline_job(job.pk, task_id=job.task_id)
    adopted.refresh_from_db()
    assert adopted.is_active and adopted.nodes[0]["title"] == "人工校准"
    second = edit_outline(asset.pk, nodes=[{"title": "新的校准", "pdf_page": 3, "calibration_status": "confirmed"}], expected_revision=3, actor=admin_user)
    adopt_outline(asset.pk, revision_id=second.pk, expected_revision=4, actor=admin_user)
    restored = adopt_outline(asset.pk, revision_id=first.pk, expected_revision=5, actor=admin_user, restore=True)
    assert restored.revision == 6 and restored.restored_from_id == first.pk
    assert public_outline(asset)[0]["title"] == "人工校准"
    assert asset.outline_revisions.count() == 6


def test_stale_edits_and_invalid_tree_do_not_replace_active_directory(source, admin_user):
    asset, _, _ = source
    revision = edit_outline(asset.pk, nodes=[{"title": "有效目录", "pdf_page": 1, "calibration_status": "confirmed"}], expected_revision=0, actor=admin_user)
    adopted = adopt_outline(asset.pk, revision_id=revision.pk, expected_revision=1, actor=admin_user)
    with pytest.raises(OutlineConflict):
        edit_outline(asset.pk, nodes=[{"title": "过时编辑", "pdf_page": 2}], expected_revision=0, actor=admin_user)
    with pytest.raises(ValueError, match="父节点"):
        validate_nodes(asset, [{"id": str(uuid4()), "parent_id": str(uuid4()), "title": "孤儿节点", "pdf_page": 1}])
    with pytest.raises(ValueError, match="物理页"):
        validate_nodes(asset, [{"title": "越界页", "pdf_page": 99}])
    assert public_outline(asset)[0]["title"] == "有效目录"


@pytest.mark.parametrize("change", ["private", "document_revision"])
def test_public_outline_does_not_serve_ineligible_content(source, api_client, admin_user, change):
    asset, document, _ = source
    revision = edit_outline(asset.pk, nodes=[{"title": "有资格才公开", "pdf_page": 1, "calibration_status": "confirmed"}], expected_revision=0, actor=admin_user)
    adopt_outline(asset.pk, revision_id=revision.pk, expected_revision=1, actor=admin_user)
    if change == "private":
        asset.access_status = "private"
        asset.save(update_fields=["access_status"])
    else:
        # A different text interpretation cannot reuse a manually adopted tree.
        DocumentRevision.objects.filter(pk=document.pk).update(is_active=False)
        new = DocumentRevision.objects.create(asset=asset, revision=2, is_active=True,
            source_checksum=asset.sha256, text_checksum="x" * 64)
        adopted = asset.outline_revisions.get(is_active=True)
        adopted.document_revision = new
        adopted.save(update_fields=["document_revision"])
    response = api_client.get(f"/api/catalog/assets/{asset.pk}/outline/")
    if change == "private":
        assert response.status_code == 404
    else:
        assert response.status_code == 200
        assert all(row["title"] != "有资格才公开" for row in response.data["nodes"])


def test_printed_contents_uses_segment_labels_not_one_global_offset(source, tmp_path):
    asset, _, _ = source
    path = tmp_path / "no-bookmarks.pdf"
    with fitz.open() as document:
        for _ in range(3):
            document.new_page()
        document.save(path)
    pages = list(asset.pages.order_by("index"))
    for page, text, label in zip(pages, ["Contents\nPreface .... iv\nIntroduction .... 1", "Preface", "Introduction"], ["", "iv", "1"]):
        page.text, page.printed_label = text, label
        page.save(update_fields=["text", "printed_label"])
    nodes, diagnostics = extract_outline(asset, path)
    assert [(row["title"], row["pdf_page"], row["printed_label"]) for row in nodes] == [("Preface", 2, "iv"), ("Introduction", 3, "1")]
    assert not diagnostics


def test_split_contents_header_and_synopsis_do_not_pollute_next_chapter(source, tmp_path):
    asset, _, _ = source
    path = tmp_path / "split-contents.pdf"
    with fitz.open() as document:
        for _ in range(3):
            document.new_page()
        document.save(path)
    asset.pages.all().update(text="", printed_label="")
    TextBlock.objects.filter(page__asset=asset).delete()
    Page.objects.filter(asset=asset, index=1).update(text=(
        "目\n录\n引言  21\n关于社会事实的讨论与研究的方法。\n"
        "第一章 什么是社会事实……23\n本章讨论社会事实的特征。"))
    Page.objects.filter(asset=asset, index=2).update(text="第二章 关于观察社会事实的准则……35")
    nodes, _ = extract_outline(asset, path)
    printed = [row for row in nodes if row["source"] == "printed_contents"]
    assert [(row["title"], row["printed_label"]) for row in printed] == [
        ("引言", "21"), ("第一章 什么是社会事实", "23"), ("第二章 关于观察社会事实的准则", "35")]


def test_outline_write_requires_staff_capability(source, api_client):
    asset, _, _ = source
    response = api_client.post(f"/api/catalog/admin/assets/{asset.pk}/outline/", {"action": "rebuild", "request_id": str(uuid4())}, format="json")
    assert response.status_code in {401, 403}
    assert not ProcessingJob.objects.filter(stats__operation="outline_rebuild").exists()


def test_canceled_delivery_and_changed_source_cannot_adopt(source):
    asset, _, _ = source
    with patch("catalog.services.document_outline.dispatch_outline_job"):
        canceled = queue_outline_rebuild(asset.pk, request_id=uuid4())
        canceled.status = "canceled"
        canceled.save(update_fields=["status"])
        job = queue_outline_rebuild(asset.pk, request_id=uuid4())
    assert run_outline_job(canceled.pk, task_id=canceled.task_id).status == "canceled"
    Asset.objects.filter(pk=asset.pk).update(is_current=False)
    with pytest.raises(OutlineConflict):
        run_outline_job(job.pk, task_id=job.task_id)
    assert not asset.outline_revisions.exists()


def test_fused_tree_keeps_native_parents_with_unknown_pages_and_repeated_titles():
    # Static counterexample to globally sorting pages and rebuilding by level:
    # the new same-page printed child belongs to A, not the last native root B.
    rows = [
        {"id": "a", "parent_id": None, "level": 1, "pdf_page": 1, "title": "A"},
        {"id": "a1", "parent_id": "a", "level": 2, "pdf_page": None, "title": "Introduction"},
        {"id": "b", "parent_id": None, "level": 1, "pdf_page": 3, "title": "B"},
        {"id": "b1", "parent_id": "b", "level": 2, "pdf_page": 3, "title": "Introduction"},
        {"id": "a2", "parent_id": "a", "level": 2, "pdf_page": 1, "title": "Printed supplement"},
    ]
    ordered = _tree_order(rows)
    assert [row["id"] for row in ordered] == ["a", "a1", "a2", "b", "b1"]
    assert {row["id"]: row["parent_id"] for row in ordered} == {"a": None, "a1": "a", "a2": "a", "b": None, "b1": "b"}


def test_ocr_locator_preserves_pixels_and_rotated_crop_geometry(source, tmp_path):
    asset, _, _ = source
    path = tmp_path / "rotated-cropped.pdf"
    with fitz.open() as document:
        for _ in range(3):
            document.new_page()
        document[1].set_cropbox(fitz.Rect(30, 40, 500, 700))
        document[1].set_rotation(90)
        document.save(path)
    asset.pages.update(text="", chapter_title="")
    Page.objects.filter(asset=asset, index=1).update(text="Contents\nIntroduction .... 1")
    target = asset.pages.get(index=2)
    target.text, target.printed_label, target.text_source = "Introduction", "1", "ocr"
    target.width, target.height = 2640, 1880
    target.save()
    target.blocks.all().delete()
    TextBlock.objects.create(page=target, order=0, text="Introduction", bbox=[400, 200, 900, 280])
    nodes, _ = extract_outline(asset, path)
    assert nodes[0]["pdf_position"] == []
    assert nodes[0]["coordinate_unit"] == ""
    locator = nodes[0]["source_locator"]
    assert locator["coordinate_unit"] == "pixels"
    assert locator["coordinate_space"] == "ocr_rendered_page"
    assert locator["source_width"] == 2640
    assert locator["page_geometry"]["rotation"] == 90
    assert locator["page_geometry"]["cropbox"] == [30, 40, 500, 700]


def test_metadata_only_reader_keeps_native_bookmarks(source, api_client):
    asset, _, _ = source
    with patch("catalog.services.document_outline.dispatch_outline_job"):
        job = queue_outline_rebuild(asset.pk, request_id=uuid4())
    run_outline_job(job.pk, task_id=job.task_id)
    publication = asset.edition.active_catalog_revision
    publication.fulltext_ready = False
    publication.save(update_fields=["fulltext_ready"])
    response = api_client.get(f"/api/catalog/assets/{asset.pk}/outline/")
    assert response.status_code == 200
    assert len(response.data["nodes"]) == 4
    assert all(row["source"] == "pdf_bookmark" for row in response.data["nodes"])


def test_metadata_only_reader_keeps_explicitly_adopted_navigation(source, admin_user, api_client):
    asset, _, _ = source
    manual = edit_outline(asset.pk, nodes=[{"title": "已校准目录", "pdf_page": 2, "calibration_status": "confirmed"}], expected_revision=0, actor=admin_user)
    adopt_outline(asset.pk, revision_id=manual.pk, expected_revision=1, actor=admin_user)
    publication = asset.edition.active_catalog_revision
    publication.fulltext_ready = False
    publication.save(update_fields=["fulltext_ready"])
    response = api_client.get(f"/api/catalog/assets/{asset.pk}/outline/")
    assert response.status_code == 200
    assert response.data["nodes"][0]["title"] == "已校准目录"


def test_two_adoptions_cannot_share_the_same_edit_precondition(source, admin_user):
    asset, _, _ = source
    first = edit_outline(asset.pk, nodes=[{"title": "第一稿", "pdf_page": 1, "calibration_status": "confirmed"}], expected_revision=0, actor=admin_user)
    second = edit_outline(asset.pk, nodes=[{"title": "第二稿", "pdf_page": 2, "calibration_status": "confirmed"}], expected_revision=1, actor=admin_user)
    adopted = adopt_outline(asset.pk, revision_id=first.pk, expected_revision=2, actor=admin_user)
    with pytest.raises(OutlineConflict):
        adopt_outline(asset.pk, revision_id=second.pk, expected_revision=2, actor=admin_user)
    assert asset.outline_revisions.get(is_active=True).pk == adopted.pk


def test_directory_writes_replay_receipts_before_stale_precondition(source, admin_user):
    asset, _, _ = source
    request = uuid4()
    nodes = [{"title": "回执保存", "pdf_page": 1, "calibration_status": "confirmed"}]
    saved = edit_outline(asset.pk, nodes=nodes, expected_revision=0, actor=admin_user, request_id=request)
    assert edit_outline(asset.pk, nodes=nodes, expected_revision=0, actor=admin_user, request_id=request).pk == saved.pk
    adopted_request = uuid4()
    adopted = adopt_outline(asset.pk, revision_id=saved.pk, expected_revision=1, actor=admin_user, request_id=adopted_request)
    assert adopt_outline(asset.pk, revision_id=saved.pk, expected_revision=1, actor=admin_user, request_id=adopted_request).pk == adopted.pk
    with pytest.raises(OutlineConflict):
        edit_outline(asset.pk, nodes=[{"title": "不能换输入", "pdf_page": 2}], expected_revision=0, actor=admin_user, request_id=request)


def test_scanned_contents_rejects_file_indexes_and_running_headers(source, tmp_path):
    asset, _, _ = source
    path = tmp_path / "scan-fixture.pdf"
    with fitz.open() as document:
        for _ in range(8): document.new_page()
        document.set_page_labels([{"startpage":0,"prefix":"","firstpagenum":1,"style":"D"}])
        document.save(path)
    asset.pages.all().delete()
    asset.page_count = 8
    asset.save(update_fields=["page_count"])
    texts = ["目\n录\n第一章 合成标题…… 1", "2\n目\n本页只有章节摘要", "目\n3\n结论…… 5",
             "第一章 合成\n标题", "第一章 合成标题\n真实正文", "第一章 合成标题\n其他正文",
             "第一章 合成标题\n其他正文", "结\n论"]
    for number,text in enumerate(texts,1):
        page=Page.objects.create(asset=asset,index=number,text=text,text_source="ocr",printed_label=str(number),label_source="pdf_page_labels",width=600,height=800)
        for order,line in enumerate(text.splitlines()):
            top=80 if number in {5,6,7} and order==0 else 220+order*30
            TextBlock.objects.create(page=page,order=order,text=line,bbox=[100,top,400,top+20])
    nodes, diagnostics = extract_outline(asset,path)
    assert [(row["title"],row["pdf_page"]) for row in nodes] == [("第一章 合成标题",4),("结论",8)]
    assert all(row["calibration_status"] == "matched" for row in nodes)
    assert any(row["code"] == "repeated_running_headers" for row in diagnostics)
