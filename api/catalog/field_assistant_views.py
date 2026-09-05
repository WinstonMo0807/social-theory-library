from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.services.field_assistant import (
    FieldAssistantError,
    FieldAssistantRequest,
    FieldAssistantService,
)
from common.permissions import IsCatalogEditor


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
            result = self.service.lookup(
                FieldAssistantRequest(
                    object_type=data["object_type"],
                    object_id=data["object_id"],
                    field_name=data["field_name"],
                    query=data.get("query", ""),
                    confirmed_context=data.get("confirmed_context", {}),
                    upload_item_id=data.get("upload_item_id"),
                )
            )
        except (FieldAssistantError, ValueError, ObjectDoesNotExist) as exc:
            return self._error(exc)
        return Response(result.as_dict())


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
