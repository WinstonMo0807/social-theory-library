"""Read-only authority duplicate discovery and Person merge impact previews.

Previewing never merges identities or starts publication/index work. The
explicit inventory is also a guard against silently overlooking new FKs.
"""
from hashlib import sha256
import json
import re

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import FileField, Q, UniqueConstraint

from catalog import models
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.query_lexicon.sync import QueryLexiconInvariantError, _validate_state


PREVIEW_VERSION = "person-resolution-preview-v1"
REFERENCE_LIMIT = 500
PERSON_REFERENCES = (
    (models.Person, "merged_into", "已有合并来源"),
    (models.PersonNameVariant, "person", "规范名称变体"),
    (models.ScholarProfile, "person", "学者档案"),
    (models.Contribution, "person", "书目贡献关系"),
    (models.PersonKnowledgeRelation, "person", "旧知识关系"),
    (models.PersonSubdisciplineRelation, "person", "子学科关系"),
    (models.PersonDisciplineRelation, "person", "学科关系"),
    (models.PersonTopicRelation, "person", "主题关系"),
    (models.PersonNodeRelation, "person", "知识节点关系"),
)
PROFILE_REFERENCES = (
    (models.TheoryTimelineEvent, "scholar", "学者时间线事件"),
    (models.TimelineEventRelation, "scholar", "时间线关联"),
    (models.CuratedClaim, "scholar", "人工策展观点"),
    (models.RecommendationItem, "scholar", "推荐快照项目"),
    (models.RecommendationOverride, "scholar", "推荐人工设置"),
)


def _json(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True))


def _record(instance):
    if instance is None:
        return None
    values = {}
    for field in instance._meta.concrete_fields:
        value = getattr(instance, field.attname)
        values[field.attname] = value.name if isinstance(field, FileField) else value
    return _json(values)


def _assert_inventory():
    for owner, registry in ((models.Person, PERSON_REFERENCES), (models.ScholarProfile, PROFILE_REFERENCES)):
        actual = {(relation.related_model._meta.label, relation.field.name) for relation in owner._meta.related_objects}
        declared = {(model._meta.label, field) for model, field, _label in registry}
        if actual != declared:
            raise ValueError("人物引用结构已经变化，请先更新合并影响预览。")


def _summary(person):
    return {
        "id": str(person.pk), "preferred_name": person.preferred_name,
        "original_name": person.original_name, "birth_year": person.birth_year,
        "death_year": person.death_year, "authority_status": person.authority_status,
    }


def _names(person):
    values = [person.preferred_name, person.original_name]
    values.extend(row.name for row in person.name_variants.all() if row.is_verified)
    return {normalize_term(value) for value in values if str(value or "").strip()}


def _identifiers(person):
    return {
        str(scheme): str(value).strip()
        for scheme, value in (person.external_ids or {}).items()
        if isinstance(value, (str, int)) and not isinstance(value, bool)
        and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,40}", str(scheme))
        and "__" not in str(scheme) and str(value).strip()
    }


def _identity_conflicts(source, target):
    if target is None:
        return []
    issues = []
    for field in ("birth_year", "death_year"):
        left, right = getattr(source, field), getattr(target, field)
        if left is not None and right is not None and left != right:
            issues.append({"field": field, "source": left, "target": right})
    left_ids, right_ids = _identifiers(source), _identifiers(target)
    for scheme in sorted(left_ids.keys() & right_ids.keys()):
        if left_ids[scheme] != right_ids[scheme]:
            issues.append({"field": f"external_ids.{scheme}", "source": left_ids[scheme], "target": right_ids[scheme]})
    return issues


def duplicate_people(source, *, limit=10):
    """Bounded exact-name/identifier hints, never an identity decision."""
    limit = max(1, min(int(limit), 50))
    source_names = _names(source)
    condition = Q(pk__in=[])
    original_names = [source.preferred_name, source.original_name]
    original_names.extend(row.name for row in source.name_variants.all() if row.is_verified)
    for name in list(dict.fromkeys(name for name in original_names if name))[:20]:
        condition |= Q(preferred_name__iexact=name) | Q(original_name__iexact=name)
    if source_names:
        condition |= Q(name_variants__normalized_name__in=sorted(source_names)[:20], name_variants__is_verified=True)
    source_ids = _identifiers(source)
    for scheme, value in list(sorted(source_ids.items()))[:20]:
        # An explicit final lookup keeps reserved words such as 'isnull' or
        # 'contains' as JSON keys, never as user-selected query operators.
        lookup = f"external_ids__{scheme}__exact"
        condition |= Q(**{lookup: value})
        # Older authority imports can store integer IDs rather than strings.
        # Preserve significant leading zeros and avoid oversized SQL integers.
        if value.isdecimal() and len(value) <= 18 and str(int(value)) == value:
            condition |= Q(**{lookup: int(value)})
    rows = list(models.Person.objects.filter(condition).exclude(pk=source.pk).exclude(
        authority_status__in=["merged", "archived", "rejected"],
    ).prefetch_related("name_variants").distinct().order_by("preferred_name", "pk")[:limit + 1])
    candidates = []
    for candidate in rows[:limit]:
        matches = []
        shared_names = sorted(source_names & _names(candidate))
        if shared_names:
            matches.append({"kind": "name", "values": shared_names})
        candidate_ids = _identifiers(candidate)
        shared_ids = sorted(scheme for scheme, value in source_ids.items() if candidate_ids.get(scheme) == value)
        if shared_ids:
            matches.append({"kind": "external_identifier", "values": shared_ids})
        candidates.append({"person": _summary(candidate), "matches": matches, "identity_conflicts": _identity_conflicts(source, candidate)})
    return {
        "source": _summary(source), "results": candidates, "limit": limit,
        "has_more": len(rows) > limit, "automatic_merge": False,
        "matching_policy": "exact_authority_names_and_identifiers; human_review_required",
    }


def _bounded_rows(queryset, *, fields=()):
    rows = list(queryset.order_by("pk").values(*fields)[:REFERENCE_LIMIT + 1])
    truncated = len(rows) > REFERENCE_LIMIT
    return _json(rows[:REFERENCE_LIMIT]), queryset.count() if truncated else len(rows), truncated


def _unique_keys(model, field):
    if model._meta.get_field(field).unique:
        return [()]
    keys = []
    for constraint in model._meta.constraints:
        if isinstance(constraint, UniqueConstraint) and field in constraint.fields and constraint.condition is None:
            keys.append(tuple(model._meta.get_field(name).attname for name in constraint.fields if name != field))
    return keys


def _reference_group(model, field, label, source_id, target_id):
    column = model._meta.get_field(field).attname
    source_rows, source_count, source_truncated = _bounded_rows(model.objects.filter(**{column: source_id}) if source_id else model.objects.none())
    target_rows, target_count, target_truncated = _bounded_rows(model.objects.filter(**{column: target_id}) if target_id else model.objects.none())
    collisions = []
    seen_pairs = set()
    for keys in _unique_keys(model, field):
        targets = {tuple(row.get(key) for key in keys): row for row in target_rows}
        for row in source_rows:
            match = targets.get(tuple(row.get(key) for key in keys))
            if match is None or (row["id"], match["id"]) in seen_pairs:
                continue
            seen_pairs.add((row["id"], match["id"]))
            differences = [
                key for key in row if key not in {"id", column, "created_at", "updated_at"}
                and row.get(key) != match.get(key)
            ]
            collisions.append({"source_id": row["id"], "target_id": match["id"], "different_fields": differences})
    return {
        "model": model._meta.label, "field": field, "label": label,
        "source_count": source_count, "target_count": target_count,
        "source_rows": source_rows, "target_rows": target_rows, "collisions": collisions,
        "truncated": source_truncated or target_truncated,
    }


def _lexicon_preview(source, target):
    # Do not call ensure_query_lexicon_state here: a preview is not authorized
    # to initialize a generation or repair a broken serving pointer.
    state = models.QueryLexiconState.objects.select_related("active_generation").filter(key="default").first()
    payload = {
        "scope": "active_generation", "available": False, "status": "not_initialized",
        "generation_id": None, "revision": None,
        "normalization_version": "", "source_registry_version": "",
        "source": 0, "target": 0, "source_rows": [], "target_rows": [],
        "truncated": False, "error": "",
    }
    if state is None:
        return payload
    payload.update(
        generation_id=str(state.active_generation_id), revision=state.revision,
        normalization_version=state.normalization_version,
        source_registry_version=state.source_registry_version,
    )
    try:
        _validate_state(state)
    except QueryLexiconInvariantError as error:
        payload.update(status="inconsistent", error=str(error))
        return payload
    fields = (
        "id", "entity_id", "term", "normalized_term", "language", "term_type",
        "source_kind", "trust_level", "source_ref", "displayable", "public_active", "admin_resolvable",
    )
    entries = models.QueryLexiconEntry.objects.filter(generation_id=state.active_generation_id, entity_type="person")
    for side, person in (("source", source), ("target", target)):
        rows, count, truncated = _bounded_rows(
            entries.filter(entity_id=person.pk) if person else entries.none(), fields=fields,
        )
        payload[side] = count
        payload[f"{side}_rows"] = rows
        payload["truncated"] = payload["truncated"] or truncated
    payload.update(available=True, status="ready")
    return payload


def person_merge_preview(source, target=None):
    _assert_inventory()
    if target is not None and source.pk == target.pk:
        raise ValueError("来源人物和保留人物不能相同。")
    source_profile = models.ScholarProfile.objects.filter(person=source).first()
    target_profile = models.ScholarProfile.objects.filter(person=target).first() if target else None
    groups = [_reference_group(model, field, label, source.pk, target.pk if target else None) for model, field, label in PERSON_REFERENCES]
    groups.extend(
        _reference_group(model, field, label, source_profile.pk if source_profile else None, target_profile.pk if target_profile else None)
        for model, field, label in PROFILE_REFERENCES
    )
    contribution_group = next(group for group in groups if group["model"] == "catalog.Contribution")
    edition_ids = {row["edition_id"] for row in contribution_group["source_rows"]}
    work_ids = {
        row["work_id"] for group in groups for row in group["source_rows"] if row.get("work_id")
    }
    editions = models.Edition.objects.filter(Q(pk__in=edition_ids) | Q(work_id__in=work_ids))
    affected_editions, edition_count, editions_truncated = _bounded_rows(
        editions, fields=("id", "work_id", "state", "public_slug", "publication_mode", "active_catalog_revision_id", "updated_at"),
    )
    work_ids.update(row["work_id"] for row in affected_editions)
    works = list(models.Work.objects.filter(pk__in=work_ids).order_by("pk").values("id", "title", "document_type"))
    revisions, revision_count, revisions_truncated = _bounded_rows(
        models.CatalogPublicationRevision.objects.filter(edition__in=editions),
        fields=("id", "edition_id", "revision", "status"),
    )
    # Historical full snapshots may contain much more text than an impact
    # summary needs. They remain untouched; only identities/states are shown.
    revisions = [{key: row[key] for key in ("id", "edition_id", "revision", "status")} for row in revisions]
    profile_ids = [profile.pk for profile in (source_profile, target_profile) if profile]
    drafts = models.EditorialRevision.objects.filter(status="draft").filter(
        Q(target_type="scholar_profile", target_id__in=profile_ids)
        | Q(target_type="work", target_id__in=work_ids)
        | Q(target_type="edition", target_id__in=edition_ids)
    )
    pending_drafts = list(drafts.order_by("pk").values("id", "target_type", "target_id", "updated_at")[:REFERENCE_LIMIT + 1])
    lexicon = _lexicon_preview(source, target)
    issues = []
    if source.authority_status in {"merged", "rejected", "archived"}:
        issues.append({"code": "source_not_active", "detail": "来源人物当前状态需要先处理。"})
    if target and target.authority_status != "verified":
        issues.append({"code": "target_not_verified", "detail": "保留人物尚未核验。"})
    if source_profile and target_profile:
        issues.append({"code": "two_scholar_profiles", "detail": "双方都有学者档案，需要明确保留内容及引用处理。"})
    if pending_drafts:
        issues.append({"code": "pending_editorial_drafts", "detail": "受影响对象仍有编辑草稿。"})
    if any(row["status"] == "preparing" for row in revisions):
        issues.append({"code": "publication_preparing", "detail": "受影响书目仍有正在准备的公开修订。"})
    if not lexicon["available"]:
        issues.append({"code": "lexicon_unavailable", "detail": lexicon["error"] or "词典尚未初始化，当前检索影响待核实。"})
    truncated = (
        any(group["truncated"] for group in groups) or editions_truncated or revisions_truncated
        or len(pending_drafts) > REFERENCE_LIMIT or lexicon["truncated"]
    )
    complete = not truncated and lexicon["available"]
    if truncated:
        issues.append({"code": "bounded_preview", "detail": "影响范围超过本次预览上限，当前列表不完整。"})
    payload = _json({
        "version": PREVIEW_VERSION, "source": _record(source), "target": _record(target),
        "source_profile": _record(source_profile), "target_profile": _record(target_profile),
        "references": groups, "affected_works": works, "affected_editions": affected_editions,
        "affected_edition_count": edition_count, "publication_revisions": revisions,
        "publication_revision_count": revision_count, "editorial_drafts": pending_drafts[:REFERENCE_LIMIT],
        "identity_conflicts": _identity_conflicts(source, target), "review_issues": issues,
        "lexicon_entries": lexicon,
        "complete_reference_listing": complete,
        "merge_execution_available": False,
        "coverage": {"person_fk_types": len(PERSON_REFERENCES), "profile_fk_types": len(PROFILE_REFERENCES),
                     "generic_candidate_payloads": "not_retargeted_or_exhaustively_scanned", "reader_private_data": "not_read"},
        "preservation": ["source_person", "original_files", "historical_publication_snapshots", "reader_private_data", "unreviewed_candidates"],
    })
    payload["fingerprint"] = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return payload
