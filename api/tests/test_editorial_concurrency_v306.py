"""Six real PostgreSQL row-lock conflicts, followed by a successful retry."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import close_old_connections, connection, transaction
from rest_framework.test import APIClient

from catalog.models import EditorialRevision
from .test_editorial_edit_version_v306 import object_editor

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres_integration]


@pytest.mark.parametrize("kind", ["scholars", "topics", "disciplines", "subdisciplines", "theory-system/nodes", "theory-system/reading-paths", "knowledge_relation", "timeline_event"])
def test_busy_editor_never_writes_and_retry_preserves_public_content(admin_user, kind):
    if connection.vendor != "postgresql":
        pytest.skip("requires real PostgreSQL row locks")
    if kind in {"knowledge_relation", "timeline_event"}:
        from .test_relation_timeline_editorial_v306 import editor_object
        row, url = editor_object(kind)
        field, target = "description", kind
    else:
        row, url, field, target = object_editor(kind, True)
    original = getattr(row, field)
    client = APIClient()
    client.force_authenticate(admin_user)
    version = client.get(url).data["edit_version"]
    ready, release = Event(), Event()

    def hold_object():
        close_old_connections()
        try:
            with transaction.atomic():
                type(row).objects.select_for_update().get(pk=row.pk)
                ready.set()
                assert release.wait(20), "bounded lock holder release"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        holder = pool.submit(hold_object)
        assert ready.wait(5)
        try:
            busy = client.patch(url, {field: "尚未提交的编辑"}, format="json", HTTP_IF_MATCH=version)
            assert busy.status_code == 409, busy.data
            assert busy.data["code"] == "edit_busy"
            assert not EditorialRevision.objects.filter(target_id=row.pk).exists()
        finally:
            release.set()
            holder.result(timeout=5)

    saved = client.patch(url, {field: "重试保存的草稿"}, format="json", HTTP_IF_MATCH=version)
    assert saved.status_code == 202, saved.data
    assert saved.data[field] == "重试保存的草稿"
    row.refresh_from_db()
    assert getattr(row, field) == original
    assert EditorialRevision.objects.filter(target_type=target, target_id=row.pk, status="draft").count() == 1
