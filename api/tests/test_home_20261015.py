"""Homepage publication, privacy and truthful section-state boundaries."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.utils import timezone

from catalog.models import (
    Edition, EditorialRevision, Person, PublicationState, RecommendationIssue,
    RecommendationItem, RecommendationPolicy, RecommendationSnapshot, ScholarProfile,
    SearchQueryAggregate, Topic, Work,
)
from .v304_helpers import activate_catalog_revision


@pytest.mark.django_db
def test_empty_home_is_truthful_and_does_not_initialize_recommendations(api_client):
    # Migration 0009 seeds policies; exercise an actually uninitialized home.
    RecommendationPolicy.objects.all().delete()
    response = api_client.get("/api/catalog/home/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "empty"
    assert payload["issue"] is None and payload["issue_count"] == 0
    for key in ("works", "random_works", "topics", "scholars", "issues", "hot_searches"):
        assert payload[key] == []
        assert payload["sections"][key]["status"] == "empty"
        assert payload["sections"][key]["count"] == 0
    assert payload["config"]["home_title_left_lines"] == ["连接思想，"]
    assert not RecommendationPolicy.objects.exists()
    assert not RecommendationSnapshot.objects.exists()


@pytest.mark.django_db
def test_home_rechecks_public_targets_and_uses_published_snapshots(api_client, admin_user):
    work = Work.objects.create(title="已发布作品", document_type="book")
    edition = Edition.objects.create(work=work, state=PublicationState.PUBLISHED, is_primary=True, public_slug="home-public")
    activate_catalog_revision(edition, fulltext_ready=False)
    Work.objects.filter(pk=work.pk).update(title="未发布的书名修改")
    hidden = Work.objects.create(title="仅有发布状态", document_type="book")
    Edition.objects.create(work=hidden, state=PublicationState.PUBLISHED, is_primary=True, public_slug="home-hidden")
    topic = Topic.objects.create(name="公开主题", slug="home-public", editorial_status="published")
    hidden_topic = Topic.objects.create(name="已撤回主题", slug="home-withdrawn", editorial_status="archived")
    person = Person.objects.create(preferred_name="已核验学者", authority_status="verified")
    scholar = ScholarProfile.objects.create(person=person, slug="home-scholar", editorial_status="published")
    unverified = Person.objects.create(preferred_name="未核验人物")
    ScholarProfile.objects.create(person=unverified, slug="home-unverified", editorial_status="published")
    now = timezone.now()
    policy, _ = RecommendationPolicy.objects.get_or_create(placement="home_topics", defaults={"title": "首页主题"})
    snapshot = RecommendationSnapshot.objects.create(policy=policy, starts_at=now-timedelta(days=1), expires_at=now+timedelta(days=1))
    RecommendationItem.objects.create(snapshot=snapshot, position=0, topic=hidden_topic)
    RecommendationItem.objects.create(snapshot=snapshot, position=1, topic=topic)
    for query, count, excluded in (("社会理论", 4, False), ("单人检索", 1, False), ("匿名排除", 8, True), ("private@example.org", 9, False)):
        SearchQueryAggregate.objects.create(period_start=timezone.localdate(), normalized_query=query,
                                            search_count=count, unique_sessions=count, excluded=excluded)
    for index in range(6):
        issue = RecommendationIssue.objects.create(slug=f"home-issue-{index}", title="尚未发布的编辑稿")
        revision = EditorialRevision.objects.create(
            target_type="recommendation_issue", target_id=issue.pk, revision=1,
            idempotency_key=f"home-issue-{index}", status="published", published_at=now,
            materialized_preview={"title": f"已发布策划{index}", "body_blocks": [], "items": []},
        )
        issue.active_revision = revision
        issue.display_from = now-timedelta(days=index) if index < 5 else now+timedelta(days=1)
        issue.save()
    policy_count = RecommendationPolicy.objects.count()
    response = api_client.get("/api/catalog/home/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert [(row["id"], row["title"]) for row in payload["works"]] == [(str(work.pk), "已发布作品")]
    assert [row["id"] for row in payload["topics"]] == [str(topic.pk)]
    assert [row["id"] for row in payload["scholars"]] == [str(scholar.pk)]
    assert payload["hot_searches"] == ["社会理论"]
    assert [row["title"] for row in payload["issues"]] == [f"已发布策划{index}" for index in range(4)]
    assert payload["issue"] == payload["issues"][0]
    assert payload["issue_count"] == 5
    assert RecommendationPolicy.objects.count() == policy_count
    assert RecommendationSnapshot.objects.count() == 1
    api_client.force_authenticate(admin_user)
    assert api_client.get("/api/catalog/home/").json() == payload


@pytest.mark.django_db
def test_home_section_failure_is_not_an_empty_success(api_client):
    with patch("catalog.home_views._home_issues", side_effect=OperationalError("private internal diagnostic")):
        response = api_client.get("/api/catalog/home/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["issue_count"] is None
    assert payload["sections"]["issues"] == {
        "status": "unavailable", "source": "unavailable", "count": None,
        "message": "特别策划暂时无法加载，请稍后重试。",
    }
    assert payload["sections"]["works"]["status"] == "empty"
    assert "private internal diagnostic" not in str(payload)
