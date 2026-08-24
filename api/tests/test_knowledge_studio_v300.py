from hashlib import sha256

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import (
    Asset,
    ClaimEvidence,
    CuratedClaim,
    DerivedClaim,
    DocumentRevision,
    EditorialRevision,
    Edition,
    EnrichmentCandidate,
    EvidenceSnippet,
    EvidenceSpan,
    KnowledgeNode,
    Page,
    Person,
    ScholarProfile,
    TheoryReviewTask,
    Topic,
    Work,
    WorkNodeRelation,
)


pytestmark = pytest.mark.django_db


def _knowledge_fixture():
    theory = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="制度理论",
        canonical_name_en="Institutional theory",
        slug="institutional-theory-studio",
        summary="解释制度如何塑造行动。",
        definition="制度由规则、规范和认知结构组成。",
        core_questions=["制度为何持续？"],
        status="published",
    )
    KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="合法性",
        slug="legitimacy-studio",
    )
    KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.DEBATE,
        canonical_name_zh="结构与行动争论",
        slug="structure-agency-debate-studio",
    )
    person = Person.objects.create(
        preferred_name="测试学者",
        original_name="Test Scholar",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    scholar = ScholarProfile.objects.create(
        person=person,
        slug="test-scholar-studio",
        short_description="制度研究者",
        editorial_status="published",
    )
    topic = Topic.objects.create(
        name="制度变迁",
        slug="institutional-change-studio",
        problem_statement="制度为什么改变？",
        editorial_status="published",
    )
    work = Work.objects.create(title="制度与行动", language="zh-CN")
    edition = Edition.objects.create(work=work, state="published")
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("knowledge-studio.pdf", b"%PDF-1.4 knowledge studio"),
        sha256=sha256(b"knowledge-studio").hexdigest(),
        byte_size=26,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        printed_label="17",
        text="制度会改变行动策略，但这种影响受到组织位置的限定。",
        normalized_text="制度会改变行动策略，但这种影响受到组织位置的限定。",
        text_source=Page.TextSource.EMBEDDED,
    )
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        parser_name="pymupdf",
        parser_version="studio-test",
        source_checksum="a" * 64,
        text_checksum="b" * 64,
        is_active=True,
    )
    evidence = EvidenceSpan.objects.create(
        document_revision=revision,
        page=page,
        page_number=1,
        printed_page_label="17",
        original_text=page.text,
        normalized_text=page.normalized_text,
        content_hash="c" * 64,
        quality=0.94,
    )
    WorkNodeRelation.objects.create(
        work=work,
        node=theory,
        role=WorkNodeRelation.Role.FOUNDATIONAL,
        is_primary=True,
        status="published",
    )
    derived = DerivedClaim.objects.create(
        document_revision=revision,
        primary_evidence=evidence,
        work=work,
        edition=edition,
        proposition="制度会改变行动策略。",
        subject="制度",
        predicate="改变",
        object="行动策略",
        claim_type=DerivedClaim.ClaimType.CAUSAL,
        attribution=DerivedClaim.Attribution.AUTHOR_CLAIM,
        prompt_key="claim_extraction",
        prompt_version="studio-v1",
        model_provider="local",
        model_name="test-model",
        quality_score=0.9,
        importance_score=0.88,
        fingerprint="d" * 64,
        shadow=True,
    )
    curated = CuratedClaim.objects.create(
        node=theory,
        kind=CuratedClaim.Kind.CORE_VIEWPOINT,
        proposition="制度影响行动，但其效应受组织位置限定。",
        status=CuratedClaim.Status.DRAFT,
        adopted_from=derived,
    )
    ClaimEvidence.objects.create(
        curated_claim=curated,
        evidence_span=evidence,
        role=ClaimEvidence.Role.PRIMARY,
        confidence=0.94,
    )
    EvidenceSnippet.objects.create(
        work=work,
        file=asset,
        node=theory,
        page_number=1,
        printed_page_label="17",
        quote=page.text,
        review_status="approved",
    )
    TheoryReviewTask.objects.create(
        task_type=TheoryReviewTask.TaskType.WORK_NODE,
        work=work,
        file=asset,
        candidate_node=theory,
        suggested_relation_type=WorkNodeRelation.Role.THEORETICAL_DEVELOPMENT,
        confidence=0.82,
        evidence_pages=[1],
        evidence_text=page.text,
    )
    EnrichmentCandidate.objects.create(
        target_type=EnrichmentCandidate.TargetType.KNOWLEDGE_NODE,
        target_id=theory.id,
        field_name="definition",
        candidate_kind=EnrichmentCandidate.CandidateKind.INTERPRETIVE,
        proposed_value={"text": "制度也包含认知脚本。"},
        source_class="scholarly_encyclopedia",
        confidence=0.8,
        conflict_group="studio-definition",
        policy_version="studio-v1",
        extraction_version="studio-v1",
        fingerprint="e" * 64,
    )
    EditorialRevision.objects.create(
        target_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
        target_id=theory.id,
        base_revision=1,
        revision=2,
        patch={"definition": "草稿定义"},
        materialized_preview={"definition": "草稿定义", "summary": theory.summary},
        changed_fields=["definition"],
        status=EditorialRevision.Status.DRAFT,
        idempotency_key="knowledge-studio-revision",
        change_note="待发布定义",
    )
    return theory, scholar, topic, derived


def test_knowledge_studio_aggregates_objects_without_promoting_machine_claims(api_client, admin_user):
    theory, _scholar, _topic, derived = _knowledge_fixture()
    before = {
        "definition": theory.definition,
        "status": theory.status,
        "derived": DerivedClaim.objects.count(),
        "curated": CuratedClaim.objects.count(),
    }
    api_client.force_authenticate(user=admin_user)

    response = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {
            "object_type": "all",
            "selected_type": "theory",
            "selected_id": str(theory.id),
            "limit": 999,
        },
    )

    assert response.status_code == 200
    studio = response.data["studio"]
    assert studio["filters"]["limit"] == 50
    assert len(studio["objects"]) <= 50
    assert {row["object_type"] for row in studio["objects"]} >= {
        "theory", "concept", "debate", "scholar", "topic"
    }
    selected = studio["selection"]
    assert selected["id"] == str(theory.id)
    assert selected["canonical"]["definition"] == before["definition"]
    assert selected["preview"]["source"] == "editorial_revision"
    assert selected["preview"]["materialized"]["definition"] == "草稿定义"
    assert selected["claims"]["derived_is_machine_only"] is True
    assert selected["claims"]["derived"][0]["id"] == str(derived.id)
    assert selected["claims"]["derived"][0]["shadow"] is True
    assert selected["claims"]["curated"][0]["status"] == "draft"
    assert selected["evidence"][0]["locator"]["printed_page_label"] == "17"
    assert selected["evidence"][0]["reader_url"].endswith("?page=1")
    assert {row["kind"] for row in selected["evidence"]} >= {"collection_text"}
    assert selected["ai_candidates"]
    assert selected["revisions"][0]["changed_fields"] == ["definition"]
    assert selected["editor_url"].startswith("/admin/theory-nodes?node=")
    assert "Knowledge Graph" in selected["frontend_impact"]["projections"]
    assert studio["read_only_aggregation"] is True
    assert studio["machine_claims_are_canonical"] is False

    theory.refresh_from_db()
    assert {
        "definition": theory.definition,
        "status": theory.status,
        "derived": DerivedClaim.objects.count(),
        "curated": CuratedClaim.objects.count(),
    } == before


def test_knowledge_studio_selection_is_type_scoped_and_reader_cannot_access(api_client, admin_user, reader_user):
    theory, scholar, topic, _derived = _knowledge_fixture()
    api_client.force_authenticate(user=admin_user)

    topic_response = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"object_type": "topic", "selected_type": "topic", "selected_id": str(topic.id)},
    )
    assert topic_response.status_code == 200
    assert topic_response.data["studio"]["selection"]["object_type"] == "topic"
    assert topic_response.data["studio"]["selection"]["editor_url"] == f"/admin/topics/{topic.id}"

    topic_search = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"object_type": "topic", "q": "制度变迁"},
    )
    assert topic_search.status_code == 200
    assert [row["id"] for row in topic_search.data["studio"]["objects"]] == [str(topic.id)]

    scholar_response = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"object_type": "scholar", "selected_type": "scholar", "selected_id": str(scholar.id)},
    )
    assert scholar_response.status_code == 200
    assert scholar_response.data["studio"]["selection"]["object_type"] == "scholar"
    assert scholar_response.data["studio"]["selection"]["editor_url"] == f"/admin/scholars/{scholar.id}"

    mismatched = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"object_type": "topic", "selected_type": "topic", "selected_id": str(theory.id)},
    )
    assert mismatched.status_code == 200
    assert mismatched.data["studio"]["selection"] is None
    assert mismatched.data["studio"]["selection_error"] == "not_found_or_type_mismatch"

    api_client.force_authenticate(user=reader_user)
    assert api_client.get("/api/catalog/admin/knowledge-workspace/").status_code in {401, 403}
