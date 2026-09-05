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
    allow_external = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
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
    edition_id = serializers.UUIDField()
    field_name = serializers.CharField(max_length=80)
    label = serializers.CharField(max_length=300)
    details = serializers.JSONField(required=False)
    allow_possible_duplicate = serializers.BooleanField(required=False, default=False)


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
        return Response({"detail": str(exc)}, status=code)


class AdminFieldAssistantLookupView(_FieldAssistantView):
    def post(self, request):
        serializer = FieldAssistantLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            if data.get("scope") == "curation" or data["object_type"] not in {"work", "edition"}:
                from catalog.services.field_assistant.curation import lookup_curation_field

                return Response(lookup_curation_field(
                    object_type=data["object_type"], object_id=data.get("object_id"),
                    field_name=data["field_name"], query=data.get("query", ""),
                    authority_type=data.get("authority_type", ""),
                    current_value=data.get("current_value"), form_context=data.get("form_context", {}),
                    actor=request.user,
                ))
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
            if data["refresh"]:
                if not CanRunEnrichment().has_permission(request, self):
                    refresh = {"state": "local", "message": "已查找馆内记录和已有依据。当前账户没有外部查找权限，仍可手工填写。"}
                else:
                    from catalog.services.field_assistant.refresh import request_field_refresh

                    try:
                        refresh = request_field_refresh(field_request, actor=request.user)
                    except (ValueError, RuntimeError):
                        logger.warning("Field research could not be prepared", exc_info=True)
                        refresh = {"state": "unavailable", "message": "新的建议暂时无法准备，仍可使用馆内记录、已有依据或手工填写。"}
            result = self.service.lookup(field_request)
        except (FieldAssistantError, ValueError, ObjectDoesNotExist) as exc:
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
        except (FieldAssistantError, ValueError, ObjectDoesNotExist) as exc:
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
        except (FieldAssistantError, ValueError, ObjectDoesNotExist) as exc:
            return self._error(exc)
        return Response(result)


class AdminFieldAssistantCreateView(_FieldAssistantView):
    def post(self, request):
        serializer = FieldAssistantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = self.service.create_and_link(
                actor=request.user,
                **serializer.validated_data,
            )
        except (FieldAssistantError, ValueError, ObjectDoesNotExist) as exc:
            return self._error(exc)
        return Response(result, status=status.HTTP_201_CREATED)


class AdminFieldAssistantDuplicateView(_FieldAssistantView):
    def post(self, request):
        serializer = FieldAssistantDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            matches = self.service.duplicate_check(**serializer.validated_data)
        except (FieldAssistantError, ValueError) as exc:
            return self._error(exc)
        return Response({"matches": matches})
