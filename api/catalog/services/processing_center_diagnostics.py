"""Persisted diagnostics for Processing Center 3.0.

The snapshot is deliberately read-only.  It explains projection lag, missing
executor capabilities and provider degradation from PostgreSQL-backed state
without running probes or treating Redis/Celery as business truth.
"""

from __future__ import annotations

from typing import Any

from django.db.models import F, Q
from django.utils import timezone

from catalog.models import (
    CanonicalObjectRevision,
    CapabilityDemand,
    CapabilityExecutor,
    DomainChangeEvent,
    HealthIncident,
    PromptRegistryEntry,
    ProjectionState,
    ResearchTaskProfile,
)
from common.ai_runtime import (
    current_profile_document,
    profile_environment_status,
    validate_runtime_profile,
)
from catalog.services.research.feedback import feedback_calibration_snapshot
from catalog.services.claim_benchmark import claim_benchmark_gold_summary


DIAGNOSTICS_VERSION = "processing-center-diagnostics-v1"
VISIBLE_LIMIT = 100

PROJECTION_LABELS = dict(ProjectionState.ProjectionType.choices)
PROJECTION_FEATURES = {
    ProjectionState.ProjectionType.QUERY_LEXICON: [
        "观点检索的查询扩展",
        "实体发现",
        "向书库提问的 Query Understanding",
    ],
    ProjectionState.ProjectionType.FULLTEXT: ["公开全文检索", "作品内检索"],
    ProjectionState.ProjectionType.SEMANTIC: ["观点检索", "语义检索", "向书库提问"],
    ProjectionState.ProjectionType.CLAIM_INDEX: [
        "观点检索的 Claim recall",
        "核心观点与批评候选",
    ],
    ProjectionState.ProjectionType.KNOWLEDGE_GRAPH: ["知识关系", "Theory 与 Debate 页面"],
    ProjectionState.ProjectionType.TIMELINE: ["理论发展脉络", "学者时间轴"],
    ProjectionState.ProjectionType.RECOMMENDATION: ["相关推荐", "下一步阅读"],
    ProjectionState.ProjectionType.READING_PATH_SUPPORT: ["Reading Path 策展依据"],
    ProjectionState.ProjectionType.PUBLIC: ["公网知识页面", "公开目录一致性"],
}
CAPABILITY_FEATURES = {
    "cpu_light": ["轻量后台任务", "投影协调"],
    "document_parse": ["PDF 结构解析", "Document Intelligence"],
    "ocr": ["选择性 OCR", "Evidence 原文质量"],
    "embedding": ["语义索引", "观点检索召回"],
    "rerank": ["观点检索排序", "研究证据排序"],
    "llm_small": ["Claim 派生", "研究候选"],
    "llm_large": ["复杂研究推理", "Debate 与 Reading Path 候选"],
    "web_research": ["Authority 与网页研究", "Entity Discovery"],
    "projection": ["知识投影更新", "公网一致性"],
}
AI_CAPABILITY_FEATURES = {
    "metadata_extraction": ["书目识别候选"],
    "library_qa": ["向书库提问的答案生成"],
    "field_enrichment_optional": ["字段研究候选"],
    "entity_reasoning": ["实体识别与消歧候选"],
    "claim_extraction": ["Derived Claim shadow processing"],
    "claim_attribution": ["Claim 归属判断"],
    "claim_stance": ["观点支持、相斥与限定判断"],
    "rerank": ["观点与研究证据排序"],
    "theory_reasoning": ["理论定位候选"],
    "knowledge_relation_reasoning": ["知识关系候选"],
    "debate_discovery": ["Debate 候选"],
    "reading_path_generation": ["Reading Path 候选"],
    "curation_reasoning": ["策展候选优先级"],
}
REFRESHABLE_TARGETS = {"work", "edition", "asset", "person", "knowledge_node", "topic"}
REFRESHABLE_PROJECTIONS = {
    ProjectionState.ProjectionType.QUERY_LEXICON,
    ProjectionState.ProjectionType.SEMANTIC,
}
PROJECTION_STATUS_RANK = {
    ProjectionState.Status.FAILED: 5,
    ProjectionState.Status.WAITING_FOR_CAPABILITY: 4,
    ProjectionState.Status.STALE: 3,
    ProjectionState.Status.UNKNOWN: 2,
    ProjectionState.Status.PROJECTING: 1,
    ProjectionState.Status.CURRENT: 0,
}
SAFE_HEALTH_RECOVERY_ACTIONS = {
    "rerun_probe",
    "recover_ingestion_queue",
    "recover_semantic_queue",
    "recover_query_lexicon",
    "recover_stale_research",
    "retry_failed_research",
}


def _projection_diagnostics() -> tuple[list[dict[str, Any]], dict[str, int]]:
    lagging_query = ProjectionState.objects.filter(
        Q(
            status__in=[
                ProjectionState.Status.STALE,
                ProjectionState.Status.WAITING_FOR_CAPABILITY,
                ProjectionState.Status.FAILED,
                ProjectionState.Status.UNKNOWN,
            ]
        )
        | Q(source_revision__gt=F("projected_revision"))
    )
    total = lagging_query.count()
    lagging = list(
        lagging_query.order_by("status", "projection_type", "updated_at")[:VISIBLE_LIMIT]
    )
    object_types = {row.object_type for row in lagging}
    object_ids = {row.object_id for row in lagging}
    revision_map = {
        (row.object_type, row.object_id): row
        for row in CanonicalObjectRevision.objects.filter(
            object_type__in=object_types,
            object_id__in=object_ids,
        )
    }
    event_map: dict[tuple[str, object], DomainChangeEvent] = {}
    for event in DomainChangeEvent.objects.filter(
        object_type__in=object_types,
        object_id__in=object_ids,
        processed_at__isnull=True,
    ).order_by("object_type", "object_id", "-canonical_revision"):
        event_map.setdefault((event.object_type, event.object_id), event)

    items: list[dict[str, Any]] = []
    for state in lagging:
        key = (state.object_type, state.object_id)
        canonical = revision_map.get(key)
        event = event_map.get(key)
        canonical_revision = canonical.current_revision if canonical else state.source_revision
        source_revision = max(state.source_revision, canonical_revision)
        revision_lag = max(0, source_revision - state.projected_revision)
        effective_status = (
            ProjectionState.Status.STALE
            if revision_lag and state.status == ProjectionState.Status.CURRENT
            else state.status
        )
        if state.last_error_message:
            reason = state.last_error_message
        elif state.stale_reason:
            reason = state.stale_reason
        elif event is not None:
            changed = "、".join(str(value) for value in (event.changed_fields or [])[:6])
            reason = (
                f"canonical revision {event.canonical_revision} 尚未完成依赖处理"
                + (f"，涉及 {changed}" if changed else "")
            )
        else:
            reason = (
                f"source revision {source_revision}，projected revision {state.projected_revision}"
                if revision_lag
                else "投影状态尚未被确认成最新"
            )

        safe_actions: list[dict[str, Any]] = []
        if (
            state.object_type in REFRESHABLE_TARGETS
            and state.projection_type in REFRESHABLE_PROJECTIONS
            and state.status != ProjectionState.Status.PROJECTING
        ):
            safe_actions.append(
                {
                    "key": "bounded_projection_refresh",
                    "label": "安全刷新相关投影",
                    "endpoint": (
                        f"/catalog/admin/projection-status/{state.object_type}/"
                        f"{state.object_id}/refresh/"
                    ),
                    "method": "POST",
                    "body": {"force": False},
                }
            )

        publication_blocking = bool(
            state.projection_type == ProjectionState.ProjectionType.PUBLIC
            and state.status == ProjectionState.Status.FAILED
        )
        items.append(
            {
                "id": f"projection:{state.id}",
                "kind": "projection",
                "status": effective_status,
                "severity": "critical" if publication_blocking else "warning",
                "title": (
                    f"{PROJECTION_LABELS.get(state.projection_type, state.projection_type)}投影落后"
                ),
                "reason": reason[:1000],
                "affected_features": PROJECTION_FEATURES.get(state.projection_type, ["下游投影"]),
                "publication_blocking": publication_blocking,
                "suggested_action": (
                    "先执行对象级安全刷新并观察 projected revision。"
                    if safe_actions
                    else "检查对应 projection executor 与最近一次失败记录。"
                ),
                "guidance": (
                    "当前没有与该投影类型匹配的对象级安全恢复动作，请保留 canonical 数据并由相应投影任务重试。"
                    if not safe_actions
                    else "刷新只处理当前对象，不会修改 canonical 内容或触发全库重建。"
                ),
                "safe_actions": safe_actions,
                "details": {
                    "object_type": state.object_type,
                    "object_id": str(state.object_id),
                    "projection_type": state.projection_type,
                    "source_revision": source_revision,
                    "projected_revision": state.projected_revision,
                    "revision_lag": revision_lag,
                    "task_owner_type": state.task_owner_type,
                    "task_owner_key": state.task_owner_key,
                    "attempts": state.attempts,
                    "lease_expires_at": state.lease_expires_at,
                    "last_projected_at": state.last_projected_at,
                    "last_error_code": state.last_error_code,
                    "unprocessed_domain_change": str(event.id) if event else "",
                },
            }
        )
    items.sort(
        key=lambda row: (
            -PROJECTION_STATUS_RANK.get(row["status"], 0),
            -int(row["publication_blocking"]),
            row["title"],
        )
    )
    return items, {
        "total": total,
        "visible": len(items),
        "failed": lagging_query.filter(status=ProjectionState.Status.FAILED).count(),
        "blocking": lagging_query.filter(
            status=ProjectionState.Status.FAILED,
            projection_type=ProjectionState.ProjectionType.PUBLIC,
        ).count(),
    }


def _capability_diagnostics() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    from common.task_runtime import executor_matches_demand

    now = timezone.now()
    all_executors = list(CapabilityExecutor.objects.order_by("kind", "executor_id"))
    executors = all_executors[:VISIBLE_LIMIT]
    live_executors = [
        executor
        for executor in all_executors
        if (
            executor.status == CapabilityExecutor.Status.ONLINE
            and executor.heartbeat_expires_at
            and executor.heartbeat_expires_at > now
        )
    ]
    executor_rows = []
    for executor in executors:
        fresh = bool(
            executor.status == CapabilityExecutor.Status.ONLINE
            and executor.heartbeat_expires_at
            and executor.heartbeat_expires_at > now
        )
        metadata = executor.metadata if isinstance(executor.metadata, dict) else {}
        executor_rows.append(
            {
                "id": str(executor.id),
                "executor_id": executor.executor_id,
                "display_name": executor.display_name,
                "kind": executor.kind,
                "status": "online" if fresh else executor.status,
                "heartbeat_fresh": fresh,
                "last_heartbeat_at": executor.last_heartbeat_at,
                "heartbeat_expires_at": executor.heartbeat_expires_at,
                "capabilities": list(executor.capabilities or []),
                "task_kinds": list(metadata.get("task_kinds") or []),
                "task_profiles": dict(metadata.get("task_profiles") or {}),
                "model_revisions": dict(executor.model_revisions or {}),
                "current_load": executor.current_load,
                "concurrency": executor.concurrency,
            }
        )

    unresolved = list(CapabilityDemand.objects.filter(
        state__in=[
            CapabilityDemand.State.WAITING_FOR_CAPABILITY,
            CapabilityDemand.State.READY,
        ]
    ).order_by("-priority", "created_at")[:5000])
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for demand in unresolved:
        if any(
            executor_matches_demand(executor, demand)
            for executor in live_executors
        ):
            continue
        payload = demand.payload if isinstance(demand.payload, dict) else {}
        task_kind = str(payload.get("task_kind") or "").strip()
        task_profile = str(
            payload.get("task_profile_key")
            or payload.get("profile_key")
            or ""
        ).strip()
        key = (str(demand.capability), task_kind, task_profile)
        group = grouped.setdefault(
            key,
            {
                "capability": key[0],
                "task_kind": task_kind,
                "task_profile": task_profile,
                "waiting_count": 0,
                "blocking_count": 0,
                "oldest_waiting_at": demand.created_at,
                "owner_samples": [],
            },
        )
        group["waiting_count"] += 1
        group["blocking_count"] += int(demand.publication_blocking)
        if demand.created_at < group["oldest_waiting_at"]:
            group["oldest_waiting_at"] = demand.created_at
        if len(group["owner_samples"]) < 5:
            group["owner_samples"].append(
                {
                    "owner_type": demand.owner_type,
                    "owner_key": demand.owner_key,
                    "state": demand.state,
                }
            )

    items = []
    for group in grouped.values():
        capability = str(group["capability"])
        waiting_count = int(group["waiting_count"])
        blocking = bool(group["blocking_count"])
        task_kind = str(group["task_kind"])
        task_profile = str(group["task_profile"])
        requirement = "/".join(
            value for value in (task_kind, task_profile) if value
        )
        items.append(
            {
                "id": f"capability:{capability}:{task_kind}:{task_profile}",
                "kind": "capability",
                "status": "waiting_for_capability",
                "severity": "critical" if blocking else "warning",
                "title": (
                    f"缺少 {capability} executor"
                    + (f"（{requirement}）" if requirement else "")
                ),
                "reason": (
                    f"{waiting_count} 项持久任务正在等待，但当前没有新鲜 heartbeat "
                    "同时匹配 capability、task kind 与 profile。"
                ),
                "affected_features": CAPABILITY_FEATURES.get(capability, ["后台派生任务"]),
                "publication_blocking": blocking,
                "suggested_action": "启动具备该 capability 的 executor，并确认 heartbeat 后等待任务自动转为可领取。",
                "guidance": (
                    "任务保留在 PostgreSQL 的 waiting_for_capability 状态。不要手工伪造完成状态；"
                    "远程 GPU 下线时，非阻断任务可以继续等待。"
                ),
                "safe_actions": [],
                "details": {
                    "capability": capability,
                    "task_kind": task_kind,
                    "task_profile": task_profile,
                    "waiting_count": waiting_count,
                    "oldest_waiting_at": group["oldest_waiting_at"],
                    "owner_samples": group["owner_samples"],
                    "live_executor_count": 0,
                },
            }
        )
    items.sort(key=lambda row: (-int(row["publication_blocking"]), row["title"]))
    executor_by_id = {str(row.id): row for row in executors}
    for executor_row in executor_rows:
        executor = executor_by_id.get(executor_row["id"])
        if executor is None:
            continue
        compatible = [
            demand
            for demand in unresolved
            if executor_matches_demand(executor, demand)
        ]
        executor_row["backlog"] = {
            "compatible_ready": sum(
                demand.state == CapabilityDemand.State.READY
                for demand in compatible
            ),
            "compatible_waiting": sum(
                demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
                for demand in compatible
            ),
            "claimed": CapabilityDemand.objects.filter(
                claimed_by=executor,
                state=CapabilityDemand.State.CLAIMED,
            ).count(),
        }
    return items, executor_rows, {
        "missing_capabilities": len(items),
        "waiting_demands": sum(int(row["details"]["waiting_count"]) for row in items),
        "live_executors": sum(bool(row["heartbeat_fresh"]) for row in executor_rows),
    }


def _provider_diagnostics() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    document = current_profile_document()
    profile_rows = [row for row in document.get("profiles") or [] if isinstance(row, dict)]
    by_key = {str(row.get("key") or ""): row for row in profile_rows}
    active = dict(document.get("active") or {})
    overview = []
    items = []

    if document.get("source") == "database-invalid":
        items.append(
            {
                "id": "provider:runtime-document-invalid",
                "kind": "provider",
                "status": "failed",
                "severity": "warning",
                "title": "AI Runtime 配置无效",
                "reason": "数据库中的 AI Runtime 文档未通过版本或字段校验。",
                "affected_features": ["所有已启用的 AI 派生任务"],
                "publication_blocking": False,
                "suggested_action": "由 Superadmin 在设置页修正 Provider、模型与 fallback 配置。",
                "guidance": "AI 派生能力保持降级，人工编辑和发布不应因此被阻断。",
                "safe_actions": [],
                "details": {"source": "database-invalid"},
            }
        )

    for capability, profile_key in active.items():
        row = by_key.get(str(profile_key))
        if row is None:
            overview.append(
                {
                    "capability": capability,
                    "profile": str(profile_key),
                    "provider": "",
                    "model": "",
                    "status": "invalid",
                    "fallback_available": False,
                }
            )
            items.append(
                {
                    "id": f"provider:{capability}:missing-profile",
                    "kind": "provider",
                    "status": "failed",
                    "severity": "warning",
                    "title": f"{capability} active profile 不存在",
                    "reason": f"active 配置指向 {profile_key}，但 profiles 中没有该记录。",
                    "affected_features": AI_CAPABILITY_FEATURES.get(capability, ["AI 派生任务"]),
                    "publication_blocking": False,
                    "suggested_action": "由 Superadmin 选择存在且同 capability 的 active profile。",
                    "guidance": "该 AI 能力保持降级，不自动改用未声明的模型。",
                    "safe_actions": [],
                    "details": {"capability": capability, "profile": str(profile_key)},
                }
            )
            continue
        try:
            profile = validate_runtime_profile(row)
            environment = profile_environment_status(profile)
        except Exception as exc:
            overview.append(
                {
                    "capability": capability,
                    "profile": str(profile_key),
                    "provider": str(row.get("provider") or ""),
                    "model": str(row.get("model") or ""),
                    "status": "invalid",
                    "fallback_available": False,
                }
            )
            items.append(
                {
                    "id": f"provider:{capability}:invalid-profile",
                    "kind": "provider",
                    "status": "failed",
                    "severity": "warning",
                    "title": f"{capability} profile 无法加载",
                    "reason": str(exc)[:1000],
                    "affected_features": AI_CAPABILITY_FEATURES.get(capability, ["AI 派生任务"]),
                    "publication_blocking": False,
                    "suggested_action": "由 Superadmin 修正该 profile 的受控字段。",
                    "guidance": "不要在诊断页填写 credential。凭据只通过服务器 alias 配置。",
                    "safe_actions": [],
                    "details": {"capability": capability, "profile": str(profile_key)},
                }
            )
            continue

        fallback_available = False
        fallback_key = profile.fallback_profile_key
        fallback_row = by_key.get(fallback_key) if fallback_key else None
        if fallback_row:
            try:
                fallback = validate_runtime_profile(fallback_row)
                fallback_environment = profile_environment_status(fallback)
                fallback_available = bool(
                    fallback.enabled
                    and fallback_environment["endpoint_configured"]
                    and fallback_environment["credential_configured"]
                )
            except Exception:
                fallback_available = False
        if not profile.enabled:
            runtime_status = "disabled"
        elif environment["endpoint_configured"] and environment["credential_configured"]:
            runtime_status = "configured_unverified"
        else:
            runtime_status = "degraded"
        overview.append(
            {
                "capability": capability,
                "profile": profile.key,
                "provider": profile.provider,
                "model": profile.model,
                "status": runtime_status,
                "fallback_profile": fallback_key,
                "fallback_available": fallback_available,
                "endpoint_configured": environment["endpoint_configured"],
                "credential_configured": environment["credential_configured"],
                "management_url": "/admin/settings#ai-runtime",
            }
        )
        if runtime_status != "degraded":
            continue
        missing = []
        if not environment["endpoint_configured"]:
            missing.append("endpoint alias")
        if not environment["credential_configured"]:
            missing.append("credential alias")
        items.append(
            {
                "id": f"provider:{capability}:{profile.key}",
                "kind": "provider",
                "status": "degraded",
                "severity": "warning",
                "title": f"{capability} Provider 配置不完整",
                "reason": f"已启用的 {profile.key} 缺少 {'、'.join(missing)}。",
                "affected_features": AI_CAPABILITY_FEATURES.get(capability, ["AI 派生任务"]),
                "publication_blocking": False,
                "suggested_action": (
                    "先验证 fallback，再由 Superadmin 修正服务器端 alias。"
                    if fallback_available
                    else "由 Superadmin 配置服务器端 endpoint 与 credential alias，随后执行显式健康测试。"
                ),
                "guidance": "配置值不会在 Processing Center 返回。AI 不可用时任务应等待或降级，人工发布继续可用。",
                "safe_actions": [],
                "details": {
                    "capability": capability,
                    "profile": profile.key,
                    "provider": profile.provider,
                    "model": profile.model,
                    "fallback_profile": fallback_key,
                    "fallback_available": fallback_available,
                },
            }
        )

    provider_incidents = HealthIncident.objects.filter(
        status__in=[HealthIncident.Status.OPEN, HealthIncident.Status.RECOVERING],
        capability="external_research",
    ).order_by("-severity", "-last_seen_at")[:VISIBLE_LIMIT]
    for incident in provider_incidents:
        safe_actions = [
            {
                "key": f"health_recovery:{action}",
                "label": "重新探测" if action == "rerun_probe" else str(action),
                "endpoint": "/catalog/admin/functional-health/",
                "method": "POST",
                "body": {
                    "action": "recover",
                    "incident_id": str(incident.id),
                    "recovery_action": action,
                    "idempotency_key": (
                        f"incident:{incident.id}:occurrence:{incident.occurrence_count}:{action}"
                    ),
                },
            }
            for action in (incident.safe_recovery_actions or [])
            if action in SAFE_HEALTH_RECOVERY_ACTIONS
        ]
        items.append(
            {
                "id": f"provider-incident:{incident.id}",
                "kind": "provider",
                "status": incident.status,
                "severity": incident.severity,
                "title": f"{incident.probe_key} Provider 降级",
                "reason": incident.error_message or incident.error_code or "最近一次 Provider 探测未通过。",
                "affected_features": list(incident.affected_features or ["外部研究候选"]),
                "publication_blocking": False,
                "suggested_action": (
                    "使用允许清单中的恢复动作后观察下一次持久化探测。"
                    if safe_actions
                    else "保留本地与其他 Provider 的降级路径，并检查来源服务状态。"
                ),
                "guidance": incident.manual_guidance or "Provider 失败不会把 SearXNG snippet 提升为正式 Evidence，也不会阻断发布。",
                "safe_actions": safe_actions,
                "details": {
                    "incident_id": str(incident.id),
                    "probe_key": incident.probe_key,
                    "error_code": incident.error_code,
                    "last_seen_at": incident.last_seen_at,
                    "occurrence_count": incident.occurrence_count,
                },
            }
        )

    items.sort(key=lambda row: (-int(row["severity"] == "critical"), row["title"]))
    overview.sort(key=lambda row: (row["status"] not in {"degraded", "invalid"}, row["capability"]))
    return items, overview, {
        "degraded": len(items),
        "enabled_profiles": sum(row["status"] != "disabled" for row in overview),
        "configured_unverified": sum(row["status"] == "configured_unverified" for row in overview),
    }


def processing_center_diagnostics() -> dict[str, Any]:
    projections, projection_summary = _projection_diagnostics()
    capabilities, executors, capability_summary = _capability_diagnostics()
    providers, provider_profiles, provider_summary = _provider_diagnostics()
    from catalog.services.research_sources import research_source_registry_payload

    research_sources = research_source_registry_payload()
    feedback_calibration = feedback_calibration_snapshot()[:VISIBLE_LIMIT]
    claim_benchmark = claim_benchmark_gold_summary()
    prompt_rows = list(
        PromptRegistryEntry.objects.filter(
            status=PromptRegistryEntry.Status.ACTIVE,
        )
        .order_by("key")
        .values(
            "id",
            "key",
            "version",
            "capability",
            "task_profile_key",
            "content_hash",
            "schema_hash",
            "activated_at",
        )[:VISIBLE_LIMIT]
    )
    active_prompt_keys = {str(row["key"]) for row in prompt_rows}
    expected_prompt_keys = set(
        ResearchTaskProfile.objects.filter(is_active=True).values_list(
            "prompt_key",
            flat=True,
        )
    )
    blocking_capabilities = sum(bool(row["publication_blocking"]) for row in capabilities)
    impact_rows = [
        {
            "id": row["id"],
            "title": row["title"],
            "reason": row["reason"],
            "affected_features": row["affected_features"],
            "publication_blocking": row["publication_blocking"],
            "severity": row["severity"],
        }
        for row in [*projections, *capabilities, *providers]
    ]
    impact_rows.sort(
        key=lambda row: (
            -int(row["publication_blocking"]),
            -int(row["severity"] == "critical"),
            row["title"],
        )
    )
    return {
        "version": DIAGNOSTICS_VERSION,
        "generated_at": timezone.now(),
        "page_load_performs_live_probes": False,
        "summary": {
            "issue_count": projection_summary["total"] + len(capabilities) + len(providers),
            "blocking_count": projection_summary["blocking"] + blocking_capabilities,
            "stale_projection_count": projection_summary["total"],
            "missing_capability_count": len(capabilities),
            "provider_degradation_count": len(providers),
            "research_source_degradation_count": research_sources["summary"]["degraded"],
            "claim_gold_query_count": claim_benchmark["gold_query_count"],
            "claim_benchmark_ready": claim_benchmark["benchmark_ready"],
        },
        "functional_impacts": impact_rows[:8],
        "sections": [
            {
                "key": "projections",
                "label": "投影新鲜度",
                "description": "比较 canonical source revision 与 projected revision。",
                "items": projections,
                "summary": projection_summary,
            },
            {
                "key": "capabilities",
                "label": "执行能力",
                "description": "识别没有新鲜 executor heartbeat 的持久任务。",
                "items": capabilities,
                "summary": capability_summary,
            },
            {
                "key": "providers",
                "label": "Provider 降级",
                "description": "读取脱敏 AI Runtime 配置与已持久化 Provider incident。",
                "items": providers,
                "summary": provider_summary,
            },
        ],
        "executors": executors,
        "provider_profiles": provider_profiles,
        "research_sources": research_sources,
        "prompt_registry": {
            "active": [
                {
                    **row,
                    "id": str(row["id"]),
                }
                for row in prompt_rows
            ],
            "draft_count": PromptRegistryEntry.objects.filter(
                status=PromptRegistryEntry.Status.DRAFT,
            ).count(),
            "retired_count": PromptRegistryEntry.objects.filter(
                status=PromptRegistryEntry.Status.RETIRED,
            ).count(),
            "missing_active_for_task_profiles": sorted(
                expected_prompt_keys - active_prompt_keys
            ),
            "management_endpoint": "/api/catalog/admin/prompt-registry/",
        },
        "feedback_calibration": feedback_calibration,
        "claim_benchmark": claim_benchmark,
    }
