"""Source-preserving relation migration, review and delayed withdrawal."""
from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_core import entity_for_legacy, page_content
from catalog.services.knowledge_migration import migrate_relation, migrate_assertion_page
from catalog.services.academic_relations import legacy_relation_draft, submit_withdrawal, relation_directory
from catalog.services.academic_projection import person_node_links
from catalog.services.knowledge_public import publish_page, page_data
from catalog.services.knowledge_workspace import source_hash
from catalog.services.intelligence_queries import changeset_data
from tests.test_manual_knowledge_sources import apply_all

pytestmark = pytest.mark.django_db


def legacy(actor):
    person = m.Person.objects.create(preferred_name="关系测试学者", authority_status="verified")
    m.ScholarProfile.objects.create(person=person, slug="relation-command-scholar", editorial_status="published")
    node = m.KnowledgeNode.objects.create(canonical_name_zh="关系测试概念", node_type="concept", slug="relation-command-node", status="published")
    row = m.PersonNodeRelation.objects.create(person=person, node=node, status="published", relation_type="uses",
        direction="directed", relation_label="原人工使用关系", source="原人工书目出处", reviewed_by=actor)
    mapping = migrate_relation(row)
    statement = m.Assertion.objects.get(pk=mapping.target_id)
    page_map = migrate_assertion_page(statement)
    return row, statement, m.KnowledgePage.objects.get(pk=page_map.provenance["page_id"])


def test_legacy_relation_page_and_new_source_keep_history(admin_user):
    row, statement, page = legacy(admin_user)
    assert str(migrate_assertion_page(statement).target_id) == page.body_blocks[0]["id"]
    assert m.PersonNodeRelation.objects.count() == 1
    assert len(list(person_node_links(person_ids=[row.person_id]))) == 1
    assert page_data(page, admin_user)["assertions"][0]["id"] == str(statement.pk)
    draft = legacy_relation_draft("person", {"person": row.person, "node": row.node, "text": "另一作品中的批评",
        "relation_type": "criticizes", "source_citation": "另一作品的人工出处"}, admin_user, request_id=uuid4())
    assert m.Assertion.objects.count() == 1 and m.PersonNodeRelation.objects.count() == 1
    result = apply_all(draft, admin_user)
    assert not result["blocked"], result
    assert m.Assertion.objects.count() == 2 and m.PersonNodeRelation.objects.count() == 1
    publish_page(page.pk, page_content(page)[1].pk, admin_user)
    assert len(list(person_node_links(person_ids=[row.person_id]))) == 2
    assert {v.relation_type for v in person_node_links(person_ids=[row.person_id])} == {"uses", "criticizes"}
    assert relation_directory(admin_user, entity_id=entity_for_legacy(row.person).pk)["count"] == 2


def test_withdrawal_is_reviewed_draft_until_publish_and_never_deletes_legacy(admin_user):
    row, statement, page = legacy(admin_user)
    request = uuid4()
    draft = submit_withdrawal(statement, admin_user, request_id=request, base_hash=source_hash("assertion", statement.pk), reason="原解释需要撤回")
    assert submit_withdrawal(statement, admin_user, request_id=request, base_hash=source_hash("assertion", statement.pk), reason="原解释需要撤回").pk == draft.pk
    result = apply_all(draft, admin_user)
    assert not result["blocked"], result
    statement.refresh_from_db()
    assert statement.status == "published" and len(list(person_node_links(person_ids=[row.person_id]))) == 1
    assert changeset_data(draft, admin_user)["items"]
    preview = page_data(page, admin_user, draft=True)
    assert len(preview["publication_scope"]["withdrawals"]) == 1
    revision = page_content(page)[1]
    publish_page(page.pk, revision.pk, admin_user)
    publish_page(page.pk, revision.pk, admin_user)
    statement.refresh_from_db(); row.refresh_from_db()
    assert statement.status == "withdrawn" and row.status == "published"
    assert list(person_node_links(person_ids=[row.person_id])) == []
    assert m.PersonNodeRelation.objects.filter(pk=row.pk).exists()
    assert changeset_data(draft, admin_user)["status"] == "published"


def test_historical_backfill_defers_live_draft(admin_user):
    row, statement, page = legacy(admin_user)
    second = m.Assertion.objects.create(text="另一历史解释", status="published", origin={"human_confirmation_preserved":True})
    m.AssertionParticipant.objects.create(assertion=second, role="subject", entity=entity_for_legacy(row.person))
    m.EditorialRevision.objects.create(target_type="knowledge_page", target_id=page.pk, revision=2,
        materialized_preview={"body_blocks":page.body_blocks}, idempotency_key="pending-human-edit")
    with pytest.raises(ValidationError, match="暂缓"):
        migrate_assertion_page(second)
    assert m.EditorialRevision.objects.filter(idempotency_key="pending-human-edit").exists()
    page.refresh_from_db()
    assert len(page.body_blocks) == 1


def test_legacy_http_write_is_changeset_and_reader_cannot_write(admin_user, reader_user, api_client):
    node = m.KnowledgeNode.objects.create(canonical_name_zh="HTTP主体", slug="http-subject", node_type="concept")
    other = m.KnowledgeNode.objects.create(canonical_name_zh="HTTP客体", slug="http-object", node_type="concept")
    body = {"source_node": str(node.pk), "target_node": str(other.pk), "relation_type": "criticizes",
        "description": "隔离测试批评关系", "evidence_source": "隔离测试文献出处", "status": "published"}
    api_client.force_authenticate(admin_user)
    key = str(uuid4())
    response = api_client.post("/api/catalog/admin/theory-system/relations/", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 202, response.data
    again = api_client.post("/api/catalog/admin/theory-system/relations/", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert again.status_code == 202 and again.data["id"] == response.data["id"]
    assert not m.KnowledgeRelation.objects.exists() and not m.Assertion.objects.exists()
    api_client.force_authenticate(reader_user)
    assert api_client.post("/api/catalog/admin/theory-system/relations/", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code == 403


def test_catalog_selector_does_not_delete_confirmed_relation_or_publish_new_one(admin_user):
    from catalog.services.work_editor import apply_work_knowledge
    work = m.Work.objects.create(title="编目测试作品")
    old_node = m.KnowledgeNode.objects.create(canonical_name_zh="旧概念", slug="catalog-old", node_type="concept", status="published")
    new_node = m.KnowledgeNode.objects.create(canonical_name_zh="新概念", slug="catalog-new", node_type="concept", status="published")
    old = m.WorkNodeRelation.objects.create(work=work, node=old_node, status="published", role="general_mention")
    apply_work_knowledge(work, {"nodes":[{"id":new_node.pk,"role":"critique","strength":"medium"}]}, admin_user)
    old.refresh_from_db()
    assert old.status == "published" and m.WorkNodeRelation.objects.count() == 1
    draft = m.ChangeSet.objects.get(subject_work=work)
    assert draft.items.filter(kind="assertion", decision="pending").exists()
    assert not m.Assertion.objects.exists()


def test_retired_producer_cannot_create_old_candidates(admin_user):
    from catalog.services.theory_suggestions import generate_theory_review_tasks
    from types import SimpleNamespace
    work = m.Work.objects.create(title="退役入口测试")
    result = generate_theory_review_tasks(SimpleNamespace(edition=SimpleNamespace(work_id=work.pk)), actor=admin_user)
    assert result["retired"] and not result["enabled"]
    assert not m.WorkNodeRelation.objects.exists() and not m.TheoryReviewTask.objects.exists()


def test_internal_provenance_is_not_citation_and_v3_repair_preserves_manual_history(admin_user):
    row, statement, page = legacy(admin_user)
    row.source = "workflow_section_confirmation"
    row.save(update_fields=["source"])
    m.KnowledgeLegacyMapping.objects.filter(source_type=row._meta.label_lower, source_id=row.pk).update(provenance={"migration_version": 3})
    statement.sources.update(citation=row.source)
    m.AssertionSource.objects.create(assertion=statement, citation="独立补充的真实人工出处", expression="editorial_judgment")
    migrate_relation(row)
    statement.refresh_from_db()
    assert set(statement.sources.values_list("citation", flat=True)) == {"", "独立补充的真实人工出处"}
    assert statement.origin["migration_v2"]["record"]["source"] == row.source
    assert page_data(page, admin_user)["assertions"][0]["predicate_label"] == "使用"
    assert m.PersonNodeRelation.objects.get(pk=row.pk).source == row.source


def test_public_theory_and_catalog_read_canonical_relations_without_publishing_catalog_draft(admin_user):
    from catalog.theory_serializers import KnowledgeNodeDetailSerializer
    from catalog.serializers import WorkDetailSerializer
    from catalog.services.publication_eligibility import active_catalog_snapshot
    from catalog.services.discovery_sources import edition_metadata_header
    from tests.v304_helpers import activate_catalog_revision
    work = m.Work.objects.create(title="原已发布书名")
    edition = m.Edition.objects.create(work=work, state="published", public_slug=str(uuid4()))
    activate_catalog_revision(edition, fulltext_ready=False)
    node = m.KnowledgeNode.objects.create(canonical_name_zh="已公开概念", slug="canonical-consumer", node_type="concept", status="published")
    draft = legacy_relation_draft("work", {"work": work, "node": node, "role": "critique",
        "text": "本作品批评这一概念的适用条件", "source_citation": "人工明确记载的文献出处"}, admin_user, request_id=uuid4())
    result = apply_all(draft, admin_user)
    assert not result["blocked"], result
    page = m.KnowledgePage.objects.get(work=work)
    assert not KnowledgeNodeDetailSerializer(node).data["work_groups"]
    publish_page(page.pk, page_content(page)[1].pk, admin_user)
    work.title = "尚未发布的书名修改"
    work.save(update_fields=["title"])
    edition.refresh_from_db()
    data = KnowledgeNodeDetailSerializer(node).data
    assert data["work_count"] == 1 and data["work_groups"]["critique"][0]["assertion_id"]
    snapshot = active_catalog_snapshot(edition)
    assert snapshot["work"]["title"] == "原已发布书名"
    assert snapshot["knowledge"]["nodes"][0]["id"] == str(node.pk)
    assert edition_metadata_header(edition)["theories"][0]["id"] == str(node.pk)
    assert WorkDetailSerializer(work).data["theory_associations"][0]["role"] == "critique"
    statement = m.Assertion.objects.get(text="本作品批评这一概念的适用条件")
    statement.status = "withdrawn"; statement.save(update_fields=["status"])
    assert not active_catalog_snapshot(edition)["knowledge"]["nodes"]
    assert not KnowledgeNodeDetailSerializer(node).data["work_groups"]
