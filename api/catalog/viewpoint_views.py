from __future__ import annotations

from uuid import UUID

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.concurrency import capacity_slot

from .services.semantic_search import viewer_access_statuses
from .services.viewpoint_search import ViewpointSearchError, search_viewpoints_v3


def _query_values(request, name: str) -> list[str]:
    values: list[str] = []
    for raw_value in request.query_params.getlist(name):
        values.extend(part.strip() for part in raw_value.split(","))
    return [value for value in values if value]


def _public_filters(request) -> dict:
    requested_work_ids: list[str] = []
    for value in _query_values(request, "work") or _query_values(request, "work_id"):
        try:
            requested_work_ids.append(str(UUID(value)))
        except (TypeError, ValueError, AttributeError):
            continue
    authenticated = bool(request.user.is_authenticated)
    staff = bool(
        authenticated
        and (
            getattr(request.user, "is_staff", False)
            or getattr(request.user, "role", "") in {"admin", "editor", "reviewer"}
        )
    )
    return {
        "document_types": _query_values(request, "document_type"),
        "languages": _query_values(request, "language"),
        "authors": _query_values(request, "author") or _query_values(request, "scholar"),
        "years": _query_values(request, "year"),
        "theories": _query_values(request, "theory"),
        "topics": _query_values(request, "topic"),
        "concepts": _query_values(request, "concept") or _query_values(request, "tag"),
        "access": _query_values(request, "access"),
        "work_ids": requested_work_ids,
        "_allowed_access_statuses": viewer_access_statuses(
            authenticated=authenticated,
            staff=staff,
        ),
    }


class ViewpointSearchView(APIView):
    """Public EvidenceSpan-backed viewpoint retrieval with Claim shadowing."""

    permission_classes = [AllowAny]

    def get_throttles(self):
        self.throttle_scope = (
            "semantic_search_user"
            if self.request.user.is_authenticated
            else "semantic_search_anon"
        )
        return super().get_throttles()

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response({"q": ["观点检索至少需要两个字符。"]}, status=400)
        if len(query) > 1200:
            return Response({"q": ["观点检索内容不能超过 1200 个字符。"]}, status=400)
        try:
            limit = min(80, max(1, int(request.query_params.get("limit", "40"))))
        except ValueError:
            limit = 40
        try:
            max_per_work = int(
                request.query_params.get(
                    "max_per_work",
                    str(settings.SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK),
                )
            )
        except ValueError:
            max_per_work = settings.SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK
        sort = request.query_params.get("sort", "relevance")
        if sort not in {"relevance", "newest", "year"}:
            sort = "relevance"
        show_shadow = bool(
            request.user.is_authenticated
            and request.user.is_staff
            and request.query_params.get("debug") == "1"
        )

        with capacity_slot(
            "semantic-search",
            limit=settings.SEMANTIC_SEARCH_MAX_CONCURRENT,
            timeout=settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS + 10,
        ) as acquired:
            if not acquired:
                response = Response(
                    {"detail": "观点检索正在处理其他请求，请稍后重试。", "retry_after": 3},
                    status=429,
                )
                response["Retry-After"] = "3"
                return response
            try:
                result = search_viewpoints_v3(
                    query,
                    filters=_public_filters(request),
                    limit=limit,
                    max_per_work=max(0, min(max_per_work, 20)),
                    sort=sort,
                    debug=show_shadow,
                )
            except ViewpointSearchError as exc:
                return Response({"q": [str(exc)]}, status=400)

        baseline = result.get("baseline") or {}
        if not show_shadow:
            result.pop("shadow", None)
            result.pop("baseline", None)
        result["count"] = len(result["results"])
        result["work_count"] = len(
            {str(row.get("work", {}).get("id") or "") for row in result["results"]}
            - {""}
        )
        result["stance_counts"] = {
            stance: len(rows) for stance, rows in result["groups"].items()
        }
        result["engine"] = baseline.get("engine") or "unavailable"
        result["search_version"] = baseline.get("search_version") or "v2"
        result["fallback_used"] = bool(baseline.get("fallback_used"))
        result["fallback_reason"] = baseline.get("fallback_reason") or ""
        result["notice"] = (
            "当前限定下没有找到可核对的馆藏原文。"
            if not result["results"]
            else "结果按与输入命题的关系分组。每条均已验证到当前馆藏版本和 PDF 页。"
        )
        return Response(result)
