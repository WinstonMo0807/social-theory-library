"""Exact catalog search over active edition snapshots; no draft or parallel index.

Filtering, version intersection, grouping, facets and pagination execute in SQL.
Only the requested Work page and its public editions are materialized in Python.
"""
from collections import defaultdict

from django.core.exceptions import EmptyResultSet
from django.db import connection
from django.db.models import BooleanField, Case, CharField, Count, Exists, F, Func, IntegerField, OuterRef, Prefetch, Q, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Cast, Replace

from catalog.models import Asset, DocumentType, EvidenceSpan, KnowledgeNode, Topic, Work
from catalog.catalog_search_serializers import CatalogSearchQuery, CatalogWorkSerializer
from .publication_eligibility import public_editions
from .text import normalize_search_text

SNAPSHOT = "active_catalog_revision__snapshot"
YEARS = {"before-1900": (1, 1899), "1900-1949": (1900, 1949), "1950-1999": (1950, 1999),
         "2000-2009": (2000, 2009), "2010-2019": (2010, 2019), "2020-now": (2020, 9999)}
YEAR_LABELS = {"before-1900": "1900 年以前", "2020-now": "2020 年至今"}
LANGUAGES = {"zh-CN": "简体中文", "zh-TW": "繁体中文", "zh-HK": "繁体中文", "en": "英文", "fr": "法文", "de": "德文"}
ARRAYS = {"author": ("contributions",), "topic": ("knowledge", "topics"),
          "theory": ("knowledge", "nodes"), "concept": ("knowledge", "nodes")}


def _rows_sql(db, snapshot_sql, kind):
    """Identifiers/paths here are fixed code; all user input remains SQL parameters."""
    path = ARRAYS[kind]
    if db.vendor == "postgresql":
        array = f"({snapshot_sql} #> '{{{','.join(path)}}}')"
        source = f"jsonb_array_elements(CASE WHEN jsonb_typeof({array}) = 'array' THEN {array} ELSE '[]'::jsonb END) AS item(value)"
        def field(*keys):
            return f"(item.value #>> '{{{','.join(keys)}}}')"
        id_cast = "::text"
    elif db.vendor == "sqlite":
        array = f"json_extract({snapshot_sql}, '$.{'.'.join(path)}')"
        source = f"json_each(CASE WHEN json_type({snapshot_sql}, '$.{'.'.join(path)}') = 'array' THEN {array} ELSE '[]' END) AS item"
        def field(*keys):
            return f"json_extract(item.value, '$.{'.'.join(keys)}')"
        id_cast = ""
    else:
        raise NotImplementedError("Catalog snapshot search requires PostgreSQL or SQLite JSON support.")
    if kind == "author":
        identifier = f"COALESCE({field('person_id')}, {field('person', 'id')})"
        label = f"COALESCE({field('person', 'preferred_name')}, {field('name')}, '')"
        if db.vendor == "postgresql":
            scope = "item.value->'scope'"
            whole = f"({scope} IS NULL OR {scope} IN ('null'::jsonb, '{{}}'::jsonb) OR (jsonb_typeof({scope}) = 'object' AND {field('scope', 'kind')} = 'edition' AND ({field('scope', 'chapters')} IS NULL OR {field('scope', 'chapters')} = '[]')))"
        else:
            scope = "json_extract(item.value, '$.scope')"
            whole = f"({scope} IS NULL OR {scope} = '{{}}' OR (json_type(item.value, '$.scope') = 'object' AND {field('scope', 'kind')} = 'edition' AND ({field('scope', 'chapters')} IS NULL OR {field('scope', 'chapters')} = '[]')))"
        predicate = f"{field('role')} = 'author' AND {whole}"
        text = [label, field("person", "original_name"), field("person", "aliases")]
    else:
        identifier, label = field("slug"), field("name")
        model, status = (Topic, "editorial_status") if kind == "topic" else (KnowledgeNode, "status")
        table = db.ops.quote_name(model._meta.db_table)
        row_id = field("id")
        # SQLite's UUIDField omits dashes, unlike PostgreSQL's UUID text cast.
        comparison = f"entity.id{id_cast} = {row_id}" if db.vendor == "postgresql" else f"entity.id = replace({row_id}, '-', '')"
        predicate = f"EXISTS (SELECT 1 FROM {table} AS entity WHERE {comparison} AND entity.{status} = 'published')"
        if kind != "topic":
            node_type = "theory_tradition" if kind == "theory" else "concept"
            predicate += f" AND {field('type')} = '{node_type}'"
        text = [label, field("foreign_name")]
    return source, identifier, label, predicate, text


class SnapshotArrayMatch(Func):
    output_field = BooleanField()

    def __init__(self, kind, *, text=None, identifiers=None):
        self.kind, self.text, self.identifiers = kind, text, identifiers
        super().__init__(F(SNAPSHOT))

    def as_sql(self, compiler, db, **extra_context):
        sql, params = compiler.compile(self.source_expressions[0])
        source, identifier, _label, predicate, fields = _rows_sql(db, sql, self.kind)
        if self.text is not None:
            pattern = "%" + db.ops.prep_for_like_query(self.text) + "%"
            operator = "ILIKE" if db.vendor == "postgresql" else "LIKE"
            conditions = " OR ".join(f"COALESCE({field}, '') {operator} %s ESCAPE '\\'" for field in fields)
            values = [pattern] * len(fields)
        else:
            conditions = f"{identifier} IN ({', '.join(['%s'] * len(self.identifiers))})"
            values = self.identifiers
        return f"EXISTS (SELECT 1 FROM {source} WHERE {predicate} AND ({conditions}))", [*params, *params, *values]


def _count(edition_rows):
    return edition_rows.order_by().values("work_id").distinct().count()


def _base():
    primary = public_editions().filter(is_primary=True).order_by().values("work_id")
    readable = Asset.objects.filter(pk=OuterRef("active_catalog_revision__reader_asset_id"),
        edition_id=OuterRef("pk"), kind=Asset.Kind.NORMALIZED, status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        access_status__in=[Asset.AccessStatus.PUBLIC, Asset.AccessStatus.INHERIT]).exclude(file="").annotate(
            compact_id=Replace(Cast("pk", CharField()), Value("-"), Value("")),
        ).filter(compact_id=OuterRef("catalog_asset_identity"))
    return public_editions().filter(work_id__in=primary).annotate(
        catalog_asset_identity=Replace(KeyTextTransform("asset_id", KeyTransform("document", F(SNAPSHOT))), Value("-"), Value("")),
        catalog_readable=Exists(readable),
        catalog_year=Cast(KeyTextTransform("publication_year", KeyTransform("edition", F(SNAPSHOT))), IntegerField()),
        catalog_title=KeyTextTransform("title", KeyTransform("work", F(SNAPSHOT))),
        catalog_language=KeyTextTransform("language", KeyTransform("work", F(SNAPSHOT))),
        catalog_type=KeyTextTransform("document_type", KeyTransform("work", F(SNAPSHOT))),
    ).order_by()


def _query(rows, query, matches):
    for index, term in enumerate(query.split()):
        condition = Q(pk__in=[])
        if "title" in matches:
            for field in ("title", "subtitle", "original_title", "uniform_title"):
                condition |= Q(**{f"{SNAPSHOT}__work__{field}__icontains": term})
        if "abstract" in matches:
            condition |= Q(**{f"{SNAPSHOT}__work__abstract__icontains": term})
        for kind in (["author"] if "author" in matches else []) + (["topic", "theory", "concept"] if "keyword" in matches else []):
            alias = f"catalog_{kind}_{index}"
            rows = rows.alias(**{alias: SnapshotArrayMatch(kind, text=term)})
            condition |= Q(**{alias: True})
        if "fulltext" in matches and normalize_search_text(term):
            evidence = EvidenceSpan.objects.filter(document_revision_id=OuterRef("active_catalog_revision__document_revision_id"),
                document_revision__is_active=True, document_revision__asset_id=OuterRef("active_catalog_revision__reader_asset_id"),
                page__asset_id=OuterRef("active_catalog_revision__reader_asset_id"), is_stale=False,
                normalized_text__icontains=normalize_search_text(term))
            alias = f"catalog_fulltext_{index}"
            rows = rows.alias(**{alias: Exists(evidence)})
            condition |= Q(**{alias: True}, catalog_readable=True, active_catalog_revision__fulltext_ready=True)
        rows = rows.filter(condition)
    return rows


def _filter(rows, data):
    for field, key in (("catalog_type", "document_type"), ("catalog_language", "language")):
        if data[key]:
            values = ["journal_article" if key == "document_type" and value == "article" else value for value in data[key]]
            rows = rows.filter(**{f"{field}__in": values})
    for kind in ARRAYS:
        if data[kind]:
            rows = rows.filter(SnapshotArrayMatch(kind, identifiers=data[kind]))
    if data["year"]:
        condition = Q(pk__in=[])
        for value in data["year"]:
            condition |= Q(catalog_year__range=YEARS[value])
        rows = rows.filter(condition)
    if "year_min" in data:
        rows = rows.filter(catalog_year__gte=data["year_min"])
    if "year_max" in data:
        rows = rows.filter(catalog_year__lte=data["year_max"])
    if len(set(data["access"])) == 1:
        rows = rows.filter(catalog_readable=data["access"][0] == "readable")
    return rows


def _array_facets(rows, kind):
    query = rows.values("work_id", public_snapshot=F(SNAPSHOT)).query
    try:
        sql, params = query.sql_with_params()
    except EmptyResultSet:
        return []
    source, value, label, predicate, _text = _rows_sql(connection, "base.public_snapshot", kind)
    # The CTE stays a database relation; no full-library snapshots enter application memory.
    sql = f"WITH base AS ({sql}) SELECT {value} AS value, MIN({label}) AS label, COUNT(DISTINCT base.work_id) FROM base, {source} WHERE {predicate} AND COALESCE({value}, '') <> '' GROUP BY {value} ORDER BY 3 DESC, 2, 1"
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return [{"value": value, "label": label or value, "count": count} for value, label, count in cursor.fetchall()]


def _facets(rows):
    def scalar(field, labels):
        return [{"value": row[field], "label": labels.get(row[field], row[field]), "count": row["count"]}
            for row in rows.exclude(**{f"{field}__isnull": True}).exclude(**{field: ""}).values(field).annotate(count=Count("work_id", distinct=True)).order_by("-count", field)]
    years = [{"year": row["catalog_year"], "count": row["count"]} for row in rows.filter(catalog_year__gte=1, catalog_year__lte=9999)
        .values("catalog_year").annotate(count=Count("work_id", distinct=True)).order_by("catalog_year")]
    return {"document_types": scalar("catalog_type", dict(DocumentType.choices)), "languages": scalar("catalog_language", LANGUAGES),
        "authors": _array_facets(rows, "author"), "topics": _array_facets(rows, "topic"),
        "theories": _array_facets(rows, "theory"), "concepts": _array_facets(rows, "concept"),
        "years": [{"value": key, "label": YEAR_LABELS.get(key, key.replace("-", "—")), "count": _count(rows.filter(catalog_year__range=limits))} for key, limits in YEARS.items()],
        "year_histogram": years, "access": [{"value": key, "label": label, "count": _count(rows.filter(catalog_readable=key == "readable"))}
            for key, label in (("readable", "可在线阅读"), ("metadata", "仅书目信息"))]}


def search_catalog(request):
    params = request.query_params
    repeated = {"match", "document_type", "author", "language", "theory", "topic", "concept", "access", "year"}
    supplied = {key: params.getlist(key) if key in repeated else params[key] for key in CatalogSearchQuery().fields if key in params}
    schema = CatalogSearchQuery(data=supplied)
    schema.is_valid(raise_exception=True)
    data = schema.validated_data
    base = _query(_base(), data["q"], data["match"])
    matched = _filter(base, data)
    total = _count(matched)
    # Stable order on one Work row; related Edition joins never multiply pagination.
    work_rows = Work.objects.filter(pk__in=matched.values("work_id"))
    own = matched.filter(work_id=OuterRef("pk"))
    primary_title = public_editions().filter(work_id=OuterRef("pk"), is_primary=True).order_by("pk")
    work_rows = work_rows.annotate(search_title=Subquery(primary_title.values(f"{SNAPSHOT}__work__title")[:1]))
    if data["sort"] == "year":
        work_rows = work_rows.annotate(sort_value=Subquery(own.order_by(F("catalog_year").desc(nulls_last=True), "pk").values("catalog_year")[:1])).order_by(F("sort_value").desc(nulls_last=True), "search_title", "pk")
    elif data["sort"] == "newest":
        work_rows = work_rows.annotate(sort_value=Subquery(own.order_by("-first_published_at", "pk").values("first_published_at")[:1])).order_by(F("sort_value").desc(nulls_last=True), "search_title", "pk")
    else:
        rank = Case(When(catalog_title__iexact=data["q"], then=Value(0)), When(catalog_title__istartswith=data["q"], then=Value(1)), default=Value(2), output_field=IntegerField())
        work_rows = work_rows.annotate(sort_value=Subquery(own.annotate(rank=rank).order_by("rank", "pk").values("rank")[:1])).order_by("sort_value", "search_title", "pk")
    start = (data["page"] - 1) * data["page_size"]
    works = list(work_rows.prefetch_related(Prefetch("editions", queryset=public_editions().order_by("-is_primary", "pk")))[start:start + data["page_size"]])
    matched_editions = defaultdict(list)
    for work_id, edition_id in matched.filter(work_id__in=[work.pk for work in works]).values_list("work_id", "pk"):
        matched_editions[work_id].append(str(edition_id))
    counts = {"works": total, "scholars": 0, "topics": 0, "theories": 0, "passages": 0,
        **{key: _count(matched.filter(catalog_type=value)) for key, value in (("books", "book"), ("articles", "journal_article"), ("theses", "thesis"), ("reports", "report"))}}
    return {"context": "global", "scope": "catalog", "query": data["q"], "counts": counts,
        "works": CatalogWorkSerializer(works, many=True, context={"request": request, "matched_editions": matched_editions}).data,
        "facets": _facets(base), "scholars": [], "topics": [], "theories": [], "passages": [],
        "pagination": {"page": data["page"], "page_size": data["page_size"], "total": total, "total_pages": max(1, (total + data["page_size"] - 1) // data["page_size"])}}
