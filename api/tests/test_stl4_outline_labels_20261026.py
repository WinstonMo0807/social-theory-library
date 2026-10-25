"""Deferred coverage for real label segments/spreads; not executed in development."""
from catalog.services.outline_labels import OutlineLabels


def page(number, printed, segment=""):
    return {"index": number, "printed_label": printed, "label_segment": segment}


def test_applied_spread_keeps_both_labels_on_the_same_physical_page():
    labels = OutlineLabels([page(7, "10–11", "body")], {"pages": [{"pdf_page": 7, "labels": ["10", "11"]}]})
    assert labels.observations("11") == [{"pdf_page": 7, "label_segment": "body", "printed_labels": ["10", "11"], "spread": True}]
    assert labels.observations("10-11")[0]["pdf_page"] == 7
    assert labels.observations("１１")[0]["pdf_page"] == 7


def test_stale_or_duplicate_mapping_metadata_does_not_invent_spread_slots():
    pages = [page(7, "12")]
    assert not OutlineLabels(pages, {"pages": [{"pdf_page": 7, "labels": ["10", "11"]}]}).observations("11")
    duplicate = {"pages": [{"pdf_page": 7, "labels": ["10", "11"]}, {"pdf_page": 7, "labels": ["10", "11"]}]}
    assert not OutlineLabels([page(7, "10–11")], duplicate).observations("11")
    assert not OutlineLabels([page(7, "10–11")], {}).observations("11")


def test_repeated_labels_preserve_every_segment_without_selecting_the_first():
    labels = OutlineLabels([page(2, "i", "front"), page(30, "i", "appendix")], {})
    assert [(row["pdf_page"], row["label_segment"]) for row in labels.observations("I")] == [(2, "front"), (30, "appendix")]


def test_ranges_require_unique_real_endpoints_within_same_known_segment():
    labels = OutlineLabels([page(2, "10", "one"), page(5, "20", "one"), page(10, "10", "two"), page(11, "20", "two")], {})
    assert [(row["pdf_page"], row["range_end_pdf_page"]) for row in labels.observations("10–20")] == [(2, 5), (10, 11)]
    assert not OutlineLabels([page(2, "10"), page(5, "20")], {}).observations("10–20")
    assert not OutlineLabels([page(2, "10", "one"), page(5, "20", "one"), page(6, "20", "one")], {}).observations("10–20")
    assert not OutlineLabels([page(5, "10", "one"), page(2, "20", "one")], {}).observations("10–20")


def test_missing_labels_refer_to_existing_neighbor_only_and_make_no_physical_page():
    labels = OutlineLabels([page(3, "A-1", "appendix")], {"missing": [{"label": "A-2", "after_pdf_page": 3}, {"label": "99", "after_pdf_page": 999}]})
    assert labels.has_missing_label("A-2")
    assert not labels.observations("A-2")
    assert not labels.has_missing_label("99")
    assert labels.observations("a－1")[0]["pdf_page"] == 3
