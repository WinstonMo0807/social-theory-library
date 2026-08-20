from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Edition
from catalog.services.workflow_suggestions import suggestion_policy_payload
from catalog.services.workflow_suggestions import STEP_FIELD_ALIASES, WorkflowSuggestionAggregator
from common.permissions import CanRunEnrichment, CanViewEvidence
from ingestion.models import UploadItem


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
                payload = aggregator.run_step(step=step or "work", fields=fields or ([field] if field else None), mode=mode, actor=request.user)
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
