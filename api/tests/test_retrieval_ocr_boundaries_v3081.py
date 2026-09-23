from pathlib import Path
from unittest.mock import patch
import fitz
from catalog.services.discovery_query import keyword_question
from catalog.services.discovery_sessions import _diverse_prefix
from ingestion.services.ocr_provider import _request_document_gateway


def test_question_branch_keeps_content_negation_and_chinese_terms():
    assert keyword_question("如何认识农业组织互助？") == "农业组织互助"
    assert keyword_question("请问，为什么国家干预不总是有效？") == "国家干预不总是有效"
    assert keyword_question("不是国家的视角") == "不是国家的视角"
    assert keyword_question("如何") == "如何"


def test_diversity_does_not_promote_unrelated_tail_over_top_six():
    rows = [{"id": str(i), "work_id": "high" if i < 6 else "low", "score": 1 - i/10} for i in range(10)]
    assert _diverse_prefix(rows) == rows
    rows[2]["work_id"] = "second"
    result = _diverse_prefix(rows)
    assert result[:3] == rows[:3]
    assert {row["id"] for row in result} == {row["id"] for row in rows}


def test_retry_sends_identical_pdf_subset_bytes_and_maps_page_back(tmp_path, settings):
    path = Path(tmp_path) / "source.pdf"
    with fitz.open() as pdf:
        for index in range(3):
            pdf.new_page().insert_text((72, 72), f"Page {index+1}")
        pdf.save(path)
    uploads = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"pages": [{"index": 1, "blocks": []}]}
    def post(url, **kwargs):
        uploads.append(kwargs["files"]["file"][1].read())
        return Response()
    with patch("ingestion.services.ocr_provider.httpx.post", side_effect=post):
        for _ in range(2):
            payload = _request_document_gateway(path, base_url="http://nas-ocr", api_key="", page_numbers=[3])
            assert payload["pages"][0]["index"] == 3
    assert uploads[0] == uploads[1]
    with fitz.open(stream=uploads[0], filetype="pdf") as pdf:
        assert pdf.page_count == 1 and "Page 3" in pdf[0].get_text()
