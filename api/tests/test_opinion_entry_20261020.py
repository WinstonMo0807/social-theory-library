"""Synthetic history contracts for later unified acceptance; no production records."""
from uuid import uuid4

import pytest

from reading import privacy, research
from reading.models import ReaderSearchRecord


pytestmark = pytest.mark.django_db
PATH = "/api/reading/search-records/"


def save(user, query, **filters):
    return ReaderSearchRecord.objects.create(user=user, request_id=uuid4(),
        data_ciphertext=research.pack({"query": query, "filters": filters}))


def test_history_requires_matching_owner_and_does_not_grant_staff_access(api_client, reader_user, admin_user):
    own = save(reader_user, "合成本人问题", work_ids=[str(uuid4())])
    other = save(admin_user, "合成管理者私人问题")
    assert api_client.get(PATH, {"owner_id": reader_user.pk}).status_code in {401, 403}
    api_client.force_authenticate(admin_user)
    assert api_client.get(PATH, {"owner_id": reader_user.pk}).status_code == 403
    response = api_client.get(PATH, {"owner_id": admin_user.pk})
    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(other.pk)]
    assert str(own.pk) not in str(response.data)
    assert "no-store" in response["Cache-Control"]
    assert {"Cookie", "Authorization"} <= set(response["Vary"].split(", "))


def test_history_default_off_and_read_never_enables_recording(api_client, reader_user):
    assert privacy.retention_enabled(reader_user, "search_history") is False
    old = save(reader_user, "合成旧记录", authors=[str(uuid4())], languages=["zh"])
    api_client.force_authenticate(reader_user)
    response = api_client.get(PATH, {"owner_id": reader_user.pk})
    assert response.data["recording_enabled"] is False
    assert response.data["owner_id"] == str(reader_user.pk)
    assert response.data["results"][0]["filters"] == research.unpack(old)["filters"]
    assert "合成旧记录".encode() not in bytes(old.data_ciphertext)
    assert privacy.retention_enabled(reader_user, "search_history") is False
    assert api_client.post(PATH, {"query": "不接受页面直接写入"}, format="json").status_code == 405
    assert ReaderSearchRecord.objects.filter(user=reader_user).count() == 1


def test_history_pagination_preserves_filters_and_uses_newest_first(api_client, reader_user):
    first = save(reader_user, "合成较早问题")
    second = save(reader_user, "合成较新问题", topic_ids=[str(uuid4())], year_min=2000)
    api_client.force_authenticate(reader_user)
    response = api_client.get(PATH, {"owner_id": reader_user.pk, "page_size": 1, "page": 1})
    assert response.data["count"] == 2
    assert response.data["results"][0]["id"] == str(second.pk)
    assert response.data["results"][0]["filters"]["year_min"] == 2000
    next_page = api_client.get(PATH, {"owner_id": reader_user.pk, "page_size": 1, "page": 2})
    assert next_page.data["results"][0]["id"] == str(first.pk)


@pytest.mark.parametrize("query", [{}, {"page": 0}, {"page_size": 21}])
def test_history_rejects_missing_owner_or_invalid_paging(api_client, reader_user, query):
    api_client.force_authenticate(reader_user)
    params = {"owner_id": reader_user.pk, **query} if query else {}
    assert api_client.get(PATH, params).status_code == (400 if query else 403)
