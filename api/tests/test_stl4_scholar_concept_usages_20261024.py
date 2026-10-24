"""Deferred original-node usage aggregation and scholar placement isolation."""
from uuid import uuid4
import pytest
from catalog.models import EditorialRevision, EvidenceSpan
from catalog.services import content_placements as placements, editorial_issues as ledger
from .test_stl4_person_node_directory_20261024 import node, scholar
from .test_stl4_person_node_sources_20261024 import material

pytestmark = pytest.mark.django_db


def snapshot(concept, person, span):
    return {"page_type": "node", "page_id": str(concept.pk), "items": [{"id": str(uuid4()), "area": "concept-usages", "group": "用法", "position": 0,
        "target": {"type": "span", "id": str(span.pk), "document_revision_id": str(span.document_revision_id)}, "reason": "", "local_text": "",
        "concept_usage": {"source_person_id": str(person.pk), "term": "验收术语", "review_status": "candidate", "usage_type": "application",
            "interpretation": "待核对的解释", "attribution_note": "明确归属依据", "internal_note": "仅供编辑"}}]}


def endpoint(profile):
    return f"/api/catalog/admin/scholars/{profile.pk}/concept-usages/"


def test_current_author_assignment_comes_only_from_latest_original_node_ledger(api_client, admin_user):
    first, second = scholar(), scholar()
    concept, (span, _, _) = node(), material()
    body = snapshot(concept, first.person, span)
    before = ledger._save_revision(placements.KIND, placements.target_id("node", concept.pk), body, admin_user)
    api_client.force_authenticate(admin_user)
    result = api_client.get(endpoint(first))
    assert result.status_code == 200 and result.data["count"] == 1
    group = result.data["results"][0]
    assert group["revision_id"] == str(before.pk) and group["items"][0]["id"] == body["items"][0]["id"]
    assert group["items"][0]["source"]["text"] == span.original_text
    assert api_client.get(endpoint(second)).data["count"] == 0
    body["items"][0]["concept_usage"]["source_person_id"] = str(second.person_id)
    ledger._save_revision(placements.KIND, placements.target_id("node", concept.pk), body, admin_user)
    assert api_client.get(endpoint(first)).data["count"] == 0
    assert api_client.get(endpoint(second)).data["count"] == 1
    ledger._save_revision(placements.KIND, placements.target_id("node", concept.pk), {**body, "items": [], "withdrawn": True}, admin_user)
    assert api_client.get(endpoint(second)).data["count"] == 0


def test_stale_sources_are_kept_for_review_and_editor_only_read_route_is_paginated(api_client, admin_user, reader_user):
    profile = scholar()
    span, _, _ = material()
    for index in range(7):
        concept = node(f"用法分组{index}")
        ledger._save_revision(placements.KIND, placements.target_id("node", concept.pk), snapshot(concept, profile.person, span), admin_user)
    EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    api_client.force_authenticate(admin_user)
    first = api_client.get(endpoint(profile)).data
    second = api_client.get(endpoint(profile), {"page": 2}).data
    assert first["count"] == 7 and len(first["results"]) == 6 and len(second["results"]) == 1
    assert first["results"][0]["items"][0]["source"] is None
    assert api_client.get(endpoint(profile), {"page": 3}).status_code == 404
    assert api_client.post(endpoint(profile), {}, format="json").status_code == 405
    api_client.force_authenticate(reader_user)
    assert api_client.get(endpoint(profile)).status_code == 403


def test_scholar_material_edit_preserves_original_page_identity_and_node_records(admin_user):
    profile, concept = scholar(), node()
    span, _, _ = material()
    original = ledger._save_revision(placements.KIND, placements.target_id("node", concept.pk), snapshot(concept, profile.person, span), admin_user)
    item = {"id": str(uuid4()), "target": {"type": "span", "id": str(span.pk), "document_revision_id": str(span.document_revision_id)}, "area": "materials"}
    saved = placements.command("scholar", profile.pk, {"action": "save", "request_id": str(uuid4()), "expected_revision": "0", "items": [item]}, admin_user)
    assert saved["page_type"] == "scholar" and saved["page_id"] == str(profile.pk)
    assert placements.revisions("node", concept.pk).first().pk == original.pk
    assert EditorialRevision.objects.get(pk=saved["revision_id"]).target_id == placements.target_id("scholar", profile.pk)
