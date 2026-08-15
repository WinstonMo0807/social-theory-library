from ingestion.services.metadata import Candidate, overall_confidence, select_best
from ingestion.services.metadata_scoring import calibrate_candidate


def test_independent_source_agreement_is_auditable():
    candidates = [
        Candidate("title", "规训与惩罚", "pdf_metadata", 0.72, {"page": 1}),
        Candidate("title", "规训与惩罚", "google_books", 0.72, {"record_url": "https://example.test/1"}),
        Candidate("title", "规训与处罚", "first_pages", 0.86, {"page": 1}),
    ]

    selected = select_best(candidates)
    score = calibrate_candidate(candidates[0], candidates)

    assert selected["title"] == "规训与惩罚"
    assert score.factors["independent_sources"] == 2
    assert score.factors["calibration_version"] == "metadata-candidate-v1"


def test_llm_self_reported_confidence_is_not_trusted():
    llm = Candidate("publisher", "错误出版社", "local_llm", 0.99, {})
    page = Candidate("publisher", "三联书店", "pdf_copyright_page", 0.78, {"page": 4})

    selected = select_best([llm, page])
    llm_score = calibrate_candidate(llm, [llm, page])

    assert selected["publisher"] == "三联书店"
    assert llm_score.factors["declared_confidence_used"] is False


def test_overall_confidence_uses_calibrated_scores():
    candidates = [
        Candidate("title", "社会学的想象力", "pdf_title_page", 0.9, {"page": 1}),
        Candidate("authors", ["赖特·米尔斯"], "pdf_title_page", 0.9, {"page": 1}),
        Candidate("document_type", "book", "first_pages", 0.72, {"page": 1}),
        Candidate("publication_year", 1959, "pdf_copyright_page", 0.9, {"page": 4}),
    ]
    selected = select_best(candidates)

    assert 0.7 < overall_confidence(candidates, selected) <= 0.99
