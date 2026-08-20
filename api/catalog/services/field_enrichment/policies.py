from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

from catalog.models import EnrichmentCandidate, EnrichmentSourceClass


POLICY_VERSION = "field-enrichment-policy-v1"
EXTRACTION_VERSION = "field-enrichment-extraction-v1"


class ConflictPolicy:
    MERGE = "merge"
    REPLACE_AFTER_REVIEW = "replace_after_review"
    CREATE_PENDING_RELATION = "create_pending_relation"
    EDITORIAL_APPEND = "editorial_append"


@dataclass(frozen=True)
class FieldPolicy:
    target_type: str
    field_name: str
    candidate_kind: str
    allowed_source_classes: tuple[str, ...]
    source_priority: MappingProxyType
    structured_adapters: tuple[str, ...] = ()
    allow_general_web: bool = False
    requires_identity: bool = True
    evidence_min_count: int = 1
    independent_source_min: int = 1
    required_source_classes: tuple[str, ...] = ()
    mutation_adapter: str = ""
    conflict_policy: str = ConflictPolicy.REPLACE_AFTER_REVIEW
    refresh_seconds: int = 86400 * 180
    value_schema: dict = field(default_factory=dict)
    policy_version: str = POLICY_VERSION
    extraction_version: str = EXTRACTION_VERSION

    def priority_for(self, source_class: str) -> int:
        return int(self.source_priority.get(source_class, 0))


class FieldPolicyRegistry:
    def __init__(self):
        self._policies: dict[tuple[str, str], FieldPolicy] = {}

    def register(self, policy: FieldPolicy) -> FieldPolicy:
        key = (policy.target_type, policy.field_name)
        if key in self._policies:
            raise RuntimeError(f"重复的 field enrichment policy：{key[0]}.{key[1]}")
        self._policies[key] = policy
        return policy

    def get(self, target_type: str, field_name: str) -> FieldPolicy:
        key = (str(target_type).strip().casefold(), str(field_name).strip())
        try:
            return self._policies[key]
        except KeyError as exc:
            raise ValueError(f"不支持的联网补全字段：{key[0]}.{key[1]}") from exc

    def for_target(self, target_type: str) -> tuple[FieldPolicy, ...]:
        target_type = str(target_type).strip().casefold()
        return tuple(
            policy
            for (registered_type, _field), policy in self._policies.items()
            if registered_type == target_type
        )

    def all(self) -> tuple[FieldPolicy, ...]:
        return tuple(self._policies.values())


FIELD_POLICIES = FieldPolicyRegistry()


def _priority(*values: tuple[str, int]) -> MappingProxyType:
    return MappingProxyType(dict(values))


IDENTITY_PRIORITY = _priority(
    (EnrichmentSourceClass.IDENTIFIER_REGISTRY, 100),
    (EnrichmentSourceClass.NATIONAL_LIBRARY, 95),
    (EnrichmentSourceClass.UNIVERSITY, 90),
    (EnrichmentSourceClass.RESEARCH_INSTITUTE, 90),
    (EnrichmentSourceClass.SCHOLAR_HOMEPAGE, 85),
    (EnrichmentSourceClass.ACADEMIC_JOURNAL, 65),
    (EnrichmentSourceClass.GENERAL_WEB, 20),
)

BIBLIOGRAPHIC_PRIORITY = _priority(
    (EnrichmentSourceClass.IDENTIFIER_REGISTRY, 100),
    (EnrichmentSourceClass.PUBLISHER, 98),
    (EnrichmentSourceClass.NATIONAL_LIBRARY, 95),
    (EnrichmentSourceClass.LIBRARY_CATALOG, 85),
    (EnrichmentSourceClass.ACADEMIC_JOURNAL, 85),
    (EnrichmentSourceClass.GENERAL_WEB, 20),
)

SCHOLARLY_PRIORITY = _priority(
    (EnrichmentSourceClass.ACADEMIC_JOURNAL, 100),
    (EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA, 95),
    (EnrichmentSourceClass.UNIVERSITY, 90),
    (EnrichmentSourceClass.RESEARCH_INSTITUTE, 90),
    (EnrichmentSourceClass.PROFESSIONAL_ASSOCIATION, 85),
    (EnrichmentSourceClass.NATIONAL_LIBRARY, 75),
    (EnrichmentSourceClass.GENERAL_WEB, 15),
)

INTERPRETIVE_PRIORITY = _priority(
    (EnrichmentSourceClass.ACADEMIC_JOURNAL, 100),
    (EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA, 95),
    (EnrichmentSourceClass.UNIVERSITY, 90),
    (EnrichmentSourceClass.RESEARCH_INSTITUTE, 90),
    (EnrichmentSourceClass.PROFESSIONAL_ASSOCIATION, 85),
)

EDITORIAL_PRIORITY = _priority(
    (EnrichmentSourceClass.SYLLABUS, 100),
    (EnrichmentSourceClass.UNIVERSITY, 90),
    (EnrichmentSourceClass.PROFESSIONAL_ASSOCIATION, 80),
    (EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA, 75),
    (EnrichmentSourceClass.GENERAL_WEB, 10),
)


def _register(
    target_type: str,
    field_name: str,
    kind: str,
    priority: MappingProxyType,
    *,
    structured: tuple[str, ...] = (),
    web: bool = False,
    identity: bool = True,
    evidence: int = 1,
    independent: int = 1,
    required: tuple[str, ...] = (),
    mutation: str,
    conflict: str = ConflictPolicy.REPLACE_AFTER_REVIEW,
    refresh: int = 86400 * 180,
    schema: dict | None = None,
) -> None:
    FIELD_POLICIES.register(
        FieldPolicy(
            target_type=target_type,
            field_name=field_name,
            candidate_kind=kind,
            allowed_source_classes=tuple(priority.keys()),
            source_priority=priority,
            structured_adapters=structured,
            allow_general_web=web,
            requires_identity=identity,
            evidence_min_count=evidence,
            independent_source_min=independent,
            required_source_classes=required,
            mutation_adapter=mutation,
            conflict_policy=conflict,
            refresh_seconds=refresh,
            value_schema=schema or {},
        )
    )


FACTUAL = EnrichmentCandidate.CandidateKind.FACTUAL
CLASSIFICATION = EnrichmentCandidate.CandidateKind.CLASSIFICATION
INTERPRETIVE = EnrichmentCandidate.CandidateKind.INTERPRETIVE

_register(
    "person", "external_identifier", FACTUAL, IDENTITY_PRIORITY,
    structured=("authority",), web=True, mutation="person_external_identifier",
    conflict=ConflictPolicy.MERGE, refresh=86400 * 365,
    schema={"type": "object", "required": ["scheme", "value"]},
)
_register(
    "person", "affiliation", FACTUAL, IDENTITY_PRIORITY,
    structured=("authority",), web=True, mutation="person_affiliation",
    conflict=ConflictPolicy.MERGE, refresh=86400 * 30,
    schema={"type": "object", "required": ["name"]},
)
_register(
    "person", "name_variant", FACTUAL, IDENTITY_PRIORITY,
    structured=("authority",), web=True, mutation="person_name_variant",
    conflict=ConflictPolicy.MERGE, refresh=86400 * 365,
    schema={"type": "object", "required": ["name", "language", "variant_type"]},
)

for field_name, adapter in (
    ("publication_year", "edition_publication_year"),
    ("publisher", "edition_publisher"),
    ("isbn", "edition_isbn"),
):
    _register(
        "edition", field_name, FACTUAL, BIBLIOGRAPHIC_PRIORITY,
        structured=("bibliographic",), web=True, mutation=adapter,
        refresh=86400 * 365,
        schema={"type": "integer" if field_name == "publication_year" else "string"},
    )

for field_name in (
    "version_label",
    "publication_place",
    "isbn10",
    "isbn13",
    "doi",
    "journal_title",
    "volume",
    "issue",
    "page_range",
    "series",
    "extent",
    "responsibility_statement",
    "degree_institution",
    "degree_type",
    "report_institution",
):
    _register(
        "edition", field_name, FACTUAL, BIBLIOGRAPHIC_PRIORITY,
        structured=("bibliographic",), web=True,
        mutation=f"edition_{field_name}", refresh=86400 * 365,
        schema={"type": "string"},
    )

for field_name in (
    "title",
    "subtitle",
    "original_title",
    "uniform_title",
    "language",
    "original_language",
    "abstract",
):
    _register(
        "work", field_name, FACTUAL, BIBLIOGRAPHIC_PRIORITY,
        structured=("bibliographic",), web=True,
        mutation=f"work_{field_name}", refresh=86400 * 365,
        schema={"type": "string"},
    )

_register(
    "work", "first_publication_date", FACTUAL, BIBLIOGRAPHIC_PRIORITY,
    structured=("bibliographic",), web=True, mutation="work_first_publication_date",
    refresh=86400 * 365, schema={"type": "string", "format": "date"},
)

_register(
    "work", "discipline", CLASSIFICATION, SCHOLARLY_PRIORITY,
    web=True, mutation="work_discipline",
    conflict=ConflictPolicy.CREATE_PENDING_RELATION,
    schema={"type": "object", "required": ["discipline_id", "relation_type"]},
)
_register(
    "work", "subdiscipline", CLASSIFICATION, SCHOLARLY_PRIORITY,
    web=True, mutation="work_subdiscipline",
    conflict=ConflictPolicy.CREATE_PENDING_RELATION,
    schema={"type": "object", "required": ["subdiscipline_node_id"]},
)

for target_type in ("discipline", "subdiscipline"):
    _register(
        target_type, "foreign_name", FACTUAL, SCHOLARLY_PRIORITY,
        structured=("authority",), web=True, identity=True,
        mutation=f"{target_type}_foreign_name", refresh=86400 * 365,
        schema={"type": "string"},
    )

_register(
    "knowledge_node", "alias", FACTUAL, SCHOLARLY_PRIORITY,
    structured=("authority",), web=True, mutation="knowledge_node_alias",
    conflict=ConflictPolicy.MERGE, refresh=86400 * 365,
    schema={"type": "object", "required": ["alias", "language", "alias_type"]},
)
_register(
    "knowledge_node", "discipline", CLASSIFICATION, SCHOLARLY_PRIORITY,
    web=True, mutation="knowledge_node_discipline",
    conflict=ConflictPolicy.CREATE_PENDING_RELATION,
    schema={"type": "object", "required": ["discipline_id", "relation_type"]},
)
_register(
    "knowledge_node", "subdiscipline", CLASSIFICATION, SCHOLARLY_PRIORITY,
    web=True, mutation="knowledge_node_subdiscipline",
    conflict=ConflictPolicy.REPLACE_AFTER_REVIEW,
    schema={"type": "object", "required": ["subdiscipline_node_id"]},
)
_register(
    "knowledge_node", "relation", INTERPRETIVE, INTERPRETIVE_PRIORITY,
    web=True, mutation="knowledge_relation",
    evidence=2, independent=2,
    required=(EnrichmentSourceClass.ACADEMIC_JOURNAL, EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA, EnrichmentSourceClass.UNIVERSITY, EnrichmentSourceClass.RESEARCH_INSTITUTE, EnrichmentSourceClass.PROFESSIONAL_ASSOCIATION),
    conflict=ConflictPolicy.CREATE_PENDING_RELATION, refresh=86400 * 180,
    schema={"type": "object", "required": ["target_node_id", "relation_type"]},
)
_register(
    "knowledge_node", "timeline_fact", FACTUAL, SCHOLARLY_PRIORITY,
    web=True, mutation="knowledge_node_timeline_fact",
    conflict=ConflictPolicy.CREATE_PENDING_RELATION,
    schema={"type": "object", "required": ["title", "event_type", "start_year"]},
)
_register(
    "knowledge_node", "timeline_interpretation", INTERPRETIVE, INTERPRETIVE_PRIORITY,
    web=True, mutation="knowledge_node_timeline_interpretation",
    evidence=2, independent=2,
    required=(EnrichmentSourceClass.ACADEMIC_JOURNAL, EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA, EnrichmentSourceClass.UNIVERSITY, EnrichmentSourceClass.RESEARCH_INSTITUTE),
    conflict=ConflictPolicy.CREATE_PENDING_RELATION,
    schema={"type": "object", "required": ["title", "description", "date_label"]},
)

_register(
    "topic", "discipline", CLASSIFICATION, SCHOLARLY_PRIORITY,
    web=True, mutation="topic_discipline",
    conflict=ConflictPolicy.CREATE_PENDING_RELATION,
    schema={"type": "object", "required": ["discipline_id"]},
)
_register(
    "reading_path", "item", INTERPRETIVE, EDITORIAL_PRIORITY,
    web=True, identity=False, mutation="reading_path_item",
    evidence=1, independent=1,
    required=(EnrichmentSourceClass.SYLLABUS, EnrichmentSourceClass.UNIVERSITY),
    conflict=ConflictPolicy.EDITORIAL_APPEND, refresh=86400 * 90,
    schema={"type": "object", "required": ["stage_name"]},
)
