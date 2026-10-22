"""Short-lived editor observations. Presence never locks or saves article content."""
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from redis.exceptions import RedisError
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from catalog.models import RecommendationIssue
from catalog.services.shared_curation import identifier
from common.capabilities import Capability, has_capability

TTL = 90


class PresenceUnavailable(APIException):
    status_code = 503
    default_detail = "协作状态暂时不可用，草稿保存与版本冲突保护不受影响。"


def observe(issue_id, actor, data):
    if not actor.is_active or not has_capability(actor, Capability.ACCESS_BACK_OFFICE):
        raise PermissionDenied("当前账户不能查看协作状态。")
    get_object_or_404(RecommendationIssue, pk=issue_id)
    session = str(identifier(data.get("session_id")))
    mode = data.get("mode")
    if mode not in {"editing", "viewing", "leave"}:
        raise ValidationError("协作状态无效。")
    if mode == "editing" and not has_capability(actor, Capability.EDIT_METADATA):
        raise PermissionDenied("当前账户不能报告编辑状态。")
    key, now = f"stl4:issue-presence:{issue_id}", timezone.now()
    token = str(uuid4())
    try:
        # One cache write per issue avoids lost concurrent observers. The lock
        # encloses only bounded cache operations, never database or provider IO.
        if not cache.add(key + ":lock", token, timeout=5):
            raise PresenceUnavailable("协作状态正在更新，请稍后重试。")
        try:
            rows = {k: v for k, v in (cache.get(key) or {}).items() if v["timestamp"] > now.timestamp() - TTL}
            own_key = f"{actor.pk}:{session}"
            if mode == "leave":
                rows.pop(own_key, None)
            else:
                if len(rows) >= 100 and own_key not in rows:
                    raise PresenceUnavailable("当前协作连接较多，稍后可重新读取；编辑和保存仍可继续。")
                rows[own_key] = {"user_id": str(actor.pk), "mode": mode, "timestamp": now.timestamp(), "last_seen": now.isoformat()}
            cache.set(key, rows, timeout=TTL)
        finally:
            if cache.get(key + ":lock") == token:
                cache.delete(key + ":lock")
    except (RedisError, OSError):
        raise PresenceUnavailable()
    users = {str(user.pk): user for user in get_user_model().objects.filter(pk__in={row["user_id"] for row in rows.values()}, is_active=True)}
    grouped = {}
    for row in rows.values():
        user = users.get(row["user_id"])
        if not user or not has_capability(user, Capability.ACCESS_BACK_OFFICE):
            continue
        state = row["mode"] if has_capability(user, Capability.EDIT_METADATA) else "viewing"
        previous = grouped.get(row["user_id"])
        grouped[row["user_id"]] = {"id": row["user_id"], "name": user.display_name or "未设置署名", "is_self": user.pk == actor.pk,
            "mode": "editing" if state == "editing" or previous and previous["mode"] == "editing" else "viewing",
            "last_seen": max(previous["last_seen"], row["last_seen"]) if previous else row["last_seen"]}
    shared = settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    return {"participants": sorted(grouped.values(), key=lambda row: (not row["is_self"], row["name"], row["id"])),
            "checked_at": now, "expires_after_seconds": TTL, "shared": shared,
            "notice": "显示最近90秒内实际连接状态；不代表内容已保存。" if shared else "当前只观察到本服务进程的连接；跨进程协作状态尚不可用。"}
