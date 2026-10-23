"""Deferred acceptance: a task result link must not widen to other materials."""
from urllib.parse import parse_qs, urlsplit

import pytest

from catalog.models import TheoryReviewTask
from ingestion.models import ProcessingJob
from ingestion.services.processing_identity import concept_review_url
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/theory-system/review-tasks/"


def test_task_result_scope_is_exact_and_invalid_identity_is_rejected(api_client, admin_user, settings, tmp_path):
    settings.THEORY_SYSTEM_ENABLED = True
    work_a, edition_a, _, file_a = create_item_with_files(settings, tmp_path, title="来源甲")
    work_b, _, _, file_b = create_item_with_files(settings, tmp_path, title="来源乙")
    exact = TheoryReviewTask.objects.create(task_type="new_node", work=work_a, file=file_a, suggested_node_name="甲候选")
    TheoryReviewTask.objects.create(task_type="new_node", work=work_a, suggested_node_name="未绑定文件")
    TheoryReviewTask.objects.create(task_type="new_node", work=work_b, file=file_b, suggested_node_name="乙候选")
    job = ProcessingJob.objects.create(job_type="text_extraction", edition=edition_a, asset=file_a, stats={"operation": "concept_alignment"})
    url = urlsplit(concept_review_url(job))
    scope = parse_qs(url.query)
    assert scope["review_work"] == [str(work_a.pk)] and scope["review_file"] == [str(file_a.pk)]
    assert scope["processing_task"] == [str(job.pk)] and scope["review_status"] == ["all"]
    api_client.force_authenticate(admin_user)
    response = api_client.get(URL, {"work": str(work_a.pk), "file": str(file_a.pk)})
    assert response.status_code == 200, response.data
    assert [row["id"] for row in response.data["results"]] == [str(exact.pk)]
    assert api_client.get(URL, {"work": str(work_a.pk)}).data["count"] == 2
    assert api_client.get(URL, {"work": str(work_b.pk), "file": str(file_a.pk)}).data["count"] == 0
    for field in ("work", "file"):
        assert api_client.get(URL, {field: "invalid-source"}).status_code == 400
