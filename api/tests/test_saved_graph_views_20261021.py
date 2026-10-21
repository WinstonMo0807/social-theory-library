"""Synthetic owner/CAS/receipt cases prepared for the unified acceptance run."""
from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import KnowledgeNode, KnowledgeRelation, Person, ScholarProfile
from reading import graph_saves, privacy, research
from reading.graph_models import GraphViewReceipt, SavedGraphView
from tests.test_privacy_atlas_20261018 import operation, command as privacy_command, run

pytestmark = pytest.mark.django_db
BASE = "/api/reading/graph-views/"


def node(status="published"):
    return KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="合成图谱中心",
        slug=f"graph-fixture-{uuid4()}", status=status)


def request_for(target=None):
    target = target or node()
    return {"request_id": str(uuid4()), "data": {"title": "合成私人视图名称", "view": {
        "center_kind": "knowledge_node", "center": str(target.pk), "depth": 2,
        "node_type": ["concept"], "relation_type": [], "has_collection": None,
        "start_year": 0, "end_year": 1950, "zoom": 1.2, "offset": {"x": -50, "y": 25},
    }}}


def test_owner_headers_and_staff_cannot_read_or_mutate_another_view(api_client, reader_user, admin_user):
    created = graph_saves.create_view(reader_user, request_for())
    identifier = created["record"]["id"]
    api_client.force_authenticate(admin_user)
    assert api_client.get(BASE).status_code == 403
    assert api_client.get(BASE, HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 403
    own_headers = {"HTTP_X_READER_OWNER": str(admin_user.pk)}
    listed = api_client.get(BASE, **own_headers)
    assert listed.data["owner_id"] == str(admin_user.pk) and listed.data["count"] == 0
    assert listed["Cache-Control"] == "private, no-store"
    assert api_client.get(f"{BASE}{identifier}/", **own_headers).status_code == 404
    assert api_client.get(f"{BASE}by-request/", {"request_id": created["receipt"]["request_id"]}, **own_headers).status_code == 404
    patch = {**request_for(), "expected_revision": 1}
    assert api_client.patch(f"{BASE}{identifier}/", patch, format="json", **own_headers).status_code == 404
    assert SavedGraphView.objects.get(pk=identifier).revision == 1


def test_nonce_replay_and_cas_return_current_record_without_applying_twice(reader_user):
    raw = request_for()
    first = graph_saves.create_view(reader_user, raw)
    identifier = first["record"]["id"]
    assert graph_saves.create_view(reader_user, raw) == first
    patch = {"request_id": str(uuid4()), "expected_revision": 1,
        "data": {**first["record"]["data"], "title": "修改后的合成私人名称"}}
    updated = graph_saves.update_view(reader_user, identifier, patch)
    assert updated["record"]["revision"] == 2
    assert graph_saves.update_view(reader_user, identifier, patch) == updated
    replay = graph_saves.create_view(reader_user, raw)
    assert replay["record"]["revision"] == 2 and replay["receipt"]["applied_revision"] == 1
    with pytest.raises(research.ResearchConflict):
        graph_saves.update_view(reader_user, identifier, {**patch, "request_id": str(uuid4())})
    with pytest.raises(research.ResearchConflict):
        graph_saves.update_view(reader_user, identifier, {**patch, "data": raw["data"]})
    with pytest.raises(NotFound):
        graph_saves.by_request(reader_user, uuid4())
    assert GraphViewReceipt.objects.filter(user=reader_user).count() == 2


def test_delete_receipts_and_old_create_update_cannot_resurrect(reader_user):
    raw = request_for()
    first = graph_saves.create_view(reader_user, raw)
    identifier = first["record"]["id"]
    patch = {"request_id": str(uuid4()), "expected_revision": 1, "data": first["record"]["data"]}
    graph_saves.update_view(reader_user, identifier, patch)
    deletion = {"request_id": str(uuid4()), "expected_revision": 2}
    removed = graph_saves.delete_view(reader_user, identifier, deletion)
    assert removed["record"] is None and removed["receipt"]["deleted"] is True
    assert graph_saves.delete_view(reader_user, identifier, deletion) == removed
    for replay in (graph_saves.create_view(reader_user, raw), graph_saves.update_view(reader_user, identifier, patch),
                   graph_saves.by_request(reader_user, raw["request_id"])):
        assert replay["record"] is None and replay["receipt"]["deleted"] is True
    assert not SavedGraphView.objects.filter(user=reader_user).exists()
    assert GraphViewReceipt.objects.filter(user=reader_user, record__isnull=True).count() == 3
    with pytest.raises(research.ResearchConflict):
        graph_saves.create_view(reader_user, {**raw, "data": {**raw["data"], "title": "改绑旧请求"}})


def test_hidden_sources_cannot_be_introduced_but_existing_identity_is_preserved(reader_user):
    target = node()
    first = graph_saves.create_view(reader_user, request_for(target))
    KnowledgeNode.objects.filter(pk=target.pk).update(status="archived")
    changed = deepcopy(first["record"]["data"])
    changed["title"] = "来源撤回后保留的私人视图"
    updated = graph_saves.update_view(reader_user, first["record"]["id"], {
        "request_id": str(uuid4()), "expected_revision": 1, "data": changed})
    assert updated["record"]["data"]["view"]["center"] == str(target.pk)
    with pytest.raises(ValidationError):
        graph_saves.create_view(reader_user, request_for(target))
    changed["view"]["center"] = str(node("draft").pk)
    with pytest.raises(ValidationError):
        graph_saves.update_view(reader_user, first["record"]["id"], {
            "request_id": str(uuid4()), "expected_revision": 2, "data": changed})


def test_scholar_center_uses_public_profile_identity_and_candidate_edges_are_rejected(reader_user):
    person = Person.objects.create(preferred_name="合成图谱学者", authority_status="verified")
    profile = ScholarProfile.objects.create(person=person, slug=f"graph-scholar-{uuid4()}", editorial_status="published")
    raw = request_for()
    raw["data"]["view"].update(center_kind="scholar", center=str(person.pk))
    with pytest.raises(ValidationError):
        graph_saves.create_view(reader_user, raw)
    raw["data"]["view"]["center"] = str(profile.pk)
    assert graph_saves.create_view(reader_user, raw)["record"]["data"]["view"]["center"] == str(profile.pk)
    left, right = node(), node()
    edge = KnowledgeRelation.objects.create(source_node=left, target_node=right, relation_type="extends", status="draft")
    edge_request = request_for(left)
    edge_request["data"]["view"]["selected_edge"] = f"KnowledgeRelation:{edge.pk}"
    with pytest.raises(ValidationError):
        graph_saves.create_view(reader_user, edge_request)
    edge.status = "published"
    edge.save(update_fields=["status"])
    assert graph_saves.create_view(reader_user, edge_request)["record"]["data"]["view"]["selected_edge"] == f"KnowledgeRelation:{edge.pk}"


@pytest.mark.parametrize("extra", [
    {"candidate_mode": True}, {"include_candidates": True}, {"quote": "不得保存来源正文"}, {"depth": 4}, {"limit": 121},
    {"node_type": ["hidden"]}, {"relation_type": ["made_up_relation"]},
    {"zoom": float("nan")}, {"offset": {"x": float("inf"), "y": 0}}, {"start_year": True},
])
def test_strict_controls_reject_unlisted_or_invalid_state(reader_user, extra):
    raw = request_for()
    raw["data"]["view"].update(extra)
    with pytest.raises(ValidationError):
        graph_saves.create_view(reader_user, raw)
    assert not SavedGraphView.objects.filter(user=reader_user).exists()


def test_retention_off_blocks_new_writes_but_keeps_replay_and_delete(reader_user):
    raw = request_for()
    first = graph_saves.create_view(reader_user, raw)
    record = SavedGraphView.objects.get(pk=first["record"]["id"])
    assert raw["data"]["title"].encode() not in bytes(record.data_ciphertext)
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"],
        "retention": {"saved_knowledge": False}})
    assert graph_saves.create_view(reader_user, raw)["record"]["id"] == str(record.pk)
    with pytest.raises(ValidationError):
        graph_saves.create_view(reader_user, request_for())
    with pytest.raises(ValidationError):
        graph_saves.update_view(reader_user, record.pk, {"request_id": str(uuid4()), "expected_revision": 1,
            "data": first["record"]["data"]})
    assert graph_saves.delete_view(reader_user, record.pk, {"request_id": str(uuid4()), "expected_revision": 1})["receipt"]["deleted"]


def test_privacy_export_and_erasure_include_only_owned_graph_views_and_leave_tombstones(reader_user, admin_user):
    raw = request_for()
    own_result = graph_saves.create_view(reader_user, raw)
    other = graph_saves.create_view(admin_user, request_for())
    own = SavedGraphView.objects.get(pk=own_result["record"]["id"])
    exported = operation(reader_user, categories=["saved_knowledge"])
    assert run(exported)["completed"] == 1
    records = privacy.download_operation(reader_user, exported.id)["records"]
    assert len(records) == 1 and records[0]["category"] == "graph_views"
    assert raw["data"]["title"] in str(records[0]) and other["record"]["id"] not in str(records)
    erased = operation(reader_user, "erase", targets=[privacy.target_of(own, "graph_views")])
    privacy_command(reader_user, erased, "confirm")
    assert run(erased)["completed"] == 1
    assert graph_saves.create_view(reader_user, raw)["receipt"]["deleted"] is True
    assert SavedGraphView.objects.filter(user=admin_user).count() == 1
    assert KnowledgeNode.objects.filter(pk=raw["data"]["view"]["center"]).exists()
