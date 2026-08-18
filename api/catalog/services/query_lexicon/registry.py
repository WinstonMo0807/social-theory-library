from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
from typing import Iterable
from uuid import UUID

from catalog.models import (
    Concept,
    Discipline,
    KnowledgeNode,
    KnowledgeNodeAlias,
    LegacyKnowledgeMapping,
    Person,
    PersonNameVariant,
    QueryLexiconEntry,
    Subdiscipline,
    TheorySchool,
    Topic,
)
from catalog.services.query_lexicon.normalization import (
    GENERATED_VARIANT_VERSION,
    detect_language,
    generated_search_variants,
    normalize_language,
    normalize_term,
)


SOURCE_REGISTRY_VERSION = "query-lexicon-registry-v1"
SUPPORTED_SOURCE_REGISTRY_VERSIONS = {SOURCE_REGISTRY_VERSION}


@dataclass(frozen=True, order=True)
class EntityKey:
    entity_type: str
    entity_id: UUID


@dataclass
class TermCandidate:
    term: str
    language: str
    term_type: str
    source_kind: str
    trust_level: str
    source_ref: str
    displayable: bool
    public_active: bool
    admin_resolvable: bool
    provenance: dict = field(default_factory=dict)

    @property
    def normalized_term(self) -> str:
        return normalize_term(self.term)


@dataclass
class EntityBuild:
    key: EntityKey
    entries: list[dict]
    audit: dict[str, int]


LEGACY_MODELS = {
    "TheorySchool": (TheorySchool, QueryLexiconEntry.EntityType.THEORY_SCHOOL),
    "Subdiscipline": (Subdiscipline, QueryLexiconEntry.EntityType.SUBDISCIPLINE),
    "Concept": (Concept, QueryLexiconEntry.EntityType.CONCEPT),
}

ENTITY_MODELS = {
    QueryLexiconEntry.EntityType.PERSON: Person,
    QueryLexiconEntry.EntityType.KNOWLEDGE_NODE: KnowledgeNode,
    QueryLexiconEntry.EntityType.DISCIPLINE: Discipline,
    QueryLexiconEntry.EntityType.THEORY_SCHOOL: TheorySchool,
    QueryLexiconEntry.EntityType.TOPIC: Topic,
    QueryLexiconEntry.EntityType.CONCEPT: Concept,
    QueryLexiconEntry.EntityType.SUBDISCIPLINE: Subdiscipline,
}

_TERM_PRIORITY = {
    QueryLexiconEntry.TermType.CANONICAL: 70,
    QueryLexiconEntry.TermType.TRANSLATION: 60,
    QueryLexiconEntry.TermType.ALIAS: 50,
    QueryLexiconEntry.TermType.ABBREVIATION: 40,
    QueryLexiconEntry.TermType.HISTORICAL: 30,
    QueryLexiconEntry.TermType.TRANSLITERATION: 20,
    QueryLexiconEntry.TermType.SEARCH_VARIANT: 10,
}
_TRUST_PRIORITY = {
    QueryLexiconEntry.TrustLevel.AUTHORITATIVE: 50,
    QueryLexiconEntry.TrustLevel.VERIFIED: 40,
    QueryLexiconEntry.TrustLevel.UNVERIFIED: 30,
    QueryLexiconEntry.TrustLevel.LEGACY: 20,
    QueryLexiconEntry.TrustLevel.GENERATED: 10,
}


def _entity_key(entity_type: str, entity_id) -> EntityKey:
    return EntityKey(str(entity_type), UUID(str(entity_id)))


def _person_terminal(person: Person, *, max_depth: int = 32) -> Person | None:
    started_merged = person.authority_status == Person.AuthorityStatus.MERGED
    current = person
    seen: set[UUID] = set()
    for _depth in range(max_depth + 1):
        if current.pk in seen:
            return None
        seen.add(current.pk)
        if current.authority_status != Person.AuthorityStatus.MERGED:
            if started_merged and current.authority_status in {
                Person.AuthorityStatus.REJECTED,
                Person.AuthorityStatus.ARCHIVED,
            }:
                return None
            return current
        if not current.merged_into_id:
            return None
        current = (
            Person.objects.select_related("merged_into")
            .filter(pk=current.merged_into_id)
            .first()
        )
        if current is None:
            return None
    return None


def audit_person_merges(
    *,
    entity_id: UUID | str | None = None,
    finding_limit: int = 100,
    max_depth: int = 32,
) -> dict:
    """Audit merge pointers without guessing or changing a survivor."""

    requested_id = UUID(str(entity_id)) if entity_id is not None else None
    rows = {
        row["id"]: row
        for row in Person.objects.order_by("pk").values(
            "id",
            "authority_status",
            "merged_into_id",
        )
    }
    merged_ids = [
        person_id
        for person_id, row in rows.items()
        if row["authority_status"] == Person.AuthorityStatus.MERGED
    ]
    findings = []
    resolved = []
    anomaly_counts = defaultdict(int)
    chained_merges = 0
    valid_merges = 0

    for person_id in sorted(merged_ids, key=str):
        current_id = person_id
        path = [person_id]
        seen = {person_id}
        code = ""
        survivor_id = None

        for _depth in range(max_depth + 1):
            current = rows.get(current_id)
            if current is None:
                code = "merged_survivor_missing"
                break
            target_id = current["merged_into_id"]
            if target_id is None:
                code = "merged_target_missing"
                break
            if target_id == current_id:
                code = "merged_self_reference"
                path.append(target_id)
                break
            if target_id in seen:
                code = "merged_cycle"
                path.append(target_id)
                break
            path.append(target_id)
            seen.add(target_id)
            target = rows.get(target_id)
            if target is None:
                code = "merged_survivor_missing"
                break
            if target["authority_status"] != Person.AuthorityStatus.MERGED:
                if target["authority_status"] == Person.AuthorityStatus.REJECTED:
                    code = "merged_survivor_rejected"
                elif target["authority_status"] == Person.AuthorityStatus.ARCHIVED:
                    code = "merged_survivor_archived"
                else:
                    survivor_id = target_id
                break
            current_id = target_id
        else:
            code = "merged_chain_too_deep"

        relevant = requested_id is None or person_id == requested_id or survivor_id == requested_id
        if not relevant:
            continue
        if code:
            anomaly_counts[code] += 1
            if len(findings) < max(1, finding_limit):
                findings.append(
                    {
                        "code": code,
                        "person_id": str(person_id),
                        "direct_target_id": (
                            str(rows[person_id]["merged_into_id"])
                            if rows[person_id]["merged_into_id"]
                            else None
                        ),
                        "path": [str(value) for value in path],
                    }
                )
            continue

        if len(path) > 2:
            chained_merges += 1
        valid_merges += 1
        if len(resolved) < max(1, finding_limit):
            resolved.append(
                {
                    "person_id": str(person_id),
                    "survivor_id": str(survivor_id),
                    "depth": len(path) - 1,
                }
            )

    anomaly_total = sum(anomaly_counts.values())
    return {
        "merged_people_audited": valid_merges + anomaly_total,
        "valid_merges": valid_merges,
        "chained_merges": chained_merges,
        "historical_sources_resolvable": valid_merges,
        "anomaly_count": anomaly_total,
        "anomaly_counts": dict(sorted(anomaly_counts.items())),
        "findings": findings,
        "findings_truncated": anomaly_total > len(findings),
        "resolved_samples": resolved,
    }


def _mapped_node_for_legacy(instance) -> KnowledgeNode | None:
    mapping = (
        LegacyKnowledgeMapping.objects.select_related("node")
        .filter(
            legacy_model=instance.__class__.__name__,
            legacy_id=instance.pk,
            migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
        )
        .first()
    )
    return mapping.node if mapping else None


def entity_keys_for_source(instance) -> set[EntityKey]:
    """Return every canonical entity that may change when one source row changes."""

    keys: set[EntityKey] = set()
    if isinstance(instance, Person):
        keys.add(_entity_key(QueryLexiconEntry.EntityType.PERSON, instance.pk))
        terminal = _person_terminal(instance)
        if terminal and terminal.pk != instance.pk:
            keys.add(_entity_key(QueryLexiconEntry.EntityType.PERSON, terminal.pk))
        return keys
    if isinstance(instance, PersonNameVariant):
        keys.add(_entity_key(QueryLexiconEntry.EntityType.PERSON, instance.person_id))
        terminal = _person_terminal(instance.person)
        if terminal and terminal.pk != instance.person_id:
            keys.add(_entity_key(QueryLexiconEntry.EntityType.PERSON, terminal.pk))
        return keys
    if isinstance(instance, KnowledgeNode):
        return {_entity_key(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, instance.pk)}
    if isinstance(instance, KnowledgeNodeAlias):
        return {_entity_key(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, instance.node_id)}
    if isinstance(instance, LegacyKnowledgeMapping):
        config = LEGACY_MODELS.get(instance.legacy_model)
        if config:
            _model, entity_type = config
            keys.add(_entity_key(entity_type, instance.legacy_id))
        keys.add(_entity_key(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, instance.node_id))
        return keys
    for model_name, (model, entity_type) in LEGACY_MODELS.items():
        if isinstance(instance, model):
            keys.add(_entity_key(entity_type, instance.pk))
            node = _mapped_node_for_legacy(instance)
            if node:
                keys.add(_entity_key(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, node.pk))
            return keys
    if isinstance(instance, Discipline):
        return {_entity_key(QueryLexiconEntry.EntityType.DISCIPLINE, instance.pk)}
    if isinstance(instance, Topic):
        return {_entity_key(QueryLexiconEntry.EntityType.TOPIC, instance.pk)}
    return keys


def all_entity_keys(
    *,
    entity_type: str | None = None,
    entity_id: UUID | str | None = None,
) -> list[EntityKey]:
    validated_id = validate_entity_filter(entity_type=entity_type, entity_id=entity_id)
    entity_id = validated_id

    if entity_id is not None:
        return [_entity_key(entity_type, entity_id)]

    selected = [entity_type] if entity_type else sorted(ENTITY_MODELS)
    keys: set[EntityKey] = set()
    for current_type in selected:
        model = ENTITY_MODELS[current_type]
        keys.update(
            _entity_key(current_type, pk)
            for pk in model.objects.order_by("pk").values_list("pk", flat=True)
        )
    return sorted(keys)


def validate_entity_filter(
    *,
    entity_type: str | None = None,
    entity_id: UUID | str | None = None,
) -> UUID | None:
    """Validate a reconciliation selector without reading or writing authority rows."""

    if entity_type and entity_type not in ENTITY_MODELS:
        raise ValueError(f"未知 QueryLexicon entity type：{entity_type}")
    if entity_id is not None:
        if not entity_type:
            raise ValueError("entity_id 必须与 entity_type 同时使用。")
        try:
            return UUID(str(entity_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"无效 QueryLexicon entity id：{entity_id}") from exc
    return None


def _status_flags(instance) -> tuple[bool, bool, str | None]:
    if isinstance(instance, Person):
        if instance.authority_status == Person.AuthorityStatus.VERIFIED:
            return True, True, None
        if instance.authority_status in {
            Person.AuthorityStatus.DRAFT,
            Person.AuthorityStatus.NEEDS_REVIEW,
        }:
            return False, True, None
        if instance.authority_status in {
            Person.AuthorityStatus.REJECTED,
            Person.AuthorityStatus.ARCHIVED,
            Person.AuthorityStatus.MERGED,
        }:
            return False, False, None
        return False, False, "unknown_person_status"
    if isinstance(instance, KnowledgeNode):
        if instance.status == "published":
            return True, True, None
        if instance.status in {"draft", "pending"}:
            return False, True, None
        if instance.status in {"rejected", "archived"}:
            return False, False, None
        return False, False, "unknown_knowledge_node_status"
    status = str(getattr(instance, "editorial_status", "") or "")
    if status == "published":
        return True, True, None
    if status == "draft":
        return False, True, None
    if status == "archived":
        return False, False, None
    return False, False, "unknown_editorial_status"


def _candidate(
    term,
    *,
    language: str | None,
    term_type: str,
    source_kind: str,
    trust_level: str,
    source_ref: str,
    displayable: bool,
    public_active: bool,
    admin_resolvable: bool,
    provenance: dict | None = None,
) -> TermCandidate | None:
    text = str(term or "").strip()
    if not normalize_term(text):
        return None
    return TermCandidate(
        term=text,
        language=normalize_language(language or detect_language(text)),
        term_type=str(term_type),
        source_kind=str(source_kind),
        trust_level=str(trust_level),
        source_ref=source_ref,
        displayable=bool(displayable),
        public_active=bool(public_active),
        admin_resolvable=bool(admin_resolvable),
        provenance=provenance or {},
    )


def _append(candidates: list[TermCandidate], candidate: TermCandidate | None) -> None:
    if candidate is not None:
        candidates.append(candidate)


def _generated_candidates(
    base_candidates: Iterable[TermCandidate],
) -> list[TermCandidate]:
    generated: list[TermCandidate] = []
    for base in base_candidates:
        if base.source_kind in {
            QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS,
            QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT,
        }:
            continue
        for variant in generated_search_variants(base.term):
            _append(
                generated,
                _candidate(
                    variant.term,
                    language="und",
                    term_type=QueryLexiconEntry.TermType.SEARCH_VARIANT,
                    source_kind=QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT,
                    trust_level=QueryLexiconEntry.TrustLevel.GENERATED,
                    source_ref=f"{base.source_ref}:{variant.generator}",
                    displayable=False,
                    public_active=base.public_active,
                    admin_resolvable=base.admin_resolvable,
                    provenance={
                        "generator": variant.generator,
                        "generator_version": GENERATED_VARIANT_VERSION,
                        "base_source_ref": base.source_ref,
                    },
                ),
            )
    return generated


def _known_generated_normalized(terms: Iterable[str]) -> set[str]:
    values: set[str] = set()
    for term in terms:
        values.update(variant.term for variant in generated_search_variants(term))
    return {normalize_term(value) for value in values if normalize_term(value)}


def _legacy_alias_candidates(
    values: Iterable[str],
    *,
    generated_values: set[str],
    source_ref: str,
    public_active: bool,
    admin_resolvable: bool,
) -> tuple[list[TermCandidate], dict[str, int]]:
    candidates: list[TermCandidate] = []
    audit = defaultdict(int)
    for raw in values or []:
        normalized = normalize_term(raw)
        if not normalized:
            continue
        is_generated = normalized in generated_values
        source_kind = (
            QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT
            if is_generated
            else QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
        )
        trust = (
            QueryLexiconEntry.TrustLevel.GENERATED
            if is_generated
            else QueryLexiconEntry.TrustLevel.LEGACY
        )
        audit["generated_search_variant" if is_generated else "legacy_mixed_alias"] += 1
        _append(
            candidates,
            _candidate(
                raw,
                language="und",
                term_type=QueryLexiconEntry.TermType.SEARCH_VARIANT,
                source_kind=source_kind,
                trust_level=trust,
                source_ref=source_ref,
                displayable=False,
                public_active=public_active,
                admin_resolvable=admin_resolvable,
                provenance={"legacy_mixed": not is_generated},
            ),
        )
    return candidates, dict(audit)


def _merged_person_sources(person: Person) -> list[Person]:
    result: list[Person] = []
    frontier = [person.pk]
    seen = {person.pk}
    while frontier:
        rows = list(
            Person.objects.select_related("merged_into")
            .filter(merged_into_id__in=frontier, authority_status=Person.AuthorityStatus.MERGED)
            .order_by("pk")
        )
        frontier = []
        for row in rows:
            if row.pk in seen:
                continue
            seen.add(row.pk)
            result.append(row)
            frontier.append(row.pk)
    return result


def _build_person(person: Person) -> tuple[list[TermCandidate], dict[str, int]]:
    audit = defaultdict(int)
    if person.authority_status == Person.AuthorityStatus.MERGED:
        if not _person_terminal(person):
            audit["merge_target_missing_or_invalid"] += 1
        return [], dict(audit)

    public_active, admin_resolvable, status_issue = _status_flags(person)
    if status_issue:
        audit[status_issue] += 1
    candidates: list[TermCandidate] = []
    canonical_terms = [person.preferred_name, person.original_name]
    _append(
        candidates,
        _candidate(
            person.preferred_name,
            language=detect_language(person.preferred_name),
            term_type=QueryLexiconEntry.TermType.CANONICAL,
            source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
            trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
            source_ref="catalog.Person.preferred_name",
            displayable=True,
            public_active=public_active,
            admin_resolvable=admin_resolvable,
        ),
    )
    _append(
        candidates,
        _candidate(
            person.original_name,
            language=detect_language(person.original_name),
            term_type=QueryLexiconEntry.TermType.CANONICAL,
            source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
            trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
            source_ref="catalog.Person.original_name",
            displayable=True,
            public_active=public_active,
            admin_resolvable=admin_resolvable,
        ),
    )

    for variant in person.name_variants.order_by("pk"):
        variant_public = public_active and variant.is_verified
        _append(
            candidates,
            _candidate(
                variant.name,
                language=variant.language,
                term_type=variant.variant_type,
                source_kind=QueryLexiconEntry.SourceKind.PERSON_NAME_VARIANT,
                trust_level=(
                    QueryLexiconEntry.TrustLevel.VERIFIED
                    if variant.is_verified
                    else QueryLexiconEntry.TrustLevel.UNVERIFIED
                ),
                source_ref=f"catalog.PersonNameVariant:{variant.pk}",
                displayable=variant.displayable and variant.is_verified,
                public_active=variant_public,
                admin_resolvable=admin_resolvable,
                provenance={
                    "variant_id": str(variant.pk),
                    "source_kind": variant.source_kind,
                    "source_note": variant.source_note,
                    "is_verified": variant.is_verified,
                    "created_by_id": (
                        str(variant.created_by_id) if variant.created_by_id else None
                    ),
                },
            ),
        )

    generated_values = _known_generated_normalized(canonical_terms)
    legacy, legacy_audit = _legacy_alias_candidates(
        person.aliases,
        generated_values=generated_values,
        source_ref="catalog.Person.aliases",
        public_active=public_active,
        admin_resolvable=admin_resolvable,
    )
    candidates.extend(legacy)
    for key, value in legacy_audit.items():
        audit[key] += value

    for merged in _merged_person_sources(person):
        merged_terms = [merged.preferred_name, merged.original_name]
        for field_name, value in (
            ("preferred_name", merged.preferred_name),
            ("original_name", merged.original_name),
        ):
            _append(
                candidates,
                _candidate(
                    value,
                    language=detect_language(value),
                    term_type=QueryLexiconEntry.TermType.HISTORICAL,
                    source_kind=QueryLexiconEntry.SourceKind.LEGACY_AUTHORITY_FIELD,
                    trust_level=QueryLexiconEntry.TrustLevel.VERIFIED,
                    source_ref=f"catalog.Person:{merged.pk}:{field_name}",
                    displayable=False,
                    public_active=public_active,
                    admin_resolvable=admin_resolvable,
                    provenance={"merged_person_id": str(merged.pk)},
                ),
            )
        merged_generated = _known_generated_normalized(merged_terms)
        merged_legacy, merged_audit = _legacy_alias_candidates(
            merged.aliases,
            generated_values=merged_generated,
            source_ref=f"catalog.Person:{merged.pk}:aliases",
            public_active=public_active,
            admin_resolvable=admin_resolvable,
        )
        candidates.extend(merged_legacy)
        for key, value in merged_audit.items():
            audit[key] += value
        for variant in merged.name_variants.order_by("pk"):
            _append(
                candidates,
                _candidate(
                    variant.name,
                    language=variant.language,
                    term_type=(
                        variant.variant_type
                        if variant.variant_type != PersonNameVariant.VariantType.TRANSLATION
                        else QueryLexiconEntry.TermType.HISTORICAL
                    ),
                    source_kind=QueryLexiconEntry.SourceKind.PERSON_NAME_VARIANT,
                    trust_level=(
                        QueryLexiconEntry.TrustLevel.VERIFIED
                        if variant.is_verified
                        else QueryLexiconEntry.TrustLevel.UNVERIFIED
                    ),
                    source_ref=f"catalog.PersonNameVariant:{variant.pk}",
                    displayable=False,
                    public_active=public_active and variant.is_verified,
                    admin_resolvable=admin_resolvable,
                    provenance={
                        "merged_person_id": str(merged.pk),
                        "source_kind": variant.source_kind,
                        "source_note": variant.source_note,
                        "is_verified": variant.is_verified,
                        "created_by_id": (
                            str(variant.created_by_id)
                            if variant.created_by_id
                            else None
                        ),
                    },
                ),
            )

    candidates.extend(
        _generated_candidates(candidates)
    )
    return candidates, dict(audit)


def _legacy_rows_for_node(node: KnowledgeNode):
    rows = []
    mappings = node.legacy_mappings.filter(
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED
    ).order_by("legacy_model", "legacy_id")
    for mapping in mappings:
        config = LEGACY_MODELS.get(mapping.legacy_model)
        if not config:
            rows.append((mapping, None))
            continue
        model, _entity_type = config
        rows.append((mapping, model.objects.filter(pk=mapping.legacy_id).first()))
    return rows


def _seed_alias_values(node: KnowledgeNode, legacy_rows) -> set[str]:
    values: set[str] = set()
    for mapping, instance in legacy_rows:
        if instance is None:
            continue
        if mapping.legacy_model in {"TheorySchool", "Subdiscipline"}:
            foreign_name = normalize_term(getattr(instance, "foreign_name", ""))
            if foreign_name:
                values.add(foreign_name)
        values.update(
            normalize_term(value)
            for value in (getattr(instance, "search_aliases", None) or [])
            if normalize_term(value)
        )
    return values


def _build_knowledge_node(node: KnowledgeNode) -> tuple[list[TermCandidate], dict[str, int]]:
    public_active, admin_resolvable, status_issue = _status_flags(node)
    audit = defaultdict(int)
    if status_issue:
        audit[status_issue] += 1
    candidates: list[TermCandidate] = []
    for field_name, value, language in (
        ("canonical_name_zh", node.canonical_name_zh, "zh-Hans"),
        ("canonical_name_en", node.canonical_name_en, "en"),
    ):
        _append(
            candidates,
            _candidate(
                value,
                language=language,
                term_type=QueryLexiconEntry.TermType.CANONICAL,
                source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
                trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
                source_ref=f"catalog.KnowledgeNode.{field_name}",
                displayable=True,
                public_active=public_active,
                admin_resolvable=admin_resolvable,
            ),
        )

    legacy_rows = _legacy_rows_for_node(node)
    seed_values = _seed_alias_values(node, legacy_rows)
    generated_values = _known_generated_normalized(
        [node.canonical_name_zh, node.canonical_name_en]
    )
    for alias in node.aliases.order_by("pk"):
        normalized = normalize_term(alias.alias)
        suspected_seed = normalized in seed_values
        generated_seed = suspected_seed and normalized in generated_values
        if suspected_seed:
            audit["suspected_seed_alias"] += 1
        if generated_seed:
            effective_type = QueryLexiconEntry.TermType.SEARCH_VARIANT
            source_kind = QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT
            trust = QueryLexiconEntry.TrustLevel.GENERATED
        elif suspected_seed:
            effective_type = QueryLexiconEntry.TermType.SEARCH_VARIANT
            source_kind = QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
            trust = QueryLexiconEntry.TrustLevel.LEGACY
        else:
            effective_type = alias.alias_type
            source_kind = QueryLexiconEntry.SourceKind.KNOWLEDGE_NODE_ALIAS
            trust = (
                QueryLexiconEntry.TrustLevel.VERIFIED
                if alias.is_verified
                else QueryLexiconEntry.TrustLevel.UNVERIFIED
            )
        verified_alias = trust == QueryLexiconEntry.TrustLevel.VERIFIED
        _append(
            candidates,
            _candidate(
                alias.alias,
                language=alias.language,
                term_type=effective_type,
                source_kind=source_kind,
                trust_level=trust,
                source_ref=f"catalog.KnowledgeNodeAlias:{alias.pk}",
                displayable=(
                    verified_alias
                    and effective_type != QueryLexiconEntry.TermType.HISTORICAL
                ),
                public_active=public_active and verified_alias,
                admin_resolvable=admin_resolvable,
                provenance={
                    "alias_id": str(alias.pk),
                    "declared_language": alias.language,
                    "declared_alias_type": alias.alias_type,
                    "suspected_0013_seed": suspected_seed,
                    "created_by_present": bool(alias.created_by_id),
                    "created_by_id": (
                        str(alias.created_by_id) if alias.created_by_id else None
                    ),
                },
            ),
        )

    for mapping, instance in legacy_rows:
        if instance is None:
            audit[
                "unknown_legacy_model" if mapping.legacy_model not in LEGACY_MODELS else "orphan_mapping"
            ] += 1
            continue
        source_public, source_admin, source_issue = _status_flags(instance)
        if source_issue:
            audit[source_issue] += 1
        effective_public = public_active and source_public
        effective_admin = admin_resolvable and source_admin
        values = [("name", instance.name, QueryLexiconEntry.TermType.ALIAS)]
        if hasattr(instance, "foreign_name"):
            values.append(
                ("foreign_name", instance.foreign_name, QueryLexiconEntry.TermType.TRANSLATION)
            )
        for field_name, value, term_type in values:
            _append(
                candidates,
                _candidate(
                    value,
                    language=detect_language(value),
                    term_type=term_type,
                    source_kind=QueryLexiconEntry.SourceKind.LEGACY_AUTHORITY_FIELD,
                    trust_level=(
                        QueryLexiconEntry.TrustLevel.VERIFIED
                        if source_public
                        else QueryLexiconEntry.TrustLevel.UNVERIFIED
                    ),
                    source_ref=f"catalog.{mapping.legacy_model}:{instance.pk}:{field_name}",
                    displayable=source_public,
                    public_active=effective_public,
                    admin_resolvable=effective_admin,
                    provenance={
                        "legacy_model": mapping.legacy_model,
                        "legacy_id": str(instance.pk),
                        "mapping_id": str(mapping.pk),
                        "mapping_status": mapping.migration_status,
                    },
                ),
            )
        legacy_generated = _known_generated_normalized(
            [instance.name, getattr(instance, "foreign_name", "")]
        )
        legacy_candidates, legacy_audit = _legacy_alias_candidates(
            instance.search_aliases,
            generated_values=legacy_generated,
            source_ref=f"catalog.{mapping.legacy_model}:{instance.pk}:search_aliases",
            public_active=effective_public,
            admin_resolvable=effective_admin,
        )
        candidates.extend(legacy_candidates)
        for key, value in legacy_audit.items():
            audit[key] += value

    candidates.extend(
        _generated_candidates(candidates)
    )
    return candidates, dict(audit)


def _build_named(instance) -> tuple[list[TermCandidate], dict[str, int]]:
    mapped = (
        _mapped_node_for_legacy(instance)
        if instance.__class__.__name__ in LEGACY_MODELS
        else None
    )
    if mapped:
        return [], {"mapped_legacy_identity_suppressed": 1}
    public_active, admin_resolvable, status_issue = _status_flags(instance)
    audit = defaultdict(int)
    if status_issue:
        audit[status_issue] += 1
    entity_name = instance.__class__.__name__
    candidates: list[TermCandidate] = []
    _append(
        candidates,
        _candidate(
            instance.name,
            language=detect_language(instance.name),
            term_type=QueryLexiconEntry.TermType.CANONICAL,
            source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
            trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
            source_ref=f"catalog.{entity_name}.name",
            displayable=True,
            public_active=public_active,
            admin_resolvable=admin_resolvable,
        ),
    )
    foreign_name = getattr(instance, "foreign_name", "")
    _append(
        candidates,
        _candidate(
            foreign_name,
            language=detect_language(foreign_name),
            term_type=QueryLexiconEntry.TermType.TRANSLATION,
            source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
            trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
            source_ref=f"catalog.{entity_name}.foreign_name",
            displayable=True,
            public_active=public_active,
            admin_resolvable=admin_resolvable,
        ),
    )
    generated_values = _known_generated_normalized([instance.name, foreign_name])
    legacy, legacy_audit = _legacy_alias_candidates(
        instance.search_aliases,
        generated_values=generated_values,
        source_ref=f"catalog.{entity_name}.search_aliases",
        public_active=public_active,
        admin_resolvable=admin_resolvable,
    )
    candidates.extend(legacy)
    for key, value in legacy_audit.items():
        audit[key] += value
    candidates.extend(
        _generated_candidates(candidates)
    )
    return candidates, dict(audit)


def _candidate_sort_key(candidate: TermCandidate):
    return (
        _TRUST_PRIORITY.get(candidate.trust_level, 0),
        _TERM_PRIORITY.get(candidate.term_type, 0),
        int(candidate.displayable),
        candidate.source_ref,
        candidate.term,
    )


def _merge_candidates(key: EntityKey, candidates: Iterable[TermCandidate]) -> list[dict]:
    grouped: dict[str, list[TermCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.normalized_term:
            grouped[candidate.normalized_term].append(candidate)

    entries: list[dict] = []
    for normalized_term in sorted(grouped):
        rows = sorted(grouped[normalized_term], key=_candidate_sort_key, reverse=True)
        best = rows[0]
        sources = []
        for row in sorted(rows, key=lambda item: (item.source_ref, item.term_type, item.term)):
            sources.append(
                {
                    "source_ref": row.source_ref,
                    "source_kind": row.source_kind,
                    "trust_level": row.trust_level,
                    "term": row.term,
                    "term_type": row.term_type,
                    "language": row.language,
                    "displayable": row.displayable,
                    "public_active": row.public_active,
                    "admin_resolvable": row.admin_resolvable,
                    **row.provenance,
                }
            )
        provenance = {"sources": sources, "registry_version": SOURCE_REGISTRY_VERSION}
        fingerprint_payload = {
            "entity_type": key.entity_type,
            "entity_id": str(key.entity_id),
            "normalized_term": normalized_term,
            "term": best.term,
            "language": best.language,
            "term_type": best.term_type,
            "source_kind": best.source_kind,
            "trust_level": best.trust_level,
            "displayable": any(row.displayable for row in rows),
            "public_active": any(row.public_active for row in rows),
            "admin_resolvable": any(row.admin_resolvable for row in rows),
            "sources": sources,
        }
        source_fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        entries.append(
            {
                "entity_type": key.entity_type,
                "entity_id": key.entity_id,
                "term": best.term,
                "normalized_term": normalized_term,
                "language": best.language,
                "term_type": best.term_type,
                "source_kind": best.source_kind,
                "trust_level": best.trust_level,
                "source_ref": best.source_ref,
                "source_fingerprint": source_fingerprint,
                "provenance": provenance,
                "displayable": any(row.displayable for row in rows),
                "public_active": any(row.public_active for row in rows),
                "admin_resolvable": any(row.admin_resolvable for row in rows),
            }
        )
    return entries


def build_entity(key: EntityKey) -> EntityBuild:
    model = ENTITY_MODELS.get(key.entity_type)
    if model is None:
        raise ValueError(f"未注册的 QueryLexicon entity type：{key.entity_type}")
    queryset = model.objects
    if model is Person:
        queryset = queryset.select_related("merged_into")
    instance = queryset.filter(pk=key.entity_id).first()
    if instance is None:
        return EntityBuild(key=key, entries=[], audit={"missing_entity": 1})
    if isinstance(instance, Person):
        candidates, audit = _build_person(instance)
    elif isinstance(instance, KnowledgeNode):
        candidates, audit = _build_knowledge_node(instance)
    else:
        candidates, audit = _build_named(instance)
    return EntityBuild(key=key, entries=_merge_candidates(key, candidates), audit=audit)


def describe_entity(key: EntityKey) -> dict | None:
    model = ENTITY_MODELS.get(key.entity_type)
    if model is None:
        return None
    instance = model.objects.filter(pk=key.entity_id).first()
    if instance is None:
        return None
    if isinstance(instance, Person):
        terminal = _person_terminal(instance)
        if terminal is None:
            return None
        instance = terminal
        label = instance.preferred_name
        status = instance.authority_status
    elif isinstance(instance, KnowledgeNode):
        label = instance.canonical_name_zh or instance.canonical_name_en
        status = instance.status
    else:
        label = instance.name
        status = instance.editorial_status
    return {
        "entity_type": key.entity_type,
        "entity_id": str(instance.pk),
        "canonical_label": label,
        "authority_status": status,
    }
