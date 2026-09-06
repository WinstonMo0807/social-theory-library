from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiTypes
from catalog.cataloging_serializers import ApiErrorSerializer, CatalogingSessionSerializer, CatalogingSessionDetailSerializer

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import CatalogingSession, DocumentType
from catalog.services.admin_workspace import build_admin_workspace
from catalog.services.cataloging_sessions import (
    CatalogingSessionConflict, abandon_cataloging_session, open_cataloging_session, session_payload,
)
from common.permissions import CanAccessBackOffice, CanEditMetadata, CanReviewCandidate


class CatalogingSessionCreateSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=CatalogingSession.SourceType.choices)
    edition_id = serializers.UUIDField(required=False)
    upload_item_id = serializers.UUIDField(required=False)
    title = serializers.CharField(required=False, allow_blank=True, max_length=600)
    document_type = serializers.ChoiceField(required=False, choices=DocumentType.choices)
    language = serializers.CharField(required=False, allow_blank=False, max_length=16)
    request_key = serializers.UUIDField(required=False)

    def validate(self, attrs):
        source = attrs["source_type"]
        if source == "upload" and not attrs.get("upload_item_id"):
            raise serializers.ValidationError({"upload_item_id": "请选择真实上传记录。"})
        if source != "upload" and attrs.get("upload_item_id"):
            raise serializers.ValidationError({"source_type": "上传记录必须使用上传编目入口。"})
        if source == "existing" and not attrs.get("edition_id"):
            raise serializers.ValidationError({"edition_id": "请选择需要编辑的版本。"})
        if source in {"manual", "import"} and attrs.get("edition_id"):
            raise serializers.ValidationError({"edition_id": "已有版本请使用编辑馆藏入口。"})
        return attrs


class CatalogingSessionListView(AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "POST" else [CanAccessBackOffice()]

    @extend_schema(operation_id="cataloging_sessions_list", responses=inline_serializer("CatalogingSessionList", {"results": CatalogingSessionSerializer(many=True)}))
    def get(self, request):
        rows = CatalogingSession.objects.select_related("edition__work").order_by("-updated_at")[:50]
        return Response({"results": [session_payload(row) for row in rows]})

    @extend_schema(request=CatalogingSessionCreateSerializer, responses={201: CatalogingSessionSerializer, 200: CatalogingSessionSerializer, 400: ApiErrorSerializer, 409: ApiErrorSerializer})
    def post(self, request):
        serializer = CatalogingSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session, created = open_cataloging_session(actor=request.user, **serializer.validated_data)
        except ObjectDoesNotExist:
            return Response({"detail": "指定的版本或上传记录不存在。"}, status=404)
        except CatalogingSessionConflict as error:
            return Response({"code": "catalog.session_conflict", "detail": str(error)}, status=409)
        return Response(session_payload(session), status=201 if created else 200)


class CatalogingSessionDetailView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(operation_id="cataloging_sessions_detail", responses=CatalogingSessionDetailSerializer)
    def get(self, request, session_id):
        session = get_object_or_404(
            CatalogingSession.objects.select_related("edition__work", "upload_item"), pk=session_id,
        )
        workspace = None
        if session.edition_id and request.query_params.get("workspace") != "0":
            workspace = build_admin_workspace(
                session.edition, user=request.user, mode="intake" if session.upload_item_id else "maintenance",
                item=session.upload_item,
            )
        return Response({"session": session_payload(session), "workspace": workspace})


class CatalogFieldContractView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from catalog.contracts.fields import FIELDS

        return Response({"version": "catalog-field-contract-v305", "fields": [field.payload() for field in FIELDS]})


class CatalogingSessionAbandonView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(request=None, responses={200: CatalogingSessionSerializer, 409: ApiErrorSerializer})
    def post(self, request, session_id):
        get_object_or_404(CatalogingSession, pk=session_id)
        try:
            session = abandon_cataloging_session(session_id, actor=request.user)
        except CatalogingSessionConflict as error:
            return Response({"code": "catalog.session_conflict", "detail": str(error)}, status=409)
        return Response(session_payload(session))


class CatalogingCandidateDecisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["link_existing", "create_draft", "keep_unresolved", "reject"])
    target_type = serializers.CharField(max_length=40)
    target_id = serializers.UUIDField(required=False, allow_null=True)
    confirm_identity = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class CatalogingCandidateDecisionView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata, CanReviewCandidate]

    @extend_schema(request=CatalogingCandidateDecisionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, session_id, candidate_id):
        from ingestion.models import EntityResolutionCandidate
        from ingestion.serializers import EntityResolutionCandidateSerializer
        from ingestion.services.entity_resolution_decisions import ResolutionDecisionError, decide_entity_resolution

        candidate = get_object_or_404(EntityResolutionCandidate, pk=candidate_id, cataloging_session_id=session_id)
        serializer = CatalogingCandidateDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data["target_id"] = str(data.get("target_id") or "")
        try:
            result = decide_entity_resolution(candidate, actor=request.user, **data)
        except ResolutionDecisionError as error:
            return Response({"code": "catalog.candidate_conflict", "detail": str(error)}, status=409)
        return Response({
            "candidate": EntityResolutionCandidateSerializer(result.candidate).data,
            "group": EntityResolutionCandidateSerializer(result.group, many=True).data,
            "idempotent": result.idempotent,
        })


class CatalogingMetadataDecisionView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata, CanReviewCandidate]

    @extend_schema(request=inline_serializer("MetadataDecision", {"action": serializers.ChoiceField(choices=["reject", "reopen"])}), responses=OpenApiTypes.OBJECT)
    def post(self, request, session_id, candidate_id):
        from ingestion.models import MetadataCandidate
        from ingestion.serializers import MetadataCandidateSerializer
        from ingestion.services.candidate_decisions import set_candidate_decision

        candidate = get_object_or_404(MetadataCandidate, pk=candidate_id, cataloging_session_id=session_id)
        action = str(request.data.get("action") or "")
        try:
            candidate = set_candidate_decision(candidate, action=action, actor=request.user)
        except ValueError as error:
            return Response({"code": "catalog.candidate_conflict", "detail": str(error)}, status=409)
        return Response(MetadataCandidateSerializer(candidate).data)


class CatalogingMetadataImportSerializer(serializers.Serializer):
    source_label = serializers.CharField(max_length=120, allow_blank=False)
    source_url = serializers.URLField(required=False, allow_blank=True, max_length=1000)
    fields = serializers.DictField(child=serializers.JSONField(), allow_empty=False)

    def validate_fields(self, fields):
        from catalog.contracts.fields import FIELD_CONTRACTS

        if len(fields) > 50:
            raise serializers.ValidationError("一次最多导入 50 个字段。")
        for name, value in fields.items():
            contract = FIELD_CONTRACTS.get(name)
            if contract is None or contract.data_type not in {"string", "text", "date", "integer", "identifier"}:
                raise serializers.ValidationError(f"{name} 不能作为普通书目值导入。")
            if len(str(value)) > 30000:
                raise serializers.ValidationError(f"{name} 内容过长。")
        return fields


class CatalogingMetadataImportView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(request=CatalogingMetadataImportSerializer, responses={201: OpenApiTypes.OBJECT, 409: ApiErrorSerializer})
    def post(self, request, session_id):
        from ingestion.services.candidate_store import persist_metadata_candidates
        from ingestion.services.metadata import Candidate

        session = get_object_or_404(CatalogingSession, pk=session_id)
        serializer = CatalogingMetadataImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        candidates = [Candidate(name, value, f"manual_import:{values['source_label']}"[:120], 0, {
            "source_label": values["source_label"], "record_url": values.get("source_url", ""),
            "extraction_method": "manual_metadata_import",
        }) for name, value in values["fields"].items()]
        try:
            result = persist_metadata_candidates(None, candidates, cataloging_session=session, supersede_sources=set())
        except ValueError as error:
            return Response({"code": "catalog.import_conflict", "detail": str(error)}, status=409)
        return Response({"candidate_stats": result, "canonical_changed": False}, status=201)
