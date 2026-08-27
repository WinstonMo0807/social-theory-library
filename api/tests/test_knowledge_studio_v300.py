from hashlib import sha256

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import (
    Asset,
    ClaimEvidence,
    CuratedClaim,
    DerivedClaim,
    Discipline,
    DocumentRevision,
    DomainChangeEvent,
    EditorialRevision,
    Edition,
    EnrichmentCandidate,
    EvidenceSnippet,
    EvidenceSpan,
    KnowledgeNode,
    Page,
    Person,
    ProjectionState,
    ReadingPath,
    ReadingPathItem,
    ReadingPathStage,
    ScholarProfile,
    Subdiscipline,
    TheoryReviewTask,
    Topic,
    Work,
    WorkNodeRelation,
    WorkSubdisciplineRelation,
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
    assert selected["editor_url"] == f"/admin/theories/{theory.id}"
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


def _integrated_studio_fixture():
    discipline = Discipline.objects.create(
        name="组织制度研究",
        code="sociology-studio-v301",
        slug="sociology-studio-v301",
        editorial_status="published",
    )
    subdiscipline = Subdiscipline.objects.create(
        name="组织社会学",
        foreign_name="Sociology of Organizations",
        slug="sociology-of-organizations-studio-v301",
        discipline=discipline,
        research_object="组织、制度与行动者之间的关系。",
        core_questions=["组织为何趋同？"],
        editorial_status="published",
    )
    work = Work.objects.create(
        document_type="book",
        title="组织与制度",
        language="zh-CN",
        is_featured=True,
    )
    edition = Edition.objects.create(
        work=work,
        version_label="中文第一版",
        publication_year=2020,
        state="published",
        public_slug="organizations-and-institutions-studio-v301",
    )
    WorkSubdisciplineRelation.objects.create(
        work=work,
        subdiscipline=subdiscipline,
        is_primary=True,
        review_status="approved",
        evidence_text="本书以组织制度为主要研究对象。",
    )
    reading_path = ReadingPath.objects.create(
        title="组织社会学入门",
        slug="organization-sociology-path-studio-v301",
        primary_discipline=discipline,
        audience="初学者",
        introduction="从组织与制度的基本问题开始。",
        learning_goal="形成组织制度分析的基本框架。",
        status="published",
    )
    stage = ReadingPathStage.objects.create(
        reading_path=reading_path,
        name="第一阶段",
        description="理解制度与组织。",
        position=0,
    )
    ReadingPathItem.objects.create(
        reading_path=reading_path,
        stage=stage,
        stage_name=stage.name,
        stage_description=stage.description,
        work=work,
        recommendation_reason="建立组织制度分析的基础。",
        prerequisite="先了解社会学基本概念。",
        reading_order=0,
        is_required=True,
    )
    return subdiscipline, reading_path, work, edition


def test_knowledge_studio_integrates_subdiscipline_reading_path_and_important_work(
    api_client,
    admin_user,
):
    subdiscipline, reading_path, work, edition = _integrated_studio_fixture()
    api_client.force_authenticate(user=admin_user)

    listing = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"object_type": "all", "limit": 50},
    )

    assert listing.status_code == 200
    studio = listing.data["studio"]
    assert {row["value"] for row in studio["object_types"]} >= {
        "subdiscipline",
        "reading_path",
        "work",
    }
    directory_keys = {
        (row["object_type"], row["id"])
        for row in studio["objects"]
    }
    assert ("subdiscipline", str(subdiscipline.id)) in directory_keys
    assert ("reading_path", str(reading_path.id)) in directory_keys
    assert ("work", str(work.id)) in directory_keys

    subdiscipline_response = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"selected_type": "subdiscipline", "selected_id": str(subdiscipline.id)},
    )
    path_response = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"selected_type": "reading_path", "selected_id": str(reading_path.id)},
    )
    work_response = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"selected_type": "work", "selected_id": str(work.id)},
    )

    assert subdiscipline_response.status_code == 200
    selected_subdiscipline = subdiscipline_response.data["studio"]["selection"]
    assert selected_subdiscipline["canonical"]["discipline"] == "组织制度研究"
    assert "精选文献导读" in selected_subdiscipline["frontend_impact"]["modules"]
    assert selected_subdiscipline["mutation_contract"]["target_type"] == "subdiscipline"
    assert selected_subdiscipline["mutation_contract"]["published_changes_require_revision"] is True
    assert any(
        row["url"] == f"/subdisciplines/{subdiscipline.slug}"
        for row in selected_subdiscipline["frontend_impact"]["targets"]
    )

    assert path_response.status_code == 200
    selected_path = path_response.data["studio"]["selection"]
    assert selected_path["canonical"]["learning_goal"] == "形成组织制度分析的基本框架。"
    assert selected_path["canonical"]["stages"][0]["items"][0]["work"] == str(work.id)
    assert selected_path["canonical"]["stages"][0]["items"][0]["prerequisite"] == "先了解社会学基本概念。"
    assert selected_path["relations"][0]["target"] == work.title
    assert selected_path["relations"][0]["prerequisite"] == "先了解社会学基本概念。"
    assert selected_path["preview_url"] == f"/theories/reading-paths/{reading_path.slug}"

    assert work_response.status_code == 200
    selected_work = work_response.data["studio"]["selection"]
    assert selected_work["canonical"]["editions"][0]["id"] == str(edition.id)
    assert selected_work["preview_url"] == f"/works/{edition.public_slug}"
    assert any(row["target"] == subdiscipline.name for row in selected_work["relations"])
    assert any(
        row["url"] == f"/works/{edition.public_slug}"
        for row in selected_work["frontend_impact"]["targets"]
    )


def test_published_reading_path_explicit_semantics_publish_through_revision(
    api_client,
    admin_user,
):
    _subdiscipline, reading_path, work, _edition = _integrated_studio_fixture()
    stage = reading_path.stages.get()
    item = reading_path.items.get()
    api_client.force_authenticate(user=admin_user)

    drafted = api_client.patch(
        f"/api/catalog/admin/theory-system/reading-paths/{reading_path.id}/",
        {
            "learning_goal": "比较组织制度理论的不同解释。",
            "stage_groups": [
                {
                    "id": str(stage.id),
                    "name": stage.name,
                    "description": stage.description,
                    "position": 0,
                    "items": [
                        {
                            "id": str(item.id),
                            "node": None,
                            "work": str(work.id),
                            "recommendation_reason": item.recommendation_reason,
                            "prerequisite": "先读组织社会学导论。",
                            "position": 0,
                            "is_required": True,
                            "editorial_note": "仅后台可见的编辑说明。",
                        }
                    ],
                }
            ],
        },
        format="json",
    )

    assert drafted.status_code == 202
    assert drafted.data["learning_goal"] == "比较组织制度理论的不同解释。"
    assert drafted.data["draft_stage_groups"][0]["items"][0]["prerequisite"] == (
        "先读组织社会学导论。"
    )
    reading_path.refresh_from_db()
    item.refresh_from_db()
    assert reading_path.learning_goal == "形成组织制度分析的基本框架。"
    assert item.prerequisite == "先了解社会学基本概念。"

    revision_id = drafted.data["editorial_revision"]["id"]
    published = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{revision_id}/publish/",
        {},
        format="json",
    )

    assert published.status_code == 200
    reading_path.refresh_from_db()
    item = reading_path.items.get()
    assert reading_path.learning_goal == "比较组织制度理论的不同解释。"
    assert item.prerequisite == "先读组织社会学导论。"
    assert item.editorial_note == "仅后台可见的编辑说明。"
    assert DomainChangeEvent.objects.filter(
        object_type="reading_path",
        object_id=reading_path.id,
        idempotency_key=f"editorial-publish:{revision_id}",
    ).exists()


def test_published_subdiscipline_edit_and_lifecycle_archive_use_editorial_revision(
    api_client,
    admin_user,
):
    subdiscipline, _reading_path, _work, _edition = _integrated_studio_fixture()
    api_client.force_authenticate(user=admin_user)

    other_discipline = Discipline.objects.create(
        name="跨学科层级检查",
        code="cross-discipline-studio-v301",
        slug="cross-discipline-studio-v301",
    )
    invalid_parent = Subdiscipline.objects.create(
        name="错误上级候选",
        slug="invalid-parent-studio-v301",
        discipline=other_discipline,
    )
    invalid_revision = api_client.post(
        "/api/catalog/admin/editorial-revisions/",
        {
            "target_type": "subdiscipline",
            "target_id": str(subdiscipline.id),
            "patch": {"parent": str(invalid_parent.id)},
        },
        format="json",
    )
    assert invalid_revision.status_code == 400
    assert "同一学科" in invalid_revision.data["detail"]

    drafted = api_client.patch(
        f"/api/catalog/admin/subdisciplines/{subdiscipline.id}/",
        {"description": "新的前台说明"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="subdiscipline-studio-draft-v301",
    )

    assert drafted.status_code == 202
    subdiscipline.refresh_from_db()
    assert subdiscipline.description == ""
    revision = EditorialRevision.objects.get(
        target_type=EditorialRevision.TargetType.SUBDISCIPLINE,
        target_id=subdiscipline.id,
        status=EditorialRevision.Status.DRAFT,
    )
    assert revision.patch == {"description": "新的前台说明"}
    assert drafted.data["editorial_revision"]["id"] == str(revision.id)

    published = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{revision.id}/publish/",
        {},
        format="json",
    )

    assert published.status_code == 200
    subdiscipline.refresh_from_db()
    assert subdiscipline.description == "新的前台说明"
    event = DomainChangeEvent.objects.get(
        object_type="subdiscipline",
        object_id=subdiscipline.id,
        idempotency_key=f"editorial-publish:{revision.id}",
    )
    assert ProjectionState.objects.filter(
        object_type="subdiscipline",
        object_id=subdiscipline.id,
        source_revision=event.canonical_revision,
    ).exists()

    archive_draft = api_client.post(
        f"/api/catalog/admin/lifecycle/subdiscipline/{subdiscipline.id}/",
        {"action": "archive"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="subdiscipline-studio-archive-v301",
    )
    assert archive_draft.status_code == 202
    subdiscipline.refresh_from_db()
    assert subdiscipline.editorial_status == "published"
    assert archive_draft.data["editorial_revision"]["status"] == "draft"
    assert archive_draft.data["editorial_revision"]["patch"] == {
        "editorial_status": "archived"
    }
