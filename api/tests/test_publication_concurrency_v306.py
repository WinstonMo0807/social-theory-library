"""Real PostgreSQL lock-contention gates; skipped explicitly on SQLite."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection, transaction
from rest_framework.test import APIClient

from catalog.models import Edition
from .test_primary_editions_v306 import pair, prepare

pytestmark=[pytest.mark.django_db(transaction=True),pytest.mark.postgres_integration]


@pytest.mark.parametrize("command",["primary","maintenance"])
def test_sibling_edition_contention_returns_conflict_without_lock_cycle(admin_user,command):
    if connection.vendor!="postgresql":
        pytest.skip("Requires real PostgreSQL row locks")
    work,old,target=pair()
    ready,release=Event(),Event()
    def hold_edition():
        close_old_connections()
        try:
            with transaction.atomic():
                Edition.objects.select_for_update().get(pk=old.pk)
                ready.set()
                assert release.wait(12),"bounded contender release"
        finally:
            close_old_connections()
    client=APIClient();client.force_authenticate(admin_user)
    payload=prepare(client,target) if command=="primary" else None
    with ThreadPoolExecutor(max_workers=1) as pool:
        holder=pool.submit(hold_edition)
        assert ready.wait(5)
        try:
            if command=="primary":
                response=client.post(f"/api/catalog/admin/editions/{target.pk}/primary/",{"request_key":str(uuid4()),"fingerprint":payload["fingerprint"],"confirm":True},format="json")
            else:
                response=client.post(f"/api/catalog/admin/library/works/{work.pk}/publication/?edition={target.pk}",{"confirm_warnings":True},format="json")
            assert response.status_code==409,response.data
            assert not target.catalog_revisions.filter(revision__gt=1).exists()
        finally:
            release.set()
            holder.result(timeout=5)
    old.refresh_from_db();target.refresh_from_db()
    assert old.is_primary and not target.is_primary
