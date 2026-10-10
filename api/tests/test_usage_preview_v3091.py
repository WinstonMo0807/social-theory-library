from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import AnonymousUsageEvent, Edition, PublicationState, Work
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


def _holding():
    work = Work.objects.create(title="统计引用的公开馆藏", document_type="book")
    primary = Edition.objects.create(
        work=work, state=PublicationState.PUBLISHED,
        is_primary=True, public_slug="analytics-primary-serving-page",
    )
    secondary = Edition.objects.create(
        work=work, state=PublicationState.PUBLISHED,
        is_primary=False, public_slug="analytics-secondary-serving-page",
    )
    for edition in (primary, secondary):
        activate_catalog_revision(edition, fulltext_ready=False)
    for session in ("a", "a", "b"):
        AnonymousUsageEvent.objects.create(
            event_type=AnonymousUsageEvent.EventType.READER_OPEN,
            work=work, session_hash=session * 64,
            expires_at=timezone.now() + timedelta(days=90),
        )
    client = APIClient()
    client.force_authenticate(get_user_model().objects.create_user(
        username="analytics-admin", email="analytics-admin@example.test", role="admin",
    ))
    return client, work, primary, secondary


def test_top_holding_previews_use_the_actual_primary_public_slug():
    client, work, primary, _secondary = _holding()
    response = client.get("/api/catalog/admin/usage-analytics/?days=90")
    assert response.status_code == 200
    row = response.data["top_works"][0]
    assert row["work_id"] == work.pk
    assert row["opens"] == 3
    assert row["unique_sessions"] == 2
    assert row["public_url"] == f"/works/{primary.public_slug}"
    assert str(work.pk) not in row["public_url"]
    public = APIClient().get(f"/api/catalog/works/{primary.public_slug}/")
    assert public.status_code == 200
    assert public.data["id"] == str(work.pk)


@pytest.mark.parametrize("unavailable", ["withdrawn", "inactive", "no_primary"])
def test_historical_counts_remain_when_a_public_preview_is_unavailable(unavailable):
    client, work, primary, _secondary = _holding()
    if unavailable == "withdrawn":
        primary.state = PublicationState.WITHDRAWN
        primary.save(update_fields=["state"])
    elif unavailable == "inactive":
        primary.active_catalog_revision.status = "superseded"
        primary.active_catalog_revision.save(update_fields=["status"])
    else:
        primary.is_primary = False
        primary.save(update_fields=["is_primary"])
    response = client.get("/api/catalog/admin/usage-analytics/")
    assert response.status_code == 200
    row = response.data["top_works"][0]
    assert row["work_id"] == work.pk
    assert (row["opens"], row["unique_sessions"]) == (3, 2)
    assert row["public_url"] is None
    assert AnonymousUsageEvent.objects.filter(work=work).count() == 3


def test_readers_cannot_open_administrative_analytics():
    client = APIClient()
    client.force_authenticate(get_user_model().objects.create_user(
        username="analytics-reader", email="analytics-reader@example.test", role="reader",
    ))
    assert client.get("/api/catalog/admin/usage-analytics/").status_code == 403
