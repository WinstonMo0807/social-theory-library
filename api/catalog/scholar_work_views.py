"""Bounded book selection for scholar editing, over activated catalog snapshots."""
from uuid import UUID

from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanAccessBackOffice
from common.private_responses import PrivateAccountResponses
from catalog.models import ScholarProfile
from catalog.scholar_serializers import ScholarWorkSerializer
from catalog.services.public_scholars import _work_rows, selectable_works


class ScholarWorkSelectionPage(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = ScholarWorkSerializer(many=True)


class ScholarWorkSelectionView(PrivateAccountResponses, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[OpenApiParameter("kind", str, enum=["essential", "recommended"]),
        OpenApiParameter("q", str), OpenApiParameter("page", int), OpenApiParameter("ids", str)],
        responses=ScholarWorkSelectionPage)
    def get(self, request, scholar_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新打开选书窗口。")
        profile = get_object_or_404(ScholarProfile.objects.select_related("person"), pk=scholar_id)
        params = request.query_params
        if set(params) - {"kind", "q", "page", "ids"} or any(len(params.getlist(key)) != 1 for key in params):
            raise ValidationError("选书参数无效。")
        kind, query, page = params.get("kind", "essential"), params.get("q", "").strip(), params.get("page", "1")
        if kind not in {"essential", "recommended"} or len(query) > 200 or not page.isdecimal() or not 1 <= int(page) <= 100000:
            raise ValidationError("请选择有效的作品类型、题名和页码。")
        rows = selectable_works(profile, kind)
        size = 12
        if "ids" in params:
            raw = params["ids"].split(",") if params["ids"] else []
            if len(raw) > 100 or query or page != "1":
                raise ValidationError("已选作品最多核对 100 项，不能同时搜索或翻页。")
            try:
                ids = [UUID(value) for value in raw]
            except (ValueError, TypeError, AttributeError):
                raise ValidationError("作品标识无效。") from None
            rows = rows.filter(work_id__in=ids)
            size = 100
        if query:
            rows = rows.filter(Q(active_catalog_revision__snapshot__work__title__icontains=query)
                | Q(active_catalog_revision__snapshot__work__original_title__icontains=query))
        count, page = rows.count(), int(page)
        if page > max(1, (count + size - 1) // size):
            raise NotFound("选书页已变化，请返回第一页。")
        selected = list(rows[(page - 1) * size:page * size])
        return Response(ScholarWorkSelectionPage({"count": count, "page": page, "page_size": size,
            "results": _work_rows(selected, profile)}).data)
