"""Recorded associations, heading levels and manual comparison; acceptance deferred."""
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from catalog.models import KnowledgeNode, KnowledgeRelation, PersonNodeRelation
from catalog.services import editorial_assistance as assistant, editorial_issues as ledger
from catalog.services.editorial_selection import related
from .test_issue_selection_20261022 import chosen, generated_job, review
from .test_issue_workbench_20261022 import new_issue, command
from .test_public_scholars_20261021 import profile
from .test_v307_editorial_issues import public_edition

pytestmark = pytest.mark.django_db


def test_related_graph_uses_published_edges_and_public_people_only(admin_user):
    issue, origin, _ = chosen(admin_user)
    visible = KnowledgeNode.objects.create(canonical_name_zh="隔离验收相邻概念", node_type="concept", slug=f"related-{uuid4().hex}", status="published")
    hidden = KnowledgeNode.objects.create(canonical_name_zh="未发布概念", node_type="concept", slug=f"related-{uuid4().hex}", status="draft")
    for target in [visible, hidden]:
        KnowledgeRelation.objects.create(source_node=origin, target_node=target, relation_type="extends", status="published")
    scholar, draft = profile("公开关系作者"), profile("尚未公开作者")
    draft.editorial_status = "draft"
    draft.save(update_fields=["editorial_status"])
    for row in [scholar, draft]:
        PersonNodeRelation.objects.create(person=row.person, node=origin, relation_label="原编目关系标签", status="published")
    rows, details = related(issue, "node")
    assert [row["target"]["id"] for row in rows] == [str(visible.pk)]
    assert "扩展" in rows[0]["reasons"][0]
    people, _ = related(issue, "person")
    assert [row["target"]["id"] for row in people] == [str(scholar.person_id)]
    assert "原编目关系标签" in people[0]["reasons"][0]
    assert details["edit_version"] == ledger.edit_version("recommendation_issue", issue.pk)
    KnowledgeNode.objects.filter(pk=origin.pk).update(status="draft")
    rows, details = related(issue, "node")
    assert rows == [] and details["unavailable_count"] == 1


def test_related_edition_uses_formal_author_and_knowledge_snapshot(admin_user):
    author, chapter_author = profile("整版作者"), profile("章作者")
    node = KnowledgeNode.objects.create(canonical_name_zh="版本编目概念", node_type="concept", slug=f"edition-node-{uuid4().hex}", status="published")
    edition = public_edition(snapshot={"work": {"title": "正式版本"}, "contributions": [
        {"role": "author", "person_id": str(author.person_id), "name": author.person.preferred_name},
        {"role": "author", "person_id": str(chapter_author.person_id), "name": chapter_author.person.preferred_name, "scope": {"kind": "chapter", "chapters": []}}],
        "knowledge": {"nodes": [{"id": str(node.pk)}]}})
    issue = new_issue(admin_user, selection_workspace={"references": [{"type": "work", "id": str(edition.work_id), "edition_id": str(edition.pk)}]})
    people, _ = related(issue, "person")
    assert [row["target"]["id"] for row in people] == [str(author.person_id)]
    nodes, _ = related(issue, "node")
    assert nodes[0]["target"]["id"] == str(node.pk)
    assert "不据此断言" in nodes[0]["reasons"][0]
    assert ledger.issue_draft_payload(issue)["body_blocks"][0]["text"] == "人工导读"


def test_related_endpoint_permissions_pagination_and_private_response(api_client, admin_user, reader_user):
    issue, node, _ = chosen(admin_user)
    for index in range(25):
        target = KnowledgeNode.objects.create(canonical_name_zh=f"候选{index:02d}", node_type="concept", slug=f"candidate-{uuid4().hex}", status="published")
        KnowledgeRelation.objects.create(source_node=node, target_node=target, relation_type="extends", status="published")
    url = f"/api/catalog/admin/recommendation-issues/{issue.pk}/sources/"
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, {"related": "node"}).status_code == 403
    api_client.force_authenticate(admin_user)
    first = api_client.get(url, {"related": "node"})
    assert first.status_code == 200 and first["Cache-Control"] == "private, no-store"
    assert first.data["count"] == 25 and len(first.data["results"]) == 24
    assert "related=node" in first.data["next"]
    second = api_client.get(url, {"related": "node", "page": 2})
    assert len(second.data["results"]) == 1 and not second.data["next"]
    assert api_client.get(url, {"related": "private-notes"}).status_code == 400


def generate(actor, candidates):
    issue, node, job, _ = generated_job(actor)
    job.status, job.stats = "pending", {**job.stats, "suggestions": []}
    job.save(update_fields=["status", "stats"])
    original = ledger.issue_draft_payload(issue)["body_blocks"][0]
    with patch("reading.local_analysis.generate_local", return_value=({"suggestions": candidates(original)}, {"model": "isolated-fixture"})):
        result = assistant.run_assistance(job.pk, job.task_id)
    return issue, original, result


def test_outline_levels_and_original_text_survive_review_without_replacing_manual_prose(admin_user):
    def candidates(original):
        return [{"kind": "heading", "text": "第一节", "level": 1, "source_keys": [], "gap": "", "target_block_id": None},
                {"kind": "heading", "text": "子节", "level": 2, "source_keys": ["s1"], "gap": "", "target_block_id": None},
                {"kind": "paragraph", "text": "针对人工段落的建议", "level": 0, "source_keys": ["s1"], "gap": "", "target_block_id": original["id"], "original_text": "模型伪造的旧文字不得采用"}]
    issue, original, job = generate(admin_user, candidates)
    assert job.status == "succeeded"
    rows = job.stats["suggestions"]
    assert rows[2]["original_text"] == original["text"] and rows[2]["target_block_id"] == original["id"]
    assistant.assistance_action(job.pk, review(job, rows[0], suggestion_ids=[row["id"] for row in rows]), admin_user)
    blocks = ledger.issue_draft_payload(issue)["body_blocks"]
    assert blocks[0] == original
    assert [block["heading_level"] for block in blocks[1:3]] == [1, 2]
    assert blocks[3]["text"] == rows[2]["text"]
    assert issue.active_revision_id is None


def test_invalid_level_or_target_keeps_only_earlier_complete_candidate(admin_user):
    for invalid in ({"kind": "heading", "level": 3, "target_block_id": None},
                    {"kind": "paragraph", "level": 0, "target_block_id": str(uuid4())},
                    {"kind": "heading", "level": True, "target_block_id": None}):
        _, _, job = generate(admin_user, lambda _original: [
            {"kind": "heading", "text": "完整一级标题", "level": 1, "source_keys": [], "gap": "", "target_block_id": None},
            {"text": "不应保留", "source_keys": ["s1"], "gap": "", **invalid}])
        assert job.status == "failed" and job.stats["stage"] == "partial"
        assert len(job.stats["suggestions"]) == 1 and job.stats["suggestions"][0]["text"] == "完整一级标题"


def test_heading_level_saved_only_on_heading_blocks_and_retained_in_preview(admin_user):
    issue = new_issue(admin_user, body_blocks=[{"type": "heading", "text": "一级", "heading_level": 1}, {"type": "heading", "text": "子节", "heading_level": 2}])
    assert [row["heading_level"] for row in ledger.issue_payload(issue)["body_blocks"]] == [1, 2]
    for row in [{"type": "paragraph", "text": "普通正文", "heading_level": 1}, {"type": "heading", "text": "非法", "heading_level": 4}]:
        with pytest.raises(ValidationError):
            ledger.save_issue(issue.pk, command(issue, body_blocks=[row]), admin_user)
