"""Scholar follows reuse SourceFollow; definitions for unified acceptance only."""
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import EditorialRevision, Person, ScholarProfile
from reading import privacy, research, source_follow as sources
from reading.source_models import SourceFollow, SourceFollowEvent

pytestmark = pytest.mark.django_db
URL = "/api/reading/source-follows/"


def scholar():
    person = Person.objects.create(preferred_name="合成公开学者", authority_status="verified")
    return ScholarProfile.objects.create(person=person, slug=f"scholar-{uuid4()}", editorial_status="published")


def command(profile, *, action="subscribe", revision=0, nonce=None):
    return {"path": f"/scholars/{profile.slug}", "scholar_profile_id": profile.pk,
        "action": action, "expected_revision": revision, "request_id": nonce or uuid4()}


def test_profile_uuid_not_person_or_reused_slug_is_subscription_identity(reader_user):
    profile = scholar()
    with pytest.raises(ValidationError):
        sources.command(reader_user, {**command(profile), "scholar_profile_id": profile.person_id})
    first = sources.command(reader_user, command(profile))["record"]
    old_slug = profile.slug
    profile.slug = f"renamed-{uuid4()}"
    profile.save(update_fields=["slug"])
    replacement = scholar()
    replacement.slug = old_slug
    replacement.save(update_fields=["slug"])
    current = sources.output(sources.refresh(first["id"], reader_user.pk))
    assert current["path"] == f"/scholars/{profile.slug}"
    assert current["scholar_profile_id"] == str(profile.pk)
    assert current["source"]["person_id"] == str(profile.person_id)
    other = sources.command(reader_user, command(replacement))["record"]
    assert other["id"] != current["id"] and SourceFollow.objects.filter(user=reader_user).count() == 2


def test_only_published_profile_revision_changes_the_follow_fingerprint(reader_user):
    profile = scholar()
    published = EditorialRevision.objects.create(target_type="scholar_profile", target_id=profile.pk,
        revision=1, status="published", idempotency_key=str(uuid4()), published_at=timezone.now())
    created = sources.command(reader_user, command(profile))["record"]
    draft = EditorialRevision.objects.create(target_type="scholar_profile", target_id=profile.pk,
        revision=2, status="draft", idempotency_key=str(uuid4()))
    unchanged = sources.refresh(created["id"], reader_user.pk)
    assert unchanged.revision == created["revision"] and unchanged.events.filter(action="changed").count() == 0
    published.status = "superseded"
    published.save(update_fields=["status"])
    draft.status, draft.published_at = "published", timezone.now()
    draft.save(update_fields=["status", "published_at"])
    changed = sources.refresh(created["id"], reader_user.pk)
    sources.refresh(created["id"], reader_user.pk)
    assert changed.revision == created["revision"] + 1
    assert changed.events.filter(action="changed").count() == 1


@pytest.mark.parametrize("remove", [False, True])
def test_withdrawn_or_deleted_scholar_hides_metadata_but_allows_cancel(reader_user, remove):
    profile = scholar()
    body = command(profile)
    created = sources.command(reader_user, body)["record"]
    if remove:
        profile.delete()
    else:
        profile.editorial_status = "draft"
        profile.save(update_fields=["editorial_status"])
    row = sources.refresh(created["id"], reader_user.pk)
    exported = privacy.export_item(reader_user, "source_follows", row)
    assert exported["source"]["title"] == "来源当前不可用"
    assert exported["source"]["person_id"] is None and not exported["source"]["href"]
    assert "合成公开学者" not in str(exported)
    canceled = sources.command(reader_user, {**body, "request_id": uuid4(), "action": "unsubscribe", "expected_revision": row.revision})
    assert canceled["record"]["active"] is False


def test_privacy_erasure_removes_history_and_old_nonce_cannot_recreate(reader_user):
    profile = scholar()
    body = command(profile)
    created = sources.command(reader_user, body)["record"]
    row = SourceFollow.objects.get(pk=created["id"])
    SourceFollowEvent.objects.create(user=reader_user, follow=row, action="changed", before_status="available", after_status="unavailable", revision=2)
    target = privacy.target_of(row, "source_follows")
    privacy.erase_item(reader_user, target, row, privacy.erase_impact(reader_user, "source_follows", row), contexts=[])
    assert SourceFollowEvent.objects.filter(user=reader_user, request_id__isnull=True).count() == 0
    remaining = SourceFollowEvent.objects.get(user=reader_user)
    assert remaining.follow_id is None and remaining.before_status == remaining.after_status == ""
    for result in (sources.command(reader_user, body), sources.by_request(reader_user, body["request_id"])):
        assert result["record"] is None and result["receipt"]["deleted"] is True
    assert not SourceFollow.objects.filter(user=reader_user).exists()
    assert sources.command(reader_user, command(profile))["record"] is not None


def test_explicit_delete_has_cas_owner_scope_and_repeatable_tombstone(api_client, reader_user, admin_user):
    profile = scholar()
    body = command(profile)
    created = sources.command(reader_user, body)["record"]
    delete = {"request_id": uuid4(), "expected_revision": created["revision"]}
    with pytest.raises(research.ResearchConflict):
        sources.delete_follow(reader_user, created["id"], {**delete, "expected_revision": 0})
    api_client.force_authenticate(admin_user)
    other = api_client.get(URL + "by-request/", {"request_id": str(body["request_id"])}, HTTP_X_READER_OWNER=str(admin_user.pk))
    assert other.status_code == 404
    assert api_client.get(URL + "by-request/", {"request_id": str(body["request_id"])}, HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 403
    with pytest.raises(NotFound):
        sources.delete_follow(admin_user, created["id"], delete)
    first = sources.delete_follow(reader_user, created["id"], delete)
    assert first == sources.delete_follow(reader_user, created["id"], delete)
    assert first["receipt"]["deleted"] and first["record"] is None
    api_client.force_authenticate(reader_user)
    restored = api_client.get(URL + "by-request/", {"request_id": str(body["request_id"])}, HTTP_X_READER_OWNER=str(reader_user.pk))
    assert restored.status_code == 200 and "no-store" in restored["Cache-Control"]
    assert restored.data["receipt"]["deleted"]


@pytest.mark.parametrize("change", [{"expected_revision": True}, {"scholar_profile_id": "bad-id"}, {"biography": "Do not retain"}, {"include_candidates": True}])
def test_command_rejects_illegal_types_and_unapproved_content(api_client, reader_user, change):
    profile = scholar()
    body = {key: str(value) if key in {"scholar_profile_id", "request_id"} else value for key, value in command(profile).items()}
    api_client.force_authenticate(reader_user)
    response = api_client.post(URL, {**body, **change}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk))
    assert response.status_code == 400 and not SourceFollow.objects.exists()
