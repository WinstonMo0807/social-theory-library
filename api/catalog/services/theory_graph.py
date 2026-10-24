"""Bounded public graph over existing, independently published identities.

Public counters contain no candidate rows, inferred links or copied catalog
records. An explicitly requested editorial overlay is independently authorized.
Truncation requires an additional eligible edge or node to be observed.
"""
from collections import Counter, defaultdict
from uuid import UUID

from django.db.models import BooleanField, CharField, Exists, F, Func, OuterRef, Q, Value, Window
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Replace, RowNumber, StrIndex
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from catalog.models import (
    Discipline, KnowledgeNode, KnowledgeNodeSubdiscipline, KnowledgeNodeTopic,
    KnowledgeRelation, Page, PersonNodeRelation, PersonSubdisciplineRelation,
    PersonTopicRelation, ScholarRelation, Subdiscipline, Topic, TopicSubdisciplineRelation,
)
from catalog.services.publication_eligibility import public_editions
from catalog.services.scoped_search import public_scholar_queryset


KINDS = ("knowledge_node", "scholar", "topic", "subdiscipline")
LINK_LABELS = {
    "person_node": "学者与理论对象", "node_topic": "相关主题", "node_subdiscipline": "相关子学科",
    "person_topic": "学者与主题", "person_subdiscipline": "学者与子学科", "topic_subdiscipline": "主题与子学科",
    "teaching": "师承", "cooperation": "合作", "influence": "影响", "criticism": "批评",
    "comparative_reading": "比较阅读", "other": "其他关系",
}
RELATION_TYPES = {**dict(KnowledgeRelation.RelationType.choices), **LINK_LABELS}


def _values(params, key):
    raw = params.getlist(key) if hasattr(params, "getlist") else params.get(key, "")
    if raw is None:
        return []
    raw = raw if isinstance(raw, (list, tuple)) else [raw]
    values = list(dict.fromkeys(part.strip() for value in raw for part in str(value).split(",") if part.strip()))
    if len(values) > 30:
        raise ValidationError({key: "一次最多选择30项。"})
    return values


def _integer(params, key, default, low, high):
    raw = str(params.get(key) if params.get(key) is not None else "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({key: "须填写整数。"}) from exc
    if str(value) != raw.lstrip("+") or not low <= value <= high:
        raise ValidationError({key: f"须为 {low} 至 {high} 范围内的整数。"})
    return value


def graph_options(params):
    kind = str(params.get("center_kind", "knowledge_node")).strip()
    if kind not in KINDS:
        raise ValidationError({"center_kind": "不支持的图谱中心类型。"})
    node_type = _values(params, "node_type")
    if set(node_type) - set(KnowledgeNode.NodeType.values):
        raise ValidationError({"node_type": "不支持的知识节点类型。"})
    types = _values(params, "relation_type")
    if set(types) - RELATION_TYPES.keys():
        raise ValidationError({"relation_type": "包含不支持的正式关系类型。"})
    lower = _integer(params, "start_year", None, -32768, 32767)
    upper = _integer(params, "end_year", None, -32768, 32767)
    if lower is not None and upper is not None and lower > upper:
        raise ValidationError({"end_year": "结束年不能早于开始年。"})
    collection = str(params.get("has_collection") if params.get("has_collection") is not None else "").strip().lower()
    if collection not in {"", "true", "false", "1", "0", "yes", "no"}:
        raise ValidationError({"has_collection": "请选择 true 或 false。"})
    candidates = str(params.get("include_candidates", "false")).strip().lower()
    if candidates not in {"", "true", "false", "1", "0"}:
        raise ValidationError({"include_candidates": "请选择 true 或 false。"})
    return {
        "center_kind": kind, "center": str(params.get("center", "")).strip(),
        "depth": _integer(params, "depth", 1, 1, 3),
        "limit": _integer(params, "limit", 60, 1, 120),
        "edge_limit": _integer(params, "edge_limit", 150, 1, 300),
        "relation_type": types, "node_type": node_type,
        "discipline": str(params.get("discipline", "")).strip(),
        "start_year": lower, "end_year": upper,
        "has_collection": None if not collection else collection in {"true", "1", "yes"},
        "include_candidates": candidates in {"true", "1"},
    }


class _SnapshotEntity(Func):
    """Exact entity IDs inside the active catalog snapshot, including all node kinds."""
    output_field = BooleanField()

    def __init__(self, kind, identifier):
        self.kind = kind
        super().__init__(F("active_catalog_revision__snapshot"), identifier)

    def as_sql(self, compiler, connection, **extra_context):
        snapshot, params = compiler.compile(self.source_expressions[0])
        identifier, identifier_params = compiler.compile(self.source_expressions[1])
        path = {"knowledge_node": ("knowledge", "nodes"), "scholar": ("contributions",),
                "topic": ("knowledge", "topics"), "subdiscipline": ("classification", "subdisciplines")}[self.kind]
        if connection.vendor == "postgresql":
            array = f"({snapshot} #> '{{{','.join(path)}}}')"
            rows = f"jsonb_array_elements(CASE WHEN jsonb_typeof({array}) = 'array' THEN {array} ELSE '[]'::jsonb END) AS item(value)"
            target = "COALESCE(item.value->>'person_id', item.value#>>'{person,id}')" if self.kind == "scholar" else "item.value->>'id'"
            condition = f"{target} = CAST({identifier} AS text)"
        elif connection.vendor == "sqlite":
            array = f"json_extract({snapshot}, '$.{'.'.join(path)}')"
            rows = f"json_each(CASE WHEN json_type({snapshot}, '$.{'.'.join(path)}') = 'array' THEN {array} ELSE '[]' END) AS item"
            target = "COALESCE(json_extract(item.value, '$.person_id'), json_extract(item.value, '$.person.id'))" if self.kind == "scholar" else "json_extract(item.value, '$.id')"
            condition = f"replace({target}, '-', '') = replace(CAST({identifier} AS text), '-', '')"
        else:
            raise NotImplementedError("The public graph requires PostgreSQL or SQLite JSON support.")
        return f"EXISTS (SELECT 1 FROM {rows} WHERE {condition})", [*params, *params, *identifier_params]


def _match_identifier(rows, value):
    try:
        identifier = UUID(value)
    except (ValueError, TypeError, AttributeError):
        return rows.filter(slug=value)
    return rows.filter(Q(pk=identifier) | Q(slug=value))


def entity_querysets(options):
    """Only the requested neighborhood is materialized, never the full authority table."""
    rows = {
        "knowledge_node": KnowledgeNode.objects.filter(status="published").select_related("cover_rendition"),
        "scholar": public_scholar_queryset(),
        "topic": Topic.objects.filter(editorial_status="published"),
        "subdiscipline": Subdiscipline.objects.filter(editorial_status="published").filter(
            Q(discipline__isnull=True) | Q(discipline__editorial_status="published"),
        ).filter(Q(parent__isnull=True) | Q(parent__editorial_status="published")),
    }
    if options["discipline"]:
        disciplines = _match_identifier(Discipline.objects.filter(editorial_status="published"), options["discipline"])
        rows["knowledge_node"] = rows["knowledge_node"].filter(
            Q(primary_discipline__in=disciplines) | Q(discipline_links__discipline__in=disciplines, discipline_links__status="published"),
        ).distinct()
        rows["scholar"] = rows["scholar"].filter(person__discipline_relations__discipline__in=disciplines,
            person__discipline_relations__review_status="approved").distinct()
        rows["topic"] = rows["topic"].filter(discipline_relations__discipline__in=disciplines,
            discipline_relations__review_status="approved").distinct()
        rows["subdiscipline"] = rows["subdiscipline"].filter(discipline__in=disciplines)
    if options["node_type"]:
        rows["knowledge_node"] = rows["knowledge_node"].filter(node_type__in=options["node_type"])
    for kind, start, end in (("knowledge_node", "start_year", "end_year"), ("scholar", "person__birth_year", "person__death_year")):
        if options["start_year"] is not None:
            rows[kind] = rows[kind].filter(Q(**{f"{end}__gte": options["start_year"]}) |
                Q(**{f"{end}__isnull": True, f"{start}__gte": options["start_year"]}))
        if options["end_year"] is not None:
            rows[kind] = rows[kind].filter(Q(**{f"{start}__lte": options["end_year"]}) |
                Q(**{f"{start}__isnull": True, f"{end}__lte": options["end_year"]}))
    if options["has_collection"] is not None:
        for kind in KINDS:
            editions = public_editions().filter(_SnapshotEntity(kind, OuterRef("person_id" if kind == "scholar" else "pk")))
            rows[kind] = rows[kind].filter(Exists(editions) if options["has_collection"] else ~Exists(editions))
    return rows


def _key(kind, identifier):
    return f"{kind}:{identifier}"


def node_payload(kind, row, *, center=False, depth=0):
    from catalog.serializers import PersonCompactSerializer
    from catalog.services.subdiscipline_publication import cover_url
    from catalog.services.knowledge_media import image_media

    scholar = kind == "scholar"
    name = row.person.preferred_name if scholar else row.canonical_name_zh if kind == "knowledge_node" else row.name
    href = f"/theories/nodes/{row.slug}" if kind == "knowledge_node" else f"/{'scholars' if scholar else 'topics' if kind == 'topic' else 'subdisciplines'}/{row.slug}"
    return {
        "id": _key(kind, row.pk), "entity_id": str(row.pk), "kind": kind,
        "node_type": row.node_type if kind == "knowledge_node" else kind,
        "name": name, "slug": row.slug, "href": href,
        "foreign_name": row.person.original_name if scholar else getattr(row, "canonical_name_en", getattr(row, "foreign_name", "")),
        "summary": row.short_description if scholar else (row.summary or row.definition) if kind == "knowledge_node" else row.description,
        "image_url": PersonCompactSerializer().get_portrait(row.person) if scholar else cover_url(row),
        "image_media": PersonCompactSerializer().get_portrait_media(row.person) if scholar else image_media(row),
        "period_label": getattr(row, "period_label", getattr(row, "formation_period", "")),
        "start_year": row.person.birth_year if scholar else getattr(row, "start_year", None),
        "end_year": row.person.death_year if scholar else getattr(row, "end_year", None),
        "is_center": center, "depth": depth,
    }


def edge_querysets(frontier, entities):
    """Each queryset is endpoint-filtered in SQL before the bounded fetch."""
    frontier_ids = {kind: [identifier for selected_kind, identifier in (frontier or []) if selected_kind == kind] for kind in KINDS}
    nodes, people, topics, subdisciplines = (entities[kind].order_by().values("pk") for kind in KINDS)
    person_ids = entities["scholar"].order_by().values("person_id")
    front_people = entities["scholar"].filter(pk__in=frontier_ids["scholar"]).order_by().values("person_id")
    specs = [
        (KnowledgeRelation, "knowledge_node", "source_node", "knowledge_node", "target_node", "", {"status": "published"}, nodes, nodes, frontier_ids["knowledge_node"], frontier_ids["knowledge_node"]),
        (PersonNodeRelation, "scholar", "person", "knowledge_node", "node", "person_node", {"status": "published"}, person_ids, nodes, front_people, frontier_ids["knowledge_node"]),
        (KnowledgeNodeTopic, "knowledge_node", "node", "topic", "topic", "node_topic", {"status": "published"}, nodes, topics, frontier_ids["knowledge_node"], frontier_ids["topic"]),
        (KnowledgeNodeSubdiscipline, "knowledge_node", "node", "subdiscipline", "subdiscipline", "node_subdiscipline", {"status": "published"}, nodes, subdisciplines, frontier_ids["knowledge_node"], frontier_ids["subdiscipline"]),
        (PersonTopicRelation, "scholar", "person", "topic", "topic", "person_topic", {"review_status": "approved"}, person_ids, topics, front_people, frontier_ids["topic"]),
        (PersonSubdisciplineRelation, "scholar", "person", "subdiscipline", "subdiscipline", "person_subdiscipline", {"review_status": "approved"}, person_ids, subdisciplines, front_people, frontier_ids["subdiscipline"]),
        (TopicSubdisciplineRelation, "topic", "topic", "subdiscipline", "subdiscipline", "topic_subdiscipline", {"review_status": "approved"}, topics, subdisciplines, frontier_ids["topic"], frontier_ids["subdiscipline"]),
        (ScholarRelation, "scholar", "source_scholar", "scholar", "target_scholar", "", {"status": "published", "active_revision__status": "published",
            "active_revision__target_type": "scholar_relation", "active_revision__target_id": F("pk")}, people, people, frontier_ids["scholar"], frontier_ids["scholar"]),
    ]
    for model, left_kind, left, right_kind, right, relation_type, status, allowed_left, allowed_right, near_left, near_right in specs:
        query = model.objects.filter(**status, **{f"{left}_id__in": allowed_left, f"{right}_id__in": allowed_right}).select_related(left, right)
        if frontier is not None:
            query = query.filter(Q(**{f"{left}_id__in": near_left}) | Q(**{f"{right}_id__in": near_right}))
        if left == "person":
            query = query.select_related("person__scholar_profile")
        if model is ScholarRelation:
            query = query.select_related("active_revision", "source_scholar__person", "target_scholar__person")
            for side in ("source", "target"):
                query = query.alias(**{
                    f"graph_{side}_published": Replace(KeyTextTransform(f"{side}_scholar", "active_revision__materialized_preview"), Value("-"), Value(""), output_field=CharField()),
                    f"graph_{side}_row": Replace(Cast(f"{side}_scholar_id", CharField()), Value("-"), Value("")),
                }).filter(**{f"graph_{side}_published": F(f"graph_{side}_row")})
        yield model, left_kind, left, right_kind, right, relation_type, query.order_by("pk")


def _edge_payload(spec, row):
    from catalog.services.shared_curation import relation_payload
    model, left_kind, left, right_kind, right, relation_type, _query = spec
    source, target = getattr(row, left), getattr(row, right)
    if left == "person":
        source = source.scholar_profile
    direction, description, evidence_source = "undirected", "", getattr(row, "source", "")
    if model is KnowledgeRelation:
        relation_type, direction, description, evidence_source = row.relation_type, row.direction, row.description, row.evidence_source
        label = row.get_relation_type_display()
    elif model is ScholarRelation:
        payload = relation_payload(row, public=True)
        if not payload or payload["source_scholar"] != str(source.pk) or payload["target_scholar"] != str(target.pk):
            return None
        relation_type, direction = payload["relation_type"], payload["direction"]
        description, evidence_source = payload.get("summary", ""), payload.get("source", "")
        label = LINK_LABELS.get(relation_type, relation_type)
    else:
        label = getattr(row, "relation_label", "") or LINK_LABELS[relation_type]
        description = getattr(row, "relation_role", "")
    return {
        "id": f"{model.__name__}:{row.pk}", "entity_id": str(row.pk), "model": model.__name__,
        "source": _key(left_kind, source.pk), "target": _key(right_kind, target.pk),
        "relation_type": relation_type, "relation_label": label, "direction": direction,
        "description": description, "evidence_source": evidence_source,
        "status": "published", "evidence": [], "evidence_truncated": False,
        "source_status": "citation_only" if evidence_source else "missing",
    }, (left_kind, source), (right_kind, target)


def graph_evidence_queryset(identifiers, request=None):
    from catalog.theory_serializers import _public_evidence_queryset
    # Exact current-page text is checked before ranking, so stale snippets never
    # consume the per-edge allowance or escape via a still-valid reader link.
    page = Page.objects.filter(asset_id=OuterRef("file_id"), index=OuterRef("page_number")).alias(
        graph_quote_position=StrIndex("text", OuterRef("quote")),
    ).filter(graph_quote_position__gt=0)
    return _public_evidence_queryset({"request": request}).filter(
        knowledge_relation_id__in=identifiers, file__edition__active_catalog_revision__document_revision__is_active=True,
        file__edition__active_catalog_revision__document_revision__source_checksum=F("file__sha256"),
    ).exclude(file__sha256="").exclude(quote__regex=r"^\s*$").filter(
        Exists(page), Q(page_end__isnull=True) | Q(page_end=F("page_number")),
    ).annotate(graph_rank=Window(RowNumber(), partition_by=[F("knowledge_relation_id")], order_by=[F("pk").asc()])).filter(graph_rank__lte=7).order_by("knowledge_relation_id", "pk")


def _attach_evidence(edges, request):
    identifiers = [row["entity_id"] for row in edges if row["model"] == "KnowledgeRelation"]
    if not identifiers:
        return
    by_relation = defaultdict(list)
    for row in graph_evidence_queryset(identifiers, request):
        if not row.quote.strip():
            continue
        revision = row.file.edition.active_catalog_revision
        snapshot = revision.snapshot or {}
        by_relation[str(row.knowledge_relation_id)].append({
            "id": str(row.pk), "work_id": str(row.work_id), "edition_id": str(row.file.edition_id),
            "asset_id": str(row.file_id), "document_revision_id": str(revision.document_revision_id),
            "title": str((snapshot.get("work") or {}).get("title") or ""),
            "edition_label": str((snapshot.get("edition") or {}).get("version_label") or ""),
            "quote": row.quote, "pdf_page": row.page_number, "printed_page_label": row.printed_page_label,
            "reader_href": f"/reader/{row.file_id}?page={row.page_number}&evidence={row.pk}&revision={revision.document_revision_id}",
        })
    for edge in edges:
        sources = by_relation.get(edge["entity_id"], []) if edge["model"] == "KnowledgeRelation" else []
        edge["evidence"], edge["evidence_truncated"] = sources[:6], len(sources) > 6
        if sources:
            edge["source_status"] = "available"


def public_graph_edge(identifier):
    """Reuse the exact public edge boundary for private saved-view references."""
    model_name, separator, value = str(identifier).partition(":")
    try:
        key = UUID(value)
    except (ValueError, TypeError, AttributeError):
        return None
    if not separator:
        return None
    for spec in edge_querysets(None, entity_querysets(graph_options({}))):
        if spec[0].__name__ == model_name:
            row = spec[-1].filter(pk=key).first()
            projected = _edge_payload(spec, row) if row else None
            return projected[0] if projected else None
    return None


def _related_works(kind, row, request, page):
    from catalog.theory_serializers import compact_work
    editions = public_editions().filter(_SnapshotEntity(kind, Value(str(row.person_id if kind == "scholar" else row.pk)))).order_by("-is_primary", "pk")
    total = editions.count()
    if page > max(1, (total + 11) // 12):
        raise NotFound("相关文献页码超出当前范围。")
    works = []
    for edition in editions[(page - 1) * 12:page * 12]:
        work = compact_work(edition.work, request, edition=edition)
        if work is not None:
            work["version_label"] = str((edition.active_catalog_revision.snapshot.get("edition") or {}).get("version_label") or "")
            works.append(work)
    return works, total


def build_public_graph(params, request=None):
    from common.capabilities import Capability, has_capability
    options = graph_options(params)
    works_page = _integer(params, "works_page", 1, 1, 2147483647)
    user = getattr(request, "user", None)
    can_review = bool(request and has_capability(user, Capability.VIEW_EVIDENCE) and has_capability(user, Capability.EDIT_DRAFT_AUTHORITY))
    if options["include_candidates"] and not can_review:
        raise PermissionDenied("候选关系需要证据查看与知识编辑权限，普通登录不能查看。")
    entities = entity_querysets(options)
    kind = options["center_kind"]
    center_rows = entities[kind]
    if options["center"]:
        center = _match_identifier(center_rows, options["center"]).first()
        if center is None:
            raise NotFound("所选中心未公开或不在当前筛选范围内。")
    else:
        center = center_rows.order_by("sort_order", "canonical_name_zh", "pk").first() if kind == "knowledge_node" else center_rows.order_by("pk").first()
    result = {
        "center": _key(kind, center.pk) if center else None, "center_kind": kind,
        "nodes": [], "edges": [], "depth": options["depth"], "limit": options["limit"], "edge_limit": options["edge_limit"],
        "truncated": False, "state": "empty", "counts": {"nodes": 0, "edges": 0, "scholars": 0, "topics": 0},
        "filters": {**options, "scope_note": "年代筛选用于理论节点及学者生卒年；主题与子学科保留为关系上下文。节点类型筛选仅用于理论节点。"},
        "relation_types": [{"value": value, "label": label} for value, label in RELATION_TYPES.items()],
        "candidate_access": {"mode": "editorial_only", "can_review": can_review,
            "review_href": "/admin/theories/relations" if can_review else None,
            "detail": "候选仅向具备证据查看和知识编辑权限的人员显示，限当前图中已公开理论节点之间；不显示隐藏实体，不计入正式关系。"},
        "candidate_edges": [], "candidate_count": 0 if options["include_candidates"] else None, "candidates_truncated": False,
        "selected_node": None, "related_works": [], "related_works_count": 0, "related_works_truncated": False,
        "related_works_page": works_page, "related_works_page_size": 12, "related_works_total_pages": 0,
    }
    if center is None:
        return result
    selected = {(kind, center.pk): (center, 0)}
    frontier = {(kind, center.pk)}
    edges, seen_edges = {}, defaultdict(set)
    for level in range(1, options["depth"] + 1):
        next_frontier = set()
        for spec in edge_querysets(frontier, entities):
            model, _lk, _left, _rk, _right, fixed_type, query = spec
            if options["relation_type"]:
                if fixed_type and fixed_type not in options["relation_type"]:
                    continue
                if not fixed_type:
                    field = "active_revision__materialized_preview__relation_type" if model is ScholarRelation else "relation_type"
                    query = query.filter(**{f"{field}__in": options["relation_type"]})
            # One extra eligible edge is enough to establish real truncation.
            for row in query.exclude(pk__in=seen_edges[model])[:options["edge_limit"] - len(edges) + 1]:
                seen_edges[model].add(row.pk)
                projection = _edge_payload(spec, row)
                if projection is None:
                    continue
                edge, left, right = projection
                pending = {(node_kind, entity.pk): entity for node_kind, entity in (left, right) if (node_kind, entity.pk) not in selected}
                if len(edges) >= options["edge_limit"] or len(selected) + len(pending) > options["limit"]:
                    result["truncated"] = True
                    break
                edges[edge["id"]] = edge
                for identity, entity in pending.items():
                    selected[identity] = (entity, level)
                    next_frontier.add(identity)
            if result["truncated"]:
                break
        if result["truncated"] or not next_frontier:
            break
        frontier = next_frontier
    result["nodes"] = [node_payload(node_kind, row, center=(node_kind, row.pk) == (kind, center.pk), depth=level)
                       for (node_kind, _identifier), (row, level) in selected.items()]
    result["edges"] = list(edges.values())
    _attach_evidence(result["edges"], request)
    if options["include_candidates"]:
        node_ids = [identifier for node_kind, identifier in selected if node_kind == "knowledge_node"]
        pending = KnowledgeRelation.objects.filter(
            status__in=("draft", "pending"), source_node_id__in=node_ids, target_node_id__in=node_ids,
            source_node__status="published", target_node__status="published",
        ).select_related("source_node", "target_node").order_by("pk")
        if options["relation_type"]:
            pending = pending.filter(relation_type__in=options["relation_type"])
        candidates = list(pending[:61])
        spec = (KnowledgeRelation, "knowledge_node", "source_node", "knowledge_node", "target_node", "", pending)
        for row in candidates[:60]:
            edge = _edge_payload(spec, row)[0]
            edge.update(status=row.status, source_status="unverified")
            result["candidate_edges"].append(edge)
        result["candidate_count"] = len(result["candidate_edges"])
        result["candidates_truncated"] = len(candidates) > 60
    counts = Counter(row["kind"] for row in result["nodes"])
    result["counts"] = {"nodes": len(selected), "edges": len(edges), "scholars": counts["scholar"], "topics": counts["topic"]}
    result["state"] = "ready" if edges or result["truncated"] else "isolated"
    if not edges and options["relation_type"] and any(spec[-1].exists() for spec in edge_querysets({(kind, center.pk)}, entities)):
        result["state"] = "filtered"
    selected_key = str(params.get("selected_node", "")).strip() or result["center"]
    selected_pair = next(((node_kind, row) for (node_kind, _identifier), (row, _level) in selected.items() if _key(node_kind, row.pk) == selected_key), None)
    if selected_pair:
        result["selected_node"] = selected_key
        result["related_works"], result["related_works_count"] = _related_works(*selected_pair, request, works_page)
        result["related_works_truncated"] = result["related_works_count"] > len(result["related_works"])
        result["related_works_total_pages"] = max(1, (result["related_works_count"] + 11) // 12)
    return result
