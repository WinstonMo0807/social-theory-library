"""Deferred acceptance for private, recoverable maintenance queries."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import Work
from catalog.discovery_models import DiscoverySearchSession
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/index-maintenance/query/"


def test_query_replay_stop_and_changed_owner(api_client, admin_user):
    work = Work.objects.create(title="任务查询恢复用例")
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    body = {"request_id": str(uuid4()), "work_id": str(work.pk), "q": "原文线索"}
    session = DiscoverySearchSession.objects.create(owner=admin_user, query=body["q"], access_statuses=["public", "staff"], expires_at=timezone.now()+timedelta(hours=1))
    with patch("catalog.index_query_views.create_session", return_value=(session, "unused")) as create:
        first = api_client.post(URL, body, format="json", **headers)
        assert first.status_code == 200, first.data
        replay = api_client.post(URL, body, format="json", **headers)
        assert replay.data["session_id"] == str(session.pk) and create.call_count == 1
        assert create.call_args.args[2] == {"work_ids": [str(work.pk)], "access": ["public"]}
        session.refresh_from_db()
        assert session.access_statuses == ["public"]
        changed = api_client.post(URL, {**body, "q": "另一查询"}, format="json", **headers)
        assert changed.status_code == 409
        stopped = str(uuid4())
        stop = api_client.post(f"{URL}commands/{stopped}/", {"action": "cancel_pending"}, format="json", **headers)
        assert stop.status_code == 200
        late = api_client.post(URL, {**body, "request_id": stopped}, format="json", **headers)
        assert late.data["state"] == "cancelled" and create.call_count == 1
        owner_change = api_client.post(URL, {**body, "request_id": str(uuid4())}, format="json", HTTP_X_EDITOR_OWNER=str(uuid4()))
        assert owner_change.status_code == 403
    audit = AuditEvent.objects.get(action="index.query.preview", request_id=body["request_id"])
    assert "q" not in audit.after and "query" not in audit.after
