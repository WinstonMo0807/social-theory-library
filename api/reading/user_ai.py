from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.db import transaction

from common.ai_runtime import AICapability
from ingestion.services.ai_client import AIClient, AIConfiguration

from catalog.services.field_enrichment.web import WebFetchError, validate_public_url

from .models import ReaderAIConnection
from .services import decrypt_private_text, encrypt_private_text


class ReaderAIConfigurationError(ValueError):
    code = "reader_ai_configuration_error"


def _normalize_base_url(value: str) -> str:
    raw = " ".join(str(value or "").split()).strip()
    if not raw:
        raise ReaderAIConfigurationError("请输入模型服务地址。")
    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/")
    if path.casefold().endswith("/v1"):
        path = path[:-3].rstrip("/")
    normalized = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    try:
        return validate_public_url(normalized).rstrip("/")
    except WebFetchError as exc:
        raise ReaderAIConfigurationError(str(exc)) from exc


def _connection(user):
    return ReaderAIConnection.objects.filter(user=user).first()


def connection_payload(user) -> dict:
    connection = _connection(user)
    if connection is None:
        return {
            "configured": False,
            "enabled": False,
            "provider": "",
            "base_url": "",
            "model": "",
            "status": "not_configured",
            "api_key_configured": False,
            "last_checked_at": None,
            "last_error_code": "",
            "last_error_message": "",
        }
    return {
        "configured": True,
        "enabled": connection.enabled,
        "provider": connection.provider,
        "base_url": connection.base_url,
        "model": connection.model,
        "status": connection.status,
        "api_key_configured": bool(connection.api_key_ciphertext),
        "last_checked_at": connection.last_checked_at,
        "last_error_code": connection.last_error_code,
        "last_error_message": connection.last_error_message,
    }


def _configuration(connection: ReaderAIConnection) -> AIConfiguration:
    try:
        api_key = decrypt_private_text(connection.api_key_ciphertext)
    except Exception as exc:
        raise ReaderAIConfigurationError("模型密钥无法解密，请重新保存。") from exc
    if connection.provider != ReaderAIConnection.Provider.OLLAMA and not api_key:
        raise ReaderAIConfigurationError("该模型服务需要 API Key。")
    host = (urlsplit(_normalize_base_url(connection.base_url)).hostname or "").casefold()
    return AIConfiguration(
        provider=connection.provider,
        base_url=_normalize_base_url(connection.base_url),
        api_key=api_key,
        metadata_model=connection.model,
        classifier_model=connection.model,
        vision_model="",
        timeout=float(getattr(settings, "AI_TIMEOUT", 60)),
        max_concurrency=int(getattr(settings, "AI_MAX_CONCURRENCY", 2)),
        max_input_chars=int(getattr(settings, "AI_MAX_INPUT_CHARS", 16000)),
        allowed_hosts=(host,),
        capability=AICapability.LIBRARY_QA,
        profile_key=f"reader-{connection.user_id}",
        model=connection.model,
        temperature=float(getattr(settings, "AI_LIBRARY_TEMPERATURE", 0.2)),
        max_output_tokens=int(getattr(settings, "AI_LIBRARY_MAX_OUTPUT_TOKENS", 2048)),
        retrieval_profile="stable",
        answer_behavior="evidence_only",
    )


def user_ai_configuration(user) -> AIConfiguration | None:
    connection = _connection(user)
    if connection is None or not connection.enabled:
        return None
    return _configuration(connection)


@transaction.atomic
def save_connection(user, *, provider: str, base_url: str, model: str, api_key: str | None = None, enabled: bool = True) -> dict:
    provider = str(provider or "").strip().casefold()
    if provider not in {choice for choice, _label in ReaderAIConnection.Provider.choices}:
        raise ReaderAIConfigurationError("不支持的模型服务类型。")
    model = " ".join(str(model or "").split()).strip()
    if not model or len(model) > 300:
        raise ReaderAIConfigurationError("请输入有效的模型名称。")
    base_url = _normalize_base_url(base_url)
    connection = ReaderAIConnection.objects.select_for_update().filter(user=user).first()
    if connection is None:
        connection = ReaderAIConnection(user=user)
    supplied_key = str(api_key or "")
    if supplied_key:
        connection.api_key_ciphertext = encrypt_private_text(supplied_key)
    elif connection.pk is None and provider != ReaderAIConnection.Provider.OLLAMA:
        raise ReaderAIConfigurationError("首次保存该服务时必须填写 API Key。")
    elif provider != ReaderAIConnection.Provider.OLLAMA and not connection.api_key_ciphertext:
        raise ReaderAIConfigurationError("该模型服务需要 API Key。")
    connection.provider = provider
    connection.base_url = base_url
    connection.model = model
    connection.enabled = bool(enabled)
    connection.status = ReaderAIConnection.Status.NOT_TESTED
    connection.last_checked_at = None
    connection.last_error_code = ""
    connection.last_error_message = ""
    connection.save()
    return connection_payload(user)


def delete_connection(user) -> None:
    ReaderAIConnection.objects.filter(user=user).delete()


def test_connection(user) -> dict:
    connection = _connection(user)
    if connection is None:
        raise ReaderAIConfigurationError("请先保存模型服务配置。")
    try:
        result = AIClient(_configuration(connection)).health_check()
        connection.status = (
            ReaderAIConnection.Status.HEALTHY
            if result.get("available")
            else ReaderAIConnection.Status.UNAVAILABLE
        )
        connection.last_error_code = "" if result.get("available") else str(result.get("status") or "provider_unavailable")
        connection.last_error_message = "" if result.get("available") else str(result.get("reason") or "模型服务暂不可用")[:500]
    except (ReaderAIConfigurationError, WebFetchError) as exc:
        connection.status = ReaderAIConnection.Status.INVALID
        connection.last_error_code = getattr(exc, "code", "invalid_configuration")
        connection.last_error_message = str(exc)[:500]
        result = {"available": False, "status": "invalid", "reason": str(exc)}
    connection.last_checked_at = __import__("django.utils.timezone", fromlist=["now"]).now()
    connection.save(update_fields=["status", "last_error_code", "last_error_message", "last_checked_at", "updated_at"])
    return {
        **connection_payload(user),
        "available": bool(result.get("available")),
        "detail": "模型服务可用。" if result.get("available") else connection.last_error_message,
    }
