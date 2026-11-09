"""Scholar pages over existing authority, editorial and publication records.

No GET creates a revision, promotes a name, or infers authorship/influence.
All material membership comes from activated edition contribution snapshots.
"""
from copy import deepcopy
from hashlib import sha256
import json
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as ModelValidationError
from django.db.models import (BooleanField, Case, CharField, Count, Exists, F, Func,
                             IntegerField, OuterRef, Prefetch, Q, Subquery, Value, When)
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Cast, Coalesce, NullIf, Replace, StrIndex
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import (Contribution, EditorialRevision, EvidenceCurationReference,
    KnowledgeNode, Page, PersonNameVariant, PersonNodeRelation, PersonSubdisciplineRelation,
    PersonTopicRelation, ReadingPath, ScholarProfile, ScholarRelation, Subdiscipline, Topic,
    Work, WorkNodeRelation)
from catalog.services.publication_eligibility import public_editions
from catalog.services.scoped_search import public_scholar_queryset
from catalog.services.query_lexicon.registry import FORMAL_PERSON_VARIANT_SOURCES
from common.capabilities import Capability, has_capability

SECTIONS = ("overview", "works", "concepts", "questions", "timeline", "relations", "topics", "paths", "sources", "evidence")
PROFILE_SOURCE_FIELDS = ("preferred_name", "original_name", "birth_year", "death_year", "biography",
    "short_description", "nationalities", "occupations", "affiliations", "key_concerns")
PERIODS = {"classical": ("古典（1800 年以前）", -9999, 1799),
           "modern": ("近现代（1800–1949）", 1800, 1949), "contemporary": ("当代（1950 年起）", 1950, 9999)}
PERIOD_NOTICE = "时期按已知生卒年份区间交叠筛选，不代表思想活跃期；仅有一个年份时按该年，年代未知者不归入时期。"
RELATION_LABELS = {"teaching": "师承", "cooperation": "合作", "influence": "影响", "criticism": "批评",
                   "comparative_reading": "比较阅读", "other": "其他关系"}
FOLLOW_NOTICE = "关注此学者正式发布的档案内容；独立馆藏、学术关系与时间线的更新不计入本订阅。"


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _strings(value):
    return [row for row in value if isinstance(row, str)] if isinstance(value, list) else []


def _values(params, key):
    raw = params.getlist(key) if hasattr(params, "getlist") else params.get(key, [])
    raw = raw if isinstance(raw, (list, tuple)) else [raw]
    result = list(dict.fromkeys(value.strip() for item in raw for value in str(item).split(",") if value.strip()))
    if len(result) > 30:
        raise ValidationError({key: "一次最多选择 30 项。"})
    return result


def _choice(params, key, choices, default):
    value = str(params.get(key, default)).strip()
    if value not in choices:
        raise ValidationError({key: "筛选值无效。"})
    return value


def _paging(params):
    result = []
    for key, default, ceiling in (("page", 1, 100000), ("page_size", 12, 48)):
        value = str(params.get(key, default))
        if not value.isdecimal() or not 1 <= int(value) <= ceiling:
            raise ValidationError({key: f"请输入 1–{ceiling} 的整数。"})
        result.append(int(value))
    return result


def _page(rows, params, path, *, transform=None, section=None):
    page, size = _paging(params)
    if section and params.get("section", "overview") != section:
        page = 1
    count = rows.count() if hasattr(rows, "query") else len(rows)
    selected = list(rows[(page - 1) * size:page * size])
    selected = transform(selected) if transform else selected
    total = (count + size - 1) // size
    def href(number):
        pairs = [(key, val) for key in params for val in _values(params, key) if key not in {"page", "page_size", "section"}]
        pairs += [("page", str(number)), ("page_size", str(size))]
        if section:
            pairs.append(("section", section))
        return path + "?" + urlencode(pairs)
    return {"count": count, "page": page, "page_size": size, "total_pages": total,
            "next": href(page + 1) if page < total else None, "previous": href(page - 1) if page > 1 else None,
            "results": selected}


class SnapshotPersonMatch(Func):
    """Match a person and optional roles in the same activated contribution row."""
    output_field = BooleanField()

    def __init__(self, identifier, roles=(), *, whole_only=False):
        self.roles = tuple(roles)
        self.whole_only = whole_only
        super().__init__(F("active_catalog_revision__snapshot"), identifier)

    def as_sql(self, compiler, connection, **extra_context):
        from catalog.services.catalog_search import _rows_sql
        snapshot, params = compiler.compile(self.source_expressions[0])
        identifier, identifier_params = compiler.compile(self.source_expressions[1])
        rows, identity, _label, _author_only, _fields = _rows_sql(connection, snapshot, "author")
        role = "item.value->>'role'" if connection.vendor == "postgresql" else "json_extract(item.value, '$.role')"
        comparison = f"{identity} = CAST({identifier} AS text)" if connection.vendor == "postgresql" else f"replace({identity}, '-', '') = replace(CAST({identifier} AS text), '-', '')"
        if self.roles:
            comparison += f" AND {role} IN ({', '.join(['%s'] * len(self.roles))})"
        if self.whole_only:
            if connection.vendor == "postgresql":
                scope = "item.value->'scope'"
                whole = f"({scope} IS NULL OR {scope} IN ('null'::jsonb, '{{}}'::jsonb) OR (jsonb_typeof({scope}) = 'object' AND {scope}->>'kind' = 'edition' AND ({scope}->'chapters' IS NULL OR {scope}->'chapters' = 'null'::jsonb OR {scope}->'chapters' = '[]'::jsonb)))"
            else:
                scope = "json_extract(item.value, '$.scope')"
                whole = f"({scope} IS NULL OR {scope} = '{{}}' OR (json_type(item.value, '$.scope') = 'object' AND json_extract(item.value, '$.scope.kind') = 'edition' AND (json_extract(item.value, '$.scope.chapters') IS NULL OR json_extract(item.value, '$.scope.chapters') = '[]')))"
            comparison += f" AND {whole}"
        return f"EXISTS (SELECT 1 FROM {rows} WHERE {comparison})", [*params, *params, *identifier_params, *self.roles]


def scholar_editions(person_id, roles=(), *, whole_only=False):
    return public_editions().filter(SnapshotPersonMatch(Value(str(person_id)), roles, whole_only=whole_only))


def _base():
    editions = public_editions().filter(SnapshotPersonMatch(OuterRef("person_id"))).order_by()
    authored = public_editions().filter(SnapshotPersonMatch(OuterRef("person_id"), ("author",), whole_only=True)).order_by()
    def count(rows):
        return Coalesce(Subquery(rows.annotate(group=Value(1)).values("group").annotate(n=Count("work_id", distinct=True)).values("n")), 0)
    revision = EditorialRevision.objects.filter(target_type="scholar_profile", target_id=OuterRef("pk"), status="published").order_by("-revision")
    return public_scholar_queryset().select_related("person__portrait_rendition").prefetch_related(Prefetch(
        "person__name_variants", queryset=PersonNameVariant.objects.filter(is_verified=True, displayable=True,
            source_kind__in=FORMAL_PERSON_VARIANT_SOURCES).order_by("normalized_name", "pk"), to_attr="public_variants",
    )).annotate(public_work_count=count(editions), authored_work_count=count(authored),
        public_snapshot=Subquery(revision.values("materialized_preview")[:1]),
    ).annotate(public_name=Coalesce(KeyTextTransform("preferred_name", KeyTransform("person", "public_snapshot")), F("person__preferred_name"), output_field=CharField()),
        public_original=Coalesce(KeyTextTransform("original_name", KeyTransform("person", "public_snapshot")), F("person__original_name"), output_field=CharField()),
        public_description=Coalesce(KeyTextTransform("short_description", "public_snapshot"), F("short_description"), output_field=CharField()),
        public_concerns=Coalesce(KeyTextTransform("key_concerns", "public_snapshot"), Cast("key_concerns", CharField()), output_field=CharField()),
        public_birth=Case(When(public_snapshot__isnull=False, then=Cast(NullIf(KeyTextTransform("birth_year", KeyTransform("person", "public_snapshot")), Value("null")), IntegerField())), default=F("person__birth_year"), output_field=IntegerField()),
        public_death=Case(When(public_snapshot__isnull=False, then=Cast(NullIf(KeyTextTransform("death_year", KeyTransform("person", "public_snapshot")), Value("null")), IntegerField())), default=F("person__death_year"), output_field=IntegerField()))


def _formal_profile(profile, snapshot):
    from copy import copy
    result, person = copy(profile), copy(profile.person)
    result.person = person
    for key in ("slug", "short_description", "affiliations", "key_concerns", "curation"):
        if key in snapshot:
            setattr(result, key, deepcopy(snapshot[key]))
    for key in ("preferred_name", "original_name", "birth_year", "death_year", "biography"):
        if key in (snapshot.get("person") or {}):
            setattr(person, key, snapshot["person"][key])
    if "portrait_selection" in snapshot:
        selection = snapshot.get("portrait_selection") or {}
        exact = str(selection.get("person_id")) == str(person.pk)
        person.portrait_rendition_id = selection.get("rendition_id") if exact else None
        # Legacy files have no immutable rendition: a changed live file cannot stand in for the published one.
        person.portrait = person.portrait.name if exact and selection.get("legacy_path") == person.portrait.name else ""
    person._public_portrait_bound = True
    return result


def _link(row, kind):
    name = row.canonical_name_zh if kind == "school" else row.name
    path = "theories/nodes" if kind == "school" else "topics" if kind == "topic" else "subdisciplines"
    return {"id": str(row.pk), "slug": row.slug, "name": name, "href": f"/{path}/{row.slug}"}


def _cards(rows, query=""):
    from catalog.serializers import PersonCompactSerializer
    rows = list(rows)
    identifiers = [row.person_id for row in rows]
    fields, schools = {}, {}
    for relation in PersonTopicRelation.objects.filter(person_id__in=identifiers, review_status="approved", topic__editorial_status="published").select_related("topic"):
        fields.setdefault(relation.person_id, []).append(_link(relation.topic, "topic"))
    for relation in PersonSubdisciplineRelation.objects.filter(person_id__in=identifiers, review_status="approved", subdiscipline__editorial_status="published").select_related("subdiscipline"):
        fields.setdefault(relation.person_id, []).append(_link(relation.subdiscipline, "subdiscipline"))
    for relation in PersonNodeRelation.objects.filter(person_id__in=identifiers, status="published", node__status="published", node__node_type="theory_tradition").select_related("node"):
        schools.setdefault(relation.person_id, []).append(_link(relation.node, "school"))
    result = []
    for profile in rows:
        profile = _formal_profile(profile, getattr(profile, "public_snapshot", None) or {})
        person, curation = profile.person, profile.curation if isinstance(profile.curation, dict) else {}
        aliases = [row.name for row in getattr(person, "public_variants", [])]
        media = PersonCompactSerializer(person).data
        result.append({"id": str(profile.pk), "person_id": str(person.pk), "slug": profile.slug, "href": f"/scholars/{profile.slug}",
            "person": {key: media[key] for key in ("id", "preferred_name", "original_name", "birth_year", "death_year", "biography", "portrait", "portrait_media")},
            "short_description": profile.short_description, "affiliations": _strings(profile.affiliations), "key_concerns": _strings(profile.key_concerns),
            "nationalities": _strings(curation.get("nationalities")), "occupations": _strings(curation.get("occupations")),
            "matched_alias": next((name for name in aliases if query and query.casefold() in name.casefold()), ""),
            "fields": fields.get(person.pk, []), "schools": schools.get(person.pk, []),
            "work_count": profile.public_work_count, "authored_work_count": profile.authored_work_count,
            "profile_state": "available" if person.biography.strip() or profile.short_description.strip() else "sparse"})
        result[-1]["person"]["aliases"] = aliases
    return result


def _public_revision(profile):
    revision = EditorialRevision.objects.filter(target_type="scholar_profile", target_id=profile.pk, status="published").order_by("-revision").first()
    if revision:
        return {"token": f"{revision.pk}:{revision.revision}", "id": str(revision.pk), "number": revision.revision,
                "published_at": revision.published_at.isoformat() if revision.published_at else None, "change_note": revision.change_note}
    values = {"profile": str(profile.pk), "name": profile.person.preferred_name, "original_name": profile.person.original_name,
        "birth": profile.person.birth_year, "death": profile.person.death_year, "biography": profile.person.biography,
        "description": profile.short_description, "affiliations": profile.affiliations, "concerns": profile.key_concerns,
        "curation": profile.curation, "portrait": str(profile.person.portrait_rendition_id or profile.person.portrait.name or "")}
    token = sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return {"token": f"legacy:{token}", "id": None, "number": None, "published_at": None, "change_note": "旧正式档案；读取不创建版本。"}


def scholar_follow_summary(profile_id):
    """Lightweight follow resolver: no works, excerpt text or relation projection."""
    if not _uuid(profile_id):
        return None
    profile = public_scholar_queryset().filter(pk=profile_id).first()
    if profile is None:
        return None
    from catalog.serializers import PersonCompactSerializer
    revision = _public_revision(profile)
    if revision["id"]:
        published = EditorialRevision.objects.only("materialized_preview").get(pk=revision["id"])
        profile = _formal_profile(profile, published.materialized_preview)
    return {"profile_id": str(profile.pk), "person_id": str(profile.person_id), "slug": profile.slug,
        "name": profile.person.preferred_name, "portrait_url": PersonCompactSerializer().get_portrait(profile.person),
        "portrait_media": PersonCompactSerializer().get_portrait_media(profile.person),
        "public_revision": revision["token"], "updated_at": revision["published_at"], "scope_notice": FOLLOW_NOTICE}


def _period_q(value):
    _label, start, end = PERIODS[value]
    return Q(period_start__lte=end, period_end__gte=start)


def scholar_directory(params, *, request=None):
    params = params or {}
    _paging(params)
    query = str(params.get("q", params.get("search", ""))).strip()
    if len(query) > 500:
        raise ValidationError({"q": "搜索内容最多 500 字。"})
    fields, periods, schools = (_values(params, key) for key in ("field", "period", "school"))
    if set(periods) - PERIODS.keys():
        raise ValidationError({"period": "历史时期无效。"})
    sort = _choice(params, "sort", ("relevance", "name", "birth", "works"), "relevance")
    rows = _base().annotate(period_start=Coalesce("public_birth", "public_death"), period_end=Coalesce("public_death", "public_birth"))
    if query:
        aliases = PersonNameVariant.objects.filter(person_id=OuterRef("person_id"), is_verified=True,
            source_kind__in=FORMAL_PERSON_VARIANT_SOURCES, name__icontains=query)
        rows = rows.alias(alias_match=Exists(aliases)).filter(
            Q(public_name__icontains=query) | Q(public_original__icontains=query)
            | Q(public_description__icontains=query) | Q(public_concerns__icontains=query) | Q(alias_match=True)
            | Q(person__topic_relations__review_status="approved", person__topic_relations__topic__editorial_status="published", person__topic_relations__topic__name__icontains=query)
        ).annotate(search_rank=Case(When(Q(public_name__iexact=query) | Q(public_original__iexact=query), then=Value(0)), When(alias_match=True, then=Value(1)), default=Value(2), output_field=IntegerField()))
    if fields:
        condition = Q(pk__in=[])
        for field in fields:
            kind, _, key = field.partition(":")
            if kind not in {"topic", "subdiscipline"} or not _uuid(key):
                raise ValidationError({"field": "研究领域须为当前领域选项。"})
            prefix = "person__topic_relations" if kind == "topic" else "person__subdiscipline_relations"
            condition |= Q(**{prefix + "__review_status": "approved", prefix + f"__{kind}_id": key, prefix + f"__{kind}__editorial_status": "published"})
        rows = rows.filter(condition)
    if periods:
        condition = Q(pk__in=[])
        for value in periods:
            condition |= _period_q(value)
        rows = rows.filter(condition)
    if schools:
        if any(not _uuid(value) for value in schools):
            raise ValidationError({"school": "理论流派标识无效。"})
        rows = rows.filter(person__node_relations__status="published", person__node_relations__node__status="published",
            person__node_relations__node__node_type="theory_tradition", person__node_relations__node_id__in=schools)
    rows = rows.distinct()
    order = {"name": ("public_name", "pk"), "birth": ("period_start", "public_name", "pk"),
        "works": ("-public_work_count", "public_name", "pk"), "relevance": (("search_rank",) if query else ()) + ("public_name", "pk")}[sort]
    result = _page(rows.order_by(*order), params, "/api/catalog/scholars/", transform=lambda data: _cards(data, query))
    people = rows.order_by().values("person_id")
    field_facets = []
    for model, kind in ((PersonTopicRelation, "topic"), (PersonSubdisciplineRelation, "subdiscipline")):
        facets = model.objects.filter(person_id__in=people, review_status="approved", **{kind + "__editorial_status": "published"}).values(kind + "_id", kind + "__name").annotate(count=Count("person_id", distinct=True)).order_by(kind + "__name")
        field_facets.extend({"value": f"{kind}:{row[kind + '_id']}", "label": row[kind + "__name"], "count": row["count"]} for row in facets)
    school_facets = PersonNodeRelation.objects.filter(person_id__in=people, status="published", node__status="published", node__node_type="theory_tradition").values("node_id", "node__canonical_name_zh").annotate(count=Count("person_id", distinct=True)).order_by("node__canonical_name_zh")
    result.update(query=query, filters={"field": fields, "period": periods, "school": schools, "sort": sort}, period_notice=PERIOD_NOTICE,
        facets={"fields": field_facets, "periods": [{"value": key, "label": values[0], "count": rows.filter(_period_q(key)).count()} for key, values in PERIODS.items()],
                "schools": [{"value": str(row["node_id"]), "label": row["node__canonical_name_zh"], "count": row["count"]} for row in school_facets]},
        recommendations=_recommendations(), curated_topics=_curated_topics(), related_topics=[_link(row, "topic") for row in Topic.objects.filter(editorial_status="published", person_relations__person_id__in=people, person_relations__review_status="approved").distinct().order_by("-curation_level", "name", "pk")[:8]])
    return result


def _recommendations():
    from catalog.services.recommendations import current_recommendations
    snapshot = current_recommendations(read_only=True).get("home_scholars")
    result = {"revision_id": str(snapshot.pk) if snapshot else None, "source": snapshot.source if snapshot else "", "title": "学者推荐", "results": []}
    if snapshot:
        ids = list(snapshot.items.filter(scholar__isnull=False).order_by("position", "pk").values_list("scholar_id", flat=True)[:48])
        cards = {row["id"]: row for row in _cards(_base().filter(pk__in=ids))}
        result["results"] = [cards[str(key)] for key in ids if str(key) in cards]
    return result


def _curated_topics():
    from catalog.services.recommendations import current_recommendations
    snapshot = current_recommendations(read_only=True).get("home_topics")
    if snapshot is None or snapshot.source != "manual":
        return []
    return [{"id": str(row.topic_id), "slug": row.topic.slug, "title": row.topic.name,
        "summary": row.reason or row.topic.description, "href": f"/topics/{row.topic.slug}",
        "image_url": row.image_override.url if row.image_override else row.topic.hero_image.url if row.topic.hero_image else ""}
        for row in snapshot.items.filter(topic__editorial_status="published").select_related("topic").order_by("position", "pk")[:8]]


def selectable_works(profile, kind):
    rows = scholar_editions(profile.person_id) if kind == "essential" else public_editions()
    primary = rows.filter(work_id=OuterRef("work_id")).order_by("-is_primary", "pk").values("pk")[:1]
    return rows.filter(pk=Subquery(primary)).order_by("work_id", "pk")


def _work_rows(editions, profile):
    from catalog.services.contribution_scope import public_contribution_scope
    result = []
    curation = profile.curation if isinstance(profile.curation, dict) else {}
    essential = set(_strings(curation.get("essential_work_ids")))
    recommended = set(_strings(curation.get("recommended_work_ids")))
    reasons = curation.get("work_recommendations", {})
    reasons = reasons if isinstance(reasons, dict) else {}
    labels = dict(Contribution.Role.choices)
    for edition in editions:
        revision = edition.active_catalog_revision
        snapshot = revision.snapshot or {}
        work, version = snapshot.get("work") or {}, snapshot.get("edition") or {}
        reader = revision.reader_asset
        readable = bool(revision.fulltext_ready and reader and revision.document_revision_id
            and revision.document_revision.is_active and revision.document_revision.asset_id == reader.pk
            and revision.document_revision.source_checksum == reader.sha256
            and reader.edition_id == edition.pk and reader.kind == "normalized" and reader.status == "ready"
            and reader.validation_status == "valid" and reader.access_status in {"public", "inherit"} and reader.file)
        contributions = []
        for item in snapshot.get("contributions", []):
            if not isinstance(item, dict):
                continue
            person = item.get("person") or {}
            identifier = _uuid(item.get("person_id") or person.get("id"))
            if not identifier:
                continue
            role = item.get("role", "other")
            contributions.append({"person_id": identifier, "name": person.get("preferred_name") or item.get("name", ""),
                "role": role, "role_label": labels.get(role, "其他贡献者"), "scope": public_contribution_scope(edition, item.get("scope"))})
        roles = list(dict.fromkeys(item["role"] for item in contributions if item["person_id"] == str(profile.person_id)))
        cover = work.get("cover_media") or {}
        cover_url = f"/api/catalog/works/{edition.work_id}/cover/?edition_id={edition.pk}" if work.get("cover") or cover else ""
        if cover_url and cover.get("primary_rendition_id"):
            cover_url += f"&rendition={cover['primary_rendition_id']}"
        result.append({"id": str(edition.work_id), "edition_id": str(edition.pk), "catalog_revision_id": str(revision.pk),
            "title": str(work.get("title") or ""), "original_title": str(work.get("original_title") or ""),
            "href": f"/works/{edition.public_slug}", "cover_url": cover_url, "cover_media": cover or None, "document_type": work.get("document_type", ""),
            "language": work.get("language", ""), "publication_year": version.get("publication_year"), "version_label": version.get("version_label", ""),
            "roles": roles, "role_labels": [labels.get(role, "其他贡献者") for role in roles], "contributions": contributions,
            "source_status": "available" if readable else "no_fulltext", "reader_href": f"/reader/{reader.pk}?revision={revision.document_revision_id}" if readable else "",
            "is_essential": str(edition.work_id) in essential, "is_recommended": str(edition.work_id) in recommended,
            "recommendation_reason": str(reasons.get(str(edition.work_id), ""))[:2000] if str(edition.work_id) in essential | recommended else ""})
    return result


def _knowledge(profile, editions):
    from catalog.services.theory_graph import _SnapshotEntity
    direct = PersonNodeRelation.objects.filter(person_id=profile.person_id, status="published", node__status="published")
    # Work associations are material links, never a claim that this person coined a concept.
    authored = scholar_editions(profile.person_id, ("author",), whole_only=True).filter(_SnapshotEntity("knowledge_node", OuterRef("pk")))
    return KnowledgeNode.objects.filter(status="published").alias(in_authored_material=Exists(authored)).filter(Q(pk__in=direct.values("node_id")) | Q(in_authored_material=True)).distinct()


class SnapshotPathMember(Func):
    """Narrow candidates by pinned identities; the public projection decides membership."""
    output_field = BooleanField()

    def as_sql(self, compiler, connection, **extra_context):
        (snapshot, sp), (editions, ep), (nodes, np) = [compiler.compile(expression) for expression in self.source_expressions]
        if connection.vendor == "postgresql":
            groups = f"jsonb_array_elements(CASE WHEN jsonb_typeof({snapshot}->'stage_groups') = 'array' THEN {snapshot}->'stage_groups' ELSE '[]'::jsonb END) stage(value)"
            items = "jsonb_array_elements(CASE WHEN jsonb_typeof(stage.value->'items') = 'array' THEN stage.value->'items' ELSE '[]'::jsonb END) item(value)"
            edition, node = "item.value->>'edition'", "item.value->>'node'"
        elif connection.vendor == "sqlite":
            groups = f"json_each(CASE WHEN json_type({snapshot}, '$.stage_groups') = 'array' THEN json_extract({snapshot}, '$.stage_groups') ELSE '[]' END) stage"
            items = "json_each(CASE WHEN json_type(stage.value, '$.items') = 'array' THEN json_extract(stage.value, '$.items') ELSE '[]' END) item"
            edition, node = "json_extract(item.value, '$.edition')", "json_extract(item.value, '$.node')"
        else:
            raise NotImplementedError("Scholar path membership requires PostgreSQL or SQLite JSON support.")
        return f"EXISTS (SELECT 1 FROM {groups}, {items} WHERE replace({edition}, '-', '') IN {editions} OR replace({node}, '-', '') IN {nodes})", [*sp, *sp, *ep, *np]


def _related_path_candidates(editions, nodes, explicit):
    latest = EditorialRevision.objects.filter(target_type="reading_path", target_id=OuterRef("pk"), status="published",
        materialized_preview__status="published").order_by("-revision")
    def compact(rows):
        return rows.order_by().annotate(compact_id=Replace(Cast("pk", CharField()), Value("-"), Value(""))).values("compact_id")
    return ReadingPath.objects.filter(status="published").annotate(public_snapshot=Subquery(latest.values("materialized_preview")[:1]),
        public_title=Coalesce(KeyTextTransform("title", "public_snapshot"), F("title"), output_field=CharField())).alias(
        snapshot_member=SnapshotPathMember(F("public_snapshot"), Subquery(compact(editions)), Subquery(compact(nodes))),
    ).filter(Q(pk__in=explicit) | Q(snapshot_member=True) | (Q(public_snapshot__isnull=True) &
        (Q(items__work_id__in=editions.values("work_id")) | Q(items__node__in=nodes)))).distinct().order_by("sort_order", "public_title", "pk")


def _related_path_page(profile, editions, nodes, params, path, request):
    from catalog.services.public_reading_paths import public_reading_path_snapshots
    curation = profile.curation if isinstance(profile.curation, dict) else {}
    explicit = {value for value in _strings(curation.get("reading_path_ids")) if _uuid(value)}
    edition_ids, node_ids = ({str(value) for value in rows.values_list("pk", flat=True)} for rows in (editions, nodes))
    page, size = _paging(params)
    if params.get("section", "overview") != "paths":
        page = 1
    identifiers, selected, batch = [], [], []
    def project(rows):
        for item in public_reading_path_snapshots(rows, request=request):
            related = item["id"] in explicit or any(material["source_status"] not in {"unavailable", "withdrawn"} and
                (material["node_id"] in node_ids or material["edition_id"] in edition_ids) for material in item["items"])
            if related:
                identifiers.append(item["id"])
                if (page - 1) * size < len(identifiers) <= page * size:
                    selected.append(item)
    # Batch projection is necessary for legacy unpinned items and present-day access checks.
    # Keep only page DTOs; counts never treat the SQL candidate set as confirmed membership.
    for candidate in _related_path_candidates(editions, nodes, explicit).iterator(chunk_size=48):
        batch.append(candidate)
        if len(batch) == 48:
            project(batch)
            batch = []
    if batch:
        project(batch)
    output = _page(identifiers, params, path, section="paths")
    output["results"] = selected
    return output


def _knowledge_rows(nodes, profile):
    from catalog.theory_serializers import _public_evidence_queryset
    nodes = list(nodes)
    ids = [row.pk for row in nodes]
    links = {row.node_id: row for row in PersonNodeRelation.objects.filter(person_id=profile.person_id, node_id__in=ids, status="published")}
    page = Page.objects.filter(asset_id=OuterRef("file_id"), index=OuterRef("page_number")).alias(
        quote_position=StrIndex("text", OuterRef("quote"))).filter(quote_position__gt=0)
    evidence = _public_evidence_queryset({}).filter(Exists(page),
        file__edition__active_catalog_revision__document_revision__is_active=True,
        file__edition__active_catalog_revision__document_revision__source_checksum=F("file__sha256"),
    ).exclude(file__sha256="").exclude(quote__regex=r"^\s*$").annotate(source_node=Coalesce("node_id", "work_node_relation__node_id")).filter(source_node__in=ids)
    sources = dict(evidence.values("source_node").annotate(n=Count("pk", distinct=True)).values_list("source_node", "n"))
    people = dict(PersonNodeRelation.objects.filter(node_id__in=ids, status="published", person_id__in=public_scholar_queryset().values("person_id")).values("node_id").annotate(n=Count("person_id", distinct=True)).values_list("node_id", "n"))
    return [{**_link(row, "school"), "node_type": row.node_type, "summary": row.summary,
        "relation_label": links[row.pk].relation_label if row.pk in links else "相关著作中的知识条目",
        "relation_source": "person_relation" if row.pk in links else "published_work_relation",
        "source_count": sources.get(row.pk, 0), "scholar_count": people.get(row.pk, 0)} for row in nodes]


def public_scholar_relations():
    """Use the formal snapshot's exact owning row and publicly visible endpoints."""
    public = public_scholar_queryset().values("pk")
    rows = ScholarRelation.objects.filter(status="published", active_revision__status="published",
        active_revision__target_type="scholar_relation", active_revision__target_id=F("pk"),
        source_scholar_id__in=public, target_scholar_id__in=public).select_related("active_revision")
    for side in ("source", "target"):
        rows = rows.alias(**{f"{side}_snapshot": Replace(KeyTextTransform(f"{side}_scholar", "active_revision__materialized_preview"), Value("-"), Value(""), output_field=CharField()),
            f"{side}_identity": Replace(Cast(f"{side}_scholar_id", CharField()), Value("-"), Value(""))}).filter(**{f"{side}_snapshot": F(f"{side}_identity")})
    return rows


def _relation_rows(rows):
    from catalog.services.shared_curation import relation_payload
    result = []
    for row in rows:
        value = relation_payload(row, public=True)
        if value:
            result.append({key: value.get(key, "") for key in ("id", "source_scholar", "target_scholar", "source_name", "target_name", "source_slug", "target_slug", "relation_type", "direction", "summary", "source", "status")})
            result[-1]["relation_label"] = RELATION_LABELS.get(value["relation_type"], value["relation_type"])
            result[-1]["source_material"] = value.get("source_material")
    return result


def _candidate_relations(profile, params, request):
    allowed = all(has_capability(getattr(request, "user", None), capability) for capability in (Capability.VIEW_EVIDENCE, Capability.EDIT_DRAFT_AUTHORITY))
    requested = _choice(params, "include_candidates", ("", "false", "0", "true", "1"), "") in {"true", "1"}
    access = {"allowed": allowed, "requested": requested, "review_href": f"/admin/scholars/{profile.pk}/relations" if allowed else "",
        "notice": "待审关系仅供具有原文查看及知识编辑权限的编辑核对；不计入正式关系。"}
    if requested and not allowed:
        raise PermissionDenied("查看未确认学术关系需要原文查看和知识编辑权限。")
    if not requested:
        return access, None
    # Latest draft per relation; a changed draft endpoint never inherits the old row's identity.
    latest = EditorialRevision.objects.filter(target_type="scholar_relation", target_id=OuterRef("target_id"), status="draft").order_by("-revision").values("pk")[:1]
    rows = EditorialRevision.objects.filter(target_type="scholar_relation", status="draft", pk=Subquery(latest),
        target_id__in=ScholarRelation.objects.filter(status="draft").values("pk")).filter(
            Q(materialized_preview__source_scholar=str(profile.pk)) | Q(materialized_preview__target_scholar=str(profile.pk)))
    public = {}
    def project(revisions):
        keys = {identifier for row in revisions for side in ("source", "target") if (identifier := _uuid(row.materialized_preview.get(side + "_scholar")))}
        public.update({str(row.pk): row for row in public_scholar_queryset().filter(pk__in=keys)})
        output = []
        for row in revisions:
            data = row.materialized_preview
            ends = [public.get(data.get(side + "_scholar")) for side in ("source", "target")]
            if any(value is None for value in ends):
                continue
            output.append({"id": str(row.target_id), "source_scholar": str(ends[0].pk), "target_scholar": str(ends[1].pk),
                "source_name": ends[0].person.preferred_name, "target_name": ends[1].person.preferred_name,
                "source_slug": ends[0].slug, "target_slug": ends[1].slug, "relation_type": data.get("relation_type", "other"),
                "relation_label": RELATION_LABELS.get(data.get("relation_type"), "其他关系"), "direction": data.get("direction", "directed"),
                "summary": data.get("summary", ""), "source": data.get("source", ""), "status": "draft"})
        return output
    # Restrict both JSON endpoints before counting so hidden people never contribute a count.
    for side in ("source", "target"):
        rows = rows.alias(**{side + "_public_id": Replace(KeyTextTransform(side + "_scholar", "materialized_preview"), Value("-"), Value(""), output_field=CharField())}).filter(
            **{side + "_public_id__in": public_scholar_queryset().annotate(compact_id=Replace(Cast("pk", CharField()), Value("-"), Value(""))).values("compact_id")})
    return access, _page(rows.order_by("-updated_at", "pk"), params, f"/api/catalog/scholars/{profile.slug}/", transform=project, section="relations")


def _sources(profile):
    curation = profile.curation if isinstance(profile.curation, dict) else {}
    output = []
    for row in curation.get("profile_sources", []) if isinstance(curation.get("profile_sources"), list) else []:
        try:
            clean = validate_scholar_curation({"profile_sources": [row]})["profile_sources"][0]
        except ValidationError:
            continue
        output.append(clean)
    return output


def _evidence(profile, *, request=None, preview=False):
    from catalog.models import EvidenceCuration
    from catalog.services.shared_curation import curation_payload, preview_published_curation, sources
    owner = EvidenceCuration.objects.filter(object_type="scholar", object_id=profile.pk, active_revision__status="published",
        active_revision__target_type="evidence_curation", active_revision__target_id=F("pk")).first()
    if owner is None:
        return []
    payload = (preview_published_curation("scholar", profile.pk, request=request) if preview
               else curation_payload("scholar", profile.pk, public=True))
    items = payload["items"]
    current = {kind: {str(row.pk): row for row in sources(kind, public=True).filter(pk__in=[item["source_id"] for item in items if item["source_type"] == kind])}
               for kind in ("span", "passage")}
    output = []
    for item in items:
        row = current[item["source_type"]].get(item["source_id"])
        text = row.original_text if row and item["source_type"] == "span" else row.text if row else ""
        if row is None or not text or (row.page.text or "")[row.start_offset:row.end_offset] != text:
            continue
        item = deepcopy(item)
        source = item["source"]
        source["reader_url"] = f"/reader/{source['asset_id']}?page={source['page_start']}&revision={source['document_revision_id']}"
        output.append(item)
    return output


def public_scholar_detail(slug, params=None, *, request=None, preview_profile=None):
    params = params or {}
    _paging(params)
    section = _choice(params, "section", SECTIONS, "overview")
    profile = preview_profile or get_object_or_404(_base(), slug=slug)
    if preview_profile is None:
        profile = _formal_profile(profile, profile.public_snapshot or {})
    roles, kinds = _values(params, "role"), _values(params, "relation_type")
    if set(roles) - set(Contribution.Role.values) or set(kinds) - RELATION_LABELS.keys():
        raise ValidationError("作品职责或学术关系类型无效。")
    direction = _choice(params, "relation_direction", ("all", "incoming", "outgoing"), "all")
    access, candidates = _candidate_relations(profile, params, request)
    result = _cards([profile])[0]
    from catalog.services.scholar_prose import bound_profile_prose
    result["profile_prose"] = bound_profile_prose(profile.curation, profile.short_description, profile.person.biography)
    path = f"/api/catalog/scholars/{profile.slug}/"
    editions = scholar_editions(profile.person_id)
    curation = profile.curation if isinstance(profile.curation, dict) else {}
    essential = [key for key in _strings(curation.get("essential_work_ids"))[:100] if _uuid(key)]
    works = scholar_editions(profile.person_id, roles)
    if essential:
        works = works.alias(editorial_order=Case(*[When(work_id=key, then=Value(index)) for index, key in enumerate(essential)], default=Value(len(essential)), output_field=IntegerField())).order_by("editorial_order", "-is_primary", "work_id", "pk")
    else:
        works = works.order_by("-is_primary", "work_id", "pk")
    result["works"] = _page(works, params, path, section="works", transform=lambda rows: _work_rows(rows, profile))
    nodes = _knowledge(profile, editions).order_by("sort_order", "canonical_name_zh", "pk")
    for name, types in (("concepts", ("concept",)), ("questions", ("research_problem", "debate"))):
        result[name] = _page(nodes.filter(node_type__in=types), params, path, section=name, transform=lambda rows: _knowledge_rows(rows, profile))
    topics = Topic.objects.filter(editorial_status="published", person_relations__person=profile.person, person_relations__review_status="approved").distinct().order_by("-curation_level", "name", "pk")
    result["topics"] = _page(topics, params, path, section="topics", transform=lambda rows: [{**_link(row, "topic"), "description": row.description} for row in rows])
    curation = profile.curation if isinstance(profile.curation, dict) else {}
    recommended = [key for key in _strings(curation.get("recommended_work_ids"))[:24] if _uuid(key)]
    recommended_rows = {row["id"]: row for row in _work_rows(selectable_works(profile, "recommended").filter(work_id__in=recommended), profile)}
    result["recommended_works"] = [recommended_rows[key] for key in recommended if key in recommended_rows]
    result["paths"] = _related_path_page(profile, editions, nodes, params, path, request)
    from catalog.services.timeline_publication import public_events, scholar_match, ordered
    from catalog.theory_serializers import NormalizedTimelineEventSerializer
    events = ordered(public_events().filter(scholar_match(public_scholar_queryset().filter(pk=profile.pk))).distinct(), "asc")
    result["timeline"] = _page(events, params, path, section="timeline", transform=lambda rows: list(NormalizedTimelineEventSerializer(rows, many=True, context={"request": request}).data))
    relations = public_scholar_relations().filter(Q(source_scholar=profile) | Q(target_scholar=profile))
    all_relations = relations
    if kinds:
        relations = relations.filter(active_revision__materialized_preview__relation_type__in=kinds)
    if direction != "all":
        relations = relations.filter(**{("target_scholar" if direction == "incoming" else "source_scholar"): profile})
    result["relations"] = _page(relations.order_by("-updated_at", "pk"), params, path, section="relations", transform=_relation_rows)
    evidence = _evidence(profile, request=request, preview=preview_profile is not None)
    result["sources"] = _page(_sources(profile), params, path, section="sources")
    result["evidence"] = _page(evidence, params, path, section="evidence")
    result["featured_quote"] = next((row for row in evidence if row["id"] == curation.get("featured_source_id")), None)
    names = [value for value in (profile.person.preferred_name, profile.person.original_name) if value]
    same = _base().filter(Q(public_name__in=names) | Q(public_original__in=names)
        | Q(person__name_variants__name__in=names, person__name_variants__is_verified=True, person__name_variants__displayable=True,
            person__name_variants__source_kind__in=FORMAL_PERSON_VARIANT_SOURCES)).exclude(pk=profile.pk).distinct().order_by("public_name", "pk")
    result.update(public_revision=_public_revision(profile), period_notice=PERIOD_NOTICE,
        graph_href=f"/theories/graph?center_kind=scholar&center={profile.pk}",
        research_href="/explore?" + urlencode({"mode": "ask", "context": "scholars", "id": str(profile.person_id)}),
        disambiguation=_cards(same[:8]), candidate_access=access, candidate_relations=candidates,
        filters={"section": section, "role": roles, "relation_type": kinds, "relation_direction": direction},
        counts={name: result[name]["count"] for name in SECTIONS if name != "overview"})
    # There are nine fixed roles; each count is the number of exact public editions, never live metadata.
    result["facets"] = {"roles": [{"value": role, "label": label, "count": scholar_editions(profile.person_id, (role,)).count()} for role, label in Contribution.Role.choices],
        "relation_types": [{"value": row["active_revision__materialized_preview__relation_type"],
            "label": RELATION_LABELS.get(row["active_revision__materialized_preview__relation_type"], "其他关系"), "count": row["count"]}
            for row in all_relations.values("active_revision__materialized_preview__relation_type").annotate(count=Count("pk")).order_by("active_revision__materialized_preview__relation_type")]}
    return result


def validate_scholar_curation(value, profile=None):
    """Validate only added public fields; preserve the existing curation schema."""
    if not isinstance(value, dict):
        raise ValidationError({"curation": "策划内容须为对象。"})
    result = deepcopy(value)
    if "biographical_materials" in result:
        from catalog.services.scholar_media import validate_biographical_materials
        result["biographical_materials"] = validate_biographical_materials(result["biographical_materials"])
    if "profile_prose" in result:
        from catalog.services.scholar_prose import normalize_profile_prose
        result["profile_prose"] = normalize_profile_prose(result["profile_prose"])
    for key, limit in (("essential_work_ids", 100), ("recommended_work_ids", 24)):
        if key not in result:
            continue
        rows = result[key]
        if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(row, str) or not _uuid(row) for row in rows) or len(set(rows)) != len(rows):
            raise ValidationError({key: f"请选择最多 {limit} 部不同的馆藏作品。"})
        result[key] = [_uuid(row) for row in rows]
        if Work.objects.filter(pk__in=result[key]).count() != len(rows):
            raise ValidationError({key: "包含已不存在的作品，请核对原选择。"})
        previous = profile.curation if profile is not None and isinstance(profile.curation, dict) else {}
        added = set(result[key]) - set(_strings(previous.get(key)))
        if added:
            if profile is None:
                raise ValidationError({key: "请先建立学者草稿，再从馆藏选书。"})
            eligible = selectable_works(profile, "essential" if key == "essential_work_ids" else "recommended")
            if eligible.filter(work_id__in=added).count() != len(added):
                raise ValidationError({key: "新增作品当前不满足公开条件或人物贡献要求，请重新从馆藏选择。"})
    if "work_recommendations" in result:
        reasons = result["work_recommendations"]
        selected = set(result.get("essential_work_ids", [])) | set(result.get("recommended_work_ids", []))
        if not isinstance(reasons, dict) or len(reasons) > 124 or any(key not in selected or not isinstance(reason, str) or len(reason) > 2000 for key, reason in reasons.items()):
            raise ValidationError({"work_recommendations": "推荐理由须对应已选作品，每项最多 2000 字。"})
    for key in ("nationalities", "occupations"):
        if key in result and (not isinstance(result[key], list) or len(result[key]) > 20 or any(not isinstance(row, str) or not row.strip() or len(row) > 120 for row in result[key])):
            raise ValidationError({key: "最多 20 项，每项须为 1–120 字。"})
    if "profile_sources" in result:
        rows = result["profile_sources"]
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValidationError({"profile_sources": "资料来源最多 100 条。"})
        clean, seen = [], set()
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"id", "title", "url", "fields", "note"}:
                raise ValidationError({"profile_sources": "资料来源包含不支持字段。"})
            identifier = _uuid(row.get("id"))
            title, url, note = row.get("title", ""), row.get("url", ""), row.get("note", "")
            fields = row.get("fields", [])
            if not identifier or identifier in seen or not isinstance(title, str) or not 1 <= len(title.strip()) <= 500:
                raise ValidationError({"profile_sources": "每条来源须有唯一 UUID 和 1–500 字题名。"})
            if not isinstance(note, str) or len(note) > 2000 or not isinstance(url, str) or len(url) > 2000:
                raise ValidationError({"profile_sources": "来源网址或说明过长。"})
            if url:
                try:
                    URLValidator(schemes=("https", "http"))(url)
                    if urlsplit(url).username or urlsplit(url).password:
                        raise ModelValidationError("credentials")
                except (ModelValidationError, ValueError):
                    raise ValidationError({"profile_sources": "资料来源须为不含账户凭据的 HTTP(S) 网址。"})
            if not isinstance(fields, list) or not fields or any(field not in PROFILE_SOURCE_FIELDS for field in fields):
                raise ValidationError({"profile_sources": "请选择来源支持的档案字段。"})
            seen.add(identifier)
            clean.append({"id": identifier, "title": title.strip(), "url": url, "fields": list(dict.fromkeys(fields)), "note": note})
        result["profile_sources"] = clean
    if "reading_path_ids" in result:
        rows = result["reading_path_ids"]
        if not isinstance(rows, list) or len(rows) > 100 or any(not _uuid(row) for row in rows):
            raise ValidationError({"reading_path_ids": "阅读路径须为最多 100 个有效标识。"})
        if ReadingPath.objects.filter(pk__in=rows).count() != len(set(rows)):
            raise ValidationError({"reading_path_ids": "包含不存在的阅读路径。"})
    featured = result.get("featured_source_id")
    if featured:
        if not _uuid(featured) or profile is None or not EvidenceCurationReference.objects.filter(pk=featured, curation__object_type="scholar", curation__object_id=profile.pk).exists():
            raise ValidationError({"featured_source_id": "请选择此学者已保存的准确原文引用。"})
    return result


def scholar_preview_overrides(params):
    """Bound the unsaved selector inputs; an explicit blank clears a choice."""
    if set(params) - {"featured_source_id", "reading_path_ids", "essential_work_ids", "recommended_work_ids"}:
        raise ValidationError("学者预览只接受原文引用、作品和阅读路径选择。")
    result = {}
    for key in params:
        values = params.getlist(key)
        if len(values) != 1:
            raise ValidationError({key: "同一预览参数只能提供一次。"})
        value = values[0]
        if key == "featured_source_id":
            if value and (len(value) != 36 or not _uuid(value)):
                raise ValidationError({key: "原文引用须为有效 UUID，或留空。"})
            result[key] = _uuid(value) if value else ""
        else:
            rows = value.split(",") if value else []
            if len(value) > 3699 or len(rows) > 100 or any(len(row) != 36 or not _uuid(row) for row in rows):
                raise ValidationError({key: "阅读路径须为最多 100 个逗号分隔的 UUID，或留空。"})
            result[key] = list(dict.fromkeys(_uuid(row) for row in rows))
    return result


def preview_scholar(target, *, snapshot=None, request=None, curation_overrides=None):
    """Protected materialized draft preview; no replacement by current public content."""
    from copy import copy
    from types import SimpleNamespace
    user = getattr(request, "user", None)
    if not has_capability(user, Capability.ACCESS_BACK_OFFICE):
        raise PermissionDenied("学者编辑预览需要后台访问权限。")
    profile, person = copy(target), copy(target.person)
    profile.person = person
    data = snapshot or {}
    for key in ("slug", "short_description", "affiliations", "key_concerns", "curation"):
        if key in data:
            setattr(profile, key, deepcopy(data[key]))
    if curation_overrides is not None:
        if set(curation_overrides) - {"featured_source_id", "reading_path_ids", "essential_work_ids", "recommended_work_ids"}:
            raise ValidationError("学者预览不接受其他策划字段覆盖。")
        selected = validate_scholar_curation(curation_overrides, profile)
        profile.curation = {**deepcopy(profile.curation or {}), **selected}
    person_values = data.get("person") or {}
    for key in ("preferred_name", "original_name", "birth_year", "death_year", "biography"):
        if key in person_values:
            setattr(person, key, person_values[key])
    person.public_variants = [SimpleNamespace(name=row["name"]) for row in person_values.get("name_variants", [])
        if isinstance(row, dict) and row.get("is_verified") and row.get("displayable") and row.get("source_kind") in FORMAL_PERSON_VARIANT_SOURCES]
    if "name_variants" not in person_values:
        person.public_variants = list(target.person.name_variants.filter(is_verified=True, displayable=True, source_kind__in=FORMAL_PERSON_VARIANT_SOURCES))
    profile.public_work_count = scholar_editions(profile.person_id).values("work_id").distinct().count()
    profile.authored_work_count = scholar_editions(profile.person_id, ("author",), whole_only=True).values("work_id").distinct().count()
    result = public_scholar_detail(profile.slug, request=request, preview_profile=profile)
    if "portrait_selection" in data:
        from catalog.services.scholar_media import portrait_media, validate_portrait_selection
        selection = validate_portrait_selection(target, data["portrait_selection"])
        media = portrait_media(target.person, selection=selection, private=True)
        result["person"]["portrait_media"] = media
        result["person"]["portrait"] = next((row["url"] for row in media["renditions"] if row["id"] == media["primary_rendition_id"]), "") if media else target.person.portrait.url if selection["legacy_path"] and target.person.portrait else ""
    result["public_revision"] = {"token": "preview", "id": None, "number": None, "published_at": None, "change_note": "编辑预览，仅供核对，尚未发布。"}
    return result
