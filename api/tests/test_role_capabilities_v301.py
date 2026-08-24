from copy import deepcopy
from uuid import uuid4

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from accounts.models import User
from accounts.admin import LibraryUserChangeForm, LibraryUserCreationForm
from catalog.models import SiteSetting
from common.capabilities import Capability, OWNER_ONLY_CAPABILITIES, capability_snapshot
from common.middleware import OwnerOnlyDjangoAdminMiddleware
from distribution.models import CloudProvider


pytestmark = pytest.mark.django_db


def _user(suffix: str, role: str, *, superuser: bool = False) -> User:
    return User.objects.create_user(
        username=f"v301-{suffix}@example.test",
        email=f"v301-{suffix}@example.test",
        display_name=suffix,
        role=role,
        is_staff=superuser,
        is_superuser=superuser,
        password="V301-Permissions-2026",
    )


def _owner(settings) -> User:
    settings.LIBRARY_OWNER_EMAIL = "winston@example.test"
    settings.LIBRARY_OWNER_DISPLAY_NAME = "Winston"
    return User.objects.create_user(
        username="winston@example.test",
        email="winston@example.test",
        display_name="stored-name-is-not-authority",
        role=User.Role.ADMIN,
        password="V301-Owner-2026",
    )


def test_only_configured_owner_receives_owner_capabilities(settings):
    settings.LIBRARY_OWNER_EMAIL = "winston@example.test"
    reader = _user("reader", User.Role.READER)
    editor = _user("editor", User.Role.EDITOR)
    admin = _user("admin", User.Role.ADMIN)
    arbitrary_superuser = _user("django-root", User.Role.ADMIN, superuser=True)
    owner = _owner(settings)

    assert capability_snapshot(reader).capabilities == ()
    assert {
        Capability.UPLOAD,
        Capability.EDIT_METADATA,
        Capability.REVIEW_CANDIDATE,
        Capability.PUBLISH_WORK,
        Capability.PUBLISH_AUTHORITY,
        Capability.RUN_ENRICHMENT,
    } <= set(capability_snapshot(editor).capabilities)
    assert {
        Capability.MANAGE_USERS,
        Capability.MANAGE_AI,
        Capability.CONFIGURE_PROVIDERS,
        Capability.RETRY_JOBS,
    } <= set(capability_snapshot(admin).capabilities)
    assert set(capability_snapshot(admin).capabilities).isdisjoint(OWNER_ONLY_CAPABILITIES)
    assert set(capability_snapshot(arbitrary_superuser).capabilities).isdisjoint(
        OWNER_ONLY_CAPABILITIES
    )
    assert OWNER_ONLY_CAPABILITIES <= set(capability_snapshot(owner).capabilities)


def test_legacy_reviewer_is_presented_and_authorized_as_editor(api_client, settings):
    settings.LIBRARY_OWNER_EMAIL = ""
    reviewer = _user("legacy-reviewer", User.Role.REVIEWER)

    assert capability_snapshot(reviewer).access_level == "editor"
    assert Capability.PUBLISH_WORK in capability_snapshot(reviewer).capabilities
    api_client.force_authenticate(reviewer)
    current = api_client.get("/api/auth/me/")
    assert current.status_code == 200
    assert current.data["role"] == User.Role.EDITOR
    assert current.data["access_level"] == "editor"

    change_form = LibraryUserChangeForm(instance=reviewer)
    creation_form = LibraryUserCreationForm()
    assert User.Role.REVIEWER not in dict(change_form.fields["role"].choices)
    assert User.Role.REVIEWER not in dict(creation_form.fields["role"].choices)
    assert change_form.initial["role"] == User.Role.EDITOR


def test_administrator_manages_ordinary_user_but_owner_controls_roles(
    api_client,
    settings,
):
    admin = _user("user-admin", User.Role.ADMIN)
    peer_admin = _user("peer-admin", User.Role.ADMIN)
    reader = _user("managed-reader", User.Role.READER)
    owner = _owner(settings)

    api_client.force_authenticate(admin)
    renamed = api_client.patch(
        f"/api/auth/users/{reader.id}/",
        {"display_name": "Renamed reader"},
        format="json",
    )
    assert renamed.status_code == 200
    role_denied = api_client.patch(
        f"/api/auth/users/{reader.id}/",
        {"role": User.Role.EDITOR},
        format="json",
    )
    assert role_denied.status_code == 403
    owner_denied = api_client.patch(
        f"/api/auth/users/{owner.id}/",
        {"display_name": "not allowed"},
        format="json",
    )
    assert owner_denied.status_code == 403
    peer_admin_denied = api_client.patch(
        f"/api/auth/users/{peer_admin.id}/",
        {"is_active": False},
        format="json",
    )
    assert peer_admin_denied.status_code == 403

    api_client.force_authenticate(owner)
    promoted = api_client.patch(
        f"/api/auth/users/{reader.id}/",
        {"role": User.Role.EDITOR},
        format="json",
    )
    assert promoted.status_code == 200
    assert promoted.data["role"] == User.Role.EDITOR
    reviewer_denied = api_client.patch(
        f"/api/auth/users/{reader.id}/",
        {"role": User.Role.REVIEWER},
        format="json",
    )
    assert reviewer_denied.status_code == 400
    owner_row = api_client.get(f"/api/auth/users/{owner.id}/")
    assert owner_row.status_code == 200
    assert owner_row.data["display_name"] == "Winston"
    assert owner_row.data["system_owner_label"] == "Winston"


def test_profile_and_admin_updates_cannot_transfer_or_release_owner_identity(
    api_client,
    settings,
):
    reader = _user("identity-reader", User.Role.READER)
    admin = _user("identity-admin", User.Role.ADMIN)
    owner = _owner(settings)

    api_client.force_authenticate(reader)
    reader_claim = api_client.patch(
        "/api/auth/me/",
        {"email": "  WINSTON@EXAMPLE.TEST  "},
        format="json",
    )
    assert reader_claim.status_code == 400
    reader.refresh_from_db()
    assert reader.email == "v301-identity-reader@example.test"

    api_client.force_authenticate(owner)
    owner_release = api_client.patch(
        "/api/auth/me/",
        {"email": "replacement@example.test"},
        format="json",
    )
    assert owner_release.status_code == 400
    owner.refresh_from_db()
    assert owner.email == "winston@example.test"

    api_client.force_authenticate(admin)
    admin_claim = api_client.patch(
        f"/api/auth/users/{reader.id}/",
        {"email": "Winston@Example.Test"},
        format="json",
    )
    assert admin_claim.status_code == 400
    reader.refresh_from_db()
    assert reader.email == "v301-identity-reader@example.test"


def test_registration_and_admin_forms_reserve_owner_and_enforce_case_insensitive_email_uniqueness(
    api_client,
    settings,
):
    settings.LIBRARY_OWNER_EMAIL = "Winston@Example.Test"
    existing = _user("mixed-duplicate", User.Role.READER)
    existing.email = "Mixed.Duplicate@Example.Test"
    existing.save(update_fields=["email"])

    owner_registration = api_client.post(
        "/api/auth/register/",
        {
            "email": "wINSTON@example.test",
            "display_name": "not owner",
            "password": "V301-Register-Password-2026",
        },
        format="json",
    )
    assert owner_registration.status_code == 400

    duplicate_registration = api_client.post(
        "/api/auth/register/",
        {
            "email": "mixed.duplicate@example.test",
            "display_name": "duplicate",
            "password": "V301-Register-Password-2026",
        },
        format="json",
    )
    assert duplicate_registration.status_code == 400

    creation_form = LibraryUserCreationForm(
        data={
            "username": "owner-claim@example.test",
            "email": "WINSTON@example.test",
            "display_name": "owner claim",
            "role": User.Role.ADMIN,
            "password1": "V301-Admin-Create-2026",
            "password2": "V301-Admin-Create-2026",
        }
    )
    assert not creation_form.is_valid()
    assert "email" in creation_form.errors

    duplicate_creation_form = LibraryUserCreationForm(
        data={
            "username": "duplicate@example.test",
            "email": "mixed.duplicate@example.test",
            "display_name": "duplicate",
            "role": User.Role.READER,
            "password1": "V301-Admin-Create-2026",
            "password2": "V301-Admin-Create-2026",
        }
    )
    assert not duplicate_creation_form.is_valid()
    assert "email" in duplicate_creation_form.errors

    subject = _user("change-subject", User.Role.READER)
    duplicate_change_form = LibraryUserChangeForm(
        instance=subject,
        data={
            "username": subject.username,
            "email": "mixed.duplicate@example.test",
            "display_name": subject.display_name,
            "role": subject.role,
            "is_active": True,
            "date_joined": subject.date_joined,
            "locale": subject.locale,
            "password": subject.password,
        },
    )
    assert not duplicate_change_form.is_valid()
    assert "email" in duplicate_change_form.errors

    owner = _owner(settings)
    owner_release_form = LibraryUserChangeForm(
        instance=owner,
        data={
            "username": owner.username,
            "email": "replacement@example.test",
            "display_name": owner.display_name,
            "role": User.Role.ADMIN,
            "is_active": True,
            "date_joined": owner.date_joined,
            "locale": owner.locale,
            "password": owner.password,
        },
    )
    assert not owner_release_form.is_valid()
    assert "email" in owner_release_form.errors

    owner_downgrade_form = LibraryUserChangeForm(
        instance=owner,
        data={
            "username": owner.username,
            "email": "WINSTON@example.test",
            "display_name": owner.display_name,
            "role": User.Role.READER,
            "is_active": True,
            "date_joined": owner.date_joined,
            "locale": owner.locale,
            "password": owner.password,
        },
    )
    assert not owner_downgrade_form.is_valid()
    assert "__all__" in owner_downgrade_form.errors


def test_administrator_can_configure_provider_but_not_credentials_or_delete(
    api_client,
    settings,
):
    admin = _user("provider-admin", User.Role.ADMIN)
    owner = _owner(settings)
    api_client.force_authenticate(admin)
    created = api_client.post(
        "/api/distribution/providers/",
        {
            "name": "Local projection",
            "provider_type": "s3",
            "endpoint_url": "https://objects.example.test",
            "bucket": "library",
            "credential_reference": "",
            "enabled": False,
            "is_default": False,
        },
        format="json",
    )
    assert created.status_code == 201
    provider_id = created.data["id"]
    renamed = api_client.patch(
        f"/api/distribution/providers/{provider_id}/",
        {"name": "Configured projection"},
        format="json",
    )
    assert renamed.status_code == 200
    secret_denied = api_client.patch(
        f"/api/distribution/providers/{provider_id}/",
        {"credential_reference": "PRODUCTION_S3"},
        format="json",
    )
    assert secret_denied.status_code == 403
    assert api_client.delete(f"/api/distribution/providers/{provider_id}/").status_code == 403

    api_client.force_authenticate(owner)
    credential_saved = api_client.patch(
        f"/api/distribution/providers/{provider_id}/",
        {"credential_reference": "PRODUCTION_S3"},
        format="json",
    )
    assert credential_saved.status_code == 200
    assert CloudProvider.objects.get(pk=provider_id).credential_reference == "PRODUCTION_S3"
    assert api_client.delete(f"/api/distribution/providers/{provider_id}/").status_code == 204


def test_ai_runtime_allows_admin_safe_fields_and_reserves_aliases_for_owner(
    api_client,
    settings,
):
    admin = _user("runtime-admin", User.Role.ADMIN)
    owner = _owner(settings)
    api_client.force_authenticate(admin)
    current = api_client.get("/api/reading/admin/ai-runtime-profiles/")
    assert current.status_code == 200
    assert current.data["permissions"] == {
        "can_edit_profiles": True,
        "can_edit_sensitive_aliases": False,
        "can_remove_profiles": False,
    }
    document = {
        "active": deepcopy(current.data["active"]),
        "profiles": deepcopy(current.data["profiles"]),
    }
    document["profiles"][0]["temperature"] = 0.1
    safe_update = api_client.put(
        "/api/reading/admin/ai-runtime-profiles/",
        document,
        format="json",
    )
    assert safe_update.status_code == 200
    assert SiteSetting.objects.filter(key="ai_runtime_profiles").exists()

    sensitive = {
        "active": deepcopy(safe_update.data["active"]),
        "profiles": deepcopy(safe_update.data["profiles"]),
    }
    sensitive["profiles"][0]["credential_alias"] = "cloud_primary"
    denied = api_client.put(
        "/api/reading/admin/ai-runtime-profiles/",
        sensitive,
        format="json",
    )
    assert denied.status_code == 403

    api_client.force_authenticate(owner)
    allowed = api_client.put(
        "/api/reading/admin/ai-runtime-profiles/",
        sensitive,
        format="json",
    )
    assert allowed.status_code == 200
    assert allowed.data["permissions"]["can_edit_sensitive_aliases"] is True


def test_django_superuser_does_not_cross_owner_only_endpoints(api_client, settings):
    settings.LIBRARY_OWNER_EMAIL = "winston@example.test"
    arbitrary_superuser = _user("non-owner-root", User.Role.ADMIN, superuser=True)
    owner = _owner(settings)

    api_client.force_authenticate(arbitrary_superuser)
    assert api_client.get("/api/catalog/admin/prompt-registry/").status_code == 403
    assert api_client.get("/api/distribution/backups/").status_code == 403

    api_client.force_authenticate(owner)
    assert api_client.get("/api/catalog/admin/prompt-registry/").status_code == 200
    assert api_client.get("/api/distribution/backups/").status_code == 200


def test_django_admin_site_is_owner_only(settings):
    settings.LIBRARY_OWNER_EMAIL = "winston-root@example.test"
    arbitrary_superuser = User.objects.create_superuser(
        username="other-root@example.test",
        email="other-root@example.test",
        password="V301-Django-Root-2026",
    )
    owner = User.objects.create_superuser(
        username="winston-root@example.test",
        email="winston-root@example.test",
        password="V301-Django-Owner-2026",
    )

    middleware = OwnerOnlyDjangoAdminMiddleware(lambda _request: HttpResponse("ok"))
    denied_request = RequestFactory().get("/admin/")
    denied_request.user = arbitrary_superuser
    assert middleware(denied_request).status_code == 403
    owner_request = RequestFactory().get("/admin/")
    owner_request.user = owner
    assert middleware(owner_request).status_code == 200


def test_editor_publish_and_owner_delete_are_enforced_on_ingestion_endpoints(
    api_client,
    settings,
):
    missing_item = uuid4()
    editor = _user("publisher", User.Role.EDITOR)
    admin = _user("deletion-admin", User.Role.ADMIN)
    owner = _owner(settings)

    api_client.force_authenticate(editor)
    assert api_client.post(f"/api/ingestion/items/{missing_item}/publish/", {}).status_code == 404

    api_client.force_authenticate(admin)
    assert api_client.post(f"/api/ingestion/items/{missing_item}/delete/", {}).status_code == 403

    api_client.force_authenticate(owner)
    assert api_client.post(f"/api/ingestion/items/{missing_item}/delete/", {}).status_code == 404
