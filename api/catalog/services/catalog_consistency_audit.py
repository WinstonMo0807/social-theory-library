from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Iterable

from django.apps import apps
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from catalog import models as catalog_models
from catalog.models import (
    CatalogPublicationRevision,
    Contribution,
    Edition,
    EnrichmentCandidate,
    KnowledgeNode,
    Person,
    ProjectionState,
    PublicationState,
    QueryLexiconEntry,
    QueryLexiconState,
    SemanticChunk,
    TheorySchool,
    Topic,
)
from catalog.services.publication_eligibility import active_document_q
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.query_lexicon.registry import (
    SOURCE_REGISTRY_VERSION,
    EntityKey,
    build_entity,
)
from ingestion.models import EntityResolutionCandidate, MetadataCandidate


AUDIT_SCHEMA_VERSION = "catalog-consistency-audit-v304"

CORE_MODELS = {
    "work": catalog_models.Work, "edition": Edition, "person": Person,
    "scholar_profile": catalog_models.ScholarProfile, "topic": Topic,
    "knowledge_node": KnowledgeNode, "theory_school": TheorySchool,
    "discipline": catalog_models.Discipline, "subdiscipline": catalog_models.Subdiscipline,
    "reading_path": catalog_models.ReadingPath, "publisher": catalog_models.PublisherAuthority,
}


def _database_inventory() -> dict[str, Any]:
    """Inspect physical schema first so an unmigrated database is not called clean."""
    available = set(connection.introspection.table_names())
    core = set(CORE_MODELS.values())
    models = [model for model in apps.get_models() if model._meta.app_label in {
        "catalog", "ingestion", "reading", "accounts", "distribution", "common",
    }]
    entries = []
    for model in models:
        table = model._meta.db_table
        exists = table in available
        columns = set()
        if exists:
            with connection.cursor() as cursor:
                columns = {column.name for column in connection.introspection.get_table_description(cursor, table)}
        missing = [field.column for field in model._meta.local_concrete_fields if field.column not in columns]
        entries.append({"model": model._meta.label, "table": table, "table_present": exists,
                        "row_count": model._base_manager.count() if exists else None,
                        "missing_columns": missing,
                        "references": [{"field": field.name, "target": field.related_model._meta.label,
                                        "nullable": field.null, "on_delete": field.remote_field.on_delete.__name__}
                                       for field in model._meta.concrete_fields if field.is_relation and field.related_model in core]})
    return {"tables": entries, "source_schema_compatible": all(row["table_present"] and not row["missing_columns"] for row in entries)}


def _formal_ids() -> dict[type, set]:
    result = {}
    for model in set(CORE_MODELS.values()):
        if model is catalog_models.Work:
            rows = model.objects.filter(editions__state="published").distinct()
        elif model is Edition:
            rows = model.objects.filter(state="published")
        elif model is Person:
            rows = model.objects.filter(authority_status="verified")
        elif model is catalog_models.ScholarProfile:
            rows = model.objects.filter(editorial_status="published", person__authority_status="verified")
        elif any(field.name == "editorial_status" for field in model._meta.fields):
            rows = model.objects.filter(editorial_status="published")
        else:
            rows = model.objects.filter(status="published")
        result[model] = set(rows.values_list("pk", flat=True))
    return result


def _missing_foreign_key_references() -> Iterable[dict[str, Any]]:
    core = set(CORE_MODELS.values())
    for model in apps.get_app_config("catalog").get_models():
        for field in model._meta.concrete_fields:
            if not field.is_relation or field.related_model not in core:
                continue
            rows = model._base_manager.exclude(**{f"{field.attname}__isnull": True}).exclude(
                **{f"{field.attname}__in": field.related_model._base_manager.values("pk")}
            ).values_list("pk", field.attname)
            for identifier, target_id in rows.iterator(chunk_size=500):
                yield {"model": model._meta.label, "object_id": identifier, "field": field.name,
                       "target_id": target_id, "problem": "真实外键引用对象不存在"}


def _formal_entity_requirements() -> Iterable[dict[str, Any]]:
    formal = _formal_ids()
    for kind, model in CORE_MODELS.items():
        for row in model.objects.filter(pk__in=formal[model]).iterator(chunk_size=250):
            label = next((str(getattr(row, name) or "").strip() for name in (
                "title", "preferred_name", "canonical_name_zh", "canonical_name", "name",
            ) if hasattr(row, name)), None)
            if label is not None and not label:
                yield {"object_type": kind, "object_id": row.pk, "problem": "正式对象缺少名称"}
            for field in model._meta.concrete_fields:
                if field.is_relation and field.related_model in formal and field.name in {"parent", "discipline", "primary_discipline", "translation_of", "publisher_authority"}:
                    target_id = getattr(row, field.attname)
                    if target_id and target_id not in formal[field.related_model]:
                        yield {"object_type": kind, "object_id": row.pk, "field": field.name,
                               "target_id": target_id, "problem": "正式对象引用了未发布的规范对象"}
    for profile in catalog_models.ScholarProfile.objects.filter(editorial_status="published").exclude(person__authority_status="verified"):
        yield {"object_type": "scholar_profile", "object_id": profile.pk, "person_id": profile.person_id,
               "problem": "学者资料已发布但人物尚未确认，公开资格不一致"}


def _formal_relation_endpoint_issues() -> Iterable[dict[str, Any]]:
    formal = _formal_ids()
    owners = ("edition", "work", "reading_path", "person", "node", "source_node", "topic", "theory_school")
    for model in apps.get_app_config("catalog").get_models():
        fields = {field.name: field for field in model._meta.concrete_fields}
        endpoints = [field for field in fields.values() if field.is_relation and field.related_model in formal]
        if len(endpoints) < 2 or model in formal:
            continue
        owner = next((fields[name] for name in owners if name in fields and fields[name] in endpoints), None)
        if owner is None:
            continue
        if "review_status" in fields:
            rows = model.objects.filter(review_status="approved")
        elif "status" in fields and any(value == "published" for value, _ in (fields["status"].choices or ())):
            rows = model.objects.filter(status="published")
        elif model is Contribution:
            rows = model.objects.filter(approved=True)
        elif model is catalog_models.ReadingPathItem:
            rows = model.objects.all()
        else:
            continue
        rows = rows.filter(**{f"{owner.attname}__in": formal[owner.related_model]})
        for row in rows.iterator(chunk_size=250):
            for field in endpoints:
                identifier = getattr(row, field.attname)
                if identifier is not None and identifier not in formal[field.related_model]:
                    yield {"model": model._meta.label, "relation_id": row.pk, "field": field.name,
                           "target_id": identifier, "problem": "正式对象的已确认关系仍指向非正式对象"}


def _bibliographic_conflicts() -> Iterable[dict[str, Any]]:
    grouped = defaultdict(list)
    for edition in Edition.objects.select_related("work").order_by("pk").iterator(chunk_size=250):
        if edition.state == "published" and not edition.work.title.strip():
            yield {"edition_id": edition.pk, "work_id": edition.work_id, "problem": "已发布作品题名为空"}
        if edition.publication_date and edition.publication_year and edition.publication_date.year != edition.publication_year:
            yield {"edition_id": edition.pk, "problem": "版本年份与出版日期不一致",
                   "publication_year": edition.publication_year, "publication_date": edition.publication_date}
        identifiers = set()
        for name in ("isbn", "isbn10", "isbn13"):
            value = re.sub(r"[^0-9Xx]", "", str(getattr(edition, name) or "")).upper()
            if value:
                identifiers.add(("isbn", value))
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", edition.doi.strip(), flags=re.I).casefold()
        if doi:
            identifiers.add(("doi", doi))
        for kind, value in identifiers:
            grouped[(kind, value)].append({"edition_id": str(edition.pk), "work_id": str(edition.work_id), "title": edition.work.title})
    for (kind, value), editions in grouped.items():
        if len(editions) > 1:
            yield {"identifier_type": kind, "identifier": value, "editions": editions,
                   "problem": "多个版本共享规范标识，需区分重复记录与合法复本"}


def _bundle_and_revision_issues() -> Iterable[dict[str, Any]]:
    formal = _formal_ids()
    for item in catalog_models.PublicationBundleItem.objects.select_related("bundle").order_by("pk").iterator(chunk_size=250):
        model = CORE_MODELS.get(item.object_type)
        exists = model is not None and model.objects.filter(pk=item.object_id).exists()
        problem = "" if exists else "发布包对象类型不受支持或引用不存在"
        if exists and item.bundle.status == "published" and item.action != "withdraw" and not (item.snapshot or {}).get("excluded_from_publication") and item.object_id not in formal[model]:
            withdrawn_later = catalog_models.KnowledgePublicationEvent.objects.filter(
                object_type=item.object_type, object_id=item.object_id,
                payload__provenance__withdrawal=True, created_at__gte=item.created_at,
            ).exists()
            if not withdrawn_later:
                problem = "已发布包对象目前非正式，且没有后续撤回事件"
        if problem:
            yield {"bundle_id": item.bundle_id, "item_id": item.pk, "object_type": item.object_type,
                   "object_id": item.object_id, "problem": problem}
    for edition in Edition.objects.select_related("active_catalog_revision__reader_asset", "active_catalog_revision__document_revision__asset").order_by("pk").iterator(chunk_size=250):
        revision = edition.active_catalog_revision
        if revision is None:
            continue
        problems = []
        if revision.edition_id != edition.pk:
            problems.append("活动修订属于其他版本")
        if edition.state != "published" and revision.status == "active":
            problems.append("未发布版本仍指向活动修订")
        if revision.reader_asset_id and revision.reader_asset.edition_id != edition.pk:
            problems.append("活动阅读文件属于其他版本")
        if revision.document_revision_id and revision.document_revision.asset_id != revision.reader_asset_id:
            problems.append("活动正文与阅读文件不对应")
        if revision.fulltext_ready and not revision.document_revision_id:
            problems.append("正文就绪却没有正文修订")
        for problem in problems:
            yield {"edition_id": edition.pk, "catalog_revision_id": revision.pk, "problem": problem}
    for item in catalog_models.ReadingPathItem.objects.select_related("stage").order_by("pk").iterator(chunk_size=250):
        if (not item.node_id and not item.work_id) or (item.stage_id and item.stage.reading_path_id != item.reading_path_id):
            yield {"reading_path_id": item.reading_path_id, "item_id": item.pk, "problem": "阅读路径项目缺少对象或分组属于其他路径"}


def _field_decision_issues() -> Iterable[dict[str, Any]]:
    from catalog.services.field_decisions import formal_field_values, field_value_present

    for edition in Edition.objects.filter(field_decisions__status__in=["confirmed", "not_applicable"]).distinct().order_by("pk"):
        values, _manual = formal_field_values(edition)
        for decision in edition.field_decisions.filter(status__in=["confirmed", "not_applicable"]):
            if decision.field_name not in values:
                continue
            actual = values[decision.field_name]
            if (decision.status == "confirmed" and not field_value_present(actual)) or (decision.status == "not_applicable" and field_value_present(actual)):
                yield {"edition_id": edition.pk, "decision_id": decision.pk, "field": decision.field_name,
                       "status": decision.status, "problem": "人工字段状态与真实草稿值不一致"}


def _publication_delivery_issues() -> Iterable[dict[str, Any]]:
    events = catalog_models.KnowledgePublicationEvent.objects.select_related("catalog_revision", "domain_event").prefetch_related("deliveries").order_by("pk")
    for event in events.iterator(chunk_size=250):
        problems = []
        deliveries = list(event.deliveries.all())
        if event.event_type.startswith("catalog_") and not event.catalog_revision_id:
            problems.append("馆藏发布事件缺少馆藏修订")
        if not event.domain_event_id:
            problems.append("发布事件缺少统一变更事件")
        if event.status == "completed" and any(row.status not in {"completed", "skipped"} for row in deliveries):
            problems.append("发布事件已完成但消费者尚未完成")
        if event.catalog_revision_id and event.catalog_revision.status == "active" and any(row.status == "failed" for row in deliveries):
            problems.append("活动修订存在失败的派生消费者")
        for problem in problems:
            yield {"event_id": event.pk, "object_type": event.object_type, "object_id": event.object_id, "problem": problem}


def _json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "pk"):
        return str(value.pk)
    return str(value)


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normalized_label(value: Any) -> str:
    return normalize_term(" ".join(str(value or "").split()))


def _bounded(items: Iterable[dict[str, Any]], limit: int) -> tuple[int, list[dict]]:
    total = 0
    examples: list[dict] = []
    for item in items:
        total += 1
        if len(examples) < limit:
            examples.append(_json(item))
    return total, examples


def _check(
    code: str,
    *,
    title: str,
    severity: str,
    items: Iterable[dict[str, Any]],
    limit: int,
    note: str,
) -> dict[str, Any]:
    count, examples = _bounded(items, limit)
    return {
        "code": code,
        "title": title,
        "severity": severity,
        "count": count,
        "examples": examples,
        "truncated": count > len(examples),
        "note": note,
    }


def _accepted_metadata_without_value() -> Iterable[dict[str, Any]]:
    work_fields = {
        "title",
        "subtitle",
        "original_title",
        "uniform_title",
        "document_type",
        "language",
        "original_language",
        "abstract",
    }
    edition_fields = {
        field.name
        for field in Edition._meta.fields
        if field.name not in {"id", "work", "active_catalog_revision"}
    }
    roles = {
        "authors": Contribution.Role.AUTHOR,
        "translators": Contribution.Role.TRANSLATOR,
    }
    rows = (
        MetadataCandidate.objects.filter(
            lifecycle=MetadataCandidate.Lifecycle.ACCEPTED,
            upload_item__edition__isnull=False,
        )
        .select_related("upload_item__edition__work")
        .order_by("created_at", "pk")
    )
    for candidate in rows.iterator(chunk_size=250):
        edition = candidate.upload_item.edition
        field_name = candidate.field_name
        missing = False
        actual: Any = None
        if field_name in roles:
            actual = list(
                edition.contributions.filter(
                    role=roles[field_name],
                    approved=True,
                ).values_list("person_id", flat=True)
            )
            missing = not actual
        elif field_name in work_fields:
            actual = getattr(edition.work, field_name, None)
            missing = _blank(actual)
        elif field_name in edition_fields:
            actual = getattr(edition, field_name, None)
            missing = _blank(actual)
        else:
            continue
        if missing:
            yield {
                "candidate_id": candidate.pk,
                "edition_id": edition.pk,
                "work_id": edition.work_id,
                "field": field_name,
                "candidate_value_present": not _blank(candidate.value),
                "formal_draft_value": actual,
            }


def _accepted_resolution_without_relation() -> Iterable[dict[str, Any]]:
    resolved = {
        EntityResolutionCandidate.Status.LINKED,
        EntityResolutionCandidate.Status.CREATE_DRAFT,
        EntityResolutionCandidate.Status.UNRESOLVED,
    }
    rows = (
        EntityResolutionCandidate.objects.filter(
            status__in=resolved,
            upload_item__edition__isnull=False,
        )
        .select_related("upload_item__edition")
        .order_by("created_at", "pk")
    )
    for candidate in rows.iterator(chunk_size=250):
        edition = candidate.upload_item.edition
        if candidate.target_type == "person":
            role = str(
                (candidate.supporting_properties or {}).get("contribution_role")
                or Contribution.Role.AUTHOR
            )
            relation = edition.contributions.filter(
                person_id=candidate.candidate_entity_id,
                role=role,
                approved=True,
            ).exists()
            if not relation:
                yield {
                    "candidate_id": candidate.pk,
                    "edition_id": edition.pk,
                    "field": role,
                    "entity_id": candidate.candidate_entity_id,
                    "problem": "缺少已确认的贡献者草稿关系",
                }
        elif candidate.target_type == "publisher":
            deferred = bool(
                (candidate.supporting_properties or {}).get("canonical_write_deferred")
            )
            if (
                str(edition.publisher_authority_id or "")
                != str(candidate.candidate_entity_id or "")
                and not deferred
            ):
                yield {
                    "candidate_id": candidate.pk,
                    "edition_id": edition.pk,
                    "field": "publisher",
                    "entity_id": candidate.candidate_entity_id,
                    "problem": "出版社决定与版本草稿不一致",
                }


def _accepted_enrichment_without_authority() -> Iterable[dict[str, Any]]:
    rows = EnrichmentCandidate.objects.filter(
        status=EnrichmentCandidate.Status.ACCEPTED
    ).order_by("created_at", "pk")
    for candidate in rows.iterator(chunk_size=250):
        label = str(candidate.accepted_authority_model or "").strip()
        object_id = candidate.accepted_authority_id
        missing = not label or object_id is None
        if not missing:
            try:
                model = apps.get_model(label)
            except (LookupError, ValueError):
                model = None
            missing = model is None or not model._base_manager.filter(pk=object_id).exists()
        if missing:
            yield {
                "candidate_id": candidate.pk,
                "target_type": candidate.target_type,
                "target_id": candidate.target_id,
                "field": candidate.field_name,
                "accepted_authority_model": label,
                "accepted_authority_id": object_id,
            }


def _duplicate_groups() -> Iterable[dict[str, Any]]:
    sources = (
        ("person", Person.objects.exclude(authority_status=Person.AuthorityStatus.MERGED), "preferred_name"),
        ("topic", Topic.objects.all(), "name"),
        ("theory_school", TheorySchool.objects.all(), "name"),
        ("knowledge_node_zh", KnowledgeNode.objects.exclude(canonical_name_zh=""), "canonical_name_zh"),
        ("knowledge_node_en", KnowledgeNode.objects.exclude(canonical_name_en=""), "canonical_name_en"),
        ("work", catalog_models.Work.objects.all(), "title"),
        ("discipline", catalog_models.Discipline.objects.all(), "name"),
        ("subdiscipline", catalog_models.Subdiscipline.objects.all(), "name"),
        ("reading_path", catalog_models.ReadingPath.objects.all(), "title"),
    )
    for object_type, queryset, field_name in sources:
        grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for object_id, label in queryset.values_list("pk", field_name).iterator(chunk_size=500):
            normalized = _normalized_label(label)
            if normalized:
                grouped[normalized].append((str(object_id), str(label)))
        for normalized, values in sorted(grouped.items()):
            if len(values) > 1:
                yield {
                    "object_type": object_type,
                    "normalized_label": normalized,
                    "objects": [
                        {"id": object_id, "label": label}
                        for object_id, label in values
                    ],
                }


def _alias_identity_conflicts() -> Iterable[dict[str, Any]]:
    groups = defaultdict(dict)
    sources = (
        ("person", Person.objects.exclude(authority_status__in=["archived", "merged"]).values_list("pk", "preferred_name")),
        ("person", catalog_models.PersonNameVariant.objects.filter(is_verified=True, person__authority_status="verified").values_list("person_id", "name")),
        ("knowledge_node", KnowledgeNode.objects.exclude(status="archived").values_list("pk", "canonical_name_zh")),
        ("knowledge_node", KnowledgeNode.objects.exclude(status="archived").values_list("pk", "canonical_name_en")),
        ("knowledge_node", catalog_models.KnowledgeNodeAlias.objects.filter(is_verified=True).exclude(node__status="archived").values_list("node_id", "alias")),
    )
    for kind, rows in sources:
        for identifier, label in rows.iterator(chunk_size=500):
            normalized = _normalized_label(label)
            if normalized:
                groups[(kind, normalized)][str(identifier)] = label
    for (kind, normalized), values in sorted(groups.items()):
        if len(values) > 1:
            yield {"object_type": kind, "normalized_label": normalized,
                   "objects": [{"id": identifier, "label": label} for identifier, label in values.items()]}


def _published_without_stable_revision() -> Iterable[dict[str, Any]]:
    rows = Edition.objects.filter(state=PublicationState.PUBLISHED).select_related(
        "active_catalog_revision"
    )
    for edition in rows.order_by("created_at", "pk").iterator(chunk_size=250):
        revision = edition.active_catalog_revision
        if (
            revision is None
            or revision.status != CatalogPublicationRevision.Status.ACTIVE
            or not revision.metadata_ready
        ):
            yield {
                "edition_id": edition.pk,
                "work_id": edition.work_id,
                "active_revision_id": revision.pk if revision else None,
                "active_revision_status": revision.status if revision else None,
                "metadata_ready": revision.metadata_ready if revision else False,
            }


def _published_without_search_marker() -> Iterable[dict[str, Any]]:
    for edition in Edition.objects.filter(
        state=PublicationState.PUBLISHED,
        active_catalog_revision__status=CatalogPublicationRevision.Status.ACTIVE,
        active_catalog_revision__metadata_ready=True,
        search_indexed_at__isnull=True,
    ).order_by("created_at", "pk"):
        yield {
            "edition_id": edition.pk,
            "work_id": edition.work_id,
            "active_revision_id": edition.active_catalog_revision_id,
        }


def _nonformal_current_projections() -> Iterable[dict[str, Any]]:
    eligible_editions = set(
        Edition.objects.filter(
            state=PublicationState.PUBLISHED,
            active_catalog_revision__status=CatalogPublicationRevision.Status.ACTIVE,
            active_catalog_revision__metadata_ready=True,
        ).values_list("pk", flat=True)
    )
    public_types = {
        ProjectionState.ProjectionType.PUBLIC,
        ProjectionState.ProjectionType.FULLTEXT,
        ProjectionState.ProjectionType.SEMANTIC,
        ProjectionState.ProjectionType.CLAIM_INDEX,
    }
    rows = ProjectionState.objects.filter(
        object_type__iexact="edition",
        projection_type__in=public_types,
        status=ProjectionState.Status.CURRENT,
    ).exclude(object_id__in=eligible_editions)
    for row in rows.order_by("created_at", "pk"):
        yield {
            "projection_state_id": row.pk,
            "edition_id": row.object_id,
            "projection": row.projection_type,
            "source_revision": row.source_revision,
            "projected_revision": row.projected_revision,
        }


def _lexicon_rows_not_in_formal_registry() -> Iterable[dict[str, Any]]:
    state = QueryLexiconState.objects.select_related("active_generation").filter(
        key="default"
    ).first()
    if state is None or state.active_generation is None:
        return
    expected: dict[tuple[str, str], set[str]] = {}
    rows = QueryLexiconEntry.objects.filter(
        generation=state.active_generation
    ).order_by("entity_type", "entity_id", "normalized_term")
    for row in rows.iterator(chunk_size=500):
        cache_key = (row.entity_type, str(row.entity_id))
        if cache_key not in expected:
            try:
                build = build_entity(
                    EntityKey(row.entity_type, row.entity_id),
                    source_registry_version=SOURCE_REGISTRY_VERSION,
                )
                expected[cache_key] = {
                    item["normalized_term"] for item in build.entries
                }
            except (ValueError, LookupError):
                expected[cache_key] = set()
        if row.normalized_term not in expected[cache_key]:
            yield {
                "entry_id": row.pk,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "normalized_term": row.normalized_term,
                "source_kind": row.source_kind,
                "public_active": row.public_active,
                "admin_resolvable": row.admin_resolvable,
            }


def _nonformal_ready_semantic_material() -> Iterable[dict[str, Any]]:
    rows = (
        SemanticChunk.objects.filter(index_status=SemanticChunk.IndexStatus.READY)
        .exclude(active_document_q(asset_prefix="asset"))
        .select_related("asset__edition")
        .order_by("asset_id", "order")
    )
    seen: set[str] = set()
    for row in rows.iterator(chunk_size=500):
        asset_id = str(row.asset_id)
        if asset_id in seen:
            continue
        seen.add(asset_id)
        yield {
            "asset_id": row.asset_id,
            "edition_id": row.asset.edition_id,
            "work_id": row.work_id,
            "edition_state": row.asset.edition.state,
            "example_chunk_id": row.pk,
            "note": "允许作为后台预计算存在，但必须核对活动外部索引未公开该材料",
        }


def catalog_consistency_report(*, example_limit: int = 100, schema_only: bool = False) -> dict[str, Any]:
    limit = max(1, min(int(example_limit), 1000))
    inventory = _database_inventory()
    if schema_only or not inventory["source_schema_compatible"]:
        return {
            "schema_version": AUDIT_SCHEMA_VERSION, "report_revision": 2,
            "generated_at": timezone.now().isoformat(), "read_only": True,
            "inventory": inventory, "checks": [],
            "summary": {"error_count": sum(not row["table_present"] or bool(row["missing_columns"]) for row in inventory["tables"]),
                        "warning_count": 0, "clean": False, "data_checks_executed": False,
                        "requires_external_index_verification": True},
            "repair_plan": {"deterministic_after_backup": ["核对 migration 记录、物理表和当前源码。由批准的迁移流程补齐 schema 后重跑只读数据检查。"],
                            "requires_editor_decision": [], "automatic_repairs": False},
            "safety": {"database_mutated": False, "automatic_repairs": False, "external_indexes_queried": False},
        }
    checks = [
        _check(
            "accepted_metadata_without_formal_draft",
            title="已接受元数据候选没有写入正式草稿字段或关系",
            severity="error",
            items=_accepted_metadata_without_value(),
            limit=limit,
            note="候选状态不能替代正式草稿值。",
        ),
        _check(
            "accepted_entity_without_formal_relation",
            title="实体决定与正式草稿关系不一致",
            severity="error",
            items=_accepted_resolution_without_relation(),
            limit=limit,
            note="重点检查历史上的候选已采用但作者仍为空问题。",
        ),
        _check(
            "accepted_enrichment_missing_audit_target",
            title="已接受补充候选缺少可追溯写入对象",
            severity="error",
            items=_accepted_enrichment_without_authority(),
            limit=limit,
            note="只核对引用存在性，不自动重建或接受任何候选。",
        ),
        _check(
            "possible_duplicate_authorities",
            title="可能重复的人物或知识对象",
            severity="warning",
            items=_duplicate_groups(),
            limit=limit,
            note="仅按规范化名称发现疑似重复；必须人工消歧后才能合并。",
        ),
        _check(
            "published_without_active_revision",
            title="已发布版本缺少可服务的活动馆藏修订",
            severity="error",
            items=_published_without_stable_revision(),
            limit=limit,
            note="迁移后应由活动 revision 承担公开读取边界。",
        ),
        _check(
            "published_without_search_marker",
            title="已发布版本缺少全文搜索写入标记",
            severity="warning",
            items=_published_without_search_marker(),
            limit=limit,
            note="这是数据库侧线索，仍需同 Meilisearch 活动索引交叉核对。",
        ),
        _check(
            "nonformal_projection_marked_current",
            title="非正式版本仍有公开类投影被标为最新",
            severity="error",
            items=_nonformal_current_projections(),
            limit=limit,
            note="活动投影状态不应绕过正式馆藏修订。",
        ),
        _check(
            "query_lexicon_nonformal_entries",
            title="活动 QueryLexicon 含有正式规则不能重建的词条",
            severity="error",
            items=_lexicon_rows_not_in_formal_registry(),
            limit=limit,
            note="可能来自草稿、未核验别名、旧候选或过期 generation。",
        ),
        _check(
            "nonformal_ready_semantic_material",
            title="非正式正文已有就绪语义材料",
            severity="warning",
            items=_nonformal_ready_semantic_material(),
            limit=limit,
            note="后台 staging 预计算是合法的；此项用于核对它没有进入公开 RAG、观点检索或活动语义索引。",
        ),
        _check("formal_relation_nonformal_endpoint", title="正式关系指向未发布对象", severity="warning",
               items=_formal_relation_endpoint_issues(), limit=limit,
               note="包括书目、人物、主题、理论、学科和阅读路径关系。需核对审核意图，禁止仅为索引通过而自动发布端点。"),
        _check("missing_foreign_key_references", title="正式表外键引用缺失", severity="error",
               items=_missing_foreign_key_references(), limit=limit,
               note="核对数据库约束和历史变更记录。不得自动删除关系或临时创建空对象来填补外键。"),
        _check("formal_entity_requirements", title="正式对象最低字段或公开资格不一致", severity="warning",
               items=_formal_entity_requirements(), limit=limit,
               note="保留正式馆藏，按对象在后台重新核对；不自动提升未审核实体。"),
        _check("bibliographic_identity_conflicts", title="书目字段或规范标识冲突", severity="warning",
               items=_bibliographic_conflicts(), limit=limit,
               note="同 ISBN/DOI 或同名不等于重复。保留原件和不同版本，先人工确认身份与版本。"),
        _check("bundle_revision_reference_mismatch", title="发布包或活动修订引用异常", severity="error",
               items=_bundle_and_revision_issues(), limit=limit,
               note="只报告错误引用，不改写历史发布包、馆藏快照和文件身份。"),
        _check("field_decision_formal_value_mismatch", title="人工字段状态与真实字段不一致", severity="error",
               items=_field_decision_issues(), limit=limit,
               note="包括已确认却为空、不适用却仍有字段值。应回到当前编辑草稿重新核对。"),
        _check("publication_delivery_mismatch", title="知识发布事件与消费者状态不一致", severity="error",
               items=_publication_delivery_issues(), limit=limit,
               note="仅在确认来源修订合法后，通过现有幂等重试流程处理派生结果。"),
        _check("alias_identity_overlap", title="多个身份共享规范名称或已确认别名", severity="warning",
               items=_alias_identity_conflicts(), limit=limit,
               note="必须人工区分同名者、译名和真正重复实体；不得仅凭名称自动合并。"),
    ]
    state = QueryLexiconState.objects.select_related("active_generation").filter(
        key="default"
    ).first()
    errors = sum(row["count"] for row in checks if row["severity"] == "error")
    warnings = sum(
        row["count"] for row in checks if row["severity"] == "warning"
    )
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "report_revision": 2,
        "generated_at": timezone.now().isoformat(),
        "read_only": True,
        "inventory": inventory,
        "query_lexicon": {
            "active_generation_id": (
                str(state.active_generation_id) if state else None
            ),
            "source_registry_version": (
                state.source_registry_version if state else None
            ),
            "expected_source_registry_version": SOURCE_REGISTRY_VERSION,
            "registry_upgrade_required": bool(
                state and state.source_registry_version != SOURCE_REGISTRY_VERSION
            ),
        },
        "summary": {
            "error_count": errors,
            "warning_count": warnings,
            "clean": errors == 0 and warnings == 0,
            "data_checks_executed": True,
            "requires_external_index_verification": True,
        },
        "checks": checks,
        "repair_plan": {
            "deterministic_after_backup": [
                {"check": row["code"], "finding_count": row["count"],
                 "action": "先核对正式来源与活动修订，再使用现有发布事件幂等重试或正式词典重建。不得删除活动版本或直接改写索引。"}
                for row in checks if row["count"] and row["code"] in {
                    "published_without_search_marker", "query_lexicon_nonformal_entries", "publication_delivery_mismatch",
                }
            ],
            "requires_editor_decision": [
                {"check": row["code"], "finding_count": row["count"], "action": row["note"]}
                for row in checks if row["count"] and row["code"] not in {
                    "published_without_search_marker", "query_lexicon_nonformal_entries", "publication_delivery_mismatch",
                }
            ],
            "automatic_repairs": False,
        },
        "safety": {
            "database_mutated": False,
            "automatic_repairs": False,
            "external_indexes_queried": False,
        },
    }
