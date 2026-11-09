"""Important source, model-off and editorial transport boundaries."""
from uuid import uuid4
from unittest.mock import patch
import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import PermissionDenied
from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services.knowledge_sources import build_structure, context
from catalog.services.source_workspace import source_directory, verify_selection, inspect_retrieval
from catalog.services.knowledge_workspace import open_page, page_workspace
from catalog.services.knowledge_core import apply_page_patch, page_content


@pytest.mark.django_db
def test_context_windows_cover_raw_text_once_and_preserve_codepoints(source, admin_user):
    structure = build_structure(source)
    node = structure.nodes.get(kind="document")
    expected = "".join(v.page.text[v.start:v.end] for v in node.segments.select_related("page"))
    offset, text = 0, ""
    while True:
        value = context(node, admin_user, editorial=True, budget=5, offset=offset)
        assert value["offset_unit"] == "unicode_code_point"
        text += "".join(v["exact"] for v in value["segments"])
        if value["next_offset"] is None:
            break
        assert value["next_offset"] > offset
        offset = value["next_offset"]
    assert text == expected and "😀" in text


@pytest.mark.django_db
def test_selection_is_verified_idempotent_and_not_public(source, admin_user, reader_user, api_client):
    build_structure(source)
    page = source.page_snapshots.get(page_number=1)
    start = page.text.index("😀")
    segment = {"page_number": 1, "start": start, "end": start+1, "exact": "😀"}
    one = verify_selection(admin_user, source.pk, [segment])
    assert verify_selection(admin_user, source.pk, [segment])["anchor_id"] == one["anchor_id"]
    assert m.EvidenceAnchor.objects.count() == 1 and not m.Assertion.objects.exists()
    with pytest.raises(PermissionDenied):
        verify_selection(reader_user, source.pk, [segment])
    api_client.force_authenticate(reader_user)
    assert api_client.get("/api/search/sources/").status_code == 403
    assert api_client.post("/api/search/inspect/", {"q": "测试"}, format="json").status_code == 403


@pytest.mark.django_db
def test_source_status_does_not_infer_searchability_from_reading(source, admin_user):
    value = source_directory(admin_user, revision_id=source.pk)["sources"][0]
    assert value["keywords"] == value["semantic"] == "pending"
    assert not value["published"]
    result = inspect_retrieval(admin_user, "测试", revision_id=source.pk, mode="keyword")
    assert result["status"] == "unpublished"


@pytest.mark.django_db
def test_keyword_inspection_does_not_call_reranker(admin_user):
    from catalog.services.retrieval.search import retrieve_channel
    with patch("catalog.services.discovery_projection.discovery_candidates", return_value={"sparse": [], "dense": [], "warnings": []}), \
         patch("catalog.services.discovery_projection.validate_discovery_results", side_effect=lambda c, rows, *a, **kw: rows), \
         patch("catalog.services.discovery_sessions._rerank", side_effect=AssertionError("model called")):
        assert retrieve_channel("测试", "passages", {"_keyword_only": True}, ["public"])["rows"] == []


@pytest.mark.django_db
def test_page_reuses_identity_and_preserves_rich_text(source, admin_user):
    page = open_page(admin_user, work_id=source.asset.edition.work_id)
    assert open_page(admin_user, work_id=source.asset.edition.work_id)["id"] == page["id"]
    key = str(uuid4())
    apply_page_patch({"page_id": page["id"], "operation": "add", "block_id": key, "block": {
        "id": key, "type": "analysis", "text": "保留文字格式", "text_marks": [{"kind": "strong", "start": 0, "end": 2}],
        "references": [{"type": "work", "id": str(source.asset.edition.work_id), "edition_id": str(source.asset.edition_id)}]}},
        admin_user, request_key=str(uuid4()))
    saved = m.KnowledgePage.objects.get(pk=page["id"])
    assert page_content(saved)[0][0]["text_marks"] == [{"kind": "strong", "start": 0, "end": 2}]
    assert page_workspace(saved, admin_user)["references"][0]["title"]


@pytest.mark.django_db
def test_missing_physical_index_is_not_reported_as_ready(source, admin_user):
    from catalog.services.discovery_projection import DiscoveryIndexError
    m.SemanticIndexVersion.discovery_objects.create(index_family="discovery", uid="missing-fixture", status="active")
    with patch("catalog.services.source_workspace.meili", side_effect=DiscoveryIndexError("index_missing")):
        row = source_directory(admin_user, revision_id=source.pk)["sources"][0]
    assert row["keywords"] == row["semantic"] == "unavailable"
    assert row["index_error"]


@pytest.mark.django_db
def test_recovery_refuses_existing_index_without_touching_records():
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from ingestion.models import ProcessingJob
    g = m.SemanticIndexVersion.discovery_objects.create(index_family="discovery", uid="retained-fixture", status="active")
    with patch("catalog.management.commands.restore_missing_discovery_index.meili", return_value={"uid": g.uid}), pytest.raises(CommandError):
        call_command("restore_missing_discovery_index", generation=str(g.pk), initialize_missing=True)
    assert not ProcessingJob.objects.filter(stats__action="restore_projection").exists()
