from __future__ import annotations

from django.db import transaction
import logging
import uuid
import httpx
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.enrichment_serializers import (
    EnrichmentCandidateSerializer,
    EnrichmentDecisionSerializer,
    FieldEnrichmentRequestSerializer,
    NewAuthorityCandidateSerializer,
    QueryLexiconCandidateReviewSerializer,
)
from catalog.models import (
    EnrichmentCandidate,
    NewAuthorityCandidate,
    QueryLexiconCandidate,
    TheoryReviewTask,
)
from ingestion.models import MetadataCandidate
from catalog.services.field_enrichment import FieldEnrichmentRequest, FieldEnrichmentService
from catalog.services.field_enrichment.mutations import (
    accept_enrichment_candidate,
    reject_enrichment_candidate,
)
from catalog.services.query_lexicon.candidates import (
    accept_query_lexicon_candidate,
    reject_query_lexicon_candidate,
)
from catalog.services.field_enrichment.policies import FIELD_POLICIES
from catalog.services.knowledge_growth import decide_new_authority_candidate, refresh_unknown_candidate
from common.permissions import CanReviewCandidate, CanReviewCandidateOrCreateAuthority, CanViewEvidence, IsCatalogEditor


logger = logging.getLogger(__name__)


def _review_status(value: str) -> str:
    """Expose one status vocabulary while retaining each model's raw state."""

    value = str(value or "").strip().casefold()
    if value in {"pending", "proposed", "needs_changes", "deferred", "insufficient_evidence", "ambiguous", "needs_identity", "needs_evidence"}:
        return "pending"
    if value in {"accepted", "confirmed", "matched", "draft_created", "approved"}:
        return "accepted"
    if value in {"rejected", "reject"}:
        return "rejected"
    if value in {"superseded", "archived"}:
        return "superseded"
    return value or "pending"


def _with_review_status(payload: dict, raw_status: str | None = None) -> dict:
    raw = str(raw_status if raw_status is not None else payload.get("status") or "")
    payload["workflow_status"] = raw
    payload["status"] = _review_status(raw)
    if payload["status"] != raw:
        payload["review_substatus"] = raw
    return payload


def _status_filter_values(kind: str, status_filter: str) -> set[str] | None:
    if status_filter == "all":
        return None
    if kind == "new_authority" and status_filter == "accepted":
        return {NewAuthorityCandidate.Status.MATCHED, NewAuthorityCandidate.Status.DRAFT_CREATED}
    if kind == "metadata" and status_filter == "pending":
        return {MetadataCandidate.Lifecycle.PROPOSED}
    if kind == "theory" and status_filter == "accepted":
        return {TheoryReviewTask.TaskStatus.CONFIRMED}
    if kind == "theory" and status_filter == "pending":
        return {
            TheoryReviewTask.TaskStatus.PENDING,
            TheoryReviewTask.TaskStatus.NEEDS_CHANGES,
            TheoryReviewTask.TaskStatus.DEFERRED,
            TheoryReviewTask.TaskStatus.INSUFFICIENT_EVIDENCE,
        }
    return {status_filter}


class AdminFieldEnrichmentView(APIView):
    def get_permissions(self):
        return [CanViewEvidence()] if self.request.method == "GET" else [IsCatalogEditor()]

    def get(self, request):
        queryset = EnrichmentCandidate.objects.prefetch_related("evidence_records")
        params = request.query_params
        for field in ("target_type", "target_id", "field_name", "status", "candidate_kind"):
            value = str(params.get(field) or "").strip()
            if value:
                queryset = queryset.filter(**{field: value})
        queryset = queryset.order_by("-confidence", "created_at")[:200]
        return Response({"results": EnrichmentCandidateSerializer(queryset, many=True).data})

    def post(self, request):
        serializer = FieldEnrichmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        enrichment_request = FieldEnrichmentRequest(
            target_type=values["target_type"],
            target_id=values["target_id"],
            field_names=tuple(values["fields"]),
            current_value=values.get("current_value"),
            form_context=values.get("form_context") or {},
            requested_mode=values["requested_mode"],
            visibility=values["visibility"],
        )
        request_id = str(uuid.uuid4())
        try:
            result = FieldEnrichmentService().enrich(enrichment_request, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc), "request_id": request_id}, status=status.HTTP_400_BAD_REQUEST)
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            logger.warning("field enrichment provider unavailable request_id=%s error=%s", request_id, exc.__class__.__name__)
            return Response({
                "request_id": request_id,
                "results": [],
                "errors": [{"code": "provider_unavailable", "provider": "field_enrichment", "detail": "来源服务暂时不可用，其他字段和已有候选未受影响。"}],
                "stats": {"partial": True},
            })
        except Exception as exc:
            logger.exception("field enrichment unexpected failure request_id=%s", request_id)
            return Response({
                "request_id": request_id,
                "results": [],
                "errors": [{"code": "enrichment_internal_error", "provider": "field_enrichment", "detail": "字段核对服务暂时无法完成，请稍后重试。"}],
                "stats": {"partial": True},
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(
            {
                "request_id": str(result.request_id),
                "results": EnrichmentCandidateSerializer(result.candidates, many=True).data,
                "errors": [row.__dict__ for row in result.errors],
                "stats": result.stats,
            }
        )


class AdminFieldEnrichmentPolicyView(APIView):
    permission_classes = [CanViewEvidence]

    def get(self, request):
        target_type = str(request.query_params.get("target_type") or "").strip().casefold()
        policies = FIELD_POLICIES.for_target(target_type) if target_type else FIELD_POLICIES.all()
        return Response(
            {
                "policy_version": next(iter(policies), None).policy_version if policies else "",
                "results": [
                    {
                        "target_type": policy.target_type,
                        "field_name": policy.field_name,
                        "candidate_kind": policy.candidate_kind,
                        "allowed_source_classes": list(policy.allowed_source_classes),
                        "source_priority": dict(policy.source_priority),
                        "structured_adapters": list(policy.structured_adapters),
                        "allow_general_web": policy.allow_general_web,
                        "requires_identity": policy.requires_identity,
                        "evidence_min_count": policy.evidence_min_count,
                        "independent_source_min": policy.independent_source_min,
                        "conflict_policy": policy.conflict_policy,
                        "refresh_seconds": policy.refresh_seconds,
                        "value_schema": policy.value_schema,
                    }
                    for policy in policies
                ],
            }
        )


class AdminFieldEnrichmentCandidateDetailView(APIView):
    permission_classes = [CanViewEvidence]

    def get(self, request, candidate_id):
        try:
            candidate = EnrichmentCandidate.objects.prefetch_related("evidence_records").get(pk=candidate_id)
        except EnrichmentCandidate.DoesNotExist:
            return Response({"detail": "候选不存在。"}, status=404)
        return Response(EnrichmentCandidateSerializer(candidate).data)


class AdminFieldEnrichmentDecisionView(APIView):
    permission_classes = [CanReviewCandidate]

    def post(self, request, candidate_id):
        serializer = EnrichmentDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                candidate = EnrichmentCandidate.objects.select_for_update().get(pk=candidate_id)
                values = serializer.validated_data
                if values["action"] == "accept":
                    accept_enrichment_candidate(
                        candidate,
                        actor=request.user,
                        reason=values.get("reason", ""),
                    )
                else:
                    reject_enrichment_candidate(
                        candidate,
                        actor=request.user,
                        reason=values.get("reason", ""),
                    )
        except EnrichmentCandidate.DoesNotExist:
            return Response({"detail": "候选不存在。"}, status=404)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        candidate.refresh_from_db()
        return Response(EnrichmentCandidateSerializer(candidate).data)


class AdminCandidateReviewView(APIView):
    """Shared review envelope for domain-specific candidate models."""

    permission_classes = [CanViewEvidence]

    def get(self, request):
        status_filter = str(request.query_params.get("status") or "pending").strip()
        kind = str(request.query_params.get("kind") or "all").strip()
        entity_filter = str(request.query_params.get("entity") or "").strip()
        work_filter = str(request.query_params.get("work") or "").strip()
        source_filter = str(request.query_params.get("source") or "").strip()
        try:
            limit = max(1, min(int(request.query_params.get("limit") or 200), 500))
        except (TypeError, ValueError):
            limit = 200
        rows = []
        kind_counts = {"field_enrichment": 0, "query_lexicon": 0, "new_authority": 0, "metadata": 0, "theory": 0}
        if kind in {"all", "field_enrichment"}:
            queryset = EnrichmentCandidate.objects.prefetch_related("evidence_records")
            if status_filter != "all":
                queryset = queryset.filter(status=status_filter)
            if entity_filter:
                queryset = queryset.filter(target_type=entity_filter)
            if source_filter:
                queryset = queryset.filter(source_class=source_filter)
            kind_counts["field_enrichment"] = queryset.count()
            for row in queryset.order_by("-confidence", "created_at")[:limit]:
                payload = EnrichmentCandidateSerializer(row).data
                payload["review_kind"] = "field_enrichment"
                payload["target_label"] = f"{row.target_type}:{row.target_id}"
                _with_review_status(payload)
                rows.append(payload)
        if kind in {"all", "query_lexicon"}:
            queryset = QueryLexiconCandidate.objects.prefetch_related(
                "evidence_records__work"
            )
            if status_filter != "all":
                queryset = queryset.filter(status=status_filter)
            if entity_filter:
                queryset = queryset.filter(target_entity_type=entity_filter)
            if source_filter:
                queryset = queryset.filter(source_kind=source_filter)
            kind_counts["query_lexicon"] = queryset.count()
            rows.extend(
                QueryLexiconCandidateReviewSerializer(
                    queryset.order_by("-confidence", "created_at")[:limit],
                    many=True,
                ).data
            )
        if kind in {"all", "new_authority"}:
            queryset = NewAuthorityCandidate.objects.prefetch_related(
                "observations__work",
            )
            values = _status_filter_values("new_authority", status_filter)
            if values is not None:
                queryset = queryset.filter(status__in=values)
            if work_filter:
                queryset = queryset.filter(observations__work_id=work_filter)
            kind_counts["new_authority"] = queryset.distinct().count()
            for row in queryset.order_by("-confidence", "created_at").distinct()[:limit]:
                payload = NewAuthorityCandidateSerializer(row).data
                payload["target_label"] = row.primary_term
                payload["proposed_term"] = row.primary_term
                payload["candidate_kind"] = "new_authority"
                payload["evidence_count"] = row.observations.filter(is_current=True).count()
                payload["independent_source_count"] = row.observations.filter(
                    is_current=True,
                ).values("work_id").distinct().count()
                _with_review_status(payload)
                rows.append(payload)
        if kind in {"all", "metadata"}:
            queryset = MetadataCandidate.objects.select_related("upload_item__edition__work").prefetch_related("evidence_records")
            values = _status_filter_values("metadata", status_filter)
            if values is not None:
                queryset = queryset.filter(lifecycle__in=values)
            if work_filter:
                queryset = queryset.filter(upload_item__edition__work_id=work_filter)
            if source_filter:
                queryset = queryset.filter(source=source_filter)
            kind_counts["metadata"] = queryset.count()
            for row in queryset.order_by("-confidence", "created_at")[:limit]:
                rows.append(
                    _with_review_status({
                        "id": str(row.id),
                        "review_kind": "metadata",
                        "candidate_kind": "metadata",
                        "target_label": row.field_name,
                        "target_entity_type": "work" if row.upload_item.edition_id else "upload_item",
                        "target_entity_id": str(row.upload_item.edition.work_id) if row.upload_item.edition_id else str(row.upload_item_id),
                        "proposed_value": row.value,
                        "current_value": None,
                        "source_class": row.source,
                        "confidence": row.confidence,
                        "status": row.lifecycle,
                        "evidence_count": row.evidence_records.count(),
                        "independent_source_count": row.evidence_records.values("source_record_id").distinct().count(),
                        "review_action": "open_intake_workspace",
                        "upload_item_id": str(row.upload_item_id),
                        "work_id": str(row.upload_item.edition.work_id) if row.upload_item.edition_id else None,
                        "created_at": row.created_at,
                    })
                )
        if kind in {"all", "theory", "relation", "timeline"}:
            tasks = TheoryReviewTask.objects.select_related("work", "candidate_node", "file")
            values = _status_filter_values("theory", status_filter)
            if values is not None:
                tasks = tasks.filter(status__in=values)
            if work_filter:
                tasks = tasks.filter(work_id=work_filter)
            kind_counts["theory"] = tasks.count()
            for row in tasks.order_by("-confidence", "created_at")[:limit]:
                rows.append(
                    _with_review_status({
                        "id": str(row.id),
                        "review_kind": "theory",
                        "candidate_kind": row.task_type,
                        "target_label": row.suggested_node_name or (row.candidate_node.canonical_name_zh if row.candidate_node else ""),
                        "target_entity_type": "knowledge_node",
                        "target_entity_id": str(row.candidate_node_id) if row.candidate_node_id else None,
                        "proposed_value": {"relation_type": row.suggested_relation_type, "name": row.suggested_node_name},
                        "source_class": "pdf_evidence",
                        "confidence": row.confidence,
                        "status": row.status,
                        "evidence_count": 1 if row.evidence_text else 0,
                        "independent_source_count": 1 if row.file_id else 0,
                        "review_action": "open_theory_review",
                        "work_id": str(row.work_id) if row.work_id else None,
                        "created_at": row.created_at,
                    })
                )
        rows.sort(
            key=lambda row: (
                -float(row.get("confidence") or 0),
                str(row.get("created_at") or ""),
            )
        )
        total_count = sum(kind_counts.values())
        return Response(
            {
                "results": rows[:limit],
                "status": status_filter,
                "kind": kind,
                "limit": limit,
                "returned_count": min(len(rows), limit),
                "truncated": total_count > limit,
                "counts": {
                    "total": total_count,
                    **kind_counts,
                },
            }
        )


class AdminCandidateReviewDecisionView(APIView):
    permission_classes = [CanReviewCandidateOrCreateAuthority]

    def post(self, request, candidate_kind, candidate_id):
        serializer = EnrichmentDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")
        allowed_actions = {
            "field_enrichment": {"accept", "reject"},
            "query_lexicon": {"accept", "reject"},
            "new_authority": {"match_existing", "create_draft", "reject"},
        }
        if candidate_kind not in allowed_actions:
            return Response(
                {"detail": "该候选类型只能在其专用审核页面处理。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if action not in allowed_actions[candidate_kind]:
            return Response(
                {"detail": f"{candidate_kind} 不支持 {action} 审核动作。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                if candidate_kind == "field_enrichment":
                    candidate = EnrichmentCandidate.objects.select_for_update().get(
                        pk=candidate_id
                    )
                    if action == "accept":
                        accept_enrichment_candidate(candidate, actor=request.user, reason=reason)
                    else:
                        reject_enrichment_candidate(candidate, actor=request.user, reason=reason)
                    candidate.refresh_from_db()
                    payload = EnrichmentCandidateSerializer(candidate).data
                    payload["review_kind"] = "field_enrichment"
                elif candidate_kind == "query_lexicon":
                    candidate = QueryLexiconCandidate.objects.select_for_update().get(
                        pk=candidate_id
                    )
                    if action == "accept":
                        accept_query_lexicon_candidate(candidate, actor=request.user, reason=reason)
                    else:
                        reject_query_lexicon_candidate(candidate, actor=request.user, reason=reason)
                    candidate.refresh_from_db()
                    payload = QueryLexiconCandidateReviewSerializer(candidate).data
                elif candidate_kind == "new_authority":
                    candidate = NewAuthorityCandidate.objects.select_for_update().get(
                        pk=candidate_id,
                    )
                    values = serializer.validated_data
                    candidate = decide_new_authority_candidate(
                        candidate,
                        action=action,
                        actor=request.user,
                        target_type=values.get("target_type", ""),
                        target_id=str(values.get("target_id") or ""),
                        canonical_term=values.get("canonical_term", ""),
                        node_type=values.get("node_type", "theory_tradition"),
                        confirm_new=values.get("confirm_new", False),
                        reason=reason,
                    )
                    payload = NewAuthorityCandidateSerializer(candidate).data
                    payload["target_label"] = candidate.primary_term
                    _with_review_status(payload)
                else:
                    return Response({"detail": "不支持的候选类型。"}, status=400)
        except (
            EnrichmentCandidate.DoesNotExist,
            QueryLexiconCandidate.DoesNotExist,
            NewAuthorityCandidate.DoesNotExist,
        ):
            return Response({"detail": "候选不存在。"}, status=404)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(payload)


class AdminNewAuthorityCandidateView(APIView):
    permission_classes = [CanViewEvidence]

    def get(self, request):
        queryset = NewAuthorityCandidate.objects.prefetch_related("observations__work")
        status_filter = str(request.query_params.get("status") or "pending").strip()
        entity_type = str(request.query_params.get("entity_type") or "").strip()
        if status_filter != "all":
            queryset = queryset.filter(
                status=(
                    NewAuthorityCandidate.Status.PENDING
                    if status_filter == "pending"
                    else status_filter
                )
            )
        if entity_type:
            queryset = queryset.filter(entity_type=entity_type)
        rows = NewAuthorityCandidateSerializer(
            queryset.order_by("-confidence", "created_at")[:200],
            many=True,
        ).data
        return Response(
            {
                "results": rows,
                "status": status_filter,
                "counts": {
                    "total": len(rows),
                    "pending": sum(row["status"] == NewAuthorityCandidate.Status.PENDING for row in rows),
                },
            }
        )
