import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import User
from catalog.models import (
    CanonicalObjectRevision,
    Asset,
    CuratedClaim,
    DerivedClaim,
    Discipline,
    DomainChangeEvent,
    DocumentRevision,
    Edition,
    EditorialRevision,
    EvidenceSpan,
    KnowledgeNode,
    KnowledgeNodeSubdiscipline,
    KnowledgeNodeTopic,
    ProjectionState,
    PublicationState,
    Page,
    Subdiscipline,
    Topic,
    Work,
)
from catalog.services.dependency_engine import record_canonical_change


pytestmark = pytest.mark.django_db


def _user(role, suffix):
    return User.objects.create_user(
        username=f"v30-revision-{suffix}@example.org",
        email=f"v30-revision-{suffix}@example.org",
        display_name=f"编辑修订 {suffix}",
        role=role,
        password="Revision-Secure-Password-2026",
    )


def _published_work(title="正式作品原题"):
    work = Work.objects.create(document_type="book", title=title, language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        public_slug=f"revision-{work.id}",
        state=PublicationState.PUBLISHED,
        published_at=timezone.now(),
    )
    return work, edition


def test_published_work_maintenance_creates_preview_then_editor_publishes_atomically(api_client):
    editor = _user(User.Role.EDITOR, "work")
    work, edition = _published_work()
    api_client.force_authenticate(editor)

    response = api_client.patch(
        f"/api/catalog/admin/library/works/{work.id}/sections/work/?edition={edition.id}",
        {
            "data": {
                "title": "正式作品修订题",
                "document_type": "book",
                "language": "zh-CN",
                "expected_updated_at": edition.updated_at.isoformat(),
                "expected_work_updated_at": work.updated_at.isoformat(),
            }
        },
        format="json",
    )

    assert response.status_code == 202
    revision_id = response.data["editorial_revision"]["id"]
    assert response.data["editorial_revision"]["status"] == "draft"
    assert response.data["editorial_revision"]["publish_url"] == (
        f"/catalog/admin/editorial-revisions/{revision_id}/publish/"
    )
    assert response.data["data"]["work"]["title"] == "正式作品修订题"
    work.refresh_from_db()
    assert work.title == "正式作品原题"

    published = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{revision_id}/publish/",
        {},
        format="json",
    )

    assert published.status_code == 200
    work.refresh_from_db()
    assert work.title == "正式作品修订题"
    assert work.normalized_title == "正式作品修订题".casefold()
    revision = EditorialRevision.objects.get(pk=revision_id)
    assert revision.status == EditorialRevision.Status.PUBLISHED
    event = DomainChangeEvent.objects.get(
        object_type="work",
        object_id=work.id,
        change_kind=DomainChangeEvent.ChangeKind.PUBLISH,
    )
    assert event.changed_fields == ["title"]
    assert event.canonical_revision == 1
    assert ProjectionState.objects.filter(
        object_type="work",
        object_id=work.id,
        status=ProjectionState.Status.STALE,
    ).exists()


def test_published_knowledge_node_patch_stays_draft_until_single_editor_confirm(api_client):
    editor = _user(User.Role.EDITOR, "node")
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.DEBATE,
        canonical_name_zh="原争论问题",
        slug="original-debate-question",
        summary="原摘要",
        status="published",
        published_at=timezone.now(),
    )
    api_client.force_authenticate(editor)

    draft = api_client.patch(
        f"/api/catalog/admin/theory-system/nodes/{node.id}/",
        {"summary": "经过编辑确认前仍不公开的新摘要"},
        format="json",
    )

    assert draft.status_code == 202
    assert draft.data["summary"] == "经过编辑确认前仍不公开的新摘要"
    revision_id = draft.data["editorial_revision"]["id"]
    node.refresh_from_db()
    assert node.summary == "原摘要"

    published = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{revision_id}/publish/",
        {},
        format="json",
    )

    assert published.status_code == 200
    node.refresh_from_db()
    assert node.summary == "经过编辑确认前仍不公开的新摘要"
    assert node.versions.filter(change_note="知识工作室编辑草稿").exists()
    assert DomainChangeEvent.objects.filter(
        object_type="knowledge_node",
        object_id=node.id,
        canonical_revision=1,
    ).exists()


def test_published_node_normalized_taxonomy_links_publish_through_revision(api_client):
    editor = _user(User.Role.EDITOR, "node-taxonomy")
    discipline = Discipline.objects.create(
        name="3.0 修订测试学科",
        slug="political-science-revision",
        code="POL-REV",
        editorial_status="published",
    )
    subdiscipline = Subdiscipline.objects.create(
        discipline=discipline,
        name="3.0 修订测试子学科",
        slug="political-sociology-revision",
        editorial_status="published",
    )
    topic = Topic.objects.create(
        name="国家能力",
        slug="state-capacity-revision",
        editorial_status="published",
    )
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="国家理论",
        slug="state-theory-revision",
        status="published",
    )
    api_client.force_authenticate(editor)

    draft = api_client.patch(
        f"/api/catalog/admin/theory-system/nodes/{node.id}/",
        {
            "subdiscipline_links": [
                {
                    "subdiscipline_id": str(subdiscipline.id),
                    "is_primary": True,
                    "relation_role": "home",
                    "status": "published",
                }
            ],
            "topic_links": [
                {
                    "topic_id": str(topic.id),
                    "relation_label": "核心主题",
                    "status": "published",
                }
            ],
        },
        format="json",
    )

    assert draft.status_code == 202
    assert not KnowledgeNodeSubdiscipline.objects.filter(node=node).exists()
    assert not KnowledgeNodeTopic.objects.filter(node=node).exists()
    revision_id = draft.data["editorial_revision"]["id"]
    published = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{revision_id}/publish/",
        {},
        format="json",
    )
    assert published.status_code == 200
    assert KnowledgeNodeSubdiscipline.objects.filter(
        node=node,
        subdiscipline=subdiscipline,
        status="published",
    ).exists()
    assert KnowledgeNodeTopic.objects.filter(
        node=node,
        topic=topic,
        status="published",
    ).exists()


def test_reviewer_can_prepare_authority_revision_but_is_not_required_and_cannot_publish(api_client):
    reviewer = _user(User.Role.REVIEWER, "reviewer")
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="审核兼容理论",
        slug="reviewer-compatible-theory",
        status="published",
    )
    api_client.force_authenticate(reviewer)
    created = api_client.post(
        "/api/catalog/admin/editorial-revisions/",
        {
            "target_type": "knowledge_node",
            "target_id": str(node.id),
            "patch": {"definition": "审核者准备的草稿"},
            "change_note": "兼容旧审核账号",
        },
        format="json",
    )
    assert created.status_code == 201
    denied = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{created.data['id']}/publish/",
        {},
        format="json",
    )
    assert denied.status_code == 403

    editor = _user(User.Role.EDITOR, "publisher")
    api_client.force_authenticate(editor)
    allowed = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{created.data['id']}/publish/",
        {},
        format="json",
    )
    assert allowed.status_code == 200


def test_generic_revision_endpoint_covers_other_published_knowledge_targets(api_client):
    editor = _user(User.Role.EDITOR, "topic")
    topic = Topic.objects.create(
        name="原主题",
        slug="original-topic",
        description="正式主题原说明",
        editorial_status="published",
    )
    api_client.force_authenticate(editor)
    created = api_client.post(
        "/api/catalog/admin/editorial-revisions/",
        {
            "target_type": "topic",
            "target_id": str(topic.id),
            "patch": {"description": "主题编辑草稿说明"},
        },
        format="json",
    )
    assert created.status_code == 201
    topic.refresh_from_db()
    assert topic.description == "正式主题原说明"
    published = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{created.data['id']}/publish/",
        {},
        format="json",
    )
    assert published.status_code == 200
    topic.refresh_from_db()
    assert topic.description == "主题编辑草稿说明"


def test_publish_rejects_stale_base_revision_without_touching_canonical(api_client):
    editor = _user(User.Role.EDITOR, "conflict")
    work, _edition = _published_work("冲突前题名")
    api_client.force_authenticate(editor)
    created = api_client.post(
        "/api/catalog/admin/editorial-revisions/",
        {
            "target_type": "work",
            "target_id": str(work.id),
            "patch": {"title": "过期草稿题名"},
        },
        format="json",
    )
    assert created.status_code == 201
    record_canonical_change(
        object_type="work",
        object_id=work.id,
        change_kind="update",
        changed_fields=["abstract"],
        actor=editor,
        idempotency_key=f"test-external-change:{work.id}",
    )

    conflict = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{created.data['id']}/publish/",
        {},
        format="json",
    )

    assert conflict.status_code == 409
    assert conflict.data["code"] == "editorial_revision_conflict"
    work.refresh_from_db()
    assert work.title == "冲突前题名"
    assert CanonicalObjectRevision.objects.get(
        object_type="work", object_id=work.id
    ).current_revision == 1
    assert EditorialRevision.objects.get(pk=created.data["id"]).status == "draft"


def test_claim_candidate_decision_requires_permission_and_returns_bounded_remaining(api_client):
    work, edition = _published_work("Claim 决策作品")
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("claim.pdf", b"%PDF-1.4 claim"),
        sha256="a" * 64,
        byte_size=16,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        text="制度分类会塑造治理对象。",
        normalized_text="制度分类会塑造治理对象。",
        text_source=Page.TextSource.EMBEDDED,
    )
    document_revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        parser_name="pymupdf",
        parser_version="1.26",
        source_checksum="b" * 64,
        text_checksum="c" * 64,
        is_active=True,
    )
    evidence = EvidenceSpan.objects.create(
        document_revision=document_revision,
        page=page,
        page_number=1,
        original_text="制度分类会塑造治理对象。",
        normalized_text="制度分类会塑造治理对象。",
        content_hash="d" * 64,
        quality=0.92,
        is_stale=False,
    )
    claim = DerivedClaim.objects.create(
        document_revision=document_revision,
        primary_evidence=evidence,
        work=work,
        edition=edition,
        proposition="制度分类会塑造治理对象。",
        subject="制度分类",
        predicate="塑造",
        object="治理对象",
        attribution=DerivedClaim.Attribution.AUTHOR_CLAIM,
        claim_type=DerivedClaim.ClaimType.CAUSAL,
        prompt_key="claim-extraction",
        prompt_version="1",
        model_provider="local",
        model_name="shadow",
        quality_score=0.92,
        importance_score=0.88,
        fingerprint="e" * 64,
        status=DerivedClaim.Status.ACTIVE,
        shadow=True,
    )
    reader = _user(User.Role.READER, "claim-reader")
    api_client.force_authenticate(reader)
    denied = api_client.post(
        f"/api/catalog/admin/works/{work.id}/claim-candidates/{claim.id}/decision/",
        {"action": "accept"},
        format="json",
    )
    assert denied.status_code == 403

    editor = _user(User.Role.EDITOR, "claim-editor")
    api_client.force_authenticate(editor)
    accepted = api_client.post(
        f"/api/catalog/admin/works/{work.id}/claim-candidates/{claim.id}/decision/",
        {
            "action": "accept_with_edit",
            "proposition": "制度分类参与塑造治理对象。",
            "editorial_note": "编辑依据原文调整措辞。",
        },
        format="json",
    )
    assert accepted.status_code == 200
    assert accepted.data["curated_claim"]["status"] == CuratedClaim.Status.DRAFT
    assert accepted.data["curated_claim"]["proposition"] == "制度分类参与塑造治理对象。"
    assert accepted.data["curated_claim"]["evidence"][0]["locator"]["page"] == 1
    assert len(accepted.data["remaining_candidates"]) <= 5
    assert all(row["id"] != str(claim.id) for row in accepted.data["remaining_candidates"])
