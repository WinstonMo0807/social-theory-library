from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Edition
from catalog.enrichment_serializers import (
    EnrichmentCandidateSerializer,
    FieldEnrichmentRequestSerializer,
)
from catalog.services.candidate_verification import (
    CandidateVerificationError,
    verify_research_candidate,
)
from catalog.services.workflow_suggestions import suggestion_policy_payload
from catalog.services.workflow_suggestions import STEP_FIELD_ALIASES, WorkflowSuggestionAggregator
from catalog.services.field_enrichment import FieldEnrichmentRequest, FieldEnrichmentService
from catalog.services.field_enrichment.web import WebFetchError
from common.permissions import CanRunEnrichment, CanViewEvidence
from ingestion.models import AuditEvent, EntityResolutionCandidate, UploadItem
from ingestion.serializers import EntityResolutionCandidateSerializer


def _request_values(request):
    source = request.data if request.method == "POST" else request.query_params
    step = str(source.get("step") or "").strip().casefold() or None
    field = str(source.get("field") or "").strip() or None
    fields = source.get("fields")
    if isinstance(fields, str):
        fields = [value.strip() for value in fields.split(",") if value.strip()]
    elif not isinstance(fields, (list, tuple)):
        fields = None
    mode = str(source.get("mode") or "full").strip().casefold()
    query = str(source.get("q") or source.get("query") or "").strip() or None
    return step, field, list(fields) if fields else None, mode, query


class WorkflowSuggestionPermissionMixin:
    def get_permissions(self):
        return [CanRunEnrichment()] if self.request.method == "POST" else [CanViewEvidence()]


class _WorkflowSuggestionBase(WorkflowSuggestionPermissionMixin, APIView):
    def _payload(self, request, edition, item=None):
        step, field, fields, mode, query = _request_values(request)
        if step and step not in STEP_FIELD_ALIASES:
            return None, Response({"detail": "未知工作流步骤。"}, status=status.HTTP_400_BAD_REQUEST)
        if field and step and field not in STEP_FIELD_ALIASES[step]:
            return None, Response({"detail": f"{step} 步骤不支持字段 {field}。"}, status=status.HTTP_400_BAD_REQUEST)
        aggregator = WorkflowSuggestionAggregator(edition, item=item)
        try:
            if request.method == "POST":
                payload = aggregator.run_step(
                    step=step or "work",
                    fields=fields or ([field] if field else None),
                    mode=mode,
                    query=query,
                    actor=request.user,
                )
            else:
                payload = aggregator.aggregate(step=step, field=field, query=query)
        except ValueError as exc:
            return None, Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return payload, None

    def get(self, request, *args, **kwargs):
        edition, item = self.resolve_context(request, **kwargs)
        if edition is None:
            return Response({"detail": "当前项目还没有可研究的 Work/Edition。"}, status=status.HTTP_409_CONFLICT)
        payload, error = self._payload(request, edition, item=item)
        return error or Response(payload)

    def post(self, request, *args, **kwargs):
        edition, item = self.resolve_context(request, **kwargs)
        if edition is None:
            return Response({"detail": "当前项目还没有可研究的 Work/Edition。"}, status=status.HTTP_409_CONFLICT)
        payload, error = self._payload(request, edition, item=item)
        return error or Response(payload)


class IntakeWorkflowSuggestionView(_WorkflowSuggestionBase):
    def resolve_context(self, request, *, item_id, **kwargs):
        item = get_object_or_404(UploadItem.objects.select_related("edition__work"), pk=item_id)
        return (item.edition, item) if item.edition_id else (None, item)


class MaintenanceWorkflowSuggestionView(_WorkflowSuggestionBase):
    def resolve_context(self, request, *, work_id, **kwargs):
        edition = Edition.objects.select_related("work").filter(work_id=work_id).order_by("-is_primary", "-updated_at").first()
        return edition, None


class WorkflowSuggestionPolicyView(APIView):
    permission_classes = [CanViewEvidence]

    def get(self, request):
        step = str(request.query_params.get("step") or "").strip().casefold() or None
        return Response(suggestion_policy_payload(step))


class ResearchCandidateVerifyView(APIView):
    permission_classes = [CanRunEnrichment]

    @staticmethod
    def _candidate_payload(candidate):
        raw = EntityResolutionCandidateSerializer(candidate).data
        item = candidate.upload_item
        if item.edition_id:
            suggestions = WorkflowSuggestionAggregator(item.edition, item=item).aggregate(
                step=None,
            )["suggestions"]
            suggestion = next(
                (row for row in suggestions if row["id"] == str(candidate.id)),
                None,
            )
            if suggestion is not None:
                return suggestion, raw
        return raw, raw

    def post(self, request, candidate_id):
        candidate = get_object_or_404(
            EntityResolutionCandidate.objects.select_related(
                "upload_item__edition__work"
            ),
            pk=candidate_id,
        )
        try:
            result = verify_research_candidate(candidate)
        except CandidateVerificationError as exc:
            candidate.refresh_from_db()
            payload, raw = self._candidate_payload(candidate)
            return Response(
                {
                    "status": "no_reliable_candidate" if exc.code == "no_reliable_candidate" else "failed",
                    "code": exc.code,
                    "detail": str(exc),
                    "candidate": payload,
                    "entity_candidate": raw,
                },
                status=exc.http_status,
            )

        result.candidate.refresh_from_db()
        payload, raw = self._candidate_payload(result.candidate)
        if not result.idempotent:
            AuditEvent.objects.create(
                actor=request.user,
                action="research_candidate_verified",
                object_type="EntityResolutionCandidate",
                object_id=str(result.candidate.id),
                before={"evidence_status": "lead_only"},
                after={
                    "evidence_status": "verified_text",
                    "source_record_id": str(result.candidate.source_record_id or ""),
                },
                request_id=str(request.META.get("HTTP_X_REQUEST_ID") or "")[:120],
            )
        return Response(
            {
                "status": result.status,
                "code": result.code,
                "detail": result.detail,
                "candidate": payload,
                "entity_candidate": raw,
                "idempotent": result.idempotent,
            }
        )


class ResearchLeadVerifyView(APIView):
    """Verify an ephemeral search lead through the existing field candidate store."""

    permission_classes = [CanRunEnrichment]

    def post(self, request):
        source_url = str(request.data.get("source_url") or "").strip()
        if not source_url or len(source_url) > 2048:
            return Response(
                {
                    "status": "failed",
                    "code": "missing_source_url",
                    "detail": "请提供需要核实的来源地址。",
                    "candidates": [],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        request_payload = {
            "target_type": request.data.get("target_type"),
            "target_id": request.data.get("target_id"),
            "field_name": request.data.get("field_name"),
            "form_context": request.data.get("form_context") or {},
            "requested_mode": "web",
            "visibility": "admin",
        }
        if request.data.get("fields") is not None:
            request_payload["fields"] = request.data.get("fields")
        if "current_value" in request.data:
            request_payload["current_value"] = request.data.get("current_value")
        serializer = FieldEnrichmentRequestSerializer(data=request_payload)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        enrichment_request = FieldEnrichmentRequest(
            target_type=values["target_type"],
            target_id=values["target_id"],
            field_names=tuple(values["fields"]),
            current_value=values.get("current_value"),
            form_context=values.get("form_context") or {},
            requested_mode="web",
            visibility="admin",
        )
        try:
            result = FieldEnrichmentService().verify_source(
                enrichment_request,
                source_url=source_url,
                actor=request.user,
            )
        except WebFetchError as exc:
            response_status = (
                status.HTTP_400_BAD_REQUEST
                if exc.code in {"invalid_source", "fetch_blocked"}
                else status.HTTP_502_BAD_GATEWAY
            )
            return Response(
                {
                    "status": "failed",
                    "code": exc.code,
                    "detail": str(exc),
                    "candidates": [],
                },
                status=response_status,
            )
        except ValueError as exc:
            return Response(
                {
                    "status": "no_reliable_candidate",
                    "code": "unsupported_field_contract",
                    "detail": str(exc),
                    "candidates": [],
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        candidates = EnrichmentCandidateSerializer(result.candidates, many=True).data
        if candidates:
            return Response(
                {
                    "status": "verified",
                    "code": "lead_verified",
                    "detail": "已取得正文 Evidence，并生成可供人工决定的字段候选。",
                    "candidate": candidates[0],
                    "candidates": candidates,
                    "errors": [row.__dict__ for row in result.errors],
                    "stats": result.stats,
                }
            )
        reliable_error = next(
            (row for row in result.errors if row.code == "no_reliable_candidate"),
            None,
        )
        return Response(
            {
                "status": "no_reliable_candidate",
                "code": reliable_error.code if reliable_error else "no_reliable_candidate",
                "detail": (
                    reliable_error.detail
                    if reliable_error
                    else "来源正文未达到当前字段的 Evidence policy，未生成候选。"
                ),
                "candidates": [],
                "errors": [row.__dict__ for row in result.errors],
                "stats": result.stats,
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
