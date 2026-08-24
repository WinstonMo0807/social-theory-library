from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
import pytest

from catalog.models import (
    Asset,
    ClaimEvidence,
    Contribution,
    CuratedClaim,
    DerivedClaim,
    DocumentRevision,
    DocumentType,
    Edition,
    EvidenceSpan,
    KnowledgeNode,
    Page,
    Person,
    PublicationState,
    ScholarProfile,
    Topic,
    Work,
)


def make_public_source(title="策展观点公开测试"):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title=title,
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        public_slug=f"curated-{work.id}",
        publication_year=2026,
        state=PublicationState.PUBLISHED,
    )
    author = Person.objects.create(preferred_name="证据作者")
    Contribution.objects.create(
        edition=edition,
        person=author,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("curated.pdf", b"%PDF-1.4 curated claim"),
        sha256=str(work.id).replace("-", "") * 2,
        byte_size=24,
        page_count=12,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    page = Page.objects.create(
        asset=asset,
        index=7,
        printed_label="3",
        text="制度分类会把历史差异转化为可管理的行政对象。",
        normalized_text="制度分类会把历史差异转化为可管理的行政对象。",
        text_source=Page.TextSource.EMBEDDED,
        confidence=0.94,
    )
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        parser_name="pymupdf",
        parser_version="1.26",
        extraction_method="embedded",
        extraction_version="native-v1",
        source_checksum="a" * 64,
        text_checksum="b" * 64,
        is_active=True,
    )
    evidence = EvidenceSpan.objects.create(
        document_revision=revision,
        page=page,
        page_number=7,
        printed_page_label="3",
        original_text="制度分类会把历史差异转化为可管理的行政对象。",
        normalized_text="制度分类会把历史差异转化为可管理的行政对象。",
        language="zh-CN",
        content_hash="c" * 64,
        quality=0.94,
        extraction_method="embedded",
        is_stale=False,
    )
    return work, edition, asset, revision, evidence


@pytest.mark.django_db
def test_work_detail_exposes_only_published_evidence_backed_curated_claims(api_client):
    work, edition, asset, revision, evidence = make_public_source()
    published = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.CORE_VIEWPOINT,
        title="分类与治理",
        proposition="制度分类参与塑造治理对象。",
        editorial_note="由编辑依据馆藏原文采用。",
        status=CuratedClaim.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    ClaimEvidence.objects.create(
        curated_claim=published,
        evidence_span=evidence,
        role=ClaimEvidence.Role.PRIMARY,
        confidence=0.91,
    )
    draft = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.MAJOR_CRITICISM,
        proposition="这条草稿不能公开。",
        status=CuratedClaim.Status.DRAFT,
    )
    ClaimEvidence.objects.create(curated_claim=draft, evidence_span=evidence)
    debate = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.DEBATE_POSITION,
        proposition="争论立场由 Debate 页面消费。",
        status=CuratedClaim.Status.PUBLISHED,
    )
    ClaimEvidence.objects.create(curated_claim=debate, evidence_span=evidence)
    stale_evidence = EvidenceSpan.objects.create(
        document_revision=revision,
        page=evidence.page,
        page_number=7,
        original_text="已经失效的旧识别文本。",
        normalized_text="已经失效的旧识别文本。",
        content_hash="9" * 64,
        quality=0.2,
        is_stale=True,
        stale_reason="targeted_ocr_superseded",
        invalidated_at=timezone.now(),
    )
    stale_claim = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.MAJOR_RESPONSE,
        proposition="失效证据不能继续公开。",
        status=CuratedClaim.Status.PUBLISHED,
    )
    ClaimEvidence.objects.create(curated_claim=stale_claim, evidence_span=stale_evidence)
    DerivedClaim.objects.create(
        document_revision=revision,
        primary_evidence=evidence,
        work=work,
        edition=edition,
        proposition="机器影子 Claim 不能直接上公网。",
        claim_type=DerivedClaim.ClaimType.ASSERTION,
        prompt_key="claim-extraction",
        prompt_version="1",
        model_provider="local",
        model_name="shadow",
        fingerprint="d" * 64,
        shadow=True,
    )

    response = api_client.get(f"/api/catalog/works/{edition.public_slug}/")

    assert response.status_code == 200
    groups = response.data["curated_claims"]
    assert [row["proposition"] for row in groups["core_viewpoint"]] == [
        "制度分类参与塑造治理对象。"
    ]
    assert groups["major_criticism"] == []
    assert groups["major_response"] == []
    rendered = str(groups)
    assert "这条草稿不能公开" not in rendered
    assert "争论立场由 Debate 页面消费" not in rendered
    assert "失效证据不能继续公开" not in rendered
    assert "机器影子 Claim 不能直接上公网" not in rendered

    envelope = groups["core_viewpoint"][0]["evidence"][0]
    assert envelope["kind"] == "collection_text"
    assert envelope["text"] == evidence.original_text
    assert envelope["source"]["authors"] == ["证据作者"]
    assert envelope["source"]["asset_id"] == str(asset.id)
    assert envelope["locator"]["page"] == 7
    assert envelope["locator"]["page_id"] == str(evidence.page_id)
    assert envelope["locator"]["printed_page_label"] == "3"
    assert envelope["quality"]["stale"] is False
    assert envelope["reader_url"] == f"/reader/{asset.id}?page=7"
    assert envelope["pdf_url"] == f"/api/catalog/assets/{asset.id}/manifest/"


@pytest.mark.django_db
def test_work_detail_hides_curated_claim_without_public_reader_source(api_client):
    work, edition, _asset, _revision, _evidence = make_public_source("证据可访问性测试")
    private_edition = Edition.objects.create(
        work=work,
        public_slug=f"private-{work.id}",
        state=PublicationState.DRAFT,
        is_primary=False,
    )
    private_asset = Asset.objects.create(
        edition=private_edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("private.pdf", b"%PDF-1.4 private"),
        sha256="e" * 64,
        byte_size=16,
        page_count=1,
        status=Asset.Status.READY,
        is_current=True,
    )
    private_page = Page.objects.create(
        asset=private_asset,
        index=1,
        text="尚未公开的证据。",
        normalized_text="尚未公开的证据。",
        text_source=Page.TextSource.EMBEDDED,
    )
    private_revision = DocumentRevision.objects.create(
        asset=private_asset,
        revision=1,
        source_checksum="f" * 64,
        text_checksum="1" * 64,
    )
    private_evidence = EvidenceSpan.objects.create(
        document_revision=private_revision,
        page=private_page,
        page_number=1,
        original_text="尚未公开的证据。",
        normalized_text="尚未公开的证据。",
        content_hash="2" * 64,
    )
    claim = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.MAJOR_RESPONSE,
        proposition="没有公开 Reader 来源时不能展示。",
        status=CuratedClaim.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    ClaimEvidence.objects.create(curated_claim=claim, evidence_span=private_evidence)

    response = api_client.get(f"/api/catalog/works/{edition.public_slug}/")

    assert response.status_code == 200
    assert response.data["curated_claims"]["major_response"] == []
    assert "尚未公开的证据" not in str(response.data)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "access_status",
    [
        Asset.AccessStatus.REGISTERED,
        Asset.AccessStatus.RESTRICTED,
        Asset.AccessStatus.PRIVATE,
    ],
)
def test_anonymous_curated_claim_never_leaks_non_public_asset_text(
    api_client,
    access_status,
):
    work, edition, asset, _revision, evidence = make_public_source(
        f"受限策展证据 {access_status}"
    )
    asset.access_status = access_status
    asset.save(update_fields=["access_status", "updated_at"])
    claim = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.CORE_VIEWPOINT,
        proposition="公开页面不应展示这条受限来源命题。",
        status=CuratedClaim.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    ClaimEvidence.objects.create(
        curated_claim=claim,
        evidence_span=evidence,
        role=ClaimEvidence.Role.PRIMARY,
    )

    response = api_client.get(f"/api/catalog/works/{edition.public_slug}/")

    assert response.status_code == 200
    assert response.data["curated_claims"]["core_viewpoint"] == []
    rendered = str(response.data)
    assert claim.proposition not in rendered
    assert evidence.original_text not in rendered


@pytest.mark.django_db
def test_debate_node_exposes_human_positions_with_current_pdf_evidence(api_client):
    _work, _edition, asset, _revision, evidence = make_public_source("争论证据来源")
    debate = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.DEBATE,
        canonical_name_zh="分类是否塑造治理对象",
        slug="classification-governance-debate",
        core_questions=["制度分类是否会塑造其治理对象？"],
        status="published",
        published_at=timezone.now(),
    )
    position = CuratedClaim.objects.create(
        node=debate,
        kind=CuratedClaim.Kind.DEBATE_POSITION,
        proposition="制度分类会参与塑造治理对象。",
        status=CuratedClaim.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    ClaimEvidence.objects.create(
        curated_claim=position,
        evidence_span=evidence,
        role=ClaimEvidence.Role.SUPPORTS,
        confidence=0.92,
    )

    response = api_client.get(
        f"/api/catalog/theory-system/nodes/{debate.slug}/"
    )

    assert response.status_code == 200
    rows = response.data["curated_claims"]["debate_position"]
    assert len(rows) == 1
    assert rows[0]["position"] == "support"
    assert rows[0]["evidence"][0]["reader_url"] == f"/reader/{asset.id}?page=7"


@pytest.mark.django_db
def test_topic_and_scholar_share_the_same_evidence_backed_curated_core(api_client):
    _work, edition, _asset, _revision, evidence = make_public_source(
        "主题与学者共同证据"
    )
    topic = Topic.objects.create(
        name="制度分类",
        slug="institutional-classification",
        editorial_status="published",
    )
    person = Person.objects.create(
        preferred_name="策展学者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    scholar = ScholarProfile.objects.create(
        person=person,
        slug="curated-scholar",
        editorial_status="published",
    )
    Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
        order=2,
    )
    for target in ({"topic": topic}, {"scholar": scholar}):
        claim = CuratedClaim.objects.create(
            **target,
            kind=CuratedClaim.Kind.CORE_VIEWPOINT,
            proposition="同一 Knowledge Core 可由不同公开对象消费。",
            status=CuratedClaim.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        ClaimEvidence.objects.create(
            curated_claim=claim,
            evidence_span=evidence,
            role=ClaimEvidence.Role.PRIMARY,
        )

    topic_response = api_client.get(f"/api/catalog/topics/{topic.slug}/")
    scholar_response = api_client.get(f"/api/catalog/scholars/{scholar.slug}/")

    assert topic_response.status_code == 200
    assert scholar_response.status_code == 200
    assert topic_response.data["curated_claims"]["core_viewpoint"][0][
        "proposition"
    ] == "同一 Knowledge Core 可由不同公开对象消费。"
    assert scholar_response.data["curated_claims"]["core_viewpoint"][0][
        "proposition"
    ] == "同一 Knowledge Core 可由不同公开对象消费。"
