"""Risk checks for materialized paging and task ownership; no model mocks claim
to establish actual retrieval relevance or NAS model readiness.
"""
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.discovery_models import DiscoverySearchSession
from catalog.discovery_index_models import DiscoveryDocument
from catalog.models import (Asset, CatalogPublicationRevision, DocumentRevision, Edition,
                            EvidenceSpan, Page, SemanticIndexVersion, Work)
from catalog.services import discovery_sessions as sessions
from catalog.services.discovery_context import session_context
from catalog.services.discovery_projection import validate_discovery_results
from catalog.services.discovery_sources import fingerprint, source_header, source_units

pytestmark = pytest.mark.django_db


def fixture_source(count=7):
    work = Work.objects.create(title="正式检索材料", document_type="book")
    edition = Edition.objects.create(work=work, state="published")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
                                 sha256=uuid4().hex * 2, access_status="public", page_count=count)
    document = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum=asset.sha256,
                                               text_checksum="b" * 64)
    spans = []
    for number in range(1, count + 1):
        text = f"第 {number} 段来自同一正式修订的真实夹具文本。"
        page = Page.objects.create(asset=asset, index=number, text=text, text_source="native")
        spans.append(EvidenceSpan.objects.create(document_revision=document, page=page, page_number=number,
            original_text=text, content_hash=fingerprint(text), start_offset=0, end_offset=len(text)))
    revision = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active",
        metadata_ready=True, fulltext_ready=True, reader_asset=asset, document_revision=document,
        snapshot={"work": {"title": work.title, "document_type": "book", "language": "zh"},
                  "edition": {"publication_year": 2020}}, content_fingerprint=uuid4().hex)
    edition.active_catalog_revision = revision
    edition.save(update_fields=["active_catalog_revision"])
    generation = SemanticIndexVersion.discovery_objects.create(uid=f"discovery-test-{uuid4().hex}",
        index_family="discovery", status="active", provider="userProvided", config_snapshot={
            "embedding_artifact": "test-embed", "reranker_artifact": "test-reranker"})
    header = source_header("edition", edition)
    documents = []
    for unit in source_units("edition", edition, header):
        text = unit["text"]
        documents.append(DiscoveryDocument.objects.create(generation=generation, channel="passages",
            source_type="edition", source_id=edition.pk, edition=edition, document_revision=document,
            source_revision=header["source_revision"], scope_token=header["scope_token"], access_status="public",
            input_hash=fingerprint(text), text=text, normalized_text=text, token_count=20, start_offset=0,
            end_offset=len(text), keyword_ready=True, vector_ready=True,
            payload={**header, **unit["metadata"], "unit_hash": fingerprint(text)}))
    return edition, asset, spans, documents


def make_session(documents=(), owner=None, status="completed"):
    return DiscoverySearchSession.objects.create(owner=owner, token_hash=sessions._token_hash("test-capability"),
        query="正式检索材料", access_statuses=["inherit", "public"], status=status, task_id=str(uuid4()),
        expires_at=timezone.now() + timedelta(hours=1), filters={},
        results={"passages": [{"id": str(doc.pk), "source_revision": doc.source_revision, "match_basis": ["原文命中"]}
                              for doc in documents], "entities": [], "curation": []},
        channels={key: {"status": "completed"} for key in sessions.CHANNELS})


def request(user=None, token=""):
    return SimpleNamespace(user=user or AnonymousUser(), headers={"X-Discovery-Token": token})


def test_cursor_survives_withdrawn_earlier_rows_without_skipping_or_repeating():
    _, _, spans, docs = fixture_source()
    session = make_session(docs)
    first = sessions.serialize_session(session, ["public"], limit=3)
    assert [row["id"] for row in first["passages"]] == [str(doc.pk) for doc in docs[:3]]
    EvidenceSpan.objects.filter(pk__in=[spans[0].pk, spans[3].pk]).update(is_stale=True)
    second = sessions.serialize_session(session, ["public"], cursor=first["next_cursor"], limit=3)
    assert [row["id"] for row in second["passages"]] == [str(doc.pk) for doc in docs[4:7]]
    assert second["count"] == 5
    assert second["source_changed"] is True
    assert second["next_cursor"] is None
    assert first["passages"][0]["excerpt"] == docs[0].text
    assert "scope_token" not in first["passages"][0]


@pytest.mark.parametrize("change", ["private", "registered", "withdrawn", "source_text", "wrong_revision"])
def test_old_session_does_not_return_revoked_or_changed_source(change):
    edition, asset, spans, docs = fixture_source(1)
    session = make_session(docs)
    assert sessions.serialize_session(session, ["public"])["count"] == 1
    if change in {"private", "registered"}:
        Asset.objects.filter(pk=asset.pk).update(access_status=change)
    elif change == "withdrawn":
        Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    elif change == "source_text":
        EvidenceSpan.objects.filter(pk=spans[0].pk).update(original_text="来源修订后不同内容")
    else:
        session.results["passages"][0]["source_revision"] = "wrong-revision"
    assert sessions.serialize_session(session, ["public"])["passages"] == []
    assert sessions.serialize_session(session, ["public"])["count"] == 0
    with pytest.raises(NotFound):
        session_context(session, str(docs[0].pk), ["public"])


def test_anonymous_capability_and_owner_are_not_interchangeable(reader_user, admin_user):
    anonymous = make_session()
    assert sessions.get_session(request(token="test-capability"), anonymous.pk).pk == anonymous.pk
    with pytest.raises(NotFound):
        sessions.get_session(request(), anonymous.pk)
    with pytest.raises(NotFound):
        sessions.get_session(request(token="wrong"), anonymous.pk)
    private = make_session(owner=reader_user)
    assert sessions.get_session(request(reader_user), private.pk).pk == private.pk
    with pytest.raises(NotFound):
        sessions.get_session(request(admin_user, "test-capability"), private.pk)
    with pytest.raises(NotFound):
        sessions.get_session(request(token="test-capability"), private.pk)


def test_cursor_is_bound_to_session():
    _, _, _, docs = fixture_source(4)
    first, other = make_session(docs), make_session(docs)
    cursor = sessions.serialize_session(first, ["public"])["next_cursor"]
    with pytest.raises(ValidationError):
        sessions.serialize_session(other, ["public"], cursor=cursor)


def test_cancel_during_retrieval_blocks_late_channel_write(monkeypatch):
    session = make_session(status="queued")
    calls = []
    def candidates(*args, **kwargs):
        calls.append(args[1])
        sessions.cancel_session(session)
        return {"sparse": [], "dense": [], "version": "v1", "warnings": [], "reranker_artifact": "test-reranker"}
    monkeypatch.setattr("catalog.services.discovery_projection.discovery_candidates", candidates)
    sessions.execute_session(session.pk, session.generation, session.task_id)
    session.refresh_from_db()
    assert session.status == "canceled"
    assert session.generation == 2
    assert calls == ["entities"]
    assert all(not rows for rows in session.results.values())


def test_duplicate_task_cannot_reclaim_running_session(monkeypatch):
    session = make_session(status="running")
    def forbidden(*args, **kwargs):
        raise AssertionError("Duplicate task performed retrieval")
    monkeypatch.setattr("catalog.services.discovery_projection.discovery_candidates", forbidden)
    sessions.execute_session(session.pk, session.generation, session.task_id)
    session.refresh_from_db()
    assert session.status == "running"


def test_expansion_append_and_stale_task_cannot_overwrite(monkeypatch):
    _, _, _, docs = fixture_source(5)
    session = make_session(docs[:2])
    old_task, old_generation = session.task_id, session.generation
    monkeypatch.setattr(sessions, "_enqueue", lambda *args: None)
    expanded = sessions.expand_session(session, ["public"])
    assert expanded.access_statuses == ["public"]
    calls, contexts = [], []
    def candidates(query, channel, filters, access_statuses, **kwargs):
        calls.append((channel, kwargs["limit"], kwargs["expanded"]))
        contexts.append(kwargs["request_context"])
        rows = validate_discovery_results("passages", [{"id": str(doc.pk), "source_revision": doc.source_revision}
                                                        for doc in reversed(docs)], ["public"]) if channel == "passages" else []
        return {"sparse": rows, "dense": [], "version": "v1", "warnings": [], "reranker_artifact": "test-reranker"}
    monkeypatch.setattr("catalog.services.discovery_projection.discovery_candidates", candidates)
    seen_artifact = []
    def rerank(query, documents, top_n=20, expected_artifact=""):
        seen_artifact.append(expected_artifact)
        return {"results": [{"index": index} for index in range(top_n)]}
    monkeypatch.setattr("catalog.services.discovery_inference.rerank", rerank)
    sessions.execute_session(session.pk, old_generation, old_task)
    assert calls == []
    sessions.execute_session(expanded.pk, expanded.generation, expanded.task_id)
    expanded.refresh_from_db()
    assert [row["id"] for row in expanded.results["passages"][:2]] == [str(doc.pk) for doc in docs[:2]]
    assert len(expanded.results["passages"]) == 5
    assert calls[-1] == ("passages", 300, True)
    assert contexts[0] is contexts[1] is contexts[2]
    assert seen_artifact == ["test-reranker"]
    with pytest.raises(ValidationError):
        sessions.expand_session(expanded)


def test_context_is_same_revision_and_bounded_neighbouring_pages():
    _, asset, _, docs = fixture_source(5)
    session = make_session(docs)
    context = session_context(session, str(docs[2].pk), ["public"])
    assert context["asset_id"] == str(asset.pk)
    assert [block["pdf_page"] for block in context["blocks"]] == [2, 3, 4]
    assert [block["role"] for block in context["blocks"]] == ["before", "hit", "after"]
    with pytest.raises(NotFound):
        session_context(session, str(uuid4()), ["public"])
