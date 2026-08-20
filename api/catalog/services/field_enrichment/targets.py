from __future__ import annotations

from typing import Any

from catalog.models import (
    Discipline,
    Edition,
    KnowledgeNode,
    Person,
    ReadingPath,
    Subdiscipline,
    Topic,
    Work,
)
from catalog.services.query_lexicon.normalization import normalize_term


TARGET_MODELS = {
    "person": Person,
    "work": Work,
    "edition": Edition,
    "discipline": Discipline,
    "subdiscipline": Subdiscipline,
    "knowledge_node": KnowledgeNode,
    "topic": Topic,
    "reading_path": ReadingPath,
}


def get_target(target_type: str, target_id, *, for_update: bool = False):
    target_type = str(target_type or "").strip().casefold()
    model = TARGET_MODELS.get(target_type)
    if model is None:
        raise ValueError("不支持的联网补全 target type。")
    queryset = model.objects.all()
    if target_type == "edition":
        queryset = queryset.select_related("work")
    elif target_type == "person":
        queryset = queryset.select_related("scholar_profile")
    if for_update:
        # Only the authority row is the mutation lock.  Person's optional
        # ScholarProfile reverse relation may be a LEFT OUTER JOIN.
        queryset = queryset.select_for_update(of=("self",))
    try:
        return queryset.get(pk=target_id)
    except model.DoesNotExist as exc:
        raise ValueError("联网补全目标不存在或已被删除。") from exc


def canonical_terms(target_type: str, target) -> list[str]:
    values: list[str] = []
    if target_type == "person":
        values.extend([target.preferred_name, target.original_name])
        values.extend(
            target.name_variants.filter(is_verified=True).values_list("name", flat=True)
        )
    elif target_type == "work":
        values.extend([target.title, target.original_title, target.uniform_title])
    elif target_type == "edition":
        values.extend(
            [target.work.title, target.work.original_title, target.work.uniform_title]
        )
    elif target_type == "knowledge_node":
        values.extend([target.canonical_name_zh, target.canonical_name_en])
        values.extend(target.aliases.values_list("alias", flat=True))
    elif target_type in {"discipline", "subdiscipline", "topic"}:
        values.extend([target.name, getattr(target, "foreign_name", "")])
    elif target_type == "reading_path":
        values.append(target.title)
    output = []
    seen = set()
    for value in values:
        normalized = normalize_term(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(str(value).strip())
    return output


def current_field_value(target_type: str, target, field_name: str) -> Any:
    if target_type == "person":
        if field_name == "external_identifier":
            return target.external_ids or {}
        if field_name == "affiliation":
            profile = getattr(target, "scholar_profile", None)
            return list(profile.affiliations or []) if profile else []
        if field_name == "name_variant":
            return list(
                target.name_variants.values(
                    "name", "language", "variant_type", "is_verified"
                )
            )
    if target_type == "edition" and field_name in {
        "version_label",
        "publication_year",
        "publisher",
        "publication_place",
        "journal_title",
        "volume",
        "issue",
        "page_range",
        "degree_institution",
        "degree_type",
        "report_institution",
        "isbn",
        "isbn10",
        "isbn13",
        "doi",
        "series",
        "extent",
        "responsibility_statement",
    }:
        return getattr(target, field_name)
    if target_type == "work":
        if field_name == "first_publication_date":
            return target.first_publication_date.isoformat() if target.first_publication_date else ""
        if field_name in {
            "title",
            "subtitle",
            "original_title",
            "uniform_title",
            "language",
            "original_language",
            "abstract",
        }:
            return getattr(target, field_name)
        if field_name == "discipline":
            return list(target.discipline_relations.values("discipline_id", "is_primary", "review_status"))
        if field_name == "subdiscipline":
            return list(target.subdiscipline_relations.values("subdiscipline_id", "is_primary", "review_status"))
    if target_type in {"discipline", "subdiscipline"} and field_name == "foreign_name":
        return target.foreign_name
    if target_type == "knowledge_node":
        if field_name == "alias":
            return list(target.aliases.values("alias", "language", "alias_type"))
        if field_name == "discipline":
            return list(
                target.discipline_links.values(
                    "discipline_id", "relation_type", "status"
                )
            )
        if field_name == "subdiscipline":
            return str(target.parent_id or "")
        if field_name == "relation":
            return list(
                target.outgoing_relations.values(
                    "target_node_id", "relation_type", "status"
                )
            )
        if field_name in {"timeline_fact", "timeline_interpretation"}:
            return []
    if target_type == "topic" and field_name == "discipline":
        return list(target.discipline_relations.values("discipline_id", "review_status"))
    if target_type == "reading_path" and field_name == "item":
        return list(target.items.values("node_id", "work_id", "reading_order"))
    return None


def target_context(target_type: str, target) -> dict[str, Any]:
    context: dict[str, Any] = {
        "target_type": target_type,
        "target_id": str(target.pk),
        "canonical_terms": canonical_terms(target_type, target),
    }
    if target_type == "person":
        profile = getattr(target, "scholar_profile", None)
        context.update(
            {
                "name": target.preferred_name,
                "original_name": target.original_name,
                "birth_year": target.birth_year,
                "death_year": target.death_year,
                "external_ids": target.external_ids or {},
                "affiliations": list(profile.affiliations or []) if profile else [],
                "works": list(
                    target.contributions.filter(approved=True)
                    .values_list("edition__work__title", flat=True)
                    .distinct()[:12]
                ),
            }
        )
    elif target_type == "edition":
        context.update(
            {
                "title": target.work.title,
                "original_title": target.work.original_title,
                "publication_year": target.publication_year,
                "publisher": target.publisher,
                "isbn": target.isbn,
                "doi": target.doi,
                "authors": list(
                    target.contributions.filter(approved=True)
                    .order_by("order")
                    .values_list("person__preferred_name", flat=True)[:12]
                ),
            }
        )
    elif target_type == "work":
        context.update(
            {
                "title": target.title,
                "original_title": target.original_title,
                "first_publication_date": (
                    target.first_publication_date.isoformat()
                    if target.first_publication_date
                    else ""
                ),
            }
        )
    elif target_type == "knowledge_node":
        context.update(
            {
                "name": target.canonical_name_zh,
                "original_name": target.canonical_name_en,
                "node_type": target.node_type,
                "primary_discipline_id": str(target.primary_discipline_id or ""),
                "external_ids": getattr(target, "external_ids", {}) or {},
            }
        )
    elif target_type in {"discipline", "subdiscipline", "topic"}:
        context.update(
            {
                "name": target.name,
                "original_name": getattr(target, "foreign_name", ""),
            }
        )
    elif target_type == "reading_path":
        context.update(
            {
                "title": target.title,
                "primary_discipline_id": str(target.primary_discipline_id or ""),
            }
        )
    return context
