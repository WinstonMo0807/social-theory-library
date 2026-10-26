"""Engine replacement must not silently accept a retired gateway."""
import httpx
import pytest
from ingestion.services.ocr_provider import _request_document_gateway, OCR_MODEL_ID


@pytest.mark.parametrize("engine,model,revision,accepted", [
    ("RapidOCR", OCR_MODEL_ID, "rapidocr-3.10.0-ppocrv6-tiny-1", True),
    ("PaddleOCR", OCR_MODEL_ID, "legacy", False),
    ("RapidOCR", "PP-OCRv6-small", "other", False),
    ("RapidOCR", OCR_MODEL_ID, "", False),
])
def test_gateway_requires_selected_engine_and_model(engine, model, revision, accepted):
    payload = {"engine": engine, "model": model, "model_revision": revision,
               "pages": [{"index": 1, "blocks": []}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    def invoke():
        return _request_document_gateway(None, base_url="http://ocr.invalid", pdf_bytes=b"%PDF-fixture", transport=transport)
    if accepted:
        assert invoke()["model"] == OCR_MODEL_ID
    else:
        with pytest.raises(ValueError):
            invoke()


@pytest.mark.django_db
def test_resumed_pages_retain_legacy_identity_and_record_new_model(settings, tmp_path):
    from .test_stl4_selected_retry_20261024 import interrupted
    from ingestion.services.extract import ExtractedPage
    from ingestion.services.processing import _persist_claimed_ocr_pages
    job, old_page = interrupted(settings, tmp_path)
    job.status = "running"
    job.stats["engine"] = "paddleocr_nas"
    job.save()
    page = ExtractedPage(index=2, printed_label="", chapter_title="", width=100, height=200,
        text="New page", source="ocr", confidence=.9, blocks=[],
        ocr_metadata={"provider": "rapidocr_nas", "model": OCR_MODEL_ID, "model_revision": "tiny-1"})
    assert _persist_claimed_ocr_pages(job, [page], job.task_id)
    job.refresh_from_db(); old_page.refresh_from_db()
    assert old_page.text == "已保存的第一页"
    assert job.stats["completed_page_indexes"] == [1, 2]
    assert job.stats["page_models"]["1"]["provider"] == "paddleocr_nas"
    assert job.stats["page_models"]["1"]["legacy"] is True
    assert job.stats["page_models"]["2"]["model"] == OCR_MODEL_ID
