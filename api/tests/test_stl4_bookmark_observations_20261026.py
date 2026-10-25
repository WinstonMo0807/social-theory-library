"""Deferred native title/page checks; no PDF or test execution during development."""
from copy import deepcopy
import re

import pytest

from catalog.services.outline_bookmarks import BookmarkObservations


def node(title="Chapter 1 Introduction", page=2, identifier="original"):
    return {"id": identifier, "title": title, "pdf_page": page, "pdf_position": [72, 36],
            "parent_id": None, "source": "pdf_bookmark", "calibration_status": "native"}


def review(nodes, observed, contents=()):
    verifier = BookmarkObservations([[1, row["title"], row["pdf_page"]] for row in nodes])
    for page, title in observed:
        verifier.observe(page, title)
    return verifier, verifier.review(nodes, set(contents), lambda title: re.fullmatch(r"contents", title, re.I))


def test_exact_title_at_original_page_keeps_native_but_does_not_confirm_it():
    nodes = [node("Ｃｈａｐｔｅｒ １ Introduction")]
    _, problems = review(nodes, [(2, "Chapter 1 Introduction")])
    assert not problems and nodes[0]["calibration_status"] == "native"
    assert nodes[0]["pdf_page"] == 2 and nodes[0]["pdf_position"] == [72, 36]


@pytest.mark.parametrize("observed,code", [
    ([], "bookmark_title_unverified"),
    ([(2, "Chapter 2 Introduction")], "bookmark_title_unverified"),
    ([(3, "Chapter 1 Introduction")], "bookmark_target_mismatch"),
    ([(2, "Chapter 1 Introduction"), (3, "Chapter 1 Introduction")], "bookmark_title_repeated"),
])
def test_missing_wrong_and_repeated_titles_never_retarget_original_nodes(observed, code):
    nodes = [node()]
    original = deepcopy(nodes[0])
    _, problems = review(nodes, observed)
    assert problems[0]["code"] == code and nodes[0]["calibration_status"] == "needs_review"
    assert {k: v for k, v in nodes[0].items() if k != "calibration_status"} == {k: v for k, v in original.items() if k != "calibration_status"}


def test_contents_listing_cannot_verify_an_incorrect_body_target():
    nodes = [node(page=1), node("Contents", 1, "contents")]
    _, problems = review(nodes, [(1, "Chapter 1 Introduction"), (1, "Contents")], contents=[1])
    assert problems[0]["node_id"] == "original"
    assert nodes[0]["calibration_status"] == "needs_review" and nodes[1]["calibration_status"] == "native"


def test_duplicate_nodes_and_url_titles_remain_available_for_manual_repair():
    nodes = [node(), node(identifier="duplicate"), node("https://example.invalid", 3, "url")]
    _, problems = review(nodes, [(2, "Chapter 1 Introduction"), (3, "https://example.invalid")])
    assert [problem["code"] for problem in problems] == ["duplicate_bookmark", "duplicate_bookmark", "bookmark_title_unverified"]
    assert len(nodes) == 3 and all(row["calibration_status"] == "needs_review" for row in nodes)


def test_observation_memory_is_bounded_and_late_original_target_is_kept():
    nodes = [node(page=1000)]
    verifier, problems = review(nodes, [(page, "Chapter 1 Introduction") for page in range(1, 1001)])
    assert len(next(iter(verifier.pages.values()))) <= 22
    assert 1000 in next(iter(verifier.pages.values()))
    assert problems[0]["observed_page_count_is_lower_bound"] is True
    assert problems[0]["code"] == "bookmark_title_repeated"


def test_wrapped_native_text_is_observed_without_inventing_a_heading():
    nodes = [node()]
    verifier = BookmarkObservations([[1, nodes[0]["title"], 2]])
    verifier.observe_blocks(2, [{"type": 0, "lines": [
        {"spans": [{"text": "Chapter 1"}]}, {"spans": [{"text": "Introduction"}]}]}])
    assert not verifier.review(nodes, set(), lambda title: False)
