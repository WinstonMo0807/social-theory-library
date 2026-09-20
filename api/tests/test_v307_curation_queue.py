"""Missing secondary-page inventory: SQL pagination and permission boundaries."""
from uuid import uuid4
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import User
from catalog.models import (Discipline, EditorialRevision, KnowledgeNode, LegacyKnowledgeMapping, Person,
                            ReadingPath, ScholarProfile, SiteSetting, Subdiscipline, TheorySchool, Topic)
from catalog.services import editorial_issues as issues

pytestmark = pytest.mark.django_db


def draft(kind, target, revision=1, status="draft", **payload):
    return EditorialRevision.objects.create(target_type=kind, target_id=target.pk, revision=revision,
        materialized_preview=payload, status=status, idempotency_key=f"curation-test:{uuid4()}")


def test_curation_queue_counts_sql_pages_and_one_row_per_object(api_client, admin_user):
    for index in range(37):
        topic = Topic.objects.create(name=f"策展 {index:03}", slug=f"curation-{index}")
        if index == 0:
            draft("topic", topic, name="旧稿")
            draft("topic", topic, 2, name="策展最新稿")
    api_client.force_authenticate(admin_user)
    with CaptureQueriesContext(connection) as captured:
        response = api_client.get("/api/catalog/admin/curation-drafts/?q=策展&page=2")
    assert response.status_code == 200
    assert response.data["count"] == 37
    assert response.data["total_pages"] == 2
    assert len(response.data["results"]) == 7
    assert len({row["id"] for row in response.data["results"]}) == 7
    assert any("LIMIT 7 OFFSET 30" in row["sql"] or "LIMIT 30 OFFSET 30" in row["sql"] for row in captured.captured_queries)
    assert any("COUNT(*)" in row["sql"] and "UNION ALL" in row["sql"] for row in captured.captured_queries)
    result = api_client.get("/api/catalog/admin/curation-drafts/?q=最新稿").data
    assert result["count"] == 1
    assert result["results"][0]["title"] == "策展最新稿"


def test_curation_queue_excludes_finished_revision_and_preserves_draft_title(api_client, admin_user):
    finished = Topic.objects.create(name="已完成", slug="completed", editorial_status="published")
    draft("topic", finished, name="历史草稿")
    draft("topic", finished, 2, status="published", name="已完成")
    pending = Topic.objects.create(name="公开名称", slug="changed", editorial_status="published")
    draft("topic", pending, name="待发布新名称")
    api_client.force_authenticate(admin_user)
    response = api_client.get("/api/catalog/admin/curation-drafts/")
    rows = {row["object_id"]: row for row in response.data["results"]}
    assert str(finished.pk) not in rows
    assert rows[str(pending.pk)]["title"] == "待发布新名称"
    assert rows[str(pending.pk)]["state"] == "changes_pending"
    assert rows[str(pending.pk)]["edit_url"] == f"/admin/topics/{pending.pk}"
    assert response["Cache-Control"] == "private, no-store"


def test_curation_queue_includes_initial_drafts_and_exact_editor_routes(api_client, admin_user):
    discipline = Discipline.objects.create(name="社会学草稿", slug="discipline-draft", code="sociology-draft")
    sub = Subdiscipline.objects.create(name="子学科草稿", slug="sub-draft", discipline=discipline)
    scholar = ScholarProfile.objects.create(person=Person.objects.create(preferred_name="学者草稿"), slug="scholar-draft")
    node = KnowledgeNode.objects.create(canonical_name_zh="理论草稿", node_type="theory_tradition", slug="node-draft")
    path = ReadingPath.objects.create(title="路径草稿", slug="path-draft")
    draft("scholar_profile", scholar, person={"preferred_name": "新的学者草稿"})
    api_client.force_authenticate(admin_user)
    response = api_client.get("/api/catalog/admin/curation-drafts/")
    rows = {row["object_id"]: row for row in response.data["results"]}
    expected = {discipline.pk: f"/admin/theories/disciplines?discipline={discipline.pk}",
                sub.pk: f"/admin/theories/subdisciplines?subdiscipline={sub.pk}",
                scholar.pk: f"/admin/scholars/{scholar.pk}", node.pk: f"/admin/theories/{node.pk}",
                path.pk: f"/admin/theories/reading-paths?path={path.pk}"}
    for key, url in expected.items():
        assert rows[str(key)]["edit_url"] == url
    assert rows[str(scholar.pk)]["title"] == "新的学者草稿"


def test_curation_queue_site_permission_and_private_boundary(api_client, admin_user, reader_user):
    setting, _ = SiteSetting.objects.get_or_create(key="site_config", defaults={"value": {}})
    latest = EditorialRevision.objects.filter(target_type="site_content", target_id=setting.pk).order_by("-revision").first()
    draft("site_content", setting, (latest.revision if latest else 0) + 1)
    issue = issues.create_issue({"title": "推荐期草稿"}, admin_user)
    api_client.force_authenticate(admin_user)
    data = api_client.get("/api/catalog/admin/curation-drafts/").data
    assert {"site_content", "recommendation_issue"} <= {row["object_type"] for row in data["results"]}
    editor = User.objects.create_user(username="curation-editor", role="editor")
    api_client.force_authenticate(editor)
    data = api_client.get("/api/catalog/admin/curation-drafts/").data
    assert "site_content" not in {row["object_type"] for row in data["results"]}
    assert str(issue.pk) in {row["object_id"] for row in data["results"]}
    api_client.force_authenticate(reader_user)
    assert api_client.get("/api/catalog/admin/curation-drafts/").status_code == 403
    api_client.force_authenticate(None)
    assert api_client.get("/api/catalog/admin/curation-drafts/").status_code in (401, 403)


def test_legacy_theory_redirect_only_uses_verified_public_identity(api_client):
    legacy = TheorySchool.objects.create(name="精确映射", slug="legacy-theory", editorial_status="published")
    node = KnowledgeNode.objects.create(canonical_name_zh="精确映射", node_type="theory_tradition", slug="mapped-theory", status="published")
    mapping = LegacyKnowledgeMapping.objects.create(legacy_model="TheorySchool", legacy_id=legacy.pk, node=node, migration_status="mapped")
    url = f"/api/catalog/theory-schools/{legacy.slug}/"
    assert api_client.get(url).data["canonical_node_url"] == "/theories/nodes/mapped-theory"
    node.status = "draft"
    node.save(update_fields=["status"])
    assert api_client.get(url).data["canonical_node_url"] == ""
    node.status = "published"
    node.canonical_name_zh = "另一个身份"
    node.save(update_fields=["status", "canonical_name_zh"])
    assert api_client.get(url).data["canonical_node_url"] == ""
