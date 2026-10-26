"""Candidate, publication and spread regressions; authored for unified acceptance."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from catalog.models import Asset, DocumentOutlineRevision, DocumentRevision, Edition, Page, PageMappingRevision, Work
from catalog.services.page_label_metadata import claimed_page_status, structured_page_labels
from catalog.services.page_mapping import (
    MappingConflict, apply_mapping, current_data, diagnostics, prepare_mapping,
    save_mapping, source_fingerprint, validate_data,
)


@pytest.fixture
def mapping_asset(db):
    work = Work.objects.create(title="合成页码测试")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
                                 page_count=3, sha256="1" * 64)
    Page.objects.bulk_create([Page(asset=asset, index=i, printed_label=str(i), text="合成文字",
                                  normalized_text="合成文字", text_source="embedded") for i in range(1, 4)])
    return asset


def command(asset, action="save", **values):
    asset.refresh_from_db()
    return {"action": action, "request_id": uuid4(), "expected_revision": asset.page_mapping_revisions.count(),
            "source_fingerprint": source_fingerprint(asset), **values}


def confirmed_data(asset):
    data = current_data(asset)
    for row in data["pages"]:
        row["confirmed"] = True
    return data


@pytest.mark.django_db
def test_candidates_are_immutable_and_replay_precedes_stale_guard(mapping_asset, admin_user):
    data = confirmed_data(mapping_asset)
    data["pages"][0]["labels"] = ["i"]
    request = command(mapping_asset, data=data)
    first = save_mapping(mapping_asset.pk, data=request, actor=admin_user)
    assert mapping_asset.pages.get(index=1).printed_label == "1"
    second = save_mapping(mapping_asset.pk, data=command(mapping_asset, data=confirmed_data(mapping_asset)), actor=admin_user)
    assert second.revision == 2
    assert save_mapping(mapping_asset.pk, data=request, actor=admin_user).pk == first.pk
    altered = deepcopy(request)
    altered["data"]["pages"][0]["labels"] = ["ii"]
    with pytest.raises(MappingConflict):
        save_mapping(mapping_asset.pk, data=altered, actor=admin_user)
    with pytest.raises(MappingConflict):
        save_mapping(mapping_asset.pk, data={**request, "request_id": uuid4()}, actor=admin_user)


@pytest.mark.django_db
def test_manual_lock_and_automatic_candidates_do_not_erase_confirmation(mapping_asset, admin_user):
    page = mapping_asset.pages.get(index=1)
    page.is_label_manual = True
    page.save(update_fields=["is_label_manual"])
    data = confirmed_data(mapping_asset)
    data["pages"][0]["labels"] = ["x"]
    with pytest.raises(ValueError, match="人工锁定"):
        save_mapping(mapping_asset.pk, data=command(mapping_asset, data=data), actor=admin_user)
    data["pages"][0].update(override_manual=True, note="逐页核对后的人工修改")
    saved = save_mapping(mapping_asset.pk, data=command(mapping_asset, data=data), actor=admin_user)
    assert saved.data["pages"][0]["labels"] == ["x"]
    analyzed = save_mapping(mapping_asset.pk, data=command(mapping_asset, "analyze"), actor=admin_user)
    assert analyzed.data["pages"][0]["labels"] == ["x"]
    assert mapping_asset.pages.get(index=1).printed_label == "1"


@pytest.mark.django_db
def test_segment_ends_at_explicit_boundary_and_does_not_confirm(mapping_asset, admin_user):
    result = save_mapping(mapping_asset.pk, actor=admin_user, data=command(mapping_asset, "segment", segment={
        "id": "front", "name": "前置页", "start": 1, "end": 2, "start_label": "i", "style": "roman_lower"}))
    assert [r["labels"] for r in result.data["pages"]] == [["i"], ["ii"], ["3"]]
    assert not any(r["confirmed"] for r in result.data["pages"])
    assert mapping_asset.pages.get(index=1).printed_label == "1"


@pytest.mark.django_db
def test_duplicate_and_missing_page_require_review_without_creating_pdf_pages(mapping_asset, admin_user):
    data = confirmed_data(mapping_asset)
    data["pages"][1]["labels"] = ["1"]
    data["missing"] = [{"id": "missing-two", "label": "2", "after_pdf_page": 1, "note": "扫描原件缺失", "confirmed": True}]
    result = save_mapping(mapping_asset.pk, actor=admin_user, data=command(mapping_asset, data=data))
    assert not prepare_mapping(mapping_asset, result)["can_apply"]
    data["pages"][0]["note"] = data["pages"][1]["note"] = "原件重复编号，保留原貌"
    result = save_mapping(mapping_asset.pk, actor=admin_user, data=command(mapping_asset, data=data))
    preview = prepare_mapping(mapping_asset, result)
    assert preview["can_apply"]
    # Confirmation changes are included even when that page's label stays put.
    assert preview["changed_page_count"] == 3
    assert preview["changes"][2]["before"] == preview["changes"][2]["after"]
    assert mapping_asset.pages.count() == 3
    invalid = deepcopy(data)
    invalid["missing"][0]["label"] = "1"
    assert diagnostics(invalid)["missing_present"] == ["missing-two"]


@pytest.mark.django_db
def test_stale_document_and_changed_preview_cannot_apply(mapping_asset, admin_user):
    saved = save_mapping(mapping_asset.pk, actor=admin_user, data=command(mapping_asset, data=confirmed_data(mapping_asset)))
    preview = prepare_mapping(mapping_asset, saved)
    request = command(mapping_asset, "publish", revision_id=saved.pk, prepared_fingerprint=preview["prepared_fingerprint"])
    mapping_asset.sha256 = "2" * 64
    mapping_asset.save(update_fields=["sha256", "updated_at"])
    with pytest.raises(MappingConflict):
        apply_mapping(mapping_asset.pk, actor=admin_user, data=request)
    assert PageMappingRevision.objects.get(pk=saved.pk).applied_at is None


@pytest.mark.django_db
def test_draft_apply_preserves_missing_as_metadata_and_nonce_is_replayable(mapping_asset, admin_user):
    data = confirmed_data(mapping_asset)
    data["pages"][1]["labels"] = ["2", "3"]
    data["pages"][2]["labels"] = ["5"]
    data["missing"] = [{"id": "missing", "label": "4", "after_pdf_page": 2, "confirmed": True, "note": "原件缺页"}]
    saved = save_mapping(mapping_asset.pk, actor=admin_user, data=command(mapping_asset, data=data))
    preview = prepare_mapping(mapping_asset, saved)
    request = command(mapping_asset, "publish", revision_id=saved.pk, prepared_fingerprint=preview["prepared_fingerprint"])
    result = apply_mapping(mapping_asset.pk, actor=admin_user, data=request)
    assert result.publication_event_id is None
    assert apply_mapping(mapping_asset.pk, actor=admin_user, data=request).pk == result.pk
    mapping_asset.refresh_from_db()
    assert mapping_asset.pages.count() == 3
    assert mapping_asset.pages.get(index=2).printed_label == "2–3"
    assert mapping_asset.validation_details["page_mapping"]["missing"] == [
        {**row, "action": "mark"} for row in data["missing"]
    ]
    assert mapping_asset.edition.page_label_status == "ready"


@pytest.mark.django_db
def test_reader_cannot_read_or_write_admin_mapping(mapping_asset, api_client, reader_user):
    api_client.force_authenticate(reader_user)
    endpoint = f"/api/catalog/admin/assets/{mapping_asset.pk}/page-mapping/"
    assert api_client.get(endpoint).status_code == 403
    assert api_client.post(endpoint, command(mapping_asset, data=confirmed_data(mapping_asset)), format="json").status_code == 403


@pytest.mark.django_db
def test_published_mapping_stages_new_identity_and_preserves_public_metadata_and_outline(mapping_asset, admin_user):
    from .v304_helpers import activate_catalog_revision

    edition = mapping_asset.edition
    edition.state = "published"
    edition.save(update_fields=["state"])
    document = DocumentRevision.objects.create(asset=mapping_asset, revision=1, source_checksum=mapping_asset.sha256,
        text_checksum="3" * 64, parser_name="synthetic", extraction_method="embedded")
    outline = DocumentOutlineRevision.objects.create(asset=mapping_asset, document_revision=document, revision=1,
        source_checksum=mapping_asset.sha256, nodes=[{"id": str(uuid4()), "title": "人工目录标题", "pdf_page": 1,
            "printed_label": "1", "calibration_status": "confirmed", "normalized_position": [0.1, 0.2]}],
        is_active=True, reviewed=True)
    active = activate_catalog_revision(edition, reader_asset=mapping_asset, fulltext_ready=False)
    edition.work.title = "尚未发布的标题草稿"
    edition.work.save(update_fields=["title"])
    data = confirmed_data(mapping_asset)
    data["pages"][0]["labels"] = ["10"]
    saved = save_mapping(mapping_asset.pk, actor=admin_user, data=command(mapping_asset, data=data))
    preview = prepare_mapping(mapping_asset, saved)
    assert preview["can_apply"]
    request = command(mapping_asset, "publish", revision_id=saved.pk, prepared_fingerprint=preview["prepared_fingerprint"])
    result = apply_mapping(mapping_asset.pk, actor=admin_user, data=request)
    assert result.applied_asset_id != mapping_asset.pk
    assert result.publication_event.catalog_revision.snapshot["work"]["title"] == active.snapshot["work"]["title"]
    assert result.publication_event.catalog_revision.reader_asset_id == result.applied_asset_id
    assert mapping_asset.pages.get(index=1).printed_label == "1"
    assert result.applied_asset.pages.get(index=1).printed_label == "10"
    copied = result.applied_asset.outline_revisions.get(is_active=True)
    assert copied.nodes[0]["title"] == "人工目录标题"
    assert copied.nodes[0]["normalized_position"] == [0.1, 0.2]
    assert copied.nodes[0]["printed_label"] == "10"
    outline.refresh_from_db()
    assert outline.nodes[0]["printed_label"] == "1"
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == active.pk
    assert mapping_asset.is_current
    assert not result.applied_asset.is_current
    assert apply_mapping(mapping_asset.pk, actor=admin_user, data=request).pk == result.pk


@pytest.mark.django_db
def test_forged_and_overlapping_physical_pages_are_rejected(mapping_asset):
    data = current_data(mapping_asset)
    data["pages"][2]["pdf_page"] = 4
    with pytest.raises(ValueError, match="不存在"):
        validate_data(mapping_asset, data)
    data = current_data(mapping_asset)
    data["segments"] = [{"id": "one", "name": "甲", "start": 1, "end": 2, "style": "arabic", "start_label": "1"},
                        {"id": "two", "name": "乙", "start": 2, "end": 3, "style": "arabic", "start_label": "2"}]
    with pytest.raises(ValueError, match="重叠"):
        validate_data(mapping_asset, data)


def test_spread_uses_explicit_metadata_and_cannot_claim_precise_half():
    page = SimpleNamespace(index=4, printed_label="16–17", asset=SimpleNamespace(validation_details={}))
    assert structured_page_labels(page)["printed_labels"] == ["16–17"]
    page.asset.validation_details = {"page_mapping": {"pages": [{"pdf_page": 4, "labels": ["16", "17"]}]}}
    assert structured_page_labels(page) == {"printed_labels": ["16", "17"], "printed_label_precision": "spread"}
    ref = {"source_status": "available", "printed_label": "16–17", **structured_page_labels(page)}
    assert claimed_page_status([ref], "17") == "needs_review"
    assert claimed_page_status([ref], "16–17") == "needs_review"
    assert claimed_page_status([{"source_status": "available", "printed_label": "17"}], "17") == "matched"
    assert claimed_page_status([{"source_status": "source_unavailable", "printed_label": "17"}], "17") == "needs_review"
