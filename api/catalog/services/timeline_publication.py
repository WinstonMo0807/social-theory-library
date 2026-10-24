"""Public timeline projections over reviewed events and active catalog snapshots."""
from catalog.services.contribution_scope import whole_edition_contribution
from uuid import UUID

from collections import defaultdict

from django.db.models import CharField, Count, Exists, F, IntegerField, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Cast, Coalesce
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from catalog.models import (
    Discipline, KnowledgeNode, KnowledgeNodeTopic, KnowledgeRelation, PersonTopicRelation,
    TheoryTimelineEvent, TimelineEventRelation, Topic,
)
from catalog.services.catalog_search import SnapshotArrayMatch, _rows_sql
from catalog.services.publication_eligibility import public_editions
from catalog.services.scoped_search import public_scholar_queryset
from catalog.services.timeline_evidence import timeline_file, timeline_reader_href


def public_events():
    return TheoryTimelineEvent.objects.filter(review_status="approved").select_related(
        "discipline", "subdiscipline", "theory_school", "scholar__person", "work",
        "subject_edition__work", "subject_edition__active_catalog_revision__reader_asset",
        "subject_edition__active_catalog_revision__document_revision",
    ).prefetch_related(
        "normalized_relations__node", "normalized_relations__discipline",
        "normalized_relations__scholar__person", "normalized_relations__work",
    ).annotate(timeline_year=Coalesce("start_year", "end_year"))


def values(params, key):
    raw = params.getlist(key) if hasattr(params, "getlist") else [params.get(key, "")]
    output = list(dict.fromkeys(value.strip() for item in raw for value in str(item).split(",") if value.strip()))
    if len(output) > 30:
        raise ValidationError({key: "一次最多选择30项。"})
    return output


def chosen(queryset, selected):
    ids = []
    for value in selected:
        try:
            ids.append(UUID(value))
        except (ValueError, TypeError):
            pass
    return queryset.filter(Q(slug__in=selected) | Q(pk__in=ids))


def scholar_card(profile):
    from catalog.serializers import PersonCompactSerializer
    return {
        "id": str(profile.pk), "person_id": str(profile.person_id), "name": profile.person.preferred_name,
        "slug": profile.slug, "href": f"/scholars/{profile.slug}",
        "portrait_url": PersonCompactSerializer().get_portrait(profile.person),
        "portrait_media": PersonCompactSerializer().get_portrait_media(profile.person),
    }


def topic_card(topic):
    return {"id": str(topic.pk), "name": topic.name, "slug": topic.slug, "href": f"/topics/{topic.slug}"}


def work_match(editions):
    """An explicit subject edition never borrows another edition's matching metadata."""
    works = editions.order_by().values("work_id")
    related = TimelineEventRelation.objects.filter(event_id=OuterRef("pk"), work_id__in=works)
    return (
        Q(subject_edition_id__in=editions.order_by().values("pk"))
        | Q(subject_edition__isnull=True, work_id__in=works)
        | Q(subject_edition__isnull=True, pk__in=related.values("event_id"))
        | Q(subject_edition__isnull=False) & Q(Exists(
            related.exclude(work_id=OuterRef("subject_edition__work_id")),
        ))
    )


class SnapshotScholarMatch(SnapshotArrayMatch):
    """Keep matching public author identities in SQL, even for broad queries."""
    def __init__(self, profiles):
        super().__init__("author")
        self.source_expressions.append(Subquery(profiles.order_by().annotate(
            timeline_person_id=Cast("person_id", CharField()),
        ).values("timeline_person_id")))

    def as_sql(self, compiler, db, **extra_context):
        snapshot_sql, snapshot_params = compiler.compile(self.source_expressions[0])
        people_sql, people_params = compiler.compile(self.source_expressions[1])
        source, identifier, _label, predicate, _fields = _rows_sql(db, snapshot_sql, "author")
        if db.vendor == "sqlite":
            identifier = f"replace({identifier}, '-', '')"
        return (
            f"EXISTS (SELECT 1 FROM {source} WHERE {predicate} AND {identifier} IN {people_sql})",
            [*snapshot_params, *snapshot_params, *people_params],
        )


def scholar_match(profiles):
    ids = profiles.order_by().values("pk")
    query = Q(scholar_id__in=ids) | Q(normalized_relations__scholar_id__in=ids)
    return query | work_match(public_editions().filter(SnapshotScholarMatch(profiles)))


def integer(params, key):
    raw = params.get(key, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (ValueError, TypeError):
        raise ValidationError({key: "年份须为整数。"})
    if not -32768 <= value <= 32767 or str(value) != raw.lstrip("+"):
        raise ValidationError({key: "年份须为支持范围内的整数。"})
    return value


def scoped_events(params):
    rows = public_events()
    selections = {"selected_topics": [], "selected_authors": []}
    lower, upper = integer(params, "year_from"), integer(params, "year_to")
    if lower is not None and upper is not None and lower > upper:
        raise ValidationError({"year_to": "结束年份不能早于开始年份。"})
    if lower is not None:
        rows = rows.annotate(range_end=Coalesce("end_year", "start_year")).filter(range_end__gte=lower)
    if upper is not None:
        rows = rows.filter(timeline_year__lte=upper)
    event_types = values(params, "event_type")
    if set(event_types) - set(TheoryTimelineEvent.EventType.values):
        raise ValidationError({"event_type": "包含不支持的事件类型。"})
    if event_types:
        rows = rows.filter(event_type__in=event_types)
    sort = params.get("sort", "asc").strip()
    if sort not in {"asc", "desc"}:
        raise ValidationError({"sort": "排序须为 asc 或 desc。"})
    discipline = params.get("discipline", "").strip()
    if discipline:
        disciplines = chosen(Discipline.objects.filter(editorial_status="published"), [discipline])
        nodes = KnowledgeNode.objects.filter(
            Q(primary_discipline__in=disciplines)
            | Q(discipline_links__discipline__in=disciplines, discipline_links__status="published"),
            status="published",
        )
        rows = rows.filter(
            Q(discipline__in=disciplines) | Q(normalized_relations__discipline__in=disciplines)
            | Q(normalized_relations__node__in=nodes)
            | Q(subdiscipline__discipline__in=disciplines, subdiscipline__editorial_status="published")
        )
    node = params.get("node", "").strip()
    if node:
        rows = rows.filter(normalized_relations__node__in=chosen(
            KnowledgeNode.objects.filter(status="published"), [node],
        ))
    authors = values(params, "author")
    if authors:
        profiles = chosen(public_scholar_queryset(), authors)
        selections["selected_authors"] = [scholar_card(row) for row in profiles.order_by("person__preferred_name", "pk")]
        rows = rows.filter(scholar_match(profiles))
    topics = values(params, "topic")
    if topics:
        selected = chosen(Topic.objects.filter(editorial_status="published"), topics)
        selections["selected_topics"] = [topic_card(row) for row in selected.order_by("name", "pk")]
        nodes = KnowledgeNodeTopic.objects.filter(
            topic__in=selected, status="published", node__status="published",
        ).values("node_id")
        people = PersonTopicRelation.objects.filter(topic__in=selected, review_status="approved").values("person_id")
        profiles = public_scholar_queryset().filter(person_id__in=people)
        slugs = list(selected.values_list("slug", flat=True))
        query = Q(normalized_relations__node_id__in=nodes) | scholar_match(profiles)
        if slugs:
            query |= work_match(public_editions().filter(SnapshotArrayMatch("topic", identifiers=slugs)))
        rows = rows.filter(query)
    collection = params.get("has_collection", "").strip().lower()
    if collection not in {"", "1", "true", "yes", "0", "false", "no"}:
        raise ValidationError({"has_collection": "馆藏筛选值无效。"})
    if collection:
        query = work_match(public_editions())
        rows = rows.filter(query) if collection in {"1", "true", "yes"} else rows.exclude(query)
    query = params.get("q", "").strip()
    if query:
        profiles = public_scholar_queryset().filter(
            Q(person__preferred_name__icontains=query) | Q(person__original_name__icontains=query),
        )
        editions = public_editions().filter(
            Q(active_catalog_revision__snapshot__work__title__icontains=query)
            | Q(active_catalog_revision__snapshot__work__original_title__icontains=query),
        )
        rows = rows.filter(
            Q(title__icontains=query) | Q(description__icontains=query) | Q(source__icontains=query)
            | Q(normalized_relations__node__canonical_name_zh__icontains=query, normalized_relations__node__status="published")
            | scholar_match(profiles) | work_match(editions)
        )
    related = params.get("related_to", "").strip()
    if related:
        origin = get_object_or_404(public_events(), pk=event_id(related, "related_to"))
        rows = rows.filter(related_query(origin)).exclude(pk=origin.pk)
    return rows.distinct(), sort, selections


def event_id(raw, key="focus"):
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        raise ValidationError({key: "事件标识须为有效 UUID。"})


def ordered(rows, sort):
    return rows.annotate(
        timeline_sort_year=Coalesce("start_year", "end_year", Value(32768 if sort == "asc" else -32769), output_field=IntegerField()),
    ).order_by("timeline_sort_year" if sort == "asc" else "-timeline_sort_year", "display_order", "title", "pk")


def focus_page(rows, focus, sort, page_size):
    row = get_object_or_404(rows, pk=event_id(focus))
    year_lookup = "timeline_sort_year__lt" if sort == "asc" else "timeline_sort_year__gt"
    before = Q(**{year_lookup: row.timeline_sort_year})
    tie = Q(timeline_sort_year=row.timeline_sort_year)
    before |= tie & Q(display_order__lt=row.display_order)
    before |= tie & Q(display_order=row.display_order, title__lt=row.title)
    before |= tie & Q(display_order=row.display_order, title=row.title, pk__lt=row.pk)
    return rows.filter(before).count() // page_size + 1, str(row.pk)


def aggregates(rows):
    groups = {}
    for row in rows.order_by().values("timeline_year", "event_type").annotate(count=Count("pk", distinct=True)).order_by(
        F("timeline_year").asc(nulls_last=True), "event_type",
    ):
        group = groups.setdefault(row["timeline_year"], {"year": row["timeline_year"], "count": 0, "event_types": []})
        group["count"] += row["count"]
        group["event_types"].append({"event_type": row["event_type"], "count": row["count"]})
    years = [year for year in groups if year is not None]
    latest = rows.aggregate(value=Max(Coalesce("end_year", "start_year")))["value"]
    return {
        "scope_count": sum(row["count"] for row in groups.values()),
        "year_groups": list(groups.values()),
        "bounds": {"min_year": min(years) if years else None, "max_year": latest,
                   "undated_count": groups.get(None, {}).get("count", 0)},
    }


def _snapshot_ids(snapshot):
    people, topics = set(), set()
    for row in snapshot.get("contributions") or []:
        if isinstance(row, dict) and row.get("role") == "author" and whole_edition_contribution(row):
            raw = row.get("person_id") or (row.get("person") or {}).get("id")
            try:
                people.add(UUID(str(raw)))
            except (ValueError, TypeError):
                pass
    for row in (snapshot.get("knowledge") or {}).get("topics") or []:
        try:
            topics.add(UUID(str(row.get("id"))))
        except (ValueError, TypeError, AttributeError):
            pass
    return people, topics


def prepare_timeline_projections(events, context):
    from catalog.timeline_participants import participant_identity_ids
    """Batch page-level catalog, author and topic joins; never scan the library."""
    prepared = context.setdefault("_timeline_prepared", set())
    events = [row for row in events if row.pk not in prepared]
    if not events:
        return
    work_ids, edition_ids, node_ids, person_ids = set(), set(), set(), set()
    for event in events:
        if event.subject_edition_id:
            edition_ids.add(event.subject_edition_id)
        elif event.work_id:
            work_ids.add(event.work_id)
        if event.scholar_id:
            person_ids.add(event.scholar.person_id)
        for relation in event.normalized_relations.all():
            if relation.work_id and (
                not event.subject_edition_id or relation.work_id != event.subject_edition.work_id
            ):
                work_ids.add(relation.work_id)
            if relation.node_id and relation.node.status == "published":
                node_ids.add(relation.node_id)
            if relation.scholar_id:
                person_ids.add(relation.scholar.person_id)
    editions = context.setdefault("_timeline_editions", {})
    work_editions = context.setdefault("_timeline_work_editions", {})
    for work_id in work_ids:
        work_editions[work_id] = []
    for edition in public_editions().filter(Q(work_id__in=work_ids) | Q(pk__in=edition_ids)).order_by("-is_primary", "-published_at", "pk"):
        editions[edition.pk] = edition
        if edition.work_id in work_ids:
            work_editions[edition.work_id].append(edition)
        # Only IDs are used from raw snapshots; labels still require current
        # public entities, and work cards use the established snapshot serializer.
        raw = edition.active_catalog_revision.snapshot
        if isinstance(raw, dict):
            person_ids.update(_snapshot_ids(raw)[0])
            person_ids.update(participant_identity_ids(raw))
    profiles = list(public_scholar_queryset().filter(person_id__in=person_ids))
    context.setdefault("_timeline_scholars", {}).update({row.person_id: row for row in profiles})
    node_topics = defaultdict(set)
    for node_id, topic_id in KnowledgeNodeTopic.objects.filter(
        node_id__in=node_ids, status="published", topic__editorial_status="published",
    ).values_list("node_id", "topic_id"):
        node_topics[node_id].add(topic_id)
    context.setdefault("_timeline_node_topics", {}).update({node_id: node_topics[node_id] for node_id in node_ids})
    person_topics = defaultdict(set)
    for person_id, topic_id in PersonTopicRelation.objects.filter(
        person_id__in=[row.person_id for row in profiles], review_status="approved",
        topic__editorial_status="published",
    ).values_list("person_id", "topic_id"):
        person_topics[person_id].add(topic_id)
    context.setdefault("_timeline_person_topics", {}).update({row.person_id: person_topics[row.person_id] for row in profiles})
    topic_ids = set().union(*node_topics.values(), *person_topics.values())
    for edition in editions.values():
        raw = edition.active_catalog_revision.snapshot
        if isinstance(raw, dict):
            topic_ids.update(_snapshot_ids(raw)[1])
    context.setdefault("_timeline_topics", {}).update({
        row.pk: row for row in Topic.objects.filter(pk__in=topic_ids, editorial_status="published")
    })
    prepared.update(row.pk for row in events)


def _work_card(edition, context):
    if edition is None:
        return None
    from catalog.theory_serializers import compact_work
    cards = context.setdefault("_timeline_work_cards", {})
    if edition.pk not in cards:
        cards[edition.pk] = compact_work(edition.work, context.get("request"), edition=edition)
    return cards[edition.pk]


def event_projection(event, context):
    cache = context.setdefault("_timeline_projections", {})
    if event.pk in cache:
        return cache[event.pk]
    from catalog.services.scholar_publication import scholar_public_eligibility
    prepare_timeline_projections([event], context)
    editions = context["_timeline_editions"]
    work_editions = context["_timeline_work_editions"]
    selected = event.subject_edition
    subject = _work_card(editions.get(selected.pk), context) if selected else None
    if subject:
        subject["version_label"] = str((selected.active_catalog_revision.snapshot.get("edition") or {}).get("version_label") or "")
    choices = work_editions.get(event.work_id, [])
    work = subject if selected else _work_card(choices[0], context) if choices else None
    targets, scholars, node_ids, snapshots = [], {}, set(), []
    if selected and subject:
        snapshots.append(selected.active_catalog_revision.snapshot)
    elif not selected and event.work_id:
        snapshots.extend(row.active_catalog_revision.snapshot for row in choices)
    for relation in event.normalized_relations.all():
        target = None
        if relation.node_id and relation.node.status == "published":
            node = relation.node
            node_ids.add(node.pk)
            target = {"type": "node", "id": str(node.pk), "name": node.canonical_name_zh, "slug": node.slug,
                      "href": f"/theories/nodes/{node.slug}", "node_type": node.node_type}
        elif relation.discipline_id and relation.discipline.editorial_status == "published":
            row = relation.discipline
            target = {"type": "discipline", "id": str(row.pk), "name": row.name, "slug": row.slug,
                      "href": f"/theories?discipline={row.slug}"}
        elif relation.scholar_id and scholar_public_eligibility(relation.scholar)["eligible"]:
            row = relation.scholar
            scholars[row.pk] = scholar_card(row)
            target = {"type": "scholar", "id": str(row.pk), "name": row.person.preferred_name, "slug": row.slug,
                      "href": f"/scholars/{row.slug}"}
        elif relation.work_id:
            if selected and relation.work_id == selected.work_id:
                related_editions = [editions[selected.pk]] if subject else []
            else:
                related_editions = work_editions.get(relation.work_id, [])
            card = _work_card(related_editions[0], context) if related_editions else None
            if card:
                target = {"type": "work", "id": card["id"], "name": card["title"],
                          "slug": card["slug"], "detail_href": card["detail_href"], "href": card["detail_href"]}
                snapshots.extend(row.active_catalog_revision.snapshot for row in related_editions)
        if target:
            targets.append({**target, "relation_type": relation.relation_type, "description": relation.description})
    for name, kind, url in (
        ("discipline", "discipline", "/theories?discipline="),
        ("subdiscipline", "subdiscipline", "/subdisciplines/"),
        ("theory_school", "legacy_theory", "/theory-schools/"),
    ):
        row = getattr(event, name)
        if row and row.editorial_status == "published":
            targets.append({"type": kind, "id": str(row.pk), "name": row.name, "slug": row.slug,
                            "href": url + row.slug, "relation_type": "subject", "description": ""})
    if event.scholar_id and scholar_public_eligibility(event.scholar)["eligible"]:
        row = event.scholar
        scholars[row.pk] = scholar_card(row)
        targets.append({"type": "scholar", "id": str(row.pk), "name": row.person.preferred_name,
                        "slug": row.slug, "href": f"/scholars/{row.slug}", "relation_type": "subject", "description": ""})
    if work:
        targets.append({"type": "work", "id": work["id"], "name": work["title"], "slug": work["slug"],
                        "href": work["detail_href"], "detail_href": work["detail_href"], "relation_type": "subject", "description": ""})
    # Only stored, currently public associations are projected as topics/authors.
    person_ids, topic_ids = set(), set()
    for snapshot in snapshots:
        authors, subjects = _snapshot_ids(snapshot)
        person_ids.update(authors)
        topic_ids.update(subjects)
    for person_id in person_ids:
        profile = context["_timeline_scholars"].get(person_id)
        if profile:
            scholars[profile.pk] = scholar_card(profile)
    for node_id in node_ids:
        topic_ids.update(context["_timeline_node_topics"].get(node_id, set()))
    for row in scholars.values():
        topic_ids.update(context["_timeline_person_topics"].get(UUID(row["person_id"]), set()))
    topics = [topic_card(row) for row in sorted(
        (context["_timeline_topics"][pk] for pk in topic_ids if pk in context["_timeline_topics"]),
        key=lambda row: (row.name, str(row.pk)),
    )]
    href = timeline_reader_href(event, context)
    evidence = None
    if href:
        asset = timeline_file(event, context)
        # timeline_reader_href has already checked this exact active source.
        # Only work/edition labels are read here; taxonomy masking is unrelated.
        snapshot = asset.edition.active_catalog_revision.snapshot
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        evidence = {
            "asset_id": str(asset.pk), "edition_id": str(asset.edition_id), "work_id": str(asset.edition.work_id),
            "document_revision_id": str(asset.edition.active_catalog_revision.document_revision_id),
            "title": str((snapshot.get("work") or {}).get("title") or ""),
            "edition_label": str((snapshot.get("edition") or {}).get("version_label") or ""),
            "pdf_page": event.evidence_page, "printed_page_label": event.evidence_printed_label,
            "quote": event.evidence_text, "reader_href": href,
        }
    borrowed_portrait = next((row for row in scholars.values() if row["portrait_url"]), None)
    image_url = event.image.url if event.image else (subject["cover_url"] if subject else "") or (borrowed_portrait or {}).get("portrait_url", "")
    image_media = None if event.image else subject.get("cover_media") if subject and subject["cover_url"] else (borrowed_portrait or {}).get("portrait_media")
    from catalog.timeline_participants import event_participants
    result = {
        "relations": list({(row["type"], row["id"], row["relation_type"]): row for row in targets}.values()),
        "participants": event_participants(event, editions.get(selected.pk) if selected and subject else None, context["_timeline_scholars"]),
        "subject_edition": subject,
        "subject_status": "available" if subject else "unavailable" if selected else "unspecified",
        "subject_work": {key: work[key] for key in ("id", "title", "detail_href")} if work else None,
        "scholars": list(scholars.values()), "topics": topics,
        "image_url": image_url, "image_media": image_media,
        "source_status": "available" if evidence else "unavailable" if event.evidence_asset_id
                         else "citation_only" if event.source or event.evidence_text else "missing",
        "evidence_source": evidence,
    }
    cache[event.pk] = result
    return result


def related_query(event, context=None):
    data = event_projection(event, {} if context is None else context)
    ids = {kind: [row["id"] for row in data["relations"] if row["type"] == kind] for kind in ("node", "work", "scholar")}
    return (
        Q(normalized_relations__node_id__in=ids["node"])
        | Q(subject_edition__isnull=True, normalized_relations__work_id__in=ids["work"])
        | Q(subject_edition__isnull=True, work_id__in=ids["work"])
        | Q(subject_edition_id__in=public_editions().values("pk"), normalized_relations__work_id__in=ids["work"])
        | Q(subject_edition__work_id__in=ids["work"], subject_edition_id__in=public_editions().values("pk"))
        | Q(normalized_relations__scholar_id__in=ids["scholar"]) | Q(scholar_id__in=ids["scholar"])
    )


def event_knowledge_relations(event):
    node_ids = [row.node_id for row in event.normalized_relations.all() if row.node_id and row.node.status == "published"]
    return KnowledgeRelation.objects.filter(
        Q(source_node_id__in=node_ids) | Q(target_node_id__in=node_ids),
        status="published", source_node__status="published", target_node__status="published",
    ).select_related("source_node", "target_node").order_by("-published_at", "pk")
