import pytest
from rest_framework.test import APIClient

from accounts.models import User
from ingestion.models import AuditEvent


pytestmark = pytest.mark.django_db
PASSWORD = 'OwnAccountCreate-Testing-2026!'


@pytest.fixture
def owner(settings):
    settings.LIBRARY_OWNER_EMAIL = 'account52-owner@example.test'
    settings.LIBRARY_OWNER_DISPLAY_NAME = '固定所有者'
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    return User.objects.create_user(username='account52-owner', email=settings.LIBRARY_OWNER_EMAIL,
        display_name='保留的所有者存储名称', role='admin', password=PASSWORD)


@pytest.fixture
def client(owner):
    result = APIClient()
    result.force_authenticate(owner)
    return result


def payload(**changes):
    return {'email': 'own-created52@example.test', 'display_name': '自有账号', 'password': PASSWORD, **changes}


def test_owner_creates_real_default_reader_with_profile_private_response_and_password_free_audit(client, owner, mailoutbox):
    response = client.post('/api/auth/users/', payload(), format='json')
    assert response.status_code == 201
    user = User.objects.get(pk=response.data['id'])
    assert user.email == 'own-created52@example.test' and user.display_name == '自有账号'
    assert user.role == 'reader' and user.is_active and not user.is_staff and not user.is_superuser
    assert user.check_password(PASSWORD) and user.password != PASSWORD and user.reader_profile.pk
    assert response.data['annotation_count'] == response.data['bookmark_count'] == response.data['saved_count'] == 0
    assert 'private' in response['Cache-Control'] and 'no-store' in response['Cache-Control']
    assert not {'password', 'username', 'token_version', 'is_superuser', 'is_staff'} & response.data.keys()
    audit = AuditEvent.objects.get(action='admin_create_user', object_id=str(user.id))
    assert audit.actor == owner and audit.before == {}
    assert audit.after == {'email': user.email, 'display_name': user.display_name, 'role': 'reader', 'is_active': True}
    assert PASSWORD not in str(audit.after) and user.password not in str(audit.after)
    assert not mailoutbox
    client.force_authenticate(user)
    me = client.get('/api/auth/me/')
    assert me.status_code == 200 and me.data['capabilities'] == []
    assert client.get('/api/auth/users/').status_code == 403


@pytest.mark.parametrize('role', ['editor', 'admin'])
def test_only_owner_can_create_backend_roles_without_granting_django_superuser(client, role):
    response = client.post('/api/auth/users/', payload(role=role, is_active=False), format='json')
    assert response.status_code == 201 and response.data['role'] == role and not response.data['is_active']
    user = User.objects.get(pk=response.data['id'])
    assert not user.is_superuser and not user.is_staff and not user.is_active


@pytest.mark.parametrize('role', ['editor', 'admin'])
def test_regular_administrator_cannot_assign_new_backend_role_but_can_create_reader(client, role):
    actor = User.objects.create_user(username='account52-admin', email='account52-admin@example.test', role='admin')
    client.force_authenticate(actor)
    count = User.objects.count()
    rejected = client.post('/api/auth/users/', payload(role=role), format='json')
    assert rejected.status_code == 403 and User.objects.count() == count
    assert not AuditEvent.objects.filter(action='admin_create_user').exists()
    accepted = client.post('/api/auth/users/', payload(), format='json')
    assert accepted.status_code == 201 and accepted.data['role'] == 'reader'


@pytest.mark.parametrize('role', [None, 'reader', 'editor'])
def test_public_and_content_roles_cannot_create_accounts_through_admin_api(client, role):
    actor = None if role is None else User.objects.create_user(username='account52-actor', email='account52-actor@example.test', role=role)
    client.force_authenticate(actor)
    count = User.objects.count()
    response = client.post('/api/auth/users/', payload(), format='json')
    assert response.status_code == (401 if role is None else 403)
    assert User.objects.count() == count and not AuditEvent.objects.filter(action='admin_create_user').exists()


@pytest.mark.parametrize('changes', [
    {'email': 'ACCOUNT52-OWNER@EXAMPLE.TEST'}, {'password': '123'}, {'is_superuser': True},
    {'role': 'reviewer'}, {'token_version': 10},
])
def test_reserved_identity_weak_password_and_privilege_fields_are_rejected_without_rows(client, changes):
    count = User.objects.count()
    response = client.post('/api/auth/users/', payload(**changes), format='json')
    assert response.status_code == 400 and User.objects.count() == count
    assert not AuditEvent.objects.filter(action='admin_create_user').exists()


def test_duplicate_email_case_does_not_create_second_account_or_audit(client):
    first = client.post('/api/auth/users/', payload(email='Own-Created52@Example.Test'), format='json')
    assert first.status_code == 201 and first.data['email'] == 'own-created52@example.test'
    count = User.objects.count()
    second = client.post('/api/auth/users/', payload(email=' OWN-CREATED52@EXAMPLE.TEST '), format='json')
    assert second.status_code == 400 and User.objects.count() == count
    assert AuditEvent.objects.filter(action='admin_create_user').count() == 1


def test_failed_audit_rolls_back_new_user_and_profile_without_hiding_failure(client, monkeypatch, caplog):
    count = User.objects.count()
    profiles = User._meta.get_field('reader_profile').related_model.objects.count()
    def refuse(*args, **kwargs):
        raise RuntimeError('own audit failure')
    monkeypatch.setattr(AuditEvent.objects, 'create', refuse)
    response = client.post('/api/auth/users/', payload(), format='json')
    assert response.status_code == 500 and response.data['error']['code'] == 'internal_error'
    assert 'Unhandled API error' in caplog.text
    assert User.objects.count() == count
    assert User._meta.get_field('reader_profile').related_model.objects.count() == profiles


@pytest.mark.parametrize('path', ['/api/auth/me/', '/api/auth/users/{id}/'])
def test_fixed_owner_display_name_is_rejected_before_hidden_storage_changes(client, owner, path):
    before = (owner.display_name, owner.role, owner.is_active, owner.password, owner.token_version)
    response = client.patch(path.format(id=owner.id), {'display_name': '不会公开的新名称'}, format='json')
    assert response.status_code == 400 and 'display_name' in response.data['details']
    owner.refresh_from_db()
    assert (owner.display_name, owner.role, owner.is_active, owner.password, owner.token_version) == before
    assert not AuditEvent.objects.filter(action='admin_update_user').exists()
    shown = client.get('/api/auth/users/').data['results']
    assert next(row for row in shown if row['id'] == owner.id)['display_name'] == '固定所有者'


def test_new_own_reader_name_and_password_round_trip_preserves_role_and_revokes_old_password(client):
    created = client.post('/api/auth/users/', payload(), format='json')
    assert created.status_code == 201
    user = User.objects.get(pk=created.data['id'])
    updated = client.patch(f'/api/auth/users/{user.id}/', {'display_name': '保存后的自有名称'}, format='json')
    assert updated.status_code == 200 and updated.data['display_name'] == '保存后的自有名称'
    new_password = PASSWORD + '-new'
    reset = client.post(f'/api/auth/users/{user.id}/set-password/', {'new_password': new_password}, format='json')
    assert reset.status_code == 200 and 'no-store' in reset['Cache-Control']
    user.refresh_from_db()
    assert user.display_name == '保存后的自有名称' and user.role == 'reader' and user.is_active
    assert user.token_version == 1 and user.check_password(new_password) and not user.check_password(PASSWORD)
    client.force_authenticate(user)
    assert client.get('/api/auth/me/').data['display_name'] == '保存后的自有名称'
