"""Repeatable source-preserving migration of confirmed editorial records."""
import json
from uuid import uuid5
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
from catalog import models as m
from .knowledge_core import entity_for_legacy
from .knowledge_sources import migrate_span
from .academic_vocabulary import legacy_citation


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
    if mapping and mapping.provenance.get("migration_version") == 4:
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
    elif isinstance(row, m.ScholarRelation):
        source, target = entity_for_legacy(row.source_scholar.person), entity_for_legacy(row.target_scholar.person)
        participants = [("subject", {"entity": source}), ("object", {"entity": target})]
        text = row.summary or f"{source.label} — {predicate} — {target.label}"
        # Published rows are materialized from this immutable revision. A newer
        # unpublished revision remains a separate historical draft.
        if (not row.active_revision_id or row.active_revision.status != "published"
            or row.active_revision.target_type != "scholar_relation" or row.active_revision.target_id != row.pk
            or any(str(row.active_revision.materialized_preview.get(f"{side}_scholar")) != str(getattr(row, f"{side}_scholar_id")) for side in ("source", "target"))):
            raise ValueError("Scholar relation lacks a published source revision")
    else:
        source, target = entity_for_legacy(row.source_node), entity_for_legacy(row.target_node)
        participants = [("subject", {"entity": source}), ("object", {"entity": target})]
        text = text or f"{source.label} — {row.get_relation_type_display()} — {target.label}"
    origin = {"legacy_type": label, "legacy_id": str(row.pk), "record": record_snapshot(row),
              "human_confirmation_preserved": True, "finer_semantics_not_reconstructed": True}
    origin["history"] = historical_revisions({"catalog.knowledgerelation":"knowledge_relation",
        "catalog.personnoderelation":"person_node_relation", "catalog.worknoderelation":"work_node_relation",
        "catalog.scholarrelation":"scholar_relation"}[label],row.pk)
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
    if isinstance(row, m.ScholarRelation) and span and (span.document_revision_id != row.source_document_revision_id
        or row.active_revision.materialized_preview.get("source_anchor") != {"span_id": str(span.pk), "document_revision_id": str(span.document_revision_id)}):
        statement.origin = {**statement.origin, "historical_anchor_mismatch": True}
        statement.save(update_fields=["origin", "updated_at"])
        span = None
    if span:
        evidence = migrate_span(span)
        if evidence.target_id:
            m.AssertionEvidence.objects.get_or_create(assertion=statement, anchor_id=evidence.target_id, stance="context",
                defaults={"note":"历史关系证据；原记录未细分支持或反对，不推断立场。"})
            statement.source_quality = "verified_legacy_text"
            statement.save(update_fields=["source_quality", "updated_at"])
    raw_source = str(getattr(row, "source", getattr(row, "evidence_source", "")) or "").strip()
    citation = legacy_citation(raw_source)
    if raw_source and not citation:
        # Repair only the exact v3 import. Preserve genuine citations and the
        # original source code in origin/provenance, including manual edits.
        statement.sources.filter(citation=raw_source).update(citation="")
    if citation:
        if statement.sources.exists():
            statement.sources.filter(citation="").update(citation=citation)
        else:
            m.AssertionSource.objects.create(assertion=statement, expression="editorial_judgment", citation=citation,
                provenance={"legacy_type": label, "legacy_id": str(row.pk), "revision_gap": True})
    return m.KnowledgeLegacyMapping.objects.update_or_create(source_type=label,source_id=row.pk,target_type="assertion",
        defaults={"target_id":statement.pk,"quality":"manual_status_preserved",
            "provenance":{"migration_version":4,"source_quality":statement.source_quality}})[0]


@transaction.atomic
def migrate_assertion_page(statement):
    """Materialize already confirmed history, without inventing a new review.

    The source row and all earlier revisions remain available. A conflicting
    live editorial draft is deferred rather than overwritten by backfill.
    """
    from django.db.models import Max
    from rest_framework.exceptions import ValidationError
    from catalog.services.academic_relations import assertion_page
    from catalog.services.knowledge_core import normalize_page_blocks
    from catalog.services.knowledge_workspace import sync_dependencies
    mapping = m.KnowledgeLegacyMapping.objects.filter(source_type="catalog.assertion", source_id=statement.pk,
        target_type="knowledge_block").first()
    if mapping:
        return mapping
    if not statement.origin.get("human_confirmation_preserved"):
        raise ValidationError("只有有原人工确认记录的陈述可进入历史页迁移。")
    page = assertion_page(statement)
    page = m.KnowledgePage.objects.select_for_update().get(pk=page.pk)
    revisions = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk)
    if revisions.filter(status="draft").exists():
        raise ValidationError("知识页有未发布编辑稿，历史回填已暂缓，原内容保持。")
    block_id = uuid5(statement.pk, "legacy-assertion-block")
    block = {"id": str(block_id), "type": "analysis", "text": statement.text,
        "origin": "legacy_human", "human_edited": True,
        "references": [{"type": "assertion", "id": str(statement.pk)}]}
    blocks = normalize_page_blocks([*page.body_blocks, block], retained=page.body_blocks)
    number = (revisions.aggregate(value=Max("revision"))["value"] or 0) + 1
    status = "published" if statement.status == "published" else "draft"
    snapshot = {"title": page.title, "scope": page.scope, "body_blocks": blocks, "status": status}
    record = statement.origin.get("record", {})
    revision = m.EditorialRevision.objects.create(target_type="knowledge_page", target_id=page.pk,
        base_revision=number-1, revision=number, patch={"body_blocks": blocks}, materialized_preview=snapshot,
        changed_fields=["body_blocks"], status=status, idempotency_key=f"legacy-assertion-page:{statement.pk}",
        created_by=statement.created_by, published_by_id=record.get("reviewed_by_id") if status == "published" else None,
        published_at=record.get("reviewed_at") if status == "published" else None,
        change_note="迁移原人工确认陈述；原审核时间与定位缺口分别保留，不作为新审核")
    if status == "published":
        page.body_blocks, page.status = blocks, "published"
        page.save(update_fields=["body_blocks", "status", "updated_at"])
    sync_dependencies(page, blocks)
    return m.KnowledgeLegacyMapping.objects.create(source_type="catalog.assertion", source_id=statement.pk,
        target_type="knowledge_block", target_id=block_id, quality="human_history_preserved",
        provenance={"page_id": str(page.pk), "editorial_revision_id": str(revision.pk), "origin": statement.origin.get("legacy_type")})
