"""Public source adapters shared by indexing and current-permission checks.

Never read drafts or private editorial_note. Source text remains unmodified;
token children are disposable projections over the exact captured revision.
"""
from catalog.services.contribution_scope import whole_edition_contribution
from hashlib import sha256
import json
from itertools import islice
from uuid import UUID
from urllib.parse import urlencode

from django.db.models import F, Q
from django.urls import reverse
from catalog.models import (Asset, Concept, Discipline, Edition, EvidenceCuration,
    EvidenceSpan, KnowledgeNode, ReadingPath, RecommendationIssue, ScholarProfile,
    Subdiscipline, TheoryTimelineEvent, Topic)
from catalog.services.publication_eligibility import current_retrieval_source_q, public_editions
from catalog.services.scoped_search import public_scholar_queryset


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def text_values(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(text_values(item) for item in value if isinstance(item, (str, list)))
    return ""


def source_queryset(kind, access_statuses=None):
    if kind == "edition":
        rows = public_editions(require_fulltext=True).filter(
            active_catalog_revision__reader_asset__kind="normalized",
            active_catalog_revision__reader_asset__status="ready",
            active_catalog_revision__reader_asset__validation_status="valid",
            active_catalog_revision__reader_asset__edition_id=F("pk"),
            active_catalog_revision__document_revision__asset_id=F("active_catalog_revision__reader_asset_id"))
        return rows.filter(current_retrieval_source_q(asset_prefix="active_catalog_revision__reader_asset", access_statuses=access_statuses))
    if kind == "scholar":
        return public_scholar_queryset()
    if kind == "node":
        return KnowledgeNode.objects.filter(status="published").prefetch_related("aliases")
    if kind in {"topic", "discipline", "subdiscipline", "concept"}:
        model = {"topic": Topic, "discipline": Discipline, "subdiscipline": Subdiscipline, "concept": Concept}[kind]
        rows = model.objects.filter(editorial_status="published")
        if kind == "subdiscipline":
            rows = rows.filter(discipline__editorial_status="published").select_related("discipline")
        return rows
    if kind == "reading_path":
        return ReadingPath.objects.filter(status="published").prefetch_related("stages", "items")
    if kind == "recommendation_issue":
        from catalog.services.editorial_issues import published_issues
        return published_issues()
    if kind == "evidence_curation":
        return EvidenceCuration.objects.filter(active_revision__status="published").select_related("active_revision")
    if kind == "timeline":
        return TheoryTimelineEvent.objects.filter(review_status="approved")
    raise ValueError("未知检索资料类型。")


SOURCE_TYPES = ("edition", "scholar", "node", "topic", "discipline", "subdiscipline", "concept",
                "reading_path", "recommendation_issue", "evidence_curation", "timeline")


def scope_token(kind, row):
    if kind == "edition":
        asset = row.active_catalog_revision.reader_asset
        return f"edition:{row.pk}:{row.active_catalog_revision_id}:{asset.access_status}"
    return f"{kind}:{row.pk}"


def _taxonomy_for(rows):
    """One permission lookup per taxonomy and batch, never four per book."""
    allowed = {}
    for section, field, model, status in (
        ("classification", "disciplines", Discipline, "editorial_status"),
        ("classification", "subdisciplines", Subdiscipline, "editorial_status"),
        ("knowledge", "topics", Topic, "editorial_status"),
        ("knowledge", "nodes", KnowledgeNode, "status"),
    ):
        ids = set()
        for row in rows:
            snapshot = row.active_catalog_revision.snapshot or {}
            for value in (snapshot.get(section) or {}).get(field, []):
                try:
                    ids.add(UUID(str(value.get("id"))))
                except (AttributeError, TypeError, ValueError):
                    continue
        allowed[(section, field)] = set(map(str, model.objects.filter(
            pk__in=ids, **{status: "published"}).values_list("pk", flat=True))) if ids else set()
    return allowed


def iter_source_headers(kind, access_statuses=None, *, queryset=None):
    rows = iter((queryset if queryset is not None else source_queryset(kind, access_statuses)).iterator(chunk_size=100))
    while batch := list(islice(rows, 100)):
        taxonomy = _taxonomy_for(batch) if kind == "edition" else None
        for row in batch:
            header = source_header(kind, row, taxonomy=taxonomy)
            if header:
                yield row, header


def edition_revision(revision_id, document_id, text_checksum, access_status):
    return fingerprint({"revision": str(revision_id), "document": str(document_id),
                        "text_checksum": text_checksum, "access": access_status})


def edition_scope_records(access_statuses):
    """Lightweight current identities for unfiltered polling/recall."""
    values = source_queryset("edition", access_statuses).values_list("pk", "active_catalog_revision_id",
        "active_catalog_revision__document_revision_id", "active_catalog_revision__document_revision__text_checksum",
        "active_catalog_revision__reader_asset__access_status")
    for key, revision, document, checksum, access in values.iterator(chunk_size=200):
        version = edition_revision(revision, document, checksum, access)
        yield str(key), version, f"edition:{key}:{version}"


def edition_metadata_header(row, *, taxonomy=None):
    """Published facets also describe records whose text is not yet eligible."""
    rev = row.active_catalog_revision
    asset = rev.reader_asset
    snapshot = dict(rev.snapshot or {})
    taxonomy = _taxonomy_for([row]) if taxonomy is None else taxonomy
    for (section, field), allowed in taxonomy.items():
        values = snapshot.get(section) or {}
        snapshot[section] = {**values, field: [item for item in values.get(field, [])
            if isinstance(item, dict) and str(item.get("id")) in allowed]}
    from catalog.services.academic_projection import published_knowledge_nodes
    knowledge = snapshot.get("knowledge") or {}
    snapshot["knowledge"] = {**knowledge, "nodes": published_knowledge_nodes(row.work_id, knowledge.get("nodes") or [])}
    work = snapshot.get("work") or {}
    edition = snapshot.get("edition") or {}
    readable = bool(asset and asset.kind == "normalized" and asset.status == "ready"
        and asset.validation_status == "valid" and asset.file and asset.edition_id == row.pk
        and str((snapshot.get("document") or {}).get("asset_id")) == str(asset.pk))
    translated = bool(work.get("translation_of_id") or any(item.get("role") == "translator"
        and whole_edition_contribution(item) for item in snapshot.get("contributions", [])))
    public_slug = str(edition.get("public_slug") or row.pk)
    cover = work.get("cover_media") or {}
    cover_url = reverse("public-work-cover", kwargs={"work_id": row.work_id}) if work.get("cover") or cover else ""
    if cover_url:
        cover_params = {"edition_id": str(row.pk)}
        if cover.get("primary_rendition_id"):
            cover_params["rendition"] = cover["primary_rendition_id"]
        cover_url += "?" + urlencode(cover_params)
    return dict(channel="passages", title=work.get("title", ""), source_kind="passage",
        edition_id=str(row.pk), work_id=str(row.work_id), asset_id=str(asset.pk) if asset else None,
        access_status=asset.access_status if asset else "public", url=f"/works/{public_slug}",
        publication_year=edition.get("publication_year"), document_type=work.get("document_type", "book"),
        reader_available=readable, pdf_available=readable and asset.mime_type.lower().split(";")[0] == "application/pdf",
        translation_of_id=str(work.get("translation_of_id") or ""),
        chinese_translation=translated and str(work.get("language") or "").lower().startswith("zh"),
        work={"id": str(row.work_id), "title": work.get("title", ""), "slug": public_slug},
        bibliography={"cover_url": cover_url, "cover_media": cover or None, "original_title": work.get("original_title", ""),
            "publication_year": edition.get("publication_year"), "publisher": edition.get("publisher", ""),
            "language": work.get("language", ""), "page_count": asset.page_count if asset and asset.page_count else None,
            "version_label": edition.get("version_label", ""), "document_type": work.get("document_type", "")},
        authors=[str(item.get("name") or (item.get("person") or {}).get("preferred_name") or "")
                 for item in snapshot.get("contributions", []) if item.get("role") == "author" and whole_edition_contribution(item)],
        author_ids=[str(item.get("person_id") or (item.get("person") or {}).get("id") or "")
                    for item in snapshot.get("contributions", []) if item.get("role") == "author" and whole_edition_contribution(item)],
        language=work.get("language", ""), topics=snapshot.get("knowledge", {}).get("topics", []),
        theories=snapshot.get("knowledge", {}).get("nodes", []))


def iter_edition_metadata_headers(queryset):
    rows = iter(queryset.iterator(chunk_size=100))
    while batch := list(islice(rows, 100)):
        taxonomy = _taxonomy_for(batch)
        for row in batch:
            yield row, edition_metadata_header(row, taxonomy=taxonomy)


def source_header(kind, row, *, taxonomy=None):
    """A hash of published input, never an unbounded full-document read."""
    payload = {"source_type": kind, "source_id": str(row.pk), "scope_token": scope_token(kind, row)}
    portrait_media = None
    if kind == "edition":
        rev = row.active_catalog_revision
        asset = rev.reader_asset
        payload.update(edition_metadata_header(row, taxonomy=taxonomy))
        payload.update(
            document_revision_id=str(rev.document_revision_id), catalog_revision_id=str(rev.pk),
            source_revision=edition_revision(rev.pk, rev.document_revision_id, rev.document_revision.text_checksum, asset.access_status))
        payload["scope_token"] = f"edition:{row.pk}:{payload['source_revision']}"
        return payload
    payload.update(channel="entities", access_status="public", aliases=[])
    if kind == "scholar":
        person = row.person
        from catalog.serializers import PersonCompactSerializer
        portrait_serializer = PersonCompactSerializer()
        portrait_media = portrait_serializer.get_portrait_media(person)
        aliases = [person.original_name, *person.aliases]
        payload.update(title=person.preferred_name, source_kind="scholar", url=f"/scholars/{row.slug}",
            text="\n".join(filter(None, [person.preferred_name, text_values(aliases), row.short_description,
                                       person.biography, text_values(row.key_concerns)])), aliases=list(filter(None, aliases)),
            portrait_url=portrait_serializer.get_portrait(person))
    elif kind == "node":
        aliases = [row.canonical_name_en, *[item.alias for item in row.aliases.all() if item.is_verified]]
        payload.update(title=row.canonical_name_zh, source_kind=row.node_type, url=f"/theories/nodes/{row.slug}", aliases=list(filter(None, aliases)),
            text="\n".join(filter(None, [row.canonical_name_zh, text_values(aliases), row.summary, row.definition,
                                       text_values(row.core_questions), text_values(row.basic_propositions), row.theoretical_boundary])))
    elif kind in {"topic", "discipline", "subdiscipline", "concept"}:
        url = f"/topics/{row.slug}" if kind == "topic" else f"/concepts/{row.slug}" if kind == "concept" else f"/theories/disciplines/{row.slug}"
        if kind == "subdiscipline":
            url = f"/theories/disciplines/{row.discipline.slug}?type=subdiscipline"
        payload.update(title=row.name, source_kind=kind, url=url, aliases=row.search_aliases,
            text="\n".join(filter(None, [row.name, text_values(row.search_aliases), row.description,
                *[text_values(getattr(row, field, "")) for field in ("introduction", "research_object", "definition", "problem_statement", "core_questions", "research_directions", "methods")]])))
    elif kind == "timeline":
        payload.update(title=row.title, source_kind="timeline", url=f"/theories/events/{row.pk}",
                       text="\n".join(filter(None, [row.title, row.description, row.date_label])))
    elif kind == "reading_path":
        # editorial_note is PRIVATE in 3.0.7. It is deliberately never read here.
        items = list(row.items.all())
        public_work_ids = set(str(key) for key in public_editions().filter(work_id__in=[item.work_id for item in items if item.work_id]).values_list("work_id", flat=True))
        public_nodes = set(str(key) for key in KnowledgeNode.objects.filter(pk__in=[item.node_id for item in items if item.node_id], status="published").values_list("pk", flat=True))
        reasons = [item.recommendation_reason for item in items
                   if (not item.work_id or str(item.work_id) in public_work_ids) and (not item.node_id or str(item.node_id) in public_nodes)]
        payload.update(channel="curation", title=row.title, source_kind="reading_path", url=f"/theories/reading-paths/{row.slug}",
            text="\n".join(filter(None, [row.title, row.introduction, row.learning_goal,
                  *[stage.description for stage in row.stages.all()], *reasons])),
            linked_work_ids=sorted(public_work_ids), source_label="阅读策划 · 已发布推荐理由")
    elif kind == "recommendation_issue":
        from catalog.services.editorial_issues import issue_payload, public_issue_revision
        data = issue_payload(row, public=True)
        texts = [data.get("title", ""), data.get("introduction", ""), data.get("summary", "")]
        for block in data.get("body_blocks", []):
            if isinstance(block, dict):
                texts.extend([block.get("text", ""), block.get("title", "")])
        for item in data.get("items", []):
            if item.get("status") != "unavailable":
                # note is the published per-item recommendation text, unlike
                # the private ReadingPathItem.editorial_note.
                texts.extend([item.get("title", ""), item.get("authors", ""), item.get("note", ""),
                              item.get("recommendation_reason", ""), item.get("reason", ""), item.get("description", "")])
        payload.update(channel="curation", title=data.get("title", ""), source_kind="recommendation_issue", url=f"/recommendations/{row.slug}",
                       text="\n".join(filter(None, texts)), published_revision_id=str(public_issue_revision(row).pk), source_label="书库推荐 · 编辑发布")
    elif kind == "evidence_curation":
        from catalog.services.shared_curation import curation_payload
        from django.http import Http404
        try:
            data = curation_payload(row.object_type, row.object_id, public=True)
        except Http404:
            return None
        parent_kind = {"scholar": "scholar", "topic": "topic", "node": "node"}.get(row.object_type)
        parent = source_queryset(parent_kind).filter(pk=row.object_id).first() if parent_kind else None
        if parent is None:
            return None
        header = source_header(parent_kind, parent)
        reasons = ["\n".join(filter(None, [item.get("group_title"), item.get("reason")])) for item in data.get("items", [])]
        payload.update(channel="curation", title=data.get("title", ""), source_kind="evidence_curation", url=header["url"] + "/passages",
                       text="\n".join(filter(None, reasons)), published_revision_id=str(row.active_revision_id), source_label="原文策展 · 编辑说明")
    # Portrait/display-only changes invalidate the rendered payload but do not
    # change input_hash. Index refresh can preserve existing model vectors.
    payload["source_revision"] = fingerprint(payload)
    # Updated/withdrawn source text must be excluded BEFORE either recall
    # channel. A source ID alone would let stale private text affect ranking.
    payload["scope_token"] = f"{kind}:{row.pk}:{payload['source_revision']}"
    if kind == "scholar":
        # Derived from the immutable rendition already identified by portrait_url.
        # Hydrate this display field without invalidating unchanged search vectors/scopes.
        payload["portrait_media"] = portrait_media
    return payload


def get_source(kind, key, access_statuses=None):
    row = source_queryset(kind, access_statuses).filter(pk=key).first()
    if row is None:
        return None, None
    return row, source_header(kind, row)


def source_units(kind, row, header, *, structure_id=None):
    from catalog.services.discovery_scope import unit_exclusions
    if kind != "edition":
        if header.get("text", "").strip():
            yield {"unit_id": str(row.pk), "text": header["text"], "metadata": {}}
        return
    revision = row.active_catalog_revision
    if structure_id:
        yield from logical_source_units(revision.document_revision, structure_id, header)
        return
    spans = EvidenceSpan.objects.filter(document_revision_id=revision.document_revision_id,
        page__asset_id=revision.reader_asset_id, page_number=F("page__index"),
        is_stale=False).select_related("page").prefetch_related("page__blocks").order_by("page_number", "start_offset", "id")
    if spans.exists():
        for span in spans.iterator(chunk_size=100):
            if not span.original_text.strip():
                continue
            is_ocr = (span.extraction_method.lower() in {"ocr", "hybrid"}
                or "ocr" in span.extraction_method.lower()
                or any((span.ocr_provenance or {}).get(key) for key in ("provider", "model", "version")))
            yield {"unit_id": str(span.pk), "text": span.original_text,
                "scope_exclusions": unit_exclusions(span.page, span.original_text, span.start_offset, span.end_offset), "metadata": {
                "evidence_span_id": str(span.pk), "passage_id": str(span.passage_id) if span.passage_id else None,
                "page_id": str(span.page_id), "unit_hash": fingerprint(span.original_text),
                "source_start_offset": span.start_offset,
                "pdf_page": span.page_number, "page_index": span.page_number, "printed_page": span.printed_page_label,
                "source_kind": "ocr" if is_ocr else "native",
                "language": span.language, "bbox": [], "locator_precision": "page",
                "reader_url": f"/reader/{revision.reader_asset_id}?page={span.page_number}" + (f"&passage={span.passage_id}" if span.passage_id else ""),
                "quality_flags": ["ocr_unverified"] if is_ocr else []}}
    else:
        # No inferred coordinates. A page-level source is still a real source.
        for page in revision.reader_asset.pages.exclude(text="").prefetch_related("blocks").order_by("index").iterator(chunk_size=50):
            yield {"unit_id": str(page.pk), "text": page.text, "scope_exclusions": unit_exclusions(page, page.text, 0, len(page.text)), "metadata": {
                "page_id": str(page.pk), "pdf_page": page.index, "page_index": page.index,
                "printed_page": page.printed_label, "unit_hash": fingerprint(page.text), "source_kind": "page_text", "locator_precision": "page", "bbox": [],
                "reader_url": f"/reader/{revision.reader_asset_id}?page={page.index}", "quality_flags": ["page_locator_only"]}}


def logical_source_units(revision, structure_id, header):
    """New writes use immutable raw node segments; the old adapter is read-only recovery."""
    from types import SimpleNamespace
    from catalog.models import DocumentNodeSegment, DocumentStructure
    from catalog.services.discovery_scope import unit_exclusions
    from catalog.services.knowledge_sources import digest
    structure = DocumentStructure.objects.get(pk=structure_id, document_revision=revision)
    nodes = {n.pk:n for n in structure.nodes.all()}
    segments = DocumentNodeSegment.objects.filter(node__structure=structure,
        node__kind__in=["paragraph","footnote","table","references","unresolved"], node__children__isnull=True
        ).select_related("page").order_by("node__order","order")
    for segment in segments.iterator(chunk_size=100):
        page, node = segment.page, nodes[segment.node_id]
        text = page.text[segment.start:segment.end]
        if digest(page.text) != page.content_hash or digest(text) != segment.content_hash:
            raise ValueError("修订原文或节点摘要不一致，停止索引并保留上一版本。")
        if not text.strip():
            continue
        path, parent = [], nodes.get(node.parent_id)
        while parent:
            if parent.kind != "document" and parent.title:
                path.insert(0,parent.title)
            parent = nodes.get(parent.parent_id)
        blocks = [SimpleNamespace(text=b.get("text",""),block_type=b.get("kind","")) for b in page.blocks]
        snapshot = SimpleNamespace(text=page.text,blocks=SimpleNamespace(all=lambda:blocks))
        exclusions = [(0,len(text),True)] if node.kind == "footnote" else unit_exclusions(snapshot,text,segment.start,segment.end)
        yield {"unit_id":str(segment.pk),"text":text,"scope_exclusions":exclusions,"metadata":{
            "projection_layout":"logical-node-v1","structure_id":str(structure.pk),
            "node_id":str(node.pk),"node_kind":node.kind,"node_segment_id":str(segment.pk),"snapshot_id":str(page.pk),
            "source_start_offset":segment.start,"unit_hash":fingerprint(text),"pdf_page":page.page_number,"page_index":page.page_number,
            "printed_page":page.printed_label,"chapter_path":path,"section_title":path[-1] if path else "",
            "source_kind":page.text_source,"language":header.get("language","unknown"),"bbox":[],"locator_precision":"text_range",
            "reader_url":f"/reader/{revision.asset_id}?revision={revision.pk}&page={page.page_number}",
            "quality_flags":["structure_pending"] if node.kind == "unresolved" else []}}


def visible_scope_tokens(channel, access_statuses):
    """Bounded identifiers, not corpus text, before either retrieval channel."""
    kinds = ("edition",) if channel == "passages" else ("reading_path", "recommendation_issue", "evidence_curation") if channel == "curation" else ("scholar", "node", "topic", "discipline", "subdiscipline", "concept", "timeline")
    tokens = []
    for kind in kinds:
        for row, header in iter_source_headers(kind, access_statuses):
            tokens.append(header["scope_token"])
            if len(tokens) > 20000:
                raise ValueError("当前可检索来源超过单次权限过滤上限，请缩小检索范围。")
    return tokens
