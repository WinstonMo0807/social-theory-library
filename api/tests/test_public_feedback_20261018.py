"""Synthetic regression cases; execution is reserved for the final acceptance phase."""
import uuid

import pytest
from django.core.cache import cache
from django.utils import timezone

from accounts.models import User
from catalog.models import PublicFeedback
from catalog.services import public_feedback as service
from ingestion.models import AuditEvent

PUBLIC = "/api/catalog/feedback/"
ADMIN = "/api/catalog/admin/public-feedback/"


def submission(**changes):
    return {"request_id": str(uuid.uuid4()), "category": "function", "body": "合成反馈：分页按钮无法打开。",
            "contact": "synthetic@example.invalid", "path": "/help?token=synthetic", "consent": True, **changes}


def command(**changes):
    return {"request_id": str(uuid.uuid4()), "expected_revision": 1, "status": "reviewing",
            "note": "合成处理：正在核对分页。", "follow_up": False, **changes}


@pytest.mark.parametrize(("path", "expected"), [
    ("/?token=secret", "/"), ("/home?token=secret#section", "/home"),
    ("/welcome?compare=1", "/welcome"), ("/home/", "/home/"),
    ("/home/private", ""), ("/welcome/account", ""),
    ("/works/123?token=secret#fragment", "/works/123"),
    ("/reader/81000000-0000-4000-8000-000000000001?page=12&token=secret", "/reader/81000000-0000-4000-8000-000000000001?page=12"),
    ("/reader/abc?page=-1", "/reader/abc"), ("/reader/abc?page=1&page=2", "/reader/abc"),
    ("https://example.invalid/works/a", ""), ("//example.invalid/works/a", ""),
    ("/account/citation-audits", ""), ("/admin/about", ""), ("/auth/login", ""),
    ("/works/%2e%2e/account", ""), ("/works/%252e%252e/account", ""),
    ("/%2fexample.invalid", ""), ("/works/%5csecret", ""), ("/works/%00x", ""),
    ("/help/./reading", ""), ("/help/%20reading", ""), ("/help/%FF", ""),
    ("/help/%252525252e", ""), ("/help/%72eading", "/help/reading"),
    ("/reader/abc?page=1&%70age=2", "/reader/abc"),
    ("/reader/abc?page=999999", "/reader/abc?page=999999"),
    ("/reader/abc?page=1000000", "/reader/abc"),
])
def test_context_never_keeps_private_routes_or_tokens(path, expected):
    assert service.safe_public_path(path) == expected


@pytest.mark.django_db
def test_anonymous_receipt_is_idempotent_and_private_fields_are_not_returned(api_client):
    body = submission()
    created = api_client.post(PUBLIC, body, format="json")
    assert created.status_code == 201
    repeat = api_client.post(PUBLIC, body, format="json")
    assert repeat.status_code == 200 and repeat.data == created.data
    assert set(created.data) == {"id", "request_id", "status", "created_at", "message"}
    assert created["Cache-Control"] == "private, no-store"
    row = PublicFeedback.objects.get(pk=created.data["id"])
    assert row.consent_at and row.consent_version == service.CONSENT_VERSION and row.path == "/help"
    assert PublicFeedback.objects.count() == 1
    assert api_client.get(f"{ADMIN}{row.id}/").status_code in {401, 403}
    assert api_client.get(PUBLIC).status_code == 405


@pytest.mark.django_db
def test_submission_uuid_cannot_be_reused_with_changed_body_or_owner(api_client, reader_user):
    body = submission()
    assert api_client.post(PUBLIC, body, format="json").status_code == 201
    assert api_client.post(PUBLIC, {**body, "body": "合成反馈：另一条内容。"}, format="json").status_code == 409
    api_client.force_authenticate(reader_user)
    assert api_client.post(PUBLIC, body, format="json").status_code == 409
    assert PublicFeedback.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("patch", [{"consent": False}, {"body": "短"}, {"body": "文" * 501}, {"contact": "not-an-email"},
    {"contact": "synthetic@" + ".".join(["a" * 63] * 4)}, {"request_id": "not-a-uuid"}])
def test_invalid_submission_creates_nothing(api_client, patch):
    assert api_client.post(PUBLIC, submission(**patch), format="json").status_code == 400
    assert not PublicFeedback.objects.exists()


@pytest.mark.django_db
def test_dedicated_throttle_cannot_be_bypassed_by_forwarded_or_internal_headers(api_client):
    for index in range(6):
        assert api_client.post(PUBLIC, submission(), format="json", REMOTE_ADDR="192.0.2.1",
            HTTP_X_FORWARDED_FOR=f"198.51.100.{index}", HTTP_X_INTERNAL_REQUEST="true").status_code == 201
    response = api_client.post(PUBLIC, submission(), format="json", REMOTE_ADDR="192.0.2.1", HTTP_X_FORWARDED_FOR="198.51.100.99")
    assert response.status_code == 429 and "Retry-After" in response


@pytest.mark.django_db
def test_only_administrators_can_read_contact_or_handle(api_client, admin_user, reader_user):
    row = PublicFeedback.objects.create(body="合成私密反馈正文", contact="private@example.invalid")
    editor = User.objects.create_user(username="synthetic-editor", role=User.Role.EDITOR, password="synthetic-not-a-secret")
    for actor in (reader_user, editor):
        api_client.force_authenticate(actor)
        assert api_client.get(ADMIN).status_code == 403
        assert api_client.get(f"{ADMIN}{row.id}/").status_code == 403
        assert api_client.patch(f"{ADMIN}{row.id}/", command(), format="json").status_code == 403
    api_client.force_authenticate(admin_user)
    response = api_client.get(f"{ADMIN}{row.id}/")
    assert response.status_code == 200 and response.data["contact"] == row.contact
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_list_counts_are_global_to_search_and_category_before_status(api_client, admin_user):
    PublicFeedback.objects.bulk_create([PublicFeedback(body=f"合成分页 {index}", category="usage", status="submitted") for index in range(21)])
    PublicFeedback.objects.create(body="合成分页处理中", category="usage", status="reviewing")
    PublicFeedback.objects.create(body="另一类别", category="other", status="resolved")
    api_client.force_authenticate(admin_user)
    response = api_client.get(ADMIN, {"q": "合成分页", "category": "usage", "status": "submitted", "page": 2})
    assert response.status_code == 200
    assert response.data["counts"] == {"total": 22, "submitted": 21, "reviewing": 1, "resolved": 0}
    assert response.data["count"] == 21 and len(response.data["results"]) == 1
    assert "contact" not in response.data["results"][0]


@pytest.mark.django_db
def test_handling_cas_history_and_replay_preserve_original_submission(api_client, admin_user):
    row = PublicFeedback.objects.create(body="合成原始反馈正文", contact="private@example.invalid", consent_at=timezone.now())
    api_client.force_authenticate(admin_user)
    path = f"{ADMIN}{row.id}/"
    payload = command(follow_up=True)
    first = api_client.patch(path, payload, format="json")
    assert first.status_code == 200 and first.data["accepted_revision"] == 2
    replay = api_client.patch(path, payload, format="json")
    assert replay.status_code == 200 and replay.data["accepted_revision"] == 2
    assert AuditEvent.objects.filter(action=service.ACTION).count() == 1
    assert api_client.patch(path, command(), format="json").status_code == 409
    assert api_client.patch(path, {**payload, "note": "同编号但另一段处理说明"}, format="json").status_code == 409
    row.refresh_from_db()
    assert row.body == "合成原始反馈正文" and row.revision == 2 and row.handled_by == admin_user
    detail = api_client.get(path).data
    assert detail["history"]["count"] == 1 and detail["history"]["results"][0]["before"]["status"] == "submitted"
    assert "request_fingerprint" not in str(detail)


@pytest.mark.django_db
def test_resolved_requires_explanation_and_cannot_claim_pending_reply(api_client, admin_user):
    row = PublicFeedback.objects.create(body="合成反馈", contact="synthetic@example.invalid", consent_at=timezone.now())
    api_client.force_authenticate(admin_user)
    path = f"{ADMIN}{row.id}/"
    assert api_client.patch(path, command(status="resolved", note=""), format="json").status_code == 400
    assert api_client.patch(path, command(status="resolved", follow_up=True), format="json").status_code == 400
    assert api_client.patch(path, command(status="resolved", note="合成结果已处理"), format="json").status_code == 200


@pytest.mark.django_db
def test_legacy_body_and_unknown_consent_are_preserved(api_client, admin_user):
    row = PublicFeedback.objects.create(body="旧" * 5000, category="citation", contact="legacy@example.invalid", path="/account?token=old")
    api_client.force_authenticate(admin_user)
    path = f"{ADMIN}{row.id}/"
    detail = api_client.get(path).data
    assert detail["body"] == row.body and detail["path"] == "" and not detail["can_follow_up"]
    assert detail["consent_at"] is None
    assert api_client.patch(path, command(follow_up=True), format="json").status_code == 400
    assert api_client.patch(path, command(), format="json").status_code == 200
    row.refresh_from_db()
    assert len(row.body) == 5000 and row.consent_at is None and row.request_id is None


@pytest.mark.django_db
def test_history_is_paginated_and_nonce_replay_survives_later_revision(api_client, admin_user):
    row = PublicFeedback.objects.create(body="合成反馈正文")
    api_client.force_authenticate(admin_user)
    path = f"{ADMIN}{row.id}/"
    original = command()
    assert api_client.patch(path, original, format="json").status_code == 200
    for revision in range(2, 13):
        cache.clear()
        assert api_client.patch(path, command(expected_revision=revision, note=f"合成处理说明 {revision}"), format="json").status_code == 200
    response = api_client.get(path, {"history_page": 2})
    assert response.data["history"]["count"] == 12 and len(response.data["history"]["results"]) == 2
    replay = api_client.patch(path, original, format="json")
    assert replay.status_code == 200 and replay.data["accepted_revision"] == 2 and replay.data["record"]["revision"] == 13
