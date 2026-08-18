import pytest
from rest_framework.test import APIClient

from accounts.models import User
from reading.models import ReaderAIConnection
from reading.user_ai import user_ai_configuration
from reading.services import decrypt_private_text


pytestmark = pytest.mark.django_db


def test_reader_ai_connection_is_encrypted_and_key_is_never_serialized(api_client, monkeypatch):
    monkeypatch.setattr("reading.user_ai.validate_public_url", lambda value: value)
    user = User.objects.create_user(
        username="reader-ai@example.org",
        email="reader-ai@example.org",
        role=User.Role.READER,
        password="Reader-AI-Password-2026",
    )
    api_client.force_authenticate(user=user)
    response = api_client.put(
        "/api/reading/library-assistant/connection/",
        {
            "provider": "openai_compatible",
            "base_url": "https://api.openai.com",
            "model": "library-model",
            "api_key": "reader-secret-value",
        },
        format="json",
    )
    assert response.status_code == 200
    assert "api_key" not in response.data
    assert response.data["api_key_configured"] is True
    connection = ReaderAIConnection.objects.get(user=user)
    assert decrypt_private_text(connection.api_key_ciphertext) == "reader-secret-value"
    assert "reader-secret-value" not in response.content.decode("utf-8")
    config = user_ai_configuration(user)
    assert config is not None
    assert config.api_key == "reader-secret-value"
    assert config.model == "library-model"


def test_reader_ai_connection_rejects_private_endpoint(api_client, reader_user):
    api_client.force_authenticate(user=reader_user)
    response = api_client.put(
        "/api/reading/library-assistant/connection/",
        {
            "provider": "openai_compatible",
            "base_url": "http://127.0.0.1:11434",
            "model": "library-model",
            "api_key": "secret",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "私网" in response.data["detail"] or "本机" in response.data["detail"]


def test_reader_ai_connection_test_returns_safe_health_payload(api_client, reader_user, monkeypatch):
    monkeypatch.setattr("reading.user_ai.validate_public_url", lambda value: value)
    api_client.force_authenticate(user=reader_user)
    api_client.put(
        "/api/reading/library-assistant/connection/",
        {
            "provider": "openai_compatible",
            "base_url": "https://api.openai.com",
            "model": "library-model",
            "api_key": "reader-secret-value",
        },
        format="json",
    )
    monkeypatch.setattr(
        "reading.user_ai.AIClient.health_check",
        lambda self: {"available": True, "status": "healthy"},
    )
    response = api_client.post("/api/reading/library-assistant/connection/test/")
    assert response.status_code == 200
    assert response.data["available"] is True
    assert "reader-secret-value" not in response.content.decode("utf-8")


def test_library_assistant_status_prefers_reader_connection_without_server_profile(
    api_client,
    reader_user,
    monkeypatch,
):
    monkeypatch.setattr("reading.user_ai.validate_public_url", lambda value: value)
    api_client.force_authenticate(user=reader_user)
    api_client.put(
        "/api/reading/library-assistant/connection/",
        {
            "provider": "openai_compatible",
            "base_url": "https://api.example.com",
            "model": "reader-model",
            "api_key": "reader-secret-value",
        },
        format="json",
    )
    from reading.models import ReaderAIConnection

    ReaderAIConnection.objects.filter(user=reader_user).update(status=ReaderAIConnection.Status.HEALTHY)
    response = api_client.get("/api/reading/library-assistant/status/")
    assert response.status_code == 200
    assert response.data["effective_source"] == "reader"
    assert response.data["user_configured"] is True
    assert response.data["model"] == "reader-model"
    assert "reader-secret-value" not in response.content.decode("utf-8")
