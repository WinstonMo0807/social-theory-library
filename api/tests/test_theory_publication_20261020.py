"""PDF 45–49 public theory boundaries. Written for the final acceptance run."""
from uuid import uuid4

import pytest

from catalog.models import (
    Asset, Contribution, Discipline, Edition, EvidenceSnippet, KnowledgeNode,
    KnowledgeNodeAlias, KnowledgeRelation, MediaAsset, MediaRendition, Page, Person, PersonNodeRelation,
    ReadingPath, ReadingPathItem, ScholarProfile, TheoryTimelineEvent,
    TimelineEventRelation, Work, WorkNodeRelation,
)
from catalog.services.scoped_search import SearchContext, SearchService, SearchVisibility
from catalog.theory_serializers import (
    AdminKnowledgeNodeSerializer, KnowledgeNodeDetailSerializer,
    KnowledgeNodeListSerializer, NormalizedTimelineEventSerializer,
    ReadingPathSerializer, compact_work,
)
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def theory_enabled(settings):
    settings.THEORY_SYSTEM_ENABLED = True


def node(*, status="published", name="正式概念"):
    return KnowledgeNode.objects.create(
        node_type="concept", canonical_name_zh=name,
        slug=f"theory-public-{uuid4()}", status=status,
    )


def source(*, related_node=None, activate=True, fulltext=True):
    work = Work.objects.create(title="正式版本题名", document_type="book")
    edition = Edition.objects.create(
        work=work, state="published", public_slug=f"theory-source-{uuid4()}",
        publication_year=2001, publisher="正式出版社", is_primary=True,
    )
    asset = Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        file=f"test/theory-{uuid4()}.pdf", sha256="a" * 64, page_count=1,
    )
    Page.objects.create(
        asset=asset, index=1, text="用于核对理论关系的原文。",
        text_source="embedded", width=600, height=900,
    )
    if related_node:
        WorkNodeRelation.objects.create(
            node=related_node, work=work, status="published", role="systematic_exposition",
        )
    if activate:
        activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=fulltext)
    return work, edition, asset


def test_compact_work_uses_activated_metadata_and_exact_reader():
    work, edition, asset = source(activate=False)
    author = Person.objects.create(preferred_name="正式作者", authority_status="verified")
    Contribution.objects.create(edition=edition, person=author, role="author", approved=True)
    work.cover = "public/covers/formal.jpg"
    work.save()
    revision = activate_catalog_revision(edition, reader_asset=asset)
    Work.objects.filter(pk=work.pk).update(title="待发布题名", cover="public/covers/draft.jpg")
    Edition.objects.filter(pk=edition.pk).update(
        public_slug=f"draft-{uuid4()}", publisher="待发布出版社", publication_year=2099,
    )
    Person.objects.filter(pk=author.pk).update(preferred_name="待发布姓名")
    # Preparing a replacement file does not switch the serving revision.
    Asset.objects.filter(pk=asset.pk).update(is_current=False)
    Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        file="test/replacement.pdf", sha256="b" * 64, page_count=1, version=2,
    )
    result = compact_work(work)
    assert result["title"] == "正式版本题名"
    assert result["author"] == "正式作者"
    assert result["year"] == 2001 and result["publisher"] == "正式出版社"
    assert result["slug"] == edition.public_slug
    assert result["asset_id"] == str(asset.pk)
    assert result["edition_id"] == str(edition.pk)
    assert result["catalog_revision_id"] == str(revision.pk)
    assert result["document_revision_id"] == str(revision.document_revision_id)
    assert result["reader_href"].endswith(f"revision={revision.document_revision_id}")
    assert result["cover_url"].endswith(f"?edition_id={edition.pk}")


def test_readable_pdf_does_not_depend_on_page_count_backfill():
    work, edition, asset = source(fulltext=False)
    Asset.objects.filter(pk=asset.pk).update(page_count=0)
    row = compact_work(work)
    assert row["source_status"] == "available"
    assert row["asset_id"] == str(asset.pk)
    assert row["reader_href"] == f"/reader/{asset.pk}"
    assert row["catalog_revision_id"] == str(edition.active_catalog_revision_id)
    assert row["document_revision_id"] is None


def test_media_only_cover_uses_selected_formal_edition():
    work, edition, asset = source(activate=False)
    media = MediaAsset.objects.create(
        file="test/cover-source.webp", media_type="image/webp",
        width=320, height=480, checksum="c" * 64, byte_size=100,
    )
    rendition = MediaRendition.objects.create(
        media=media, variant_key="theory-cover", kind="cover", requested_width=320,
        file="test/cover-rendition.webp", width=320, height=480,
        checksum="d" * 64, byte_size=100,
    )
    work.cover_rendition = rendition
    work.save(update_fields=["cover_rendition"])
    revision = activate_catalog_revision(edition, reader_asset=asset)
    assert not revision.snapshot["work"]["cover"]
    assert revision.snapshot["work"]["cover_media"]
    assert compact_work(work)["cover_url"] == (
        f"/api/catalog/works/{work.pk}/cover/?edition_id={edition.pk}"
    )


@pytest.mark.parametrize("unavailable", ["private", "invalid", "missing_file"])
def test_unavailable_pdf_retains_formal_bibliography(unavailable):
    work, edition, asset = source()
    changes = (
        {"access_status": "private"} if unavailable == "private"
        else {"validation_status": "invalid"} if unavailable == "invalid"
        else {"file": ""}
    )
    Asset.objects.filter(pk=asset.pk).update(**changes)
    row = compact_work(work)
    assert row["title"] == "正式版本题名"
    assert row["detail_href"] == f"/works/{edition.public_slug}"
    assert row["source_status"] == "unavailable"
    assert row["asset_id"] is None and row["reader_href"] is None


@pytest.mark.parametrize("change", ["no_revision", "not_ready", "withdrawn", "foreign_revision"])
def test_state_alone_does_not_publish_cards_counts_or_has_works(api_client, change):
    concept = node()
    work, edition, _asset = source(related_node=concept)
    if change == "no_revision":
        Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=None)
    elif change == "not_ready":
        edition.active_catalog_revision.metadata_ready = False
        edition.active_catalog_revision.save(update_fields=["metadata_ready"])
    elif change == "withdrawn":
        Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    else:
        _other_work, other, _other_asset = source()
        Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=other.active_catalog_revision)
    assert compact_work(work) is None
    assert KnowledgeNodeListSerializer(concept).data["work_count"] == 0
    result = api_client.get("/api/catalog/theory-system/nodes/", {"has_works": "true"})
    assert result.status_code == 200 and result.data["count"] == 0


def test_has_works_filters_before_pagination_and_includes_metadata_only(api_client):
    for index in range(3):
        node(name=f"无馆藏{index}")
    concept = node(name="书目已正式公开")
    source(related_node=concept, fulltext=False)
    response = api_client.get("/api/catalog/theory-system/nodes/", {"has_works": "true", "page_size": 1})
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(concept.pk)
    assert response.data["results"][0]["work_count"] == 1


def test_unverified_aliases_remain_admin_only_and_cannot_drive_public_search():
    concept = node()
    KnowledgeNodeAlias.objects.create(node=concept, alias="已确认译名", is_verified=True)
    KnowledgeNodeAlias.objects.create(node=concept, alias="待核准译名", source_kind="pdf_evidence")
    public = KnowledgeNodeDetailSerializer(concept).data
    assert [row["alias"] for row in public["aliases"]] == ["已确认译名"]
    assert public["aliases_count"] == 1
    assert len(AdminKnowledgeNodeSerializer(concept).data["aliases"]) == 2
    service = SearchService()
    assert service.queryset(SearchContext.THEORIES, "已确认译名").filter(pk=concept.pk).exists()
    assert not service.queryset(SearchContext.THEORIES, "待核准译名").exists()
    assert service.queryset(
        SearchContext.THEORIES, "待核准译名", visibility=SearchVisibility.ADMIN,
    ).filter(pk=concept.pk).exists()


@pytest.mark.parametrize("hidden", ["profile", "person", "relation", "not_representative"])
def test_representative_search_requires_every_public_boundary(api_client, hidden):
    concept = node()
    person = Person.objects.create(
        preferred_name="可检索学者", original_name="Searchable Scholar", authority_status="verified",
    )
    profile = ScholarProfile.objects.create(
        person=person, slug=f"scholar-{uuid4()}", editorial_status="published",
    )
    relation = PersonNodeRelation.objects.create(
        person=person, node=concept, status="published", is_representative=True,
    )
    endpoint = "/api/catalog/theory-system/nodes/"
    assert api_client.get(endpoint, {"q": "Searchable Scholar"}).data["count"] == 1
    if hidden == "profile":
        ScholarProfile.objects.filter(pk=profile.pk).update(editorial_status="draft")
    elif hidden == "person":
        Person.objects.filter(pk=person.pk).update(authority_status="needs_review")
    elif hidden == "relation":
        PersonNodeRelation.objects.filter(pk=relation.pk).update(status="pending")
    else:
        PersonNodeRelation.objects.filter(pk=relation.pk).update(is_representative=False)
    assert api_client.get(endpoint, {"q": "Searchable Scholar"}).data["count"] == 0
    assert KnowledgeNodeListSerializer(concept).data["representative_scholars"] == []


def test_relation_count_and_timeline_targets_hide_unpublished_endpoints():
    visible, hidden = node(), node(status="draft", name="不可公开概念")
    KnowledgeRelation.objects.create(
        source_node=visible, target_node=hidden, relation_type="related_to", status="published",
    )
    assert KnowledgeNodeListSerializer(visible).data["relation_count"] == 0
    draft_discipline = Discipline.objects.create(
        name="未发布学科", code=f"private-{uuid4()}", slug=f"private-{uuid4()}", editorial_status="draft",
    )
    event = TheoryTimelineEvent.objects.create(
        title="正式时间轴事件", event_type="publication", review_status="approved",
    )
    TimelineEventRelation.objects.create(event=event, node=visible)
    TimelineEventRelation.objects.create(event=event, node=hidden)
    TimelineEventRelation.objects.create(event=event, discipline=draft_discipline)
    draft_work, _draft_edition, _draft_asset = source(activate=False)
    TimelineEventRelation.objects.create(event=event, work=draft_work)
    work, edition, _asset = source()
    TimelineEventRelation.objects.create(event=event, work=work)
    Work.objects.filter(pk=work.pk).update(title="不得显示的新题名")
    rows = NormalizedTimelineEventSerializer(event).data["relations"]
    assert {row["id"] for row in rows} == {str(visible.pk), str(work.pk)}
    work_row = next(row for row in rows if row["type"] == "work")
    assert work_row["name"] == "正式版本题名"
    assert work_row["detail_href"] == f"/works/{edition.public_slug}"


def test_reading_path_retains_existing_node_filter_and_hides_draft_bibliography():
    visible, hidden = node(), node(status="draft")
    discipline = Discipline.objects.create(
        name="私人学科", code=f"hidden-{uuid4()}", slug=f"hidden-{uuid4()}", editorial_status="draft",
    )
    path = ReadingPath.objects.create(
        title="正式路径", slug=f"path-{uuid4()}", status="published", primary_discipline=discipline,
    )
    work, _edition, _asset = source(activate=False)
    for index, values in enumerate(({"node": visible}, {"node": hidden}, {"work": work})):
        ReadingPathItem.objects.create(reading_path=path, stage_name="阅读", reading_order=index, **values)
    public = ReadingPathSerializer(path).data
    assert len(public["items"]) == 1 and str(public["items"][0]["node"]) == str(visible.pk)
    assert public["primary_discipline"] is None and public["primary_discipline_data"] is None
    assert len(ReadingPathSerializer(path, context={"include_unpublished_items": True}).data["items"]) == 3


def test_mixed_legacy_path_item_cannot_reveal_its_private_target():
    visible, hidden = node(), node(status="draft", name="隐藏节点")
    public_work, _edition, _asset = source()
    private_work, _draft_edition, _draft_asset = source(activate=False)
    path = ReadingPath.objects.create(title="历史路径", slug=f"mixed-{uuid4()}", status="published")
    ReadingPathItem.objects.create(
        reading_path=path, stage_name="第一步", reading_order=1, node=hidden, work=public_work,
    )
    ReadingPathItem.objects.create(
        reading_path=path, stage_name="第二步", reading_order=2, node=visible, work=private_work,
    )
    rows = ReadingPathSerializer(path).data["items"]
    assert len(rows) == 2
    assert rows[0]["node"] is None and rows[0]["node_data"] is None
    assert rows[0]["work_data"]["title"] == "正式版本题名"
    assert rows[1]["work"] is None and rows[1]["work_data"] is None
    assert rows[1]["node_data"]["id"] == str(visible.pk)


@pytest.mark.parametrize("access", ["private", "registered", "restricted"])
def test_timeline_anonymous_file_excerpt_follows_file_access(access):
    _work, _edition, asset = source()
    Asset.objects.filter(pk=asset.pk).update(access_status=access)
    event = TheoryTimelineEvent.objects.create(
        title="事件", event_type="publication", review_status="approved",
        source="独立书目出处", evidence_asset=asset, evidence_page=1,
        evidence_text="受文件访问权限限制的摘录", evidence_printed_label="I",
    )
    row = NormalizedTimelineEventSerializer(event).data
    assert row["source"] == "独立书目出处"
    assert row["evidence_text"] == "" and row["reader_href"] is None
    assert row["evidence_page"] is None and row["evidence_printed_label"] == ""


def test_text_only_timeline_citation_is_not_removed():
    event = TheoryTimelineEvent.objects.create(
        title="印刷本出处", event_type="publication", review_status="approved",
        source="馆外书目", evidence_text="独立审核的文字引述",
    )
    assert NormalizedTimelineEventSerializer(event).data["evidence_text"] == "独立审核的文字引述"


def test_explicit_unavailable_graph_center_never_falls_back(api_client):
    fallback = node()
    KnowledgeNode.objects.filter(pk=fallback.pk).update(node_type="theory_tradition")
    hidden = node(status="draft")
    for center in (hidden.slug, "does-not-exist"):
        assert api_client.get("/api/catalog/theory-system/graph/", {"center": center}).status_code == 404
    assert api_client.get("/api/catalog/theory-system/graph/", {"limit": "invalid"}).status_code == 400


def test_relation_only_evidence_has_current_revision_and_focus(api_client):
    left, right = node(), node(name="关联概念")
    relation = KnowledgeRelation.objects.create(
        source_node=left, target_node=right, relation_type="related_to", status="published",
    )
    work, edition, asset = source()
    snippet = EvidenceSnippet.objects.create(
        work=work, file=asset, knowledge_relation=relation,
        page_number=1, quote="用于核对理论关系的原文。", review_status="approved",
    )
    EvidenceSnippet.objects.create(
        work=work, file=asset, knowledge_relation=relation,
        page_number=1, quote="尚待审核", review_status="suggested",
    )
    data = KnowledgeNodeDetailSerializer(left).data
    evidence = data["direct_relations"][0]["evidence"]
    assert len(evidence) == 1 and evidence[0]["id"] == str(snippet.pk)
    assert evidence[0]["document_revision_id"] == str(edition.active_catalog_revision.document_revision_id)
    assert "&revision=" in evidence[0]["reader_href"]
    focused = api_client.get(f"/api/catalog/theory-system/evidence/{snippet.pk}/focus/")
    assert focused.status_code == 200
    assert focused.data["document_revision_id"] == evidence[0]["document_revision_id"]
    assert focused.data["geometry_status"] == "unknown"
    graph = api_client.get("/api/catalog/theory-system/graph/", {"center": left.slug})
    edge = next(row for row in graph.data["edges"] if row["id"] == str(relation.pk))
    assert edge["evidence"][0]["id"] == str(snippet.pk)
    Asset.objects.filter(pk=asset.pk).update(access_status="private")
    assert KnowledgeNodeDetailSerializer(left).data["direct_relations"][0]["evidence"] == []
    assert api_client.get(f"/api/catalog/theory-system/evidence/{snippet.pk}/focus/").status_code == 404


def test_evidence_cannot_use_foreign_work_or_out_of_range_page(api_client):
    concept = node()
    work, _edition, asset = source()
    other, _other_edition, _other_asset = source()
    for evidence_work, page_number in ((other, 1), (work, 2)):
        snippet = EvidenceSnippet.objects.create(
            work=evidence_work, file=asset, node=concept, page_number=page_number,
            quote="不能作为本文件有效证据", review_status="approved",
        )
        assert api_client.get(f"/api/catalog/theory-system/evidence/{snippet.pk}/focus/").status_code == 404
    assert KnowledgeNodeDetailSerializer(concept).data["evidence"] == []
