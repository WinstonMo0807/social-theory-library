"""Only the newly added recycle reasons, counts, private previews and batch command."""
from uuid import uuid4

import pytest

from catalog.models import Contribution, Edition, Person, RecycleEntry, ScholarProfile, Topic, Work
from catalog.services.recycle import recycle_object
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db


def test_recycle_counts_and_reason_are_actual_and_old_reason_stays_unknown(api_client, superadmin_user):
    work = Work.objects.create(title="53新增原因", document_type="book")
    topic = Topic.objects.create(name="53旧记录", slug="53-old-reason", editorial_status="draft")
    recycle_object(work, actor=superadmin_user, kind="work", name=work.title, reason="误删")
    recycle_object(topic, actor=superadmin_user, kind="topic", name=topic.name)
    api_client.force_authenticate(superadmin_user)
    response = api_client.get("/api/catalog/admin/recycle/?kind=work&search=新增")
    assert response.status_code == 200
    assert response.data["count"] == 1 and response.data["total_count"] == 2
    assert response.data["kind_counts"] == {"work": 1, "topic": 1}
    assert response.data["results"][0]["reason"] == "误删"
    response = api_client.get("/api/catalog/admin/recycle/?kind=topic")
    assert response.data["results"][0]["reason"] == ""


def test_recycle_work_preview_uses_retained_version_and_never_restores_or_publishes(api_client, superadmin_user):
    work = Work.objects.create(title="53未公开馆藏预览", document_type="book", abstract="保留的简介")
    edition = Edition.objects.create(work=work, state="draft", is_primary=True, publication_year=2026)
    person = Person.objects.create(preferred_name="53保留作者")
    # The shared public serializer displays human-approved contributions.
    Contribution.objects.create(edition=edition, person=person, role="author", order=0, approved=True)
    entry = recycle_object(work, actor=superadmin_user, kind="work", name=work.title)
    api_client.force_authenticate(superadmin_user)
    before_events = AuditEvent.objects.count()
    response = api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/preview/")
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    assert response.data["preview_kind"] == "work" and response.data["can_restore"] is True
    preview = response.data["preview"]
    assert preview["work"]["id"] == str(work.pk)
    assert preview["work"]["abstract"] == "保留的简介"
    assert preview["work"]["edition"]["id"] == str(edition.pk)
    assert preview["work"]["edition"]["contributors"][0]["person"]["id"] == str(person.pk)
    entry.refresh_from_db()
    assert entry.restored_at is None and not Work.objects.filter(pk=work.pk).exists()
    assert not Edition.objects.filter(pk=edition.pk).exists() and AuditEvent.objects.count() == before_events
    assert api_client.get(f"/api/catalog/admin/page-preview/editions/{edition.pk}/").status_code == 404
    api_client.force_authenticate(None)
    assert api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/preview/").status_code in (401, 403)


def test_recycle_scholar_preview_reuses_public_serializer_without_public_perspective(api_client, superadmin_user):
    person = Person.objects.create(preferred_name="53恢复学者", authority_status="verified", biography="实际保留的人物说明")
    profile = ScholarProfile.objects.create(person=person, slug="53-private-scholar", editorial_status="draft")
    entry = recycle_object(profile, actor=superadmin_user, kind="scholar", name=person.preferred_name)
    api_client.force_authenticate(superadmin_user)
    response = api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/preview/")
    assert response.status_code == 200 and response.data["preview_kind"] == "knowledge"
    preview = response.data["preview"]
    assert preview["perspective"]["data"]["person"]["preferred_name"] == person.preferred_name
    assert preview["active_perspective"] == "draft" and preview["perspectives"]["published"]["available"] is False
    assert not ScholarProfile.objects.filter(pk=profile.pk).exists()
    entry.refresh_from_db()
    assert entry.restored_at is None


def test_batch_restore_parent_before_child_and_reuses_single_restore_audit(api_client, superadmin_user):
    work = Work.objects.create(title="53批量父项", document_type="book")
    edition = Edition.objects.create(work=work, state="draft", is_primary=True)
    child = recycle_object(edition, actor=superadmin_user, kind="edition", name=work.title)
    parent = recycle_object(work, actor=superadmin_user, kind="work", name=work.title)
    api_client.force_authenticate(superadmin_user)
    response = api_client.post("/api/catalog/admin/recycle/", {"ids": [str(child.pk), str(parent.pk)]}, format="json")
    assert response.status_code == 200 and response.data["count"] == 2
    assert {row["id"] for row in response.data["results"]} == {str(work.pk), str(edition.pk)}
    assert Work.objects.filter(pk=work.pk).exists() and Edition.objects.get(pk=edition.pk).state == "draft"
    assert AuditEvent.objects.filter(action="record.restore").count() == 2
    assert not Edition.objects.get(pk=edition.pk).active_catalog_revision_id


def test_batch_restore_failure_is_atomic_and_preview_explains_parent_block(api_client, superadmin_user):
    person = Person.objects.create(preferred_name="53未恢复父项")
    scholar = ScholarProfile.objects.create(person=person, slug="53-parent-block", editorial_status="draft")
    topic = Topic.objects.create(name="53不能部分恢复", slug="53-atomic-topic", editorial_status="draft")
    child = recycle_object(scholar, actor=superadmin_user, kind="scholar", name=person.preferred_name)
    recycle_object(person, actor=superadmin_user, kind="person", name=person.preferred_name)
    other = recycle_object(topic, actor=superadmin_user, kind="topic", name=topic.name)
    api_client.force_authenticate(superadmin_user)
    preview = api_client.get(f"/api/catalog/admin/recycle/{child.pk}/preview/")
    assert preview.status_code == 200 and preview.data["can_restore"] is False
    assert "先恢复" in preview.data["blocked_reason"]
    response = api_client.post("/api/catalog/admin/recycle/", {"ids": [str(other.pk), str(child.pk)]}, format="json")
    assert response.status_code == 400
    assert not Topic.objects.filter(pk=topic.pk).exists() and not ScholarProfile.objects.filter(pk=scholar.pk).exists()
    assert not RecycleEntry.objects.filter(pk__in=[child.pk, other.pk], restored_at__isnull=False).exists()
    assert not AuditEvent.objects.filter(action="record.restore").exists()


@pytest.mark.parametrize("payload", [{"ids": []}, {"ids": [str(uuid4())]*2}, {"ids": [str(uuid4()) for _ in range(51)]}])
def test_batch_validation_does_not_write(api_client, superadmin_user, payload):
    api_client.force_authenticate(superadmin_user)
    response = api_client.post("/api/catalog/admin/recycle/", payload, format="json")
    assert response.status_code == 400 and not AuditEvent.objects.filter(action="record.restore").exists()


def test_new_recycle_read_and_batch_require_edit_capability(api_client, reader_user):
    api_client.force_authenticate(reader_user)
    assert api_client.get(f"/api/catalog/admin/recycle/{uuid4()}/preview/").status_code == 403
    assert api_client.post("/api/catalog/admin/recycle/", {"ids": [str(uuid4())]}, format="json").status_code == 403


@pytest.mark.parametrize("reason", ["超"*301, 123, None])
def test_new_delete_reason_validation_preserves_original_record(api_client, superadmin_user, reason):
    work = Work.objects.create(title="53拒绝错误原因", document_type="book")
    api_client.force_authenticate(superadmin_user)
    response = api_client.post(f"/api/catalog/admin/lifecycle/work/{work.pk}/", {"action": "delete", "confirmed": True, "reason": reason}, format="json")
    assert response.status_code == 400 and Work.objects.filter(pk=work.pk).exists()
    assert not RecycleEntry.objects.filter(object_id=work.pk).exists()


def test_recycle_issue_preview_keeps_saved_revision_text_without_publication(api_client, superadmin_user):
    from catalog.services import editorial_issues
    from tests.test_v307_editorial_issues import issue_data
    issue = editorial_issues.create_issue({**issue_data(), "title": "53荐读恢复预览", "items": [],
        "category": "保留的栏目", "body_blocks": [{"type": "paragraph", "text": "实际保存的荐读内容"}]}, superadmin_user)
    entry = recycle_object(issue, actor=superadmin_user, kind="recommendation-issue", name=issue.title)
    api_client.force_authenticate(superadmin_user)
    response = api_client.get(f"/api/catalog/admin/recycle/{entry.pk}/preview/")
    assert response.status_code == 200 and response.data["preview_kind"] == "issue"
    assert response.data["preview"]["body_blocks"] == [{"type": "paragraph", "text": "实际保存的荐读内容"}]
    assert response.data["preview"]["category"] == "保留的栏目" and response.data["preview"]["public_url"] == ""
    entry.refresh_from_db()
    assert entry.restored_at is None
