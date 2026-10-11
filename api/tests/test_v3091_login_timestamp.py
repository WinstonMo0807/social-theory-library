from datetime import datetime, timezone

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from accounts.serializers import api_settings


pytestmark = pytest.mark.django_db


def test_successful_login_records_time_only_when_enabled_and_failed_login_never_changes_it(monkeypatch):
    recorded = datetime(2026, 10, 12, tzinfo=timezone.utc)
    monkeypatch.setattr('django.contrib.auth.models.timezone.now', lambda: recorded)
    for enabled in (True, False):
        monkeypatch.setattr(api_settings, 'UPDATE_LAST_LOGIN', enabled)
        user = User.objects.create_user(username=f'own-login52-{enabled}', email=f'own-login52-{enabled}@example.test',
            role='reader', password='OwnLoginTime-Testing-2026!')
        client = APIClient()
        failed = client.post('/api/auth/login/', {'email': user.email, 'password': 'incorrect'}, format='json')
        assert failed.status_code == 400
        user.refresh_from_db()
        assert user.last_login is None
        success = client.post('/api/auth/login/', {'email': user.email, 'password': 'OwnLoginTime-Testing-2026!'}, format='json')
        assert success.status_code == 200
        user.refresh_from_db()
        assert user.last_login == (recorded if enabled else None)
        before = user.last_login
        failed = client.post('/api/auth/login/', {'email': user.email, 'password': 'incorrect'}, format='json')
        assert failed.status_code == 400
        user.refresh_from_db()
        assert user.last_login == before and user.role == 'reader' and not user.is_staff and not user.is_superuser
