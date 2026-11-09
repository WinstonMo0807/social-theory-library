"""Enrich already-authorized retrieval rows without inventing raw offsets."""
from catalog.models import EvidenceAnchor, KnowledgeLegacyMapping
from catalog.services.knowledge_sources import locator_payload


def attach_locators(rows):
    span_ids = [row["evidence_span_id"] for row in rows if row.get("evidence_span_id")]
    mapping = {str(row.source_id): row.target_id for row in KnowledgeLegacyMapping.objects.filter(
        source_type="evidence_span", source_id__in=span_ids, target_type="anchor", quality="verified_text")}
    anchors = {a.pk: a for a in EvidenceAnchor.objects.filter(pk__in=mapping.values()).select_related("document_revision__asset__edition")}
    for row in rows:
        row["source_type"] = "original_text" if row.get("asset_id") else "knowledge_object"
        anchor = anchors.get(mapping.get(str(row.get("evidence_span_id"))))
        if anchor and str(anchor.document_revision_id) == str(row.get("document_revision_id")):
            row["locator"] = locator_payload(anchor)
            row["anchor_id"] = str(anchor.pk)
            row["node_id"] = row["locator"]["node_id"]
            row["reader_url"] = row["locator"]["reader_url"]
            row["coverage"] = "verified_source_range"
        else:
            row["anchor_id"] = None
            row["node_id"] = None
            row["coverage"] = "legacy_locator_pending"
    return rows
