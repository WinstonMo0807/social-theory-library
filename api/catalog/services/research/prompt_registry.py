from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from catalog.models import PromptRegistryEntry
from common.capabilities import Capability, has_capability


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: dict) -> str:
    return _hash_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _require_prompt_admin(actor) -> None:
    if not has_capability(actor, Capability.MANAGE_PROMPT_REGISTRY):
        raise PermissionError("只有 Superadmin 可以管理 Prompt Registry。")


@transaction.atomic
def create_prompt_revision(
    *,
    key: str,
    capability: str,
    content: str,
    output_schema: dict,
    actor,
    task_profile_key: str = "",
    provider_guidance: dict | None = None,
) -> PromptRegistryEntry:
    _require_prompt_admin(actor)
    normalized_key = str(key or "").strip()
    normalized_content = str(content or "").strip()
    if not normalized_key or not normalized_content:
        raise ValueError("Prompt key 与内容不能为空。")
    if len(normalized_key) > 160:
        raise ValueError("Prompt key 不能超过 160 个字符。")
    normalized_capability = str(capability or "").strip()
    from common.ai_runtime import AICapability

    if normalized_capability not in AICapability.VALUES:
        raise ValueError("Prompt capability 未注册。")
    normalized_task_profile_key = str(task_profile_key or "").strip()
    if len(normalized_task_profile_key) > 120:
        raise ValueError("Task Profile key 不能超过 120 个字符。")
    if not isinstance(output_schema, dict) or not isinstance(
        provider_guidance or {},
        dict,
    ):
        raise ValueError("Prompt schema 与 Provider guidance 必须是 JSON 对象。")
    previous = PromptRegistryEntry.objects.select_for_update().filter(key=normalized_key).order_by("-version").first()
    version = int(previous.version if previous else 0) + 1
    return PromptRegistryEntry.objects.create(
        key=normalized_key,
        version=version,
        capability=normalized_capability,
        task_profile_key=normalized_task_profile_key,
        content=normalized_content,
        output_schema=dict(output_schema or {}),
        provider_guidance=dict(provider_guidance or {}),
        content_hash=_hash_text(normalized_content),
        schema_hash=_hash_json(dict(output_schema or {})),
        status=PromptRegistryEntry.Status.DRAFT,
        created_by=actor,
    )


@transaction.atomic
def activate_prompt_revision(*, prompt: PromptRegistryEntry, actor) -> PromptRegistryEntry:
    _require_prompt_admin(actor)
    locked = PromptRegistryEntry.objects.select_for_update().get(pk=prompt.pk)
    PromptRegistryEntry.objects.filter(
        key=locked.key,
        status=PromptRegistryEntry.Status.ACTIVE,
    ).exclude(pk=locked.pk).update(status=PromptRegistryEntry.Status.RETIRED)
    locked.status = PromptRegistryEntry.Status.ACTIVE
    locked.activated_by = actor
    locked.activated_at = timezone.now()
    locked.save(update_fields=["status", "activated_by", "activated_at", "updated_at"])
    return locked


def resolve_prompt(*, key: str) -> PromptRegistryEntry | None:
    return PromptRegistryEntry.objects.filter(key=key, status=PromptRegistryEntry.Status.ACTIVE).first()
