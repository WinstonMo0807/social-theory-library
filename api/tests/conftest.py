import pytest
from rest_framework.test import APIClient

from accounts.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin@example.org",
        email="admin@example.org",
        display_name="管理员",
        role=User.Role.ADMIN,
        password="Correct-Horse-Battery-2026",
    )


@pytest.fixture
def reader_user(db):
    return User.objects.create_user(
        username="reader@example.org",
        email="reader@example.org",
        display_name="读者",
        role=User.Role.READER,
        password="Reader-Secure-Password-2026",
    )
