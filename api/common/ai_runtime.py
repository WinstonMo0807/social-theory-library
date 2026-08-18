from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
import re
from typing import Any

from django.conf import settings
from django.db import DatabaseError


PROFILE_DOCUMENT_VERSION = "ai-runtime-profiles-v1"
PROFILE_SETTING_KEY = "ai_runtime_profiles"


class AICapability:
    METADATA_EXTRACTION = "metadata_extraction"
    LIBRARY_QA = "library_qa"
    FIELD_ENRICHMENT_OPTIONAL = "field_enrichment_optional"

    VALUES = (
        METADATA_EXTRACTION,
        LIBRARY_QA,
        FIELD_ENRICHMENT_OPTIONAL,
    )


SUPPORTED_AI_PROVIDERS = {"none", "ollama", "vllm", "openai_compatible"}
LIBRARY_RETRIEVAL_PROFILES = {"stable", "experimental_v2"}
PROFILE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class CapabilityPolicy:
    capability: str
    supports_json: bool
    supports_stream: bool
    default_temperature: float
    default_max_output_tokens: int
    default_timeout_seconds: int
    default_answer_behavior: str


CAPABILITY_POLICIES = {
    AICapability.METADATA_EXTRACTION: CapabilityPolicy(
        capability=AICapability.METADATA_EXTRACTION,
        supports_json=True,
        supports_stream=False,
        default_temperature=0,
        default_max_output_tokens=2048,
        default_timeout_seconds=60,
        default_answer_behavior="structured_candidates",
    ),
    AICapability.LIBRARY_QA: CapabilityPolicy(
        capability=AICapability.LIBRARY_QA,
        supports_json=False,
        supports_stream=True,
        default_temperature=0.2,
        default_max_output_tokens=2048,
        default_timeout_seconds=60,
        default_answer_behavior="evidence_only",
    ),
    AICapability.FIELD_ENRICHMENT_OPTIONAL: CapabilityPolicy(
        capability=AICapability.FIELD_ENRICHMENT_OPTIONAL,
        supports_json=True,
        supports_stream=False,
        default_temperature=0,
        default_max_output_tokens=1536,
        default_timeout_seconds=45,
        default_answer_behavior="candidate_judge_only",
    ),
}


@dataclass(frozen=True, slots=True)
class AIRuntimeProfile:
    key: str
    capability: str
    provider: str
    model: str
    enabled: bool
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    max_input_chars: int
    endpoint_alias: str = "default"
    credential_alias: str = "default"
    retrieval_profile: str = "stable"
    answer_behavior: str = "evidence_only"
    fallback_profile_key: str = ""
    reasoning: dict[str, Any] = field(default_factory=dict)

    def safe_dict(self) -> dict:
        return asdict(self)


class AIRuntimeProfileError(ValueError):
    pass


def _provider_from_settings() -> str:
    provider = str(getattr(settings, "AI_PROVIDER", "none") or "none").strip().casefold()
    return provider if provider in SUPPORTED_AI_PROVIDERS else "none"


def _environment_profiles() -> dict:
    provider = _provider_from_settings()
    metadata_model = str(getattr(settings, "AI_METADATA_MODEL", "") or "").strip()
    library_model = str(getattr(settings, "AI_LIBRARY_MODEL", "") or "").strip()
    classifier_model = str(getattr(settings, "AI_CLASSIFIER_MODEL", "") or "").strip()
    timeout = int(getattr(settings, "AI_TIMEOUT", 60))
    max_input = int(getattr(settings, "AI_MAX_INPUT_CHARS", 16000))
    profiles = [
        AIRuntimeProfile(
            key="metadata-default",
            capability=AICapability.METADATA_EXTRACTION,
            provider=provider,
            model=metadata_model,
            enabled=provider != "none" and bool(metadata_model),
            temperature=0,
            max_output_tokens=2048,
            timeout_seconds=timeout,
            max_input_chars=max_input,
            answer_behavior="structured_candidates",
        ),
        AIRuntimeProfile(
            key="library-default",
            capability=AICapability.LIBRARY_QA,
            provider=provider,
            model=library_model,
            enabled=provider != "none" and bool(library_model),
            temperature=float(getattr(settings, "AI_LIBRARY_TEMPERATURE", 0.2)),
            max_output_tokens=int(getattr(settings, "AI_LIBRARY_MAX_OUTPUT_TOKENS", 2048)),
            timeout_seconds=timeout,
            max_input_chars=max_input,
            retrieval_profile="stable",
            answer_behavior="evidence_only",
        ),
        AIRuntimeProfile(
            key="field-enrichment-default",
            capability=AICapability.FIELD_ENRICHMENT_OPTIONAL,
            provider=provider,
            model=classifier_model,
            enabled=False,
            temperature=0,
            max_output_tokens=1536,
            timeout_seconds=min(timeout, 60),
            max_input_chars=max_input,
            answer_behavior="candidate_judge_only",
        ),
    ]
    return {
        "version": PROFILE_DOCUMENT_VERSION,
        "active": {
            AICapability.METADATA_EXTRACTION: "metadata-default",
            AICapability.LIBRARY_QA: "library-default",
            AICapability.FIELD_ENRICHMENT_OPTIONAL: "field-enrichment-default",
        },
        "profiles": [profile.safe_dict() for profile in profiles],
        "source": "environment-default",
    }


def _stored_profile_document() -> dict | None:
    try:
        from catalog.models import SiteSetting

        value = SiteSetting.objects.filter(key=PROFILE_SETTING_KEY).values_list("value", flat=True).first()
    except DatabaseError:
        return None
    except RuntimeError as exc:
        # pytest blocks unmarked database access. Config-only unit tests should
        # still exercise the environment fallback without requiring DB setup.
        if "Database access not allowed" in str(exc):
            return None
        raise
    return value if isinstance(value, dict) else None


def _bounded_reasoning(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    output = {}
    for key, item in list(value.items())[:12]:
        normalized_key = str(key).strip()[:80]
        if not normalized_key:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            output[normalized_key] = item
    return output


def validate_runtime_profile(value: dict) -> AIRuntimeProfile:
    if not isinstance(value, dict):
        raise AIRuntimeProfileError("AI runtime profile 必须是对象。")
    key = str(value.get("key") or "").strip().casefold()
    capability = str(value.get("capability") or "").strip().casefold()
    provider = str(value.get("provider") or "none").strip().casefold()
    model = str(value.get("model") or "").strip()
    endpoint_alias = str(value.get("endpoint_alias") or "default").strip().casefold()
    credential_alias = str(value.get("credential_alias") or "default").strip().casefold()
    fallback = str(value.get("fallback_profile_key") or "").strip().casefold()
    if not PROFILE_KEY_RE.fullmatch(key):
        raise AIRuntimeProfileError("Profile key 必须以字母开头，只包含小写字母、数字、下划线或短横线。")
    if capability not in AICapability.VALUES:
        raise AIRuntimeProfileError("不支持的 AI capability。")
    if provider not in SUPPORTED_AI_PROVIDERS:
        raise AIRuntimeProfileError("不支持的 AI provider。")
    if not ALIAS_RE.fullmatch(endpoint_alias) or not ALIAS_RE.fullmatch(credential_alias):
        raise AIRuntimeProfileError("Endpoint/Credential alias 格式无效。")
    enabled = bool(value.get("enabled", False))
    if enabled and (provider == "none" or not model):
        raise AIRuntimeProfileError("启用的 profile 必须配置 provider 和 model。")
    if len(model) > 300:
        raise AIRuntimeProfileError("模型标识不能超过 300 个字符。")
    try:
        temperature = float(value.get("temperature", CAPABILITY_POLICIES[capability].default_temperature))
        max_output_tokens = int(value.get("max_output_tokens", CAPABILITY_POLICIES[capability].default_max_output_tokens))
        timeout_seconds = int(value.get("timeout_seconds", CAPABILITY_POLICIES[capability].default_timeout_seconds))
        max_input_chars = int(value.get("max_input_chars", getattr(settings, "AI_MAX_INPUT_CHARS", 16000)))
    except (TypeError, ValueError) as exc:
        raise AIRuntimeProfileError("AI profile 数值参数格式无效。") from exc
    if not 0 <= temperature <= 2:
        raise AIRuntimeProfileError("temperature 必须在 0 到 2 之间。")
    if not 128 <= max_output_tokens <= 8192:
        raise AIRuntimeProfileError("max output tokens 必须在 128 到 8192 之间。")
    if not 3 <= timeout_seconds <= 600:
        raise AIRuntimeProfileError("timeout 必须在 3 到 600 秒之间。")
    if not 1000 <= max_input_chars <= 100000:
        raise AIRuntimeProfileError("max input chars 必须在 1000 到 100000 之间。")
    retrieval_profile = str(value.get("retrieval_profile") or "stable").strip().casefold()
    if capability == AICapability.LIBRARY_QA and retrieval_profile not in LIBRARY_RETRIEVAL_PROFILES:
        raise AIRuntimeProfileError("Library QA retrieval profile 必须是 stable 或 experimental_v2。")
    if capability != AICapability.LIBRARY_QA:
        retrieval_profile = "stable"
    answer_behavior = str(
        value.get("answer_behavior")
        or CAPABILITY_POLICIES[capability].default_answer_behavior
    ).strip().casefold()
    allowed_behaviors = {
        AICapability.METADATA_EXTRACTION: {"structured_candidates"},
        AICapability.LIBRARY_QA: {"evidence_only"},
        AICapability.FIELD_ENRICHMENT_OPTIONAL: {"candidate_judge_only"},
    }
    if answer_behavior not in allowed_behaviors[capability]:
        raise AIRuntimeProfileError("该 capability 不允许此 answer behavior。")
    return AIRuntimeProfile(
        key=key,
        capability=capability,
        provider=provider,
        model=model,
        enabled=enabled,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
        max_input_chars=max_input_chars,
        endpoint_alias=endpoint_alias,
        credential_alias=credential_alias,
        retrieval_profile=retrieval_profile,
        answer_behavior=answer_behavior,
        fallback_profile_key=fallback,
        reasoning=_bounded_reasoning(value.get("reasoning")),
    )


def validate_profile_document(value: dict) -> dict:
    if not isinstance(value, dict):
        raise AIRuntimeProfileError("AI runtime 配置必须是对象。")
    rows = value.get("profiles")
    active = value.get("active")
    if not isinstance(rows, list) or not isinstance(active, dict):
        raise AIRuntimeProfileError("AI runtime 配置缺少 profiles 或 active。")
    if not 1 <= len(rows) <= 24:
        raise AIRuntimeProfileError("AI runtime profiles 数量必须在 1 到 24 之间。")
    profiles = [validate_runtime_profile(row) for row in rows]
    by_key = {profile.key: profile for profile in profiles}
    if len(by_key) != len(profiles):
        raise AIRuntimeProfileError("AI runtime profile key 不能重复。")
    normalized_active = {}
    for capability in AICapability.VALUES:
        key = str(active.get(capability) or "").strip().casefold()
        profile = by_key.get(key)
        if profile is None or profile.capability != capability:
            raise AIRuntimeProfileError(f"{capability} 的 active profile 无效。")
        normalized_active[capability] = key
    for profile in profiles:
        fallback = profile.fallback_profile_key
        if not fallback:
            continue
        target = by_key.get(fallback)
        if target is None or target.capability != profile.capability or target.key == profile.key:
            raise AIRuntimeProfileError("fallback profile 必须存在、同 capability 且不能指向自身。")
        if target.fallback_profile_key:
            raise AIRuntimeProfileError("第一版 fallback 只允许一层。")
    return {
        "version": PROFILE_DOCUMENT_VERSION,
        "active": normalized_active,
        "profiles": [profile.safe_dict() for profile in profiles],
        "source": "database",
    }


def current_profile_document() -> dict:
    stored = _stored_profile_document()
    if stored is None:
        return _environment_profiles()
    try:
        return validate_profile_document(stored)
    except AIRuntimeProfileError:
        # Invalid DB settings must fail at capability resolution rather than
        # silently substituting another model.
        return {**stored, "source": "database-invalid"}


def safe_profile_document(value: dict | None = None) -> dict:
    document = value or current_profile_document()
    return {
        "version": document.get("version", ""),
        "active": dict(document.get("active") or {}),
        "profiles": [dict(row) for row in document.get("profiles") or []],
        "source": document.get("source", ""),
        "secret_values_exposed": False,
    }


def runtime_profile(capability: str, profile_key: str | None = None) -> AIRuntimeProfile:
    capability = str(capability or "").strip().casefold()
    if capability not in AICapability.VALUES:
        raise AIRuntimeProfileError("不支持的 AI capability。")
    document = current_profile_document()
    try:
        validated = validate_profile_document(document)
    except AIRuntimeProfileError as exc:
        raise AIRuntimeProfileError(f"AI runtime profile 配置无效：{exc}") from exc
    key = str(profile_key or validated["active"][capability]).strip().casefold()
    rows = {row["key"]: row for row in validated["profiles"]}
    row = rows.get(key)
    if row is None or row["capability"] != capability:
        raise AIRuntimeProfileError("指定的 AI runtime profile 不存在或 capability 不匹配。")
    return validate_runtime_profile(row)


def resolve_endpoint(alias: str) -> str:
    alias = str(alias or "default").strip().casefold()
    if alias == "default":
        return str(getattr(settings, "AI_BASE_URL", "") or "").strip().rstrip("/")
    key = "AI_ENDPOINT_" + alias.upper().replace("-", "_")
    return str(os.getenv(key, "") or "").strip().rstrip("/")


def resolve_credential(alias: str) -> str:
    alias = str(alias or "default").strip().casefold()
    if alias == "default":
        return str(getattr(settings, "AI_API_KEY", "") or "")
    key = "AI_CREDENTIAL_" + alias.upper().replace("-", "_")
    return str(os.getenv(key, "") or "")


def profile_environment_status(profile: AIRuntimeProfile) -> dict:
    endpoint = resolve_endpoint(profile.endpoint_alias)
    credential = resolve_credential(profile.credential_alias)
    return {
        "endpoint_configured": bool(endpoint),
        "credential_configured": bool(credential) or profile.provider in {"none", "ollama"},
        "restart_may_be_required": True,
    }
