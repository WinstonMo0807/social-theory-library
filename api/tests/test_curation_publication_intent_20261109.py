from uuid import uuid4

import pytest

from catalog.models import Contribution, EditorialRevision, PublicationBundle, Person, ScholarProfile
from catalog.services.field_assistant import FieldAssistantService
from catalog.services.knowledge_publication import _publish_bundle_entities
from catalog.services.scholar_media import save_scholar_editorial_patch
from .test_editorial_edit_version_v306 import object_editor
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("field,profile_status,expected", [
    ("author", "draft", "published"),
    ("translator", "draft", "draft"),
    ("translator", "published", "published"),
    ("translator", "archived", "archived"),
])
def test_bundle_publishes_identity_without_promoting_translation_to_scholar(
    admin_user, settings, tmp_path, field, profile_status, expected,
):
    _, edition, _, _ = create_item_with_files(settings, tmp_path, title="贡献身份核对")
    created = FieldAssistantService().create_and_link(
        edition_id=edition.pk, field_name=field, label="身份核对人物", actor=admin_user,
    )
    person = Person.objects.get(pk=created["entity"]["id"])
    profile = person.scholar_profile
    profile.editorial_status = profile_status
    profile.save(update_fields=["editorial_status"])
    bundle = PublicationBundle.objects.get(pk=created["bundle_id"])
    _publish_bundle_entities(bundle, actor=admin_user)
    person.refresh_from_db(); profile.refresh_from_db()
    assert person.authority_status == "verified"
    assert profile.editorial_status == expected
    assert Contribution.objects.get(edition=edition, person=person).role == field


def test_preparing_public_scholar_draft_keeps_prose_and_selection_private(api_client, admin_user):
    row, url, _, target = object_editor("scholars", False)
    original = save_scholar_editorial_patch(row.pk, {
        "short_description": "已经审校的简介", "person": {"biography": "已经审校的传记"},
        "portrait_selection": {"person_id": str(row.person_id), "rendition_id": None, "legacy_path": ""},
    }, actor=admin_user, request_key=str(uuid4()))
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    version = api_client.get(url).data["edit_version"]
    saved = api_client.patch(url, {"editorial_status": "published"}, format="json", HTTP_IF_MATCH=version)
    assert saved.status_code == 202, saved.data
    assert saved.data["editorial_status"] == "published"
    assert saved.data["short_description"] == "已经审校的简介"
    assert saved.data["biography"] == "已经审校的传记"
    draft = EditorialRevision.objects.get(target_type=target, target_id=row.pk, status="draft")
    assert draft.materialized_preview["portrait_selection"] == original.materialized_preview["portrait_selection"]
    row.refresh_from_db(); row.person.refresh_from_db()
    assert row.editorial_status == "draft"
    assert row.short_description == "旧内容"
    assert row.person.biography == ""
    assert api_client.patch(url, {"editorial_status": "published"}, format="json", HTTP_IF_MATCH=version).status_code == 409
    published = api_client.post(f"/api/catalog/admin/editorial-revisions/{draft.pk}/publish/", {}, format="json")
    assert published.status_code == 200, published.data
    row.refresh_from_db(); row.person.refresh_from_db()
    assert row.editorial_status == "published"
    assert row.short_description == "已经审校的简介"
    assert row.person.biography == "已经审校的传记"


def test_existing_withdrawal_keeps_its_intent_and_draft_content(api_client, admin_user):
    row, url, field, target = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    version = api_client.get(url).data["edit_version"]
    saved = api_client.patch(url, {field: "保存的新导读", "editorial_status": "archived"},
                             format="json", HTTP_IF_MATCH=version)
    assert saved.status_code == 202, saved.data
    draft = EditorialRevision.objects.get(target_type=target, target_id=row.pk, status="draft")
    response = api_client.get(f"/api/catalog/admin/knowledge-preview/topic/{row.pk}/",
                              {"edit_version": saved.data["edit_version"], "review": "1"})
    assert response.status_code == 200, response.data
    assert response.data["publication_review"]["withdrawing"]
    assert response.data["publication_review"]["draft_revision_id"] == str(draft.pk)
    row.refresh_from_db()
    assert row.editorial_status == "published" and row.description == "旧内容"
