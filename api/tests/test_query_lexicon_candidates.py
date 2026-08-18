from __future__ import annotations

from hashlib import sha256
from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command

from catalog.models import (
    Asset,
    Contribution,
    DocumentType,
    Edition,
    KnowledgeNode,
    KnowledgeNodeAlias,
    Page,
    Person,
    PersonNameVariant,
    QueryLexiconCandidate,
    QueryLexiconCandidateEvidence,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    QueryLexiconState,
    SemanticChunk,
    SemanticIndexJob,
    SemanticIndexVersion,
    Work,
)
from catalog.services.query_lexicon.candidates import (
    accept_query_lexicon_candidate,
    extract_explicit_pairs,
    reject_query_lexicon_candidate,
    scan_asset_for_query_lexicon_candidates,
    term_noise_reason,
)
from catalog.services.query_lexicon.registry import EntityKey
from catalog.services.query_lexicon.resolver import ADMIN_RESOLVABLE, resolve_terms
from catalog.services.query_lexicon.sync import (
    ensure_query_lexicon_state,
    process_pending_events,
    sync_entity,
)
from catalog.services.semantic_indexing import run_semantic_index_job
from ingestion.models import ProcessingJob
from ingestion.services.processing import (
    create_query_lexicon_candidate_job,
    run_query_lexicon_candidate_job,
)


pytestmark = pytest.mark.django_db


def _asset(text: str, *, title: str = "术语候选测试"):
    work = Work.objects.create(document_type=DocumentType.BOOK, title=title)
    edition = Edition.objects.create(work=work)
    digest = uuid4().hex * 2
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/test/{digest}.pdf",
        sha256=digest,
        byte_size=100,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        printed_label="1",
        text=text,
        normalized_text=text.casefold(),
        text_source=Page.TextSource.OCR,
        confidence=0.94,
    )
    document_id = sha256(f"{asset.id}:1".encode()).hexdigest()
    chunk = SemanticChunk.objects.create(
        asset=asset,
        work=work,
        order=0,
        page_start=1,
        page_end=1,
        original_text=text,
        normalized_text=text.casefold(),
        language="mixed",
        document_type=DocumentType.BOOK,
        parser_version="test-parser",
        chunk_version="test-chunk",
        document_id=document_id,
        content_hash=sha256(text.encode()).hexdigest(),
        locators=[
            {
                "page_index": 1,
                "printed_label": "1",
                "bbox": [1, 2, 3, 4],
                "text": text,
            }
        ],
        index_status=SemanticChunk.IndexStatus.READY,
    )
    return work, edition, asset, page, chunk


def _sync(entity_type: str, instance) -> None:
    ensure_query_lexicon_state()
    sync_entity(EntityKey(entity_type, instance.pk))
    process_pending_events()


def _node(*, zh: str, en: str) -> KnowledgeNode:
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh=zh,
        canonical_name_en=en,
        slug=f"candidate-{uuid4().hex}",
        status="draft",
    )
    _sync(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, node)
    return node


def _person(*, zh: str, en: str) -> Person:
    person = Person.objects.create(
        preferred_name=zh,
        original_name=en,
        authority_status=Person.AuthorityStatus.DRAFT,
    )
    _sync(QueryLexiconEntry.EntityType.PERSON, person)
    return person


def test_explicit_pair_rules_keep_original_spans_and_relation_hints():
    text = (
        "惯习（habitus）；场域 / field；资本，英文原文为 capital；"
        "社会实践又译作 practice；国际社会学协会以下简称 ISA。"
    )
    pairs, audit = extract_explicit_pairs(text)

    assert not audit.get("noise:digit_inside_word")
    observed = {(row.left, row.right, row.relation_hint) for row in pairs}
    assert ("惯习", "habitus", "translation") in observed
    assert ("场域", "field", "translation") in observed
    assert ("资本", "capital", "translation") in observed
    assert any(row.relation_hint == "historical" for row in pairs)
    assert any(row.relation_hint == "abbreviation" for row in pairs)
    assert all(text[row.start : row.end] for row in pairs)

    contextual, _audit = extract_explicit_pairs(
        "首先要感谢彼得·曼德勒（Peter Mandler）的帮助。"
    )
    assert contextual[0].left == "彼得·曼德勒"
    assert term_noise_reason("·劳伦斯") == "leading_middle_dot"


def test_unknown_pair_does_not_create_candidate_or_authority():
    ensure_query_lexicon_state()
    _work, _edition, asset, _page, _chunk = _asset("福理论（foo theory）用于说明未知对象。")

    result = scan_asset_for_query_lexicon_candidates(asset, commit=True)

    assert result["candidate_count"] == 0
    assert result["audit"]["unresolved"] == 1
    assert result["rejection_funnel"]["no_canonical_anchor_match"] == 1
    assert sum(result["rejection_funnel"].values()) == result[
        "explicit_pair_observations"
    ]
    assert QueryLexiconCandidate.objects.count() == 0
    assert KnowledgeNode.objects.count() == 0
    assert Person.objects.count() == 0


def test_person_requires_identity_corroboration_before_linking():
    person = _person(zh="布尔迪厄", en="Pierre Bourdieu")
    _work, _edition, asset, _page, _chunk = _asset("布迪厄（Pierre Bourdieu）提出了这一概念。")

    scan_asset_for_query_lexicon_candidates(asset, commit=True)

    candidate = QueryLexiconCandidate.objects.get()
    assert candidate.candidate_type == QueryLexiconCandidate.CandidateType.PERSON_NAME_VARIANT
    assert candidate.linking_status == QueryLexiconCandidate.LinkingStatus.AMBIGUOUS
    assert candidate.target_entity_id is None
    assert candidate.possible_targets[0]["entity_id"] == str(person.id)
    assert candidate.ambiguity["reason"] == "person_identity_not_corroborated"
    assert candidate.evidence_records.exists()
    assert PersonNameVariant.objects.count() == 0
    dry = scan_asset_for_query_lexicon_candidates(asset, commit=False)
    assert dry["rejection_funnel"]["person_identity_insufficient"] == 1


def test_person_contribution_allows_linked_name_variant_candidate():
    person = _person(zh="布尔迪厄", en="Pierre Bourdieu")
    _work, edition, asset, _page, _chunk = _asset("布迪厄（Pierre Bourdieu）讨论惯习。")
    Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )

    result = scan_asset_for_query_lexicon_candidates(asset, commit=True)

    candidate = QueryLexiconCandidate.objects.get()
    assert result["person_candidate_count"] == 1
    assert candidate.target_entity_id == person.id
    assert candidate.linking_status == QueryLexiconCandidate.LinkingStatus.LINKED
    assert candidate.proposed_term == "布迪厄"
    assert candidate.proposed_term_type == QueryLexiconEntry.TermType.TRANSLITERATION
    assert candidate.confidence_factors["person_identity_corroborators"] == [
        "approved_contribution_current_edition"
    ]
    evidence = candidate.evidence_records.get()
    assert evidence.evidence_text == "布迪厄（Pierre Bourdieu）讨论惯习。"
    assert evidence.page_number == 1
    assert evidence.document_id
    assert evidence.bbox == [1, 2, 3, 4]

    dry = scan_asset_for_query_lexicon_candidates(asset, commit=False)
    assert dry["rejection_funnel"]["valid_candidate_created"] == 1


def test_ambiguous_entity_is_preserved_without_forced_target():
    first = _node(zh="场域甲", en="field")
    second = _node(zh="场域乙", en="field")
    _work, _edition, asset, _page, _chunk = _asset("field（场域）在这里具有理论含义。")

    result = scan_asset_for_query_lexicon_candidates(asset, commit=True)

    candidate = QueryLexiconCandidate.objects.get()
    assert result["ambiguous_candidate_count"] == 1
    assert candidate.linking_status == QueryLexiconCandidate.LinkingStatus.AMBIGUOUS
    assert candidate.target_entity_type == QueryLexiconEntry.EntityType.KNOWLEDGE_NODE
    assert candidate.target_entity_id is None
    assert {row["entity_id"] for row in candidate.possible_targets} == {
        str(first.id),
        str(second.id),
    }

    dry = scan_asset_for_query_lexicon_candidates(asset, commit=False)
    assert dry["rejection_funnel"]["ambiguous_multi_target"] == 1

    batch = resolve_terms(
        ["field", "unknown term"],
        entity_types=[QueryLexiconEntry.EntityType.KNOWLEDGE_NODE],
        scope=ADMIN_RESOLVABLE,
    )
    assert batch["results"]["field"]["ambiguous"] is True
    assert len(batch["results"]["field"]["matches"]) == 2
    assert batch["results"]["unknown term"]["matches"] == []


def test_ocr_noise_is_rejected_before_candidate_linking():
    _node(zh="惯性结构", en="habitus")
    _work, _edition, asset, _page, _chunk = _asset("惯性结构（Bourd1eu）是 OCR 噪声。")

    result = scan_asset_for_query_lexicon_candidates(asset, commit=True)

    assert term_noise_reason("Bourd1eu") == "digit_inside_word"
    assert result["candidate_count"] == 0
    assert result["audit"]["noise:digit_inside_word"] == 1
    assert result["rejection_funnel"]["invalid_noisy_pair"] == 1
    assert result["explicit_pair_observations"] == 1


def test_rejection_funnel_separates_inactive_and_low_trust_anchors():
    archived = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="归档概念",
        canonical_name_en="archived anchor",
        slug=f"candidate-{uuid4().hex}",
        status="archived",
    )
    _sync(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, archived)
    _work1, _edition1, asset1, _page1, _chunk1 = _asset(
        "archived anchor（归档译名）只用于诊断。",
        title="归档锚点诊断",
    )

    inactive = scan_asset_for_query_lexicon_candidates(asset1, commit=False)

    assert inactive["candidate_count"] == 0
    assert inactive["rejection_funnel"]["target_not_admin_resolvable"] == 1

    node = _node(zh="低信任概念", en="trusted canonical")
    KnowledgeNodeAlias.objects.create(
        node=node,
        alias="legacy anchor",
        language="en",
        alias_type=KnowledgeNodeAlias.AliasType.TRANSLATION,
    )
    _sync(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, node)
    _work2, _edition2, asset2, _page2, _chunk2 = _asset(
        "legacy anchor（低信任译名）不得绑定。",
        title="低信任锚点诊断",
    )

    low_trust = scan_asset_for_query_lexicon_candidates(asset2, commit=False)

    assert low_trust["candidate_count"] == 0
    assert low_trust["rejection_funnel"]["low_trust_generated_only_match"] == 1


def test_rejection_funnel_marks_proposed_term_already_authoritative():
    _node(zh="惯习", en="habitus")
    _work, _edition, asset, _page, _chunk = _asset(
        "habitus（惯习）已经是同一 authority。"
    )

    result = scan_asset_for_query_lexicon_candidates(asset, commit=False)

    assert result["candidate_count"] == 0
    assert result["rejection_funnel"]["proposed_term_already_exists"] == 1


def test_candidate_dedup_merges_occurrences_and_independent_works():
    node = _node(zh="惯性结构", en="habitus")
    _work1, _edition1, first_asset, _page1, _chunk1 = _asset(
        "habitus（惯习）反复出现，随后再次写作 habitus（惯习）。",
        title="第一本证据书",
    )
    _work2, _edition2, second_asset, _page2, _chunk2 = _asset(
        "本书也明确写作 habitus（惯习）。",
        title="第二本证据书",
    )

    first = scan_asset_for_query_lexicon_candidates(first_asset, commit=True)
    second = scan_asset_for_query_lexicon_candidates(second_asset, commit=True)
    repeated = scan_asset_for_query_lexicon_candidates(first_asset, commit=True)

    assert node
    assert first["candidate_count"] == 1
    assert second["candidate_count"] == 1
    assert repeated["added_candidates"] == 0
    assert repeated["added_evidence"] == 0
    candidate = QueryLexiconCandidate.objects.get()
    assert candidate.evidence_records.count() == 3
    assert candidate.evidence_records.values("work_id").distinct().count() == 2
    assert candidate.confidence_factors["independent_work_count"] == 2


def test_rejected_candidate_is_not_reopened_by_identical_rescan(admin_user):
    _node(zh="惯性结构", en="habitus")
    _work, _edition, asset, _page, _chunk = _asset("habitus（惯习）是一种概念。")
    scan_asset_for_query_lexicon_candidates(asset, commit=True)
    candidate = QueryLexiconCandidate.objects.get()
    evidence_id = candidate.evidence_records.get().id

    rejected, repeated = reject_query_lexicon_candidate(
        candidate,
        actor=admin_user,
        reason="原文不是术语对应",
    )
    result = scan_asset_for_query_lexicon_candidates(asset, commit=True)

    rejected.refresh_from_db()
    assert repeated is False
    assert rejected.status == QueryLexiconCandidate.Status.REJECTED
    assert rejected.review_reason == "原文不是术语对应"
    assert rejected.evidence_records.get().id == evidence_id
    assert result["added_candidates"] == 0
    assert result["added_evidence"] == 0


def test_accept_knowledge_candidate_writes_authority_then_outbox_sync(admin_user):
    node = _node(zh="惯性结构", en="habitus")
    _work, _edition, asset, _page, _chunk = _asset("habitus（惯习）构成实践倾向。")
    scan_asset_for_query_lexicon_candidates(asset, commit=True)
    candidate = QueryLexiconCandidate.objects.get()
    before = QueryLexiconState.objects.get(key="default").revision
    chunk_count = SemanticChunk.objects.count()

    result = accept_query_lexicon_candidate(candidate, actor=admin_user)

    alias = KnowledgeNodeAlias.objects.get(node=node, alias="惯习")
    candidate.refresh_from_db()
    assert result.authority_created is True
    assert alias.alias_type == KnowledgeNodeAlias.AliasType.TRANSLATION
    assert alias.created_by == admin_user
    assert candidate.status == QueryLexiconCandidate.Status.ACCEPTED
    assert candidate.accepted_authority_id == alias.id
    assert QueryLexiconChangeEvent.objects.filter(processed_at__isnull=True).exists()
    assert not QueryLexiconEntry.objects.filter(normalized_term="惯习").exists()

    process_pending_events()

    state = QueryLexiconState.objects.get(key="default")
    assert state.revision == before + 1
    assert QueryLexiconEntry.objects.filter(
        generation=state.active_generation,
        entity_id=node.id,
        normalized_term="惯习",
    ).exists()
    assert SemanticChunk.objects.count() == chunk_count


def test_accept_person_candidate_is_transactional_and_idempotent(
    admin_user,
    monkeypatch,
):
    person = _person(zh="布尔迪厄", en="Pierre Bourdieu")
    _work, edition, asset, _page, _chunk = _asset("布迪厄（Pierre Bourdieu）讨论场域。")
    Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )
    scan_asset_for_query_lexicon_candidates(asset, commit=True)
    candidate = QueryLexiconCandidate.objects.get()
    original_save = PersonNameVariant.save

    def fail_once(instance, *args, **kwargs):
        raise RuntimeError("simulated authority failure")

    monkeypatch.setattr(PersonNameVariant, "save", fail_once)
    with pytest.raises(RuntimeError, match="simulated authority failure"):
        accept_query_lexicon_candidate(candidate, actor=admin_user)
    candidate.refresh_from_db()
    assert candidate.status == QueryLexiconCandidate.Status.PENDING
    assert PersonNameVariant.objects.count() == 0

    monkeypatch.setattr(PersonNameVariant, "save", original_save)
    first = accept_query_lexicon_candidate(candidate, actor=admin_user)
    second = accept_query_lexicon_candidate(candidate, actor=admin_user)

    variant = PersonNameVariant.objects.get(person=person, name="布迪厄")
    assert first.authority_created is True
    assert second.idempotent is True
    assert variant.variant_type == PersonNameVariant.VariantType.TRANSLITERATION
    assert variant.source_kind == PersonNameVariant.SourceKind.PDF_EVIDENCE
    assert str(candidate.id) in variant.source_note
    assert PersonNameVariant.objects.count() == 1


def test_existing_authority_term_accept_is_noop_for_revision(admin_user):
    node = _node(zh="惯性结构", en="habitus")
    _work, _edition, asset, _page, _chunk = _asset("habitus（惯习）是正文术语。")
    scan_asset_for_query_lexicon_candidates(asset, commit=True)
    candidate = QueryLexiconCandidate.objects.get()
    first = accept_query_lexicon_candidate(candidate, actor=admin_user)
    process_pending_events()
    revision = QueryLexiconState.objects.get(key="default").revision
    pending_before = QueryLexiconChangeEvent.objects.filter(processed_at__isnull=True).count()

    second = accept_query_lexicon_candidate(candidate, actor=admin_user)
    process_pending_events()

    assert first.authority_created is True
    assert second.idempotent is True
    assert QueryLexiconState.objects.get(key="default").revision == revision
    assert QueryLexiconChangeEvent.objects.filter(processed_at__isnull=True).count() == pending_before
    assert KnowledgeNodeAlias.objects.filter(node=node, alias="惯习").count() == 1


def test_candidate_job_is_idempotent_and_failure_does_not_change_ingestion_state(
    monkeypatch,
):
    ensure_query_lexicon_state()
    _work, edition, asset, _page, chunk = _asset("没有可解析的词对。")
    first = create_query_lexicon_candidate_job(asset)
    second = create_query_lexicon_candidate_job(asset)
    assert first.id == second.id
    assert ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.QUERY_LEXICON_CANDIDATES
    ).count() == 1

    token = str(uuid4())
    first.task_id = token
    first.status = ProcessingJob.Status.PENDING
    first.save(update_fields=["task_id", "status", "updated_at"])

    def fail_scan(*args, **kwargs):
        raise RuntimeError("simulated extraction failure")

    monkeypatch.setattr(
        "ingestion.services.processing.scan_asset_for_query_lexicon_candidates",
        fail_scan,
    )
    with pytest.raises(RuntimeError, match="simulated extraction failure"):
        run_query_lexicon_candidate_job(str(first.id), task_id=token)

    first.refresh_from_db()
    edition.refresh_from_db()
    asset.refresh_from_db()
    chunk.refresh_from_db()
    assert first.status == ProcessingJob.Status.FAILED
    assert edition.state == "draft"
    assert asset.status == Asset.Status.READY
    assert chunk.index_status == SemanticChunk.IndexStatus.READY

    retried = create_query_lexicon_candidate_job(asset, force=True)
    assert retried.id == first.id
    assert retried.status == ProcessingJob.Status.PENDING
    assert retried.task_id == ""
    assert retried.attempt == 0


def test_ambiguous_admin_target_must_be_revalidated_before_accept(admin_user):
    first = _node(zh="场域甲", en="field")
    _node(zh="场域乙", en="field")
    _work, _edition, asset, _page, _chunk = _asset("field（场域）需要人工判断。")
    scan_asset_for_query_lexicon_candidates(asset, commit=True)
    candidate = QueryLexiconCandidate.objects.get()

    with pytest.raises(ValueError, match="尚未唯一关联"):
        accept_query_lexicon_candidate(candidate, actor=admin_user)

    candidate.linking_status = QueryLexiconCandidate.LinkingStatus.LINKED
    candidate.target_entity_type = QueryLexiconEntry.EntityType.KNOWLEDGE_NODE
    candidate.target_entity_id = first.id
    candidate.save(
        update_fields=[
            "linking_status",
            "target_entity_type",
            "target_entity_id",
            "updated_at",
        ]
    )
    accepted = accept_query_lexicon_candidate(candidate, actor=admin_user)

    assert accepted.authority_created is True
    assert KnowledgeNodeAlias.objects.filter(node=first, alias="场域").exists()


def test_management_command_is_dry_run_by_default():
    _node(zh="惯性结构", en="habitus")
    _work, _edition, asset, _page, _chunk = _asset("habitus（惯习）供管理员审计。")
    output = StringIO()

    call_command(
        "extract_query_lexicon_candidates",
        "--asset-id",
        str(asset.id),
        stdout=output,
    )

    assert '"mode": "dry_run"' in output.getvalue()
    assert '"candidate_count": 1' in output.getvalue()
    assert QueryLexiconCandidate.objects.count() == 0
    assert QueryLexiconCandidateEvidence.objects.count() == 0


def test_multi_locator_chunk_uses_pair_locator_for_page_and_bbox():
    _node(zh="惯性结构", en="habitus")
    _work, _edition, asset, _page, chunk = _asset("第一段没有术语对应。")
    page_two = Page.objects.create(
        asset=asset,
        index=2,
        printed_label="27",
        text="habitus（惯习）是第二页证据。",
        normalized_text="habitus（惯习）是第二页证据。",
        text_source=Page.TextSource.OCR,
        confidence=0.91,
    )
    chunk.page_end = 2
    chunk.original_text = "第一段没有术语对应。\nhabitus（惯习）是第二页证据。"
    chunk.normalized_text = chunk.original_text.casefold()
    chunk.locators = [
        {
            "page_index": 1,
            "printed_label": "1",
            "bbox": [1, 1, 2, 2],
            "text": "第一段没有术语对应。",
        },
        {
            "page_index": 2,
            "printed_label": "27",
            "bbox": [10, 20, 30, 40],
            "text": "habitus（惯习）是第二页证据。",
        },
    ]
    chunk.save(
        update_fields=[
            "page_end",
            "original_text",
            "normalized_text",
            "locators",
            "updated_at",
        ]
    )

    scan_asset_for_query_lexicon_candidates(asset, commit=True)

    evidence = QueryLexiconCandidateEvidence.objects.get()
    assert evidence.page == page_two
    assert evidence.page_number == 2
    assert evidence.printed_page_label == "27"
    assert evidence.bbox == [10, 20, 30, 40]


def test_candidate_queue_failure_does_not_fail_semantic_job(
    settings,
    monkeypatch,
):
    ensure_query_lexicon_state()
    _work, edition, asset, _page, chunk = _asset("habitus（惯习）用于非阻塞测试。")
    SemanticIndexVersion.objects.create(
        uid=f"candidate-queue-{uuid4()}",
        provider="huggingFace",
        model_repo_id="test-model",
        status=SemanticIndexVersion.Status.ACTIVE,
    )
    settings.SEMANTIC_SEARCH_ENABLED = False
    token = str(uuid4())
    job = SemanticIndexJob.objects.create(
        operation=SemanticIndexJob.Operation.BUILD,
        status=SemanticIndexJob.Status.QUEUED,
        asset=asset,
        task_id=token,
    )
    monkeypatch.setattr(
        "catalog.services.semantic_indexing.build_semantic_chunks",
        lambda *args, **kwargs: [chunk],
    )

    def fail_queue(*args, **kwargs):
        raise RuntimeError("simulated candidate queue failure")

    monkeypatch.setattr(
        "ingestion.services.processing.queue_query_lexicon_candidate_job",
        fail_queue,
    )

    completed = run_semantic_index_job(str(job.id), task_id=token)

    edition.refresh_from_db()
    assert completed.status == SemanticIndexJob.Status.COMPLETED
    assert "simulated candidate queue failure" in completed.stats[
        "query_lexicon_candidate_warning"
    ]
    assert QueryLexiconCandidate.objects.count() == 0


def test_shared_candidate_review_serializes_pdf_evidence_and_rejects_query_candidate(
    api_client,
    admin_user,
):
    person = _person(zh="布尔迪厄", en="Pierre Bourdieu")
    _work, edition, asset, _page, _chunk = _asset(
        "布迪厄（Pierre Bourdieu）讨论惯习。"
    )
    Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )
    scan_asset_for_query_lexicon_candidates(asset, commit=True)
    candidate = QueryLexiconCandidate.objects.get()

    api_client.force_authenticate(admin_user)
    response = api_client.get(
        "/api/catalog/admin/candidate-review/",
        {"kind": "query_lexicon", "status": "pending"},
    )
    assert response.status_code == 200
    assert response.data["counts"]["query_lexicon"] == 1
    row = response.data["results"][0]
    assert row["review_kind"] == "query_lexicon"
    assert row["proposed_term"] == "布迪厄"
    assert row["evidence_count"] == 1
    assert row["evidence_records"][0]["work_title"] == "术语候选测试"
    assert row["evidence_records"][0]["evidence_text"]

    decision = api_client.post(
        f"/api/catalog/admin/candidate-review/query_lexicon/{candidate.id}/decision/",
        {"action": "reject", "reason": "身份译名暂不纳入词典。"},
        format="json",
    )
    assert decision.status_code == 200
    assert decision.data["status"] == QueryLexiconCandidate.Status.REJECTED
    assert decision.data["review_reason"] == "身份译名暂不纳入词典。"
    assert PersonNameVariant.objects.count() == 0
