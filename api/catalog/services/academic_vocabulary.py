"""Shared display vocabulary; provenance codes are never bibliographic evidence."""
from catalog import models as m

PREDICATES = {**dict(m.WorkNodeRelation.Role.choices), **dict(m.KnowledgeRelation.RelationType.choices),
    **dict(m.PersonNodeRelation.RelationType.choices),
    "uses": "使用", "criticizes": "批评", "inherits": "继承", "develops": "发展", "cites": "引用",
    "responds_to": "回应", "mentions": "提及", "proposes": "提出", "defines": "定义", "interprets": "解释",
    "explains": "阐释", "influences": "影响", "teaching": "师承", "cooperation": "合作",
    "influence": "影响", "criticism": "批评", "comparative_reading": "比较阅读", "other": "其他关系"}

PROVENANCE_CODES = {"workflow_section_confirmation", "workflow_legacy_identity_adapter", "field_assistant",
    "field_assistant_inline", "manual_cataloging", "editorial", "theory_review_new_node", "field_enrichment"}


def legacy_citation(value):
    value = str(value or "").strip()
    return "" if value in PROVENANCE_CODES or value.startswith("field_enrichment:") else value
