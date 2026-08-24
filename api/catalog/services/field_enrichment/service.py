from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from hashlib import sha256
import logging
import time
from uuid import uuid4

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Discipline,
    EnrichmentCandidate,
    EnrichmentEvidence,
    EnrichmentSourceClass,
    KnowledgeNode,
    Subdiscipline,
)

from .extraction import extract_web_observations
from .identity import assess_identity
from .policies import FIELD_POLICIES, FieldPolicy
from .structured import STRUCTURED_ADAPTERS
from .targets import current_field_value, get_target, target_context
from .types import EnrichmentError, EnrichmentResult, FieldEnrichmentRequest, FieldObservation
from .values import (
    candidate_identity_value,
    normalize_candidate_value,
    normalize_json,
    stable_json,
)
from .web import SafeWebFetcher, WebSearchError, search_and_fetch


logger = logging.getLogger(__name__)


def _digest(*values) -> str:
    return sha256("\x1f".join(stable_json(value) for value in values).encode("utf-8")).hexdigest()


def _request_context(value: dict) -> dict:
    allowed = {
        "language",
        "related_entity_ids",
        "target_node_id",
        "related_entity_name",
        "relation_type",
        "proposed_value",
        "current_value",
        "node_id",
        "work_id",
        "research_run_id",
        "research_context_fingerprint",
        "research_draft_session_id",
        "research_draft_hash",
        "research_trigger_input_hash",
        "is_current_context",
    }
    return normalize_json({key: value[key] for key in allowed if key in value})


def _value_exists(current, value, field_name: str) -> bool:
    current = normalize_json(current)
    value = normalize_json(value)
    if field_name == "external_identifier" and isinstance(current, dict) and isinstance(value, dict):
        return str(current.get(value.get("scheme")) or "").casefold() == str(value.get("value") or "").casefold()
    if field_name == "affiliation" and isinstance(current, list) and isinstance(value, dict):
        proposed = str(value.get("name") or "").casefold()
        return any(
            str(row.get("name") if isinstance(row, dict) else row).casefold() == proposed
            for row in current
        )
    if field_name in {"name_variant", "alias"} and isinstance(current, list) and isinstance(value, dict):
        key = "name" if field_name == "name_variant" else "alias"
        proposed = str(value.get(key) or "").casefold()
        return any(
            str(row.get(key) if isinstance(row, dict) else row).casefold() == proposed
            for row in current
        )
    if field_name == "relation" and isinstance(current, list) and isinstance(value, dict):
        return any(
            str(row.get("target_node_id") or "") == str(value.get("target_node_id") or "")
            and str(row.get("relation_type") or "") == str(value.get("relation_type") or "")
            for row in current
            if isinstance(row, dict)
        )
    if field_name == "discipline" and isinstance(current, list) and isinstance(value, dict):
        return any(
            str(row.get("discipline_id") or "") == str(value.get("discipline_id") or "")
            for row in current
            if isinstance(row, dict)
        )
    if field_name == "subdiscipline" and isinstance(current, list) and isinstance(value, dict):
        target_id = value.get("subdiscipline_node_id")
        return any(
            str(row.get("subdiscipline_id") or row.get("subdiscipline_node_id") or "") == str(target_id or "")
            for row in current
            if isinstance(row, dict)
        )
    if isinstance(current, list):
        return any(stable_json(row) == stable_json(value) for row in current)
    return stable_json(current) == stable_json(value)


def _confidence(policy: FieldPolicy, observation: FieldObservation, identity_status: str) -> tuple[float, dict]:
    priority = policy.priority_for(observation.source_class)
    source_component = min(0.36, max(0, priority) / 280)
    identity_component = 0.12 if identity_status == EnrichmentCandidate.IdentityStatus.CONFIRMED else 0
    structured_component = 0.05 if observation.extraction_method == "structured_provider" else 0
    explicit_component = 0.06 if observation.confidence_factors.get("explicit_bilingual_pair") or observation.confidence_factors.get("explicit_relation_phrase") else 0
    base = 0.35
    value = round(min(0.98, base + source_component + identity_component + structured_component + explicit_component), 4)
    return value, {
        "base": base,
        "field_source_priority": priority,
        "source_component": round(source_component, 4),
        "identity_component": identity_component,
        "structured_component": structured_component,
        "explicit_evidence_component": explicit_component,
        "observation": observation.confidence_factors,
        "final": value,
    }


def _evidence_fingerprint(candidate_fingerprint: str, observation: FieldObservation) -> str:
    return _digest(
        candidate_fingerprint,
        observation.canonical_url,
        observation.content_checksum,
        observation.supporting_text,
        observation.locator,
    )


def _candidate_conflict_group(target_type: str, target_id, field_name: str) -> str:
    return _digest(target_type, str(target_id), field_name)[:64]


def _enrich_form_context(target_type: str, form_context: dict) -> dict:
    context = dict(form_context or {})
    if target_type in {"work", "knowledge_node", "topic"}:
        context["discipline_options"] = list(
            Discipline.objects.exclude(editorial_status="archived")
            .values("id", "name")[:200]
        )
    if target_type == "work":
        context["subdiscipline_options"] = list(
            Subdiscipline.objects.exclude(editorial_status="archived")
            .values("id", "name")[:200]
        )
    if target_type == "knowledge_node":
        context["subdiscipline_options"] = list(
            KnowledgeNode.objects.filter(
                node_type=KnowledgeNode.NodeType.SUBDISCIPLINE,
                status__in=["draft", "pending", "published"],
            ).values("id", "canonical_name_zh")[:200]
        )
        for row in context["subdiscipline_options"]:
            row["name"] = row.pop("canonical_name_zh")
        target_node_id = str(context.get("target_node_id") or "").strip()
        if target_node_id:
            try:
                related = KnowledgeNode.objects.get(
                    pk=target_node_id,
                    status__in=["draft", "pending", "published"],
                )
            except (KnowledgeNode.DoesNotExist, ValueError) as exc:
                raise ValueError("关系候选的 target KnowledgeNode 不存在或不可审核。") from exc
            context["related_entity_name"] = related.canonical_name_zh or related.canonical_name_en
            context["target_node_id"] = str(related.id)
    return context


def _draft_aware_target_context(target_type: str, context: dict, form_context: dict) -> dict:
    research = form_context.get("research_context")
    if not isinstance(research, dict):
        return context
    draft = research.get("draft_data")
    if not isinstance(draft, dict):
        return context
    section_name = "bibliography" if target_type == "edition" else "work" if target_type == "work" else ""
    section = draft.get(section_name) if section_name else None
    if not isinstance(section, dict):
        return context
    merged = dict(context)
    for field_name in (
        "title", "original_title", "canonical_title", "uniform_title", "language",
        "publication_date", "publication_year", "publisher", "isbn", "isbn10", "isbn13", "doi",
    ):
        if field_name in section and section[field_name] not in (None, ""):
            merged[field_name] = section[field_name]
    if target_type == "edition":
        work_draft = draft.get("work")
        if isinstance(work_draft, dict):
            for field_name in ("title", "original_title", "language", "document_type"):
                if work_draft.get(field_name) not in (None, ""):
                    merged[field_name] = work_draft[field_name]
    canonical = [
        merged.get("title"),
        merged.get("original_title"),
        merged.get("canonical_title"),
        merged.get("uniform_title"),
    ]
    merged["canonical_terms"] = [str(value).strip() for value in canonical if str(value or "").strip()]
    contributors = draft.get("contributors")
    if isinstance(contributors, dict):
        merged["authors"] = [
            str(row.get("display_name") or "").strip()
            for row in contributors.get("items") or []
            if isinstance(row, dict) and str(row.get("display_name") or "").strip()
        ]
    return merged


class FieldEnrichmentService:
    def __init__(self, *, structured_adapters=None, search_adapter=None, fetcher=None):
        self.structured_adapters = structured_adapters or STRUCTURED_ADAPTERS
        self.search_adapter = search_adapter
        self.fetcher = fetcher or SafeWebFetcher()

    def _validate_request(self, request: FieldEnrichmentRequest) -> tuple[tuple[FieldPolicy, ...], object]:
        if request.visibility != "admin":
            raise ValueError("Field enrichment 只允许明确的 admin visibility。")
        if request.requested_mode not in EnrichmentCandidate.RequestedMode.values:
            raise ValueError("requested_mode 必须是 structured、web 或 full。")
        fields = tuple(dict.fromkeys(str(value).strip() for value in request.field_names if str(value).strip()))
        if not fields or len(fields) > 12:
            raise ValueError("每次 enrichment 必须选择 1 至 12 个字段。")
        policies = tuple(FIELD_POLICIES.get(request.target_type, value) for value in fields)
        target = get_target(request.target_type, request.target_id)
        return policies, target

    def _structured_observations(self, *, request, target, policies, context):
        grouped: dict[str, list[FieldPolicy]] = defaultdict(list)
        for policy in policies:
            for adapter in policy.structured_adapters:
                grouped[adapter].append(policy)
        observations = []
        errors = []
        for name, values in grouped.items():
            adapter = self.structured_adapters.get(name)
            if adapter is None:
                errors.append(EnrichmentError(code="provider_unavailable", provider=name, detail="StructuredSourceAdapter 未配置。"))
                continue
            try:
                rows, adapter_errors = adapter.collect(
                    target_type=request.target_type,
                    target=target,
                    policies=tuple(values),
                    context=context,
                )
                observations.extend(rows)
                errors.extend(adapter_errors)
            except (httpx.HTTPError, ValueError, OSError) as exc:
                logger.exception("field enrichment structured adapter failed", extra={"adapter": name, "target_type": request.target_type, "target_id": str(request.target_id)})
                errors.append(EnrichmentError(code="provider_unavailable", provider=name, detail=str(exc)[:300]))
        return observations, errors

    def _web_observations(self, *, request, target, policies, context, form_context):
        web_policies = tuple(policy for policy in policies if policy.allow_general_web)
        if not web_policies:
            return [], [], {"query_count": 0, "fetched_document_count": 0}
        try:
            documents, errors, stats = search_and_fetch(
                context=context,
                policies=web_policies,
                form_context=form_context,
                search_adapter=self.search_adapter,
                fetcher=self.fetcher,
            )
        except WebSearchError as exc:
            return [], [EnrichmentError(code=exc.code, provider="web_search", detail=str(exc))], {"query_count": 0, "fetched_document_count": 0}
        observations = []
        for document in documents:
            for policy in web_policies:
                if document.source_class not in policy.allowed_source_classes:
                    continue
                observations.extend(
                    extract_web_observations(
                        document=document,
                        policy=policy,
                        context=context,
                        form_context=form_context,
                    )
                )
        return observations, errors, stats

    @transaction.atomic
    def _persist(
        self,
        *,
        request: FieldEnrichmentRequest,
        target,
        policies: tuple[FieldPolicy, ...],
        context: dict,
        form_context: dict,
        observations: list[FieldObservation],
        actor,
        request_id,
    ) -> tuple[list[EnrichmentCandidate], list[EnrichmentError], dict]:
        research_run_id = str(form_context.get("research_run_id") or "").strip()
        if research_run_id:
            from catalog.models import ResearchRun

            run_filters = {
                "pk": research_run_id,
                "is_current": True,
                "context_fingerprint": str(form_context.get("research_context_fingerprint") or ""),
                "draft_session_id": str(form_context.get("research_draft_session_id") or ""),
                "draft_hash": str(form_context.get("research_draft_hash") or ""),
                "trigger_input_hash": str(form_context.get("research_trigger_input_hash") or ""),
                "status__in": [ResearchRun.Status.QUEUED, ResearchRun.Status.RUNNING],
            }
            if request.target_type == EnrichmentCandidate.TargetType.WORK:
                run_filters["work_id"] = request.target_id
            elif request.target_type == EnrichmentCandidate.TargetType.EDITION:
                run_filters["edition_id"] = request.target_id
            current_run = ResearchRun.objects.select_for_update(of=("self",)).filter(
                **run_filters,
            ).first()
            if current_run is None or form_context.get("is_current_context") is not True:
                return (
                    [],
                    [
                        EnrichmentError(
                            code="research_context_stale",
                            provider="research_orchestrator",
                            detail="未保存草稿已经变化，迟到结果未写入候选。",
                        )
                    ],
                    {"stale_result_ignored": 1},
                )
        policies_by_field = {policy.field_name: policy for policy in policies}
        current_values = {
            policy.field_name: normalize_json(
                current_field_value(request.target_type, target, policy.field_name)
            )
            for policy in policies
        }
        candidates: dict[object, EnrichmentCandidate] = {}
        errors: list[EnrichmentError] = []
        stats = defaultdict(int)
        for observation in observations:
            policy = policies_by_field.get(observation.field_name)
            if policy is None:
                continue
            stats["observation_count"] += 1
            if observation.extraction_method == "search_snippet":
                stats["snippet_rejected"] += 1
                continue
            if not observation.supporting_text.strip() or not observation.canonical_url:
                stats["evidence_missing"] += 1
                continue
            if observation.source_class not in policy.allowed_source_classes:
                stats["source_class_rejected"] += 1
                continue
            try:
                normalized_value = normalize_candidate_value(
                    policy.mutation_adapter,
                    observation.value,
                )
            except ValueError as exc:
                stats["invalid_value"] += 1
                errors.append(
                    EnrichmentError(
                        code="invalid_source",
                        field_name=policy.field_name,
                        provider=observation.provider,
                        detail=str(exc),
                    )
                )
                continue
            if _value_exists(current_values[policy.field_name], normalized_value, policy.field_name):
                stats["existing_authority_value"] += 1
                continue
            identity = assess_identity(
                target_type=request.target_type,
                target=target,
                observation=observation,
                context=context,
                required=policy.requires_identity,
            )
            if identity.status not in {
                EnrichmentCandidate.IdentityStatus.CONFIRMED,
                EnrichmentCandidate.IdentityStatus.NOT_REQUIRED,
            }:
                stats[f"identity_{identity.status}"] += 1
                errors.append(
                    EnrichmentError(
                        code=f"identity_{identity.status}",
                        field_name=policy.field_name,
                        provider=observation.provider,
                        detail="来源记录未通过 target identity gate。",
                    )
                )
                continue
            fingerprint = _digest(
                request.target_type,
                str(request.target_id),
                policy.field_name,
                candidate_identity_value(policy.mutation_adapter, normalized_value),
                policy.policy_version,
                str(form_context.get("research_context_fingerprint") or ""),
            )
            confidence, confidence_factors = _confidence(
                policy,
                observation,
                identity.status,
            )
            defaults = {
                "target_type": request.target_type,
                "target_id": request.target_id,
                "field_name": policy.field_name,
                "candidate_kind": policy.candidate_kind,
                "proposed_value": normalized_value,
                "normalized_value": normalized_value,
                "current_value": current_values[policy.field_name],
                "request_context": _request_context(form_context),
                "source_class": observation.source_class,
                "confidence": confidence,
                "confidence_factors": confidence_factors,
                "identity_status": identity.status,
                "identity_evidence": identity.evidence,
                "requested_mode": request.requested_mode,
                "request_id": request_id,
                "conflict_group": _candidate_conflict_group(
                    request.target_type, request.target_id, policy.field_name
                ),
                "policy_version": policy.policy_version,
                "extraction_version": policy.extraction_version,
                "refresh_after": observation.retrieved_at + timedelta(seconds=policy.refresh_seconds),
                "created_by": actor,
            }
            candidate, created = EnrichmentCandidate.objects.get_or_create(
                fingerprint=fingerprint,
                defaults=defaults,
            )
            if created:
                stats["candidate_created"] += 1
            elif candidate.status == EnrichmentCandidate.Status.PENDING:
                if confidence > candidate.confidence:
                    candidate.source_class = observation.source_class
                    candidate.confidence = confidence
                    candidate.confidence_factors = confidence_factors
                candidate.request_id = request_id
                candidate.requested_mode = request.requested_mode
                candidate.request_context = _request_context(form_context)
                candidate.refresh_after = max(
                    filter(None, [candidate.refresh_after, defaults["refresh_after"]])
                )
                candidate.save(
                    update_fields=[
                        "source_class",
                        "confidence",
                        "confidence_factors",
                        "request_id",
                        "requested_mode",
                        "request_context",
                        "refresh_after",
                        "updated_at",
                    ]
                )
                stats["candidate_reused"] += 1
            else:
                stats[f"candidate_{candidate.status}_preserved"] += 1
            old_evidence = candidate.evidence_records.filter(
                canonical_url=observation.canonical_url,
                is_current=True,
            ).exclude(content_checksum=observation.content_checksum)
            if old_evidence.exists():
                old_evidence.update(is_current=False, superseded_at=timezone.now(), updated_at=timezone.now())
            evidence_fingerprint = _evidence_fingerprint(fingerprint, observation)
            _evidence, evidence_created = EnrichmentEvidence.objects.get_or_create(
                candidate=candidate,
                fingerprint=evidence_fingerprint,
                defaults={
                    "source_record_id": observation.source_record_id,
                    "source_url": observation.source_url,
                    "canonical_url": observation.canonical_url,
                    "source_title": observation.source_title,
                    "source_domain": observation.canonical_url.split("/", 3)[2][:255],
                    "source_class": observation.source_class,
                    "provider": observation.provider,
                    "external_identifier": observation.external_identifier,
                    "supporting_text": observation.supporting_text[:4000],
                    "locator": normalize_json(observation.locator),
                    "retrieved_at": observation.retrieved_at,
                    "http_status": observation.http_status,
                    "content_type": observation.content_type,
                    "content_checksum": observation.content_checksum,
                    "entity_match_evidence": identity.evidence,
                    "extraction_method": observation.extraction_method,
                    "extraction_version": policy.extraction_version,
                    "confidence": confidence,
                    "is_current": True,
                },
            )
            stats["evidence_created" if evidence_created else "evidence_reused"] += 1
            candidates[candidate.id] = candidate
        affected_groups = {
            candidate.conflict_group
            for candidate in candidates.values()
        }
        for group in affected_groups:
            rows = list(
                EnrichmentCandidate.objects.filter(
                    conflict_group=group,
                    status=EnrichmentCandidate.Status.PENDING,
                ).prefetch_related("evidence_records")
            )
            distinct_values = {stable_json(row.normalized_value) for row in rows}
            for row in rows:
                conflicts = []
                for other in rows:
                    if other.pk == row.pk or stable_json(other.normalized_value) == stable_json(row.normalized_value):
                        continue
                    conflicts.append(
                        {
                            "candidate_id": str(other.id),
                            "value": other.proposed_value,
                            "source_class": other.source_class,
                        }
                    )
                if len(distinct_values) > 1 and stable_json(row.current_value) not in {"null", "{}", "[]", '""'}:
                    conflicts.append({"kind": "current_authority_value", "value": row.current_value})
                row.conflicts = conflicts
                evidence = row.evidence_records.filter(is_current=True)
                values = list(evidence.values_list("confidence", flat=True))
                if values:
                    source_count = evidence.values("canonical_url").distinct().count()
                    class_count = evidence.values("source_class").distinct().count()
                    row.confidence = round(min(0.99, max(values) + min(0.08, 0.02 * (source_count - 1)) + min(0.05, 0.025 * (class_count - 1))), 4)
                    row.confidence_factors = {
                        **(row.confidence_factors or {}),
                        "evidence_count": evidence.count(),
                        "independent_source_count": source_count,
                        "source_class_count": class_count,
                        "final": row.confidence,
                    }
                row.save(update_fields=["conflicts", "confidence", "confidence_factors", "updated_at"])
        refreshed = list(
            EnrichmentCandidate.objects.filter(pk__in=candidates)
            .prefetch_related("evidence_records")
            .order_by("-confidence", "created_at")
        )
        return refreshed, errors, dict(stats)

    def enrich(self, request: FieldEnrichmentRequest, *, actor=None) -> EnrichmentResult:
        started = time.perf_counter()
        policies, target = self._validate_request(request)
        submitted_context = dict(request.form_context or {})
        if request.current_value is not None:
            submitted_context["current_value"] = normalize_json(request.current_value)
        form_context = _enrich_form_context(request.target_type, submitted_context)
        context = _draft_aware_target_context(
            request.target_type,
            target_context(request.target_type, target),
            form_context,
        )
        request_id = uuid4()
        observations = []
        errors = []
        stats = {
            "structured_adapter_count": 0,
            "query_count": 0,
            "fetched_document_count": 0,
        }
        if request.requested_mode in {
            EnrichmentCandidate.RequestedMode.STRUCTURED,
            EnrichmentCandidate.RequestedMode.FULL,
        }:
            structured, structured_errors = self._structured_observations(
                request=request,
                target=target,
                policies=policies,
                context=context,
            )
            observations.extend(structured)
            errors.extend(structured_errors)
            stats["structured_adapter_count"] = len(
                {name for policy in policies for name in policy.structured_adapters}
            )
        if request.requested_mode in {
            EnrichmentCandidate.RequestedMode.WEB,
            EnrichmentCandidate.RequestedMode.FULL,
        }:
            web, web_errors, web_stats = self._web_observations(
                request=request,
                target=target,
                policies=policies,
                context=context,
                form_context=form_context,
            )
            observations.extend(web)
            errors.extend(web_errors)
            stats.update(web_stats)
        candidates, persistence_errors, persistence_stats = self._persist(
            request=request,
            target=target,
            policies=policies,
            context=context,
            form_context=form_context,
            observations=observations,
            actor=actor,
            request_id=request_id,
        )
        errors.extend(persistence_errors)
        stats.update(persistence_stats)
        stats["candidate_count"] = len(candidates)
        stats["error_count"] = len(errors)
        stats["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        logger.info(
            "field_enrichment_complete target_type=%s target_id=%s fields=%s mode=%s candidates=%s errors=%s latency_ms=%s",
            request.target_type,
            request.target_id,
            ",".join(request.field_names),
            request.requested_mode,
            len(candidates),
            len(errors),
            stats["latency_ms"],
        )
        return EnrichmentResult(
            request_id=request_id,
            candidates=candidates,
            errors=errors,
            stats=stats,
        )

    def verify_source(
        self,
        request: FieldEnrichmentRequest,
        *,
        source_url: str,
        actor=None,
    ) -> EnrichmentResult:
        """Fetch one chosen search lead and persist only field-valid observations."""

        started = time.perf_counter()
        policies, target = self._validate_request(request)
        submitted_context = dict(request.form_context or {})
        if request.current_value is not None:
            submitted_context["current_value"] = normalize_json(request.current_value)
        form_context = _enrich_form_context(request.target_type, submitted_context)
        context = _draft_aware_target_context(
            request.target_type,
            target_context(request.target_type, target),
            form_context,
        )
        document = self.fetcher.fetch(source_url)
        observations: list[FieldObservation] = []
        errors: list[EnrichmentError] = []
        eligible_policies = tuple(
            policy
            for policy in policies
            if policy.allow_general_web
            and document.source_class in policy.allowed_source_classes
        )
        for policy in eligible_policies:
            observations.extend(
                extract_web_observations(
                    document=document,
                    policy=policy,
                    context=context,
                    form_context=form_context,
                )
            )
        if not eligible_policies:
            errors.append(
                EnrichmentError(
                    code="source_class_not_allowed",
                    provider="safe_web_fetch",
                    detail="该来源类型不符合当前字段的 Evidence policy。",
                )
            )
        elif not observations:
            errors.append(
                EnrichmentError(
                    code="no_reliable_candidate",
                    provider="safe_web_fetch",
                    detail="已取得来源正文，但没有提取到符合字段格式和身份要求的可靠候选。",
                )
            )
        request_id = uuid4()
        candidates, persistence_errors, persistence_stats = self._persist(
            request=request,
            target=target,
            policies=policies,
            context=context,
            form_context=form_context,
            observations=observations,
            actor=actor,
            request_id=request_id,
        )
        errors.extend(persistence_errors)
        if observations and not candidates and not any(
            row.code == "no_reliable_candidate" for row in errors
        ):
            errors.append(
                EnrichmentError(
                    code="no_reliable_candidate",
                    provider="safe_web_fetch",
                    detail="正文中的值未通过目标身份或字段证据门槛，未生成可采用候选。",
                )
            )
        stats = {
            **persistence_stats,
            "source_url": document.canonical_url,
            "source_record_id": str(document.source_record_id or ""),
            "fetched_document_count": 1,
            "observation_count": len(observations),
            "candidate_count": len(candidates),
            "error_count": len(errors),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        return EnrichmentResult(
            request_id=request_id,
            candidates=candidates,
            errors=errors,
            stats=stats,
        )
