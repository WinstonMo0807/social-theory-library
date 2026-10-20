"""Legacy public source regressions, written for final acceptance; not run here."""
from uuid import uuid4

import pytest
from django.test import RequestFactory

from catalog.models import (
    Asset, Discipline, Edition, Page, Person, ScholarProfile, Subdiscipline,
    TheoryDisciplineRelation, TheoryHierarchyRelation, TheoryRelation, TheorySchool,
    TheoryTimelineEvent, Work,
)
from catalog.serializers import (
    AdminTheoryHierarchyRelationSerializer, AdminTheoryRelationSerializer,
    AdminTheoryTimelineEventSerializer, TheorySchoolSerializer, TheoryTimelineEventSerializer,
)
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


def school(*, published=True):
    key = uuid4()
    return TheorySchool.objects.create(
        name=f"隔离测试理论 {key}", slug=f"legacy-{key}",
        editorial_status="published" if published else "draft",
    )


def source(*, primary=True):
    work = Work.objects.create(title="隔离测试正式书目", document_type="book")
    edition = Edition.objects.create(
        work=work, state="published", is_primary=primary, public_slug=f"legacy-source-{uuid4()}",
    )
    asset = Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        access_status="public", file=f"test/legacy-{uuid4()}.pdf", sha256="a" * 64, page_count=1,
    )
    Page.objects.create(asset=asset, index=1, text="隔离测试原文", text_source="embedded", width=600, height=900)
    activate_catalog_revision(edition, reader_asset=asset)
    return work, edition, asset


def records(asset, work):
    left, right = school(), school()
    relation = TheoryRelation.objects.create(
        source_theory=left, target_theory=right, relation_type="influence",
        review_status="approved", evidence_work=work, evidence_asset=asset,
        evidence_page=1, evidence_printed_label="前言 i", evidence_text="隔离测试原文",
    )
    event = TheoryTimelineEvent.objects.create(
        theory_school=left, work=work, title="独立审核的事件说明", event_type="publication",
        review_status="approved", start_year=1901, evidence_asset=asset,
        evidence_page=1, evidence_printed_label="前言 i", evidence_text="隔离测试原文",
    )
    return left, right, relation, event


def evidence_rows(api_client, left, right, relation, event):
    graph = api_client.get("/api/catalog/theory-graph/")
    assert graph.status_code == 200
    graph_row = next(row for row in graph.data["edges"] if row["id"] == str(relation.pk))
    timeline = api_client.get("/api/catalog/theory-timeline/")
    assert timeline.status_code == 200
    rows = timeline.data["results"] if isinstance(timeline.data, dict) else timeline.data
    event_row = next(row for row in rows if str(row["id"]) == str(event.pk))
    # Both relation directions and the nested timeline use the same boundary.
    return [
        graph_row, event_row,
        TheorySchoolSerializer().get_relations(left)[0],
        TheorySchoolSerializer().get_relations(right)[0],
        TheorySchoolSerializer().get_timeline(left)[0],
    ]


@pytest.mark.parametrize("unavailable", [
    "no_activation", "metadata_not_ready", "metadata_only", "withdrawn", "private", "registered", "restricted",
    "original_file", "invalid", "failed", "empty_file", "missing_page", "page_out_of_range",
    "stale_asset", "wrong_document_asset",
])
def test_public_legacy_paths_mask_unavailable_source(api_client, unavailable):
    work, edition, asset = source()
    left, right, relation, event = records(asset, work)
    if unavailable == "no_activation":
        Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=None)
    elif unavailable == "metadata_not_ready":
        edition.active_catalog_revision.metadata_ready = False
        edition.active_catalog_revision.save(update_fields=["metadata_ready"])
    elif unavailable == "metadata_only":
        edition.active_catalog_revision.fulltext_ready = False
        edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    elif unavailable == "withdrawn":
        Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    elif unavailable in {"private", "registered", "restricted"}:
        Asset.objects.filter(pk=asset.pk).update(access_status=unavailable)
    elif unavailable == "original_file":
        Asset.objects.filter(pk=asset.pk).update(kind="original")
    elif unavailable == "invalid":
        Asset.objects.filter(pk=asset.pk).update(validation_status="invalid")
    elif unavailable == "failed":
        Asset.objects.filter(pk=asset.pk).update(status="failed")
    elif unavailable == "empty_file":
        Asset.objects.filter(pk=asset.pk).update(file="")
    elif unavailable == "missing_page":
        asset.pages.all().delete()
    elif unavailable == "page_out_of_range":
        relation.evidence_page = event.evidence_page = 2
        relation.save(update_fields=["evidence_page"])
        event.save(update_fields=["evidence_page"])
    elif unavailable == "stale_asset":
        replacement = Asset.objects.create(
            edition=edition, kind="normalized", status="ready", validation_status="valid",
            file="test/legacy-new.pdf", sha256="b" * 64, page_count=1, version=2,
        )
        Page.objects.create(asset=replacement, index=1, text="新文件原文", width=600, height=900)
        activate_catalog_revision(edition, reader_asset=replacement)
    else:
        _other_work, other_edition, _other_asset = source()
        revision = edition.active_catalog_revision
        revision.document_revision = other_edition.active_catalog_revision.document_revision
        revision.save(update_fields=["document_revision"])

    for row in evidence_rows(api_client, left, right, relation, event):
        assert row["evidence_text"] == ""
        assert row["evidence_page"] is None
        if "evidence_printed_label" in row:
            assert row["evidence_printed_label"] == ""


def test_current_formal_source_survives_pending_replacement_flag(api_client):
    work, edition, asset = source()
    left, right, relation, event = records(asset, work)
    Asset.objects.filter(pk=asset.pk).update(is_current=False)
    Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        file="test/preparing.pdf", sha256="b" * 64, page_count=1, version=2,
    )
    for row in evidence_rows(api_client, left, right, relation, event):
        assert row["evidence_text"] == "隔离测试原文"
        assert row["evidence_page"] == 1


def test_legacy_relation_rejects_mismatched_evidence_work(api_client):
    work, _edition, asset = source()
    left, right, relation, event = records(asset, work)
    relation.evidence_work = Work.objects.create(title="不是此文件的作品")
    relation.save(update_fields=["evidence_work"])
    rows = evidence_rows(api_client, left, right, relation, event)
    for row in (rows[0], rows[2], rows[3]):
        assert row["evidence_text"] == "" and row["evidence_page"] is None
    assert rows[1]["evidence_text"] == "隔离测试原文"


def test_unlocated_or_deleted_source_does_not_become_public_text(api_client):
    work, _edition, asset = source()
    left, right, relation, event = records(asset, work)
    relation.evidence_asset = event.evidence_asset = None
    relation.save(update_fields=["evidence_asset"])
    event.save(update_fields=["evidence_asset"])
    for row in evidence_rows(api_client, left, right, relation, event):
        assert row["evidence_text"] == "" and row["evidence_page"] is None
    hierarchy = TheoryHierarchyRelation.objects.create(
        parent=left, child=right, review_status="approved", evidence_text="没有文件身份的旧依据",
    )
    graph = api_client.get("/api/catalog/theory-graph/").data
    row = next(row for row in graph["edges"] if row["id"] == str(hierarchy.pk))
    assert row["relation_type"] == "hierarchy" and row["evidence_text"] == ""
    assert AdminTheoryHierarchyRelationSerializer(hierarchy).data["evidence_text"] == "没有文件身份的旧依据"


def test_hidden_entities_and_draft_relations_are_not_public(api_client):
    work, _edition, asset = source()
    left, _right, relation, event = records(asset, work)
    hidden = school(published=False)
    relation.target_theory = hidden
    relation.save(update_fields=["target_theory"])
    discipline = Discipline.objects.create(
        name="未公开学科", code=f"hidden-{uuid4()}", slug=f"hidden-{uuid4()}", editorial_status="draft",
    )
    subdiscipline = Subdiscipline.objects.create(
        name="未公开子学科", slug=f"hidden-{uuid4()}", discipline=discipline, editorial_status="draft",
    )
    person = Person.objects.create(preferred_name="未公开人物")
    scholar = ScholarProfile.objects.create(person=person, slug=f"hidden-{uuid4()}", editorial_status="draft")
    event.theory_school, event.discipline, event.subdiscipline = hidden, discipline, subdiscipline
    event.scholar = scholar
    event.work = Work.objects.create(title="未公开作品")
    event.save()
    data = TheoryTimelineEventSerializer(event).data
    assert all(data[key] is None for key in ("theory", "discipline", "subdiscipline", "scholar", "work"))
    assert data["title"] == "独立审核的事件说明"
    assert TheorySchoolSerializer().get_relations(left) == []
    assert TheorySchoolSerializer().get_relations(hidden) == []
    assert TheorySchoolSerializer().get_timeline(hidden) == []
    graph = api_client.get("/api/catalog/theory-graph/").data
    assert str(hidden.pk) not in {row["id"] for row in graph["nodes"]}
    assert str(relation.pk) not in {row["id"] for row in graph["edges"]}


def test_hidden_discipline_cannot_filter_public_graph(api_client):
    left = school()
    discipline = Discipline.objects.create(
        name="图谱隐藏学科", code=f"hidden-{uuid4()}", slug=f"hidden-{uuid4()}", editorial_status="draft",
    )
    TheoryDisciplineRelation.objects.create(
        theory_school=left, discipline=discipline, review_status="approved",
    )
    result = api_client.get("/api/catalog/theory-graph/", {"discipline": discipline.slug})
    assert result.status_code == 200 and result.data["nodes"] == [] and result.data["edges"] == []


def test_registered_source_respects_reader_session(api_client, reader_user):
    work, _edition, asset = source()
    left, _right, relation, event = records(asset, work)
    Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    # Public query strings cannot activate a server-owned preview context.
    anonymous = api_client.get("/api/catalog/theory-timeline/", {"include_unpublished_items": "true"})
    assert anonymous.data["results"][0]["evidence_text"] == ""
    api_client.force_authenticate(reader_user)
    graph = api_client.get("/api/catalog/theory-graph/").data
    assert next(row for row in graph["edges"] if row["id"] == str(relation.pk))["evidence_text"] == "隔离测试原文"
    timeline = api_client.get("/api/catalog/theory-timeline/").data
    assert timeline["results"][0]["evidence_text"] == "隔离测试原文"
    request = RequestFactory().get("/")
    request.user = reader_user
    assert TheorySchoolSerializer(context={"request": request}).get_timeline(left)[0]["evidence_page"] == 1
    Asset.objects.filter(pk=asset.pk).update(access_status="private")
    assert api_client.get("/api/catalog/theory-timeline/").data["results"][0]["evidence_text"] == ""


def test_explicit_admin_preview_preserves_original_data(admin_user):
    work, edition, asset = source()
    left, _right, relation, event = records(asset, work)
    Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    request = RequestFactory().get("/")
    request.user = admin_user
    public_context = {"request": request}
    assert TheoryTimelineEventSerializer(event, context=public_context).data["evidence_text"] == ""
    preview_context = {"request": request, "include_unpublished_items": True}
    assert TheoryTimelineEventSerializer(event, context=preview_context).data["evidence_text"] == "隔离测试原文"
    assert TheorySchoolSerializer(context=preview_context).get_relations(left)[0]["evidence_page"] == 1
    assert AdminTheoryRelationSerializer(relation).data["evidence_text"] == "隔离测试原文"
    assert AdminTheoryTimelineEventSerializer(event).data["evidence_text"] == "隔离测试原文"


def test_timeline_metadata_uses_formal_secondary_edition_snapshot():
    work, _edition, asset = source(primary=False)
    event = TheoryTimelineEvent.objects.create(
        title="已审核书目事件", event_type="publication", review_status="approved", work=work,
        evidence_asset=asset, evidence_page=1, evidence_text="隔离测试原文",
    )
    Edition.objects.create(work=work, state="draft", is_primary=True)
    Work.objects.filter(pk=work.pk).update(title="待发布改题")
    event.refresh_from_db()
    assert TheoryTimelineEventSerializer(event).data["work"]["title"] == "隔离测试正式书目"
