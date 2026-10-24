"""Public Topic projections from editorial and catalog publication snapshots.

No title matching, inferred discussion activity or GET-time publication writes.
"""
from copy import copy, deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
from urllib.parse import urlencode
from uuid import uuid4

from django.db import transaction
from django.db.models import BooleanField, Case, CharField, Count, Exists, F, Func, IntegerField, JSONField, OuterRef, Q, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce, StrIndex
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import (ClaimEvidence, CuratedClaim, Discipline, Edition, EditorialRevision, EvidenceCuration,
    EvidenceCurationReference, KnowledgeNode, KnowledgeNodeTopic, Person, PersonTopicRelation,
    ReadingPath, RecommendationIssue, ScholarProfile, Subdiscipline, TheorySchool, Topic)
from catalog.services.public_scholars import _choice, _page, _paging, _strings, _uuid, _values
from catalog.services.publication_eligibility import public_editions, current_retrieval_source_q, active_document_revision_q
from catalog.services.theory_graph import _SnapshotEntity
from common.capabilities import Capability, has_capability

SECTIONS = ("overview", "questions", "works", "scholars", "concepts", "articles", "paths", "evidence")
FOLLOW_NOTICE = "仅关注主题正式发布的档案与编排更新；独立作品、问题、原文和阅读路径的修订不计入此订阅。"
DISCUSSION_NOTICE = "讨论数为该规范问题明确关联、已发布且有当前公开原文支持的编辑立场与批评；回应数仅统计编辑回应，不含私人研究或读者活动。"
CURATION_IDS = {"question_node_ids": (KnowledgeNode, "research_problem"), "debate_node_ids": (KnowledgeNode, "debate"),
    "concept_node_ids": (KnowledgeNode, "concept"), "edition_ids": (Edition, None),
    "foundational_edition_ids": (Edition, None), "disputed_edition_ids": (Edition, None),
    "related_scholar_ids": (ScholarProfile, None), "reading_path_ids": (ReadingPath, None), "issue_ids": (RecommendationIssue, None)}
PUBLIC_FIELDS = ("name", "slug", "search_aliases", "description", "problem_statement", "core_questions",
    "research_dimensions", "methods", "formation_context", "key_concepts", "timeline", "curation_level", "curation")


def _ids(value):
    return list(dict.fromkeys(identifier for item in _strings(value) if (identifier := _uuid(item))))


def validate_topic_parent(topic, parent_id):
    if parent_id in (None, ""):
        return None
    identifier = _uuid(getattr(parent_id, "pk", parent_id))
    if not identifier:
        raise ValidationError({"parent": "上级主题编号无效。"})
    seen = {str(topic.pk)} if topic is not None and topic.pk else set()
    current = identifier
    while current:
        if current in seen:
            raise ValidationError({"parent": "主题不能以自身或后代为上级。"})
        seen.add(current)
        row = Topic.objects.filter(pk=current).values("parent_id", "curation").first()
        if row is None:
            raise ValidationError({"parent": "上级主题不存在。"})
        if (row.get("curation") or {}).get("topic_merge"):
            raise ValidationError({"parent": "合并后的旧主题不能再作为上级，请选择保留的主题。"})
        current = str(row["parent_id"]) if row["parent_id"] else None
    return identifier


def validate_topic_curation(value, topic=None):
    if not isinstance(value, dict):
        raise ValidationError({"curation": "主题编排必须为对象。"})
    result = deepcopy(value)
    for key, (model, node_type) in CURATION_IDS.items():
        if key not in result:
            continue
        rows = result[key]
        maximum = 50 if key == "issue_ids" else 200
        if not isinstance(rows, list) or len(rows) > maximum or any(not _uuid(row) for row in rows):
            raise ValidationError({key: f"请选择最多 {maximum} 个有效对象编号。"})
        identifiers = list(dict.fromkeys(_uuid(row) for row in rows))
        query = model.objects.filter(pk__in=identifiers)
        if node_type:
            query = query.filter(node_type=node_type)
        found = set(map(str, query.values_list("pk", flat=True)))
        if key == "related_scholar_ids" and topic is not None:
            previous = set(_ids((topic.curation or {}).get(key)))
            found.update(map(str, Person.objects.filter(pk__in=previous.intersection(identifiers)).values_list("pk", flat=True)))
        if len(found) != len(identifiers):
            raise ValidationError({key: "包含不存在或类型不符的对象。"})
        result[key] = identifiers
    if "featured_source_id" in result:
        value = result["featured_source_id"]
        if value in (None, ""):
            result["featured_source_id"] = None
        else:
            identifier = _uuid(value)
            rows = EvidenceCurationReference.objects.filter(pk=identifier) if identifier else EvidenceCurationReference.objects.none()
            if topic is not None:
                rows = rows.filter(curation__object_type="topic", curation__object_id=topic.pk)
            if not rows.exists():
                raise ValidationError({"featured_source_id": "请选择本主题已有的真实原文引用。"})
            result["featured_source_id"] = identifier
    return result


def _latest(topic):
    return EditorialRevision.objects.filter(target_type="topic", target_id=topic.pk, status="published").order_by("-revision").first()


def _formal(topic, snapshot=None):
    result = copy(topic)
    if snapshot is None:
        snapshot = getattr(topic, "public_snapshot", None)
        if snapshot is None and not hasattr(topic, "public_snapshot"):
            revision = _latest(topic)
            snapshot = revision.materialized_preview if revision else None
    if snapshot is not None:
        for key in PUBLIC_FIELDS:
            if key in snapshot:
                setattr(result, key, deepcopy(snapshot[key]))
        result.parent_id = _uuid(snapshot.get("parent"))
        result._public_image_selection = snapshot.get("image_selection") or {"object_type": "topic", "object_id": str(topic.pk), "rendition_id": None, "legacy_path": ""}
    result._public_snapshot = snapshot
    return result


class _CuratedEdition(Func):
    """Same explicit edition membership used by cards, counted before pagination."""
    output_field = BooleanField()

    def as_sql(self, compiler, connection, **extra_context):
        (curation, params), (identifier, id_params) = [compiler.compile(value) for value in self.source_expressions]
        clauses, values = [], []
        for key in ("edition_ids", "foundational_edition_ids", "disputed_edition_ids"):
            if connection.vendor == "postgresql":
                array = f"({curation}->'{key}')"
                table = f"jsonb_array_elements_text(CASE WHEN jsonb_typeof({array}) = 'array' THEN {array} ELSE '[]'::jsonb END) item(value)"
                comparison = f"item.value = CAST({identifier} AS text)"
            elif connection.vendor == "sqlite":
                table = f"json_each(CASE WHEN json_type({curation}, '$.{key}') = 'array' THEN json_extract({curation}, '$.{key}') ELSE '[]' END) item"
                comparison = f"replace(item.value, '-', '') = replace(CAST({identifier} AS text), '-', '')"
            else:
                raise NotImplementedError("Topic publication requires PostgreSQL or SQLite JSON support.")
            clauses.append(f"EXISTS (SELECT 1 FROM {table} WHERE {comparison})")
            values.extend([*params, *params, *id_params])
        return "(" + " OR ".join(clauses) + ")", values


def _base(*, counts=True):
    latest = EditorialRevision.objects.filter(target_type="topic", target_id=OuterRef("pk"), status="published").order_by("-revision")
    editions = public_editions().alias(in_topic=_SnapshotEntity("topic", OuterRef("pk")),
        curated_topic=_CuratedEdition(OuterRef("public_curation"), F("pk"))).filter(Q(in_topic=True) | Q(curated_topic=True)).order_by()
    def count(query, field):
        return Coalesce(Subquery(query.annotate(group=Value(1)).values("group").annotate(n=Count(field, distinct=True)).values("n")), 0)
    rows = Topic.objects.filter(editorial_status="published").annotate(
        public_snapshot=Subquery(latest.values("materialized_preview")[:1]),
        public_updated=Coalesce(Subquery(latest.values("published_at")[:1]), F("updated_at")),
    ).annotate(public_curation=Case(When(public_snapshot__isnull=True, then=F("curation")),
        default=KeyTransform("curation", "public_snapshot"), output_field=JSONField()),
    )
    if counts:
        rows = rows.annotate(public_work_count=count(editions, "work_id"), public_edition_count=count(editions, "pk"))
    return rows.annotate(public_name=Coalesce(KeyTextTransform("name", "public_snapshot"), F("name"), output_field=CharField()),
        public_slug=Coalesce(KeyTextTransform("slug", "public_snapshot"), F("slug"), output_field=CharField()),
        public_description=Coalesce(KeyTextTransform("description", "public_snapshot"), F("description"), output_field=CharField()),
        public_problem=Coalesce(KeyTextTransform("problem_statement", "public_snapshot"), F("problem_statement"), output_field=CharField()))


def _revision(topic, revision=None):
    revision = revision or _latest(topic)
    if revision:
        return {"token": f"{revision.pk}:{revision.revision}", "id": str(revision.pk), "number": revision.revision,
            "published_at": revision.published_at.isoformat() if revision.published_at else None, "change_note": revision.change_note}
    from catalog.services.knowledge_media import image_selection
    raw = {key: getattr(topic, key) for key in PUBLIC_FIELDS}
    raw.update(parent=str(topic.parent_id) if topic.parent_id else None, image_selection=image_selection(topic))
    digest = sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return {"token": "legacy:" + digest, "id": None, "number": None, "published_at": None, "change_note": "既有已发布主题；读取不创建版本。"}


def topic_follow_summary(topic_id):
    if not _uuid(topic_id):
        return None
    topic = Topic.objects.filter(pk=topic_id, editorial_status="published").first()
    if topic is None:
        return None
    revision = _latest(topic)
    row = _formal(topic, revision.materialized_preview) if revision else topic
    version = _revision(row, revision)
    return {"topic_id": str(row.pk), "slug": row.slug, "name": row.name, "public_revision": version["token"],
        "updated_at": version["published_at"], "scope_notice": FOLLOW_NOTICE}


def topic_identity(topic_id):
    """Lightweight safe projection for the existing SavedTopic serializer."""
    if not _uuid(topic_id):
        return None
    topic = Topic.objects.filter(pk=topic_id, editorial_status="published").first()
    if topic is None:
        return None
    topic = _formal(topic)
    return {**_link(topic), "description": topic.description}


def topic_id_for_public_slug(slug):
    return _base(counts=False).filter(public_slug=str(slug)).values_list("pk", flat=True).first()


@transaction.atomic
def capture_topic_publication(topic, *, actor, change_note="发布主题"):
    """Direct administrative publication and audited merges share EditorialRevision."""
    from catalog.services.editorial_revision import editorial_target_snapshot
    from catalog.topic_editor import lock_topic_hierarchy, ensure_topic_publication
    lock_topic_hierarchy()
    if topic.editorial_status == "published":
        ensure_topic_publication(topic)
    Topic.objects.select_for_update().get(pk=topic.pk)
    latest = EditorialRevision.objects.filter(target_type="topic", target_id=topic.pk).order_by("-revision").first()
    revision = EditorialRevision.objects.create(target_type="topic", target_id=topic.pk,
        revision=(latest.revision if latest else 0) + 1, base_revision=latest.revision if latest else 0,
        patch={}, materialized_preview=editorial_target_snapshot(target_type="topic", target=topic), changed_fields=[],
        status="published", idempotency_key=f"topic-publication:{uuid4()}", change_note=change_note,
        created_by=actor, published_by=actor, published_at=timezone.now())
    from catalog.services.knowledge_media import protect_image_references
    protect_image_references(revision, topic)
    return revision


def _link(topic):
    return {"id": str(topic.pk), "slug": topic.slug, "name": topic.name, "href": f"/topics/{topic.slug}"}


def _tree():
    # One directory read; formal parents are resolved only among currently public topics.
    topics = {_uuid(row.pk): _formal(row) for row in _base(counts=False).order_by("public_name", "pk")}
    parents = {key: str(row.parent_id) if str(row.parent_id) in topics else None for key, row in topics.items()}
    for key in parents:
        seen, current = {key}, parents[key]
        while current:
            if current in seen:
                parents[key] = None
                break
            seen.add(current)
            current = parents[current]
    descendants = {key: set() for key in topics}
    for key in topics:
        current, seen = parents[key], {key}
        while current and current not in seen:
            descendants[current].add(key)
            seen.add(current)
            current = parents[current]
    return topics, parents, descendants


def _selected_first(rows, identifiers, ordering):
    ids = _ids(identifiers)
    if not ids:
        return rows.order_by(*ordering)
    return rows.annotate(editorial_position=Case(*[When(pk=identifier, then=Value(index)) for index, identifier in enumerate(ids)],
        default=Value(len(ids)), output_field=IntegerField())).order_by("editorial_position", *ordering)


def _editions(topic):
    curated = topic.curation if isinstance(topic.curation, dict) else {}
    explicit = [identifier for key in ("edition_ids", "foundational_edition_ids", "disputed_edition_ids") for identifier in _ids(curated.get(key))]
    return public_editions().alias(in_topic=_SnapshotEntity("topic", Value(str(topic.pk)))).filter(Q(in_topic=True) | Q(pk__in=explicit)).distinct()


def _nodes(topic, types):
    curated = topic.curation if isinstance(topic.curation, dict) else {}
    explicit = [key for kind, key in (("research_problem", "question_node_ids"), ("debate", "debate_node_ids"), ("concept", "concept_node_ids")) if kind in types]
    identifiers = [value for key in explicit for value in _ids(curated.get(key))]
    return KnowledgeNode.objects.filter(status="published", node_type__in=types).filter(
        Q(pk__in=KnowledgeNodeTopic.objects.filter(topic=topic, status="published").values("node_id")) | Q(pk__in=identifiers)).distinct()


def _scholars(topic):
    from catalog.services.public_scholars import _base as scholar_base
    curated = topic.curation if isinstance(topic.curation, dict) else {}
    return scholar_base().filter(Q(person_id__in=PersonTopicRelation.objects.filter(topic=topic, review_status="approved").values("person_id")) |
        Q(pk__in=_ids(curated.get("related_scholar_ids")))).distinct().order_by("public_name", "pk")


def _image_media(topic, *, private=False):
    from catalog.services.knowledge_media import image_media
    selection = getattr(topic, "_public_image_selection", None)
    return image_media(topic, selection=selection, private=private)


def _image(topic, *, private=False, media=None):
    selection = getattr(topic, "_public_image_selection", None)
    media = media if media is not None else _image_media(topic, private=private)
    if media:
        return next((row["url"] for row in media["renditions"] if row["id"] == media["primary_rendition_id"]), "")
    permitted = selection is None or selection.get("legacy_path") == topic.hero_image.name
    return topic.hero_image.url if permitted and topic.hero_image else ""


def _cards(rows, tree=None, *, private=False, query=""):
    topics, parents, _descendants = tree or _tree()
    output = []
    for raw in rows:
        row = _formal(raw) if not getattr(raw, "_topic_preview", False) else raw
        editions = _editions(row)
        parent = topics.get(parents.get(str(row.pk)))
        media = _image_media(row, private=private)
        output.append({**_link(row), "description": row.description, "problem_statement": row.problem_statement,
            "hero_image": _image(row, private=private, media=media), "cover_media": media, "tags": _strings(row.key_concepts),
            "matched_alias": next((alias for alias in _strings(row.search_aliases) if query and alias.casefold() == query.casefold() and alias != row.name), ""),
            "parent": _link(parent) if parent else None, "work_count": row.public_work_count if not private and hasattr(row, "public_work_count") else editions.values("work_id").distinct().count(),
            "edition_count": row.public_edition_count if not private and hasattr(row, "public_edition_count") else editions.count(), "scholar_count": _scholars(row).count(),
            "question_count": _nodes(row, ("research_problem", "debate")).count(),
            "profile_state": "available" if row.description or row.problem_statement else "sparse"})
    return output


def public_topic_directory(params=None, *, request=None):
    params = params or {}
    _paging(params)
    sort = _choice(params, "sort", ("relevance", "name", "works", "updated"), "relevance")
    query = str(params.get("q") or params.get("search") or "").strip()
    if len(query) > 300:
        raise ValidationError({"q": "关键词不能超过 300 字。"})
    tree = _tree()
    topics, parents, descendants = tree
    rows = _base()
    parent_values = _values(params, "parent")
    if len(parent_values) > 20:
        raise ValidationError({"parent": "一次最多选择 20 个主题分支。"})
    selected_parents = [next((row for key, row in topics.items() if key == value or row.slug == value), None) for value in parent_values]
    selected = selected_parents[0] if selected_parents else None
    parent_value = parent_values[0] if parent_values else ""
    if parent_values:
        branches = set()
        for row in selected_parents:
            if row is not None:
                branches.update({str(row.pk)} | descendants[str(row.pk)])
        rows = rows.filter(pk__in=branches if all(row is not None for row in selected_parents) else [])
    filters = {key: str(params.get(key, "")).strip() for key in ("discipline", "subdiscipline", "theory")}
    for key, value in filters.items():
        if not value:
            continue
        field, target = {"discipline": ("discipline_relations", "discipline"), "subdiscipline": ("subdiscipline_relations", "subdiscipline"), "theory": ("theory_relations", "theory_school")}[key]
        identifier = _uuid(value)
        relation = Q(**{field + "__review_status": "approved", field + "__" + target + "__editorial_status": "published",
            field + "__" + target + ("_id" if identifier else "__slug"): identifier or value})
        if key == "theory":
            # Keep canonical-node links and legacy-school links as distinct identities.
            normalized = KnowledgeNodeTopic.objects.filter(status="published", node__status="published", node__node_type="theory_tradition")
            normalized = normalized.filter(**{"node_id" if identifier else "node__slug": identifier or value})
            relation |= Q(pk__in=normalized.values("topic_id"))
        rows = rows.filter(relation)
    if query:
        formal_match = Q(public_name__icontains=query) | Q(public_description__icontains=query) | Q(public_problem__icontains=query)
        # Labels and aliases are only those in the formal snapshot; old public topics retain their canonical aliases.
        formal_match |= Q(public_snapshot__search_aliases__icontains=query) | Q(public_snapshot__isnull=True, search_aliases__icontains=query)
        matching_nodes = KnowledgeNode.objects.filter(status="published").filter(Q(canonical_name_zh__icontains=query) | Q(canonical_name_en__icontains=query))
        rows = rows.filter(formal_match | Q(pk__in=KnowledgeNodeTopic.objects.filter(status="published", node__in=matching_nodes).values("topic_id")))
    ordering = {"name": ("public_name", "pk"), "works": ("-public_work_count", "public_name", "pk"), "updated": ("-public_updated", "public_name", "pk"), "relevance": ("public_name", "pk")}[sort]
    result = _page(rows.distinct().order_by(*ordering), params, "/api/catalog/topics/", transform=lambda page: _cards(page, tree, query=query))
    from catalog.services.recommendations import current_recommendations
    recommendation = current_recommendations(read_only=True).get("home_topics")
    recommended = []
    if recommendation:
        ids = list(recommendation.items.filter(topic__editorial_status="published").order_by("position", "pk").values_list("topic_id", flat=True)[:48])
        cards = {row["id"]: row for row in _cards(_base().filter(pk__in=ids), tree)}
        recommended = [cards[str(key)] for key in ids if str(key) in cards]
    exact = [row for row in topics.values() if query and query.casefold() in {row.name.casefold(), *(alias.casefold() for alias in _strings(row.search_aliases))}]
    result.update(query=query, filters={**filters, "parent": parent_value, "parents": parent_values, "sort": sort}, selected_parent=_link(selected) if selected else None,
        selected_parents=[_link(row) for row in selected_parents if row is not None],
        hierarchy=[{**_link(row), "parent_id": parents[key], "child_count": sum(value == key for value in parents.values()),
            "descendant_count": len(descendants[key]), "count": len(descendants[key]) + 1} for key, row in topics.items()],
        recommendations={"revision_id": str(recommendation.pk) if recommendation else None, "source": recommendation.source if recommendation else "", "results": recommended},
        disambiguation=_cards(exact, tree, query=query) if len(exact) > 1 else [],
        overlap_notice="多个正式主题匹配同一名称或已确认别名，请按各自的问题范围选择。" if len(exact) > 1 else "")
    return result


def _knowledge_rows(rows, topic):
    rows = list(rows)
    result = []
    relations = {row.node_id: row.relation_label for row in KnowledgeNodeTopic.objects.filter(topic=topic, status="published", node__in=rows)}
    links = ClaimEvidence.objects.filter(evidence_span__is_stale=False,
        evidence_span__page__asset_id=F("evidence_span__document_revision__asset_id"),
        evidence_span__page_number=F("evidence_span__page__index")).filter(
        active_document_revision_q(revision_prefix="evidence_span__document_revision"),
        current_retrieval_source_q(asset_prefix="evidence_span__document_revision__asset", access_statuses=("public", "inherit")),
    ).alias(quote_position=StrIndex("evidence_span__page__text", F("evidence_span__original_text"))).filter(quote_position__gt=0).exclude(evidence_span__original_text="")
    counts = {(row["node_id"], row["kind"]): row["n"] for row in CuratedClaim.objects.filter(node__in=rows,
        status="published", evidence_links__in=links).values("node_id", "kind").annotate(n=Count("pk", distinct=True))}
    for row in rows:
        result.append({"id": str(row.pk), "slug": row.slug, "name": row.canonical_name_zh, "href": f"/theories/nodes/{row.slug}",
            "node_type": row.node_type, "summary": row.summary, "relation_label": relations.get(row.pk) or "编辑选入",
            "work_count": public_editions().filter(_SnapshotEntity("knowledge_node", Value(str(row.pk)))).values("work_id").distinct().count(),
            "discussion_count": counts.get((row.pk, "major_criticism"), 0) + counts.get((row.pk, "debate_position"), 0),
            "response_count": counts.get((row.pk, "major_response"), 0), "count_notice": DISCUSSION_NOTICE})
    return result


def _evidence(topic):
    from catalog.services.shared_curation import curation_payload, sources, source_payload
    owner = EvidenceCuration.objects.filter(object_type="topic", object_id=topic.pk, active_revision__status="published",
        active_revision__target_type="evidence_curation", active_revision__target_id=F("pk")).first()
    items = curation_payload("topic", topic.pk, public=True)["items"] if owner is not None and topic.editorial_status == "published" else []
    legacy_id = _uuid((topic.curation or {}).get("featured_passage_id"))
    if legacy_id and not any(row["source_type"] == "passage" and row["source_id"] == legacy_id for row in items):
        items.append({"id": legacy_id, "source_type": "passage", "source_id": legacy_id, "group_title": "既有主题原文", "reason": "旧编排保留的准确段落身份。", "order": len(items)})
    current = {kind: {str(row.pk): row for row in sources(kind, public=True).filter(pk__in=[item["source_id"] for item in items if item["source_type"] == kind]).filter(
        current_retrieval_source_q(asset_prefix="page__asset", access_statuses=("public", "inherit")))}
        for kind in ("span", "passage")}
    output = []
    for item in items:
        row = current[item["source_type"]].get(item["source_id"])
        text = row.original_text if row and item["source_type"] == "span" else row.text if row else ""
        if row is None or not text or (row.page.text or "")[row.start_offset:row.end_offset] != text:
            continue
        item = deepcopy(item)
        if "source" not in item:
            try:
                item["source"] = source_payload(item["source_type"], row, public=True)
            except ValidationError:
                continue
        source = item["source"]
        source["reader_url"] = f"/reader/{source['asset_id']}?page={source['page_start']}&revision={source['document_revision_id']}"
        output.append(item)
    return output


def _articles_and_planned(topic):
    from catalog.services.editorial_issues import published_issues, issue_payload
    ids = _ids((topic.curation or {}).get("issue_ids"))
    issues = {str(row.pk): row for row in published_issues().filter(pk__in=ids)}
    articles, planned = [], []
    for identifier in ids:
        issue = issues.get(identifier)
        if issue is None:
            continue
        data = issue_payload(issue, public=True)
        linked = {str(value) for value in issue.items.filter(linked_edition__isnull=False).values_list("pk", flat=True)}
        articles.append({"id": identifier, "slug": data["slug"], "title": data.get("title", ""),
            "summary": data.get("introduction", ""), "href": f"/recommendations/{data['slug']}", "cover_url": data.get("cover_url", ""),
            "public_byline": data.get("public_byline", ""), "published_at": data.get("published_at")})
        for item in data.get("items", []):
            if item.get("kind") != "planned" or item.get("status") != "planned" or item["id"] in linked:
                continue
            planned.append({"id": item["id"], "edition_id": None, "catalog_revision_id": None,
                "title": item.get("title", ""), "original_title": "", "href": articles[-1]["href"], "cover_url": item.get("cover_url", ""),
                "document_type": item.get("document_type", ""), "language": item.get("language", ""), "publication_year": item.get("publication_year"),
                "version_label": item.get("version_label", ""), "roles": [], "role_labels": [], "contributions": [],
                "source_status": "planned", "source_notice": "已由本期公开策划明确列为计划材料；尚无可读馆藏版本。",
                "reader_href": "", "is_essential": False, "selection": "related", "issue_id": identifier, "issue_item_id": item["id"]})
    return articles, planned


def _work_rows(rows, topic):
    from catalog.services.public_scholars import _work_rows as edition_cards
    curated = topic.curation or {}
    foundational, disputed = set(_ids(curated.get("foundational_edition_ids"))), set(_ids(curated.get("disputed_edition_ids")))
    rows = list(rows)
    readable = {str(key) for key in public_editions().filter(pk__in=[row.pk for row in rows]).filter(
        current_retrieval_source_q(asset_prefix="active_catalog_revision__reader_asset", access_statuses=("public", "inherit"))).values_list("pk", flat=True)}
    output = edition_cards(rows, SimpleNamespace(person_id=None, curation={}))
    for row in output:
        if row["edition_id"] not in readable:
            row.update(source_status="no_fulltext", reader_href="")
        row.update(selection="foundational" if row["edition_id"] in foundational else "disputed" if row["edition_id"] in disputed else "related",
            source_notice="可打开当前公开版本原文。" if row["source_status"] == "available" else "当前仅有公开书目，尚无可读全文；此状态不代表待购。",
            issue_id=None, issue_item_id=None)
    return output


def _path_candidates(topic, editions, nodes, explicit):
    from catalog.services.public_scholars import _related_path_candidates
    candidates = _related_path_candidates(editions, nodes, explicit)
    latest = EditorialRevision.objects.filter(target_type="reading_path", target_id=OuterRef("pk"), status="published", materialized_preview__status="published").order_by("-revision")
    topic_paths = ReadingPath.objects.filter(status="published").annotate(public_snapshot=Subquery(latest.values("materialized_preview")[:1])).filter(
        Q(public_snapshot__topics__icontains=str(topic.pk)) | Q(public_snapshot__isnull=True, topics=topic)).distinct()
    return (candidates | topic_paths).distinct()


def _paths(topic, editions, nodes, params, path, request):
    from catalog.services.public_reading_paths import public_reading_path_snapshots
    explicit = set(_ids((topic.curation or {}).get("reading_path_ids")))
    # The candidate SQL is not membership proof: a withdrawn or revised material cannot keep a path related.
    candidates = _selected_first(_path_candidates(topic, editions, nodes, explicit),
        (topic.curation or {}).get("reading_path_ids", []), ("sort_order", "title", "pk"))
    edition_ids, node_ids = ({str(value) for value in rows.values_list("pk", flat=True)} for rows in (editions, nodes))
    page, size = _paging(params)
    if params.get("section", "overview") != "paths":
        page = 1
    total, selected, batch = 0, [], []
    def accept(rows):
        nonlocal total
        for item in public_reading_path_snapshots(rows, request=request):
            linked = item["id"] in explicit or any(row["id"] == str(topic.pk) for row in item.get("topics", []))
            linked |= any(row.get("source_status") in {"available", "no_fulltext"} and (row.get("edition_id") in edition_ids or row.get("node_id") in node_ids) for row in item["items"])
            if not linked:
                continue
            if (page - 1) * size <= total < page * size:
                selected.append(item)
            total += 1
    for row in candidates.iterator(chunk_size=100):
        batch.append(row)
        if len(batch) == 48:
            accept(batch)
            batch = []
    accept(batch)
    output = _page(range(total), params, path, section="paths")
    output["results"] = selected
    return output


def public_topic_detail(slug, params=None, *, request=None, preview_topic=None):
    params = params or {}
    _paging(params)
    section = _choice(params, "section", SECTIONS, "overview")
    question_type = _choice(params, "question_type", ("all", "research_problem", "debate"), "all")
    availability = _choice(params, "availability", ("all", "readable", "no_fulltext", "planned"), "all")
    reading = _choice(params, "reading", ("all", "foundational", "disputed"), "all")
    sort = _choice(params, "sort", ("relevance", "published", "title"), "relevance")
    topic = preview_topic or _formal(get_object_or_404(_base(), public_slug=slug))
    tree = _tree()
    topics, parents, _descendants = tree
    if preview_topic is not None:
        topics[str(topic.pk)] = topic
        parents[str(topic.pk)] = str(topic.parent_id) if str(topic.parent_id) in topics else None
    path = f"/api/catalog/topics/{topic.slug}/"
    result = _cards([topic], tree, private=preview_topic is not None)[0]
    curation = topic.curation if isinstance(topic.curation, dict) else {}
    editions = _editions(topic)
    nodes = _nodes(topic, ("research_problem", "debate", "concept"))
    questions = nodes.filter(node_type__in=("research_problem", "debate"))
    if question_type != "all":
        questions = questions.filter(node_type=question_type)
    concepts = nodes.filter(node_type="concept")
    scholars = _selected_first(_scholars(topic), curation.get("related_scholar_ids", []), ("public_name", "pk"))
    from catalog.services.public_scholars import _cards as scholar_cards
    articles, planned = _articles_and_planned(topic)
    readable = editions.filter(current_retrieval_source_q(asset_prefix="active_catalog_revision__reader_asset", access_statuses=("public", "inherit")))
    facets = {"all": editions.count() + len(planned), "readable": readable.count(), "no_fulltext": editions.count() - readable.count(), "planned": len(planned)}
    works = editions
    if availability == "readable":
        works = readable
    elif availability == "no_fulltext":
        works = editions.exclude(pk__in=readable.values("pk"))
    elif availability == "planned":
        works = editions.none()
    if reading != "all":
        works = works.filter(pk__in=_ids(curation.get(reading + "_edition_ids")))
        planned = []
    if availability not in {"all", "planned"}:
        planned = []
    # SQL ordering uses published metadata, never a newer working bibliography.
    works = works.annotate(public_title=KeyTextTransform("title", "active_catalog_revision__snapshot__work"))
    ordering = ("public_title", "pk") if sort == "title" else ("-active_catalog_revision__snapshot__edition__publication_year", "pk") if sort == "published" else ("-published_at", "pk")
    works = _selected_first(works, [identifier for key in ("edition_ids", "foundational_edition_ids", "disputed_edition_ids") for identifier in _ids(curation.get(key))], ordering) if sort == "relevance" else works.order_by(*ordering)
    work_page = _page(works, params, path, transform=lambda rows: _work_rows(rows, topic), section="works")
    # Explicit planned records follow catalog versions; their page count remains exact.
    work_total = works.count()
    page, size = _paging(params)
    if section != "works":
        page = 1
    start, end = (page - 1) * size, page * size
    if planned and end > work_total:
        work_page["results"].extend(planned[max(0, start - work_total):max(0, end - work_total)])
    page_meta = _page(range(work_total + len(planned)), params, path, section="works")
    work_page.update({key: value for key, value in page_meta.items() if key != "results"})
    evidence = _evidence(topic)
    result.update(public_revision=_revision(topic), introduction={key: getattr(topic, key) for key in ("description", "problem_statement", "formation_context", "core_questions", "research_dimensions", "methods")},
        questions=_page(_selected_first(questions, [*_ids(curation.get("question_node_ids")), *_ids(curation.get("debate_node_ids"))], ("sort_order", "canonical_name_zh", "pk")), params, path, transform=lambda rows: _knowledge_rows(rows, topic), section="questions"),
        concepts=_page(_selected_first(concepts, curation.get("concept_node_ids", []), ("sort_order", "canonical_name_zh", "pk")), params, path, transform=lambda rows: _knowledge_rows(rows, topic), section="concepts"),
        works=work_page, scholars=_page(scholars, params, path, transform=scholar_cards, section="scholars"),
        articles=_page(articles, params, path, section="articles"), paths=_paths(topic, editions, nodes, params, path, request),
        evidence=_page(evidence, params, path, section="evidence"), featured_quote=next((row for row in evidence if row["id"] == (curation.get("featured_source_id") if "featured_source_id" in curation else curation.get("featured_passage_id"))), None),
        filters={"section": section, "question_type": question_type, "availability": availability, "reading": reading, "sort": sort}, work_facets=facets,
        feedback_href="/feedback?" + urlencode({"category": "content", "path": f"/topics/{topic.slug}"}),
        graph_href="/theories/graph?" + urlencode({"center_kind": "topic", "center": str(topic.pk)}),
        research_href="/explore?" + urlencode({"mode": "ask", "context": "topics", "id": str(topic.pk)}), discussion_notice=DISCUSSION_NOTICE,
        children=[_link(topics[key]) for key, parent in parents.items() if parent == str(topic.pk)])
    ancestors, current, seen = [], parents.get(str(topic.pk)), {str(topic.pk)}
    while current and current not in seen:
        seen.add(current)
        ancestors.append(_link(topics[current]))
        current = parents[current]
    result["breadcrumbs"] = list(reversed(ancestors))
    result["counts"] = {key: result[key]["count"] for key in SECTIONS if key != "overview"}
    result["unavailable_links"] = _unavailable(topic, nodes, editions, scholars, articles)
    result["unavailable_notice"] = "部分曾编入的关联目前不可公开访问；仅保留失效标识，不展示其名称或正文。" if result["unavailable_links"] else ""
    result["legacy"] = _legacy(topic)
    return result


def _legacy(topic):
    from catalog.services.editorial_revision import topic_relation_snapshot
    raw = getattr(topic, "_public_snapshot", None)
    raw = raw if raw is not None else topic_relation_snapshot(topic)
    def linked(key, field, model, path):
        ids = [row.get(field) for row in raw.get(key, []) if isinstance(row, dict) and row.get("review_status") == "approved"]
        return [{"id": str(row.pk), "slug": row.slug, "name": row.name, "href": f"/{path}/{row.slug}"}
            for row in model.objects.filter(pk__in=_ids(ids), editorial_status="published").order_by("name", "pk")]
    timeline = []
    for row in topic.timeline if isinstance(topic.timeline, list) else []:
        if isinstance(row, (tuple, list)) and len(row) == 3 and all(isinstance(value, (str, int)) for value in row):
            timeline.append({"year": row[0], "title": row[1], "description": row[2]})
        elif isinstance(row, dict):
            timeline.append({key: value for key, value in row.items() if key in {"year", "date", "period", "title", "description", "label", "text"} and isinstance(value, (str, int))})
    curation = topic.curation if isinstance(topic.curation, dict) else {}
    inline_paths = [row for row in curation.get("reading_paths", []) if isinstance(row, dict)]
    old_work_ids = _ids([*curation.get("foundational_work_ids", []), *curation.get("recent_work_ids", []),
        *(identifier for row in inline_paths for identifier in row.get("work_ids", []))])
    work_cards = {}
    for edition in public_editions().filter(work_id__in=old_work_ids).order_by("-is_primary", "pk"):
        work_cards.setdefault(str(edition.work_id), {"id": str(edition.work_id), "title": (edition.active_catalog_revision.snapshot or {}).get("work", {}).get("title", ""),
            "href": f"/works/{edition.public_slug}", "notice": "旧编排仅记录作品身份，未指定版本；请在作品页选择准确版本。"})
    def work_list(values):
        return [work_cards[key] for key in _ids(values) if key in work_cards]
    from catalog.services.public_scholars import _base as scholar_base, _cards as scholar_cards
    old_people = _ids(curation.get("related_scholar_ids"))
    actual_profiles = set(map(str, ScholarProfile.objects.filter(pk__in=old_people).values_list("pk", flat=True)))
    old_people = [key for key in old_people if key not in actual_profiles]
    legacy_scholars = [{"id": row["person_id"], "profile_id": row["id"], "name": row["person"]["preferred_name"],
        "href": row["href"], "identity_kind": "person", "notice": "旧编排记录人物身份，经现有一对一学者档案关系提供入口。"}
        for row in scholar_cards(scholar_base().filter(person_id__in=old_people))]
    linked_theories = linked("theory_relations", "theory_school_id", TheorySchool, "theory-schools")
    known = {row["id"] for row in linked_theories}
    linked_theories.extend({"id": str(row.pk), "slug": row.slug, "name": row.name, "href": f"/theory-schools/{row.slug}"}
        for row in TheorySchool.objects.filter(pk__in=_ids(curation.get("linked_theory_ids")), editorial_status="published").order_by("name", "pk") if str(row.pk) not in known)
    return {"timeline": timeline, "research_dimensions": _strings(topic.research_dimensions), "methods": _strings(topic.methods),
        "subdisciplines": linked("subdiscipline_relations", "subdiscipline_id", Subdiscipline, "subdisciplines"),
        "linked_theories": linked_theories, "related_scholars": legacy_scholars,
        "curated_works": {"foundational": work_list(curation.get("foundational_work_ids")), "recent": work_list(curation.get("recent_work_ids"))},
        "reading_paths": [{"title": str(row.get("title") or ""), "description": str(row.get("description") or ""), "level": str(row.get("level") or ""),
            "works": work_list(row.get("work_ids")), "unavailable_work_ids": [key for key in _ids(row.get("work_ids")) if key not in work_cards],
            "notice": "既有主题内编排，尚非独立阅读路径；保留原作品身份与顺序。"} for row in inline_paths],
        "theory_nodes": [{"id": str(row.pk), "slug": row.slug, "name": row.canonical_name_zh, "href": f"/theories/nodes/{row.slug}"}
            for row in _nodes(topic, ("theory_tradition",)).order_by("sort_order", "canonical_name_zh", "pk")]}


def _unavailable(topic, nodes, editions, scholars, articles):
    curation = topic.curation or {}
    sets = {"question": set(map(str, nodes.filter(node_type__in=("research_problem", "debate")).values_list("pk", flat=True))),
        "concept": set(map(str, nodes.filter(node_type="concept").values_list("pk", flat=True))),
        "work": set(map(str, editions.values_list("pk", flat=True))), "scholar": set(map(str, scholars.values_list("pk", flat=True))),
        "article": {row["id"] for row in articles}, "path": set(map(str, ReadingPath.objects.filter(status="published", pk__in=_ids(curation.get("reading_path_ids"))).values_list("pk", flat=True)))}
    keys = {"question": ("question_node_ids", "debate_node_ids"), "concept": ("concept_node_ids",), "work": ("edition_ids", "foundational_edition_ids", "disputed_edition_ids"),
        "scholar": ("related_scholar_ids",), "article": ("issue_ids",), "path": ("reading_path_ids",)}
    from catalog.services.scoped_search import public_scholar_queryset
    legacy_people = set(_ids(curation.get("related_scholar_ids"))) - set(map(str, ScholarProfile.objects.filter(pk__in=_ids(curation.get("related_scholar_ids"))).values_list("pk", flat=True)))
    sets["scholar"].update(map(str, public_scholar_queryset().filter(person_id__in=legacy_people).values_list("person_id", flat=True)))
    return [{"id": identifier, "kind": kind, "status": "unavailable", "notice": "该关联对象目前不可公开访问。"}
        for kind, fields in keys.items() for identifier in _ids([value for key in fields for value in curation.get(key, [])]) if identifier not in sets[kind]]


def preview_topic(target, *, snapshot=None, request=None, curation_overrides=None):
    if not has_capability(getattr(request, "user", None), Capability.ACCESS_BACK_OFFICE):
        raise PermissionDenied("主题预览需要后台访问权限。")
    row = _formal(target, snapshot) if snapshot is not None else copy(target)
    if curation_overrides is not None:
        if not isinstance(curation_overrides, dict) or set(curation_overrides) - {"curation", "parent"}:
            raise ValidationError("主题预览只接受明确的编排字段。")
        overrides = curation_overrides.get("curation", {})
        if not isinstance(overrides, dict) or set(overrides) - set(CURATION_IDS) - {"featured_source_id"}:
            raise ValidationError("主题预览包含不支持的策划字段。")
        if "parent" in curation_overrides:
            row.parent_id = validate_topic_parent(row, curation_overrides["parent"])
        row.curation = {**deepcopy(row.curation or {}), **validate_topic_curation(overrides, row)}
    row._topic_preview = True
    result = public_topic_detail(row.slug, request=request, preview_topic=row)
    result["public_revision"] = {"token": "preview", "id": None, "number": None, "published_at": None, "change_note": "编辑预览，尚未发布。"}
    return result
