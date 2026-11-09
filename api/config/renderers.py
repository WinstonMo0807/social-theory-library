"""Stable JSON API errors, retaining legacy fields for existing clients."""
from collections.abc import Mapping
from rest_framework.renderers import JSONRenderer


def error_contract(data, status, request_id=None):
    legacy = dict(data) if isinstance(data, Mapping) else {"detail": data}
    nested = legacy.get("error") if isinstance(legacy.get("error"), Mapping) else {}
    detail = legacy.get("detail", nested.get("detail", "请求未能完成。"))
    message = legacy.get("message") or (detail if isinstance(detail, str) else "请检查所填字段。")
    code = legacy.get("code") or nested.get("code") or {
        400: "request.invalid", 401: "auth.required", 403: "auth.forbidden",
        404: "resource.not_found", 409: "request.conflict", 429: "request.throttled",
    }.get(status, "server.error" if status >= 500 else "request.failed")
    details = legacy.get("details") or (detail if isinstance(detail, Mapping) else {})
    payload = {**legacy, "code": code, "message": message, "field": legacy.get("field"),
               "severity": legacy.get("severity", "blocking"), "details": details}
    trace = request_id or nested.get("request_id")
    if trace:
        payload["trace_id"] = trace
        payload.setdefault("request_id", trace)
    return payload


class ContractJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        context = renderer_context or {}
        response = context.get("response")
        if response is not None and response.status_code >= 400:
            # Django renders DRF responses before outer response middleware
            # attaches headers; the request is the authoritative trace source.
            request_id = getattr(context.get("request"), "stl_request_id", "") or response.headers.get("X-Request-ID")
            data = error_contract(data, response.status_code, request_id)
            response.data = data
        return super().render(data, accepted_media_type, renderer_context)
