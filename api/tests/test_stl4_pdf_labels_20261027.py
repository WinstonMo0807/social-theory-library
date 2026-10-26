import fitz

from catalog.models import Page
from ingestion.services.extract import _native_pages


def test_scanner_file_sequence_is_not_printed_pagination(tmp_path):
    path = tmp_path / "scanner.pdf"
    with fitz.open() as document:
        for _ in range(3):
            document.new_page()
        document.set_page_labels([{"startpage": 0, "prefix": "", "firstpagenum": 1, "style": "D"}])
        document.save(path)
    pages = _native_pages(path)
    assert [p.printed_label for p in pages] == ["", "", ""]
    assert all(p.label_source == Page.LabelSource.FILE_INDEX for p in pages)


def test_explicit_front_matter_and_body_labels_are_preserved(tmp_path):
    path = tmp_path / "labelled.pdf"
    with fitz.open() as document:
        for _ in range(3):
            document.new_page()
        document.set_page_labels([
            {"startpage": 0, "prefix": "", "firstpagenum": 1, "style": "r"},
            {"startpage": 1, "prefix": "", "firstpagenum": 1, "style": "D"},
        ])
        document.save(path)
    pages = _native_pages(path)
    assert [p.printed_label for p in pages] == ["i", "1", "2"]
    assert all(p.label_source == Page.LabelSource.PDF_PAGE_LABELS for p in pages)
