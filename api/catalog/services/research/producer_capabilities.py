from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field as dataclass_field
from typing import Iterable

from .contracts import (
    RESEARCH_CONTRACTS,
    ResearchFieldContract,
    ResearchImplementation,
)
from .entity_discovery import SUPPORTED_ENTITY_TYPES
from .task_profiles import builtin_task_profile, profile_key_for_contract


FIELD_PRODUCER_CAPABILITY_MATRIX_VERSION = "field-producer-capability-matrix-v1"


class ProducerState:
    PRODUCTIVE = "productive"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


PRODUCER_CHANNELS = (
    "pdf_native",
    "ocr",
    "local_catalog",
    "authority",
    "structured_provider",
    "verified_web",
    "ai_synthesis",
)


@dataclass(frozen=True, slots=True)
class FieldProducerCapability:
    step: str
    field: str
    canonical_field: str
    implementation: str
    producer: str
    persistence_models: tuple[str, ...]
    decision_adapter: str
    required_capability: str
    state: str
    reason: str
    channels: dict[str, dict[str, object]] = dataclass_field(default_factory=dict)
    version: str = FIELD_PRODUCER_CAPABILITY_MATRIX_VERSION

    def payload(self) -> dict[str, object]:
        value = asdict(self)
        value["persistence_models"] = list(self.persistence_models)
        return value


def _channel(state: str, reason: str, sources: Iterable[str] = ()) -> dict[str, object]:
    return {
        "state": state,
        "reason": reason,
        "sources": list(sources),
    }


def _producer_channels(contract: ResearchFieldContract) -> dict[str, dict[str, object]]:
    unavailable = {
        key: _channel(
            ProducerState.UNAVAILABLE,
            "该字段没有注册此类 producer。",
        )
        for key in PRODUCER_CHANNELS
    }
    if not contract.research_enabled:
        return {
            key: _channel(
                ProducerState.UNAVAILABLE,
                "ResearchFieldContract 已明确禁用自动研究。",
            )
            for key in PRODUCER_CHANNELS
        }

    document_sources = set(contract.document_sources)
    document_direct = (
        contract.implementation == ResearchImplementation.FIELD_ENRICHMENT
        and contract.step in {"work", "bibliography", "contributors"}
    )
    if document_sources & {"native_text", "front_matter", "evidence_span"}:
        unavailable["pdf_native"] = _channel(
            ProducerState.PRODUCTIVE if document_direct else ProducerState.DEGRADED,
            "" if document_direct else "PDF Evidence 可进入 ResearchContext，但该字段仍需专业候选 producer。",
            sorted(document_sources & {"native_text", "front_matter", "evidence_span"}),
        )
    if "selective_ocr" in document_sources:
        unavailable["ocr"] = _channel(
            ProducerState.PRODUCTIVE if document_direct else ProducerState.DEGRADED,
            "" if document_direct else "OCR 可补充 EvidenceSpan，是否形成候选仍由字段 producer 决定。",
            ("selective_ocr",),
        )
    if contract.local_catalog_sources:
        unavailable["local_catalog"] = _channel(
            ProducerState.PRODUCTIVE,
            "",
            contract.local_catalog_sources,
        )
    if contract.authority_providers:
        unavailable["authority"] = _channel(
            ProducerState.DEGRADED,
            "Provider 已注册，实际产出取决于当前配置、健康与字段适用性。",
            contract.authority_providers,
        )
    if contract.implementation == ResearchImplementation.FIELD_ENRICHMENT and contract.source_classes:
        unavailable["structured_provider"] = _channel(
            ProducerState.PRODUCTIVE,
            "",
            contract.source_classes,
        )
    elif contract.authority_providers:
        unavailable["structured_provider"] = _channel(
            ProducerState.DEGRADED,
            "结构化来源可参与发现，但采用仍由当前实体或策展决定协议约束。",
            contract.authority_providers,
        )
    if "safe_web_fetcher" in contract.external_providers:
        unavailable["verified_web"] = _channel(
            ProducerState.DEGRADED,
            "搜索结果必须成功抓取正文并形成 Evidence 后才可采用。",
            contract.external_providers,
        )

    field_key = f"{contract.step}.{contract.field}"
    if field_key in {
        "work.abstract",
        "curation.core_viewpoints",
        "curation.major_criticisms",
        "curation.major_responses",
    }:
        unavailable["ai_synthesis"] = _channel(
            ProducerState.DEGRADED,
            "Evidence-only 任务已注册；没有匹配 executor 时安全等待且不阻塞发布。",
            ("library_synthesis", contract.research_task_profile),
        )
    return unavailable


def _required_capability(contract: ResearchFieldContract) -> str:
    if not contract.research_enabled:
        return ""
    profile_key = contract.research_task_profile or profile_key_for_contract(
        step=contract.step,
        field=contract.field,
        implementation=contract.implementation,
    )
    try:
        return builtin_task_profile(profile_key).required_capability
    except ValueError:
        return ""


def _field_enrichment_capability(contract: ResearchFieldContract) -> FieldProducerCapability:
    reason = ""
    state = ProducerState.PRODUCTIVE
    try:
        from catalog.services.field_enrichment.policies import FIELD_POLICIES

        FIELD_POLICIES.get(str(contract.target_type), contract.enrichment_field)
    except (ImportError, ValueError) as exc:
        state = ProducerState.UNAVAILABLE
        reason = f"FieldPolicy 未注册：{exc.__class__.__name__}。"
    return FieldProducerCapability(
        step=contract.step,
        field=contract.field,
        canonical_field=contract.canonical_field,
        implementation=contract.implementation,
        producer="catalog.services.field_enrichment.FieldEnrichmentService",
        persistence_models=("EnrichmentCandidate", "EnrichmentEvidence"),
        decision_adapter="field_enrichment_candidate",
        required_capability=_required_capability(contract),
        state=state,
        reason=reason,
        channels=_producer_channels(contract),
    )


def _entity_discovery_capability(contract: ResearchFieldContract) -> FieldProducerCapability:
    unsupported = sorted(
        {
            "organization" if value == "institution" else value
            for value in contract.entity_types
            if value not in SUPPORTED_ENTITY_TYPES
        }
    )
    state = ProducerState.UNAVAILABLE if unsupported else ProducerState.PRODUCTIVE
    reason = f"未注册的实体类型：{', '.join(unsupported)}。" if unsupported else ""
    return FieldProducerCapability(
        step=contract.step,
        field=contract.field,
        canonical_field=contract.canonical_field,
        implementation=contract.implementation,
        producer="catalog.services.research.entity_discovery.UniversalEntityDiscovery",
        persistence_models=("EntityResolutionCandidate",),
        decision_adapter="entity_resolution_candidate",
        required_capability=_required_capability(contract),
        state=state,
        reason=reason,
        channels=_producer_channels(contract),
    )


def _editorial_discovery_capability(contract: ResearchFieldContract) -> FieldProducerCapability:
    return FieldProducerCapability(
        step=contract.step,
        field=contract.field,
        canonical_field=contract.canonical_field,
        implementation=contract.implementation,
        producer="catalog.services.research.entity_discovery.UniversalEntityDiscovery",
        persistence_models=("EntityResolutionCandidate",),
        decision_adapter="entity_resolution_candidate",
        required_capability=_required_capability(contract),
        state=ProducerState.DEGRADED,
        reason=(
            "当前 producer 可发现已有 ReadingPath 和相关实体，"
            "但尚不产生完整 ReadingPathCandidate。"
        ),
        channels=_producer_channels(contract),
    )


def _evidence_only_capability(contract: ResearchFieldContract) -> FieldProducerCapability:
    if contract.step == "curation" and contract.field in {
        "core_viewpoints",
        "major_criticisms",
        "major_responses",
    }:
        return FieldProducerCapability(
            step=contract.step,
            field=contract.field,
            canonical_field=contract.canonical_field,
            implementation=contract.implementation,
            producer="catalog.services.claims.curation.high_value_claim_candidates",
            persistence_models=("DerivedClaim", "ClaimEvidence", "CuratedClaim"),
            decision_adapter="derived_claim_curation",
            required_capability=_required_capability(contract),
            state=ProducerState.DEGRADED,
            reason=(
                "高价值 Claim producer 已存在，但当前 ResearchOrchestrator "
                "尚未把其结果纳入该字段的 editorial_evidence。"
            ),
            channels=_producer_channels(contract),
        )
    if contract.step == "curation" and contract.field == "recommendation_reason":
        return FieldProducerCapability(
            step=contract.step,
            field=contract.field,
            canonical_field=contract.canonical_field,
            implementation=contract.implementation,
            producer="catalog.services.workflow_suggestions.WorkflowSuggestionAggregator.run_step",
            persistence_models=("SemanticChunk", "EnrichmentCandidate"),
            decision_adapter="read_only_evidence",
            required_capability=_required_capability(contract),
            state=ProducerState.PRODUCTIVE,
            reason="",
            channels=_producer_channels(contract),
        )
    return FieldProducerCapability(
        step=contract.step,
        field=contract.field,
        canonical_field=contract.canonical_field,
        implementation=contract.implementation,
        producer="",
        persistence_models=(),
        decision_adapter="",
        required_capability=_required_capability(contract),
        state=ProducerState.UNAVAILABLE,
        reason="当前 Evidence-only 字段没有已注册 producer。",
        channels=_producer_channels(contract),
    )


def capability_for_contract(contract: ResearchFieldContract) -> FieldProducerCapability:
    if not contract.research_enabled:
        return FieldProducerCapability(
            step=contract.step,
            field=contract.field,
            canonical_field=contract.canonical_field,
            implementation=contract.implementation,
            producer="",
            persistence_models=(),
            decision_adapter="",
            required_capability="",
            state=ProducerState.UNAVAILABLE,
            reason="该字段由业务状态决定，ResearchFieldContract 已明确禁用自动研究。",
            channels=_producer_channels(contract),
        )
    if contract.implementation == ResearchImplementation.FIELD_ENRICHMENT:
        return _field_enrichment_capability(contract)
    if contract.implementation == ResearchImplementation.ENTITY_DISCOVERY:
        return _entity_discovery_capability(contract)
    if contract.implementation == ResearchImplementation.EDITORIAL_DISCOVERY:
        return _editorial_discovery_capability(contract)
    if contract.implementation == ResearchImplementation.EVIDENCE_ONLY:
        return _evidence_only_capability(contract)
    return FieldProducerCapability(
        step=contract.step,
        field=contract.field,
        canonical_field=contract.canonical_field,
        implementation=contract.implementation,
        producer="",
        persistence_models=(),
        decision_adapter="",
        required_capability=_required_capability(contract),
        state=ProducerState.UNAVAILABLE,
        reason=f"未注册的 Research implementation：{contract.implementation}。",
        channels=_producer_channels(contract),
    )


def producer_capability_matrix(
    contracts: Iterable[ResearchFieldContract] | None = None,
) -> list[dict[str, object]]:
    selected = tuple(contracts) if contracts is not None else RESEARCH_CONTRACTS.all()
    return [capability_for_contract(contract).payload() for contract in selected]


def producer_capability_coverage() -> dict[str, object]:
    contracts = RESEARCH_CONTRACTS.all()
    rows = [capability_for_contract(contract) for contract in contracts]
    enabled = [
        row
        for row, contract in zip(rows, contracts, strict=True)
        if contract.research_enabled
    ]
    counts = Counter(row.state for row in rows)
    unavailable = [f"{row.step}.{row.field}" for row in enabled if row.state == ProducerState.UNAVAILABLE]
    degraded = [f"{row.step}.{row.field}" for row in enabled if row.state == ProducerState.DEGRADED]
    return {
        "version": FIELD_PRODUCER_CAPABILITY_MATRIX_VERSION,
        "contract_count": len(rows),
        "states": dict(counts),
        "degraded_fields": degraded,
        "unavailable_enabled_fields": unavailable,
        "healthy": not unavailable,
    }
