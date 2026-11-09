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


@transaction.atomic
def migrate_relation(row):
    """Do not infer missing editions, fine-grained predicates or claimants."""
    label = row._meta.label_lower
    mapping = m.KnowledgeLegacyMapping.objects.filter(source_type=label, source_id=row.pk, target_type="assertion").first()
    if mapping:
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
    if isinstance(row, m.KnowledgeRelation):
        origin["versions"] = [record_snapshot(v) for v in row.versions.order_by("version_number")]
    statement = m.Assertion.objects.create(id=uuid5(row.pk, "assertion-v1"), text=text,
        predicate=predicate, category="relation", direction=getattr(row, "direction", "directed"),
        expression="editorial_judgment", status=row.status, source_quality="legacy_source_gap",
        created_by_id=getattr(row, "created_by_id", None), origin=origin)
    for role, reference in participants:
        m.AssertionParticipant.objects.create(assertion=statement, role=role, **reference)
    revision = getattr(row, "source_document_revision", None)
    work = revision.asset.edition.work if revision else getattr(row, "work", None)
    if work:
        m.AssertionSource.objects.create(assertion=statement, work=work,
            edition=revision.asset.edition if revision else None, document_revision=revision,
            expression="editorial_judgment", provenance={"legacy_type": label, "legacy_id": str(row.pk),
                "source_text": getattr(row, "source", getattr(row, "evidence_source", "")), "revision_gap": revision is None})
    span = getattr(row, "evidence_span", None)
    if span:
        evidence = migrate_span(span)
        if evidence.target_id:
            m.AssertionEvidence.objects.create(assertion=statement, anchor_id=evidence.target_id, stance="context",
                note="历史关系证据；原记录未细分支持或反对，不推断立场。")
            statement.source_quality = "verified_legacy_text"
            statement.save(update_fields=["source_quality", "updated_at"])
    return m.KnowledgeLegacyMapping.objects.create(source_type=label, source_id=row.pk, target_type="assertion",
        target_id=statement.pk, quality="manual_status_preserved", provenance={"source_quality": statement.source_quality})
