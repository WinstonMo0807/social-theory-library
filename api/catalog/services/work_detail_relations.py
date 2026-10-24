"""PDF 33–35 relationships resolved from the selected published edition."""
from uuid import UUID

from django.db.models import BooleanField, F, Func, Prefetch, Q
from rest_framework import serializers

from catalog.catalog_search_serializers import CatalogEditionSerializer, CatalogWorkSerializer
from catalog.models import KnowledgeNode, ReadingPath, Topic, Work
from catalog.serializers import PersonCompactSerializer
from catalog.media_views import PublicCoverMediaSerializer
from catalog.services.catalog_search import SnapshotArrayMatch
from catalog.services.publication_eligibility import active_catalog_snapshot, public_editions
from catalog.services.scoped_search import public_scholar_queryset

LIMIT = 6


class WorkRelatedScholarSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    person = PersonCompactSerializer()
    short_description = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())


class WorkRelatedConceptSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    summary = serializers.CharField()


class WorkRelatedTopicSerializer(WorkRelatedConceptSerializer):
    description = serializers.CharField()
    hero_image = serializers.CharField(allow_blank=True)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)


class WorkRelatedPathSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.CharField()
    introduction = serializers.CharField()
    cover_url = serializers.CharField(allow_blank=True)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)


class WorkRelatedCurationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.CharField()
    summary = serializers.CharField()
    cover_url = serializers.CharField(allow_blank=True)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)


class WorkIssueContentsSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    article_work_id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    author_display = serializers.CharField()
    page_range = serializers.CharField()
    position = serializers.IntegerField()
    article_href = serializers.CharField(allow_blank=True)


class WorkRelatedJournalSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    cover_url = serializers.CharField(allow_blank=True)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)
    edition = CatalogEditionSerializer()
    contents = WorkIssueContentsSerializer(many=True)


class WorkRelationsSerializer(serializers.Serializer):
    scholars = WorkRelatedScholarSerializer(many=True)
    concepts = WorkRelatedConceptSerializer(many=True)
    topics = WorkRelatedTopicSerializer(many=True)
    reading_paths = WorkRelatedPathSerializer(many=True)
    curations = WorkRelatedCurationSerializer(many=True)
    works = CatalogWorkSerializer(many=True)
    journal_issues = WorkRelatedJournalSerializer(many=True)


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


# Compatibility name for the shared published issue-content formatter.
from .journal_issues import public_journal_contents as public_issue_contents

class _IssueContainsWork(Func):
    """Exact frozen issue membership, independent of mutable journal rows."""
    output_field = BooleanField()

    def __init__(self, work_id):
        self.work_id = str(work_id)
        super().__init__(F("active_catalog_revision__snapshot"))

    def as_sql(self, compiler, connection, **extra_context):
        sql, params = compiler.compile(self.source_expressions[0])
        if connection.vendor == "postgresql":
            value = f"({sql} -> 'journal_contents')"
            source = f"jsonb_array_elements(CASE WHEN jsonb_typeof({value}) = 'array' THEN {value} ELSE '[]'::jsonb END) AS item(value)"
            field = "(item.value ->> 'article_work_id')"
        elif connection.vendor == "sqlite":
            source = f"json_each(CASE WHEN json_type({sql}, '$.journal_contents') = 'array' THEN json_extract({sql}, '$.journal_contents') ELSE '[]' END) AS item"
            field = "json_extract(item.value, '$.article_work_id')"
        else:
            raise NotImplementedError("Published issue membership requires PostgreSQL or SQLite JSON support.")
        return f"EXISTS (SELECT 1 FROM {source} WHERE {field} = %s)", [*params, *params, self.work_id]


def _related_works(work, snapshot, context):
    knowledge = snapshot.get("knowledge") or {}
    condition = Q(pk__in=[])
    for kind, values in (
        ("topic", [row.get("slug") for row in knowledge.get("topics", [])]),
        ("theory", [row.get("slug") for row in knowledge.get("nodes", []) if row.get("type") == "theory_tradition"]),
        ("concept", [row.get("slug") for row in knowledge.get("nodes", []) if row.get("type") == "concept"]),
        ("author", [row.get("person_id") or (row.get("person") or {}).get("id") for row in snapshot.get("contributions", []) if row.get("role") == "author"]),
    ):
        identifiers = list(dict.fromkeys(str(value) for value in values if value))
        if identifiers:
            condition |= Q(SnapshotArrayMatch(kind, identifiers=identifiers))
    editions = public_editions().filter(is_primary=True).exclude(work_id=work.pk).filter(condition)
    # Limit after SQL relationship matching, never filter a general first page.
    identifiers = list(editions.order_by("-published_at", "id").values_list("work_id", flat=True)[:LIMIT])
    objects = Work.objects.filter(pk__in=identifiers).prefetch_related(
        Prefetch("editions", queryset=public_editions().order_by("-is_primary", "id")),
    )
    lookup = {row.pk: row for row in objects}
    result = CatalogWorkSerializer([lookup[key] for key in identifiers], many=True, context={**context, "matched_editions": {}}).data
    return result


def _journal_issues(work, context):
    primary = public_editions().filter(is_primary=True).values("work_id")
    editions = public_editions().filter(
        work_id__in=primary,
        active_catalog_revision__snapshot__work__document_type="journal_issue",
    ).filter(_IssueContainsWork(work.pk)).order_by("-is_primary", "-published_at", "id")[:LIMIT]
    result = []
    for edition in editions:
        snapshot = active_catalog_snapshot(edition)
        values = snapshot.get("work") or {}
        contents = public_issue_contents(snapshot.get("journal_contents", []))
        data = CatalogEditionSerializer(edition, context=context).data
        data["journal_contents"] = contents
        media = values.get("cover_media") or {}
        cover = f"/api/catalog/works/{edition.work_id}/cover/?edition_id={edition.pk}" if values.get("cover") or media else ""
        if cover and media.get("primary_rendition_id"):
            cover += f"&rendition={media['primary_rendition_id']}"
        result.append({"id": str(edition.work_id), "slug": data["public_slug"] or str(edition.pk),
                       "title": values.get("title", ""), "cover_url": cover, "cover_media": media or None,
                       "edition": data, "contents": contents})
    return result


def _curations(work):
    from catalog.models import RecommendationIssueItem
    from catalog.services.editorial_issues import issue_payload, public_issue_revision, published_issues

    result = []
    linked = {str(value) for value in RecommendationIssueItem.objects.filter(
        linked_work_id=work.pk, linked_edition__work_id=work.pk,
    ).values_list("pk", flat=True)}
    # ponytail: published issue previews have no reverse membership index.
    # Stream frozen headers; hydrate only matches, index the ledger if this grows.
    for issue in published_issues().order_by("-effective_display_from", "id").iterator(chunk_size=50):
        revision = public_issue_revision(issue)
        if not revision or revision.status != "published":
            continue
        items = (revision.materialized_preview or {}).get("items", [])
        if not any(str(item.get("work_id")) == str(work.pk) or str(item.get("id")) in linked for item in items):
            continue
        payload = issue_payload(issue, public=True)
        if not any(str(item.get("work_id")) == str(work.pk) for item in payload.get("items", [])):
            continue
        result.append({"id": str(issue.pk), "slug": payload["slug"], "title": payload.get("title", ""),
                       "summary": payload.get("introduction", "") or payload.get("summary", ""),
                       "cover_url": payload.get("cover_url", "")})
        if len(result) == LIMIT:
            break
    return result


def public_work_relations(work, edition, *, context=None):
    """Small previews, not exhaustive relationship counts or inferred claims."""
    result = {name: [] for name in WorkRelationsSerializer().fields}
    snapshot = active_catalog_snapshot(edition)
    if not snapshot or edition.work_id != work.pk:
        return result
    # Public relationships never inherit admin preview/include-unpublished flags.
    context = {"request": (context or {}).get("request")}
    contributions = snapshot.get("contributions") or []
    person_ids = {_uuid(row.get("person_id") or (row.get("person") or {}).get("id")) for row in contributions} - {None}
    profiles = public_scholar_queryset().filter(person_id__in=person_ids).order_by("person__sort_name", "id")[:LIMIT]
    result["scholars"] = [{"id": str(row.pk), "slug": row.slug, "short_description": row.short_description,
        "person": PersonCompactSerializer(row.person, context=context).data,
        "roles": list(dict.fromkeys(item.get("role", "") for item in contributions if str(item.get("person_id") or (item.get("person") or {}).get("id")) == str(row.person_id))),
    } for row in profiles]
    knowledge = snapshot.get("knowledge") or {}
    concept_ids = {_uuid(row.get("id")) for row in knowledge.get("nodes", []) if row.get("type") == "concept"} - {None}
    concepts = KnowledgeNode.objects.filter(pk__in=concept_ids, status="published", node_type="concept").order_by("sort_order", "id")[:LIMIT]
    result["concepts"] = [{"id": str(row.pk), "name": row.canonical_name_zh, "slug": row.slug, "summary": row.summary} for row in concepts]
    topic_ids = {_uuid(row.get("id")) for row in knowledge.get("topics", [])} - {None}
    topics = Topic.objects.filter(pk__in=topic_ids, editorial_status="published").order_by("-curation_level", "id")[:LIMIT]
    from catalog.services.public_topics import _image, _image_media
    result["topics"] = [{"id": str(row.pk), "name": row.name, "slug": row.slug, "summary": row.description,
                         "description": row.description, "hero_image": _image(row), "cover_media": _image_media(row)} for row in topics]
    from catalog.theory_serializers import ReadingPathSerializer
    paths = ReadingPath.objects.filter(status="published", items__work=work).distinct().order_by("sort_order", "id")[:LIMIT]
    path_serializer = ReadingPathSerializer(context=context)
    result["reading_paths"] = [{"id": str(row.pk), "title": row.title, "slug": row.slug, "introduction": row.introduction,
                                "cover_url": path_serializer.get_cover_url(row), "cover_media": path_serializer.get_cover_media(row)} for row in paths]
    result["works"] = _related_works(work, snapshot, context)
    result["journal_issues"] = _journal_issues(work, context) if (snapshot.get("work") or {}).get("document_type") == "journal_article" else []
    result["curations"] = _curations(work)
    return result
