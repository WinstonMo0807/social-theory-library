"""Issue categories follow confirmed revision visibility, including schedules."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.services import editorial_issues as service
from tests.test_v307_editorial_issues import issue_data

pytestmark = pytest.mark.django_db


def test_issue_category_draft_does_not_replace_public_category(api_client, admin_user):
    issue = service.create_issue({**issue_data(), "category": " 理论阅读 "}, admin_user)
    assert service.issue_payload(issue)["category"] == "理论阅读"
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    service.save_issue(issue.pk, {**service.issue_payload(issue), "category": "未确认分类"}, admin_user)
    draft = service.create_issue({**issue_data(), "category": "纯草稿栏目"}, admin_user)
    public = api_client.get("/api/catalog/recommendation-issues/")
    assert public.status_code == 200
    assert public.data["categories"] == ["理论阅读"]
    assert public.data["results"][0]["category"] == "理论阅读"
    assert public.data["results"][0]["id"] == str(issue.pk)
    assert all(row["id"] != str(draft.pk) for row in public.data["results"])
    assert api_client.get("/api/catalog/recommendation-issues/", {"category": "未确认分类"}).data["results"] == []


def test_issue_category_filter_paginates_and_keeps_filtered_lead(api_client, admin_user):
    selected = []
    for index in range(13):
        issue = service.create_issue({**issue_data(), "title": f"栏目检索验收 {index}", "category": "研究方法"}, admin_user)
        service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
        selected.append(str(issue.pk))
    other = service.create_issue({**issue_data(), "title": "栏目检索验收另一栏目", "category": "理论阅读"}, admin_user)
    service.publish_issue(other.pk, service.issue_payload(other)["edit_version"], admin_user)
    first = api_client.get("/api/catalog/recommendation-issues/", {"category": "研究方法", "q": "栏目检索验收"})
    assert first.status_code == 200 and first.data["count"] == 13
    assert first.data["current"]["id"] in selected
    assert len(first.data["results"]) == 12 and "category=" in first.data["next"] and "q=" in first.data["next"]
    second = api_client.get(first.data["next"])
    assert second.status_code == 200 and len(second.data["results"]) == 1
    assert {row["id"] for row in first.data["results"] + second.data["results"]} == set(selected)
    assert all(row["category"] == "研究方法" for row in first.data["results"] + second.data["results"])
    missing = api_client.get("/api/catalog/recommendation-issues/", {"category": "没有这个栏目"})
    assert missing.data["results"] == [] and missing.data["current"] is None
    assert set(missing.data["categories"]) == {"研究方法", "理论阅读"}


def test_issue_category_schedule_uses_due_published_snapshot(api_client, admin_user, monkeypatch):
    now = timezone.now()
    monkeypatch.setattr(timezone, "now", lambda: now)
    issue = service.create_issue({**issue_data(), "category": "当前栏目"}, admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    service.save_issue(issue.pk, {**service.issue_payload(issue), "category": "未来栏目", "display_from": (now + timedelta(days=1)).isoformat()}, admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    service.save_issue(issue.pk, {**service.issue_payload(issue), "category": "未确认分类"}, admin_user)
    before = api_client.get("/api/catalog/recommendation-issues/")
    assert before.data["categories"] == ["当前栏目"]
    assert before.data["results"][0]["category"] == "当前栏目"
    monkeypatch.setattr(timezone, "now", lambda: now + timedelta(days=2))
    after = api_client.get("/api/catalog/recommendation-issues/", {"category": "未来栏目"})
    assert after.data["categories"] == ["未来栏目"] and after.data["count"] == 1
    assert after.data["current"]["category"] == "未来栏目"


@pytest.mark.parametrize("category", ["x" * 81, 123])
def test_issue_category_rejects_nontext_or_excessive_length(admin_user, category):
    with pytest.raises(ValidationError):
        service.create_issue({**issue_data(), "category": category}, admin_user)
