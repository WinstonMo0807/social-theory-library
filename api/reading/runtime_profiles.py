from __future__ import annotations

import logging

from django.db import transaction

from common.ai_runtime import (
    AICapability,
    PROFILE_SETTING_KEY,
    current_profile_document,
    profile_environment_status,
    runtime_profile,
    safe_profile_document,
    validate_profile_document,
)
from ingestion.models import AuditEvent
from ingestion.services.ai_client import AIClient, AIConfigurationError


logger = logging.getLogger(__name__)


def runtime_profile_payload() -> dict:
    document = safe_profile_document()
    profiles = []
    for row in document["profiles"]:
        try:
            profile = runtime_profile(row["capability"], row["key"])
            environment = profile_environment_status(profile)
        except (ValueError, AIConfigurationError):
            environment = {
                "endpoint_configured": False,
                "credential_configured": False,
                "restart_may_be_required": True,
            }
        profiles.append({**row, "environment": environment})
    return {
        **document,
        "profiles": profiles,
        "hot_reload_fields": [
            "enabled",
            "provider",
            "model",
            "temperature",
            "max_output_tokens",
            "timeout_seconds",
            "max_input_chars",
            "retrieval_profile",
            "answer_behavior",
            "fallback_profile_key",
        ],
        "deployment_fields": ["endpoint_alias", "credential_alias"],
    }


@transaction.atomic
def save_runtime_profile_document(value: dict, *, actor, request_id: str = "") -> dict:
    from catalog.models import SiteSetting

    validated = validate_profile_document(value)
    before = safe_profile_document(current_profile_document())
    setting, _created = SiteSetting.objects.select_for_update().update_or_create(
        key=PROFILE_SETTING_KEY,
        defaults={
            "value": validated,
            "public": False,
            "updated_by": actor,
        },
    )
    after = safe_profile_document(validated)
    AuditEvent.objects.create(
        actor=actor,
        action="ai_runtime_profiles_update",
        object_type="SiteSetting",
        object_id=str(setting.id),
        before=before,
        after=after,
        request_id=str(request_id or "")[:120],
    )
    return runtime_profile_payload()


def test_runtime_profile(profile_key: str) -> dict:
    document = validate_profile_document(current_profile_document())
    rows = {row["key"]: row for row in document["profiles"]}
    row = rows.get(str(profile_key or "").strip().casefold())
    if row is None:
        raise ValueError("AI runtime profile 不存在。")
    client = AIClient(capability=row["capability"], profile_key=row["key"])
    result = client.health_check()
    reason = str(result.pop("reason", "") or "")
    if reason:
        logger.warning(
            "AI profile health check failed profile=%s capability=%s provider=%s",
            row["key"],
            row["capability"],
            row["provider"],
        )
    return {
        "profile_key": row["key"],
        "capability": row["capability"],
        "provider": row["provider"],
        "model": row["model"],
        "configured": bool(result.get("configured")),
        "available": bool(result.get("available")),
        "status": result.get("status", "unknown"),
        "detail": (
            "模型服务可用。"
            if result.get("available")
            else "模型服务当前不可用，请核对服务器端 endpoint 与 credential alias。"
        ),
        "secret_values_exposed": False,
    }


def active_library_runtime_summary() -> dict:
    try:
        profile = runtime_profile(AICapability.LIBRARY_QA)
    except ValueError as exc:
        return {
            "configured": False,
            "available": False,
            "status": "invalid_profile",
            "detail": str(exc),
        }
    environment = profile_environment_status(profile)
    return {
        "configured": bool(profile.enabled and profile.provider != "none" and profile.model),
        "enabled": profile.enabled,
        "profile_key": profile.key,
        "capability": profile.capability,
        "provider": profile.provider,
        "model": profile.model,
        "retrieval_profile": profile.retrieval_profile,
        "answer_behavior": profile.answer_behavior,
        "endpoint_configured": environment["endpoint_configured"],
        "credential_configured": environment["credential_configured"],
    }
