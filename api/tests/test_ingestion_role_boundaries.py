import pytest

from accounts.models import User


pytestmark = pytest.mark.django_db


def make_user(role: str, suffix: str):
    return User.objects.create_user(
        username=f"{role}-{suffix}",
        email=f"{role}-{suffix}@example.test",
        password="safe-test-password",
        role=role,
    )


@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.EDITOR])
def test_catalog_writers_can_create_upload_batches(api_client, role):
    user = make_user(role, "writer")
    api_client.force_authenticate(user)

    response = api_client.post(
        "/api/ingestion/batches/create/",
        {"expected_count": 1},
        format="json",
    )

    assert response.status_code == 201


def test_reviewer_can_read_review_queue_but_cannot_create_or_delete_ingestion_records(
    api_client,
    admin_user,
):
    reviewer = make_user(User.Role.REVIEWER, "review-only")
    api_client.force_authenticate(reviewer)

    list_response = api_client.get("/api/ingestion/items/")
    create_response = api_client.post(
        "/api/ingestion/batches/create/",
        {"expected_count": 1},
        format="json",
    )

    assert list_response.status_code == 200
    assert create_response.status_code == 403


def test_reader_cannot_open_ingestion_queue(api_client, reader_user):
    api_client.force_authenticate(reader_user)

    assert api_client.get("/api/ingestion/items/").status_code == 403
