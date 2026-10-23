"""Deferred acceptance: partial stage results share counts, filters and detail."""
from unittest.mock import patch

import pytest

from ingestion.models import ProcessingJob
from ingestion.services.processing_outcomes import outcome_issues, workspace_status
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-workspace/"


@pytest.mark.parametrize("key", ["theory_suggestion_warning", "page_label_warning", "ocr_pdf_warning", "front_matter_warning", "publication_place_warning", "taxonomy_candidate_warning"])
def test_partial_stage_is_discoverable_and_raw_error_is_private(api_client, admin_user, settings, tmp_path, key):
    _, edition, _, asset = create_item_with_files(settings, tmp_path)
    private_error = "internal-provider-detail-must-stay-private"
    job = ProcessingJob.objects.create(job_type="ocr", status="succeeded", progress=100, edition=edition, asset=asset,
        stats={key: private_error, "completed_page_indexes": [1]})
    api_client.force_authenticate(admin_user)
    with patch("ingestion.services.processing.dispatch_ocr_job") as dispatch:
        for grouping in ("task", "file"):
            failed = api_client.get(URL, {"group_by": grouping, "status": "failed"})
            assert failed.status_code == 200, failed.data
            assert failed.data["count"] == 1 and failed.data["counts"]["failed"] == 1
            row = failed.data["results"][0]
            assert row["status"] == "succeeded" and row["partial"] is True
            assert row["outcome_issues"][0]["code"] == key
            assert "retry" not in row["actions"] and row["can_export_results"] is True
            assert private_error not in str(failed.data)
            assert api_client.get(URL, {"group_by": grouping, "status": "succeeded"}).data["count"] == 0
    dispatch.assert_not_called()
    job.refresh_from_db()
    assert job.status == "succeeded" and job.stats[key] == private_error


def test_recorded_alignment_outcome_supersedes_old_warning(settings, tmp_path):
    _, edition, _, asset = create_item_with_files(settings, tmp_path)
    job = ProcessingJob.objects.create(job_type="ocr", status="succeeded", edition=edition, asset=asset,
        stats={"theory_suggestion_warning": "old failure", "concept_alignment": {"state": "completed"}})
    def visible_state():
        return ProcessingJob.objects.filter(pk=job.pk).annotate(view_state=workspace_status()).values_list("view_state", flat=True).get()
    assert visible_state() == "succeeded"
    assert outcome_issues(job, files_url="", workbench_url="") == []
    job.stats = {"concept_alignment": {"state": "failed"}}
    job.save(update_fields=["stats", "updated_at"])
    assert visible_state() == "failed"
    assert outcome_issues(job, files_url="", workbench_url="")[0]["code"] == "theory_suggestion_warning"
    for stats in ({}, {"page_label_warning": ""}, {"page_label_warning": None}):
        job.stats = stats
        job.save(update_fields=["stats", "updated_at"])
        assert visible_state() == "succeeded"
        assert outcome_issues(job, files_url="", workbench_url="") == []
