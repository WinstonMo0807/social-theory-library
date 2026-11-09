"""Repeatable source-preserving migration of confirmed editorial records."""
import json
from uuid import uuid5
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
from catalog import models as m
from .knowledge_core import entity_for_legacy
from .knowledge_sources import migrate_span


def record_snapshot(row):
    values = {f.attname: getattr(row, f.attname) for f in row._meta.concrete_fields}
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def historical_revisions(kind, key):
    return {"canonical": [record_snapshot(r) for r in m.DomainChangeEvent.objects.filter(
        object_type=kind, object_id=key).order_by("canonical_revision")],
        "editorial": [record_snapshot(r) for r in m.EditorialRevision.objects.filter(
            target_type=kind, target_id=key).order_by("revision")]}


@transaction.atomic
def migrate_curated_claim(claim):
    """Preserve human decisions separately from the recoverability of evidence.

    v2 enriches earlier incomplete mappings without overwriting any subsequent
    Assertion edit. Old rows, evidence links and review history remain intact.
    """
    claim = m.CuratedClaim.objects.select_for_update().select_related("adopted_from", "scholar__person").get(pk=claim.pk)
    mapping = m.KnowledgeLegacyMapping.objects.filter(source_type="catalog.curatedclaim",source_id=claim.pk,target_type="assertion").first()
    if mapping and mapping.provenance.get("migration_version") == 2:
        return mapping
    derived = claim.adopted_from
    origin = {"legacy_type":"catalog.curatedclaim", "legacy_id":str(claim.pk),
        "record":record_snapshot(claim), "history":historical_revisions("curated_claim",claim.pk),
        "human_confirmation_preserved":True, "source_quality_independent_of_human_decision":True,
        "adopted_record":record_snapshot(derived) if derived else None}
    if derived:
        origin["decisions"] = [record_snapshot(r) for r in m.IntelligenceFeedback.objects.filter(
            candidate_type="derived_claim_curation",candidate_id=str(derived.pk)).order_by("created_at")]
    statement, created = m.Assertion.objects.get_or_create(pk=mapping.target_id if mapping else uuid5(claim.pk,"assertion-v1"),defaults={
        "text":claim.proposition,"category":claim.kind,"conditions":{"legacy_qualifiers":claim.qualifiers},
        "expression":"editorial_judgment", "status":claim.status,"source_quality":"legacy_source_gap",
        "created_by":claim.created_by,"origin":origin})
    if not created:
        statement.origin={**statement.origin, "migration_v2":origin}
        statement.save(update_fields=["origin","updated_at"])
    for target in (claim.node, claim.topic, claim.scholar.person if claim.scholar_id else None):
        if target:
            m.AssertionParticipant.objects.get_or_create(assertion=statement,role="context",entity=entity_for_legacy(target))
    if claim.work_id:
        m.AssertionParticipant.objects.get_or_create(assertion=statement,role="context",work_id=claim.work_id)
    gaps, verified, revisions = [], 0, set()
    # Preserve every explicitly linked evidence role. Adoption's primary span
    # is supplemental only when the historical curated link was absent.
    links=list(claim.evidence_links.select_related("evidence_span__document_revision__asset__edition").order_by("sort_order","id"))
    evidence_rows=[(link.evidence_span,link.role,record_snapshot(link)) for link in links]
    if derived and not any(span.pk == derived.primary_evidence_id for span,_,_ in evidence_rows):
        evidence_rows.append((derived.primary_evidence,"primary",{"adopted_from":str(derived.pk)}))
    for span, role, record in evidence_rows:
        revision=span.document_revision
        revisions.add(revision.pk)
        m.AssertionSource.objects.get_or_create(assertion=statement,document_revision=revision,
            defaults={"work":revision.asset.edition.work,"edition":revision.asset.edition,
                "expression":"editorial_judgment","provenance":{"legacy_claim_id":str(claim.pk),"attribution_status":"not_reconstructed"}})
        anchor=migrate_span(span)
        if anchor.target_id:
            stance=role if role in {"supports","opposes","qualifies"} else "context"
            m.AssertionEvidence.objects.get_or_create(assertion=statement,anchor_id=anchor.target_id,stance=stance,
                defaults={"note":f"历史证据角色：{role}；primary/attribution仅保留语境，不推断支持立场。"})
            verified+=1
        else:
            gaps.append({"record":record,"span_id":str(span.pk),"quality":anchor.quality,"provenance":anchor.provenance})
    if not revisions and claim.work_id:
        m.AssertionSource.objects.get_or_create(assertion=statement,work_id=claim.work_id,document_revision=None,
            defaults={"expression":"editorial_judgment","provenance":{"revision_gap":True,"legacy_claim_id":str(claim.pk)}})
    statement.source_quality="verified_legacy_text" if verified and not gaps else "legacy_partial_evidence" if verified else "legacy_source_gap"
    statement.origin={**statement.origin,"evidence_migration":{"version":2,"verified":verified,"gaps":gaps}}
    statement.save(update_fields=["source_quality","origin","updated_at"])
    mapping,_=m.KnowledgeLegacyMapping.objects.update_or_create(source_type="catalog.curatedclaim",source_id=claim.pk,target_type="assertion",
        defaults={"target_id":statement.pk,"quality":"manual_status_preserved","provenance":{"migration_version":2,
            "source_quality_independent_of_human_decision":True,"verified_evidence":verified,"evidence_gaps":len(gaps)}})
    return mapping


@transaction.atomic
def migrate_relation(row):
    """Do not infer missing editions, fine-grained predicates or claimants."""
    label = row._meta.label_lower
    mapping = m.KnowledgeLegacyMapping.objects.filter(source_type=label, source_id=row.pk, target_type="assertion").first()
    if mapping and mapping.provenance.get("migration_version") == 2:
        return mapping
    if row.status not in {"confirmed", "approved", "published"}:
        raise ValueError("Only confirmed historical records enter canonical knowledge")
    predicate = getattr(row, "relation_type", getattr(row, "role", ""))
    text = getattr(row, "relation_label", getattr(row, "description", ""))
    if isinstance(row, m.PersonNodeRelation):
        person, node = entity_for_legacy(row.person), entity_for_legacy(row.node)
        participants = [("subject", {"entity": node if row.node_is_source else person}),
                        ("object", {"entity": person if row.node_is_source else node})]
        text = text or f"{person.label} — {row.get_relation_type_display()} — {node.label}"
    elif isinstance(row, m.WorkNodeRelation):
        node = entity_for_legacy(row.node)
        participants = [("subject", {"work": row.work}), ("object", {"entity": node})]
        text = text or f"{row.work.title} — {row.get_role_display()} — {node.label}"
    else:
        source, target = entity_for_legacy(row.source_node), entity_for_legacy(row.target_node)
        participants = [("subject", {"entity": source}), ("object", {"entity": target})]
        text = text or f"{source.label} — {row.get_relation_type_display()} — {target.label}"
    origin = {"legacy_type": label, "legacy_id": str(row.pk), "record": record_snapshot(row),
              "human_confirmation_preserved": True, "finer_semantics_not_reconstructed": True}
    origin["history"] = historical_revisions({"catalog.knowledgerelation":"knowledge_relation",
        "catalog.personnoderelation":"person_node_relation", "catalog.worknoderelation":"work_node_relation"}[label],row.pk)
    snippets = list(row.evidence.all()) if hasattr(row,"evidence") else []
    origin["legacy_evidence_snippets"] = [record_snapshot(v) for v in snippets]
    origin["snippet_revision_gap"] = bool(snippets)
    if isinstance(row, m.KnowledgeRelation):
        origin["versions"] = [record_snapshot(v) for v in row.versions.order_by("version_number")]
    statement, created = m.Assertion.objects.get_or_create(id=mapping.target_id if mapping else uuid5(row.pk,"assertion-v1"),defaults={
        "text":text,"predicate":predicate,"category":"relation","direction":getattr(row,"direction","directed"),
        "expression":"editorial_judgment","status":row.status,"source_quality":"legacy_source_gap",
        "created_by_id":getattr(row,"created_by_id",None),"origin":origin})
    if not created:
        statement.origin={**statement.origin,"migration_v2":origin}
        statement.save(update_fields=["origin","updated_at"])
    for role, reference in participants:
        m.AssertionParticipant.objects.get_or_create(assertion=statement, role=role, **reference)
    revision = getattr(row, "source_document_revision", None)
    work = revision.asset.edition.work if revision else getattr(row, "work", None)
    if work:
        m.AssertionSource.objects.get_or_create(assertion=statement,work=work,document_revision=revision,
            defaults={"edition":revision.asset.edition if revision else None,"expression":"editorial_judgment",
                "provenance":{"legacy_type":label,"legacy_id":str(row.pk),
                    "source_text":getattr(row,"source",getattr(row,"evidence_source","")),"revision_gap":revision is None}})
    for snippet in snippets:
        m.AssertionSource.objects.get_or_create(assertion=statement,work=snippet.work,edition=snippet.file.edition,document_revision=None,
            defaults={"expression":"editorial_judgment","provenance":{"legacy_snippet_id":str(snippet.pk),"revision_gap":True}})
        m.KnowledgeLegacyMapping.objects.get_or_create(source_type="catalog.evidencesnippet",source_id=snippet.pk,target_type="anchor",
            defaults={"quality":"historical_revision_missing","provenance":{"record":record_snapshot(snippet),"historical_locator_preserved":True}})
    span = getattr(row, "evidence_span", None)
    if span:
        evidence = migrate_span(span)
        if evidence.target_id:
            m.AssertionEvidence.objects.get_or_create(assertion=statement, anchor_id=evidence.target_id, stance="context",
                defaults={"note":"历史关系证据；原记录未细分支持或反对，不推断立场。"})
            statement.source_quality = "verified_legacy_text"
            statement.save(update_fields=["source_quality", "updated_at"])
    return m.KnowledgeLegacyMapping.objects.update_or_create(source_type=label,source_id=row.pk,target_type="assertion",
        defaults={"target_id":statement.pk,"quality":"manual_status_preserved",
            "provenance":{"migration_version":2,"source_quality":statement.source_quality}})[0]
