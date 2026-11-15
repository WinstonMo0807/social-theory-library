"""Passive status of the model actually bound to the active viewpoint index."""
from django.conf import settings
from django.utils import timezone

from catalog.services.discovery_inference import DiscoveryInferenceError, inference_health
from catalog.services.discovery_projection import active_generation


def discovery_model_status():
    generation = active_generation()
    config = (generation.config_snapshot or {}) if generation else {}
    result = {
        "status": "unknown", "configured": bool(settings.DISCOVERY_INFERENCE_URL),
        "available": None, "checked_at": timezone.now(), "source": "discovery",
        "model": generation.model_repo_id if generation else "",
        "revision": generation.model_revision if generation else "",
        "dimensions": generation.dimensions if generation else None,
        "on_demand": bool(getattr(settings, "NAS_ON_DEMAND_ENABLED", False)),
    }
    try:
        # Reading maintenance must never signal demand, wait for startup or load
        # weights. An idle service remains unknown until a real request uses it.
        health = inference_health(allow_unready=True)
    except DiscoveryInferenceError as exc:
        result.update(
            error_code=exc.code,
            reason=("本次未连通按需推理服务；可能处于休眠或连接异常，尚不能确认模型可用。"
                    if result["on_demand"] else "本地推理服务暂不可连接。"),
        )
        if not result["on_demand"] or exc.code != "service_unavailable":
            result.update(status="unavailable", available=False)
        return result
    models = health.get("models")
    if not isinstance(models, dict) or any(not isinstance(models.get(role), dict) for role in ("embedding", "reranker")):
        return {**result, "status": "unavailable", "available": False,
                "error_code": "invalid_response", "reason": "模型服务返回的状态不完整。"}
    result["health"] = {
        "manifest_ready": health.get("manifest_ready") is True,
        "backend": str(health.get("backend") or "")[:100],
        "threads": health.get("threads"), "batch_size": health.get("batch_size"),
        "models": {role: {key: model.get(key) for key in (
            "model", "revision", "artifact_id", "loaded", "inference_completed")}
            for role, model in models.items() if role in {"embedding", "reranker"}},
    }
    if health.get("manifest_ready") is not True:
        result.update(status="unavailable", available=False, reason="本地模型文件或清单未就绪。")
    elif generation is None:
        result.update(status="not_ready", reason="模型文件已准备，尚无活动观点索引可核对模型身份。")
    elif any(not config.get(role + "_artifact") or
             models[role].get("artifact_id") != config[role + "_artifact"]
             for role in ("embedding", "reranker")):
        result.update(status="unavailable", available=False, error_code="artifact_mismatch",
                      reason="模型制品与活动观点索引不一致，需核对当前部署。")
    elif models["embedding"].get("dimensions") != generation.dimensions:
        result.update(status="unavailable", available=False, error_code="dimensions_mismatch",
                      reason="向量维度与活动观点索引不一致。")
    elif models["embedding"].get("inference_completed") is True:
        result.update(status="available", available=True,
                      reason="当前索引使用的编码模型已有本次服务启动后的推理记录；索引覆盖情况另列。")
    else:
        result.update(status="prepared", reason="模型文件和索引身份一致，尚无本次服务启动后的编码记录。")
    return result
