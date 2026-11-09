"""Historical decisions survive independently of evidence repairability."""
import pytest
from catalog import models as m
from catalog.services.knowledge_core import entity_for_legacy
from catalog.services.knowledge_migration import migrate_curated_claim, migrate_relation
from catalog.services.knowledge_sources import snapshot_revision, digest
from tests.test_knowledge_core import source

pytestmark = pytest.mark.django_db


def test_curated_history_roles_gaps_and_idempotent_upgrade(source, admin_user):
    snapshot_revision(source)
    page=source.asset.pages.get(index=1)
    valid=m.EvidenceSpan.objects.create(document_revision=source,page=page,page_number=1,
        start_offset=4,end_offset=7,original_text=page.text[4:7],content_hash=digest(page.text[4:7]))
    gap=m.EvidenceSpan.objects.create(document_revision=source,page=page,page_number=1,
        start_offset=0,end_offset=4,original_text="并非当前范围",content_hash=digest("并非当前范围"))
    claim=m.CuratedClaim.objects.create(work=source.asset.edition.work,kind="core_viewpoint",
        proposition="人工保留的命题",qualifiers=["特定时期"],status="published",created_by=admin_user,published_by=admin_user)
    m.ClaimEvidence.objects.create(curated_claim=claim,evidence_span=valid,role="opposes")
    m.ClaimEvidence.objects.create(curated_claim=claim,evidence_span=gap,role="primary")
    mapping=migrate_curated_claim(claim)
    statement=m.Assertion.objects.get(pk=mapping.target_id)
    assert statement.status=="published" and statement.source_quality=="legacy_partial_evidence"
    assert statement.evidence.get().stance=="opposes"
    assert statement.sources.get().document_revision_id==source.pk
    assert statement.origin["record"]["published_by_id"]==admin_user.pk
    assert len(statement.origin["evidence_migration"]["gaps"])==1
    # A v1 migration can be enriched without replacing later editorial text.
    mapping.provenance={};mapping.save()
    statement.text="后来的人工作品解释";statement.save()
    migrate_curated_claim(claim);migrate_curated_claim(claim)
    statement.refresh_from_db()
    assert statement.text=="后来的人工作品解释" and statement.evidence.count()==1
    claim.refresh_from_db()
    assert claim.proposition=="人工保留的命题" and claim.evidence_links.count()==2


def test_concept_reviewed_mapping_and_unmapped_same_name_remain_separate():
    concept=m.Concept.objects.create(name="实践",slug="practice-legacy",definition="旧概念解释")
    node=m.KnowledgeNode.objects.create(node_type="concept",canonical_name_zh="实践",slug="practice-node",status="published")
    first=entity_for_legacy(concept)
    other=entity_for_legacy(node)
    assert first.pk!=other.pk and first.concept_id==concept.pk
    mapped=m.Concept.objects.create(name="场域",slug="field-legacy")
    target=m.KnowledgeNode.objects.create(node_type="concept",canonical_name_zh="场域",slug="field-node",status="published")
    m.LegacyKnowledgeMapping.objects.create(legacy_model="Concept",legacy_id=mapped.pk,node=target,migration_status="mapped")
    assert entity_for_legacy(mapped).pk==entity_for_legacy(target).pk


def test_relation_retains_old_snippet_without_inventing_revision(source,admin_user):
    node=m.KnowledgeNode.objects.create(node_type="concept",canonical_name_zh="概念",slug="history-node",status="published")
    relation=m.WorkNodeRelation.objects.create(work=source.asset.edition.work,node=node,role="critique",status="published",reviewed_by=admin_user)
    snippet=m.EvidenceSnippet.objects.create(work=source.asset.edition.work,file=source.asset,node=node,
        work_node_relation=relation,page_number=1,quote="旧摘录没有正文修订",extraction_method="manual")
    mapping=migrate_relation(relation);migrate_relation(relation)
    statement=m.Assertion.objects.get(pk=mapping.target_id)
    assert statement.origin["record"]["reviewed_by_id"]==admin_user.pk
    assert statement.origin["legacy_evidence_snippets"][0]["quote"]==snippet.quote
    assert not statement.evidence.exists()
    assert m.KnowledgeLegacyMapping.objects.get(source_id=snippet.pk).target_id is None
