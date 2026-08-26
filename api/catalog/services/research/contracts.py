from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from catalog.models import EnrichmentCandidate, EnrichmentSourceClass


RESEARCH_CONTRACT_VERSION = "research-field-contract-v2"


class ResearchImplementation:
    FIELD_ENRICHMENT = "field_enrichment"
    ENTITY_DISCOVERY = "entity_discovery"
    EDITORIAL_DISCOVERY = "editorial_discovery"
    EVIDENCE_ONLY = "evidence_only"
    STATUS_ONLY = "status_only"


class ResearchMutationPolicy:
    EXISTING_FIELD_POLICY = "existing_field_policy"
    EXPLICIT_ENTITY_DECISION = "explicit_entity_decision"
    EXPLICIT_EDITORIAL_REVIEW = "explicit_editorial_review"
    NEVER_DIRECT = "never_direct"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ResearchFieldContract:
    step: str
    field: str
    canonical_field: str
    output_type: str
    implementation: str
    target_type: str | None = None
    enrichment_field: str = ""
    entity_types: tuple[str, ...] = ()
    candidate_types: tuple[str, ...] = ()
    source_classes: tuple[str, ...] = ()
    evidence_min_count: int = 0
    independent_source_min: int = 0
    mutation_policy: str = ResearchMutationPolicy.NEVER_DIRECT
    allow_create_draft: bool = False
    allow_direct_use: bool = False
    research_enabled: bool = True
    dependencies: tuple[str, ...] = ()
    description: str = ""
    scope: str = ""
    trigger_inputs: tuple[str, ...] = ()
    dependent_fields: tuple[str, ...] = ()
    local_catalog_sources: tuple[str, ...] = ()
    document_sources: tuple[str, ...] = ()
    authority_providers: tuple[str, ...] = ()
    external_providers: tuple[str, ...] = ()
    research_task_profile: str = ""
    output_schema: dict | None = None
    accept_policy: str = ""
    stale_policy: str = "invalidate_on_trigger_change"
    no_reliable_candidate_reason: str = "证据数量或质量未达到当前字段要求。"
    version: str = RESEARCH_CONTRACT_VERSION

    @property
    def effective_trigger_inputs(self) -> tuple[str, ...]:
        return self.trigger_inputs or self.dependencies


class ResearchFieldContractRegistry:
    def __init__(self):
        self._contracts: dict[tuple[str, str], ResearchFieldContract] = {}

    def register(self, contract: ResearchFieldContract) -> ResearchFieldContract:
        key = (contract.step, contract.field)
        if key in self._contracts:
            raise RuntimeError(f"重复的 ResearchFieldContract：{key[0]}.{key[1]}")
        if contract.research_enabled and contract.implementation == ResearchImplementation.STATUS_ONLY:
            raise RuntimeError(f"状态字段不能声明自动研究：{key[0]}.{key[1]}")
        if contract.research_enabled and contract.implementation not in {
            ResearchImplementation.FIELD_ENRICHMENT,
            ResearchImplementation.ENTITY_DISCOVERY,
            ResearchImplementation.EDITORIAL_DISCOVERY,
            ResearchImplementation.EVIDENCE_ONLY,
        }:
            raise RuntimeError(f"ResearchFieldContract 缺少 implementation：{key[0]}.{key[1]}")
        if contract.implementation == ResearchImplementation.FIELD_ENRICHMENT and not (
            contract.target_type and contract.enrichment_field
        ):
            raise RuntimeError(f"Field Enrichment contract 缺少 target/field：{key[0]}.{key[1]}")
        if contract.implementation == ResearchImplementation.ENTITY_DISCOVERY and not contract.entity_types:
            raise RuntimeError(f"Entity Discovery contract 缺少 entity type：{key[0]}.{key[1]}")
        if contract.allow_direct_use and not contract.entity_types:
            raise RuntimeError(f"Direct Entity contract 缺少 entity type：{key[0]}.{key[1]}")
        self._contracts[key] = contract
        return contract

    def get(self, step: str, field: str) -> ResearchFieldContract:
        key = (str(step or "").strip().casefold(), str(field or "").strip())
        try:
            return self._contracts[key]
        except KeyError as exc:
            raise ValueError(f"缺少 ResearchFieldContract：{key[0]}.{key[1]}") from exc

    def for_step(self, step: str) -> tuple[ResearchFieldContract, ...]:
        normalized = str(step or "").strip().casefold()
        return tuple(
            contract
            for (registered_step, _field), contract in self._contracts.items()
            if registered_step == normalized
        )

    def all(self) -> tuple[ResearchFieldContract, ...]:
        return tuple(self._contracts.values())

    def canonical(self, step: str, field: str) -> ResearchFieldContract:
        contract = self.get(step, field)
        return self.get(step, contract.canonical_field) if contract.canonical_field != contract.field else contract

    def direct_entity(
        self,
        step: str,
        field: str,
        entity_type: str,
    ) -> tuple[ResearchFieldContract, str]:
        """Return the exact field contract for a direct picker request.

        Direct requests must be checked against the requested alias before any
        canonical-field expansion.  Otherwise a narrow alias such as
        ``knowledge.theory`` would inherit the wider entity set declared by
        ``knowledge.relations``.
        """

        contract = self.get(step, field)
        normalized_entity_type = str(entity_type or "").strip().casefold()
        if normalized_entity_type == "institution":
            normalized_entity_type = "organization"
        allowed_entity_types = {
            "organization" if value == "institution" else value
            for value in contract.entity_types
        }
        if not contract.allow_direct_use or not allowed_entity_types:
            raise ValueError("当前 ResearchFieldContract 不允许直接实体发现。")
        if normalized_entity_type not in allowed_entity_types:
            raise ValueError("entity_type 不属于当前 ResearchFieldContract。")
        return contract, normalized_entity_type


RESEARCH_CONTRACTS = ResearchFieldContractRegistry()

FACTUAL = EnrichmentCandidate.CandidateKind.FACTUAL
CLASSIFICATION = EnrichmentCandidate.CandidateKind.CLASSIFICATION
INTERPRETIVE = EnrichmentCandidate.CandidateKind.INTERPRETIVE

STRUCTURED_WEB = (
    EnrichmentSourceClass.IDENTIFIER_REGISTRY,
    EnrichmentSourceClass.PUBLISHER,
    EnrichmentSourceClass.NATIONAL_LIBRARY,
    EnrichmentSourceClass.LIBRARY_CATALOG,
    EnrichmentSourceClass.ACADEMIC_JOURNAL,
    EnrichmentSourceClass.UNIVERSITY,
    EnrichmentSourceClass.RESEARCH_INSTITUTE,
    EnrichmentSourceClass.PROFESSIONAL_ASSOCIATION,
    EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA,
    EnrichmentSourceClass.SCHOLAR_HOMEPAGE,
    EnrichmentSourceClass.SYLLABUS,
    EnrichmentSourceClass.GENERAL_WEB,
)


def _register(
    step: str,
    field: str,
    *,
    canonical: str | None = None,
    output: str,
    implementation: str,
    target: str | None = None,
    enrichment_field: str = "",
    entities: tuple[str, ...] = (),
    candidates: tuple[str, ...] = (),
    sources: tuple[str, ...] = STRUCTURED_WEB,
    evidence: int = 1,
    independent: int = 1,
    mutation: str = ResearchMutationPolicy.NEVER_DIRECT,
    create_draft: bool = False,
    direct: bool = False,
    enabled: bool = True,
    dependencies: tuple[str, ...] = (),
    description: str = "",
    scope: str = "",
    trigger_inputs: tuple[str, ...] = (),
    dependent_fields: tuple[str, ...] = (),
    local_catalog_sources: tuple[str, ...] | None = None,
    document_sources: tuple[str, ...] | None = None,
    authority_providers: tuple[str, ...] | None = None,
    external_providers: tuple[str, ...] | None = None,
    task_profile: str = "",
    output_schema: dict | None = None,
    accept_policy: str = "",
    stale_policy: str = "invalidate_on_trigger_change",
    no_reliable_reason: str = "证据数量或质量未达到当前字段要求。",
) -> None:
    resolved_scope = scope or {
        "work": "Work",
        "edition": "Edition",
        "person": "Person",
        "reading_path": "Curation",
    }.get(str(target or ""), "Curation")
    resolved_triggers = trigger_inputs or dependencies
    resolved_local_sources = local_catalog_sources if local_catalog_sources is not None else (
        "canonical_entities",
        "draft_entities",
        "existing_holdings",
        "query_lexicon",
    )
    resolved_document_sources = document_sources if document_sources is not None else (
        ("native_text", "front_matter", "selective_ocr", "evidence_span")
        if step in {"work", "bibliography", "contributors", "classification", "knowledge", "curation"}
        else ()
    )
    if authority_providers is not None:
        resolved_authorities = authority_providers
    else:
        resolved_authorities = (
            "crossref",
            "openalex",
            "viaf",
            "openlibrary",
            "google_books",
            *(("nlb_singapore",) if step in {"work", "bibliography", "contributors"} else ()),
        )
    resolved_external = external_providers if external_providers is not None else ("safe_web_fetcher", "searxng_discovery_lead")
    RESEARCH_CONTRACTS.register(
        ResearchFieldContract(
            step=step,
            field=field,
            canonical_field=canonical or field,
            output_type=output,
            implementation=implementation,
            target_type=target,
            enrichment_field=enrichment_field,
            entity_types=entities,
            candidate_types=candidates,
            source_classes=sources,
            evidence_min_count=evidence if enabled else 0,
            independent_source_min=independent if enabled else 0,
            mutation_policy=mutation,
            allow_create_draft=create_draft,
            allow_direct_use=direct,
            research_enabled=enabled,
            dependencies=dependencies,
            description=description,
            scope=resolved_scope,
            trigger_inputs=resolved_triggers,
            dependent_fields=dependent_fields,
            local_catalog_sources=resolved_local_sources,
            document_sources=resolved_document_sources,
            authority_providers=resolved_authorities if enabled else (),
            external_providers=resolved_external if enabled else (),
            research_task_profile=task_profile,
            output_schema=output_schema or {"type": output},
            accept_policy=accept_policy or mutation,
            stale_policy=stale_policy,
            no_reliable_candidate_reason=no_reliable_reason,
        )
    )


for _field in (
    "title", "subtitle", "original_title", "uniform_title", "language",
    "original_language", "first_publication_date", "abstract",
):
    _register(
        "work", _field,
        output="scalar",
        implementation=ResearchImplementation.FIELD_ENRICHMENT,
        target="work",
        enrichment_field=_field,
        candidates=("metadata", "enrichment", "corpus"),
        mutation=ResearchMutationPolicy.EXISTING_FIELD_POLICY,
        dependencies=("work.title", "work.original_title", "work.document_type"),
        dependent_fields=(
            "work.original_title",
            "work.language",
            "work.first_publication_date",
            "work.abstract",
            "bibliography",
            "contributors.authors",
            "contributors.translators",
        ) if _field in {"title", "subtitle", "original_title"} else (),
        task_profile="bibliographic_identity",
        no_reliable_reason=(
            "本馆 PDF 没有可定位的原摘要，且外部来源未提供可核验摘要。"
            if _field == "abstract"
            else "本馆文档、馆内目录和已核验书目来源均未形成可靠候选。"
        ),
    )

_register(
    "work", "canonical_title",
    canonical="uniform_title",
    output="scalar",
    implementation=ResearchImplementation.FIELD_ENRICHMENT,
    target="work",
    enrichment_field="uniform_title",
    candidates=("metadata", "enrichment", "corpus"),
    mutation=ResearchMutationPolicy.EXISTING_FIELD_POLICY,
    dependencies=("work.title", "work.original_title", "work.document_type"),
    task_profile="bibliographic_identity",
    description="Workbench 名称；正式存储继续复用 Work.uniform_title。",
)

_register(
    "work", "translation_of",
    output="entity",
    implementation=ResearchImplementation.ENTITY_DISCOVERY,
    target="work",
    entities=("work",),
    candidates=("entity", "authority", "external_web", "unresolved"),
    mutation=ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION,
    direct=True,
    dependencies=("work.title", "work.original_title", "work.document_type"),
    description="发现可能的原作 Work；只有管理员明确选择后才写入未保存表单。",
)

for _field in (
    "version_label", "publication_date", "publication_year", "publisher", "publication_place", "isbn",
    "isbn10", "isbn13", "series", "extent", "responsibility_statement",
    "journal_title", "volume", "issue", "page_range", "doi", "degree_institution",
    "degree_type", "report_institution",
):
    _direct_entities = {
        "publisher": ("publisher",),
        "journal_title": ("journal",),
        "degree_institution": ("organization",),
        "report_institution": ("organization",),
    }.get(_field, ())
    _register(
        "bibliography", _field,
        output="scalar",
        implementation=ResearchImplementation.FIELD_ENRICHMENT,
        target="edition",
        enrichment_field=_field,
        entities=_direct_entities,
        candidates=(
            "metadata", "enrichment", "corpus",
            *(("entity", "authority", "external_web", "unresolved") if _direct_entities else ()),
        ),
        mutation=ResearchMutationPolicy.EXISTING_FIELD_POLICY,
        direct=bool(_direct_entities),
        dependencies=("work.title", "work.original_title", "bibliography.isbn", "bibliography.doi"),
        task_profile="bibliographic_identity",
        no_reliable_reason="当前 PDF 前置信息和可核验书目来源均未提供该版本字段。",
    )

_register(
    "bibliography", "edition_statement",
    canonical="version_label",
    output="scalar",
    implementation=ResearchImplementation.FIELD_ENRICHMENT,
    target="edition",
    enrichment_field="version_label",
    candidates=("metadata", "enrichment", "corpus"),
    mutation=ResearchMutationPolicy.EXISTING_FIELD_POLICY,
    dependencies=("work.title", "work.original_title", "bibliography.isbn", "bibliography.doi"),
    task_profile="bibliographic_identity",
    description="Workbench 名称；正式存储继续复用 Edition.version_label。",
)

for _alias in ("contributors", "display_name", "person"):
    _register(
        "contributors", _alias,
        canonical="contributors",
        output="entity",
        implementation=ResearchImplementation.ENTITY_DISCOVERY,
        target="person",
        entities=("person",),
        candidates=("entity", "authority", "external_web", "unresolved"),
        mutation=ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION,
        create_draft=True,
        direct=True,
        dependencies=("contributors.items", "work.title", "work.original_title"),
        task_profile="person_identity",
    )

for _field, _roles in (
    ("authors", ("author",)),
    ("translators", ("translator",)),
    ("other_contributors", ("editor", "compiler", "contributor", "other")),
):
    _register(
        "contributors", _field,
        canonical="contributors",
        output="entity_list",
        implementation=ResearchImplementation.ENTITY_DISCOVERY,
        target="person",
        entities=("person",),
        candidates=("entity", "authority", "external_web", "unresolved"),
        mutation=ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION,
        create_draft=True,
        direct=True,
        dependencies=("contributors.items", "work.title", "work.original_title", "bibliography.responsibility_statement"),
        task_profile="person_identity",
        output_schema={"type": "array", "items": {"type": "object", "required": ["person", "role"]}},
        description=f"责任者角色范围：{', '.join(_roles)}。",
    )

for _field, _entities, _canonical in (
    ("primary_disciplines", ("discipline",), "primary_disciplines"),
    ("related_disciplines", ("discipline",), "related_disciplines"),
    ("disciplines", ("discipline",), "related_disciplines"),
    ("subdisciplines", ("subdiscipline", "knowledge_node"), "subdisciplines"),
):
    _register(
        "classification", _field,
        canonical=_canonical,
        output="entity_list",
        implementation=ResearchImplementation.ENTITY_DISCOVERY,
        target="work",
        entities=_entities,
        candidates=("entity", "query_lexicon", "enrichment", "external_web"),
        mutation=ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION,
        direct=True,
        dependencies=("work.title", "work.abstract", "classification"),
        task_profile="theory_classification",
    )

_register(
    "classification", "primary_discipline",
    canonical="primary_disciplines",
    output="entity",
    implementation=ResearchImplementation.ENTITY_DISCOVERY,
    target="work",
    entities=("discipline",),
    candidates=("entity", "query_lexicon", "enrichment", "external_web"),
    mutation=ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION,
    direct=True,
    dependencies=("work.title", "work.abstract", "classification"),
    task_profile="theory_classification",
    description="单数产品字段；正式工作台继续使用 primary_disciplines 列表保存。",
)

for _field, _entities in (
    ("relations", ("theory", "topic", "knowledge_node")),
    ("theory", ("theory",)),
    ("topic", ("topic",)),
    ("knowledge_node", ("knowledge_node",)),
):
    _register(
        "knowledge", _field,
        canonical="relations",
        output="entity_relation",
        implementation=ResearchImplementation.ENTITY_DISCOVERY,
        target="work",
        entities=_entities,
        candidates=("relation", "entity", "query_lexicon", "pdf_evidence", "external_web"),
        evidence=1,
        mutation=ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION,
        create_draft=True,
        direct=True,
        dependencies=("work.title", "work.abstract", "knowledge.relations"),
        task_profile=("concept_importance" if _field == "topic" else "theory_classification"),
    )

for _field, _entities, _profile in (
    ("theories", ("theory",), "theory_classification"),
    ("concepts", ("concept", "knowledge_node"), "concept_importance"),
    ("topics", ("topic",), "concept_importance"),
    ("debates", ("debate", "knowledge_node"), "debate_discovery"),
    ("scholar_relations", ("person",), "theory_development_position"),
):
    _register(
        "knowledge", _field,
        output="entity_relation",
        implementation=ResearchImplementation.ENTITY_DISCOVERY,
        target="work",
        entities=_entities,
        candidates=("relation", "entity", "query_lexicon", "pdf_evidence", "external_web"),
        evidence=1,
        mutation=ResearchMutationPolicy.EXPLICIT_ENTITY_DECISION,
        create_draft=_field in {"concepts", "debates", "scholar_relations"},
        direct=True,
        dependencies=("work.title", "work.abstract", "knowledge.relations"),
        task_profile=_profile,
    )

for _field in ("reader_rendition_policy", "text_layer_status", "page_label_status", "semantic_index_status"):
    _register(
        "reader", _field,
        output="status",
        implementation=ResearchImplementation.STATUS_ONLY,
        sources=(),
        evidence=0,
        independent=0,
        mutation=ResearchMutationPolicy.NOT_APPLICABLE,
        enabled=False,
        description="由文件、OCR、页码或语义索引状态确定，不执行外部研究。",
    )

_register(
    "curation", "reading_path_placements",
    output="editorial_entity",
    implementation=ResearchImplementation.EDITORIAL_DISCOVERY,
    target="reading_path",
    entities=("reading_path", "work", "knowledge_node"),
    candidates=("editorial", "syllabus", "external_web"),
    mutation=ResearchMutationPolicy.EXPLICIT_EDITORIAL_REVIEW,
    direct=True,
    dependencies=("work.title", "work.abstract", "knowledge.relations"),
    task_profile="reading_path_placement",
)
_register(
    "curation", "recommendation_reason",
    output="evidence",
    implementation=ResearchImplementation.EVIDENCE_ONLY,
    target="work",
    candidates=("corpus", "syllabus", "external_web"),
    mutation=ResearchMutationPolicy.NEVER_DIRECT,
    dependencies=("work.title", "work.abstract", "knowledge.relations"),
    task_profile="reading_path_placement",
)

for _field, _profile in (
    ("core_viewpoints", "core_viewpoint"),
    ("major_criticisms", "major_criticism"),
    ("major_responses", "major_response"),
):
    _register(
        "curation", _field,
        output="evidence_list",
        implementation=ResearchImplementation.EVIDENCE_ONLY,
        target="work",
        candidates=("derived_claim", "curated_claim", "pdf_evidence"),
        sources=(),
        mutation=ResearchMutationPolicy.EXPLICIT_EDITORIAL_REVIEW,
        dependencies=("work.title", "work.abstract", "knowledge.relations"),
        local_catalog_sources=("derived_claims", "curated_claims", "existing_holdings"),
        document_sources=("evidence_span", "selective_ocr"),
        authority_providers=(),
        external_providers=(),
        task_profile=_profile,
        output_schema={"type": "array", "maxItems": 5, "items": {"type": "object"}},
        no_reliable_reason="当前馆藏 Claim 与 EvidenceSpan 尚未形成可采用的高价值候选。",
    )
_register(
    "publication", "preflight",
    output="status",
    implementation=ResearchImplementation.STATUS_ONLY,
    sources=(),
    evidence=0,
    independent=0,
    mutation=ResearchMutationPolicy.NOT_APPLICABLE,
    enabled=False,
    description="直接复用 publication preflight，不执行联网研究。",
)


# Independent authority and theory-system workbenches use the same direct
# Entity Discovery endpoint as the Work workflow.  These contracts are exact
# to each maintenance field so a broad search can never return a selectable
# entity of another type.  Discovery remains read-only; the existing page
# save/review mutations are still the only way to persist a relationship.
for _step, _field, _output, _entities, _target in (
    ("maintenance_subdisciplines", "discipline", "entity", ("discipline",), "subdiscipline"),
    ("maintenance_subdisciplines", "parent", "entity", ("subdiscipline",), "subdiscipline"),
    ("maintenance_theory_nodes", "filter_discipline", "entity", ("discipline",), "knowledge_node"),
    ("maintenance_theory_nodes", "parent", "entity", ("knowledge_node",), "knowledge_node"),
    ("maintenance_theory_nodes", "primary_discipline", "entity", ("discipline",), "knowledge_node"),
    ("maintenance_theory_nodes", "related_disciplines", "entity_list", ("discipline",), "knowledge_node"),
    ("maintenance_theory_nodes", "merge_target", "entity", ("knowledge_node",), "knowledge_node"),
    ("maintenance_theory_relations", "review_candidate", "entity", ("knowledge_node",), "knowledge_node"),
    ("maintenance_theory_relations", "new_node_discipline", "entity", ("discipline",), "knowledge_node"),
    ("maintenance_theory_relations", "source_node", "entity", ("knowledge_node",), "knowledge_relation"),
    ("maintenance_theory_relations", "target_node", "entity", ("knowledge_node",), "knowledge_relation"),
    ("maintenance_theory_timeline", "filter_discipline", "entity", ("discipline",), "timeline_event"),
    ("maintenance_theory_timeline", "nodes", "entity_list", ("knowledge_node",), "timeline_event"),
    ("maintenance_theory_timeline", "disciplines", "entity_list", ("discipline",), "timeline_event"),
    ("maintenance_theory_timeline", "scholar", "entity", ("person",), "scholar_profile"),
    ("maintenance_theory_timeline", "work", "entity", ("work",), "timeline_event"),
):
    _register(
        _step,
        _field,
        output=_output,
        implementation=ResearchImplementation.ENTITY_DISCOVERY,
        target=_target,
        entities=_entities,
        candidates=("entity", "authority", "external_web", "unresolved"),
        mutation=ResearchMutationPolicy.NEVER_DIRECT,
        create_draft=False,
        direct=True,
        dependencies=(),
        description="后台独立维护页的只读实体发现；选择只更新未保存表单。",
    )


WORKFLOW_FIELDS = MappingProxyType({
    "work": (
        "title", "subtitle", "original_title", "canonical_title", "uniform_title",
        "abstract", "language", "original_language", "first_publication_date",
        "translation_of",
    ),
    "bibliography": (
        "edition_statement", "version_label", "publication_date", "publication_year",
        "publisher", "publication_place", "isbn", "isbn10", "isbn13", "series",
        "extent", "responsibility_statement", "journal_title", "volume", "issue",
        "page_range", "doi", "degree_institution", "degree_type", "report_institution",
    ),
    "contributors": (
        "contributors", "display_name", "person", "authors", "translators", "other_contributors",
    ),
    "classification": (
        "primary_discipline", "primary_disciplines", "related_disciplines", "disciplines", "subdisciplines",
    ),
    "knowledge": (
        "relations", "theory", "topic", "knowledge_node", "theories", "concepts",
        "topics", "debates", "scholar_relations",
    ),
    "reader": (
        "reader_rendition_policy", "text_layer_status", "page_label_status", "semantic_index_status",
    ),
    "curation": (
        "core_viewpoints", "major_criticisms", "major_responses",
        "reading_path_placements", "recommendation_reason",
    ),
    "publication": ("preflight",),
})


def validate_contract_coverage() -> dict[str, object]:
    missing = []
    invalid = []
    for step, fields in WORKFLOW_FIELDS.items():
        for field in fields:
            try:
                contract = RESEARCH_CONTRACTS.get(step, field)
            except ValueError:
                missing.append(f"{step}.{field}")
                continue
            if contract.research_enabled and contract.implementation == ResearchImplementation.STATUS_ONLY:
                invalid.append(f"{step}.{field}")
    if missing or invalid:
        raise RuntimeError(f"Research contract coverage invalid missing={missing} invalid={invalid}")
    return {
        "version": RESEARCH_CONTRACT_VERSION,
        "contract_count": len(RESEARCH_CONTRACTS.all()),
        "missing": missing,
        "invalid": invalid,
        "healthy": True,
    }


def contract_payload(contract: ResearchFieldContract) -> dict[str, object]:
    from .producer_capabilities import capability_for_contract

    return {
        "step": contract.step,
        "field": contract.field,
        "canonical_field": contract.canonical_field,
        "output_type": contract.output_type,
        "implementation": contract.implementation,
        "target_type": contract.target_type,
        "enrichment_field": contract.enrichment_field,
        "entity_types": list(contract.entity_types),
        "candidate_types": list(contract.candidate_types),
        "source_classes": list(contract.source_classes),
        "evidence_requirement": {
            "minimum": contract.evidence_min_count,
            "independent_sources": contract.independent_source_min,
        },
        "mutation_policy": contract.mutation_policy,
        "allow_create_draft": contract.allow_create_draft,
        "allow_direct_use": contract.allow_direct_use,
        "research_enabled": contract.research_enabled,
        "dependencies": list(contract.dependencies),
        "scope": contract.scope,
        "trigger_inputs": list(contract.effective_trigger_inputs),
        "dependent_fields": list(contract.dependent_fields),
        "local_catalog_sources": list(contract.local_catalog_sources),
        "document_ocr_sources": list(contract.document_sources),
        "authority_providers": list(contract.authority_providers),
        "external_providers": list(contract.external_providers),
        "research_task_profile": contract.research_task_profile,
        "output_schema": contract.output_schema or {},
        "accept_policy": contract.accept_policy,
        "stale_policy": contract.stale_policy,
        "no_reliable_candidate": {
            "status": "no_reliable_candidate",
            "reason": contract.no_reliable_candidate_reason,
        },
        "description": contract.description,
        "producer_capability": capability_for_contract(contract).payload(),
        "version": contract.version,
    }
