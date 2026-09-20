"""The queue must paginate its inventory before loading rich edition data."""
from unittest.mock import patch
from datetime import timedelta

import pytest
from django.utils import timezone

from catalog.models import Edition, Work
from catalog.services import admin_queue
from catalog.services.admin_queue_query import next_queue_item, queue_page
from catalog.services.admin_queue_query import edition_inventory
from ingestion.models import ProcessingJob

pytestmark = pytest.mark.django_db


def test_queue_ordering_is_applied_before_sql_pagination(api_client, admin_user):
    start = timezone.now() - timedelta(days=40)
    editions = []
    for index in range(35):
        edition = Edition.objects.create(work=Work.objects.create(title=f"排序 {index:02}"), publication_mode="bibliographic")
        date = start + timedelta(days=index)
        Edition.objects.filter(pk=edition.pk).update(updated_at=date)
        Work.objects.filter(pk=edition.work_id).update(updated_at=date)
        editions.append(edition)
    page, _, rows, _ = queue_page(user=admin_user, ordering="-updated_at", page=2)
    assert page.paginator.count == 35
    assert [row["edition_id"] for row in rows] == [str(row.pk) for row in reversed(editions[:5])]
    _, _, ascending, _ = queue_page(user=admin_user, ordering="updated_at", page=1)
    assert ascending[0]["edition_id"] == str(editions[0].pk)
    api_client.force_authenticate(admin_user)
    assert api_client.get("/api/catalog/admin/workflows/queue/?ordering=title").status_code == 400


def test_queue_filters_and_counts_before_hydrating_relations(admin_user):
    for index in range(67):
        Edition.objects.create(work=Work.objects.create(title=f"分页馆藏 {index:03}"), publication_mode="bibliographic")
    sizes = []
    original = admin_queue.load_admin_editions
    def bounded(queryset):
        sizes.append(queryset.count())
        return original(queryset)
    with patch.object(admin_queue, "load_admin_editions", side_effect=bounded):
        page, counts, rows, _ = queue_page(user=admin_user, page=2)
    assert page.paginator.count == 67
    assert counts["all"] == 67
    assert len(rows) == 30
    assert max(sizes) <= 42  # page plus bounded compatibility preview, not all editions
    filtered, _, matches, _ = queue_page(user=admin_user, query="分页馆藏 066")
    assert filtered.paginator.count == 1
    assert [row["title"] for row in matches] == ["分页馆藏 066"]


def test_next_item_uses_full_count_without_loading_every_workspace(admin_user):
    editions = [Edition.objects.create(work=Work.objects.create(title=f"下一本 {i}"), publication_mode="bibliographic") for i in range(34)]
    with patch.object(admin_queue, "load_admin_editions", wraps=admin_queue.load_admin_editions) as loader:
        row, count = next_queue_item(user=admin_user, exclude_edition=editions[0].pk)
    assert count == 33
    assert row["edition_id"] != str(editions[0].pk)
    assert loader.call_args.args[0].count() == 1


def test_resolved_old_processing_failure_does_not_remain_a_current_exception():
    edition = Edition.objects.create(work=Work.objects.create(title="已重试的处理"), publication_mode="bibliographic")
    ProcessingJob.objects.create(edition=edition, job_type="ocr", status="failed")
    assert edition_inventory().get(pk=edition.pk).q_failed_job is True
    ProcessingJob.objects.create(edition=edition, job_type="ocr", status="succeeded")
    assert edition_inventory().get(pk=edition.pk).q_failed_job is False
