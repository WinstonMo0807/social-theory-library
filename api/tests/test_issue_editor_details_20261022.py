"""Final-atlas editor details. Defined now; execute at unified acceptance."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import EditorialRevision, KnowledgeNode
from catalog.services import editorial_issues as ledger
from catalog.services import editorial_presence as presence
from catalog.services import editorial_suggestions as materials
from catalog.services.editorial_blocks import normalize_text_format
from ingestion.models import AuditEvent
from .test_issue_workbench_20261022 import new_issue, command
from .test_v307_editorial_issues import public_edition

pytestmark = pytest.mark.django_db


def formatted(text, marks, **extra):
    return normalize_text_format({"text": text, "text_marks": marks, **extra}, {"text": text.strip(), "type": "paragraph"})


def test_utf16_format_survives_whitespace_trim_and_keeps_emoji_whole(admin_user):
    marks = [{"start": 2, "end": 5, "kind": "strong"}, {"start": 5, "end": 7, "kind": "link", "href": "/topics/test"}]
    block = formatted("  甲😀乙丙  ", marks, text_style="ordered")
    assert block["text_marks"] == [{**marks[0], "start": 0, "end": 3}, {**marks[1], "start": 3, "end": 5}]
    issue = new_issue(admin_user, body_blocks=[block])
    assert ledger.issue_payload(issue)["body_blocks"][0]["text_marks"] == block["text_marks"]
    assert ledger.issue_draft_payload(issue)["body_blocks"][0]["text_style"] == "ordered"


@pytest.mark.parametrize("mark", [
    {"start": 1, "end": 2, "kind": "strong"},  # splits the surrogate pair
    {"start": False, "end": 1, "kind": "em"},
    {"start": 0, "end": 99, "kind": "em"},
    {"start": 0, "end": 1, "kind": "html"},
    *[{"start": 0, "end": 1, "kind": "link", "href": href} for href in ("javascript:alert(1)", "//other.test", "/\\other.test", "https://[broken", "https://ok.test\n")],
])
def test_invalid_marks_and_unsafe_links_are_rejected(mark):
    with pytest.raises(ValidationError):
        formatted("甲😀乙", [mark])


def test_overlapping_links_and_excess_marks_are_rejected_but_plain_legacy_is_unchanged():
    with pytest.raises(ValidationError):
        formatted("中文文本", [{"start": 0, "end": 3, "kind": "link", "href": "/a"}, {"start": 2, "end": 4, "kind": "link", "href": "/b"}])
    with pytest.raises(ValidationError):
        formatted("中文", [{"start": 0, "end": 1, "kind": "em"}] * 201)
    assert normalize_text_format({"text": "旧导读"}, {"type": "paragraph", "text": "旧导读"}) == {"type": "paragraph", "text": "旧导读"}


def test_format_cannot_modify_material_source(admin_user):
    edition = public_edition("只读馆藏")
    source = {"type": "work", "id": str(edition.work_id), "edition_id": str(edition.pk)}
    issue = new_issue(admin_user, body_blocks=[{"type": "work", "text": "人工导读", "text_marks": [{"start": 0, "end": 2, "kind": "strong"}], "target": source,
        "resolved_sources": [{"title": "伪造来源"}]}])
    block = ledger.issue_payload(issue)["body_blocks"][0]
    assert block["resolved_sources"][0]["title"] != "伪造来源"
    assert "resolved_sources" not in ledger.issue_draft_payload(issue)["body_blocks"][0]


def test_suggestions_use_public_exact_sources_and_do_not_write_article(admin_user):
    issue = new_issue(admin_user)
    edition = public_edition("建议素材验收")
    edition.is_primary = True
    edition.save(update_fields=["is_primary"])
    KnowledgeNode.objects.create(canonical_name_zh="建议素材验收概念", node_type="concept", slug="suggestion-public", status="published")
    KnowledgeNode.objects.create(canonical_name_zh="建议素材验收未公开", node_type="concept", slug="suggestion-private", status="draft")
    before = EditorialRevision.objects.count(), AuditEvent.objects.count()
    value = materials.suggestions(issue, admin_user, query="建议素材验收")
    work = next(row for row in value["results"] if row["kind"] == "work")
    assert work["target"]["edition_id"] == str(edition.pk)
    assert any(row["kind"] == "concept" for row in value["results"])
    assert not any("未公开" in row["source"]["title"] for row in value["results"])
    assert before == (EditorialRevision.objects.count(), AuditEvent.objects.count())
    with patch("catalog.services.editorial_suggestions.resolve_target", side_effect=Http404):
        assert materials.suggestions(issue, admin_user, query="建议素材验收")["results"] == []


def candidate(issue, actor):
    node = KnowledgeNode.objects.create(canonical_name_zh="放弃建议验收概念", node_type="concept", slug=f"suggestion-{uuid4()}", status="published")
    return materials.suggestions(issue, actor, query=node.canonical_name_zh, kind="concept")["results"][0]


def test_discard_receipt_is_scoped_idempotent_and_keeps_saved_version(admin_user, reader_user):
    issue, other = new_issue(admin_user), new_issue(admin_user)
    row = candidate(issue, admin_user)
    data = {"request_id": str(uuid4()), "token": row["token"]}
    for target, actor in ((other, admin_user), (issue, reader_user)):
        with pytest.raises(ValidationError):
            materials.dismiss(target.pk, actor, data)
    before = ledger.edit_version("recommendation_issue", issue.pk)
    assert materials.dismiss(issue.pk, admin_user, data) == materials.dismiss(issue.pk, admin_user, data)
    assert AuditEvent.objects.filter(action=materials.ACTION, request_id=data["request_id"]).count() == 1
    assert ledger.edit_version("recommendation_issue", issue.pk) == before
    assert not materials.suggestions(issue, admin_user, query="放弃建议验收概念", kind="concept")["results"]
    with pytest.raises(ledger.EditConflict):
        materials.dismiss(issue.pk, admin_user, {**data, "token": "another-token"})


def test_stale_suggestion_cannot_be_discarded_and_endpoint_checks_owner(api_client, admin_user, reader_user):
    issue = new_issue(admin_user)
    row = candidate(issue, admin_user)
    ledger.save_issue(issue.pk, command(issue, title="新的文章修订"), admin_user)
    with pytest.raises(ledger.EditConflict):
        materials.dismiss(issue.pk, admin_user, {"request_id": str(uuid4()), "token": row["token"]})
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/recommendation-issues/{issue.pk}/suggestions/"
    assert api_client.get(url, HTTP_X_EDITOR_OWNER="other").status_code == 403
    for data in ({"batch": "0"}, {"batch": "101"}, {"kind": "span"}, {"q": "字" * 201}):
        assert api_client.get(url, data).status_code == 400
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403


def test_presence_is_issue_and_tab_scoped_expires_and_never_writes_revision(admin_user):
    issue, other = new_issue(admin_user), new_issue(admin_user)
    first, second = str(uuid4()), str(uuid4())
    before = EditorialRevision.objects.count(), AuditEvent.objects.count()
    now = timezone.now()
    with patch.object(presence.timezone, "now", return_value=now):
        value = presence.observe(issue.pk, admin_user, {"session_id": first, "mode": "editing"})
        assert value["participants"][0]["is_self"] and value["participants"][0]["mode"] == "editing"
        presence.observe(issue.pk, admin_user, {"session_id": second, "mode": "viewing"})
        assert presence.observe(issue.pk, admin_user, {"session_id": first, "mode": "leave"})["participants"][0]["mode"] == "viewing"
        assert not presence.observe(other.pk, admin_user, {"session_id": first, "mode": "leave"})["participants"]
    with patch.object(presence.timezone, "now", return_value=now + timedelta(seconds=91)):
        assert not presence.observe(issue.pk, admin_user, {"session_id": first, "mode": "leave"})["participants"]
    assert before == (EditorialRevision.objects.count(), AuditEvent.objects.count())


def test_presence_rechecks_role_and_reports_cache_failure(api_client, admin_user, reader_user):
    issue = new_issue(admin_user)
    url = f"/api/catalog/admin/recommendation-issues/{issue.pk}/presence/"
    data = {"session_id": str(uuid4()), "mode": "viewing"}
    api_client.force_authenticate(reader_user)
    assert api_client.post(url, data, format="json").status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.post(url, data, format="json", HTTP_X_EDITOR_OWNER="other").status_code == 403
    with patch.object(presence.cache, "add", side_effect=OSError):
        assert api_client.post(url, data, format="json").status_code == 503
    response = api_client.post(url, data, format="json")
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    assert response.data["expires_after_seconds"] == 90
