from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.services.field_assistant import (
    FieldAssistantError,
    FieldAssistantRequest,
    FieldAssistantService,
)
from common.permissions import CanRunEnrichment, IsCatalogEditor
from catalog.services.editorial_revision import EditorialRevisionConflict

logger = logging.getLogger(__name__)


class FieldAssistantLookupSerializer(serializers.Serializer):
    object_type = serializers.ChoiceField(choices=("edition", "work", "person", "topic", "knowledge_node", "discipline", "subdiscipline", "reading_path"))
    object_id = serializers.UUIDField(required=False, allow_null=True)
    field_name = serializers.CharField(max_length=80)
    query = serializers.CharField(max_length=500, allow_blank=True, required=False)
    confirmed_context = serializers.JSONField(required=False)
    upload_item_id = serializers.UUIDField(required=False, allow_null=True)
    scope = serializers.ChoiceField(choices=("catalog", "curation"), required=False, default="catalog")
    authority_type = serializers.CharField(max_length=40, required=False, allow_blank=True)
    current_value = serializers.JSONField(required=False, allow_null=True)
    form_context = serializers.JSONField(required=False)
    refresh = serializers.BooleanField(required=False, default=False)
    allow_external = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        import json

        for name in ("confirmed_context", "form_context"):
            context = attrs.get(name, {})
            if not isinstance(context, dict) or len(json.dumps(context, ensure_ascii=False).encode()) > 20 * 1024:
                raise serializers.ValidationError({name: "填写上下文须为不超过20KiB的对象。"})
        if attrs.get("scope") == "catalog" and attrs["object_type"] in {"work", "edition"} and not attrs.get("object_id"):
            raise serializers.ValidationError({"object_id": "请先保存当前馆藏。"})
        return attrs


class FieldAssistantDecisionSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    field_name = serializers.CharField(max_length=80)
    source_type = serializers.CharField(max_length=80)
    source_id = serializers.UUIDField()
    selected_value = serializers.CharField(max_length=30000, allow_blank=True, required=False)
    reason = serializers.CharField(max_length=1000, allow_blank=True, required=False)


class FieldAssistantCreateSerializer(serializers.Serializer):
    request_id = serializers.UUIDField(required=False)
    edition_id = serializers.UUIDField()
    field_name = serializers.CharField(max_length=80)
    label = serializers.CharField(max_length=300)
    details = serializers.JSONField(required=False)
    allow_possible_duplicate = serializers.BooleanField(required=False, default=False)
    defer_link = serializers.BooleanField(required=False, default=False)

    def validate_details(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("新建内容须为对象。")
        if "discipline_id" in value:
            value["discipline_id"] = serializers.UUIDField().run_validation(value["discipline_id"])
        return value


class FieldAssistantDuplicateSerializer(serializers.Serializer):
    field_name = serializers.CharField(max_length=80)
    label = serializers.CharField(max_length=300)


class _FieldAssistantView(APIView):
    permission_classes = [IsCatalogEditor]
    service = FieldAssistantService()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    @staticmethod
    def _error(exc: Exception) -> Response:
        code = status.HTTP_404_NOT_FOUND if isinstance(exc, ObjectDoesNotExist) else status.HTTP_400_BAD_REQUEST
        if isinstance(exc, EditorialRevisionConflict):
            code = status.HTTP_409_CONFLICT
        return Response({"detail": str(exc)}, status=code)


class AdminFieldAssistantLookupView(_FieldAssistantView):
    def post(self, request):
        serializer = FieldAssistantLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            if data.get("scope") == "curation" or data["object_type"] not in {"work", "edition"}:
                from catalog.services.field_assistant.curation import lookup_curation_field

                can_lookup = CanRunEnrichment().has_permission(request, self)
                result = lookup_curation_field(
                    object_type=data["object_type"], object_id=data.get("object_id"),
                    field_name=data["field_name"], query=data.get("query", ""),
                    authority_type=data.get("authority_type", ""),
                    current_value=data.get("current_value"), form_context=data.get("form_context", {}),
                    actor=request.user,
                    allow_external=False,
                )
                result["can_lookup_external"] = can_lookup
                if data["refresh"] and data["allow_external"] and can_lookup:
                    result = {**result, "message": "此编辑器使用馆内已有依据。免费生成能力尚未启用，可继续手工编辑；书目请使用整条免费来源查找。", "state": "not_enabled"}
                if data["refresh"] and data["allow_external"] and not can_lookup:
                    result = {**result, "message": "当前账户没有外部查找权限。已保留馆内记录和已有建议，仍可手工填写。", "state": "permission_denied"}
                return Response(result)
            field_request = FieldAssistantRequest(
                    object_type=data["object_type"],
                    object_id=data["object_id"],
                    field_name=data["field_name"],
                    query=data.get("query", ""),
                    confirmed_context=data.get("confirmed_context", {}),
                    upload_item_id=data.get("upload_item_id"),
                    allow_external=data["allow_external"],
            )
            refresh = None
            if not data["refresh"]:
                from catalog.services.field_assistant.refresh import current_field_refresh

                refresh = current_field_refresh(field_request)
            if data["refresh"]:
                if not CanRunEnrichment().has_permission(request, self):
                    refresh = {"state": "permission_denied", "message": "已查找馆内记录和已有依据。当前账户没有外部查找权限，仍可手工填写。"}
                else:
                    refresh = {"state": "not_enabled", "message": "外部书目现按整条版本查询。请点击工作页的查找免费来源；此字段保留馆内记录和已有候选。"}
            result = self.service.lookup(field_request)
        except (FieldAssistantError, ValueError, ObjectDoesNotExist, EditorialRevisionConflict) as exc:
            return self._error(exc)
        payload = result.as_dict()
        if refresh is not None:
            payload["refresh"] = refresh
        return Response(payload)


class AdminFieldAssistantAdoptView(_FieldAssistantView):
    def post(self, request):
        serializer = FieldAssistantDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            result = self.service.adopt(actor=request.user, **data)
        except (FieldAssistantError, ValueError, ObjectDoesNotExist, EditorialRevisionConflict) as exc:
            return self._error(exc)
        return Response(result)


class AdminFieldAssistantRejectView(_FieldAssistantView):
    def post(self, request):
        serializer = FieldAssistantDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        data.pop("selected_value", None)
        try:
            result = self.service.reject(actor=request.user, **data)
        except (FieldAssistantError, ValueError, ObjectDoesNotExist, EditorialRevisionConflict) as exc:
            return self._error(exc)
        return Response(result)


class AdminFieldAssistantCreateView(_FieldAssistantView):
    def post(self, request):
        serializer = FieldAssistantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["field_name"] == "subdiscipline" and serializer.validated_data["defer_link"]:
            from django.db import transaction
            from django.shortcuts import get_object_or_404
            from catalog.models import Discipline, Edition, Subdiscipline
            from catalog.services.field_assistant.service import _unique_named_slug
            from ingestion.models import AuditEvent
            values = serializer.validated_data
            get_object_or_404(Edition, pk=values["edition_id"])
            discipline = get_object_or_404(Discipline, pk=(values.get("details") or {}).get("discipline_id"))
            if discipline.editorial_status != "published":
                return Response({"detail": "请选择已公开的所属学科。"}, status=400)
            label = " ".join(values["label"].split())
            if not label or len(label) > 240:
                return Response({"detail": "子学科名称须为1至240个字符。"}, status=400)
            if Subdiscipline.objects.filter(name__iexact=label, discipline=discipline).exists() and not values["allow_possible_duplicate"]:
                return Response({"detail": "已有同名子学科，请先核对。"}, status=409)
            with transaction.atomic():
                entity = Subdiscipline.objects.create(name=label, slug=_unique_named_slug(Subdiscipline, label), discipline=discipline, editorial_status="draft")
                AuditEvent.objects.create(actor=request.user, action="authority.inline_draft", object_type="subdiscipline", object_id=str(entity.pk), after={"linked": False})
            url = f"/admin/theories/subdisciplines?subdiscipline={entity.pk}"
            return Response({"saved": True, "linked": False, "entity": {"id": str(entity.pk), "type": "subdiscipline", "name": label, "label": label, "status": "draft", "edit_url": url}, "edit_url": url}, status=201)
        try:
            result = self.service.create_and_link(
                actor=request.user,
                **serializer.validated_data,
            )
        except (FieldAssistantError, ValueError, ObjectDoesNotExist, EditorialRevisionConflict) as exc:
            return self._error(exc)
        return Response(result, status=status.HTTP_201_CREATED)


class AdminFieldAssistantDuplicateView(_FieldAssistantView):
    def post(self, request):
        serializer = FieldAssistantDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["field_name"] == "subdiscipline":
            from catalog.models import Subdiscipline
            rows = Subdiscipline.objects.filter(name__icontains=serializer.validated_data["label"]).order_by("name")[:10]
            return Response({"matches": [{"id": str(row.pk), "label": row.name, "name": row.name, "type": "subdiscipline", "status": row.editorial_status} for row in rows]})
        try:
            matches = self.service.duplicate_check(**serializer.validated_data)
        except (FieldAssistantError, ValueError) as exc:
            return self._error(exc)
        return Response({"matches": matches})
