"""Private pre-release review notes over the existing immutable audit ledger."""
from functools import lru_cache
from hashlib import sha256
import json
import math
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qsl, urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiParameter
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.capabilities import Capability, has_capability
from common.permissions import IsLibraryAdmin
from ingestion.models import AuditEvent
from .editorial_read import AdminPrivateResponseMixin
from .editorial_issue_views import EditorialErrorMixin
from .services.editorial_issues import EditConflict

ACTION = "visual_review.save"
QUERY_KEYS = {"q", "page", "tab", "view", "status", "type", "section", "scope", "edition", "edition_id",
              "work", "work_id", "file_id", "task_id", "task_source", "selection", "item", "review_work", "review_file"}


@lru_cache(maxsize=1)
def atlas():
    return json.loads((Path(__file__).parent / "data/stl4_visual_atlas.json").read_text(encoding="utf-8"))


def local_path(value):
    decoded = value
    for _ in range(3):
        decoded = unquote(decoded)
    parsed = urlsplit(value)
    if (not value.startswith("/") or decoded.startswith("//") or "\\" in decoded or parsed.scheme or parsed.netloc
            or any(ord(char) < 32 for char in decoded) or any(part in {".", ".."} for part in decoded.split("/"))
            or any(char in decoded for char in "[]") or parsed.path.startswith(("/api/", "/admin/visual-review"))):
        raise ValidationError("请填写本站具体页面路径，不能使用接口、外部链接或尚未替换的对象编号。")
    if parsed.fragment and not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", parsed.fragment):
        raise ValidationError("请移除不适合存入批注的临时页面片段。")
    if any(key not in QUERY_KEYS for key, _ in parse_qsl(parsed.query)):
        raise ValidationError("此链接含不适合存入批注的参数，请移除登录凭据或其他临时参数后重试。")
    return parsed.path + ("?" + urlencode(parse_qsl(parsed.query)) if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")


class ReviewPoint(serializers.Serializer):
    x = serializers.FloatField(min_value=0, max_value=1)
    y = serializers.FloatField(min_value=0, max_value=1)

    def validate(self, value):
        if not all(math.isfinite(number) for number in value.values()):
            raise serializers.ValidationError("标记坐标无效。")
        return value


class ReviewStroke(serializers.Serializer):
    color = serializers.ChoiceField(choices=["#B44C3D", "#A17E42", "#282724"])
    points = ReviewPoint(many=True, min_length=1, max_length=1500)


class ReviewViewport(serializers.Serializer):
    width = serializers.IntegerField(min_value=240, max_value=3840)
    height = serializers.IntegerField(min_value=240, max_value=2160)
    scroll_x = serializers.IntegerField(min_value=0, max_value=1000000)
    scroll_y = serializers.IntegerField(min_value=0, max_value=1000000)


class VisualReviewSave(serializers.Serializer):
    request_id = serializers.UUIDField()
    review_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=64)
    atlas_id = serializers.CharField(max_length=48)
    path = serializers.CharField(max_length=2000)
    viewport = ReviewViewport()
    strokes = ReviewStroke(many=True, max_length=80)
    note = serializers.CharField(max_length=5000, allow_blank=True)
    status = serializers.ChoiceField(choices=["open", "resolved"])

    def validate_path(self, value):
        return local_path(value)

    def validate(self, value):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("批注参数不属于当前保存格式。")
        if value["atlas_id"] not in {row["id"] for row in atlas()}:
            raise serializers.ValidationError("请选择终稿中的有效视图。")
        if sum(len(stroke["points"]) for stroke in value["strokes"]) > 12000:
            raise serializers.ValidationError("本条绘图点数过多，请分成两条批注保存。")
        if not value["note"].strip() and not value["strokes"]:
            raise serializers.ValidationError("请先填写说明或画出需要调整的位置。")
        return value


class VisualReviewReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    next_url = serializers.CharField()
    review_id = serializers.UUIDField(allow_null=True)
    version = serializers.CharField()


def receipt(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id,
            "state": "cancelled" if row.after.get("cancelled") else "applied", "next_url": "/admin/visual-review",
            "review_id": row.object_id or None, "version": str(row.pk)}


def reviews(actor):
    return AuditEvent.objects.filter(actor=actor, action=ACTION).exclude(object_id="")


def require_review(request, *, lock=False):
    if not settings.STL_VISUAL_REVIEW_ENABLED or settings.PUBLIC_DEPLOYMENT_MODE:
        raise NotFound("当前环境未开放上线前视觉批注。")
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("请在当前管理账户中打开批注工作台。")
    users = get_user_model().objects
    actor = get_object_or_404(users.select_for_update() if lock else users, pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.MANAGE_USERS):
        raise PermissionDenied("当前会话不能读取上线前批注。")
    return actor


class VisualReviewView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(parameters=[OpenApiParameter("page", type=int)], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        actor = require_review(request)
        page = serializers.IntegerField(min_value=1, max_value=100000).run_validation(request.query_params.get("page", 1))
        rows = reviews(actor)
        latest = reviews(actor).filter(object_id=OuterRef("object_id")).order_by("-created_at", "-pk").values("pk")[:1]
        rows = rows.filter(pk=Subquery(latest)).order_by("-created_at", "-pk")
        count = rows.count()
        return Response({"owner_id": str(actor.pk), "atlas": atlas(), "count": count, "page": page, "page_size": 20,
            "results": [{**row.after["payload"], "version": str(row.pk), "saved_at": row.created_at} for row in rows[(page-1)*20:page*20]],
            "reference_available": Path(settings.STL_VISUAL_ATLAS_PATH).is_file()})

    @extend_schema(request=VisualReviewSave, responses={200: VisualReviewReceipt, 201: VisualReviewReceipt})
    @transaction.atomic
    def post(self, request):
        actor = require_review(request, lock=True)
        data = VisualReviewSave(data=request.data); data.is_valid(raise_exception=True)
        payload = json.loads(json.dumps(data.validated_data, default=str))
        signature = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        prior = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=payload["request_id"]).first()
        if prior:
            if not prior.after.get("cancelled") and prior.after.get("signature") != signature:
                raise EditConflict("这个保存编号已用于其他批注内容，请查回原记录。")
            return Response(receipt(prior))
        latest = reviews(actor).filter(object_id=payload["review_id"]).order_by("-created_at", "-pk").first()
        if payload["expected_version"] != (str(latest.pk) if latest else "0"):
            raise EditConflict("此批注已有更新，你的输入仍保留，请先读取保存记录。")
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="visual_review", object_id=payload["review_id"],
            request_id=payload["request_id"], after={"signature": signature, "payload": payload})
        return Response(receipt(row), status=201)


class VisualReviewReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(responses=VisualReviewReceipt)
    def get(self, request, request_id):
        actor = require_review(request)
        return Response(receipt(get_object_or_404(AuditEvent, actor=actor, action=ACTION, request_id=str(request_id))))

    @extend_schema(request=OpenApiTypes.OBJECT, responses=VisualReviewReceipt)
    @transaction.atomic
    def post(self, request, request_id):
        actor = require_review(request, lock=True)
        if request.data != {"action": "cancel_pending"}:
            raise ValidationError("请明确停止尚未执行的保存请求。")
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if row is None:
            row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="visual_review", object_id="",
                request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(row))


class VisualReviewReferenceView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(responses={(200, "image/jpeg"): OpenApiTypes.BINARY, (200, "image/png"): OpenApiTypes.BINARY})
    def get(self, request, page):
        require_review(request)
        if page not in {int(row["page"]) for row in atlas()} or not Path(settings.STL_VISUAL_ATLAS_PATH).is_file():
            raise NotFound("最终视觉PDF尚未配置，不能用其他图片替代。")
        import fitz
        with fitz.open(settings.STL_VISUAL_ATLAS_PATH) as document:
            source = document[page-1]
            images = source.get_images(full=True)
            if not images:
                raise NotFound("此页没有可读取的终稿图像。")
            original = document.extract_image(max(images, key=lambda image: image[2]*image[3])[0])
        return HttpResponse(original["image"], content_type="image/" + ("jpeg" if original["ext"] in {"jpg", "jpeg"} else original["ext"]))
