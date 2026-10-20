"""PDF50/51 public data contracts; written for the final acceptance run."""
from hashlib import sha256
from uuid import uuid4

import pytest

from catalog.models import (
    Asset, Discipline, Edition, EvidenceSpan, KnowledgeNode, KnowledgeNodeAlias,
    KnowledgeNodeDiscipline, KnowledgeNodeSubdiscipline, LegacyKnowledgeMapping,
    Page, Person, PersonSubdisciplineRelation, ReadingPath, ReadingPathItem,
    ScholarProfile, Subdiscipline, TheoryDisciplineRelation, TheorySchool,
    TheorySubdisciplineRelation, Topic, TopicSubdisciplineRelation, Work,
    WorkSubdisciplineRelation,
)
from catalog.serializers import DisciplineSerializer, SubdisciplineListSerializer, SubdisciplineSerializer
from catalog.services import content_placements
from catalog.services.scoped_search import SearchContext, SearchService, SearchVisibility
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


def discipline(*, published=True):
    key = uuid4()
    return Discipline.objects.create(
        name=f"隔离测试学科 {key}", code=f"discipline-{key}", slug=f"discipline-{key}",
        editorial_status="published" if published else "draft",
    )


def branch(**kwargs):
    key = uuid4()
    values = {"discipline": discipline(), "name": f"隔离子学科 {key}",
              "slug": f"branch-{key}", "editorial_status": "published"}
    values.update(kwargs)
    return Subdiscipline.objects.create(**values)


def node_for(branch, *, kind="theory_tradition", name=None, status="published", relation_status="published"):
    node = KnowledgeNode.objects.create(
        node_type=kind, canonical_name_zh=name or f"关联知识 {uuid4()}",
        slug=f"node-{uuid4()}", status=status, summary="真实存储的合成编辑说明",
    )
    KnowledgeNodeSubdiscipline.objects.create(
        node=node, subdiscipline=branch, status=relation_status, source="隔离测试人工关系",
    )
    return node


def source(branch, *, secondary=False):
    work = Work.objects.create(title="正式子学科书目", cover="test/cover.jpg")
    edition = Edition.objects.create(
        work=work, state="published", is_primary=not secondary,
        public_slug=f"formal-{uuid4()}", version_label="正式测试版", publication_year=2002,
    )
    asset = Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        access_status="public", file="test/subdiscipline.pdf", sha256="a" * 64, page_count=1,
    )
    page = Page.objects.create(
        asset=asset, index=1, text="用于隔离测试的来源段落", width=600, height=900, text_source="embedded",
    )
    revision = activate_catalog_revision(edition, reader_asset=asset)
    relation = WorkSubdisciplineRelation.objects.create(
        subdiscipline=branch, work=work, review_status="approved", is_primary=True,
        source="已确认的文献关联", evidence_asset=asset, evidence_page=1, evidence_text=page.text,
    )
    return work, edition, asset, page, revision, relation


def test_featured_is_curated_and_filtered_before_pagination(api_client):
    selected = branch(name="精选甲", curation_level=3)
    branch(name="精选乙", curation_level=1)
    branch(name="普通丙", curation_level=0)
    branch(name="未公开精选", curation_level=10, editorial_status="draft")
    featured = api_client.get("/api/catalog/subdisciplines/", {"featured": "true"})
    assert featured.status_code == 200 and featured.data["count"] == 2
    assert featured.data["results"][0]["id"] == str(selected.pk)
    assert all(row["featured"] is True for row in featured.data["results"])
    filtered = api_client.get("/api/catalog/subdisciplines/", {"featured": "true", "q": "精选甲"})
    assert filtered.data["count"] == 1
    ordinary = api_client.get("/api/catalog/subdisciplines/", {"featured": "false"})
    assert ordinary.data["count"] == 1 and ordinary.data["results"][0]["featured"] is False
    assert api_client.get("/api/catalog/subdisciplines/", {"featured": "invalid"}).status_code == 400


def test_list_has_only_card_fields_and_no_full_relation_queries(api_client, django_assert_num_queries):
    visible = branch(research_object="真实研究对象")
    branch(discipline=discipline(published=False))
    with django_assert_num_queries(1):
        rows = SubdisciplineListSerializer(
            Subdiscipline.objects.select_related("discipline").order_by("name"), many=True,
        ).data
    fields = {"id", "name", "slug", "description", "hero_image", "research_object", "featured", "href", "discipline"}
    assert all(set(row) == fields for row in rows)
    assert next(row for row in rows if row["id"] != str(visible.pk))["discipline"] is None
    card = next(row for row in rows if row["id"] == str(visible.pk))
    assert card["discipline"] == {
        "id": str(visible.discipline_id), "name": visible.discipline.name, "slug": visible.discipline.slug,
    }
    response = api_client.get("/api/catalog/subdisciplines/")
    assert response.status_code == 200
    assert all(set(row) == fields for row in response.data["results"])


@pytest.mark.parametrize("page", ["0", "-1", "1.5", "abc", "", "1e2", "９"])
def test_invalid_works_page_is_400(api_client, page):
    target = branch()
    response = api_client.get(f"/api/catalog/subdisciplines/{target.slug}/", {"works_page": page})
    assert response.status_code == 400


def test_empty_work_pagination_defaults_for_public_and_admin_preview(api_client):
    target = branch()
    expected = {"count": 0, "page": 1, "total_pages": 1}
    assert SubdisciplineSerializer(target).data["works_pagination"] == expected
    assert SubdisciplineSerializer(target, context={"include_unpublished_items": True}).data["works_pagination"] == expected
    endpoint = f"/api/catalog/subdisciplines/{target.slug}/"
    assert api_client.get(endpoint).data["works_pagination"] == expected
    assert api_client.get(endpoint, {"works_page": "2"}).status_code == 404
    assert api_client.get(endpoint, {"works_page": "9999999999999999999999999"}).status_code == 404


def test_work_pages_keep_exact_sources_and_independent_placements(api_client, admin_user):
    target = branch()
    records = [source(target) for _ in range(49)]
    last_work, _edition, _asset, page, revision, _relation = records[-1]
    span = EvidenceSpan.objects.create(
        document_revision=revision.document_revision, page=page, page_number=1,
        original_text=page.text, start_offset=0, end_offset=len(page.text),
        content_hash=sha256(page.text.encode()).hexdigest(),
    )
    saved = content_placements.command("subdiscipline", target.pk, {
        "action": "save", "request_id": str(uuid4()), "expected_revision": "0",
        "items": [{"target": {"type": "span", "id": str(span.pk)}}],
    }, admin_user)
    content_placements.command("subdiscipline", target.pk, {
        "action": "publish", "request_id": str(uuid4()), "expected_revision": saved["expected_revision"],
    }, admin_user)
    endpoint = f"/api/catalog/subdisciplines/{target.slug}/"
    first = api_client.get(endpoint).data
    second_response = api_client.get(endpoint, {"works_page": "2"})
    assert second_response.status_code == 200
    second = second_response.data
    assert first["works_pagination"] == {"count": 49, "page": 1, "total_pages": 2}
    assert second["works_pagination"] == {"count": 49, "page": 2, "total_pages": 2}
    assert len(first["core_works"]) == len(first["works"]) == 48
    assert len(second["core_works"]) == len(second["works"]) == 1
    assert second["core_works"][0]["id"] == str(last_work.pk)
    for data in (first, second):
        work_ids = {row["id"] for row in data["core_works"]}
        assert {row["id"] for row in data["works"]} == work_ids
        assert {row["work_id"] for row in data["sources"] if row["source_kind"] == "work_relation"} == work_ids
        assert len([row for row in data["sources"] if row["source_kind"] == "placement_span"]) == 1
        assert all(row["reader_href"].endswith(row["document_revision_id"]) for row in data["sources"])
    assert not ({row["id"] for row in first["core_works"]} & {row["id"] for row in second["core_works"]})
    assert api_client.get(endpoint, {"works_page": "3"}).status_code == 404


def test_hidden_parent_and_discipline_are_nullable_and_not_search_filters(api_client):
    hidden_discipline = discipline(published=False)
    parent = branch(editorial_status="draft")
    child = branch(discipline=hidden_discipline, parent=parent)
    visible_child = branch(parent=child)
    branch(parent=child, editorial_status="draft")
    response = api_client.get(f"/api/catalog/subdisciplines/{child.slug}/")
    assert response.status_code == 200
    assert response.data["discipline"] is None and response.data["parent"] is None
    assert response.data["children"] == [{
        "id": str(visible_child.pk), "name": visible_child.name, "slug": visible_child.slug,
        "href": f"/subdisciplines/{visible_child.slug}",
    }]
    filtered = api_client.get("/api/catalog/subdisciplines/", {"discipline": hidden_discipline.slug})
    assert filtered.data["count"] == 0
    assert api_client.get(f"/api/catalog/subdisciplines/{parent.slug}/").status_code == 404


def test_canonical_relations_win_without_erasing_legacy_identity():
    target = branch()
    node = node_for(target, name="已核实理论")
    old = TheorySchool.objects.create(name=node.canonical_name_zh, slug=f"old-{uuid4()}", editorial_status="published")
    TheorySubdisciplineRelation.objects.create(theory_school=old, subdiscipline=target, review_status="approved", role="core")
    LegacyKnowledgeMapping.objects.create(legacy_model="TheorySchool", legacy_id=old.pk, node=node)
    unmatched = TheorySchool.objects.create(name="未映射理论", slug=f"old-{uuid4()}", editorial_status="published")
    TheorySubdisciplineRelation.objects.create(theory_school=unmatched, subdiscipline=target, review_status="approved")
    concept = node_for(target, kind="concept")
    node_for(target, status="draft")
    node_for(target, relation_status="pending")
    data = SubdisciplineSerializer(target).data
    first = next(row for row in data["theories"] if row["id"] == str(node.pk))
    assert first["kind"] == "knowledge_node" and first["canonical_target"]["id"] == str(node.pk)
    assert first["legacy_identities"][0]["id"] == str(old.pk)
    assert len([row for row in data["theories"] if row["id"] == str(old.pk)]) == 0
    assert next(row for row in data["theories"] if row["id"] == str(concept.pk))["node_type"] == "concept"
    legacy = next(row for row in data["theories"] if row["id"] == str(unmatched.pk))
    assert legacy["kind"] == "legacy_theory" and legacy["canonical_target"] is None
    assert legacy["href"] == f"/theory-schools/{unmatched.slug}"
    assert len(data["theories"]) == 3
    KnowledgeNodeDiscipline.objects.create(node=node, discipline=target.discipline, status="published")
    TheoryDisciplineRelation.objects.create(theory_school=old, discipline=target.discipline, review_status="approved")
    assert DisciplineSerializer(target.discipline).data["theory_count"] == 1
    KnowledgeNode.objects.create(
        node_type="theory_tradition", canonical_name_zh="只有主学科的规范理论",
        slug=f"primary-{uuid4()}", status="published", primary_discipline=target.discipline,
    )
    assert DisciplineSerializer(target.discipline).data["theory_count"] == 2


def test_unsafe_legacy_mapping_does_not_guess_a_canonical_target():
    target = branch()
    node = node_for(target, name="不相同的规范名称")
    old = TheorySchool.objects.create(name="另一个旧名称", slug=f"old-{uuid4()}", editorial_status="published")
    TheorySubdisciplineRelation.objects.create(theory_school=old, subdiscipline=target, review_status="approved")
    LegacyKnowledgeMapping.objects.create(legacy_model="TheorySchool", legacy_id=old.pk, node=node)
    rows = SubdisciplineSerializer(target).data["theories"]
    legacy = next(row for row in rows if row["id"] == str(old.pk))
    assert legacy["canonical_target"] is None
    assert legacy["href"] == f"/theory-schools/{old.slug}"


def test_questions_link_only_real_published_research_problem():
    target = branch(core_questions=["没有规范关联的问题", "已有规范关联的问题"])
    question = node_for(target, kind="research_problem", name="已有规范关联的问题")
    node_for(target, kind="research_problem", name="不可见问题", status="draft")
    data = SubdisciplineSerializer(target).data
    assert data["core_questions"] == target.core_questions
    assert data["key_questions"][0]["id"] is None and data["key_questions"][0]["href"] is None
    assert data["key_questions"][1]["id"] == str(question.pk)
    assert data["key_questions"][1]["description"] == question.summary
    assert not data["theories"]


def test_scholars_and_topics_keep_real_metadata_without_fake_source_links():
    target = branch()
    person = Person.objects.create(
        preferred_name="已核实合成人物", authority_status="verified", portrait="test/real-portrait.jpg",
    )
    profile = ScholarProfile.objects.create(person=person, slug=f"scholar-{uuid4()}", editorial_status="published", short_description="人物资料")
    PersonSubdisciplineRelation.objects.create(
        person=person, subdiscipline=target, review_status="approved", relation_label="已有研究关联", source="书目说明",
    )
    hidden = Person.objects.create(preferred_name="待核实人物")
    ScholarProfile.objects.create(person=hidden, slug=f"hidden-{uuid4()}", editorial_status="published")
    PersonSubdisciplineRelation.objects.create(person=hidden, subdiscipline=target, review_status="approved")
    topic = Topic.objects.create(name="已发布主题", slug=f"topic-{uuid4()}", editorial_status="published", description="主题说明")
    TopicSubdisciplineRelation.objects.create(topic=topic, subdiscipline=target, review_status="approved")
    hidden_topic = Topic.objects.create(name="隐藏主题", slug=f"topic-{uuid4()}", editorial_status="draft")
    TopicSubdisciplineRelation.objects.create(topic=hidden_topic, subdiscipline=target, review_status="approved")
    data = SubdisciplineSerializer(target).data
    assert len(data["scholars"]) == 1
    scholar = data["scholars"][0]
    assert scholar["id"] == str(profile.pk) and scholar["person_id"] == str(person.pk)
    assert scholar["portrait_url"].endswith("test/real-portrait.jpg")
    assert scholar["source_label"] == "书目说明" and scholar["source_href"] is None
    assert scholar["href"] == f"/scholars/{profile.slug}"
    assert len(data["topics"]) == 1 and data["topics"][0]["href"] == f"/topics/{topic.slug}"


def test_formal_secondary_work_preserves_exact_version_and_snapshot():
    target = branch()
    work, edition, asset, _page, revision, _relation = source(target, secondary=True)
    Edition.objects.create(work=work, state="draft", is_primary=True)
    Work.objects.filter(pk=work.pk).update(title="未发布改题")
    data = SubdisciplineSerializer(target).data
    card = data["core_works"][0]
    assert card["title"] == "正式子学科书目" and card["edition_id"] == str(edition.pk)
    assert card["catalog_revision_id"] == str(revision.pk)
    assert card["document_revision_id"] == str(revision.document_revision_id)
    assert card["reader_href"] == f"/reader/{asset.pk}?revision={revision.document_revision_id}"
    assert data["works"][0]["title"] == card["title"]
    assert data["works"][0]["edition"]["id"] == str(edition.pk)
    assert data["works"][0]["cover"].endswith(f"edition_id={edition.pk}")
    assert card["evidence"]["reader_href"].endswith(f"page=1&revision={revision.document_revision_id}")


def test_card_and_evidence_keep_their_distinct_published_editions():
    target = branch()
    work, edition, asset, _page, _revision, relation = source(target)
    work.title = "证据出版版本的正式题名"
    work.save(update_fields=["title"])
    evidence_edition = Edition.objects.create(
        work=work, state="published", is_primary=False,
        version_label="证据次版", public_slug=f"evidence-{uuid4()}",
    )
    evidence_asset = Asset.objects.create(
        edition=evidence_edition, kind="normalized", status="ready", validation_status="valid",
        file="test/evidence-edition.pdf", sha256="b" * 64, page_count=1,
    )
    Page.objects.create(asset=evidence_asset, index=1, text="证据次版原文", width=600, height=900)
    evidence_revision = activate_catalog_revision(evidence_edition, reader_asset=evidence_asset)
    relation.evidence_asset, relation.evidence_text = evidence_asset, "证据次版原文"
    relation.save(update_fields=["evidence_asset", "evidence_text"])
    data = SubdisciplineSerializer(target).data
    card = data["core_works"][0]
    assert card["edition_id"] == str(edition.pk) and card["asset_id"] == str(asset.pk)
    assert card["title"] == "正式子学科书目"
    assert card["evidence"]["edition_id"] == str(evidence_edition.pk)
    assert card["evidence"]["edition_label"] == "证据次版"
    assert card["evidence"]["document_revision_id"] == str(evidence_revision.document_revision_id)
    assert card["evidence"]["title"] == "证据出版版本的正式题名"
    assert card["evidence"]["reader_href"] != card["reader_href"]


@pytest.mark.parametrize("changed", ["private", "withdrawn", "replacement", "missing_page", "mismatched_work"])
def test_sources_recheck_current_file_and_keep_only_allowed_metadata(changed):
    target = branch()
    work, edition, asset, page, _revision, relation = source(target)
    if changed == "private":
        Asset.objects.filter(pk=asset.pk).update(access_status="private")
    elif changed == "withdrawn":
        Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    elif changed == "replacement":
        replacement = Asset.objects.create(
            edition=edition, kind="normalized", status="ready", validation_status="valid",
            file="test/new-source.pdf", sha256="b" * 64, page_count=1, version=2,
        )
        Page.objects.create(asset=replacement, index=1, text="另一个文件的段落", width=600, height=900)
        activate_catalog_revision(edition, reader_asset=replacement)
    elif changed == "missing_page":
        page.delete()
    else:
        other = branch()
        _other_work, _other_edition, other_asset, *_rest = source(other)
        relation.evidence_asset = other_asset
        relation.save(update_fields=["evidence_asset"])
    data = SubdisciplineSerializer(target).data
    assert data["sources"] == []
    if changed == "withdrawn":
        assert data["core_works"] == [] and data["works"] == []
    else:
        assert data["core_works"][0]["evidence"] is None
        assert data["core_works"][0]["title"] == "正式子学科书目"


def test_reading_paths_require_a_real_visible_item():
    target = branch()
    linked = node_for(target, kind="concept")
    path = ReadingPath.objects.create(title="相关路径", slug=f"path-{uuid4()}", status="published")
    ReadingPathItem.objects.create(reading_path=path, node=linked, stage_name="入口")
    same_discipline = ReadingPath.objects.create(
        title="只有同学科而无节点关系", slug=f"path-{uuid4()}", status="published", primary_discipline=target.discipline,
    )
    mixed = ReadingPath.objects.create(title="作品已撤回的路径项", slug=f"path-{uuid4()}", status="published")
    ReadingPathItem.objects.create(reading_path=mixed, node=linked, work=Work.objects.create(title="未公开作品"))
    hidden = node_for(target, status="draft")
    hidden_path = ReadingPath.objects.create(title="隐藏节点路径", slug=f"path-{uuid4()}", status="published")
    ReadingPathItem.objects.create(reading_path=hidden_path, node=hidden)
    data = SubdisciplineSerializer(target).data
    assert [row["id"] for row in data["reading_paths"]] == [str(path.pk)]
    assert data["reading_paths"][0]["href"] == f"/theories/reading-paths/{path.slug}"
    assert str(same_discipline.pk) not in {row["id"] for row in data["reading_paths"]}


def test_public_search_uses_related_confirmed_concepts_and_topics():
    target = branch()
    concept = node_for(target, kind="concept", name="可检索的正式概念")
    KnowledgeNodeAlias.objects.create(node=concept, alias="已核实译名", is_verified=True)
    KnowledgeNodeAlias.objects.create(node=concept, alias="待核实译名", is_verified=False)
    node_for(target, name="待公开节点", status="draft")
    node_for(target, name="待确认关联", relation_status="pending")
    topic = Topic.objects.create(name="可检索的正式主题", slug=f"topic-{uuid4()}", editorial_status="published")
    TopicSubdisciplineRelation.objects.create(topic=topic, subdiscipline=target, review_status="approved")
    search = SearchService()
    for query in ("正式概念", "已核实译名", "正式主题"):
        assert list(search.queryset(SearchContext.SUBDISCIPLINES, query).values_list("pk", flat=True)) == [target.pk]
    for query in ("待核实译名", "待公开节点", "待确认关联"):
        assert not search.queryset(SearchContext.SUBDISCIPLINES, query).exists()
        assert search.queryset(SearchContext.SUBDISCIPLINES, query, visibility=SearchVisibility.ADMIN).exists()


def test_search_result_keeps_independent_identity_and_masks_hidden_discipline():
    target = branch(discipline=discipline(published=False))
    mirror = node_for(target)
    LegacyKnowledgeMapping.objects.create(legacy_model="Subdiscipline", legacy_id=target.pk, node=mirror)
    public = SearchService()._result(SearchContext.SUBDISCIPLINES, target, "")
    assert public["id"] == str(target.pk) and public["entity_type"] == "subdiscipline"
    assert public["metadata"]["discipline"] is None
    admin = SearchService()._result(SearchContext.SUBDISCIPLINES, target, "", visibility=SearchVisibility.ADMIN)
    assert admin["metadata"]["discipline"] == target.discipline.name


def test_published_placement_span_is_resolved_and_removed_when_stale(admin_user):
    target = branch()
    _work, _edition, _asset, page, revision, relation = source(target)
    relation.evidence_text = ""
    relation.save(update_fields=["evidence_text"])
    span = EvidenceSpan.objects.create(
        document_revision=revision.document_revision, page=page, page_number=1,
        original_text=page.text, start_offset=0, end_offset=len(page.text),
        content_hash=sha256(page.text.encode()).hexdigest(),
    )
    saved = content_placements.command("subdiscipline", target.pk, {
        "action": "save", "request_id": str(uuid4()), "expected_revision": "0",
        "items": [{"target": {"type": "span", "id": str(span.pk)}}],
    }, admin_user)
    content_placements.command("subdiscipline", target.pk, {
        "action": "publish", "request_id": str(uuid4()), "expected_revision": saved["expected_revision"],
    }, admin_user)
    data = SubdisciplineSerializer(target).data
    assert data["sources"][0]["source_kind"] == "placement_span"
    assert data["sources"][0]["quote"] == page.text
    EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    assert SubdisciplineSerializer(target).data["sources"] == []
