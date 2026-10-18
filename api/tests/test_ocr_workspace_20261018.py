"""Synthetic regressions, authored for the later unified acceptance run."""
from copy import deepcopy
from uuid import uuid4

import pytest

from catalog.models import Asset, DocumentOutlineRevision, DocumentRevision, Edition, Page, PageTextRevision, Passage, TextBlock, Work
from catalog.services.document_intelligence import _quality_values, document_text_checksum, stage_document_asset
from ingestion.models import ProcessingJob
from ingestion.services.catalog_ocr import start_catalog_ocr
from ingestion.services.extract import ExtractedBlock, ExtractedPage, persist_pages
from ingestion.services.ocr_workspace import OCRWorkspaceConflict, apply_correction, fingerprint, prepare_correction, review_pages, reviewed_page_query, save_correction, task_command, workspace_state
from ingestion.services.ocr_provider import _request_document_gateway, normalize_task_options
from ingestion.services.processing import _persist_claimed_ocr_pages, _remaining_ocr_page_indexes


@pytest.fixture
def text_asset(db):
    edition = Edition.objects.create(work=Work.objects.create(title="合成 OCR 质量文件"))
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
        file="synthetic/not-read.pdf", page_count=3, sha256="a" * 64, is_current=True)
    for index in range(1, 4):
        page = Page.objects.create(asset=asset, index=index, text=f"合成原文{index}", normalized_text=f"合成原文{index}", text_source="embedded")
        Passage.objects.create(page=page, order=0, text=page.text, normalized_text=page.text, start_offset=0, end_offset=len(page.text))
    return asset


def command(asset, action="save", **kwargs):
    asset.refresh_from_db()
    page_index = kwargs.get("pdf_page", 1)
    return {"action": action, "request_id": uuid4(), "pdf_page": page_index,
            "source_fingerprint": fingerprint(asset, asset.pages.get(index=page_index)),
            "expected_revision": asset.text_corrections.values_list("revision", flat=True).first() or 0,
            **({"text": "人工核对文字", "note": "已对照合成原页", "confirmed": True} if action == "save" else {}), **kwargs}


def extracted(index, text="识别重跑结果"):
    return ExtractedPage(index=index, printed_label=str(index), chapter_title="", width=100, height=200,
                         text=text, source="ocr", confidence=.8, blocks=[ExtractedBlock(order=0, text=text, bbox=[1, 1, 50, 30])])


@pytest.mark.django_db
def test_save_is_immutable_and_replay_precedes_revision_guard(text_asset, admin_user):
    data = command(text_asset)
    row = save_correction(text_asset.pk, data, admin_user)
    assert text_asset.pages.get(index=1).text == "合成原文1"
    save_correction(text_asset.pk, command(text_asset, text="第二份候选"), admin_user)
    assert save_correction(text_asset.pk, data, admin_user).pk == row.pk
    with pytest.raises(OCRWorkspaceConflict):
        save_correction(text_asset.pk, {**data, "text": "同nonce不同文字"}, admin_user)
    with pytest.raises(OCRWorkspaceConflict):
        save_correction(text_asset.pk, {**data, "request_id": uuid4()}, admin_user)
    row.text = "历史不得改写"
    with pytest.raises(Exception, match="不可原位改写"):
        row.save()


@pytest.mark.django_db
def test_draft_apply_creates_real_evidence_and_preserves_offsets_without_boxes(text_asset, admin_user):
    original = text_asset.pages.get(index=1).text
    text = "第一段人工修正。\n\n第二段保留原始分隔。"
    row = save_correction(text_asset.pk, command(text_asset, text=text), admin_user)
    preview = prepare_correction(text_asset, row)
    assert preview["can_apply"]
    data = command(text_asset, "apply", revision_id=row.pk, prepared_fingerprint=preview["prepared_fingerprint"])
    result = apply_correction(text_asset.pk, data, admin_user)
    page = text_asset.pages.get(index=1)
    assert page.is_text_manual and page.manual_text_revision_id == row.pk
    assert page.text == text and row.original_text == original
    assert not page.blocks.exists()
    assert page.passages.exists()
    for passage in page.passages.all():
        assert text[passage.start_offset:passage.end_offset] == passage.text
        assert passage.bbox_union == []
    document = text_asset.document_revisions.get(is_active=True)
    assert document.evidence_spans.filter(page=page).exists()
    assert result.publication_event_id is None
    assert apply_correction(text_asset.pk, data, admin_user).pk == result.pk


@pytest.mark.django_db
def test_persist_all_and_missing_pages_never_delete_manual_text_or_passages(text_asset, admin_user):
    row = save_correction(text_asset.pk, command(text_asset), admin_user)
    first = text_asset.pages.get(index=1)
    first.is_text_manual, first.manual_text_revision = True, row
    first.save(update_fields=["is_text_manual", "manual_text_revision"])
    passage_id = first.passages.get().pk
    TextBlock.objects.create(page=first, order=0, text=first.text, normalized_text=first.text, bbox=[])
    persist_pages(text_asset, [extracted(1), extracted(2)], replace_missing=True)
    first.refresh_from_db()
    assert first.text == "合成原文1" and first.passages.get().pk == passage_id and first.blocks.exists()
    assert text_asset.pages.get(index=2).text == "识别重跑结果"
    persist_pages(text_asset, [extracted(2)], replace_missing=True)
    first.refresh_from_db()
    assert first.text == "合成原文1" and first.passages.get().pk == passage_id


@pytest.mark.django_db
def test_selected_ocr_skips_locked_pages_and_resumes_only_remaining_targets(text_asset, admin_user):
    page = text_asset.pages.get(index=2)
    page.is_text_manual = True
    page.save(update_fields=["is_text_manual"])
    data = {"edition_id": str(text_asset.edition_id), "asset_id": str(text_asset.pk), "request_id": uuid4(),
            "confirmed": True, "source_version": text_asset.updated_at.isoformat(), "page_indexes": [3, 1, 2, 3]}
    job, replayed = start_catalog_ocr(data, admin_user)
    assert not replayed and job.stats["requested_page_indexes"] == [1, 3]
    assert job.stats["target_pages"] == 2 and job.stats["protected_page_indexes"] == [2]
    assert _remaining_ocr_page_indexes(text_asset, job) == (3, 2, [1, 3])
    job.stats["completed_page_indexes"] = [1]
    job.save(update_fields=["stats"])
    assert _remaining_ocr_page_indexes(text_asset, job) == (3, 2, [3])
    assert start_catalog_ocr(data, admin_user)[0].pk == job.pk
    with pytest.raises(Exception, match="不能更换"):
        start_catalog_ocr({**data, "page_indexes": [1]}, admin_user)


@pytest.mark.django_db
def test_late_delivery_after_cancel_cannot_write_a_page(text_asset, admin_user):
    job = ProcessingJob.objects.create(edition=text_asset.edition, asset=text_asset, job_type="ocr", status="canceled", task_id="newer")
    assert not _persist_claimed_ocr_pages(job, [extracted(1)], "older")
    assert text_asset.pages.get(index=1).text == "合成原文1"


@pytest.mark.django_db
def test_active_ocr_and_changed_page_block_manual_adoption(text_asset, admin_user):
    row = save_correction(text_asset.pk, command(text_asset), admin_user)
    job = ProcessingJob.objects.create(edition=text_asset.edition, asset=text_asset, job_type="ocr", status="paused")
    assert not prepare_correction(text_asset, row)["can_apply"]
    job.status = "canceled"
    job.save(update_fields=["status"])
    page = text_asset.pages.get(index=1)
    page.text = "识别刚返回的新文字"
    page.save(update_fields=["text"])
    assert not prepare_correction(text_asset, row)["can_apply"]


@pytest.mark.django_db
def test_blank_page_needs_an_explicit_reason_and_confirmation(text_asset, admin_user):
    with pytest.raises(ValueError, match="空白页"):
        save_correction(text_asset.pk, command(text_asset, text="", note=""), admin_user)
    row = save_correction(text_asset.pk, command(text_asset, text="", note="已看原页，确为无文字图版", confirmed=False), admin_user)
    assert not prepare_correction(text_asset, row)["can_apply"]


@pytest.mark.django_db
def test_human_authority_changes_document_hash_without_faking_ocr_confidence(text_asset, admin_user):
    page = text_asset.pages.get(index=1)
    page.confidence = .1
    page.save(update_fields=["confidence"])
    before = document_text_checksum(text_asset)
    row = save_correction(text_asset.pk, command(text_asset, text=page.text), admin_user)
    page.is_text_manual, page.manual_text_revision = True, row
    page.save(update_fields=["is_text_manual", "manual_text_revision"])
    assert document_text_checksum(text_asset) != before
    values = _quality_values(text_asset)
    assert values["details"]["human_verified_pages"] == 1
    assert values["details"]["average_text_confidence"] < values["details"]["review_adjusted_text_weight"]
    page.refresh_from_db()
    assert page.confidence == .1
    page.text = "与确认记录不符"
    page.save(update_fields=["text"])
    assert _quality_values(text_asset)["details"]["human_verified_pages"] == 0


@pytest.mark.django_db
def test_public_apply_clones_old_identity_and_manual_lock_survives_next_stage(text_asset, admin_user):
    from .v304_helpers import activate_catalog_revision

    edition = text_asset.edition
    edition.state = "published"
    edition.save(update_fields=["state"])
    document = DocumentRevision.objects.create(asset=text_asset, revision=1, source_checksum=text_asset.sha256,
        text_checksum="b"*64, parser_name="synthetic", extraction_method="embedded")
    outline = DocumentOutlineRevision.objects.create(asset=text_asset, document_revision=document, revision=1,
        source_checksum=text_asset.sha256, nodes=[{"id": str(uuid4()), "title": "人工目录", "pdf_page": 1}],
        is_active=True, reviewed=True)
    active = activate_catalog_revision(edition, reader_asset=text_asset, document_revision=document, fulltext_ready=False)
    edition.work.title = "尚未发布的新标题"
    edition.work.save(update_fields=["title"])
    row = save_correction(text_asset.pk, command(text_asset), admin_user)
    preview = prepare_correction(text_asset, row)
    result = apply_correction(text_asset.pk, command(text_asset, "apply", revision_id=row.pk, prepared_fingerprint=preview["prepared_fingerprint"]), admin_user)
    assert result.applied_asset_id != text_asset.pk
    assert text_asset.pages.get(index=1).text == "合成原文1"
    assert result.publication_event.catalog_revision.snapshot["work"]["title"] == active.snapshot["work"]["title"]
    assert result.applied_asset.pages.get(index=1).manual_text_revision_id == row.pk
    assert result.applied_asset.outline_revisions.get(is_active=True).nodes == outline.nodes
    # Marking this exact asset as served forces a further immutable clone.
    result.publication_event.catalog_revision.reader_asset = result.applied_asset
    result.publication_event.catalog_revision.save(update_fields=["reader_asset"])
    cloned = stage_document_asset(result.applied_asset, stage_key="synthetic-next-ocr", reset_ocr=True)
    protected = cloned.pages.get(index=1)
    assert protected.is_text_manual and protected.manual_text_revision_id == row.pk
    assert protected.text == row.text and protected.text_source != "none"


@pytest.mark.django_db
def test_task_nonce_is_replayable_after_state_changes_and_wrong_job_version_conflicts(text_asset, admin_user):
    start = {"action": "start", "request_id": uuid4(), "source_version": text_asset.updated_at.isoformat(), "confirmed": True, "page_indexes": [1]}
    task_command(text_asset.pk, start, admin_user)
    job = ProcessingJob.objects.get(edition=text_asset.edition, job_type="ocr")
    task_command(text_asset.pk, deepcopy(start), admin_user)
    assert ProcessingJob.objects.filter(edition=text_asset.edition, job_type="ocr").count() == 1
    with pytest.raises(OCRWorkspaceConflict):
        task_command(text_asset.pk, {"action": "pause", "request_id": uuid4(), "job_id": job.pk, "job_version": "outdated"}, admin_user)


@pytest.mark.django_db
def test_no_ocr_job_does_not_fabricate_progress_and_reader_is_denied(text_asset, admin_user, reader_user, api_client):
    state = workspace_state(text_asset, admin_user)
    assert state["jobs"] == [] and state["parsed_page_count"] == 3
    assert state["counts"] == {"completed": 3}
    assert state["settings"]["service_verified"] is False
    api_client.force_authenticate(reader_user)
    url = f"/api/ingestion/ocr-workspace/{text_asset.pk}/"
    assert api_client.get(url).status_code == 403
    assert api_client.post(url, command(text_asset), format="json").status_code == 403


def review_command(asset, indexes=(1,), **kwargs):
    return {"action": "review", "request_id": uuid4(), "confirmed": True,
            "expected_revision": asset.text_corrections.values_list("revision", flat=True).first() or 0,
            "pages": [{"pdf_page": index, "source_fingerprint": fingerprint(asset, asset.pages.get(index=index))} for index in indexes], **kwargs}


@pytest.mark.django_db
def test_batch_review_is_source_bound_manual_history_and_replayable(text_asset, admin_user):
    before = document_text_checksum(text_asset)
    data = review_command(text_asset, (1, 2))
    review_pages(text_asset.pk, data, admin_user)
    assert set(reviewed_page_query(text_asset).values_list("index", flat=True)) == {1, 2}
    assert text_asset.text_corrections.filter(review_only=True, confirmed=True).count() == 2
    assert not ProcessingJob.objects.filter(edition=text_asset.edition).exists()
    assert document_text_checksum(text_asset) == before
    assert workspace_state(text_asset, admin_user)["counts"] == {"reviewed": 2, "completed": 1}
    review_pages(text_asset.pk, deepcopy(data), admin_user)
    assert text_asset.text_corrections.count() == 2
    with pytest.raises(OCRWorkspaceConflict):
        review_pages(text_asset.pk, {**data, "note": "同nonce不同核验"}, admin_user)
    # A new document interpretation makes the old review inapplicable, even if text stayed equal.
    DocumentRevision.objects.create(asset=text_asset, revision=1, is_active=True, source_checksum=text_asset.sha256,
        text_checksum="d" * 64, parser_name="synthetic", extraction_method="embedded")
    assert not reviewed_page_query(text_asset).exists()
    assert text_asset.text_corrections.filter(review_only=True).count() == 2


@pytest.mark.django_db
def test_batch_review_checks_every_page_before_writing_and_requires_blank_reason(text_asset, admin_user):
    data = review_command(text_asset, (1, 2))
    page = text_asset.pages.get(index=2)
    page.text = "并发返回正文"
    page.save(update_fields=["text"])
    with pytest.raises(OCRWorkspaceConflict):
        review_pages(text_asset.pk, data, admin_user)
    assert not text_asset.text_corrections.exists()
    page.text = ""
    page.save(update_fields=["text"])
    with pytest.raises(ValueError, match="无文字页面"):
        review_pages(text_asset.pk, review_command(text_asset, (1, 2)), admin_user)
    assert not text_asset.text_corrections.exists()
    review_pages(text_asset.pk, review_command(text_asset, (2,), note="已对照原页，确为空白页"), admin_user)
    assert reviewed_page_query(text_asset).get().index == 2


@pytest.mark.django_db
def test_reviewed_pages_are_explicitly_skipped_or_rechecked_without_losing_history(text_asset, admin_user):
    review_pages(text_asset.pk, review_command(text_asset, (1,)), admin_user)
    data = {"edition_id": text_asset.edition_id, "asset_id": text_asset.pk, "source_version": text_asset.updated_at.isoformat(),
            "request_id": uuid4(), "confirmed": True, "page_indexes": [1, 2], "task_options": normalize_task_options({"languages": ["en"], "layout": False})}
    job, _ = start_catalog_ocr(data, admin_user)
    assert job.stats["requested_page_indexes"] == [2]
    assert job.stats["reviewed_page_indexes"] == [1]
    assert job.stats["task_options"]["languages"] == ["en"]
    assert job.stats["task_options"]["layout"] is False
    job.status = "canceled"
    job.save(update_fields=["status"])
    data.update(request_id=uuid4(), task_options=normalize_task_options({"skip_reviewed": False}))
    second, _ = start_catalog_ocr(data, admin_user)
    assert second.stats["requested_page_indexes"] == [1, 2]
    persist_pages(text_asset, [extracted(1)], replace_missing=False)
    assert not reviewed_page_query(text_asset).exists()
    assert text_asset.text_corrections.filter(review_only=True).get().text == "合成原文1"


@pytest.mark.django_db
def test_quality_filters_use_real_signal_and_respect_selected_threshold(text_asset, admin_user):
    page = text_asset.pages.get(index=1)
    page.text_source, page.confidence = "ocr", .7
    page.save(update_fields=["text_source", "confidence"])
    second = text_asset.pages.get(index=2)
    second.width, second.height = 200, 100
    second.save(update_fields=["width", "height"])
    third = text_asset.pages.get(index=3)
    third.text = "含实际\ufffd符号"
    third.save(update_fields=["text"])
    strict = workspace_state(text_asset, admin_user)
    assert strict["counts"] == {"needs_review": 3}
    relaxed = workspace_state(text_asset, admin_user, quality_threshold=.65, detect_spreads=False, detect_garbled=False)
    assert relaxed["counts"] == {"completed": 3}
    assert "双页合扫或横向图版" in strict["pages"][1]["reason"]


def test_gateway_receives_selected_languages_and_layout_without_provider_call():
    import httpx

    captured = []
    def respond(request):
        captured.append(request.content)
        return httpx.Response(200, json={"pages": []})
    _request_document_gateway(None, base_url="https://synthetic.invalid", pdf_bytes=b"synthetic-file-bytes",
        transport=httpx.MockTransport(respond), task_options=normalize_task_options({"languages": ["en"], "layout": False}))
    assert b'name="languages"\r\n\r\nen\r\n' in captured[0]
    assert b'name="layout"\r\n\r\nfalse\r\n' in captured[0]


@pytest.mark.parametrize("value", [{"languages": []}, {"languages": ["unsupported"]}, {"layout": "false"}, {"quality_threshold": float("nan")}, {"quality_threshold": True}, {"auto_publish": True}])
def test_unknown_or_invalid_task_options_are_rejected(value):
    with pytest.raises(ValueError):
        normalize_task_options(value)


@pytest.mark.django_db
def test_formerly_public_draft_adoption_activates_only_the_new_normalized_file(text_asset, admin_user):
    from .v304_helpers import activate_catalog_revision

    document = DocumentRevision.objects.create(asset=text_asset, revision=1, source_checksum=text_asset.sha256,
        text_checksum="d" * 64, parser_name="synthetic", extraction_method="embedded")
    edition = text_asset.edition
    edition.state = "published"
    edition.save(update_fields=["state"])
    activate_catalog_revision(edition, reader_asset=text_asset, document_revision=document, fulltext_ready=False)
    edition.state = "draft"
    edition.save(update_fields=["state"])
    text_asset.refresh_from_db()
    row = save_correction(text_asset.pk, command(text_asset), admin_user)
    preview = prepare_correction(text_asset, row)
    assert preview["mode"] == "apply_draft"
    result = apply_correction(text_asset.pk, command(text_asset, "apply", revision_id=row.pk, prepared_fingerprint=preview["prepared_fingerprint"]), admin_user)
    text_asset.refresh_from_db()
    assert result.applied_asset_id != text_asset.pk
    result.applied_asset.refresh_from_db()
    assert result.applied_asset.is_current and not text_asset.is_current
    assert text_asset.pages.get(index=1).text == "合成原文1"
