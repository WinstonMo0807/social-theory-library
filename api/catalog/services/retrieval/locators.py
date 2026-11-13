"""Enrich already-authorized retrieval rows without inventing raw offsets."""
from django.db.models import Prefetch
from catalog.models import DocumentNode, EvidenceAnchor, EvidenceSegment, KnowledgeLegacyMapping
from catalog.services.knowledge_sources import locator_payload


def current_source_locators(rows, access_statuses):
    """Re-read anchors for RAG consumers; never trust a stored/client locator.

    Historical reading uses knowledge_sources.locator. New answer evidence must
    still belong to the current published source, including every segment.
    """
    from uuid import UUID
    from catalog.services.publication_eligibility import active_document_revision_q, current_retrieval_source_q
    ids = set()
    for row in rows:
        try:
            ids.add(UUID(str(row.get("anchor_id"))))
        except (ValueError, TypeError):
            continue
    anchors = list(EvidenceAnchor.objects.filter(pk__in=ids).filter(
        active_document_revision_q(revision_prefix="document_revision"),
        current_retrieval_source_q(asset_prefix="document_revision__asset", access_statuses=access_statuses),
    ).select_related("document_revision__asset__edition__work").prefetch_related(
        Prefetch("segments", queryset=EvidenceSegment.objects.select_related("page", "node"), to_attr="locator_segments")))
    _prime_paths(anchors)
    return {str(anchor.pk): locator_payload(anchor) for anchor in anchors}


def _prime_paths(anchors):
    """Fetch shared chapter ancestry once per level, not once per evidence row."""
    nodes = {s.node_id: s.node for a in anchors for s in a.locator_segments if s.node_id}
    missing = {n.parent_id for n in nodes.values() if n.parent_id and n.parent_id not in nodes}
    while missing:
        parents = list(DocumentNode.objects.filter(pk__in=missing).only("id", "title", "parent_id"))
        nodes.update((n.pk, n) for n in parents)
        missing = {n.parent_id for n in parents if n.parent_id and n.parent_id not in nodes}
    for node in nodes.values():
        node.parent = nodes.get(node.parent_id)
    for anchor in anchors:
        for segment in anchor.locator_segments:
            if segment.node_id:
                segment.node = nodes[segment.node_id]


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
        anchor = create_anchor(revision, [{"page_number":page.page_number,"start":start,"end":end,"exact":document.text,
            "node_id":document.payload.get("node_id")}])
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
    anchors = {a.pk: a for a in EvidenceAnchor.objects.filter(pk__in=[*mapping.values(), *documents.values()])
        .select_related("document_revision__asset__edition")
        .prefetch_related(Prefetch("segments", queryset=EvidenceSegment.objects.select_related("page", "node"), to_attr="locator_segments"))}
    _prime_paths(anchors.values())
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
