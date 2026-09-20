from datetime import timedelta

import pytest
from django.utils import timezone

from catalog.models import KnowledgeNode, ReadingPath, ReadingPathItem, TheoryTimelineEvent

pytestmark = pytest.mark.django_db


def test_public_theory_directory_sorts_all_pages_and_preserves_public_filter(api_client):
    nodes = []
    for index in range(27):
        row = KnowledgeNode.objects.create(canonical_name_zh=f"Node {index:02}", node_type="theory_tradition", slug=f"directory-{index}", status="published")
        KnowledgeNode.objects.filter(pk=row.pk).update(updated_at=timezone.now() - timedelta(days=index))
        nodes.append(row)
    KnowledgeNode.objects.create(canonical_name_zh="Unpublished", node_type="theory_tradition", slug="private-directory", status="draft")
    response = api_client.get("/api/catalog/theory-system/nodes/?type=theory_tradition&sort=updated&page=2")
    assert response.status_code == 200
    assert response.data["count"] == 27
    assert [row["id"] for row in response.data["results"]] == [str(row.pk) for row in nodes[24:]]
    named = api_client.get("/api/catalog/theory-system/nodes/?sort=name").data
    assert named["results"][0]["canonical_name_zh"] == "Node 00"
    assert api_client.get("/api/catalog/theory-system/nodes/?sort=unsafe").status_code == 400


def test_public_timeline_year_filter_overlaps_actual_ranges(api_client):
    for title, start, end, state in [("Single", 1905, None, "approved"), ("Range", 1890, 1920, "approved"),
                                    ("Before", 1870, 1880, "approved"), ("After", 1950, None, "approved"),
                                    ("Unknown", None, None, "approved"), ("Unpublished", 1905, None, "suggested")]:
        TheoryTimelineEvent.objects.create(title=title, event_type="development", start_year=start, end_year=end, review_status=state)
    response = api_client.get("/api/catalog/theory-system/timeline/?year_from=1900&year_to=1910")
    assert response.status_code == 200
    assert {row["title"] for row in response.data["results"]} == {"Single", "Range"}
    assert api_client.get("/api/catalog/theory-system/timeline/").data["count"] == 5
    assert api_client.get("/api/catalog/theory-system/timeline/?year_from=1951").data["count"] == 0
    assert api_client.get("/api/catalog/theory-system/timeline/?year_from=1910&year_to=1900").status_code == 400
    assert api_client.get("/api/catalog/theory-system/timeline/?year_from=not-a-year").status_code == 400


def test_reading_path_node_filter_counts_all_associated_public_paths(api_client):
    node = KnowledgeNode.objects.create(canonical_name_zh="路径范围", node_type="theory_tradition", slug="path-scope", status="published")
    hidden = KnowledgeNode.objects.create(canonical_name_zh="内部节点", node_type="concept", slug="hidden-path-scope", status="draft")
    for index in range(28):
        path = ReadingPath.objects.create(title=f"阅读路径 {index:02}", slug=f"node-path-{index}", status="published")
        ReadingPathItem.objects.create(reading_path=path, node=node if index < 27 else hidden)
        if index == 0:
            ReadingPathItem.objects.create(reading_path=path, node=node, reading_order=2)
    response = api_client.get("/api/catalog/theory-system/reading-paths/?node=path-scope&page=2")
    assert response.status_code == 200
    assert response.data["count"] == 27
    assert len(response.data["results"]) == 3
    assert api_client.get("/api/catalog/theory-system/reading-paths/?node=hidden-path-scope").data["count"] == 0
