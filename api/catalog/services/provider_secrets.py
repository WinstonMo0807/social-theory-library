"""Encrypted server-side Provider credentials.

Only aliases and status metadata leave the server.  Ciphertext uses the
project's existing PRIVATE_DATA_ENCRYPTION_KEY convention.
"""

from __future__ import annotations

import re

from cryptography.fernet import InvalidToken
from django.db import DatabaseError, transaction
from django.utils import timezone

from catalog.models import ProviderCredentialSecret
from ingestion.models import AuditEvent
from reading.services import decrypt_private_text, encrypt_private_text


ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MAX_SECRET_CHARS = 16_384


class ProviderSecretError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_secret_alias(value: object) -> str:
    alias = str(value or "").strip().casefold()
    if not ALIAS_RE.fullmatch(alias):
        raise ProviderSecretError("invalid_alias", "Credential alias 格式无效。")
    return alias


def resolve_provider_secret(alias: object, *, purpose: str | None = None) -> str:
    try:
        normalized = normalize_secret_alias(alias)
    except ProviderSecretError:
        return ""
    try:
        queryset = ProviderCredentialSecret.objects.filter(alias=normalized)
        if purpose:
            queryset = queryset.filter(purpose=purpose)
        row = queryset.only("ciphertext").first()
    except (DatabaseError, RuntimeError):
        return ""
    if row is None:
        return ""
    try:
        return decrypt_private_text(row.ciphertext)
    except (InvalidToken, ValueError, TypeError):
        return ""


def serialize_provider_secret(row: ProviderCredentialSecret) -> dict:
    return {
        "alias": row.alias,
        "purpose": row.purpose,
        "provider_key": row.provider_key,
        "configured": bool(row.ciphertext),
        "updated_at": row.updated_at,
        "last_tested_at": row.last_tested_at,
        "last_test_status": row.last_test_status,
        "last_test_message": row.last_test_message,
        "secret_values_exposed": False,
    }


def provider_secret_registry_payload() -> dict:
    rows = [serialize_provider_secret(row) for row in ProviderCredentialSecret.objects.all()]
    return {
        "secrets": rows,
        "summary": {
            "configured": len(rows),
            "research_source": sum(row["purpose"] == "research_source" for row in rows),
            "ai_runtime": sum(row["purpose"] == "ai_runtime" for row in rows),
        },
        "secret_values_exposed": False,
    }


@transaction.atomic
def set_provider_secret(
    *,
    alias: object,
    purpose: str,
    provider_key: object,
    secret: object,
    actor,
    request_id: str = "",
) -> ProviderCredentialSecret:
    normalized = normalize_secret_alias(alias)
    if purpose not in ProviderCredentialSecret.Purpose.values:
        raise ProviderSecretError("invalid_purpose", "Provider credential 用途无效。")
    plain = str(secret or "")
    if not plain or len(plain) > MAX_SECRET_CHARS:
        raise ProviderSecretError("invalid_secret", "Credential 不能为空且不能超过安全长度。")
    provider = str(provider_key or "").strip().casefold()[:120]
    previous = ProviderCredentialSecret.objects.select_for_update().filter(alias=normalized).first()
    row, _created = ProviderCredentialSecret.objects.update_or_create(
        alias=normalized,
        defaults={
            "purpose": purpose,
            "provider_key": provider,
            "ciphertext": encrypt_private_text(plain),
            "key_version": "private-data-fernet-v1",
            "updated_by": actor,
            "last_tested_at": None,
            "last_test_status": "",
            "last_test_message": "",
        },
    )
    AuditEvent.objects.create(
        actor=actor,
        action="provider_credential_secret_update",
        object_type="ProviderCredentialSecret",
        object_id=str(row.id),
        before={"configured": previous is not None, "alias": normalized},
        after={
            "configured": True,
            "alias": normalized,
            "purpose": purpose,
            "provider_key": provider,
        },
        request_id=str(request_id or "")[:120],
    )
    return row


@transaction.atomic
def delete_provider_secret(*, alias: object, actor, request_id: str = "") -> bool:
    normalized = normalize_secret_alias(alias)
    row = ProviderCredentialSecret.objects.select_for_update().filter(alias=normalized).first()
    if row is None:
        return False
    object_id = str(row.id)
    safe_before = {
        "configured": True,
        "alias": row.alias,
        "purpose": row.purpose,
        "provider_key": row.provider_key,
    }
    row.delete()
    AuditEvent.objects.create(
        actor=actor,
        action="provider_credential_secret_delete",
        object_type="ProviderCredentialSecret",
        object_id=object_id,
        before=safe_before,
        after={"configured": False, "alias": normalized},
        request_id=str(request_id or "")[:120],
    )
    return True


def record_provider_secret_test(
    *,
    alias: object,
    status: str,
    message: str = "",
) -> None:
    normalized = normalize_secret_alias(alias)
    ProviderCredentialSecret.objects.filter(alias=normalized).update(
        last_tested_at=timezone.now(),
        last_test_status=str(status or "")[:32],
        last_test_message=str(message or "")[:500],
    )
