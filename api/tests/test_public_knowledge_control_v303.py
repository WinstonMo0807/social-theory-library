from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

import pytest
from django.urls import resolve

from catalog.models import (
    Asset,
    DomainChangeEvent,
    DocumentRevision,
    Edition,
    EvidenceSpan,
    KnowledgeNode,
    Page,
    Passage,
    Person,
    PersonNodeRelation,
    PublicationState,
    ScholarProfile,
    TheorySchool,
    TheoryTimelineEvent,
    TimelineEventRelation,
    Work,
)
from catalog.serializers import TheoryTimelineEventSerializer
from catalog.theory_serializers import NormalizedTimelineEventSerializer
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.knowledge_studio import knowledge_object_preview_payload
from catalog.services.public_knowledge_control import (
    LEGACY_PUBLIC_DEPENDENCIES,
    build_public_control,
    page_contracts,
    public_management_coverage,
)
from catalog.services.scoped_search import public_scholar_queryset
from catalog.services.viewpoint_search import viewpoint_search
from reading.library_assistant import persist_sources
from reading.library_retrieval import _hydrate_evidence
from reading.library_serializers import LibraryMessageSourceSerializer
from reading.models import LibraryConversation, LibraryMessage
from tests.v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


def _scholar(*, seed: str, profile_status: str, authority_status: str):
    person = Person.objects.create(
        preferred_name=f"公开资格学者 {seed}",
        authority_status=authority_status,
    )
    profile = ScholarProfile.objects.create(
        person=person,
        slug=f"public-control-scholar-{seed}",
        short_description="学术位置",
        editorial_status=profile_status,
    )
    return person, profile


def _evidence_source(*, seed: str, with_passage: bool):
    digest = sha256(seed.encode("utf-8")).hexdigest()
    text = f"{seed} 的馆藏原文证据。"
    work = Work.objects.create(
        document_type="book",
        title=f"定位测试作品 {seed}",
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug=f"locator-{digest[:20]}",
        publication_year=2026,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/locator-{digest[:20]}.pdf",
        sha256=digest,
        byte_size=2048,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        access_status=Asset.AccessStatus.PUBLIC,
        is_current=True,
        extraction_method="embedded",
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        printed_label="17",
        width=595,
        height=842,
        text=text,
        normalized_text=text,
        text_source=Page.TextSource.EMBEDDED,
        confidence=0.98,
    )
    passage = None
    if with_passage:
        passage = Passage.objects.create(
            page=page,
            order=0,
            text=text,
            normalized_text=text,
            start_offset=0,
            end_offset=len(text),
            bbox_union=[72, 124, 508, 186],
        )
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        parser_name="pymupdf",
        parser_version="test-v303",
        extraction_method="embedded",
        extraction_version="test-v303",
        source_checksum=digest,
        text_checksum=sha256(text.encode("utf-8")).hexdigest(),
        is_active=True,
    )
    span = EvidenceSpan.objects.create(
        document_revision=revision,
        page=page,
        passage=passage,
        page_number=1,
        printed_page_label="17",
        start_offset=0,
        end_offset=len(text),
        bbox=[74, 126, 506, 184],
        original_text=text,
        normalized_text=text,
        language="zh-CN",
        content_hash=sha256(f"span-{seed}".encode("utf-8")).hexdigest(),
        quality=0.96,
        extraction_method="embedded",
    )
    activate_catalog_revision(
        edition,
        reader_asset=asset,
        document_revision=revision,
    )
    return work, edition, asset, page, passage, span


def test_public_page_contracts_cover_real_routes_and_report_legacy_dependencies():
    coverage = public_management_coverage()

    assert coverage["status"] == "ok"
    assert coverage["errors"] == []
    assert coverage["page_counts"] == {"scholar": 9, "theory": 7, "topic": 8}
    assert coverage["page_contract_count"] == 24
    assert all(row["percent"] == 100 for row in coverage["route_coverage"].values())
    assert all(row["percent"] == 100 for row in coverage["admin_field_coverage"].values())
    assert len(coverage["legacy_public_dependency_matrix"]) == len(
        LEGACY_PUBLIC_DEPENDENCIES
    )
    assert any(
        row["code"] == "LEGACY_PUBLIC_FALLBACK_ACTIVE"
        for row in coverage["warnings"]
    )

    contracts = [
        page
        for object_type in ("scholar", "theory", "topic")
        for page in page_contracts(object_type)
    ]
    assert len({(page.object_type, page.page_id) for page in contracts}) == len(
        contracts
    )
    non_preview_entry_pages = {
        ("theory", "discipline-entry"),
        ("theory", "scholar-entry"),
        ("theory", "topic-entry"),
    }
    for page in contracts:
        assert page.preview_support is (
            (page.object_type, page.page_id) not in non_preview_entry_pages
        )
        assert page.admin_management_destination
        assert page.modules
        for module in page.modules:
            assert module.serializer_fields
            assert module.admin_editor_section
        resolve(
            page.api.format(
                slug="public-control-probe",
                discipline_slug="public-control-discipline",
                scholar_slug="public-control-scholar",
                topic_slug="public-control-topic",
                path_slug="public-control-path",
            ).split("?", 1)[0]
        )

    scholar_modules = {
        module.module_id
        for page in page_contracts("scholar")
        for module in page.modules
    }
    theory_modules = {
        module.module_id
        for page in page_contracts("theory")
        for module in page.modules
    }
    topic_modules = {
        module.module_id
        for page in page_contracts("topic")
        for module in page.modules
    }
    assert "scholar-quote" in scholar_modules
    assert "theory-reading-paths" in theory_modules
    assert "topic-evidence" in topic_modules


def test_theory_protected_preview_exposes_real_secondary_page_inputs():
    theory = KnowledgeNode.objects.create(
        canonical_name_zh="次级页面预览理论",
        canonical_name_en="Secondary Preview Theory",
        slug="secondary-preview-theory",
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        definition="用于验证受保护预览的数据。",
        status="published",
    )

    payload = knowledge_object_preview_payload(
        object_type="theory",
        object_id=str(theory.id),
    )

    assert payload is not None
    assert payload["active_perspective"] == "published"
    assert payload["secondary_preview"]["graph"]["center"] == str(theory.id)
    assert payload["secondary_preview"]["graph"]["nodes"][0]["name"] == theory.canonical_name_zh
    assert payload["secondary_preview"]["timeline"] == []
    assert payload["secondary_preview"]["reading_paths"] == []


def test_scholar_protected_preview_includes_public_legacy_theory_fallback():
    TheorySchool.objects.create(
        name="受保护预览兼容流派",
        slug="protected-preview-legacy-school",
        symbol="兼容",
        editorial_status="published",
    )
    _person, profile = _scholar(
        seed="preview-legacy-school",
        profile_status="published",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )

    payload = knowledge_object_preview_payload(
        object_type="scholar",
        object_id=str(profile.id),
    )

    assert payload is not None
    schools = payload["secondary_preview"]["legacy_theory_schools"]
    assert any(row["slug"] == "protected-preview-legacy-school" for row in schools)


def test_published_profile_with_unverified_person_is_not_public_or_previewed_as_published(
    api_client,
    admin_user,
):
    person, profile = _scholar(
        seed="misaligned",
        profile_status="published",
        authority_status=Person.AuthorityStatus.DRAFT,
    )

    assert not public_scholar_queryset().filter(pk=profile.pk).exists()
    assert api_client.get(f"/api/catalog/scholars/{profile.slug}/").status_code == 404

    api_client.force_authenticate(admin_user)
    admin_detail = api_client.get(f"/api/catalog/admin/scholars/{profile.id}/")
    assert admin_detail.status_code == 200
    assert admin_detail.data["authority_status"] == Person.AuthorityStatus.DRAFT
    assert admin_detail.data["public_eligible"] is False
    assert admin_detail.data["public_visibility_reason"] == (
        "person_authority_not_verified"
    )

    workspace = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"selected_type": "scholar", "selected_id": str(profile.id)},
    )
    assert workspace.status_code == 200
    selection = workspace.data["studio"]["selection"]
    assert selection["preview_perspectives"]["published"]["available"] is False
    assert selection["public_control"]["eligibility"] == {
        "eligible": False,
        "profile_published": True,
        "person_authority_status": Person.AuthorityStatus.DRAFT,
        "reason": "person_authority_not_verified",
    }
    person.refresh_from_db()
    assert person.authority_status == Person.AuthorityStatus.DRAFT


def test_direct_scholar_publication_verifies_reviewable_person_and_exposes_public_page(
    api_client,
    admin_user,
):
    person, profile = _scholar(
        seed="direct-publish",
        profile_status="draft",
        authority_status=Person.AuthorityStatus.NEEDS_REVIEW,
    )
    api_client.force_authenticate(admin_user)

    published = api_client.patch(
        f"/api/catalog/admin/scholars/{profile.id}/",
        {"editorial_status": "published"},
        format="json",
    )

    assert published.status_code == 200
    person.refresh_from_db()
    profile.refresh_from_db()
    assert person.authority_status == Person.AuthorityStatus.VERIFIED
    assert profile.editorial_status == "published"
    event = DomainChangeEvent.objects.get(
        object_type="person",
        object_id=person.id,
    )
    assert event.changed_fields == ["authority_status"]
    assert published.data["public_eligible"] is True
    api_client.force_authenticate(user=None)
    assert api_client.get(f"/api/catalog/scholars/{profile.slug}/").status_code == 200


def test_editorial_revision_publication_verifies_person_in_same_publication(
    api_client,
    admin_user,
):
    person, profile = _scholar(
        seed="revision-publish",
        profile_status="draft",
        authority_status=Person.AuthorityStatus.DRAFT,
    )
    api_client.force_authenticate(admin_user)
    created = api_client.post(
        "/api/catalog/admin/editorial-revisions/",
        {
            "target_type": "scholar_profile",
            "target_id": str(profile.id),
            "patch": {"editorial_status": "published"},
            "change_note": "发布学者公开页面",
        },
        format="json",
    )
    assert created.status_code == 201

    published = api_client.post(
        f"/api/catalog/admin/editorial-revisions/{created.data['id']}/publish/",
        {},
        format="json",
    )

    assert published.status_code == 200
    person.refresh_from_db()
    profile.refresh_from_db()
    assert person.authority_status == Person.AuthorityStatus.VERIFIED
    assert profile.editorial_status == "published"
    event = DomainChangeEvent.objects.get(
        object_type="person",
        object_id=person.id,
    )
    assert event.changed_fields == ["authority_status"]
    api_client.force_authenticate(user=None)
    assert api_client.get(f"/api/catalog/scholars/{profile.slug}/").status_code == 200


def test_scholar_publication_does_not_revive_rejected_authority(
    api_client,
    admin_user,
):
    person, profile = _scholar(
        seed="rejected",
        profile_status="draft",
        authority_status=Person.AuthorityStatus.REJECTED,
    )
    api_client.force_authenticate(admin_user)

    rejected = api_client.patch(
        f"/api/catalog/admin/scholars/{profile.id}/",
        {"editorial_status": "published"},
        format="json",
    )

    assert rejected.status_code == 400
    person.refresh_from_db()
    profile.refresh_from_db()
    assert person.authority_status == Person.AuthorityStatus.REJECTED
    assert profile.editorial_status == "draft"


def test_theory_representative_scholars_require_public_scholar_identity(api_client):
    theory = KnowledgeNode.objects.create(
        canonical_name_zh="公开学者过滤理论",
        slug="public-scholar-filter-theory",
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        status="published",
    )
    verified_person, verified_profile = _scholar(
        seed="theory-verified",
        profile_status="published",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    draft_person, _draft_profile = _scholar(
        seed="theory-draft-authority",
        profile_status="published",
        authority_status=Person.AuthorityStatus.DRAFT,
    )
    for person in (verified_person, draft_person):
        PersonNodeRelation.objects.create(
            person=person,
            node=theory,
            relation_label="代表学者",
            is_representative=True,
            status="published",
        )

    response = api_client.get(f"/api/catalog/theory-system/nodes/{theory.slug}/")

    assert response.status_code == 200
    assert [row["id"] for row in response.data["representative_scholars"]] == [
        str(verified_person.id)
    ]
    assert response.data["representative_scholars"][0]["scholar_slug"] == verified_profile.slug


def test_public_timeline_serializers_hide_non_public_scholar_links():
    _person, profile = _scholar(
        seed="timeline-draft-authority",
        profile_status="published",
        authority_status=Person.AuthorityStatus.DRAFT,
    )
    event = TheoryTimelineEvent.objects.create(
        title="不应生成幽灵学者链接的事件",
        event_type=TheoryTimelineEvent.EventType.SCHOLAR,
        start_year=2026,
        scholar=profile,
        review_status="approved",
    )
    TimelineEventRelation.objects.create(
        event=event,
        scholar=profile,
        relation_type=TimelineEventRelation.RelationType.SUBJECT,
    )

    assert TheoryTimelineEventSerializer(event).data["scholar"] is None
    assert all(
        row["type"] != "scholar"
        for row in NormalizedTimelineEventSerializer(event).data["relations"]
    )


def test_scholar_public_control_reports_active_legacy_fallback():
    _person, profile = _scholar(
        seed="legacy",
        profile_status="published",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    profile.curation = {"related_theory_ids": [str(uuid4())]}
    profile.save(update_fields=["curation", "updated_at"])

    control = build_public_control(
        object_type="scholar",
        target=profile,
        published_data={"person": {"preferred_name": profile.person.preferred_name}},
        draft_data=None,
        revision=None,
    )

    assert control["legacy_fallbacks"] == [LEGACY_PUBLIC_DEPENDENCIES[2]]
    assert control["ai_status"]["publication_blocking"] is False


@pytest.mark.parametrize("with_passage", [True, False])
def test_evidence_envelope_reader_locator_resolves_to_highlightable_focus(
    api_client,
    with_passage,
):
    _work, _edition, asset, _page, passage, span = _evidence_source(
        seed=f"focus-{with_passage}",
        with_passage=with_passage,
    )

    envelope = evidence_span_envelope(span).as_dict()
    focus_id = passage.id if passage is not None else span.id
    assert envelope["locator"]["evidence_span_id"] == str(span.id)
    assert envelope["locator"]["passage_id"] == (
        str(passage.id) if passage is not None else None
    )
    assert envelope["reader_url"] == (
        f"/reader/{asset.id}?page=1&passage={focus_id}"
    )

    focus = api_client.get(f"/api/catalog/passages/{focus_id}/focus/")
    assert focus.status_code == 200
    assert focus.data["asset_id"] == str(asset.id)
    assert focus.data["page_index"] == 1
    assert focus.data["text"] == span.original_text
    if passage is None:
        assert focus.data["locator_kind"] == "evidence_span"
        assert focus.data["bbox"] == span.bbox
    else:
        assert focus.data["bbox"] == passage.bbox_union


def test_viewpoint_and_ask_share_locator_backed_reader_urls(reader_user):
    work, edition, asset, page, passage, span = _evidence_source(
        seed="viewpoint-passage",
        with_passage=True,
    )

    viewpoint = viewpoint_search(
        "馆藏原文证据",
        retrieval_backend=lambda _query, **_kwargs: {
            "search_version": "v2",
            "engine": "v2_hybrid",
            "fallback_used": False,
            "fallback_reason": "",
            "results": [
                {
                    "id": f"passage:{passage.id}",
                    "asset_id": str(asset.id),
                    "work_id": str(work.id),
                    "edition_id": str(edition.id),
                    "title": work.title,
                    "authors": [],
                    "page_start": 1,
                    "page_index": 1,
                    "snippet": span.original_text,
                    "document_type": work.document_type,
                    "language": "zh-CN",
                }
            ],
        },
        claim_search_backend=lambda _query, **_kwargs: {
            "backend": "database-fallback",
            "index_uid": "derived_claims",
            "hits": [],
        },
    )
    viewpoint_row = viewpoint["baseline"]["results"][0]
    expected_passage_url = f"/reader/{asset.id}?page=1&passage={passage.id}"
    assert viewpoint_row["reader_url"] == expected_passage_url
    assert viewpoint_row["evidence"]["reader_url"] == expected_passage_url

    _work2, _edition2, asset2, _page2, _passage2, span2 = _evidence_source(
        seed="ask-evidence-span",
        with_passage=False,
    )
    hydrated = _hydrate_evidence(
        [
            {
                "id": f"passage:{span2.id}",
                "asset_id": str(asset2.id),
                "work_id": str(_work2.id),
                "edition_id": str(_edition2.id),
                "title": _work2.title,
                "page_start": 1,
                "page_index": 1,
                "snippet": span2.original_text,
                "language": "zh-CN",
            }
        ],
        retrieval_profile="stable",
    )
    assert len(hydrated) == 1
    expected_span_url = f"/reader/{asset2.id}?page=1&passage={span2.id}"
    assert hydrated[0].reader_url == expected_span_url
    assert hydrated[0].retrieval_provenance["locator_validation"] == "evidence_span"

    conversation = LibraryConversation.objects.create(user=reader_user)
    answer = LibraryMessage.objects.create(
        conversation=conversation,
        role=LibraryMessage.Role.ASSISTANT,
        status=LibraryMessage.Status.COMPLETED,
    )
    persisted = persist_sources(answer, [hydrated[0].source_row()])
    assert len(persisted) == 1
    serialized = LibraryMessageSourceSerializer(persisted[0]).data
    assert serialized["available"] is True
    assert serialized["reader_url"] == expected_span_url
    assert persisted[0].page_id == span2.page_id
