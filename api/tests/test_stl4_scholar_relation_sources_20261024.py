"""Exact sources survive migration and reviewed revisions without leaking drafts."""
from uuid import uuid4
import pytest
from django.http import Http404
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services import shared_curation as service
from catalog.services.knowledge_migration import migrate_relation, migrate_assertion_page
from catalog.services.knowledge_public import assertion_data, page_data, publish_page
from catalog.services.knowledge_workspace import submit_page_assertion, source_hash
from catalog.services.knowledge_core import page_content
from catalog.services.academic_projection import scholar_links
from .test_stl4_scholar_relation_commands_20261024 import profiles, publish
from .test_stl4_person_node_sources_20261024 import material as legacy_material
from .test_manual_knowledge_sources import apply_all
pytestmark = pytest.mark.django_db


def material():
    span, asset, page = legacy_material()
    from catalog.services.document_intelligence import document_text_checksum
    from catalog.services.knowledge_sources import snapshot_revision
    asset.sha256 = uuid4().hex * 2
    asset.save(update_fields=["sha256"])
    revision = span.document_revision
    revision.source_checksum, revision.text_checksum = asset.sha256, document_text_checksum(asset)
    revision.save(update_fields=["source_checksum", "text_checksum"])
    snapshot_revision(revision)
    return span, asset, page


def reference(span):
    return {"span_id": str(span.pk), "document_revision_id": str(span.document_revision_id)}


def payload(first, second, span):
    return {"request_id": str(uuid4()), "source_scholar": str(first.pk), "target_scholar": str(second.pk),
        "relation_type": "influence", "direction": "directed", "summary": "隔离测试关系", "source": "", "source_anchor": reference(span)}


def historical(first, second, span):
    data = payload(first, second, span)
    row = m.ScholarRelation.objects.create(source_scholar=first, target_scholar=second, relation_type="influence",
        summary=data["summary"], evidence_span=span, source_document_revision=span.document_revision, status="published")
    revision = m.EditorialRevision.objects.create(target_type="scholar_relation", target_id=row.pk, revision=1,
        status="published", materialized_preview=data, idempotency_key=str(uuid4()))
    row.active_revision = revision
    row.save(update_fields=["active_revision"])
    return row


def test_draft_quote_and_published_quote_keep_separate_original_versions(admin_user, reader_user):
    first, second = profiles()
    old, _, _ = material()
    new, _, _ = material()
    draft = service.save_relation(None, payload(first, second, old), admin_user)
    page = publish(draft, admin_user)
    original = m.Assertion.objects.get()
    first_anchor = original.evidence.get().anchor
    from catalog.services.knowledge_sources import migrate_span
    new_anchor = migrate_span(new).target_id
    revised = {"text": "新版隔离测试关系", "predicate": "criticizes", "expression": "editorial_judgment",
        "supersedes_id": str(original.pk), "base_hash": source_hash("assertion", original.pk),
        "participants": [{"role": v.role, "entity_id": str(v.entity_id)} for v in original.participants.all()],
        "evidence": [{"anchor_id": str(new_anchor), "stance": "context"}]}
    pending = submit_page_assertion(page, revised, admin_user, request_id=uuid4())
    assert not apply_all(pending, admin_user)["blocked"]
    assert [v.pk for v in scholar_links()] == [original.pk]
    assert assertion_data(original, reader_user)["evidence"][0]["locator"]["document_revision_id"] == str(old.document_revision_id)
    assert assertion_data(original, None)["evidence"][0].get("locator") is None
    publish_page(page.pk, page_data(page, admin_user, draft=True)["revision_id"], admin_user)
    original.refresh_from_db()
    assert original.status == "superseded" and original.evidence.get().anchor_id == first_anchor.pk
    assert len(list(scholar_links())) == 1 and list(scholar_links())[0].pk != original.pk


@pytest.mark.parametrize("damage", ["private", "stale", "wrong_revision"])
def test_historical_source_gaps_never_fabricate_locators(admin_user, damage):
    first, second = profiles()
    span, asset, _ = material()
    row = historical(first, second, span)
    if damage == "private":
        m.Asset.objects.filter(pk=asset.pk).update(access_status="restricted")
    elif damage == "stale":
        m.EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    else:
        other, _, _ = material()
        row.source_document_revision = other.document_revision
        row.save(update_fields=["source_document_revision"])
    assert service.relation_payload(row, public=True)["source_material"] is None
    result = migrate_relation(m.ScholarRelation.objects.get(pk=row.pk))
    statement = m.Assertion.objects.get(pk=result.target_id)
    assert statement.text == row.summary and statement.origin["human_confirmation_preserved"]
    assert statement.origin["history"]["editorial"][0]["id"] == str(row.active_revision_id)
    if damage == "wrong_revision":
        assert not statement.evidence.exists()
    assert m.ScholarRelation.objects.get(pk=row.pk).active_revision_id == row.active_revision_id
    assert migrate_relation(row).target_id == statement.pk


def test_reference_input_is_strict_and_unpublished_source_cannot_publish(admin_user):
    first, second = profiles()
    span, asset, _ = material()
    data = payload(first, second, span)
    for ref in ({**reference(span), "quote": "不得改写"}, {**reference(span), "document_revision_id": str(uuid4())}):
        with pytest.raises(ValidationError):
            service.save_relation(None, {**data, "source_anchor": ref}, admin_user)
    draft = service.save_relation(None, data, admin_user)
    assert not apply_all(draft, admin_user)["blocked"]
    m.Edition.objects.filter(pk=asset.edition_id).update(state="draft")
    page = m.KnowledgePage.objects.get(entity=draft.subject_entity)
    with pytest.raises(Http404):
        publish_page(page.pk, page_data(page, admin_user, draft=True)["revision_id"], admin_user)
    assert m.Assertion.objects.get().status == "draft"


def test_migration_keeps_unpublished_revision_and_never_resurrects_withdrawn_relation():
    first, second = profiles()
    span, _, _ = material()
    row = historical(first, second, span)
    m.EditorialRevision.objects.create(target_type="scholar_relation", target_id=row.pk, revision=2,
        status="draft", materialized_preview={**payload(first, second, span), "summary": "未发布修改"}, idempotency_key=str(uuid4()))
    statement = m.Assertion.objects.get(pk=migrate_relation(row).target_id)
    migrate_assertion_page(statement)
    assert statement.text == row.summary and len(statement.origin["history"]["editorial"]) == 2
    assert len(list(scholar_links())) == 1
    statement.status = "withdrawn"
    statement.save(update_fields=["status"])
    assert not list(scholar_links())
    assert service.relation_payload(row)["summary"] == "未发布修改"
