"""Public source adapters shared by indexing and current-permission checks.

Never read drafts or private editorial_note. Source text remains unmodified;
token children are disposable projections over the exact captured revision.
"""
from hashlib import sha256
import json
from itertools import islice
from uuid import UUID

from django.db.models import F, Q
from catalog.models import (Asset, Concept, Discipline, Edition, EvidenceCuration,
    EvidenceSpan, KnowledgeNode, ReadingPath, RecommendationIssue, ScholarProfile,
    Subdiscipline, TheoryTimelineEvent, Topic)
from catalog.services.publication_eligibility import public_editions
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
        return rows.filter(active_catalog_revision__reader_asset__access_status__in=access_statuses) if access_statuses is not None else rows
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


def source_header(kind, row, *, taxonomy=None):
    """A hash of published input, never an unbounded full-document read."""
    payload = {"source_type": kind, "source_id": str(row.pk), "scope_token": scope_token(kind, row)}
    if kind == "edition":
        rev = row.active_catalog_revision
        asset = rev.reader_asset
        snapshot = dict(rev.snapshot or {})
        taxonomy = _taxonomy_for([row]) if taxonomy is None else taxonomy
        for (section, field), allowed in taxonomy.items():
            values = snapshot.get(section) or {}
            snapshot[section] = {**values, field: [item for item in values.get(field, [])
                if isinstance(item, dict) and str(item.get("id")) in allowed]}
        work = snapshot.get("work") or {}
        edition = snapshot.get("edition") or {}
        payload.update(channel="passages", title=work.get("title", ""), source_kind="passage",
            edition_id=str(row.pk), work_id=str(row.work_id), asset_id=str(asset.pk),
            document_revision_id=str(rev.document_revision_id), catalog_revision_id=str(rev.pk),
            access_status=asset.access_status, url=f"/works/{row.public_slug}",
            publication_year=edition.get("publication_year"), document_type=work.get("document_type", "book"),
            work={"id": str(row.work_id), "title": work.get("title", ""), "slug": row.public_slug},
            authors=[str(item.get("name") or (item.get("person") or {}).get("preferred_name") or "")
                     for item in snapshot.get("contributions", []) if item.get("role") == "author"],
            author_ids=[str(item.get("person_id") or (item.get("person") or {}).get("id") or "")
                        for item in snapshot.get("contributions", []) if item.get("role") == "author"],
            language=work.get("language", ""),
            topics=snapshot.get("knowledge", {}).get("topics", []),
            theories=snapshot.get("knowledge", {}).get("nodes", []),
            source_revision=edition_revision(rev.pk, rev.document_revision_id, rev.document_revision.text_checksum, asset.access_status))
        payload["scope_token"] = f"edition:{row.pk}:{payload['source_revision']}"
        return payload
    payload.update(channel="entities", access_status="public", aliases=[])
    if kind == "scholar":
        person = row.person
        aliases = [person.original_name, *person.aliases]
        payload.update(title=person.preferred_name, source_kind="scholar", url=f"/scholars/{row.slug}",
            text="\n".join(filter(None, [person.preferred_name, text_values(aliases), row.short_description,
                                       person.biography, text_values(row.key_concerns)])), aliases=list(filter(None, aliases)),
            portrait_url=(f"/api/catalog/people/{person.pk}/portrait/?rendition={person.portrait_rendition_id}" if person.portrait_rendition_id else person.portrait.url if person.portrait else ""))
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
    return payload


def get_source(kind, key, access_statuses=None):
    row = source_queryset(kind, access_statuses).filter(pk=key).first()
    if row is None:
        return None, None
    return row, source_header(kind, row)


def source_units(kind, row, header):
    if kind != "edition":
        if header.get("text", "").strip():
            yield {"unit_id": str(row.pk), "text": header["text"], "metadata": {}}
        return
    revision = row.active_catalog_revision
    spans = EvidenceSpan.objects.filter(document_revision_id=revision.document_revision_id,
        page__asset_id=revision.reader_asset_id, page_number=F("page__index"),
        is_stale=False).select_related("page").order_by("page_number", "start_offset", "id")
    if spans.exists():
        for span in spans.iterator(chunk_size=100):
            if not span.original_text.strip():
                continue
            yield {"unit_id": str(span.pk), "text": span.original_text, "metadata": {
                "evidence_span_id": str(span.pk), "passage_id": str(span.passage_id) if span.passage_id else None,
                "page_id": str(span.page_id), "unit_hash": fingerprint(span.original_text),
                "source_start_offset": span.start_offset,
                "pdf_page": span.page_number, "page_index": span.page_number, "printed_page": span.printed_page_label,
                "source_kind": "ocr" if span.ocr_provenance or "ocr" in span.extraction_method.lower() else "native",
                "language": span.language, "bbox": [], "locator_precision": "page",
                "reader_url": f"/reader/{revision.reader_asset_id}?page={span.page_number}" + (f"&passage={span.passage_id}" if span.passage_id else ""),
                "quality_flags": ["ocr_unverified"] if span.ocr_provenance else []}}
    else:
        # No inferred coordinates. A page-level source is still a real source.
        for page in revision.reader_asset.pages.exclude(text="").order_by("index").iterator(chunk_size=50):
            yield {"unit_id": str(page.pk), "text": page.text, "metadata": {
                "page_id": str(page.pk), "pdf_page": page.index, "page_index": page.index,
                "printed_page": page.printed_label, "unit_hash": fingerprint(page.text), "source_kind": "page_text", "locator_precision": "page", "bbox": [],
                "reader_url": f"/reader/{revision.reader_asset_id}?page={page.index}", "quality_flags": ["page_locator_only"]}}


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
