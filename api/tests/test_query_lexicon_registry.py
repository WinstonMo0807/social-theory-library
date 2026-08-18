from __future__ import annotations

from uuid import uuid4

import pytest

from catalog.models import (
    Concept,
    Discipline,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgePublicationStatus,
    LegacyKnowledgeMapping,
    Person,
    PersonNameVariant,
    QueryLexiconEntry,
    Subdiscipline,
    TheorySchool,
)
from catalog.services.query_lexicon.normalization import (
    generated_search_variants,
    normalize_term,
)
from catalog.services.query_lexicon.registry import EntityKey, build_entity
from catalog.services.query_lexicon.resolver import (
    ADMIN_RESOLVABLE,
    PUBLIC_ACTIVE,
    resolve_term,
)
from catalog.services.query_lexicon.sync import (
    ensure_query_lexicon_state,
    sync_entity,
)


pytestmark = pytest.mark.django_db


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _key(entity_type: str, instance) -> EntityKey:
    return EntityKey(entity_type, instance.pk)


def _build(entity_type: str, instance):
    return build_entity(_key(entity_type, instance))


def _entry(build, term: str) -> dict:
    normalized = normalize_term(term)
    matches = [
        row for row in build.entries if row["normalized_term"] == normalized
    ]
    assert len(matches) == 1, (
        f"expected one entry for {term!r}, found {len(matches)}"
    )
    return matches[0]


def _sync(*keys: EntityKey) -> None:
    ensure_query_lexicon_state()
    for key in keys:
        sync_entity(key)


def _resolved_ids(result: dict) -> set[tuple[str, str]]:
    return {
        (match["entity"]["entity_type"], match["entity"]["entity_id"])
        for match in result["matches"]
    }


@pytest.mark.parametrize(
    ("status", "public_active", "admin_resolvable"),
    [
        (Person.AuthorityStatus.DRAFT, False, True),
        (Person.AuthorityStatus.NEEDS_REVIEW, False, True),
        (Person.AuthorityStatus.VERIFIED, True, True),
        (Person.AuthorityStatus.REJECTED, False, False),
        (Person.AuthorityStatus.ARCHIVED, False, False),
    ],
)
def test_person_status_controls_public_and_admin_visibility(
    status,
    public_active,
    admin_resolvable,
):
    person = Person.objects.create(
        preferred_name=f"人物-{status}",
        authority_status=status,
    )

    entry = _entry(
        _build(QueryLexiconEntry.EntityType.PERSON, person),
        person.preferred_name,
    )

    assert entry["public_active"] is public_active
    assert entry["admin_resolvable"] is admin_resolvable
    assert entry["displayable"] is True
    assert entry["term_type"] == QueryLexiconEntry.TermType.CANONICAL
    assert entry["trust_level"] == QueryLexiconEntry.TrustLevel.AUTHORITATIVE


def test_merged_person_terms_move_to_the_terminal_survivor():
    survivor = Person.objects.create(
        preferred_name="马克斯·韦伯",
        original_name="Max Weber",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    merged = Person.objects.create(
        preferred_name="韦伯旧人物记录",
        original_name="Max Weber legacy record",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    merged_key = _key(QueryLexiconEntry.EntityType.PERSON, merged)
    survivor_key = _key(QueryLexiconEntry.EntityType.PERSON, survivor)
    _sync(merged_key)

    before = resolve_term(merged.preferred_name, scope=PUBLIC_ACTIVE)
    assert _resolved_ids(before) == {
        (QueryLexiconEntry.EntityType.PERSON, str(merged.pk))
    }

    merged.authority_status = Person.AuthorityStatus.MERGED
    merged.merged_into = survivor
    merged.save()
    _sync(merged_key, survivor_key)

    assert _build(QueryLexiconEntry.EntityType.PERSON, merged).entries == []
    survivor_entry = _entry(
        _build(QueryLexiconEntry.EntityType.PERSON, survivor),
        merged.preferred_name,
    )
    assert survivor_entry["term_type"] == QueryLexiconEntry.TermType.HISTORICAL
    assert survivor_entry["displayable"] is False
    assert survivor_entry["public_active"] is True

    after = resolve_term(merged.preferred_name, scope=PUBLIC_ACTIVE)
    assert after["ambiguous"] is False
    assert _resolved_ids(after) == {
        (QueryLexiconEntry.EntityType.PERSON, str(survivor.pk))
    }


def test_person_name_variant_verification_controls_registry_and_resolver_scope():
    person = Person.objects.create(
        preferred_name="Harriet Martineau",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    verified = PersonNameVariant.objects.create(
        person=person,
        name="哈丽雅特·马蒂诺",
        language="zh-Hans",
        variant_type=PersonNameVariant.VariantType.TRANSLATION,
        source_kind=PersonNameVariant.SourceKind.EDITORIAL,
        displayable=True,
        is_verified=True,
    )
    unverified = PersonNameVariant.objects.create(
        person=person,
        name="马蒂诺待核名",
        language="zh-Hans",
        variant_type=PersonNameVariant.VariantType.ALIAS,
        source_kind=PersonNameVariant.SourceKind.LEGACY_REVIEW,
        displayable=False,
        is_verified=False,
    )

    build = _build(QueryLexiconEntry.EntityType.PERSON, person)
    verified_entry = _entry(build, verified.name)
    assert verified_entry["term_type"] == QueryLexiconEntry.TermType.TRANSLATION
    assert verified_entry["trust_level"] == QueryLexiconEntry.TrustLevel.VERIFIED
    assert verified_entry["displayable"] is True
    assert verified_entry["public_active"] is True
    assert verified_entry["admin_resolvable"] is True

    unverified_entry = _entry(build, unverified.name)
    assert unverified_entry["term_type"] == QueryLexiconEntry.TermType.ALIAS
    assert unverified_entry["trust_level"] == QueryLexiconEntry.TrustLevel.UNVERIFIED
    assert unverified_entry["displayable"] is False
    assert unverified_entry["public_active"] is False
    assert unverified_entry["admin_resolvable"] is True

    _sync(_key(QueryLexiconEntry.EntityType.PERSON, person))
    public_result = resolve_term(verified.name, scope=PUBLIC_ACTIVE)
    assert public_result["matches"]
    assert "provenance" not in public_result["matches"][0]
    assert public_result["matches"][0]["source_ref"]
    assert resolve_term(unverified.name, scope=PUBLIC_ACTIVE)["matches"] == []
    admin_result = resolve_term(unverified.name, scope=ADMIN_RESOLVABLE)
    assert _resolved_ids(admin_result) == {
        (QueryLexiconEntry.EntityType.PERSON, str(person.pk))
    }
    assert "provenance" in admin_result["matches"][0]


def test_person_json_aliases_downgrade_generated_and_residual_values():
    person = Person.objects.create(
        preferred_name="韦伯",
        original_name="Max Weber",
        aliases=["社会学家韦伯"],
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    build = _build(QueryLexiconEntry.EntityType.PERSON, person)
    pinyin = next(
        item.term
        for item in generated_search_variants(person.preferred_name)
        if item.generator == "pinyin"
    )

    generated = _entry(build, pinyin)
    assert generated["term_type"] == QueryLexiconEntry.TermType.SEARCH_VARIANT
    assert (
        generated["source_kind"]
        == QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT
    )
    assert generated["trust_level"] == QueryLexiconEntry.TrustLevel.GENERATED
    assert generated["displayable"] is False

    residual = _entry(build, "社会学家韦伯")
    assert residual["term_type"] == QueryLexiconEntry.TermType.SEARCH_VARIANT
    assert residual["source_kind"] == QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
    assert residual["trust_level"] == QueryLexiconEntry.TrustLevel.LEGACY
    assert residual["displayable"] is False


def test_named_object_json_aliases_never_become_curated_translations():
    theory = TheorySchool.objects.create(
        name="批判理论",
        slug=_slug("critical-theory"),
        foreign_name="Critical Theory",
        search_aliases=["法兰克福学派旧称"],
        editorial_status="published",
    )
    build = _build(QueryLexiconEntry.EntityType.THEORY_SCHOOL, theory)
    pinyin = next(
        item.term
        for item in generated_search_variants(theory.name)
        if item.generator == "pinyin"
    )

    generated = _entry(build, pinyin)
    assert (
        generated["source_kind"]
        == QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT
    )
    assert generated["trust_level"] == QueryLexiconEntry.TrustLevel.GENERATED
    assert generated["term_type"] == QueryLexiconEntry.TermType.SEARCH_VARIANT
    assert generated["displayable"] is False

    residual = _entry(build, "法兰克福学派旧称")
    assert residual["source_kind"] == QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
    assert residual["trust_level"] == QueryLexiconEntry.TrustLevel.LEGACY
    assert residual["term_type"] == QueryLexiconEntry.TermType.SEARCH_VARIANT
    assert residual["displayable"] is False


@pytest.mark.parametrize(
    ("status", "public_active", "admin_resolvable"),
    [
        (KnowledgePublicationStatus.PUBLISHED, True, True),
        (KnowledgePublicationStatus.DRAFT, False, True),
        (KnowledgePublicationStatus.PENDING, False, True),
        (KnowledgePublicationStatus.REJECTED, False, False),
        (KnowledgePublicationStatus.ARCHIVED, False, False),
    ],
)
def test_knowledge_node_status_controls_public_and_admin_visibility(
    status,
    public_active,
    admin_resolvable,
):
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh=f"知识节点-{status}",
        slug=_slug("node-status"),
        status=status,
    )

    entry = _entry(
        _build(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, node),
        node.canonical_name_zh,
    )

    assert entry["public_active"] is public_active
    assert entry["admin_resolvable"] is admin_resolvable
    assert entry["displayable"] is True
    assert entry["term_type"] == QueryLexiconEntry.TermType.CANONICAL


def test_mapped_legacy_identity_is_suppressed_and_redirected_to_node():
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="新制度主义知识节点",
        slug=_slug("new-institutionalism-node"),
        status=KnowledgePublicationStatus.PUBLISHED,
    )
    legacy = TheorySchool.objects.create(
        name="旧制度学派",
        slug=_slug("old-institutionalism"),
        foreign_name="Old Institutionalism",
        editorial_status="published",
    )
    legacy_key = _key(QueryLexiconEntry.EntityType.THEORY_SCHOOL, legacy)
    node_key = _key(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, node)
    _sync(legacy_key)

    before = resolve_term(legacy.name, scope=PUBLIC_ACTIVE)
    assert _resolved_ids(before) == {
        (QueryLexiconEntry.EntityType.THEORY_SCHOOL, str(legacy.pk))
    }

    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=legacy.pk,
        node=node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    _sync(legacy_key, node_key)

    legacy_build = _build(QueryLexiconEntry.EntityType.THEORY_SCHOOL, legacy)
    assert legacy_build.entries == []
    assert legacy_build.audit == {"mapped_legacy_identity_suppressed": 1}
    redirected = _entry(
        _build(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, node),
        legacy.name,
    )
    assert (
        redirected["source_kind"]
        == QueryLexiconEntry.SourceKind.LEGACY_AUTHORITY_FIELD
    )

    after = resolve_term(legacy.name, scope=PUBLIC_ACTIVE)
    assert after["ambiguous"] is False
    assert _resolved_ids(after) == {
        (QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, str(node.pk))
    }


def test_all_migrated_legacy_models_use_knowledge_node_canonical_identity():
    discipline = Discipline.objects.create(
        name="映射测试学科",
        slug=_slug("mapping-discipline"),
        code=_slug("mapping-code"),
        editorial_status="published",
    )
    legacy_rows = [
        (
            TheorySchool.objects.create(
                name="映射理论流派",
                slug=_slug("mapped-theory"),
                editorial_status="published",
            ),
            QueryLexiconEntry.EntityType.THEORY_SCHOOL,
            KnowledgeNode.NodeType.THEORY_TRADITION,
        ),
        (
            Subdiscipline.objects.create(
                name="映射子学科",
                slug=_slug("mapped-subdiscipline"),
                discipline=discipline,
                editorial_status="published",
            ),
            QueryLexiconEntry.EntityType.SUBDISCIPLINE,
            KnowledgeNode.NodeType.SUBDISCIPLINE,
        ),
        (
            Concept.objects.create(
                name="映射概念",
                slug=_slug("mapped-concept"),
                editorial_status="published",
            ),
            QueryLexiconEntry.EntityType.CONCEPT,
            KnowledgeNode.NodeType.CONCEPT,
        ),
    ]

    for legacy, legacy_entity_type, node_type in legacy_rows:
        node = KnowledgeNode.objects.create(
            node_type=node_type,
            canonical_name_zh=f"{legacy.name}规范节点",
            slug=_slug("mapped-node"),
            status=KnowledgePublicationStatus.PUBLISHED,
        )
        LegacyKnowledgeMapping.objects.create(
            legacy_model=legacy.__class__.__name__,
            legacy_id=legacy.pk,
            node=node,
            migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
        )

        assert _build(legacy_entity_type, legacy).entries == []
        redirected = _entry(
            _build(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, node),
            legacy.name,
        )
        assert (
            redirected["entity_type"]
            == QueryLexiconEntry.EntityType.KNOWLEDGE_NODE
        )
        assert redirected["entity_id"] == node.pk


@pytest.mark.parametrize(
    "mapping_status",
    [
        LegacyKnowledgeMapping.MigrationStatus.NEEDS_REVIEW,
        LegacyKnowledgeMapping.MigrationStatus.DUPLICATE,
        LegacyKnowledgeMapping.MigrationStatus.REJECTED,
    ],
)
def test_unaccepted_legacy_mapping_does_not_merge_entities(mapping_status):
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh=f"候选目标-{mapping_status}",
        slug=_slug("candidate-target"),
        status=KnowledgePublicationStatus.PUBLISHED,
    )
    legacy = TheorySchool.objects.create(
        name=f"待审旧理论-{mapping_status}",
        slug=_slug("legacy-theory"),
        editorial_status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=legacy.pk,
        node=node,
        migration_status=mapping_status,
    )

    legacy_entry = _entry(
        _build(QueryLexiconEntry.EntityType.THEORY_SCHOOL, legacy),
        legacy.name,
    )
    assert legacy_entry["public_active"] is True
    node_terms = {
        row["normalized_term"]
        for row in _build(
            QueryLexiconEntry.EntityType.KNOWLEDGE_NODE,
            node,
        ).entries
    }
    assert normalize_term(legacy.name) not in node_terms


def test_seed_knowledge_alias_is_downgraded_from_declared_translation():
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="法兰克福传统",
        slug=_slug("frankfurt-node"),
        status=KnowledgePublicationStatus.PUBLISHED,
    )
    legacy = TheorySchool.objects.create(
        name="法兰克福学派",
        slug=_slug("frankfurt-school"),
        foreign_name="Frankfurt School",
        search_aliases=["批判社会理论"],
        editorial_status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=legacy.pk,
        node=node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    alias = KnowledgeNodeAlias.objects.create(
        node=node,
        alias="批判社会理论",
        language="zh-Hans",
        alias_type=KnowledgeNodeAlias.AliasType.TRANSLATION,
    )

    entry = _entry(
        _build(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, node),
        alias.alias,
    )

    assert entry["term_type"] == QueryLexiconEntry.TermType.SEARCH_VARIANT
    assert entry["source_kind"] == QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
    assert entry["trust_level"] == QueryLexiconEntry.TrustLevel.LEGACY
    assert entry["displayable"] is False
    alias_source = next(
        source
        for source in entry["provenance"]["sources"]
        if source["source_ref"] == f"catalog.KnowledgeNodeAlias:{alias.pk}"
    )
    assert alias_source["declared_alias_type"] == KnowledgeNodeAlias.AliasType.TRANSLATION
    assert alias_source["term_type"] == QueryLexiconEntry.TermType.SEARCH_VARIANT
    assert alias_source["suspected_0013_seed"] is True


def test_public_and_admin_resolvers_preserve_same_term_ambiguity():
    first = Person.objects.create(
        preferred_name="李明",
        original_name="Li Ming A",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    second = Person.objects.create(
        preferred_name="李明",
        original_name="Li Ming B",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    keys = (
        _key(QueryLexiconEntry.EntityType.PERSON, first),
        _key(QueryLexiconEntry.EntityType.PERSON, second),
    )
    _sync(*keys)
    expected = {
        (QueryLexiconEntry.EntityType.PERSON, str(first.pk)),
        (QueryLexiconEntry.EntityType.PERSON, str(second.pk)),
    }

    public = resolve_term("  李明  ", scope=PUBLIC_ACTIVE)
    admin = resolve_term("李明", scope=ADMIN_RESOLVABLE)

    assert public["ambiguous"] is True
    assert admin["ambiguous"] is True
    assert _resolved_ids(public) == expected
    assert _resolved_ids(admin) == expected
