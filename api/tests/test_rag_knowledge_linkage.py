"""Consumer integration and publication boundaries, using explicit fixtures."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from catalog import models as m
from catalog.services.document_intelligence import document_text_checksum
from catalog.services.knowledge_sources import build_structure, create_anchor, locator_payload
from reading import library_retrieval as retrieval
from reading.library_assistant import validated_source_rows
from tests.test_discovery_sessions_v308 import fixture_source
from tests.test_library_rag_task6 import query_fixture

pytestmark = pytest.mark.django_db


def anchored_source():
    edition, asset, _, _ = fixture_source(2)
    edition.is_primary = True
    edition.save(update_fields=["is_primary"])
    revision = edition.active_catalog_revision.document_revision
    revision.text_checksum = document_text_checksum(asset)
    revision.save(update_fields=["text_checksum"])
    build_structure(revision)
    anchor = create_anchor(revision, [{"page_number":p.page_number, "start":0,
        "end":len(p.text), "exact":p.text} for p in revision.page_snapshots.all()])
    value = locator_payload(anchor)
    row = {**value, "id":str(uuid4()), "title":edition.work.title, "snippet":value["exact"],
        "text":value["exact"], "authors":[], "_discovery_identity":True,
        "_coverage_entity_id":"selected-entity"}
    return edition, asset, revision, anchor, row


def test_ask_preserves_cross_page_anchor_through_source_validation(monkeypatch, reader_user):
    edition, asset, revision, anchor, row = anchored_source()
    monkeypatch.setattr(retrieval, "_result_rows", lambda *args: ([row], [{"response":{"engine":"unified"}}]))
    result = retrieval.LibraryRetrievalService().retrieve(library_query=query_fixture(),
        resolved_scope=SimpleNamespace(asset_id="", semantic_filters={"_allowed_access_statuses":["public"]}))
    assert result.sufficient and len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.original_passage == row["exact"]
    assert evidence.retrieval_provenance["coverage_entity_id"] == "selected-entity"
    assert result.metadata["evidence_anchor_validated_count"] == 1
    source = evidence.source_row()
    assert source["anchor_id"] == str(anchor.pk)
    assert [s["page_number"] for s in source["locator"]["segments"]] == [1,2]
    # A mutable page change cannot replace the pinned source supplied to RAG.
    m.Page.objects.filter(asset=asset).update(text="未发布的新正文")
    validated = validated_source_rows([source], viewer=reader_user)
    assert validated[0]["locator"]["exact"] == row["exact"]
    assert "revision=" + str(revision.pk) in validated[0]["reader_url"]
    assert not validated_source_rows([{**source, "document_revision_id":str(uuid4())}], viewer=reader_user)
    assert not validated_source_rows([{**source, "snippet":"编造的原文"}], viewer=reader_user)
    asset.access_status = "private"
    asset.save(update_fields=["access_status"])
    assert not validated_source_rows([source], viewer=reader_user)
    assert not retrieval._hydrate_evidence([row], retrieval_profile="stable", access_statuses=["public"])


def test_anchor_budget_records_actual_model_input_without_corrupting_locator():
    _, _, _, _, row = anchored_source()
    evidence = retrieval._hydrate_evidence([row], retrieval_profile="stable", access_statuses=["public"])[0]
    from dataclasses import replace
    # An explicit budget is a source excerpt, never a claim to have read it all.
    long = replace(evidence, original_passage=evidence.original_passage * 4)
    query = replace(query_fixture(), retrieval_limits={**query_fixture().retrieval_limits, "max_evidence_chars":81})
    selected = retrieval._deduplicate_and_budget([long], library_query=query)
    assert len(selected[0].original_passage) == 81
    assert selected[0].retrieval_provenance["input_coverage"]["total_characters"] == len(long.original_passage)
    assert selected[0].locator == evidence.locator


def test_published_graph_finds_other_source_without_collapsing_criticism(monkeypatch):
    from catalog.services.retrieval import knowledge_graph as graph
    from catalog.services.retrieval.search import retrieve_channel
    from catalog.services import discovery_projection as projection, discovery_sessions as sessions
    from catalog.services.knowledge_entity_queries import mentioned_entities
    from catalog.services.knowledge_public import public_entities
    from catalog.services.retrieval.locators import index_anchor
    sources = []
    person = m.Entity.objects.create(kind="person", label="同名学者", status="published")
    homonym = m.Entity.objects.create(kind="person", label="同名学者", status="published")
    concept = m.Entity.objects.create(kind="concept", label="制度概念", status="published")
    m.EntityAlias.objects.create(entity=concept, text="制度观", review_status="confirmed")
    assert {p.pk for p in mentioned_entities("同名学者如何使用制度观", public_entities())} == {person.pk, homonym.pk, concept.pk}
    for predicate, stance in (("uses", "supports"), ("criticizes", "opposes")):
        edition, asset, spans, docs = fixture_source(1)
        revision = edition.active_catalog_revision.document_revision
        revision.text_checksum = document_text_checksum(asset)
        revision.save(update_fields=["text_checksum"])
        build_structure(revision)
        from catalog.services.discovery_sources import source_header
        header = source_header("edition", edition)
        docs[0].source_revision = header["source_revision"]
        docs[0].scope_token = header["scope_token"]
        docs[0].payload = {**docs[0].payload, **header}
        docs[0].save(update_fields=["source_revision", "scope_token", "payload"])
        mapping = index_anchor(docs[0])
        anchor = m.EvidenceAnchor.objects.get(pk=mapping.target_id)
        statement = m.Assertion.objects.create(text="来源各自的学术陈述", predicate=predicate, status="published")
        m.AssertionParticipant.objects.create(assertion=statement, entity=person, role="subject")
        m.AssertionParticipant.objects.create(assertion=statement, entity=concept, role="object")
        m.AssertionSource.objects.create(assertion=statement, work=edition.work, edition=edition, document_revision=revision)
        m.AssertionEvidence.objects.create(assertion=statement, anchor=anchor, stance=stance)
        sources.append((edition, asset, docs[0], statement))
    first, second = sources
    generation = first[2].generation
    second[2].generation = generation
    second[2].save(update_fields=["generation"])
    refs = [{"id":str(first[2].pk), "source_revision":first[2].source_revision}]
    raw = projection.validate_discovery_results("passages", refs, ["public"])
    scopes = [s[2].scope_token for s in sources]
    candidates, meta = graph.recall("制度观", raw, ["public"], generation=generation, scopes=scopes, filters={})
    assert {r["id"] for r in candidates} == {str(s[2].pk) for s in sources}
    assert meta["assertions"] == 2 and meta["iterations"] > 0
    checked = projection.validate_discovery_results("passages", candidates, ["public"])
    assert {p["predicate"] for r in checked for p in r["knowledge_paths"]} == {"uses", "criticizes"}
    assert {e["stance"] for r in checked for p in r["knowledge_paths"] for e in p["evidence"]} == {"supports", "opposes"}
    assert all(r["text"] == next(s[2].text for s in sources if str(s[2].pk) == r["id"]) for r in checked)
    # The actual application service includes the branch in the same fusion.
    def base(*args, **kwargs):
        kwargs["request_context"].update(generation=generation, passage_scopes=scopes)
        return {"sparse":raw, "dense":[], "contextual":[], "warnings":[]}
    monkeypatch.setattr(projection, "discovery_candidates", base)
    monkeypatch.setattr(sessions, "_rerank", lambda query, rows, *args: (rows, []))
    result = retrieve_channel("制度观", "passages", {}, ["public"])
    assert {r["id"] for r in result["rows"]} == {str(s[2].pk) for s in sources}
    assert result["retrieval"]["knowledge_graph"]["candidates"] == 2
    # Filtering still applies after fusion, even to a deliberately wrong scope.
    assert len(projection.validate_discovery_results("passages", candidates, ["public"],
        filters={"work_ids":[str(first[0].work_id)]})) == 1
    # Session references re-read the public statement. Rejection/withdrawal
    # removes the explanation without rewriting the original quotation.
    stored = [sessions._reference(row) for row in checked]
    second[3].status = "draft"
    second[3].save(update_fields=["status"])
    fresh = projection.validate_discovery_results("passages", stored, ["public"])
    assert not next(r for r in fresh if r["id"] == str(second[2].pk))["knowledge_paths"]
    second[1].access_status = "private"
    second[1].save(update_fields=["access_status"])
    assert len(projection.validate_discovery_results("passages", stored, ["public"])) == 1
