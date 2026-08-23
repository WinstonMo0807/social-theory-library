from __future__ import annotations

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Edition, ResearchRun, ScholarProfile
from ingestion.models import AuditEvent, EntityResolutionCandidate
from ingestion.serializers import EntityResolutionCandidateSerializer
from ingestion.services.entity_resolution_decisions import (
    ResolutionDecisionError,
    decide_entity_resolution,
)
from catalog.services.research.context import build_research_context
from catalog.services.research.contracts import (
    RESEARCH_CONTRACTS,
    ResearchMutationPolicy,
    contract_payload,
    validate_contract_coverage,
)
from catalog.services.research.entity_discovery import EntityDiscoveryRequest, UniversalEntityDiscovery
from catalog.services.research.orchestrator import (
    INTAKE_REVIEW_TARGETS,
    ResearchOrchestrator,
    research_run_payload,
)
from catalog.services.research.recovery import cancel_research_run
from common.permissions import CanAccessBackOffice, CanRunEnrichment, CanViewEvidence
from ingestion.models import UploadItem


def _request_payload(request) -> dict:
    value = request.data if isinstance(request.data, dict) else {}
    changed = value.get("changed_fields") or []
    if isinstance(changed, str):
        changed = [row.strip() for row in changed.split(",") if row.strip()]
    if not isinstance(changed, (list, tuple)):
        raise ValueError("changed_fields 必须是字符串数组。")
    draft = value.get("draft") or value.get("draft_data") or {}
    if not isinstance(draft, dict):
        raise ValueError("draft 必须是对象。")
    return {
        "active_step": str(value.get("step") or value.get("active_step") or "work").strip().casefold(),
        "draft_data": draft,
        "changed_fields": list(changed),
        "trigger": str(value.get("trigger") or ResearchRun.Trigger.AUTO_LOAD).strip().casefold(),
        "mode": str(value.get("mode") or "full").strip().casefold(),
        "force": bool(value.get("force", False)),
        "include_background": bool(value.get("include_background", False)),
    }


def _requested_edition_id(request):
    body_value = request.data.get("edition_id") if request.method == "POST" and isinstance(request.data, dict) else None
    query_value = request.query_params.get("edition_id") or request.query_params.get("edition")
    if body_value and query_value and str(body_value) != str(query_value):
        raise ValueError("请求中的 Edition 上下文不一致。")
    return body_value or query_value


def _work_edition(work_id, *, edition_id=None):
    queryset = Edition.objects.select_related("work").filter(work_id=work_id)
    if edition_id:
        return get_object_or_404(queryset, pk=edition_id)
    return queryset.order_by("-is_primary", "-publication_year", "-updated_at").first()


def _direct_entity_contract(*, step, field_name, entity_type):
    normalized_step = str(step or "").strip().casefold()
    normalized_field = str(field_name or "").strip()
    normalized_entity_type = str(entity_type or "").strip().casefold()
    if normalized_entity_type == "institution":
        normalized_entity_type = "organization"

    if "." in normalized_field:
        field_step, bare_field = normalized_field.split(".", 1)
        field_step = field_step.strip().casefold()
        if normalized_step and field_step != normalized_step:
            raise ValueError("Entity Discovery 的 step 与 field 前缀不一致。")
        normalized_step = normalized_step or field_step
        normalized_field = bare_field.strip()
    normalized_step = normalized_step or "contributors"
    if not normalized_field or not normalized_entity_type:
        raise ValueError("Entity Discovery 缺少 field 或 entity_type。")

    contract, normalized_entity_type = RESEARCH_CONTRACTS.direct_entity(
        normalized_step,
        normalized_field,
        normalized_entity_type,
    )
    return contract, contract.step, contract.field, normalized_entity_type


def _constrain_direct_discovery_payload(
    payload,
    *,
    contract,
    entity_type,
    allow_decisions: bool,
):
    """Keep a direct picker response inside its exact field contract."""

    expected_field = f"{contract.step}.{contract.field}"
    payload_entity_type = str((payload or {}).get("entity_type") or "").strip().casefold()
    if payload_entity_type == "institution":
        payload_entity_type = "organization"
    if payload_entity_type != entity_type:
        raise ValueError("Entity Discovery 返回了不属于当前字段的实体类型。")
    if str((payload or {}).get("field") or "").strip() != expected_field:
        raise ValueError("Entity Discovery 返回了不属于当前字段的结果。")

    source_results = list((payload or {}).get("results") or [])
    scholar_profiles = {}
    if contract.target_type == "scholar_profile" and entity_type == "person":
        person_ids = [
            str(row.get("entity_id"))
            for row in source_results
            if isinstance(row, dict)
            and row.get("candidate_group") in {"local", "local_draft"}
            and row.get("entity_id")
        ]
        scholar_profiles = {
            str(profile.person_id): profile
            for profile in ScholarProfile.objects.filter(person_id__in=person_ids)
        }

    allow_persistent_decisions = bool(
        allow_decisions
        and contract.mutation_policy == ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION
    )
    results = []
    for source_row in source_results:
        if not isinstance(source_row, dict):
            continue
        row_entity_type = str(source_row.get("entity_type") or "").strip().casefold()
        if row_entity_type == "institution":
            row_entity_type = "organization"
        if row_entity_type != entity_type:
            continue
        row = dict(source_row)
        row["entity_type"] = entity_type
        if (
            contract.target_type == "scholar_profile"
            and row.get("candidate_group") in {"local", "local_draft"}
        ):
            person_id = str(row.get("entity_id") or "")
            profile = scholar_profiles.get(person_id)
            if profile is None:
                continue
            metadata = dict(row.get("metadata") or {})
            metadata["person_id"] = person_id
            row["metadata"] = metadata
            row["entity_id"] = str(profile.id)
        actions = list(dict.fromkeys(str(value).strip() for value in row.get("available_actions") or [] if str(value).strip()))
        if not contract.allow_create_draft:
            actions = [value for value in actions if value != "create_draft"]
        if entity_type not in INTAKE_REVIEW_TARGETS:
            actions = [
                value
                for value in actions
                if value not in {"create_draft", "keep_unresolved", "reject"}
            ]
        if not allow_persistent_decisions:
            actions = [
                value
                for value in actions
                if value not in {"create_draft", "keep_unresolved", "reject"}
            ]
        if contract.output_type == "scalar" and row.get("candidate_group") in {"local", "local_draft"}:
            actions = ["inspect", "use_value"]
        row["available_actions"] = actions or ["inspect"]
        results.append(row)

    counts = {}
    for row in results:
        group = str(row.get("candidate_group") or "unresolved")
        counts[group] = counts.get(group, 0) + 1
    groups = []
    for source_group in (payload or {}).get("groups") or []:
        if not isinstance(source_group, dict):
            continue
        key = str(source_group.get("key") or "")
        if counts.get(key):
            groups.append({**source_group, "count": counts[key]})
    constrained = dict(payload or {})
    constrained["entity_type"] = entity_type
    constrained["field"] = expected_field
    constrained["results"] = results
    constrained["groups"] = groups
    constrained["multiple_candidates"] = len(results) > 1
    return constrained


def _resolve_direct_entity_context(request):
    item_id = request.data.get("item_id")
    work_id = request.data.get("work_id")
    edition_id = request.data.get("edition_id")
    item = None
    if item_id:
        item = get_object_or_404(
            UploadItem.objects.select_related("edition__work"),
            pk=item_id,
        )

    if edition_id:
        queryset = Edition.objects.select_related("work")
        if work_id:
            queryset = queryset.filter(work_id=work_id)
        edition = get_object_or_404(queryset, pk=edition_id)
    elif item is not None and item.edition_id:
        edition = item.edition
    elif work_id:
        edition = _work_edition(work_id)
    else:
        edition = None

    if item is not None:
        if edition is not None and item.edition_id != edition.id:
            raise Http404("UploadItem 与 Edition 不属于同一研究上下文。")
        if work_id and (
            item.edition_id is None
            or str(item.edition.work_id) != str(work_id)
        ):
            raise Http404("UploadItem 与 Work 不属于同一研究上下文。")
    return edition, item


class ResearchPermissionMixin:
    def get_permissions(self):
        return [CanRunEnrichment()] if self.request.method == "POST" else [CanViewEvidence()]


class _ResearchContextView(ResearchPermissionMixin, APIView):
    def resolve_context(self, request, **kwargs):
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        try:
            edition, item = self.resolve_context(request, **kwargs)
            if edition is None:
                return Response(
                    {"detail": "当前项目还没有可研究的 Work/Edition。"},
                    status=status.HTTP_409_CONFLICT,
                )
            values = _request_payload(request)
            run, created = ResearchOrchestrator().prepare(
                edition,
                item=item,
                actor=request.user,
                dispatch=True,
                **values,
            )
        except (RuntimeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = research_run_payload(run, include_context=True)
        payload["created"] = created
        return Response(payload, status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK)

    def get(self, request, *args, **kwargs):
        edition, item = self.resolve_context(request, **kwargs)
        if edition is None:
            return Response(
                {"detail": "当前项目还没有可研究的 Work/Edition。"},
                status=status.HTTP_409_CONFLICT,
            )
        queryset = ResearchRun.objects.filter(edition=edition)
        if item is not None:
            queryset = queryset.filter(upload_item_id=item.id)
        requested_step = str(request.query_params.get("step") or "").strip().casefold()
        if requested_step:
            if not RESEARCH_CONTRACTS.for_step(requested_step):
                return Response(
                    {"detail": "未知的 ResearchRun step。"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(active_step=requested_step)
        run = queryset.order_by("-created_at").first()
        if run is None:
            return Response({"run": None, "status": "not_started"})
        return Response(research_run_payload(run, include_context=False))


class IntakeResearchView(_ResearchContextView):
    def resolve_context(self, request, *, item_id, **kwargs):
        item = get_object_or_404(UploadItem.objects.select_related("edition__work"), pk=item_id)
        edition_id = _requested_edition_id(request)
        if edition_id and (
            item.edition_id is None
            or str(item.edition_id) != str(edition_id)
        ):
            raise Http404("UploadItem 与 Edition 不属于同一研究上下文。")
        return (item.edition, item) if item.edition_id else (None, item)


class WorkResearchView(_ResearchContextView):
    def resolve_context(self, request, *, work_id, **kwargs):
        return (
            _work_edition(
                work_id,
                edition_id=_requested_edition_id(request),
            ),
            None,
        )


class ResearchRunDetailView(ResearchPermissionMixin, APIView):
    def get(self, request, *, run_id):
        run = get_object_or_404(ResearchRun, pk=run_id)
        return Response(research_run_payload(run, include_context=False))

    def post(self, request, *, run_id):
        action = str(request.data.get("action") or "").strip().casefold()
        if action != "cancel":
            return Response({"detail": "ResearchRun 仅支持 cancel 动作。"}, status=status.HTTP_400_BAD_REQUEST)
        get_object_or_404(ResearchRun.objects.only("pk"), pk=run_id)
        transition = cancel_research_run(
            str(run_id),
            actor=request.user,
            request_id=str(request.META.get("HTTP_X_REQUEST_ID") or ""),
        )
        return Response(research_run_payload(transition.run))


class ResearchEntityDiscoveryView(APIView):
    permission_classes = [CanRunEnrichment]

    def get_permissions(self):
        step = str(self.request.data.get("step") or "").strip().casefold()
        has_workflow_context = any(
            self.request.data.get(key)
            for key in ("item_id", "work_id", "edition_id")
        )
        if step.startswith("maintenance_") and not has_workflow_context:
            return [CanAccessBackOffice()]
        return [CanRunEnrichment()]

    def post(self, request):
        query = str(request.data.get("query") or request.data.get("q") or "").strip()
        edition, item = _resolve_direct_entity_context(request)
        try:
            contract, step, field_name, entity_type = _direct_entity_contract(
                step=request.data.get("step"),
                field_name=request.data.get("field"),
                entity_type=request.data.get("entity_type"),
            )
            context = (
                build_research_context(
                    edition,
                    item=item,
                    active_step=step,
                    draft_data=request.data.get("draft") or {},
                    changed_fields=request.data.get("changed_fields") or [],
                )
                if edition is not None
                else None
            )
            payload = UniversalEntityDiscovery().discover(
                EntityDiscoveryRequest(
                    entity_type=entity_type,
                    field=f"{step}.{field_name}",
                    query=query,
                    context=context,
                    include_external=bool(request.data.get("include_external", True)),
                    include_web=bool(request.data.get("include_web", True)),
                    limit=int(request.data.get("limit") or 12),
                )
            )
            payload = _constrain_direct_discovery_payload(
                payload,
                contract=contract,
                entity_type=entity_type,
                allow_decisions=bool(item is not None and item.edition_id),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class ResearchEntityDecisionView(APIView):
    """Turn one verified discovery result into an explicit intake decision."""

    permission_classes = [CanRunEnrichment]

    def post(self, request):
        edition, item = _resolve_direct_entity_context(request)
        if item is None:
            return Response(
                {"detail": "实体决定需要有效 UploadItem 上下文。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if item.edition_id is None:
            return Response(
                {"detail": "当前上架项目尚未建立 Edition，不能执行实体决定。"},
                status=status.HTTP_409_CONFLICT,
            )
        action = str(request.data.get("action") or "").strip().casefold()
        if action not in {"create_draft", "keep_unresolved", "reject"}:
            return Response(
                {"detail": "外部研究候选仅支持 create_draft、keep_unresolved 或 reject。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        candidate_id = str(request.data.get("candidate_id") or "").strip()
        entity_type = str(request.data.get("entity_type") or "").strip().casefold()
        field_name = str(request.data.get("field") or "").strip()
        query = str(request.data.get("query") or "").strip()
        if not candidate_id or not entity_type or not field_name or not query:
            return Response(
                {"detail": "实体决定缺少 candidate_id、entity_type、field 或 query。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            contract, step, field_name, entity_type = _direct_entity_contract(
                step=request.data.get("step"),
                field_name=field_name,
                entity_type=entity_type,
            )
            if contract.mutation_policy != ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION:
                raise ValueError("当前 ResearchFieldContract 仅允许只读实体发现。")
            if action == "create_draft" and not contract.allow_create_draft:
                raise ValueError("当前 ResearchFieldContract 不允许创建 draft entity。")
            context = build_research_context(
                edition,
                item=item,
                active_step=step,
                draft_data=request.data.get("draft") or {},
                changed_fields=request.data.get("changed_fields") or [],
            )
            discovery = UniversalEntityDiscovery().discover(
                EntityDiscoveryRequest(
                    entity_type=entity_type,
                    field=f"{step}.{field_name}",
                    query=query,
                    context=context,
                    include_external=True,
                    include_web=True,
                    limit=int(request.data.get("limit") or 12),
                )
            )
            discovery = _constrain_direct_discovery_payload(
                discovery,
                contract=contract,
                entity_type=entity_type,
                allow_decisions=True,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        row = next(
            (value for value in discovery.get("results") or [] if str(value.get("id")) == candidate_id),
            None,
        )
        if row is None or row.get("candidate_group") not in {"authority", "external_web", "unresolved"}:
            return Response(
                {"detail": "候选已变化或不属于可执行决定的馆外/未解析候选，请刷新后重试。"},
                status=status.HTTP_409_CONFLICT,
            )
        if action not in set(row.get("available_actions") or []):
            return Response(
                {"detail": "当前候选或字段契约不允许该实体决定。"},
                status=status.HTTP_409_CONFLICT,
            )
        group = {**discovery, "results": [row]}
        ResearchOrchestrator._persist_intake_entity_candidates(item=item, groups=[group])
        review_candidate_id = row.get("review_candidate_id")
        if not review_candidate_id:
            return Response(
                {"detail": "当前实体类型只支持展示候选，尚不支持从普通上架流程创建或决定。"},
                status=status.HTTP_409_CONFLICT,
            )
        candidate = get_object_or_404(
            EntityResolutionCandidate.objects.select_related("upload_item__edition"),
            pk=review_candidate_id,
            upload_item=item,
        )
        before = {
            "status": candidate.status,
            "candidate_entity_type": candidate.candidate_entity_type,
            "candidate_entity_id": candidate.candidate_entity_id,
        }
        correlation_id = str(request.META.get("HTTP_X_REQUEST_ID") or "")[:128]
        try:
            result = decide_entity_resolution(
                candidate,
                action=action,
                target_type=candidate.target_type,
                actor=request.user,
                reason=str(request.data.get("reason") or "Research Entity Picker 明确决定。")[:1000],
                correlation_id=correlation_id,
            )
        except ResolutionDecisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        if not result.idempotent:
            AuditEvent.objects.create(
                actor=request.user,
                action=f"research_entity_{action}",
                object_type="EntityResolutionCandidate",
                object_id=str(result.candidate.id),
                before=before,
                after={
                    "status": result.candidate.status,
                    "target_type": result.candidate.target_type,
                    "candidate_entity_type": result.candidate.candidate_entity_type,
                    "candidate_entity_id": result.candidate.candidate_entity_id,
                    "source": "research_entity_discovery",
                },
                request_id=correlation_id,
            )
        return Response({
            "candidate": EntityResolutionCandidateSerializer(result.candidate).data,
            "group": EntityResolutionCandidateSerializer(result.group, many=True).data,
            "idempotent": result.idempotent,
            "action": action,
        })


class ResearchContractView(APIView):
    permission_classes = [CanViewEvidence]

    def get(self, request):
        step = str(request.query_params.get("step") or "").strip().casefold()
        contracts = RESEARCH_CONTRACTS.for_step(step) if step else RESEARCH_CONTRACTS.all()
        return Response({
            "coverage": validate_contract_coverage(),
            "contracts": [contract_payload(row) for row in contracts],
        })
