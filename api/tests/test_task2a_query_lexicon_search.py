from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    KnowledgeNode,
    Person,
    PersonNameVariant,
    PublicationState,
    SearchEvaluationJudgment,
    SearchEvaluationQuery,
    SearchEvaluationSet,
    SemanticChunk,
    SemanticIndexVersion,
    Work,
)
from catalog.services.passage_language import (
    detect_passage_language,
    passage_language_details,
)
from catalog.services.query_lexicon.search import resolve_search_query
from catalog.services.query_lexicon.sync import rebuild_query_lexicon
from catalog.services.semantic_search import semantic_search
from catalog.services.semantic_search import _language_filter_values, _meili_filters
from catalog.services.semantic_search_v2 import (
    _merge_ranked_lists,
    _rule_rerank_v2,
)
from catalog.services.semantic_search_v2_config import branch_weight


pytestmark = pytest.mark.django_db


def _verified_person(name: str, *, original_name: str = "") -> Person:
    return Person.objects.create(
        preferred_name=name,
        original_name=original_name,
        authority_status=Person.AuthorityStatus.VERIFIED,
    )


def _verified_variant(person: Person, name: str, *, language: str = "zh-CN", variant_type: str = "translation"):
    return PersonNameVariant.objects.create(
        person=person,
        name=name,
        language=language,
        variant_type=variant_type,
        source_kind=PersonNameVariant.SourceKind.EDITORIAL,
        displayable=True,
        is_verified=True,
    )


def test_search_resolver_keeps_original_and_resolves_verified_cross_language_terms():
    person = _verified_person("Pierre Bourdieu")
    _verified_variant(person, "布迪厄")
    _verified_variant(person, "布尔迪厄", variant_type="alias")
    cache.clear()

    rebuild_query_lexicon()
    result = resolve_search_query("布迪厄")

    assert result["normalized_original_query"] == "布迪厄"
    assert result["query_lexicon_revision"] >= 1
    assert result["matched_entities"][0]["canonical_entity"]["entity_id"] == str(person.id)
    matched = result["matched_entities"][0]
    assert sum(
        len(matched[group])
        for group in (
            "canonical_terms",
            "verified_translations",
            "verified_aliases",
            "historical_terms",
            "search_variants",
        )
    ) <= result["limits"]["max_terms_per_entity"]
    assert result["expansion_branches"][0]["branch_type"] == "original"
    assert result["expansion_branches"][0]["query"] == "布迪厄"
    assert any(
        branch["branch_type"] == "verified_translation"
        and branch["query"] == "Pierre Bourdieu"
        for branch in result["expansion_branches"][1:]
    )
    assert any(
        branch["branch_type"] == "verified_alias"
        and branch["query"] == "布尔迪厄"
        for branch in result["expansion_branches"][1:]
    )


def test_mapped_legacy_theory_term_resolves_only_to_knowledge_node():
    from catalog.models import LegacyKnowledgeMapping, TheorySchool

    legacy = TheorySchool.objects.create(
        name="映射旧流派",
        slug=f"mapped-{uuid4().hex}",
        foreign_name="Mapped School",
        editorial_status="published",
    )
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="映射规范节点",
        canonical_name_en="Mapped School",
        slug=f"node-{uuid4().hex}",
        status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=legacy.pk,
        node=node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    cache.clear()
    rebuild_query_lexicon()

    result = resolve_search_query(legacy.name)

    assert {
        (
            row["canonical_entity"]["entity_type"],
            row["canonical_entity"]["entity_id"],
        )
        for row in result["matched_entities"]
    } == {("knowledge_node", str(node.id))}


def test_cold_search_resolver_has_a_bounded_db_query_count():
    person = _verified_person("Bounded Resolver Person")
    _verified_variant(person, "有界解析人物")
    cache.clear()
    rebuild_query_lexicon()
    cache.clear()

    with CaptureQueriesContext(connection) as captured:
        result = resolve_search_query("有界解析人物")

    assert result["resolver_db_query_count"] == 4
    assert len(captured) <= 4


def test_search_resolver_preserves_ambiguity_and_suppresses_standalone_field_expansion():
    first = _verified_person("Field Scholar One")
    second = _verified_person("Field Scholar Two")
    _verified_variant(first, "field", language="en", variant_type="alias")
    _verified_variant(second, "field", language="en", variant_type="alias")
    cache.clear()

    rebuild_query_lexicon()
    result = resolve_search_query("field")

    assert result["ambiguous"] is True
    assert len(result["matched_entities"]) == 2
    assert all(
        row["ambiguity"]["expansion_suppressed"]
        for row in result["matched_entities"]
    )
    assert [branch["branch_type"] for branch in result["expansion_branches"]] == [
        "original"
    ]
    assert {row["canonical_entity"]["entity_id"] for row in result["matched_entities"]} == {
        str(first.id),
        str(second.id),
    }


def test_legacy_alias_is_retained_as_low_trust_source_and_never_verified_translation():
    person = _verified_person("Canonical Legacy Test")
    person.aliases = ["old mixed alias"]
    person.save()
    cache.clear()

    rebuild_query_lexicon()
    result = resolve_search_query("old mixed alias")
    matched = result["matched_entities"][0]

    assert matched["matched_term"]["source_kind"] == "legacy_mixed_alias"
    assert matched["matched_term"]["trust_level"] == "legacy"
    assert not any(
        term["term"] == "old mixed alias"
        for term in matched["verified_translations"]
    )
    branches = result["expansion_branches"][1:]
    assert branches
    assert all(branch["effective_trust_level"] == "legacy" for branch in branches)
    assert all(branch_weight(branch) < 0.2 for branch in branches)


def test_search_resolver_cache_key_contains_revision_and_scope():
    person = _verified_person("Revision Cache Person")
    cache.clear()
    rebuild_query_lexicon()

    first = resolve_search_query(person.preferred_name, scope="public_active")
    second = resolve_search_query(person.preferred_name, scope="public_active")
    admin = resolve_search_query(person.preferred_name, scope="admin_resolvable")
    typed = resolve_search_query(
        person.preferred_name,
        entity_type="person",
        scope="public_active",
    )

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["query_lexicon_revision"] == first["query_lexicon_revision"]
    assert admin["scope"] == "admin_resolvable"
    assert admin["cache_hit"] is False
    assert typed["entity_type"] == "person"
    assert typed["matched_entities"]


def test_query_profiles_are_deterministic_and_distinguish_exact_phrase_and_mixed_inputs():
    person = _verified_person("Pierre Bourdieu")
    _verified_variant(person, "布迪厄")
    cache.clear()
    rebuild_query_lexicon()

    assert resolve_search_query("Pierre Bourdieu")["query_profile"] == "exact_entity"
    assert resolve_search_query('"class inequality"')["query_profile"] == "lexical_phrase"
    assert resolve_search_query("class inequality")["query_profile"] == "conceptual"
    assert resolve_search_query("Bourdieu 的 habitus")["query_profile"] == "mixed_language"


def test_language_detector_distinguishes_substantial_mixing_from_names_and_citations():
    zh = "这是关于社会理论与阶级再生产的中文段落。Pierre Bourdieu 在文中被引用。"
    en = "This is an English passage about social theory and reproduction. 布迪厄只是书名中的引用。"
    mixed = (
        "这是中文理论段落，讨论制度与阶级关系，并且需要继续解释。 "
        "This English paragraph explains the mechanism and compares two traditions in detail."
    )

    assert detect_passage_language(zh) == "zh"
    assert detect_passage_language(en) == "en"
    assert detect_passage_language(mixed) == "mixed"
    assert detect_passage_language("中文理论 English theory") == "mixed"
    assert detect_passage_language("1234 — …") == "unknown"
    assert passage_language_details(zh)["latin_count"] < 20


def test_entity_and_cross_language_coverage_can_match_a_chinese_passage_for_english_query():
    chunk = SimpleNamespace(
        original_text="惯习构成阶级再生产的重要机制。",
        normalized_text="惯习构成阶级再生产的重要机制。",
        chapter_title="",
        section_title="",
        quality_flags=[],
    )
    row = {"chunk": chunk, "rrf": 1.0}
    understanding = {
        "query_lexicon": {"query_language": "en"},
        "matched_entities": [
            {
                "canonical_entity": {"entity_type": "knowledge_node", "entity_id": "1"},
                "matched_term": {"language": "en", "trust_level": "authoritative"},
                "canonical_terms": [
                    {
                        "term": "habitus",
                        "language": "en",
                        "normalized_term": "habitus",
                    },
                    {
                        "term": "惯习",
                        "language": "zh-Hans",
                        "normalized_term": "惯习",
                    },
                ],
                "verified_translations": [],
                "verified_aliases": [
                    {
                        "term": "习性",
                        "language": "zh-Hans",
                        "normalized_term": "习性",
                    }
                ],
                "ambiguity": {"is_ambiguous": False, "expansion_suppressed": False},
            }
        ],
    }
    from catalog.services.semantic_search_v2 import _entity_coverage_context

    context = _entity_coverage_context(understanding)
    reranked = _rule_rerank_v2(
        [row],
        ["habitus"],
        "mechanism",
        entity_context=context,
        query_profile="cross_language",
    )

    assert reranked[0]["literal_coverage"] == 0
    assert reranked[0]["entity_coverage"] == 1
    assert reranked[0]["cross_language_alias_coverage"] == 1
    assert reranked[0]["reranker_score"] > 1


def test_v2_retrieval_calls_bounded_verified_translation_branch_for_english_query(settings, monkeypatch):
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="惯习",
        canonical_name_en="habitus",
        slug=f"habitus-{uuid4().hex}",
        status="published",
    )
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="中文理论原文",
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug=f"cross-{uuid4().hex}",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("cross.pdf", b"%PDF-1.4\n%%EOF"),
        sha256=sha256(str(uuid4()).encode()).hexdigest(),
        status=Asset.Status.READY,
        is_current=True,
        access_status=Asset.AccessStatus.PUBLIC,
    )
    chunk = SemanticChunk.objects.create(
        asset=asset,
        work=work,
        order=0,
        page_start=1,
        page_end=1,
        original_text="惯习构成阶级再生产的重要机制。",
        normalized_text="惯习构成阶级再生产的重要机制。",
        language="zh",
        document_type=DocumentType.BOOK,
        parser_version="test",
        chunk_version="test",
        document_id=sha256(b"cross-locator").hexdigest(),
        content_hash=sha256(b"cross-content").hexdigest(),
        locators=[{"page": 1, "printed_label": "1", "bbox": []}],
        index_status=SemanticChunk.IndexStatus.READY,
    )
    cache.clear()
    rebuild_query_lexicon()
    calls: list[str] = []

    def sparse(query, *args, **kwargs):
        calls.append(query)
        return [(str(chunk.id), 0.9)] if query == "惯习" else []

    monkeypatch.setattr(
        "catalog.services.semantic_search_v2._meili_sparse_candidates",
        sparse,
    )
    monkeypatch.setattr(
        "catalog.services.semantic_search_v2._meili_dense_candidates",
        lambda query, *args, **kwargs: [],
    )
    settings.SEMANTIC_SEARCH_PROVIDER = "openAi"
    result = semantic_search(
        "How does habitus reproduce class inequality?",
        search_version="v2",
        search_profile="precision",
        filters={"_allowed_access_statuses": [Asset.AccessStatus.PUBLIC]},
        debug=True,
    )

    assert result["search_version"] == "v2"
    assert "How does habitus reproduce class inequality?" in calls
    assert "惯习" in calls
    assert result["results"][0]["id"] == str(chunk.id)
    assert result["results"][0]["debug"]["entity_coverage"] == 1
    assert result["results"][0]["debug"]["cross_language_alias_coverage"] == 1


def test_v2_evaluation_snapshot_records_lexicon_revision_and_limits(monkeypatch, admin_user):
    evaluation_set = SearchEvaluationSet.objects.create(
        name=f"Task 2A snapshot {uuid4().hex}",
        created_by=admin_user,
    )
    query = SearchEvaluationQuery.objects.create(
        evaluation_set=evaluation_set,
        query_text="habitus",
        normalized_query="habitus",
        order=0,
    )
    SearchEvaluationJudgment.objects.create(
        query=query,
        chunk_document_id="a" * 64,
        relevance=SearchEvaluationJudgment.Relevance.RELEVANT,
        created_by=admin_user,
    )
    version = SemanticIndexVersion.objects.create(
        uid=f"task2a-snapshot-{uuid4().hex}",
        provider="huggingFace",
        model_repo_id="local/test-model",
        model_revision="revision-1",
        dimensions=384,
        pooling="useModel",
        document_count=1,
        expected_document_count=1,
        status=SemanticIndexVersion.Status.READY,
    )
    runtime = {
        "enabled": True,
        "engine": "meilisearch_hybrid",
        "provider": "huggingFace",
        "model_repo_id": "local/test-model",
        "model_revision": "revision-1",
        "dimensions": 384,
        "pooling": "useModel",
        "embedder_name": "test-embedder",
    }
    from catalog.services import search_evaluation

    monkeypatch.setattr(search_evaluation, "current_semantic_runtime", lambda: runtime)
    monkeypatch.setattr(search_evaluation, "semantic_index_document_count", lambda uid: 1)
    run = search_evaluation.prepare_evaluation_run(
        evaluation_set,
        version,
        semantic_ratio=0.72,
        actor=admin_user,
        search_version="v2",
        search_profile="precision",
    )

    assert run.config_snapshot["query_lexicon_revision"] >= 0
    assert run.config_snapshot["query_lexicon_generation_id"]
    assert run.config_snapshot["ranking_profile"] == "precision"
    assert run.config_snapshot["expansion_limits"]["max_expansion_branches"] <= 4
    assert run.config_snapshot["language_detector"]["version"] == "passage-script-ratio-v1"


def test_branch_fusion_deduplicates_one_passage_and_caps_repeated_alias_bonus():
    passage = SimpleNamespace(id="one")
    sources = [
        ([(passage, 1.0)], 1.0, {"branch_id": "original:0", "branch_type": "original"}),
        *[
            ([(passage, 1.0)], 0.48, {"branch_id": f"translation:{index}", "branch_type": "verified_translation"})
            for index in range(5)
        ],
    ]

    rows, provenance = _merge_ranked_lists(
        sources,
        key=lambda value: str(value.id),
        return_provenance=True,
    )

    assert len(rows) == 1
    assert len(provenance["one"]) == 3
    assert rows[0][0] is passage


def test_v1_dispatch_does_not_call_query_lexicon(monkeypatch, settings):
    settings.SEMANTIC_SEARCH_ENABLED = False
    settings.SEMANTIC_SEARCH_V2_ENABLED = False
    monkeypatch.setattr(
        "catalog.services.query_lexicon.search.resolve_search_query",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("V1 touched QueryLexicon")),
    )

    result = semantic_search("habitus", search_version="v1")

    assert result["search_version"] == "v1"
    assert "query_lexicon_revision" not in result


def test_language_filter_accepts_legacy_work_labels_and_new_passage_labels():
    values = _language_filter_values(["zh-CN"])
    assert "zh" in values
    assert "zh-CN" in values
    assert '"zh"' in " ".join(_meili_filters({"languages": ["zh-CN"]}))


def test_new_chunk_language_is_passage_level_even_when_work_language_differs():
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="双语测试书",
        language="en",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug=f"lang-{uuid4().hex}",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("language.pdf", b"%PDF-1.4\n%%EOF"),
        sha256=sha256(str(uuid4()).encode()).hexdigest(),
        status=Asset.Status.READY,
        is_current=True,
        access_status=Asset.AccessStatus.PUBLIC,
    )
    from catalog.models import Page
    from catalog.services.semantic_chunks import build_semantic_chunks

    Page.objects.create(
        asset=asset,
        index=1,
        text="这是中文正文，讨论社会理论与阶级结构。" * 12,
        normalized_text="这是中文正文，讨论社会理论与阶级结构。" * 12,
        text_source=Page.TextSource.EMBEDDED,
        confidence=1,
    )
    chunks = build_semantic_chunks(asset, runtime_config={"model": "task2a-test"})

    assert chunks
    assert chunks[0].language == "zh"
