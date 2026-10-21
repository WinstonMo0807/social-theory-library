"""PDF52/53/55 acceptance definitions; do not run until unified acceptance."""
from uuid import uuid4

import pytest

from catalog.models import (
    Asset, Discipline, Edition, EditorialRevision, EvidenceSnippet, KnowledgeNode,
    KnowledgeNodeSubdiscipline, KnowledgeNodeTopic, KnowledgeRelation, Page, Person,
    PersonNodeRelation, ScholarProfile, ScholarRelation, Subdiscipline, Topic, Work,
    WorkNodeRelation,
)
from catalog.services.theory_graph import public_graph_edge
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db
URL = "/api/catalog/theory-system/graph/"


def node(**kwargs):
    key = uuid4()
    return KnowledgeNode.objects.create(**{
        "canonical_name_zh": f"合成图谱节点 {key}", "slug": f"graph-{key}",
        "node_type": "concept", "status": "published", **kwargs,
    })


def scholar(**kwargs):
    person = Person.objects.create(preferred_name=f"合成图谱人物 {uuid4()}", authority_status="verified")
    return ScholarProfile.objects.create(person=person, slug=f"graph-scholar-{uuid4()}", editorial_status="published", **kwargs)


def link(left, right, **kwargs):
    return KnowledgeRelation.objects.create(source_node=left, target_node=right,
        relation_type="influenced_by", status="published", **kwargs)


def graph(client, center=None, **params):
    response = client.get(URL, {**({"center": str(center.pk)} if center else {}), **params})
    assert response.status_code == 200, response.data
    return response.data


def test_real_three_hop_neighborhood_keeps_edge_and_node_identity(api_client):
    rows = [node() for _ in range(4)]
    links = [link(rows[index], rows[index + 1]) for index in range(3)]
    hidden = node(status="draft", canonical_name_zh="未公开节点不可泄漏")
    link(rows[0], hidden)
    for depth in (1, 2, 3):
        data = graph(api_client, rows[0], depth=depth)
        assert {row["entity_id"] for row in data["nodes"]} == {str(row.pk) for row in rows[:depth + 1]}
        assert {row["id"] for row in data["edges"]} == {f"KnowledgeRelation:{row.pk}" for row in links[:depth]}
        assert data["center"] == f"knowledge_node:{rows[0].pk}"
        assert max(row["depth"] for row in data["nodes"]) == depth
        assert not data["truncated"]
        assert "未公开节点不可泄漏" not in str(data)


def test_limits_are_not_evidence_of_truncation_without_an_extra_visible_record(api_client):
    left, middle = node(), node()
    link(left, middle)
    exact = graph(api_client, left, limit=2, edge_limit=1, depth=3)
    assert exact["counts"] == {"nodes": 2, "edges": 1, "scholars": 0, "topics": 0}
    assert exact["truncated"] is False
    other = node()
    link(middle, other)
    deeper = graph(api_client, left, limit=2, edge_limit=1, depth=3)
    assert deeper["truncated"] is True
    assert len(deeper["nodes"]) == 2 and len(deeper["edges"]) == 1
    shallow = graph(api_client, left, limit=2, edge_limit=1, depth=1)
    assert shallow["truncated"] is False
    minimum = graph(api_client, left, limit=1)
    assert minimum["truncated"] and minimum["counts"]["nodes"] == 1
    assert minimum["state"] == "ready"


@pytest.mark.parametrize("center_kind", ["knowledge_node", "scholar", "topic", "subdiscipline"])
def test_typed_centers_keep_scholar_profile_identity_and_same_uuid_does_not_merge(api_client, center_kind):
    profile = scholar()
    concept = node(id=profile.pk)
    topic = Topic.objects.create(name="合成图谱主题", slug="graph-topic", editorial_status="published")
    discipline = Discipline.objects.create(name="合成图谱学科", code="graph", slug="graph", editorial_status="published")
    branch = Subdiscipline.objects.create(name="合成图谱子学科", slug="graph-branch", discipline=discipline, editorial_status="published")
    PersonNodeRelation.objects.create(person=profile.person, node=concept, status="published")
    KnowledgeNodeTopic.objects.create(node=concept, topic=topic, status="published")
    KnowledgeNodeSubdiscipline.objects.create(node=concept, subdiscipline=branch, status="published")
    selected = {"knowledge_node": concept, "scholar": profile, "topic": topic, "subdiscipline": branch}[center_kind]
    data = graph(api_client, selected, center_kind=center_kind, depth=2)
    identities = {row["id"] for row in data["nodes"]}
    assert f"scholar:{profile.pk}" in identities and f"knowledge_node:{concept.pk}" in identities
    assert f"scholar:{profile.person_id}" not in identities
    assert data["center"] == f"{center_kind}:{selected.pk}"
    assert api_client.get(URL, {"center_kind": "scholar", "center": profile.person_id}).status_code == 404
    Person.objects.filter(pk=profile.person_id).update(authority_status="unverified")
    assert not any(row["kind"] == "scholar" for row in graph(api_client, concept)["nodes"])


def test_empty_isolated_and_filtered_are_actual_distinct_states(api_client):
    assert graph(api_client)["state"] == "empty"
    center = node()
    assert graph(api_client, center)["state"] == "isolated"
    link(center, node())
    data = graph(api_client, center, relation_type="criticizes")
    assert data["state"] == "filtered" and data["edges"] == []
    assert data["truncated"] is False


@pytest.mark.parametrize("params", [
    {"depth": "0"}, {"depth": "4"}, {"limit": "121"}, {"edge_limit": "301"},
    {"center_kind": "person"}, {"node_type": "made_up"}, {"relation_type": "shared_upload"},
    {"start_year": "1.5"}, {"start_year": "2000", "end_year": "1000"}, {"has_collection": "perhaps"},
])
def test_invalid_graph_filters_are_rejected_instead_of_silently_reset(api_client, params):
    assert api_client.get(URL, params).status_code == 400


def test_candidates_remain_editorial_and_login_alone_does_not_reveal_them(api_client, reader_user, admin_user):
    center, unpublished = node(), node(status="draft", canonical_name_zh="候选私名不可泄漏")
    visible = node()
    link(center, visible)
    public_candidate = KnowledgeRelation.objects.create(source_node=center, target_node=visible,
        relation_type="criticizes", status="pending", description="未确认的真实候选")
    candidate = KnowledgeRelation.objects.create(source_node=center, target_node=unpublished,
        relation_type="criticizes", status="pending", description="候选私文不可泄漏")
    for user in (None, reader_user, admin_user):
        api_client.force_authenticate(user=user)
        data = graph(api_client, center)
        access = data["candidate_access"]
        assert access["can_review"] is (user == admin_user)
        assert access["review_href"] == ("/admin/theories/relations" if user == admin_user else None)
        assert len(data["edges"]) == 1
        assert data["candidate_count"] is None and data["candidate_edges"] == []
        assert "count" not in access
        assert "候选私" not in str(data)
        requested = api_client.get(URL, {"center": center.pk, "include_candidates": "true"})
        if user != admin_user:
            assert requested.status_code == 403
            assert "候选私" not in str(requested.data)
        else:
            assert requested.status_code == 200
            overlay = requested.data
            assert overlay["candidate_count"] == 1 and not overlay["candidates_truncated"]
            assert overlay["candidate_edges"][0]["id"] == f"KnowledgeRelation:{public_candidate.pk}"
            assert overlay["candidate_edges"][0]["status"] == "pending"
            assert overlay["candidate_edges"][0]["source_status"] == "unverified"
            assert overlay["candidate_edges"][0]["evidence"] == []
            assert overlay["counts"]["edges"] == 1
            assert "候选私" not in str(overlay)
    assert public_graph_edge(f"KnowledgeRelation:{candidate.pk}") is None
    assert public_graph_edge(f"KnowledgeRelation:{public_candidate.pk}") is None


def test_candidate_limit_needs_an_actual_extra_row_and_never_expands_the_public_neighborhood(api_client, admin_user):
    center = node()
    candidates = []
    for _index in range(61):
        neighbor = node()
        link(center, neighbor)
        candidates.append(KnowledgeRelation.objects.create(source_node=center, target_node=neighbor,
            relation_type="criticizes", status="pending"))
    api_client.force_authenticate(user=admin_user)
    data = graph(api_client, center, limit=120, include_candidates="true")
    assert data["candidate_count"] == 60 and data["candidates_truncated"]
    assert data["counts"]["nodes"] == 62 and data["counts"]["edges"] == 61
    assert not data["truncated"]
    candidates[-1].delete()
    exact = graph(api_client, center, limit=120, include_candidates="true")
    assert exact["candidate_count"] == 60 and not exact["candidates_truncated"]


@pytest.mark.parametrize("damage", [None, "draft_only", "moved_endpoint", "foreign_revision", "withdrawn_profile"])
def test_scholar_edges_read_their_own_formal_snapshot(api_client, damage):
    left, right, unrelated = scholar(), scholar(), scholar()
    row = ScholarRelation.objects.create(source_scholar=left, target_scholar=right,
        relation_type="influence", direction="directed", status="published", summary="不可用现行字段替代快照")
    snapshot = {"source_scholar": str(left.pk), "target_scholar": str(right.pk),
        "relation_type": "influence", "direction": "directed", "summary": "正式关系说明", "source": "正式书目依据"}
    revision = EditorialRevision.objects.create(target_type="scholar_relation", target_id=row.pk,
        revision=1, status="published", materialized_preview=snapshot, idempotency_key=f"graph-{uuid4()}")
    row.active_revision = revision
    row.save(update_fields=["active_revision"])
    if damage == "draft_only":
        EditorialRevision.objects.create(target_type="scholar_relation", target_id=row.pk,
            revision=2, status="draft", materialized_preview={**snapshot, "summary": "尚未公开的改写"}, idempotency_key=f"graph-{uuid4()}")
    elif damage == "moved_endpoint":
        ScholarRelation.objects.filter(pk=row.pk).update(target_scholar=unrelated)
    elif damage == "foreign_revision":
        EditorialRevision.objects.filter(pk=revision.pk).update(target_id=unrelated.pk)
    elif damage == "withdrawn_profile":
        ScholarProfile.objects.filter(pk=right.pk).update(editorial_status="draft")
    data = graph(api_client, left, center_kind="scholar")
    if damage in {None, "draft_only"}:
        assert len(data["edges"]) == 1
        assert data["edges"][0]["description"] == "正式关系说明"
        assert data["edges"][0]["evidence"] == []
        assert data["edges"][0]["source_status"] == "citation_only"
    else:
        assert data["edges"] == []


@pytest.mark.parametrize("damage", [None, "case_changed", "text_changed", "inactive", "checksum_changed", "registered"])
def test_evidence_is_the_exact_current_authorized_page_not_just_a_valid_file_link(api_client, damage):
    center, other = node(), node()
    relation = link(center, other)
    work = Work.objects.create(title="确切出处作品")
    edition = Edition.objects.create(work=work, state="published", public_slug=f"graph-source-{uuid4()}")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
        access_status="public", file="test/graph-source.pdf", sha256="a" * 64, page_count=1)
    page = Page.objects.create(asset=asset, index=1, text="Exact Quote ABC", width=600, height=900)
    revision = activate_catalog_revision(edition, reader_asset=asset)
    evidence = EvidenceSnippet.objects.create(work=work, file=asset, knowledge_relation=relation,
        page_number=1, quote=page.text, review_status="approved")
    if damage == "case_changed":
        EvidenceSnippet.objects.filter(pk=evidence.pk).update(quote="exact quote abc")
    elif damage == "text_changed":
        Page.objects.filter(pk=page.pk).update(text="The current page contains different text")
    elif damage == "inactive":
        revision.document_revision.is_active = False
        revision.document_revision.save(update_fields=["is_active"])
    elif damage == "checksum_changed":
        Asset.objects.filter(pk=asset.pk).update(sha256="b" * 64)
    elif damage == "registered":
        Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    result = graph(api_client, center)["edges"][0]
    if damage is None:
        source = result["evidence"][0]
        assert source["quote"] == page.text and source["edition_id"] == str(edition.pk)
        assert source["asset_id"] == str(asset.pk)
        assert source["document_revision_id"] == str(revision.document_revision_id)
        assert f"revision={revision.document_revision_id}" in source["reader_href"]
    else:
        assert result["evidence"] == []
        assert "Exact Quote ABC" not in str(result) and "exact quote abc" not in str(result)


def test_collection_filter_and_related_versions_use_formal_snapshot_and_real_pagination(api_client):
    center, other = node(), node()
    work = Work.objects.create(title="正式关联文献")
    WorkNodeRelation.objects.create(work=work, node=center, status="published")
    for index in range(13):
        edition = Edition.objects.create(work=work, state="published", publication_mode="bibliographic",
            is_primary=index == 0, public_slug=f"graph-book-{index}", version_label=f"确切版本{index}")
        activate_catalog_revision(edition, fulltext_ready=False)
    # New live relation and title are drafts relative to the activated snapshots.
    WorkNodeRelation.objects.create(work=work, node=other, status="published")
    Work.objects.filter(pk=work.pk).update(title="未发布改名不得进入图谱")
    first = graph(api_client, center, has_collection="true")
    second = graph(api_client, center, has_collection="true", works_page="2")
    assert first["related_works_count"] == second["related_works_count"] == 13
    assert len(first["related_works"]) == 12 and len(second["related_works"]) == 1
    assert first["related_works_total_pages"] == 2
    assert set(row["edition_id"] for row in first["related_works"]).isdisjoint(row["edition_id"] for row in second["related_works"])
    assert all(row["title"] == "正式关联文献" for row in first["related_works"])
    assert api_client.get(URL, {"center": center.pk, "has_collection": "false"}).status_code == 404
    assert graph(api_client, other, has_collection="false")["related_works_count"] == 0
    assert api_client.get(URL, {"center": other.pk, "has_collection": "true"}).status_code == 404
