"""PDF56/57 contracts, written for the final acceptance run; no synthetic history in production."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from catalog.models import (
    Asset, Contribution, Discipline, Edition, KnowledgeNode, KnowledgeNodeTopic,
    KnowledgeRelation, Page, Person, ScholarProfile, TheorySchool, TheoryTimelineEvent,
    TimelineEventRelation, Topic, Work, WorkTopicRelation,
)
from catalog.serializers import AdminTheoryTimelineEventSerializer
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db
ENDPOINT = "/api/catalog/theory-system/timeline/"


def event(**kwargs):
    values = {"title": f"合成时间线事件 {uuid4()}", "event_type": "publication", "review_status": "approved"}
    values.update(kwargs)
    return TheoryTimelineEvent.objects.create(**values)


def source(*, work=None, title="正式版本标题", primary=True, fulltext=True):
    work = work or Work.objects.create(title=title, document_type="book", language="zh-CN")
    edition = Edition.objects.create(
        work=work, state="published", is_primary=primary, version_label=f"确切版本 {uuid4()}",
        public_slug=f"timeline-work-{uuid4()}", publication_year=1901,
    )
    asset = Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        access_status="public", file="test/timeline-source.pdf", page_count=1,
        sha256=str(uuid4()).replace("-", "") * 2,
    )
    page = Page.objects.create(asset=asset, index=1, text="隔离测试的真实存储段落", width=600, height=900)
    revision = activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=fulltext)
    return work, edition, asset, page, revision


def scholar(*, published=True, verified=True, name=None):
    person = Person.objects.create(
        preferred_name=name or f"合成人物 {uuid4()}",
        authority_status="verified" if verified else "unverified",
    )
    profile = ScholarProfile.objects.create(
        person=person, slug=f"timeline-person-{uuid4()}", editorial_status="published" if published else "draft",
    )
    return profile


def node(*, published=True, discipline=None):
    return KnowledgeNode.objects.create(
        canonical_name_zh=f"合成概念 {uuid4()}", slug=f"timeline-node-{uuid4()}",
        node_type="concept", status="published" if published else "draft", primary_discipline=discipline,
    )


def test_full_scope_groups_focus_and_pagination_do_not_count_only_visible_rows(api_client):
    same = [event(start_year=1867, title=f"同年事件 {index}") for index in range(27)]
    TheoryTimelineEvent.objects.filter(pk=same[0].pk).update(event_type="translation")
    unknown = event()
    event(start_year=1908, end_year=1955, date_precision="range")
    event(start_year=1867, review_status="suggested")
    first = api_client.get(ENDPOINT)
    assert first.status_code == 200
    assert first.data["count"] == first.data["scope_count"] == 29
    assert len(first.data["results"]) == 24
    assert first.data["bounds"] == {"min_year": 1867, "max_year": 1955, "undated_count": 1}
    assert [{"year": row["year"], "count": row["count"]} for row in first.data["year_groups"]] == [
        {"year": 1867, "count": 27}, {"year": 1908, "count": 1}, {"year": None, "count": 1},
    ]
    assert {row["event_type"]: row["count"] for row in first.data["year_groups"][0]["event_types"]} == {
        "publication": 26, "translation": 1,
    }
    for group in first.data["year_groups"]:
        assert sum(row["count"] for row in group["event_types"]) == group["count"]
    focused = api_client.get(ENDPOINT, {"focus": unknown.pk})
    assert focused.status_code == 200 and focused.data["page"] == 2
    assert focused.data["focus_id"] == str(unknown.pk)
    assert "focus=" not in (focused.data["previous"] or "")
    grouped = api_client.get(ENDPOINT, {"year": 1867, "page": 2})
    assert grouped.data["count"] == 27 and grouped.data["scope_count"] == 29
    assert grouped.data["year_groups"] == first.data["year_groups"]
    assert len(grouped.data["results"]) == 3
    assert api_client.get(ENDPOINT, {"year": 1908, "focus": same[0].pk}).status_code == 404
    assert api_client.get(ENDPOINT, {"year": "undated"}).data["results"][0]["id"] == str(unknown.pk)


def test_dates_use_stored_range_and_never_parse_a_label_as_year(api_client):
    uncertain = event(start_year=1908, end_year=1912, date_precision="range", date_label="约1910年")
    end_only = event(end_year=1924, date_precision="approximate")
    unknown = event(date_label="约1936年，尚未核实")
    zero = event(start_year=0, date_precision="year")
    data = api_client.get(ENDPOINT, {"year_from": 1911, "year_to": 1911}).data
    assert [row["id"] for row in data["results"]] == [str(uncertain.pk)]
    assert data["results"][0]["date_precision"] == "range"
    assert api_client.get(ENDPOINT, {"year": 1924}).data["results"][0]["id"] == str(end_only.pk)
    assert api_client.get(ENDPOINT, {"year": 1936}).data["count"] == 0
    undated = api_client.get(ENDPOINT, {"year": "undated"}).data["results"][0]
    assert undated["id"] == str(unknown.pk) and undated["date_precision"] == "unknown"
    zero_result = api_client.get(ENDPOINT, {"year": "0", "year_from": "0", "year_to": "0"}).data
    assert [row["id"] for row in zero_result["results"]] == [str(zero.pk)]
    assert zero_result["results"][0]["start_year"] == 0
    assert zero_result["bounds"] == {"min_year": 0, "max_year": 0, "undated_count": 0}


@pytest.mark.parametrize("params", [
    {"year_from": "1.5"}, {"year_to": "40000"}, {"year_from": "2000", "year_to": "1800"},
    {"year": "old"}, {"event_type": "nonexistent"}, {"sort": "sideways"}, {"page": "0"}, {"focus": "broken"},
])
def test_invalid_timeline_filters_do_not_silently_reset(api_client, params):
    assert api_client.get(ENDPOINT, params).status_code == 400


def test_topic_author_or_groups_and_combined_and_keep_real_public_selection(api_client):
    profiles = [scholar(), scholar(), scholar(published=False)]
    topics = [Topic.objects.create(name=f"主题{i}", slug=f"timeline-topic-{i}", editorial_status="published" if i < 2 else "draft") for i in range(3)]
    rows = []
    for index in range(3):
        concept = node(published=index < 2)
        KnowledgeNodeTopic.objects.create(node=concept, topic=topics[index], status="published")
        row = event(scholar=profiles[index], start_year=1900, event_type="publication" if index == 0 else "translation")
        TimelineEventRelation.objects.create(event=row, node=concept)
        rows.append(row)
    response = api_client.get(ENDPOINT, {
        "topic": [topics[0].slug, str(topics[1].pk), topics[0].slug],
        "author": [str(profiles[0].pk), profiles[1].slug], "event_type": "publication,translation",
    })
    assert response.status_code == 200 and response.data["count"] == 2
    assert len(response.data["selected_topics"]) == len(response.data["selected_authors"]) == 2
    assert {row["id"] for row in response.data["results"]} == {str(row.pk) for row in rows[:2]}
    assert api_client.get(ENDPOINT, {"topic": topics[0].slug, "author": profiles[1].slug}).data["count"] == 0
    hidden = api_client.get(ENDPOINT, {"topic": topics[2].slug, "author": profiles[2].slug}).data
    assert hidden["count"] == 0 and hidden["selected_topics"] == hidden["selected_authors"] == []
    assert api_client.get(ENDPOINT, {"author": "nonexistent"}).data["count"] == 0


def test_formal_work_snapshot_authors_topics_and_query_ignore_drafts(api_client):
    author = scholar(name="正式作者")
    work, edition, asset, _page, _revision = source(title="正式可搜书名")
    topic = Topic.objects.create(name="正式主题", slug="timeline-formal-topic", editorial_status="published")
    WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
    Contribution.objects.create(edition=edition, person=author.person, role="author", approved=True)
    activate_catalog_revision(edition, reader_asset=asset)
    row = event(subject_edition=edition)
    Work.objects.filter(pk=work.pk).update(title="不能按未发布改名命中")
    for params in ({"q": "正式可搜书名"}, {"q": author.person.preferred_name},
                   {"author": author.slug}, {"topic": topic.slug}):
        assert api_client.get(ENDPOINT, params).data["results"][0]["id"] == str(row.pk)
    assert api_client.get(ENDPOINT, {"q": "不能按未发布改名命中"}).data["count"] == 0
    Topic.objects.filter(pk=topic.pk).update(editorial_status="draft")
    ScholarProfile.objects.filter(pk=author.pk).update(editorial_status="draft")
    assert api_client.get(ENDPOINT, {"topic": topic.slug}).data["count"] == 0
    assert api_client.get(ENDPOINT, {"author": author.slug}).data["count"] == 0
    data = api_client.get(f"{ENDPOINT}{row.pk}/").data
    assert data["topics"] == data["scholars"] == []


def test_subject_and_evidence_editions_stay_independent_and_no_primary_is_guessed(api_client):
    work, primary, _asset, _page, _revision = source(title="默认主版题名")
    work.title = "明确次版题名"
    work.save(update_fields=["title"])
    _work, secondary, _, _, _ = source(work=work, primary=False)
    evidence_work, evidence_edition, evidence_asset, page, revision = source(title="另一个出处作品")
    selected = event(
        work=work, subject_edition=secondary, evidence_asset=evidence_asset, evidence_page=1, evidence_text=page.text,
    )
    data = api_client.get(f"{ENDPOINT}{selected.pk}/").data
    assert data["subject_edition"]["edition_id"] == str(secondary.pk)
    assert data["subject_edition"]["title"] == "明确次版题名"
    assert data["subject_edition"]["version_label"] == secondary.version_label
    assert data["evidence_source"]["edition_id"] == str(evidence_edition.pk)
    assert data["evidence_source"]["work_id"] == str(evidence_work.pk)
    assert data["reader_href"].endswith(f"revision={revision.document_revision_id}")
    unselected = event(work=work, evidence_asset=evidence_asset, evidence_page=1)
    assert api_client.get(f"{ENDPOINT}{unselected.pk}/").data["subject_edition"] is None
    Edition.objects.filter(pk=secondary.pk).update(state="withdrawn")
    withdrawn = api_client.get(f"{ENDPOINT}{selected.pk}/").data
    assert withdrawn["subject_edition"] is None and withdrawn["subject_work"] is None
    assert withdrawn["subject_status"] == "unavailable"
    assert withdrawn["evidence_source"]["edition_id"] == str(evidence_edition.pk)
    assert primary.state == "published"


@pytest.mark.parametrize("change", [
    "private", "registered", "withdrawn", "no_fulltext", "foreign_document", "missing_page", "missing_file", "replacement",
    "changed_text", "same_asset_new_revision",
])
def test_public_source_requires_current_exact_document_and_real_page(api_client, change):
    _work, edition, asset, page, revision = source()
    row = event(evidence_asset=asset, evidence_page=1, evidence_text=page.text, source="独立书目说明")
    assert api_client.get(f"{ENDPOINT}{row.pk}/").data["source_status"] == "available"
    if change in {"private", "registered"}:
        Asset.objects.filter(pk=asset.pk).update(access_status=change)
    elif change == "withdrawn":
        Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    elif change == "no_fulltext":
        revision.fulltext_ready = False
        revision.save(update_fields=["fulltext_ready"])
    elif change == "foreign_document":
        other = source()
        activate_catalog_revision(edition, reader_asset=asset, document_revision=other[4].document_revision)
    elif change == "missing_page":
        page.delete()
    elif change == "missing_file":
        Asset.objects.filter(pk=asset.pk).update(file="")
    elif change in {"changed_text", "same_asset_new_revision"}:
        Page.objects.filter(pk=page.pk).update(text="当前正文已不再包含先前的引用")
        if change == "same_asset_new_revision":
            from catalog.models import DocumentRevision
            DocumentRevision.objects.filter(asset=asset, is_active=True).update(is_active=False)
            newer = DocumentRevision.objects.create(
                asset=asset, revision=2, source_checksum=asset.sha256, text_checksum="f" * 64,
                parser_name="isolated-test", parser_version="next", extraction_method="embedded",
                extraction_version="next", is_active=True,
            )
            activate_catalog_revision(edition, reader_asset=asset, document_revision=newer)
    else:
        replacement = Asset.objects.create(
            edition=edition, kind="normalized", status="ready", validation_status="valid", version=2,
            file="test/new-timeline.pdf", sha256="b" * 64, page_count=1,
        )
        Page.objects.create(asset=replacement, index=1, text="替代文件", width=600, height=900)
        activate_catalog_revision(edition, reader_asset=replacement)
    data = api_client.get(f"{ENDPOINT}{row.pk}/").data
    assert data["source_status"] == "unavailable" and data["evidence_source"] is None
    assert data["evidence_text"] == "" and data["evidence_page"] is None and data["reader_href"] is None
    assert data["source"] == "独立书目说明"
    legacy = api_client.get("/api/catalog/theory-timeline/").data["results"]
    legacy_row = next(value for value in legacy if value["id"] == str(row.pk))
    assert legacy_row["evidence_text"] == "" and legacy_row["evidence_page"] is None
    row.refresh_from_db()
    assert row.evidence_asset_id == asset.pk


def test_registered_source_obeys_session_and_printed_citation_remains_independent(api_client, reader_user):
    _work, _edition, asset, page, _revision = source()
    Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    row = event(evidence_asset=asset, evidence_page=1, evidence_text=page.text)
    api_client.force_authenticate(reader_user)
    assert api_client.get(f"{ENDPOINT}{row.pk}/").data["source_status"] == "available"
    printed = event(source="经审核的馆外印刷来源", evidence_text="独立文字引述")
    data = api_client.get(f"{ENDPOINT}{printed.pk}/").data
    assert data["source_status"] == "citation_only" and data["evidence_text"] == "独立文字引述"
    assert data["evidence_source"] is None


def test_legacy_subjects_are_kept_with_public_boundaries_and_primary_discipline_filter(api_client):
    discipline = Discipline.objects.create(name="公开学科", code="timeline-public", slug="timeline-public", editorial_status="published")
    tradition = TheorySchool.objects.create(name="旧真实流派", slug="timeline-old", editorial_status="published")
    profile = scholar()
    old = event(discipline=discipline, theory_school=tradition, scholar=profile)
    concept = node(discipline=discipline)
    normalized = event()
    TimelineEventRelation.objects.create(event=normalized, node=concept)
    assert api_client.get(ENDPOINT, {"discipline": discipline.slug}).data["count"] == 2
    data = api_client.get(f"{ENDPOINT}{old.pk}/").data
    assert {row["type"] for row in data["relations"]} == {"discipline", "legacy_theory", "scholar"}
    Discipline.objects.filter(pk=discipline.pk).update(editorial_status="draft")
    TheorySchool.objects.filter(pk=tradition.pk).update(editorial_status="draft")
    ScholarProfile.objects.filter(pk=profile.pk).update(editorial_status="draft")
    assert api_client.get(f"{ENDPOINT}{old.pk}/").status_code == 200
    assert api_client.get(f"{ENDPOINT}{old.pk}/").data["relations"] == []
    assert api_client.get("/api/catalog/theory-timeline/", {"discipline": discipline.slug}).data["count"] == 0
    assert api_client.get("/api/catalog/theory-timeline/", {"theory": tradition.slug}).data["count"] == 0


def test_related_events_require_shared_entities_and_influence_requires_explicit_relation(api_client):
    left, right, hidden = node(), node(), node(published=False)
    selected, related, merely_same_year = event(start_year=1900), event(start_year=1900), event(start_year=1900)
    for row in (selected, related):
        TimelineEventRelation.objects.create(event=row, node=left)
    relation = KnowledgeRelation.objects.create(
        source_node=left, target_node=right, relation_type="influenced_by", direction="directed",
        status="published", evidence_source="明确审核来源",
    )
    KnowledgeRelation.objects.create(
        source_node=left, target_node=hidden, relation_type="extends", direction="directed", status="published",
    )
    data = api_client.get(f"{ENDPOINT}{selected.pk}/").data
    assert data["related_count"] == 1 and data["related_events"][0]["id"] == str(related.pk)
    assert str(merely_same_year.pk) not in {row["id"] for row in data["related_events"]}
    assert data["knowledge_relation_count"] == 1 and data["knowledge_relations"][0]["id"] == str(relation.pk)
    assert api_client.get(ENDPOINT, {"related_to": selected.pk}).data["count"] == 1


@pytest.mark.parametrize("precision,start,end", [
    ("year", None, None), ("year", 1900, 1901), ("approximate", None, None),
    ("range", 1900, None), ("range", 1900, 1900), ("unknown", 1901, 1900),
])
def test_editor_rejects_inconsistent_date_precision(admin_user, precision, start, end):
    profile = scholar()
    serializer = AdminTheoryTimelineEventSerializer(data={
        "title": "待编辑事件", "event_type": "publication", "scholar": str(profile.pk),
        "date_precision": precision, "start_year": start, "end_year": end,
    }, context={"request": SimpleNamespace(user=admin_user)})
    assert not serializer.is_valid()


def test_subject_edition_and_precision_pass_through_existing_draft_publish_flow(api_client, admin_user):
    work, edition, _asset, _page, _revision = source()
    _source_work, _source_edition, source_asset, source_page, _ = source(title="独立出处")
    row = event(work=work)
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    endpoint = f"/api/catalog/admin/theory-timeline/{row.pk}/"
    version = api_client.get(endpoint).data["edit_version"]
    saved = api_client.patch(endpoint, {
        "subject_edition": str(edition.pk), "date_precision": "range", "start_year": 1900, "end_year": 1910,
        "evidence_asset": str(source_asset.pk), "evidence_page": 1, "evidence_text": source_page.text,
        "source": "经人工核对的独立出处", "description": "所选出版版本及日期范围已经核对。",
        "editorial_details": {"confirmed": True},
    }, format="json", HTTP_IF_MATCH=version)
    assert saved.status_code == 202, saved.data
    assert str(saved.data["subject_edition"]) == str(edition.pk) and saved.data["date_precision"] == "range"
    row.refresh_from_db()
    assert row.subject_edition_id is None and row.date_precision == "unknown"
    published = api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json")
    assert published.status_code == 200, published.data
    row.refresh_from_db()
    assert row.subject_edition_id == edition.pk and row.evidence_asset_id == source_asset.pk
    assert row.date_precision == "range"
    version = api_client.get(endpoint).data["edit_version"]
    invalid = api_client.patch(endpoint, {"work": str(source_asset.edition.work_id)}, format="json", HTTP_IF_MATCH=version)
    assert invalid.status_code == 400


def test_explicit_subject_does_not_match_an_unselected_editions_metadata(api_client):
    work, first, _asset, _page, _revision = source(title="第一版确切题名")
    Work.objects.filter(pk=work.pk).update(title="第二版独有题名")
    work.refresh_from_db()
    _work, second, _, _, _ = source(work=work, primary=False)
    selected = event(work=work, subject_edition=first)
    assert api_client.get(ENDPOINT, {"q": "第二版独有题名"}).data["count"] == 0
    assert api_client.get(ENDPOINT, {"q": "第一版确切题名"}).data["results"][0]["id"] == str(selected.pk)
    assert second.pk != first.pk
    legacy = api_client.get("/api/catalog/theory-timeline/").data["results"]
    assert next(row for row in legacy if row["id"] == str(selected.pk))["work"]["title"] == "第一版确切题名"
