"""Read identity labels from their constrained profiles, not migration copies."""
from django.db.models import Case, When, F, Q, TextField, OuterRef, Subquery, Exists
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce
from catalog import models as m

TEXT_PROFILES = (
    ("person", "preferred_name", "biography"), ("node", "canonical_name_zh", "definition"),
    ("topic", "name", "description"), ("discipline", "name", "description"),
    ("subdiscipline", "name", "description"), ("theory_school", "name", "description"),
    ("concept", "name", "description"), ("organization", "preferred_name", "description"),
    ("timeline_event", "title", "description"),
)
MAPPED_ALIASES = ("catalog.personnamevariant", "catalog.knowledgenodealias")


def independent_aliases(rows):
    return rows.exclude(Q(source__has_key="legacy_type") & Q(source__legacy_type__in=MAPPED_ALIASES))


def profile_aliases(entity, *, public=False):
    """Legacy alias rows retain history; their live authority decides visibility."""
    from .query_lexicon.registry import FORMAL_PERSON_VARIANT_SOURCES, FORMAL_KNOWLEDGE_ALIAS_SOURCES
    rows = independent_aliases(entity.aliases.all())
    if public:
        rows = rows.filter(review_status="confirmed")
    values = list(rows.values("text", "language", "script", "review_status", "source"))
    if entity.person_id:
        variants = m.PersonNameVariant.objects.filter(person_id=entity.person_id)
        if public:
            variants = variants.filter(is_verified=True, displayable=True, source_kind__in=FORMAL_PERSON_VARIANT_SOURCES)
        values += [{"text": row.name, "language": row.language, "script": "", "review_status": "confirmed" if row.is_verified else "legacy",
            "source": {"legacy_type": MAPPED_ALIASES[0], "legacy_id": str(row.pk), "kind": row.source_kind, "note": row.source_note}} for row in variants]
    if entity.node_id:
        variants = m.KnowledgeNodeAlias.objects.filter(node_id=entity.node_id)
        if public:
            variants = variants.filter(is_verified=True, source_kind__in=FORMAL_KNOWLEDGE_ALIAS_SOURCES)
        values += [{"text": row.alias, "language": row.language, "script": "", "review_status": "confirmed" if row.is_verified else "legacy",
            "source": {"legacy_type": MAPPED_ALIASES[1], "legacy_id": str(row.pk), "kind": row.source_kind}} for row in variants]
    unique = {}
    for value in values:
        key = (value["text"], value["language"], value["script"])
        if key not in unique or value["review_status"] == "confirmed":
            unique[key] = value
    return list(unique.values())


def identity_text(entity):
    for relation, label, definition in TEXT_PROFILES:
        if getattr(entity, f"{relation}_id"):
            row = getattr(entity, relation)
            return getattr(row, label), getattr(row, definition)
    return entity.label, entity.definition


def entity_query(rows=None, *, query="", public=False, exact=False, definitions=False):
    """All callers keep their own access scope; public person text is activated."""
    if rows is None:
        rows = m.Entity.objects.all()
    labels, descriptions = [], []
    for relation, label, definition in TEXT_PROFILES:
        name, text = F(f"{relation}__{label}"), F(f"{relation}__{definition}")
        if relation == "person" and public:
            from catalog.services.public_scholars import _base
            profiles = _base().filter(person_id=OuterRef("person_id")).annotate(identity_biography=Coalesce(
                KeyTextTransform("biography", KeyTransform("person", "public_snapshot")), F("person__biography"), output_field=TextField()))
            name = Subquery(profiles.values("public_name")[:1], output_field=TextField())
            text = Subquery(profiles.values("identity_biography")[:1], output_field=TextField())
        labels.append(When(**{f"{relation}__isnull": False}, then=name))
        descriptions.append(When(**{f"{relation}__isnull": False}, then=text))
    rows = rows.select_related(*[v[0] for v in TEXT_PROFILES]).annotate(
        identity_label=Case(*labels, default=F("label"), output_field=TextField()),
        identity_definition=Case(*descriptions, default=F("definition"), output_field=TextField()))
    if query:
        lookup = "iexact" if exact else "icontains"
        from .query_lexicon.registry import FORMAL_PERSON_VARIANT_SOURCES, FORMAL_KNOWLEDGE_ALIAS_SOURCES
        aliases = independent_aliases(m.EntityAlias.objects.filter(entity_id=OuterRef("pk"), review_status="confirmed",
            **{f"text__{lookup}": query}))
        people = m.PersonNameVariant.objects.filter(person_id=OuterRef("person_id"), is_verified=True, **{f"name__{lookup}": query})
        nodes = m.KnowledgeNodeAlias.objects.filter(node_id=OuterRef("node_id"), is_verified=True, **{f"alias__{lookup}": query})
        if public:
            people = people.filter(displayable=True, source_kind__in=FORMAL_PERSON_VARIANT_SOURCES)
            nodes = nodes.filter(source_kind__in=FORMAL_KNOWLEDGE_ALIAS_SOURCES)
        rows = rows.annotate(identity_alias_match=Exists(aliases), person_alias_match=Exists(people), node_alias_match=Exists(nodes))
        condition = Q(**{f"identity_label__{lookup}": query}) | Q(identity_alias_match=True) | Q(person_alias_match=True) | Q(node_alias_match=True)
        if definitions:
            condition |= Q(identity_definition__icontains=query)
        rows = rows.filter(condition)
    return rows.distinct().order_by("identity_label", "pk")


def mentioned_entities(query, rows, *, limit=8):
    """Bounded published identity seeds, including confirmed profile aliases.

    A matching name is a retrieval hint, not an identity merge. Homonyms retain
    distinct IDs. Single-character aliases cannot expand arbitrary questions.
    """
    from django.db.models import Value
    from django.db.models.functions import Length, Lower, StrIndex
    from .query_lexicon.registry import FORMAL_PERSON_VARIANT_SOURCES, FORMAL_KNOWLEDGE_ALIAS_SOURCES
    query = str(query).strip()
    if not query or len(query) > 2000:
        return []
    def contains_label(source, field):
        return source.annotate(mention_length=Length(field),
            mention_position=StrIndex(Lower(Value(query)), Lower(F(field)))).filter(
                mention_length__gte=2, mention_position__gt=0)
    aliases = contains_label(independent_aliases(m.EntityAlias.objects.filter(
        entity_id=OuterRef("pk"), review_status="confirmed")), "text")
    people = contains_label(m.PersonNameVariant.objects.filter(person_id=OuterRef("person_id"),
        is_verified=True, displayable=True, source_kind__in=FORMAL_PERSON_VARIANT_SOURCES), "name")
    nodes = contains_label(m.KnowledgeNodeAlias.objects.filter(node_id=OuterRef("node_id"),
        is_verified=True, source_kind__in=FORMAL_KNOWLEDGE_ALIAS_SOURCES), "alias")
    matches = entity_query(rows, public=True).annotate(
        mention_length=Length("identity_label"), mention_position=StrIndex(Lower(Value(query)), Lower("identity_label")),
        alias_mentioned=Exists(aliases), person_mentioned=Exists(people), node_mentioned=Exists(nodes)
    ).filter(Q(mention_length__gte=2, mention_position__gt=0) | Q(alias_mentioned=True)
        | Q(person_mentioned=True) | Q(node_mentioned=True)).order_by("-mention_length", "pk")
    # Identity selection needs no biographies/definitions from nine joined
    # profile tables. Load the small selected identity set afterwards.
    ids = list(matches.values_list("pk", flat=True)[:limit])
    selected = m.Entity.objects.only("id", "kind", "label").in_bulk(ids)
    return [selected[key] for key in ids if key in selected]
