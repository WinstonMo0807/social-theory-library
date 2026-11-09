"""Enrich already-authorized retrieval rows without inventing raw offsets."""
from catalog.models import EvidenceAnchor, KnowledgeLegacyMapping
from catalog.services.knowledge_sources import locator_payload


def index_anchor(document):
    """Index-time source mapping; search itself never writes canonical knowledge."""
    if document.channel != "passages" or not document.document_revision_id:
        return None
    from catalog.services.knowledge_sources import build_structure, create_anchor, digest
    from rest_framework.exceptions import ValidationError
    mapping = KnowledgeLegacyMapping.objects.filter(source_type="discovery_document", source_id=document.pk, target_type="anchor").first()
    if mapping and mapping.target_id:
        return mapping
    revision = document.document_revision
    try:
        if not revision.structures.exists():
            build_structure(revision)
        page = revision.page_snapshots.filter(page_number=document.payload.get("pdf_page")).first()
        base = int(document.payload.get("source_start_offset") or 0)
        start, end = base + document.start_offset, base + document.end_offset
        if not page or not 0 <= start < end <= len(page.text) or page.text[start:end] != document.text:
            raise ValidationError("检索片段与修订原文范围不一致。")
        anchor = create_anchor(revision, [{"page_number":page.page_number,"start":start,"end":end,"exact":document.text}])
        values = {"target_id":anchor.pk,"quality":"verified_text","provenance":{"document_revision_id":str(revision.pk),"content_hash":digest(document.text)}}
    except ValidationError as exc:
        values = {"target_id":None,"quality":"legacy_offsets_not_raw_text","provenance":{"document_revision_id":str(revision.pk),"reason":str(exc.detail)}}
    mapping, _ = KnowledgeLegacyMapping.objects.update_or_create(source_type="discovery_document", source_id=document.pk,
        target_type="anchor", defaults=values)
    return mapping


def attach_locators(rows):
    span_ids = [row["evidence_span_id"] for row in rows if row.get("evidence_span_id")]
    mapping = {str(row.source_id): row.target_id for row in KnowledgeLegacyMapping.objects.filter(
        source_type="evidence_span", source_id__in=span_ids, target_type="anchor", quality="verified_text")}
    documents = {str(row.source_id): row.target_id for row in KnowledgeLegacyMapping.objects.filter(
        source_type="discovery_document", source_id__in=[r["id"] for r in rows], target_type="anchor", quality="verified_text")}
    anchors = {a.pk: a for a in EvidenceAnchor.objects.filter(pk__in=[*mapping.values(), *documents.values()]).select_related("document_revision__asset__edition")}
    for row in rows:
        row["source_type"] = "original_text" if row.get("asset_id") else "knowledge_object"
        anchor = anchors.get(documents.get(str(row["id"])) or mapping.get(str(row.get("evidence_span_id"))))
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
