from uuid import uuid4

import pytest

from catalog.models import Edition, RecommendationPolicy, RecommendationSnapshot, Work
from catalog.services.recommendations import generate_snapshot
from ingestion.models import AuditEvent
from .test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def command(policy, **extra):
    policy.refresh_from_db()
    current = policy.snapshots.filter(is_current=True).first()
    return {
        "confirm": True,
        "request_key": str(uuid4()),
        "expected_snapshot_id": str(current.pk) if current else None,
        "expected_updated_at": policy.updated_at.isoformat(),
        **extra,
    }


def test_automatic_recommendations_exclude_published_flag_without_an_active_primary_snapshot():
    edition, _ = published_edition("真正公开的推荐文献")
    fake = Work.objects.create(title="只有发布标志")
    Edition.objects.create(work=fake, state="published", is_primary=True)
    secondary, _ = published_edition("仅非主版本公开")
    Edition.objects.filter(pk=secondary.pk).update(is_primary=False)
    policy = RecommendationPolicy.objects.get(placement="home_featured")
    snapshot = generate_snapshot(policy)
    assert list(snapshot.items.values_list("work_id", flat=True)) == [edition.work_id]


@pytest.mark.parametrize("manual", [False, True])
def test_recommendation_replay_keeps_exact_snapshot_and_does_not_overwrite_later_choice(api_client, admin_user, manual):
    edition, _ = published_edition("推荐重试")
    policy = RecommendationPolicy.objects.get(placement="home_featured")
    api_client.force_authenticate(admin_user)
    url = "/api/catalog/admin/recommendations/home_featured/refresh/"
    data = command(policy, **({"items": [{"target_type": "work", "id": str(edition.work_id)}]} if manual else {}))
    first = api_client.post(url, data, format="json")
    assert first.status_code == 200
    count = policy.snapshots.count()
    replay = api_client.post(url, data, format="json")
    assert replay.status_code == 200
    assert replay.data["replayed"] is True
    assert replay.data["publication_effective"] is True
    assert replay.data["accepted_snapshot_id"] == first.data["current"]["id"]
    assert policy.snapshots.count() == count
    later = api_client.post(url, command(policy), format="json")
    assert later.status_code == 200
    late_replay = api_client.post(url, data, format="json")
    assert late_replay.status_code == 200
    assert late_replay.data["command_accepted"] is True
    assert late_replay.data["publication_effective"] is False
    assert late_replay.data["current"]["id"] == later.data["current"]["id"]
    assert policy.snapshots.count() == count + 1
    receipt = AuditEvent.objects.get(pk=first.data["audit_id"])
    assert receipt.after["snapshot_id"] == first.data["current"]["id"]


def test_recommendation_requires_confirmation_version_and_permission_and_rejects_reused_payload(api_client, admin_user, reader_user):
    edition, _ = published_edition("推荐请求保护")
    policy = RecommendationPolicy.objects.get(placement="home_featured")
    url = "/api/catalog/admin/recommendations/home_featured/refresh/"
    data = command(policy)
    api_client.force_authenticate(reader_user)
    assert api_client.post(url, data, format="json").status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.post(url, {}, format="json").status_code == 400
    assert api_client.post(url, {**data, "confirm": False}, format="json").status_code == 400
    first = api_client.post(url, data, format="json")
    assert first.status_code == 200
    changed = {**data, "items": [{"target_type": "work", "id": str(edition.work_id)}]}
    assert api_client.post(url, changed, format="json").status_code == 409
    assert api_client.post(url, {**data, "request_key": str(uuid4())}, format="json").status_code == 409
    assert policy.snapshots.count() == 1
    assert RecommendationSnapshot.objects.get(pk=first.data["current"]["id"]).is_current
