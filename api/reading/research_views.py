"""Owner-only endpoints. Staff membership never expands private querysets."""
import json
from urllib.parse import quote

from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.private_responses import PrivateAccountResponses

from . import research
from .research_replay_views import ReplayActions
from .research_directory import DirectoryActions
from .path_serializers import PathCommandOutput
from .citation_audit import audit_capabilities, audit_versions, create_audit, original_document, update_audit
from .citation_sources import paginated_units
from .research_serializers import CitationSourceCreateInput, CitationSourceCommandInput, CitationTextUnitsOutput
from .models import (CitationAudit, PersonalReadingPlan, ResearchMemory, ResearchProject, ResearchTurn)
from .research_serializers import (AnalysisDecisionInput, AuditCapabilitiesOutput, AuditCommandInput, AuditCreateInput, AuditVersionInput, AuditVersionsOutput, CitationOCROutput, ComparisonDraftInput, ComparisonInput,
    MemoryCreateInput, MemoryListInput, MemorySearchInput, MemoryUpdateInput, MemoryUsageInput, PlanCreateInput, PlanUpdateInput,
    PlanCommandInput, PlanDeleteInput, ProjectCreateInput, ProjectImportInput, ProjectUpdateInput, ResearchAccountOutput, ResearchPreferenceInput, RevisionInput, SelectionInput, TurnCreateInput,
    SubclaimsInput, TurnExpandInput, TurnListInput, TurnRetryInput)


class PrivateRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    revision = serializers.IntegerField(read_only=True)
    data = serializers.JSONField(read_only=True)
    status = serializers.CharField(read_only=True, required=False)
    state = serializers.CharField(read_only=True, required=False)
    enhancement_status = serializers.CharField(read_only=True, required=False)
    archived = serializers.BooleanField(read_only=True, required=False)
    generation = serializers.IntegerField(read_only=True, required=False)
    error_code = serializers.CharField(read_only=True, required=False)
    poll_after_ms = serializers.IntegerField(read_only=True, allow_null=True, required=False)
    completed_units = serializers.IntegerField(read_only=True, required=False)
    total_units = serializers.IntegerField(read_only=True, required=False)
    project_id = serializers.UUIDField(read_only=True, allow_null=True, required=False)
    conversation_id = serializers.UUIDField(read_only=True, allow_null=True, required=False)
    parent_id = serializers.UUIDField(read_only=True, allow_null=True, required=False)
    discovery_session_id = serializers.UUIDField(read_only=True, allow_null=True, required=False)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    finished_at = serializers.DateTimeField(read_only=True, allow_null=True, required=False)


class PrivateRecordExportSerializer(PrivateRecordSerializer):
    schema_version = serializers.IntegerField(read_only=True)
    turns = PrivateRecordSerializer(many=True, read_only=True, required=False)


class MemorySearchResultSerializer(PrivateRecordSerializer):
    match_reason = serializers.CharField(read_only=True)


class MemorySearchOutput(serializers.Serializer):
    results = MemorySearchResultSerializer(many=True, read_only=True)
    mode = serializers.ChoiceField(choices=["disabled", "local_lexical", "local_semantic_owner_candidates"], read_only=True)
    notice = serializers.CharField(read_only=True, required=False)
    warning = serializers.CharField(read_only=True, allow_blank=True, required=False)
    semantic_candidate_limit = serializers.IntegerField(read_only=True, allow_null=True, required=False)
    semantic_scope_count = serializers.IntegerField(read_only=True, allow_null=True, required=False)
    semantic_evaluated_count = serializers.IntegerField(read_only=True, allow_null=True, required=False)
    semantic_excluded_count = serializers.IntegerField(read_only=True, allow_null=True, required=False)
    semantic_scope_complete = serializers.BooleanField(read_only=True, required=False)


class MemoryListOutput(serializers.Serializer):
    count = serializers.IntegerField(read_only=True)
    next = serializers.URLField(read_only=True, allow_null=True, required=False)
    previous = serializers.URLField(read_only=True, allow_null=True, required=False)
    results = PrivateRecordSerializer(many=True, read_only=True)
    counts = serializers.DictField(child=serializers.IntegerField(), read_only=True,
        help_text="q/kind/source_status 范围内、state 过滤前的 total/confirmed/proposed/ignored 真实总数。")


class PrivateResponses(PrivateAccountResponses):
    """Compatibility name used by the existing owner-scoped workspaces."""



def command(request, schema=None):
    if not isinstance(request.data, dict) or len(json.dumps(request.data, ensure_ascii=False)) > 250_000:
        raise ValidationError({"detail": "请求需要对象，且内容不能超过 250000 字符。"})
    if schema:
        schema(data=request.data).is_valid(raise_exception=True)
    return request.data


class PrivateRecordViewSet(PrivateResponses, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PrivateRecordSerializer
    model = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.model.objects.none()
        filters = {"project__user": self.request.user} if self.model is ResearchTurn else {"user": self.request.user}
        return self.model.objects.filter(**filters)

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        rows = page if page is not None else self.get_queryset()
        data = [research.serialize_record(row, request.user) for row in rows]
        return self.get_paginated_response(data) if page is not None else Response(data)

    def retrieve(self, request, pk=None):
        return Response(research.serialize_record(self.get_object(), request.user))

    @extend_schema(responses=PrivateRecordExportSerializer)
    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        record = self.get_object()
        from .research_replay_history import export_turn, export_turns
        data = export_turn(record, request.user) if self.model is ResearchTurn else research.serialize_record(record, request.user)
        if self.model is ResearchProject:
            data["turns"] = export_turns(record, request.user)
        response = Response({"schema_version": 1, **data})
        response["Content-Disposition"] = f'attachment; filename="research-{record.id}.json"'
        return response

    @extend_schema(request=RevisionInput, responses={204: None})
    @transaction.atomic
    def destroy(self, request, pk=None):
        record = self.get_object()
        data = command(request, RevisionInput)
        if self.model is ResearchProject:
            research.delete_project(request.user, record.id, data["expected_revision"])
        else:
            record = research.owned(self.model, request.user, record.id, lock=True)
            research.expect(record, data.get("expected_revision"))
            # Worker writes use generation + active-status checks, and never recreate missing rows.
            record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResearchProjectViewSet(DirectoryActions, ReplayActions, PrivateRecordViewSet):
    model = ResearchProject

    @extend_schema(request=ProjectImportInput, responses={201: PrivateRecordSerializer})
    @action(detail=False, methods=["post"], url_path="import")
    def import_local(self, request):
        record = research.import_project(request.user, command(request, ProjectImportInput))
        return Response(research.serialize_record(record, request.user), status=201)

    @extend_schema(request=ProjectCreateInput, responses={201: PrivateRecordSerializer})
    def create(self, request):
        record = research.create_project(request.user, command(request, ProjectCreateInput))
        return Response(research.serialize_record(record, request.user), status=201)

    @extend_schema(request=ProjectUpdateInput)
    def partial_update(self, request, pk=None):
        return Response(research.serialize_record(research.update_project(request.user, pk, command(request, ProjectUpdateInput)), request.user))

    @extend_schema(request=SelectionInput)
    @action(detail=True, methods=["post"])
    def selections(self, request, pk=None):
        return Response(research.serialize_record(research.change_selection(request.user, pk, command(request, SelectionInput)), request.user))

    @extend_schema(request=ComparisonInput)
    @action(detail=True, methods=["post"])
    def comparison(self, request, pk=None):
        return Response(research.serialize_record(research.save_comparison(request.user, pk, command(request, ComparisonInput)), request.user))

    @extend_schema(request=ComparisonDraftInput, responses={202: PrivateRecordSerializer})
    @action(detail=True, methods=["post"], url_path="comparison-draft")
    def comparison_draft(self, request, pk=None):
        from .research_comparison import start_draft
        turn = start_draft(request, pk, command(request, ComparisonDraftInput))
        return Response(research.serialize_record(turn, request.user), status=202)

    @extend_schema(methods=["GET"], parameters=[TurnListInput], responses=PrivateRecordSerializer(many=True))
    @extend_schema(request=TurnCreateInput, methods=["POST"], responses={202: PrivateRecordSerializer})
    @action(detail=True, methods=["get", "post"])
    def turns(self, request, pk=None):
        project = self.get_object()
        if request.method == "POST":
            turn = research.start_turn(request, project.id, command(request, TurnCreateInput))
            return Response(research.serialize_record(turn, request.user), status=202)
        filters = TurnListInput(data=request.query_params)
        filters.is_valid(raise_exception=True)
        mode = filters.validated_data.get("mode", "all")
        newest = filters.validated_data.get("order") == "newest"
        rows = project.turns.order_by("-created_at" if newest else "created_at", "-id" if newest else "id")
        if mode != "all":
            # Mode is part of the existing encrypted payload; inspect only this owner's project.
            rows = [row for row in rows.iterator(chunk_size=100) if research.unpack(row).get("mode", "search") == mode]
        page = self.paginate_queryset(rows)
        rows = page if page is not None else rows
        data = [research.serialize_record(row, request.user) for row in rows]
        return self.get_paginated_response(data) if page is not None else Response(data)


class ResearchTurnViewSet(PrivateRecordViewSet):
    model = ResearchTurn
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(request=SubclaimsInput, responses=PrivateRecordSerializer)
    @action(detail=True, methods=["post"])
    def subclaims(self, request, pk=None):
        turn = research.save_subclaims(request.user, pk, command(request, SubclaimsInput))
        return Response(research.serialize_record(turn, request.user))

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(research.serialize_record(research.cancel_turn(request.user, pk), request.user))

    @extend_schema(request=AnalysisDecisionInput)
    @action(detail=True, methods=["post"])
    def decision(self, request, pk=None):
        return Response(research.serialize_record(research.decide_analysis(request.user, pk, command(request, AnalysisDecisionInput)), request.user))

    @extend_schema(request=TurnExpandInput, responses={202: PrivateRecordSerializer})
    @action(detail=True, methods=["post"])
    def expand(self, request, pk=None):
        turn = self.get_object()
        data = dict(command(request, TurnExpandInput))
        if "scope" not in data:
            raise ValidationError({"scope": "扩大检索需要明确选择新范围。"})
        previous = research.unpack(turn)
        data.update(parent_id=str(turn.id), expand_from_parent=True, mode=previous["mode"], statement=previous["statement"])
        data.setdefault("question", previous["question"])
        new_turn = research.start_turn(request, turn.project_id, data)
        return Response(research.serialize_record(new_turn, request.user), status=202)

    @extend_schema(request=TurnRetryInput, responses={202: PrivateRecordSerializer})
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        turn = self.get_object()
        if turn.status in research.ACTIVE:
            raise research.ResearchConflict("本轮仍在进行。")
        data = dict(command(request, TurnRetryInput))
        previous = research.unpack(turn)
        if "comparison_draft" in previous:
            from .research_comparison import start_draft
            draft = previous["comparison_draft"]
            new_turn = start_draft(request, turn.project_id, {**data, "dimension": draft["dimension"],
                "reference_ids": draft["reference_ids"]}, parent_id=str(turn.id))
            return Response(research.serialize_record(new_turn, request.user), status=202)
        data.update(parent_id=str(turn.id), question=previous["question"], scope=previous["scope"],
                    mode=previous["mode"], statement=previous["statement"], expand_from_parent=True,
                    return_context=previous.get("return_context", {}))
        new_turn = research.start_turn(request, turn.project_id, data)
        return Response(research.serialize_record(new_turn, request.user), status=202)


class ResearchMemoryViewSet(PrivateRecordViewSet):
    model = ResearchMemory

    @extend_schema(parameters=[MemoryListInput], responses=MemoryListOutput)
    def list(self, request):
        schema = MemoryListInput(data=request.query_params)
        schema.is_valid(raise_exception=True)
        rows, counts = research.list_memories(request.user, schema.validated_data)
        page = self.paginate_queryset(rows)
        contexts = research.memory_contexts(request.user)
        data = [research.serialize_record(row, request.user, memory_context_rows=contexts) for row in (page if page is not None else rows)]
        response = self.get_paginated_response(data) if page is not None else Response({"results": data, "count": len(rows)})
        response.data["counts"] = counts
        return response

    @extend_schema(request=MemoryCreateInput, responses={201: PrivateRecordSerializer})
    def create(self, request):
        memory = research.create_memory(request.user, command(request, MemoryCreateInput))
        return Response(research.serialize_record(memory, request.user), status=201)

    @extend_schema(request=MemoryUpdateInput)
    def partial_update(self, request, pk=None):
        return Response(research.serialize_record(research.update_memory(request.user, pk, command(request, MemoryUpdateInput)), request.user))

    @extend_schema(request=RevisionInput, responses={204: None})
    def destroy(self, request, pk=None):
        data = command(request, RevisionInput)
        research.delete_memory(request.user, pk, data.get("expected_revision"))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def usage(self, request, pk=None):
        memory = self.get_object()
        return Response({"memory_id": str(memory.id), "revision": memory.revision,
            "targets": research.memory_usage_targets(request.user, memory),
            "notice": "本人确认不等于授权；仅在明确选择的研究与阅读计划内使用。"})

    @extend_schema(request=MemoryUsageInput, responses=PrivateRecordSerializer)
    @usage.mapping.post
    def update_usage(self, request, pk=None):
        memory = research.update_memory_usage(request.user, pk, command(request, MemoryUsageInput))
        return Response(research.serialize_record(memory, request.user))

    @extend_schema(request=MemorySearchInput, responses=MemorySearchOutput)
    @action(detail=False, methods=["post"])
    def search(self, request):
        data = command(request, MemorySearchInput)
        if "semantic" in data and not isinstance(data["semantic"], bool):
            raise ValidationError({"semantic": "需要布尔值。"})
        return Response(research.search_memories(request.user, data.get("q"), semantic=data.get("semantic", False),
                                                allowed_ids=data.get("allowed_ids"), context=data.get("context")))


class PersonalReadingPlanViewSet(PrivateRecordViewSet):
    model = PersonalReadingPlan

    def get_queryset(self):
        return super().get_queryset().filter(public_path_id__isnull=True)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        pk = kwargs.get("pk")
        if pk:
            record = PersonalReadingPlan.objects.filter(user=request.user, pk=research.identifier(pk)).first()
            if record and research.unpack(record).get("origin", {}).get("type") == "public_path_copy":
                if request.headers.get("X-Reader-Owner") != str(request.user.pk):
                    raise PermissionDenied("读取或修改公共路径私人副本需要携带当前账户标识。")

    @extend_schema(request=PlanDeleteInput, responses={204: None, 200: PathCommandOutput})
    def destroy(self, request, pk=None):
        from . import path_plans
        record = self.get_queryset().filter(pk=research.identifier(pk)).first()
        is_copy = record and research.unpack(record).get("origin", {}).get("type") == "public_path_copy"
        if is_copy or (record is None and isinstance(request.data, dict) and request.data.get("request_id")):
            if request.headers.get("X-Reader-Owner") != str(request.user.pk):
                raise PermissionDenied("删除公共路径私人副本需要携带当前账户标识。")
            return Response(path_plans.delete_plan(request.user, pk, request.data, copy_only=True))
        return super().destroy(request, pk)

    @extend_schema(request=PlanCreateInput, responses={201: PrivateRecordSerializer, 202: PrivateRecordSerializer})
    def create(self, request):
        plan = research.request_plan(request, command(request, PlanCreateInput))
        return Response(research.serialize_record(plan, request.user),
                        status=202 if research.unpack(plan).get("generation_status") == "queued" else 201)

    @extend_schema(request=PlanUpdateInput)
    def partial_update(self, request, pk=None):
        return Response(research.serialize_record(research.update_plan(request.user, pk, command(request, PlanUpdateInput)), request.user))

    @extend_schema(request=PlanCommandInput, responses=PrivateRecordSerializer)
    @action(detail=True, methods=["post"])
    def command(self, request, pk=None):
        plan = research.command_plan(request, pk, command(request, PlanCommandInput))
        return Response(research.serialize_record(plan, request.user))


class CitationAuditViewSet(PrivateRecordViewSet):
    model = CitationAudit

    def get_queryset(self):
        return super().get_queryset().filter(purpose="manuscript").defer("original_ciphertext", "preview_ciphertext")

    @extend_schema(responses=AuditCapabilitiesOutput)
    @action(detail=False, methods=["get"])
    def capabilities(self, request):
        return Response(audit_capabilities())

    @extend_schema(request={"multipart/form-data": AuditCreateInput}, responses={202: PrivateRecordSerializer})
    def create(self, request):
        AuditCreateInput(data=request.data).is_valid(raise_exception=True)
        audit = create_audit(request.user, request.FILES.get("file"), request.data)
        return Response(research.serialize_record(audit, request.user), status=202)

    @extend_schema(responses=AuditVersionsOutput)
    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        return Response(audit_versions(self.get_object(), request.user))

    @extend_schema(request={"multipart/form-data": AuditVersionInput}, responses={202: PrivateRecordSerializer})
    @versions.mapping.post
    def upload_version(self, request, pk=None):
        schema = AuditVersionInput(data=request.data)
        schema.is_valid(raise_exception=True)
        audit = create_audit(request.user, request.FILES.get("file"), schema.validated_data, parent_id=pk)
        return Response(research.serialize_record(audit, request.user), status=202)

    @extend_schema(request=AuditCommandInput)
    @action(detail=True, methods=["post"])
    def command(self, request, pk=None):
        audit = update_audit(request.user, pk, command(request, AuditCommandInput))
        return Response(research.serialize_record(audit, request.user))

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def original(self, request, pk=None):
        audit = self.get_object()
        payload = research.unpack(audit)
        response = HttpResponse(original_document(audit), content_type="application/octet-stream")
        response["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(payload["filename"], safe="")
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(responses=CitationOCROutput)
    @action(detail=True, methods=["get"])
    def ocr(self, request, pk=None):
        audit = self.get_object()
        payload = research.unpack(audit)
        units = payload.get("ocr_units", {})
        unit_id = request.query_params.get("unit_id")
        if unit_id is not None:
            if unit_id not in units:
                raise NotFound("此稿件中没有该 OCR 页或图像。")
            return Response({"progress": payload.get("ocr_progress", {}), "unit": {"id": unit_id, **units[unit_id]}})
        return Response({"progress": payload.get("ocr_progress", {}), "units": [
            {"id": key, **{name: value for name, value in unit.items() if name not in {"text", "blocks"}}}
            for key, unit in units.items()]})


    @extend_schema(responses=CitationTextUnitsOutput)
    @action(detail=True, methods=["get"])
    def manuscript(self, request, pk=None):
        return Response(paginated_units(self.get_object(), request.query_params))


class CitationSourceViewSet(PrivateRecordViewSet):
    model = CitationAudit

    def get_queryset(self):
        return super().get_queryset().filter(purpose="private_source").defer("original_ciphertext", "preview_ciphertext")

    @extend_schema(request={"multipart/form-data": CitationSourceCreateInput}, responses={202: PrivateRecordSerializer})
    def create(self, request):
        schema = CitationSourceCreateInput(data=request.data)
        schema.is_valid(raise_exception=True)
        source = create_audit(request.user, request.FILES.get("file"), schema.validated_data, purpose="private_source")
        return Response(research.serialize_record(source, request.user), status=202)

    @extend_schema(request=CitationSourceCommandInput)
    @action(detail=True, methods=["post"])
    def command(self, request, pk=None):
        source = update_audit(request.user, pk, command(request, CitationSourceCommandInput), purpose="private_source")
        return Response(research.serialize_record(source, request.user))

    original = CitationAuditViewSet.original
    ocr = CitationAuditViewSet.ocr

    @extend_schema(responses=CitationTextUnitsOutput)
    @action(detail=True, methods=["get"])
    def segments(self, request, pk=None):
        return Response(paginated_units(self.get_object(), request.query_params))


class ResearchAccountView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ResearchAccountOutput

    @extend_schema(responses=ResearchAccountOutput)
    def get(self, request):
        user = request.user
        return Response({"counts": {"research": ResearchProject.objects.filter(user=user).count(),
            "memories": ResearchMemory.objects.filter(user=user).count(), "plans": PersonalReadingPlan.objects.filter(user=user, public_path_id__isnull=True).count(),
            "audits": CitationAudit.objects.filter(user=user, purpose="manuscript").count()},
            "preferences": (user.reader_profile.reading_preferences or {}).get("research_personalization", False),
            "deletion_notice": "删除同步移除该记录及其派生向量；独立来源笔记保留。备份按原有保留期清理。"})

    @extend_schema(request=ResearchPreferenceInput, responses=ResearchPreferenceInput)
    @transaction.atomic
    def patch(self, request):
        from accounts.models import ReaderProfile
        data = command(request, ResearchPreferenceInput)
        value = data.get("research_personalization")
        if not isinstance(value, bool):
            raise ValidationError({"research_personalization": "需要布尔值。"})
        contexts = research.memory_contexts(request.user, lock=True) if value is False else []
        profile = ReaderProfile.objects.select_for_update().get(user=request.user)
        profile.reading_preferences = {**(profile.reading_preferences or {}), "research_personalization": value}
        profile.save(update_fields=["reading_preferences"])
        if value is False:
            for _, record in contexts:
                payload = research.unpack(record)
                if payload.get("use_confirmed_memories") or payload.get("confirmed_memory_ids"):
                    payload.update(use_confirmed_memories=False, confirmed_memory_ids=[])
                    if isinstance(record, PersonalReadingPlan):
                        research.invalidate_plan_suggestions(payload, "authorization_changed")
                    research.save_data(record, payload)
        return Response({"research_personalization": value})
