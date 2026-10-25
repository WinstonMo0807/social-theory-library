"""PDF30 availability contract. Prepared for unified acceptance; not run during development."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from catalog.services.discovery_sources import edition_metadata_header
from catalog.services import discovery_projection as projection


def test_available_chinese_translation_uses_published_source_not_chinese_original(monkeypatch):
    asset = SimpleNamespace(pk="asset", edition_id="edition", kind="normalized", status="ready",
        validation_status="valid", file="reader.pdf", mime_type="application/pdf", page_count=80,
        access_status="public")
    snapshot = {"work": {"language": "zh-CN"}, "edition": {}, "document": {"asset_id": "asset"}}
    row = SimpleNamespace(pk="edition", work_id="chinese", active_catalog_revision=SimpleNamespace(
        reader_asset=asset, snapshot=snapshot))
    original = edition_metadata_header(row, taxonomy={})
    assert original["reader_available"] and original["pdf_available"]
    assert not original["chinese_translation"]
    snapshot["work"]["translation_of_id"] = "original-work"
    translation = edition_metadata_header(row, taxonomy={})
    assert translation["chinese_translation"]
    asset.status = "failed"
    failed = edition_metadata_header(row, taxonomy={})
    assert not failed["reader_available"] and not failed["pdf_available"]
    monkeypatch.setattr(projection, "public_editions", MagicMock())
    candidates = [original, failed]
    monkeypatch.setattr(projection, "iter_edition_metadata_headers", lambda rows: ((None, item) for item in candidates))
    source = {"channel": "passages", "work_id": "original-work", "translation_of_id": ""}
    selected = {"availability": ["zh_translation"]}
    assert not projection._matches(source, selected, contribution_cache={}, access_statuses=["public"])
    candidates.append(translation)
    assert projection._matches(source, selected, contribution_cache={}, access_statuses=["public"])
