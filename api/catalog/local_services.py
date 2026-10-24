"""M26 projection over the existing runtimes, task queue and HealthCheckRun.

GET reads saved observations only. Explicit checks never submit library or reader
text, run generation, change models, or evaluate retrieval quality.
"""
from datetime import timedelta
from hashlib import sha256
import json
import time
from urllib.parse import urlsplit
import httpx

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, OuterRef, Subquery
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from accounts.models import User
from common.capabilities import Capability, has_capability, capability_snapshot
from catalog.models import HealthCheckRun, SiteSetting, ProviderCredentialSecret
from catalog.services.query_lexicon.mutations import acquire_entity_lock
from ingestion.models import AuditEvent, ProcessingJob


PREFIX = "local-services:"
LIFETIME = 600
GROUPS = (
    ("parse", "知识解析", "文档理解与结构化", ["文字识别", "段落切分", "实体识别"]),
    ("embedding", "文本嵌入", "向量化表示", ["观点检索", "相似度匹配"]),
    ("rerank", "重排", "检索结果优化", ["检索结果排序", "知识发现"]),
    ("generation", "生成", "配置的语言模型", ["摘要候选", "内容辅助", "页面编排"]),
    ("metadata", "外部元数据", "公开书目信息补充", ["作者信息", "参考文献", "书目信息"]),
)
STATUS_LABELS = {"untested": "未检查", "stale": "记录已过期", "changed": "配置已变化",
    "available": "可使用", "partial": "部分能力可用", "offline": "离线", "model_unloaded": "模型未加载",
    "not_configured": "未配置", "disabled": "未启用", "quota_exhausted": "访问受限", "checking": "检查中"}


class ServiceCheckConflict(APIException):
    status_code = 409
    default_detail = "配置已变化，请刷新服务状态后再检查。"


def _fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _origin(value):
    """Never show URL userinfo, query strings, paths or fragments."""
    try:
        parsed = urlsplit(str(value or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "未配置"
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        return f"{parsed.scheme}://{host}" + (f":{parsed.port}" if parsed.port else "")
    except ValueError:
        return "地址待核对"


def service_definitions():
    from ingestion.services.ocr_provider import ocr_runtime_config
    from ingestion.services.provider_gateway import provider_configuration_health
    from reading.runtime_profiles import runtime_profile_payload
    from common.ai_runtime import PROFILE_SETTING_KEY, resolve_endpoint
    from catalog.services.research_sources import REGISTRY_SETTING_KEY, resolve_source_endpoint

    ocr = ocr_runtime_config()
    document = runtime_profile_payload()
    profile_version = SiteSetting.objects.filter(key=PROFILE_SETTING_KEY).values_list("updated_at", flat=True).first()
    source_version = SiteSetting.objects.filter(key=REGISTRY_SETTING_KEY).values_list("updated_at", flat=True).first()
    credential_versions = list(ProviderCredentialSecret.objects.order_by("id").values_list("id", "updated_at"))
    definitions = []

    def add(key, group, name, scope, configured, enabled, config, details, permission, config_url, checkable=True):
        definitions.append({"id": key, "group": group, "name": name, "scope": scope,
            "configured": bool(configured), "enabled": bool(enabled), "configuration_version": _fingerprint(config),
            "details": [{"label": label, "value": str(value)} for label, value in details],
            "permission": permission, "config_url": config_url, "checkable": checkable})

    add("ocr", "parse", "PaddleOCR", "NAS 解析服务", ocr.get("nas_url"), ocr.get("mode") != "remote_only", ocr,
        [("服务地址", _origin(ocr.get("nas_url"))), ("解析策略", ocr.get("mode", "未配置")),
         ("检查范围", "读取服务就绪状态，不发送文档")], Capability.RETRY_JOBS, "/admin/processing/settings#ocr")
    if ocr.get("remote_url") or ocr.get("mode") == "remote_only":
        add("remote-ocr", "parse", ocr.get("remote_model") or "远程解析配置", "原配置的远程解析服务",
            bool(ocr.get("remote_url") and ocr.get("remote_model") and ocr.get("remote_key_configured")),
            ocr.get("mode") in {"nas_preferred", "remote_only"}, ocr,
            [("服务地址", _origin(ocr.get("remote_url"))), ("说明", "只展示原配置；本页不向远程解析发送文档")],
            Capability.MANAGE_AI, "/admin/processing/settings#ocr", False)
    discovery = {"enabled": bool(settings.DISCOVERY_ENABLED), "url": settings.DISCOVERY_INFERENCE_URL,
        "allowed_hosts": settings.DISCOVERY_INFERENCE_ALLOWED_HOSTS, "dimensions": settings.DISCOVERY_EMBEDDING_DIMENSIONS}
    for key, group, label in (("discovery-embedding", "embedding", "Discovery 文本嵌入"), ("discovery-reranker", "rerank", "Discovery 重排")):
        add(key, group, label, "本地推理服务", bool(discovery["url"]), discovery["enabled"], discovery,
            [("服务地址", _origin(discovery["url"])), ("检查范围", "读取模型清单与已有加载记录，不运行推理"),
             ("实际模型与版本", "以最近检查返回的模型身份为准"),
             ("配置方式", "随现有服务部署维护，本页不切换模型")], Capability.MANAGE_SEARCH_RUNTIME, "")

    active = set(document.get("active", {}).values())
    for profile in document.get("profiles", []):
        if profile["key"] not in active:
            continue
        environment = profile.get("environment", {})
        configured = bool(profile.get("provider") != "none" and profile.get("model") and environment.get("endpoint_configured"))
        add(f"profile-{profile['key']}", "generation", profile.get("model") or profile["key"], "配置的模型服务", configured,
            profile.get("enabled"), {"profile": profile, "updated_at": profile_version, "credentials": credential_versions,
                "endpoint": resolve_endpoint(profile["endpoint_alias"])},
            [("配置档", profile["key"]), ("能力", profile["capability"]), ("模型来源", profile["provider"]),
             ("最大输入字符", profile["max_input_chars"]), ("最大输出 Token", profile["max_output_tokens"]),
             ("检查范围", "仅检查模型服务连接；不执行生成")], Capability.MANAGE_AI, "/admin/processing/settings#ai")
    if not any(row["group"] == "generation" for row in definitions):
        add("generation-empty", "generation", "尚未选择生成配置", "配置的模型服务", False, False, {}, [],
            Capability.MANAGE_AI, "/admin/processing/settings#ai", False)

    for provider in provider_configuration_health():
        name = provider["provider"]
        add(f"metadata-{name}", "metadata", name, "外部书目服务",
            provider["configured"] and provider["allowed_host"], provider["enabled"], {"provider": provider,
                "updated_at": source_version, "endpoint": resolve_source_endpoint(name), "credentials": credential_versions},
            [("检查范围", "使用服务既有的公开书目样例；不发送馆藏或私人材料"),
             ("来源状态", provider["status"])], Capability.CONFIGURE_PROVIDERS, "/admin/processing?surface=research-sources",
            name in {"crossref", "openlibrary", "google_books", "nlb_singapore"})
    return definitions


def observation_payload(run):
    details = run.details if isinstance(run.details, dict) else {}
    state = details.get("service_status", "untested")
    return {"id": str(run.pk), "service_id": run.probe_key.removeprefix(PREFIX),
        "status": state if state in STATUS_LABELS else "untested", "checked_at": run.started_at,
        "completed_at": run.completed_at, "latency_ms": run.latency_ms,
        "detail": details.get("safe_detail", "检查结果暂不可读。"),
        "identity": safe_identity(details.get("identity")), "configuration_version": details.get("configuration_version", "")}


def safe_identity(raw):
    """Only bounded runtime labels, never raw health payloads or paths."""
    if not isinstance(raw,dict):return {}
    result={field:raw[field][:300] for field in ("model","revision","artifact_id","backend","runtime_version","device") if isinstance(raw.get(field),str)}
    result.update({field:raw[field] for field in ("loaded","inference_completed") if type(raw.get(field)) is bool})
    result.update({field:raw[field] for field in ("threads","batch_size") if type(raw.get(field)) is int and 1<=raw[field]<=4096})
    return result


def latest_observations(keys):
    latest = HealthCheckRun.objects.filter(probe_key=OuterRef("probe_key")).order_by("-started_at", "-id")
    return HealthCheckRun.objects.filter(probe_key__in=keys, pk=Subquery(latest.values("pk")[:1]))


def task_counts():
    """Only operational queue counts. Never enumerate reader sessions or prompts."""
    since = timezone.now() - timedelta(hours=24)
    counts = list(ProcessingJob.objects.filter(Q(status__in=["pending", "running"]) | Q(status="failed", finished_at__gte=since))
        .values("job_type", "status").annotate(total=Count("id")))
    def totals(kinds=None):
        return {label: sum(row["total"] for row in counts if row["status"] == status and (kinds is None or row["job_type"] in kinds))
            for label, status in (("waiting", "pending"), ("running", "running"), ("failed_24h", "failed"))}
    groups = {"parse": ["ocr", "text_extraction", "page_labels"], "embedding": ["discovery_index"],
        "generation": ["editorial_assistance"], "metadata": ["external_enrichment"]}
    return totals(), {key: totals(kinds) for key, kinds in groups.items()}


def services_snapshot(actor):
    definitions = service_definitions()
    total_tasks, grouped_tasks = task_counts()
    keys = [PREFIX + row["id"] for row in definitions]
    latest = {row.probe_key: row for row in latest_observations(keys)}
    now = timezone.now()
    admin_configuration = capability_snapshot(actor).access_level in {"admin", "superadmin"}
    rows = []
    for definition in definitions:
        row = {key: value for key, value in definition.items() if key not in {"permission", "checkable"}}
        run = latest.get(PREFIX + row["id"])
        observation = observation_payload(run) if run else None
        state = "disabled" if not row["enabled"] else "not_configured" if not row["configured"] else "untested"
        if row["enabled"] and row["configured"] and observation:
            state = "changed" if observation["configuration_version"] != row["configuration_version"] else (
                observation["status"] if 0 <= (now - run.started_at).total_seconds() <= LIFETIME else "stale")
        row.update(status=state, status_label=STATUS_LABELS[state], observation=observation,
            can_check=bool(definition["checkable"] and row["enabled"] and row["configured"] and has_capability(actor, definition["permission"])),
            can_configure=bool(row["config_url"]) and (admin_configuration if row["id"] in {"ocr", "remote-ocr"} else has_capability(actor, definition["permission"])),
            check_notice="尚无这项服务的独立检查器。" if not definition["checkable"] else "检查不会调用生成或检索。")
        rows.append(row)
    groups = []
    ranks = {"offline": 9, "quota_exhausted": 8, "model_unloaded": 7, "not_configured": 6, "partial": 5,
        "changed": 4, "stale": 3, "untested": 2, "disabled": 1, "available": 0}
    for key, label, subtitle, affected in GROUPS:
        children = [row for row in rows if row["group"] == key]
        enabled = [row for row in children if row["enabled"]]
        state = max((row["status"] for row in enabled), key=lambda value: ranks[value], default="disabled")
        groups.append({"id": key, "label": label, "subtitle": subtitle, "affected_features": affected,
            "status": state, "status_label": STATUS_LABELS[state], "services": children,
            "tasks": grouped_tasks.get(key), "task_notice": "仅统计对应的后台处理任务。" if key in grouped_tasks else "重排随检索执行，没有独立的处理队列。"})
    history = [observation_payload(run) for run in HealthCheckRun.objects.filter(probe_key__startswith=PREFIX).order_by("-started_at", "-id")[:40]]
    return {"generated_at": now, "last_checked_at": max((run.started_at for run in latest.values()), default=None),
        "observation_lifetime_seconds": LIFETIME, "groups": groups, "history": history,
        "summary": {"capabilities": len(groups), "services": len(rows),
            "available": sum(row["status"] == "available" for row in rows),
            "limited": sum(row["status"] in {"partial", "model_unloaded", "quota_exhausted"} for row in rows),
            "unavailable": sum(row["status"] in {"offline", "not_configured"} for row in rows), **total_tasks},
        "notice": "状态来自已保存的检查记录。连接或模型加载记录不能代替效果验收；现有远端 Provider 不会由此页面自动用于馆藏或私人材料。"}


def _check(definition):
    """Explicit bounded checks; return only allowlisted operational metadata."""
    key = definition["id"]
    if key.startswith("discovery-"):
        from catalog.services.discovery_inference import inference_health, DiscoveryInferenceError
        try:
            health = inference_health(allow_unready=True)
        except DiscoveryInferenceError:
            return "offline", "本地推理服务未返回有效状态，请核对服务启动与允许的地址。", {}
        role = "embedding" if key == "discovery-embedding" else "reranker"
        models = health.get("models")
        if not isinstance(models, dict) or not isinstance(models.get(role, {}), dict):
            return "offline", "本地服务返回的模型状态格式无效，请核对服务版本。", {}
        raw = models.get(role, {})
        identity = {field: str(raw[field])[:300] for field in ("model", "revision", "artifact_id") if isinstance(raw.get(field), str)}
        identity.update(loaded=raw.get("loaded") is True, inference_completed=raw.get("inference_completed") is True)
        identity.update(safe_identity({field:health.get(field) for field in ("backend","runtime_version","threads","batch_size")}))
        if identity.get("backend")=="onnxruntime-cpu":identity["device"]="CPU"
        if health.get("manifest_ready") is not True or not identity.get("artifact_id"):
            return "model_unloaded", "模型文件或清单未就绪，请核对本地模型部署。", identity
        if identity["inference_completed"]:
            return "available", "服务报告本次启动后已有该模型的推理记录；本次只读取状态，检索质量仍待验收。", identity
        return ("partial" if identity["loaded"] else "model_unloaded"), "模型清单已准备，尚无本次启动后的推理记录。本页不会为检查而加载模型。", identity
    if key.startswith("profile-"):
        from reading.runtime_profiles import test_runtime_profile
        result = test_runtime_profile(key.removeprefix("profile-"))
        return ("partial", "模型服务可连接，所选模型的加载与生成效果仍待验证。", {}) if result.get("available") else (
            "offline", "模型服务当前不可连接，请核对已保存的服务配置。", {})
    from catalog.services.system_health import HEALTH_CHECKS
    probe_key = "ocr" if key == "ocr" else "metadata." + key.removeprefix("metadata-")
    result = HEALTH_CHECKS.get(probe_key).runner()
    warnings = result.details.get("warnings", [])
    if any(isinstance(item, str) and "HTTP 429" in item for item in warnings):
        return "quota_exhausted", "外部来源返回访问频率限制；未提供可核实余额，请稍后重试或查看原来源限制。", {}
    if result.configured is False:
        return "not_configured", "服务当前配置不可用，请核对配置与允许的访问地址。", {}
    if result.reachable is False:
        return "offline", "服务检查未成功，请查看运行维护记录并核对服务状态。", {}
    if key == "ocr" and result.functional is not True:
        return "partial", "OCR 服务有响应，但尚未确认当前运行就绪。请在原解析设置中核对模型与缓存；历史任务不能替代当前状态。", {}
    if result.functional is False or result.productive is False:
        return "partial", "服务可连接，当前检查尚未确认完整产出。", {}
    return "available", "服务检查已返回成功记录；实际文档处理与结果质量仍需单独验收。", {}


def locked_service_actor(request):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("请重新读取当前维护账户后操作。")
    actor = User.objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if not actor or actor.token_version != request.user.token_version or not has_capability(actor, Capability.VIEW_SYSTEM_STATUS):
        raise PermissionDenied("账户会话或维护权限已变化。")
    return actor


def cancelled_check(identifier,actor):
    event=AuditEvent.objects.filter(action="local-service.cancelled",request_id=str(identifier)).first()
    if event and event.actor_id!=actor.pk:raise ServiceCheckConflict("此编号属于另一账户的服务检查。")
    return event


@transaction.atomic
def check_receipt(request,identifier,*,cancel=False):
    actor=locked_service_actor(request)
    acquire_entity_lock("local_service_request",identifier)
    if cancel and request.data!={"action":"cancel_pending"}:raise ValidationError("仅接受取消尚未执行的原服务检查。")
    run=HealthCheckRun.objects.filter(pk=identifier).first()
    if run:
        if run.initiated_by_id!=actor.pk or not run.probe_key.startswith(PREFIX):raise ServiceCheckConflict("原编号不属于当前账户的服务检查。")
        return {"request_id":str(identifier),"actor_id":str(actor.pk),"state":"applied","observation":observation_payload(run)}
    event=cancelled_check(identifier,actor)
    if not event:
        if not cancel:raise NotFound("尚未查到原检查结果，请求可能仍在途。查回不重复调用服务，可稍后查回或取消尚未执行的请求。")
        AuditEvent.objects.create(actor=actor,action="local-service.cancelled",object_type="LocalServiceCheck",object_id="",request_id=str(identifier),after={})
    return {"request_id":str(identifier),"actor_id":str(actor.pk),"state":"cancelled","observation":None}


@transaction.atomic
def check_service(request, values):
    actor=locked_service_actor(request)
    acquire_entity_lock("local_service_request", values["request_id"])
    if cancelled_check(values["request_id"],actor):raise ServiceCheckConflict("原服务检查已取消，迟到请求不会再次调用服务。")
    old = HealthCheckRun.objects.filter(pk=values["request_id"]).first()
    if old:
        if old.initiated_by_id != actor.pk or old.probe_key != PREFIX + values["service_id"]:
            raise ServiceCheckConflict("请求编号不属于本次服务检查。")
        if old.details.get("configuration_version") != values["configuration_version"]:
            raise ServiceCheckConflict("原检查对应其他配置版本。")
        return observation_payload(old)
    definition = next((row for row in service_definitions() if row["id"] == values["service_id"]), None)
    if not definition or not definition["checkable"]:
        raise ValidationError("这项服务没有可用的独立检查器。")
    if not has_capability(actor, definition["permission"]):
        raise PermissionDenied("当前账户不能检查这项服务。")
    if definition["configuration_version"] != values["configuration_version"]:
        raise ServiceCheckConflict()
    if not definition["configured"] or not definition["enabled"]:
        raise ValidationError("请先启用并配置该服务。")
    started_at, started = timezone.now(), time.perf_counter()
    # Known connectivity failures are recorded; programming errors are not hidden.
    from ingestion.services.ai_client import AIConfigurationError
    try:
        state, detail, identity = _check(definition)
    except (ValueError, OSError, TimeoutError, httpx.HTTPError, AIConfigurationError):
        state, detail, identity = "offline", "检查暂未完成，请核对服务配置后重试。", {}
    row = HealthCheckRun.objects.create(pk=values["request_id"], probe_key=PREFIX + definition["id"],
        capability=definition["group"], status="healthy" if state == "available" else "degraded" if state in {"partial", "model_unloaded"} else "failed",
        source="manual", configured=definition["configured"], reachable=state not in {"offline", "not_configured"},
        functional=None, productive=None, summary=detail,
        details={"service_status": state, "safe_detail": detail, "identity": identity,
            "configuration_version": definition["configuration_version"]}, started_at=started_at,
        completed_at=timezone.now(), latency_ms=max(0, round((time.perf_counter() - started) * 1000)), initiated_by=actor)
    return observation_payload(row)
