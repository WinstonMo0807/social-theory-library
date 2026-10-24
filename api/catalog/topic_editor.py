"""Topic organization on existing identities, relations and publication snapshots."""
from copy import copy
from uuid import NAMESPACE_URL, uuid5

from django.db.models import Count, Q
from rest_framework.exceptions import ValidationError

from catalog.models import Topic
from catalog.services import public_topics
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock


def lock_topic_hierarchy():
    # ponytail: serialize this small editorial hierarchy; no second graph store.
    acquire_generation_lock(shared=True)
    acquire_entity_lock("topic_hierarchy", uuid5(NAMESPACE_URL, "stl:topic-hierarchy"))


def topic_content_counts(topic):
    from catalog.services.editorial_issues import published_issues
    curated = topic.curation if isinstance(topic.curation, dict) else {}
    return {"works": public_topics._editions(topic).count(),
            "scholars": public_topics._scholars(topic).count(),
            "knowledge": public_topics._nodes(topic, ("research_problem", "debate", "concept")).count(),
            "articles": published_issues().filter(pk__in=public_topics._ids(curated.get("issue_ids"))).count()}


def ensure_topic_publication(topic):
    public_topics.validate_topic_parent(topic, topic.parent_id)
    if not any(topic_content_counts(topic).values()):
        raise ValidationError({"publication": "尚无可公开的关联内容。请至少关联一部作品、一位学者、一个知识条目或一篇策划，再发布主题。"})


def organization_rows(query="", parent="", *, exclude=None):
    rows = Topic.objects.exclude(curation__has_key="topic_merge").annotate(children_count=Count("children", filter=~Q(children__curation__has_key="topic_merge"), distinct=True))
    if exclude:
        rows = rows.exclude(pk=exclude)
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(search_aliases__icontains=query))
    elif parent:
        rows = rows.filter(parent_id=public_topics._uuid(parent))
    else:
        rows = rows.filter(parent__isnull=True)
    return rows.order_by("name", "pk")


def topic_organization_preview(topic, data):
    proposed = copy(topic)
    if "parent" in data:
        proposed.parent_id = data["parent"]
    if "curation" in data:
        proposed.curation = {**(topic.curation or {}), **public_topics.validate_topic_curation(data["curation"], topic)}
    parent_check = public_topics.inspect_topic_parent(topic, proposed.parent_id)
    errors = [{"field": "parent", "detail": parent_check["problem"]}] if parent_check["problem"] else []
    # Enumerate only identifiers/counts; never reader SavedTopic/User rows.
    descendants, frontier, seen = [], [topic.pk], {topic.pk}
    while frontier:
        children = list(Topic.objects.filter(parent_id__in=frontier).values_list("pk", flat=True))
        frontier = [identifier for identifier in children if identifier not in seen]
        seen.update(frontier); descendants.extend(frontier)
        if len(descendants) > 10000:
            raise ValidationError("主题层级超过当前预览范围，请缩小调整范围后核对。")
    counts = topic_content_counts(proposed)
    return {"topic_id": str(topic.pk), "parent_id": str(proposed.parent_id) if proposed.parent_id else None,
            "parent_changed": str(proposed.parent_id or "") != str(topic.parent_id or ""), "descendant_count": len(descendants),
            "parent_path": parent_check["parent_path"], "cycle_path": parent_check["cycle_path"],
            "public_descendant_count": Topic.objects.filter(pk__in=descendants, editorial_status="published").count(),
            "content_counts": counts, "can_publish": bool(any(counts.values())) and not errors, "problems": errors}


def topic_selection_labels(topic):
    from catalog.models import Edition, KnowledgeNode, ScholarProfile, ReadingPath, RecommendationIssue
    curated = topic.curation if isinstance(topic.curation, dict) else {}
    result = {}
    groups = ((Edition, ("edition_ids", "foundational_edition_ids", "disputed_edition_ids"), "work__title"),
              (KnowledgeNode, ("question_node_ids", "debate_node_ids", "concept_node_ids"), "canonical_name_zh"),
              (ScholarProfile, ("related_scholar_ids",), "person__preferred_name"),
              (ReadingPath, ("reading_path_ids",), "title"), (RecommendationIssue, ("issue_ids",), "title"))
    for model, keys, label in groups:
        identifiers = [identifier for key in keys for identifier in public_topics._ids(curated.get(key))[:200]]
        result.update({str(identifier): title for identifier, title in model.objects.filter(pk__in=identifiers).values_list("pk", label)})
    if topic.parent_id:
        result.update({str(identifier): name for identifier, name in Topic.objects.filter(pk=topic.parent_id).values_list("pk", "name")})
    return result
