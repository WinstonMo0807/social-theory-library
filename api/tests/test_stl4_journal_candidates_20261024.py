"""Deferred acceptance: source-bound journal prefills keep the existing rows."""
from copy import deepcopy
from uuid import uuid4

import pytest

from catalog.models import DocumentOutlineRevision, JournalIssueArticle
from catalog.services.journal_candidates import directory
from ingestion.models import AuditEvent
from .test_outline_atlas_20261018 import outline_source, _native_revision  # noqa: F401
from .test_workspace_edits_v306 import setup_workspace

pytestmark = pytest.mark.django_db


def candidate_payload(api_client, admin_user, outline_source):
    asset, _, _ = outline_source
    edition = asset.edition
    edition.work.document_type = "journal_issue"
    edition.work.save(update_fields=["document_type", "updated_at"])
    revision = _native_revision(outline_source)
    existing = JournalIssueArticle.objects.create(issue=edition, title="保留人工填写", author_display="原作者", page_range="1–2", position=0)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    edition, base, payload = setup_workspace(api_client, admin_user, edition)
    source = directory(edition, admin_user)
    payload["sections"] = {"bibliography": {"journal_contents": [
        {"id": str(existing.pk), "title": "保留人工填写", "author_display": "原作者", "page_range": "1–2"},
        {"title": "人工校正题名", "author_display": "核对后作者", "page_range": "3–6", "candidate_source": source["results"][0]["candidate_source"]},
    ]}}
    return asset, revision, base, payload


def test_append_journal_candidate_preserves_manual_rows_and_receipt_replay(api_client, admin_user, outline_source):
    asset, _, base, payload = candidate_payload(api_client, admin_user, outline_source)
    response = api_client.post(base + "edits/", payload, format="json")
    assert response.status_code == 200, response.data
    rows = response.data["data"]["bibliography"]["journal_contents"]
    assert [row["title"] for row in rows] == ["保留人工填写", "人工校正题名"]
    assert str(rows[0]["id"]) == payload["sections"]["bibliography"]["journal_contents"][0]["id"]
    assert all("candidate_source" not in row for row in rows)
    receipt = AuditEvent.objects.get(action="workspace.edits.saved", object_id=asset.edition_id)
    observed = receipt.after["journal_candidates"]
    assert len(observed) == 1 and observed[0]["observed_title"] == "Chapter One"
    assert observed[0]["final_title"] == "人工校正题名" and observed[0]["correctness"] == "not_evaluated"
    retry = api_client.post(base + "edits/", payload, format="json")
    assert retry.status_code == 200 and retry.data["save_result"]["replayed"] is True


@pytest.mark.parametrize("change", ["file", "outline", "owner"])
def test_changed_candidate_source_cannot_partially_write_journal(api_client, admin_user, outline_source, change):
    asset, revision, base, payload = candidate_payload(api_client, admin_user, outline_source)
    if change == "file":
        asset.sha256 = "f" * 64; asset.save(update_fields=["sha256"])
    elif change == "outline":
        DocumentOutlineRevision.objects.create(asset=asset, document_revision=revision.document_revision,
            revision=revision.revision + 1, source_checksum=asset.sha256, nodes=deepcopy(revision.nodes))
    else:
        from django.core import signing
        from catalog.services.journal_candidates import SALT
        row = payload["sections"]["bibliography"]["journal_contents"][1]
        proof = signing.loads(row["candidate_source"], salt=SALT)
        proof["owner_id"] = str(uuid4())
        row["candidate_source"] = signing.dumps(proof, salt=SALT, compress=True)
    result = api_client.post(base + "edits/", payload, format="json")
    assert result.status_code == 409, result.data
    assert list(asset.edition.journal_articles.values_list("title", flat=True)) == ["保留人工填写"]
    assert not AuditEvent.objects.filter(action="workspace.edits.saved", object_id=asset.edition_id).exists()
