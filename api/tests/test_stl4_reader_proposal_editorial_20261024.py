"""Deferred proposal/privacy/recovery acceptance; no execution during development."""
from datetime import timedelta
import json
from uuid import uuid4

import pytest
from django.utils import timezone

from accounts.models import User
from catalog.models import CurationProject, Edition, RecommendationIssue
from catalog.services.editorial_issues import issue_draft_payload
from ingestion.models import AuditEvent
from reading import privacy, reader_shares, research, share_scope
from reading.models import ReadingList, ReadingListItem, ResearchProject
from reading.sharing_models import ReaderShare
from tests.test_publication_invariants_v305 import published_edition
from tests.test_stl4_article_directory_20261024 import account

pytestmark = pytest.mark.django_db
PATH = "/api/catalog/admin/recommendation-issues/create/"


def proposal(user, *, research_only=False, destination="proposal"):
    edition, revision = published_edition("合成提案公开书目")
    Edition.objects.filter(pk=edition.pk).update(is_primary=True)
    if research_only:
        source = ResearchProject.objects.create(user=user, data_ciphertext=research.pack({
            "title": "不进入正文的私人标题", "question": "不进入正文的私人问题", "notes": "不进入正文的私人笔记", "selections": []}))
        kind, materials, questions, notes = "research", [], ["project"], ["project-notes"]
    else:
        source = ReadingList.objects.create(user=user, title="不进入正文的私人标题")
        selected = ReadingListItem.objects.create(reading_list=source, work=edition.work)
        unselected, _ = published_edition("未选择的合成书目")
        ReadingListItem.objects.create(reading_list=source, work=unselected.work)
        kind, materials, questions, notes = "booklist", [str(selected.pk)], [], []
    data = {"request_id": uuid4(), "source_kind": kind, "source_id": source.pk, "expected_version": privacy.version(source),
        "questions": questions, "materials": materials, "notes": notes, "message": "不进入正文的私人附言",
        "destination": destination, "expires_days": 7, "confirmed": True}
    data["preview_hash"] = share_scope.preview(user, data)[0]["preview_hash"]
    result = reader_shares.create(user, data)
    return ReaderShare.objects.get(pk=result["share"]["id"]), source, edition, revision


def preview(client, row):
    response = client.get(f"/api/catalog/admin/recommendation-issues/proposals/{row.pk}/")
    assert response.status_code == 200, response.data
    assert "no-store" in response["Cache-Control"]
    return response.data


def command(scope):
    return {"request_id": str(uuid4()), "title": "编辑新写的合成标题", "kind": "article", "proposal": {
        "id": scope["proposal_id"], "expected_revision": scope["expected_revision"], "preview_hash": scope["preview_hash"]}}


def test_selected_public_bibliography_only_and_original_replay(api_client, reader_user, admin_user):
    row, source, edition, _ = proposal(reader_user)
    account(api_client, admin_user)
    scope = preview(api_client, row)
    assert len(scope["materials"]) == 1 and scope["materials"][0]["edition_id"] == str(edition.pk)
    assert str(source.pk) not in json.dumps(scope, default=str, ensure_ascii=False)
    body = command(scope)
    response = api_client.post(PATH, body, format="json")
    assert response.status_code == 201, response.data
    issue = RecommendationIssue.objects.get(pk=response.data["issue_id"])
    payload = issue_draft_payload(issue)
    assert payload["title"] == body["title"] and payload["body_blocks"] == [] and len(payload["items"]) == 1
    assert payload["items"][0]["edition_id"] == str(edition.pk)
    assert payload["introduction"] == "" and payload["public_byline"] == "" and issue.active_revision_id is None
    assert "不进入正文" not in json.dumps(payload, ensure_ascii=False)
    assert "不进入正文" not in json.dumps(list(AuditEvent.objects.values("before", "after")), default=str, ensure_ascii=False)
    row.refresh_from_db()
    assert row.review_state == "considering" and source.items.count() == 2
    assert api_client.post(PATH, body, format="json").data == response.data
    reader_shares.revoke(reader_user, row.pk, row.revision)
    assert api_client.get(f"{PATH}commands/{body['request_id']}/").data == response.data
    assert api_client.get(f"/api/catalog/admin/recommendation-issues/proposals/{row.pk}/").status_code == 404
    assert RecommendationIssue.objects.count() == 1


def test_other_editor_converges_without_disclosing_private_project(api_client, reader_user, admin_user):
    row, *_ = proposal(reader_user)
    account(api_client, admin_user)
    body = command(preview(api_client, row))
    created = api_client.post(PATH, body, format="json")
    assert created.status_code == 201, created.data
    other = User.objects.create_user(username="proposal-other-editor", email="proposal-other@example.org", role="editor")
    project = CurationProject.objects.create(title="合成私有策划项目", owner=admin_user, visibility="team")
    RecommendationIssue.objects.filter(pk=created.data["issue_id"]).update(project=project)
    account(api_client, other)
    scope = preview(api_client, row)
    assert scope["already_created"] and scope["issue_id"] is None and scope["next_url"] == ""
    repeated = api_client.post(PATH, command(scope), format="json")
    assert repeated.status_code == 201 and not repeated.data["available"] and repeated.data["issue_id"] is None
    assert RecommendationIssue.objects.count() == 1


def test_changed_expired_wrong_destination_and_owner_are_blocked(api_client, reader_user, admin_user):
    row, source, edition, _ = proposal(reader_user)
    account(api_client, admin_user)
    body = command(preview(api_client, row))
    assert api_client.post(PATH, {**body, "proposal": {**body["proposal"], "preview_hash": "0" * 64}}, format="json").status_code == 409
    assert api_client.post(PATH, {**body, "proposal": {**body["proposal"], "private_note": "拒绝"}}, format="json").status_code == 400
    Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    assert api_client.post(PATH, body, format="json").status_code in (404, 409)
    assert not RecommendationIssue.objects.exists()
    fresh, *_ = proposal(reader_user)
    body = command(preview(api_client, fresh))
    ReaderShare.objects.filter(pk=fresh.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert api_client.post(PATH, body, format="json").status_code == 404
    public, *_ = proposal(reader_user, destination="public")
    assert api_client.get(f"/api/catalog/admin/recommendation-issues/proposals/{public.pk}/").status_code == 404
    account(api_client, reader_user)
    assert api_client.get(f"/api/catalog/admin/recommendation-issues/proposals/{row.pk}/").status_code == 403
    account(api_client, admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.post(PATH, body, format="json").status_code == 403
    assert not RecommendationIssue.objects.exists() and ReadingList.objects.filter(pk=source.pk).exists()


def test_question_only_proposal_creates_empty_draft_and_stop_fences_late_submit(api_client, reader_user, admin_user):
    row, *_ = proposal(reader_user, research_only=True)
    account(api_client, admin_user)
    scope = preview(api_client, row)
    assert scope["materials"] == []
    body = command(scope)
    stop = api_client.post(f"{PATH}commands/{body['request_id']}/", {"action": "cancel_pending"}, format="json")
    assert stop.data["state"] == "cancelled"
    assert api_client.post(PATH, body, format="json").data["state"] == "cancelled"
    assert not RecommendationIssue.objects.exists()
    created = api_client.post(PATH, command(scope), format="json")
    assert created.status_code == 201, created.data
    payload = issue_draft_payload(RecommendationIssue.objects.get(pk=created.data["issue_id"]))
    assert payload["items"] == [] and payload["body_blocks"] == []
    assert "不进入正文" not in json.dumps(payload, ensure_ascii=False)
