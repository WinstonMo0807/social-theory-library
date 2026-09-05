"""Formal catalog revision and knowledge-publication outbox coordination.

The canonical PostgreSQL rows remain the source of truth.  This module turns
an explicit editorial publication into an immutable catalog snapshot and a
durable event.  Existing projection workers remain responsible for derived
indexes; this service only activates a fulltext revision after those workers
have proved that the captured source revision is current.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from hashlib import sha256
import json
from typing import Iterable
import uuid

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Max, Q
from django.utils import timezone

from catalog.models import (
    Asset,
    CatalogPublicationRevision,
    DocumentRevision,
    Edition,
    IntelligenceStatus,
    KnowledgeNode,
    KnowledgePublicationStatus,
    KnowledgeProjectionDelivery,
    KnowledgePublicationEvent,
    Person,
    ProjectionState,
    PublicationBundle,
    PublicationBundleItem,
    PublicationState,
    PublisherAuthority,
    ScholarProfile,
    TheorySchool,
    Topic,
    WorkNodeRelation,
)
from catalog.services.dependency_engine import (
    ProjectionType,
    projection_types_for,
    record_canonical_change,
)
from catalog.services.field_decisions import ensure_publication_bundle


FULLTEXT_QUALITY_THRESHOLD = 0.55
SEMANTIC_QUALITY_THRESHOLD = 0.50
CONTENT_FIELDS = {
    "asset",
    "document_revision",
    "reader",
    "reader_asset",
    "ocr_text",
    "fulltext_ready",
}
COMPOSITE_FIELDS = {
    "ocr": ("document_revision", "fulltext_ready"),
    "ocr_text": ("document_revision", "fulltext_ready"),
    "fulltext": ("document_revision", "fulltext_ready"),
    "file": ("asset", "document_revision", "fulltext_ready"),
    "pdf": ("asset", "document_revision", "fulltext_ready"),
    "bibliography": (
        "journal_contents",
        "version_label",
        "publication_date",
        "publication_year",
        "publisher",
        "publisher_authority",
        "publication_place",
        "isbn",
        "isbn10",
        "isbn13",
        "doi",
    ),
    "contributors": ("authors", "translators"),
    "classification": ("disciplines", "subdisciplines"),
    "knowledge": ("topics", "theories"),
    "reader": ("asset", "document_revision", "fulltext_ready"),
    "curated_claims": ("curation",),
}


PROJECTION_CONSUMERS = {
    ProjectionType.QUERY_LEXICON: (
        KnowledgeProjectionDelivery.Consumer.QUERY_LEXICON,
    ),
    ProjectionType.FULLTEXT: (
        KnowledgeProjectionDelivery.Consumer.FULLTEXT,
    ),
    ProjectionType.SEMANTIC: (
        KnowledgeProjectionDelivery.Consumer.SEMANTIC,
    ),
    ProjectionType.CLAIM_INDEX: (
        KnowledgeProjectionDelivery.Consumer.VIEWPOINT,
    ),
    ProjectionType.KNOWLEDGE_GRAPH: (
        KnowledgeProjectionDelivery.Consumer.KNOWLEDGE_GRAPH,
        KnowledgeProjectionDelivery.Consumer.PERSON_SEARCH,
    ),
    ProjectionType.RECOMMENDATION: (
        KnowledgeProjectionDelivery.Consumer.RECOMMENDATION,
    ),
    ProjectionType.READING_PATH_SUPPORT: (
        KnowledgeProjectionDelivery.Consumer.RECOMMENDATION,
    ),
    ProjectionType.PUBLIC: (
        KnowledgeProjectionDelivery.Consumer.BIBLIOGRAPHIC_SEARCH,
        KnowledgeProjectionDelivery.Consumer.PUBLIC_CACHE,
    ),
}


def _json(value):
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


def normalize_changed_fields(
    values: Iterable[str] | None,
    *,
    event_type: str,
) -> list[str]:
    fields: set[str] = set()
    for raw in values or ():
        value = str(raw or "").strip()
        if not value:
            continue
        root = value.split(".", 1)[0]
        fields.update(COMPOSITE_FIELDS.get(root, (root,)))
    if event_type == KnowledgePublicationEvent.EventType.CATALOG_PUBLISHED:
        fields.add("catalog_publish")
    elif event_type == KnowledgePublicationEvent.EventType.CATALOG_WITHDRAWN:
        fields.add("catalog_withdraw")
    return sorted(fields)


def _current_document(edition: Edition, *, content_asset_id=None) -> tuple[Asset | None, DocumentRevision | None, bool]:
    assets = edition.assets.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
        )
    assets = assets.filter(pk=content_asset_id) if content_asset_id else assets.filter(is_current=True)
    asset = (
        assets
        .order_by("-version", "-created_at")
        .first()
    )
    if asset is None:
        if content_asset_id:
            raise ValueError("指定的正文文件不属于当前版本或尚未就绪。")
        return None, None, False
    revision = (
        asset.document_revisions.filter(is_active=True)
        .order_by("-revision", "-created_at")
        .first()
    )
    if revision is None:
        return asset, None, False
    assessment = revision.quality_assessments.order_by("-created_at").first()
    ready = bool(
        assessment is not None
        and float(assessment.fulltext_quality or 0) >= FULLTEXT_QUALITY_THRESHOLD
        and float(assessment.semantic_quality or 0) >= SEMANTIC_QUALITY_THRESHOLD
    )
    return asset, revision, ready


def catalog_snapshot(edition: Edition, *, content_asset_id=None) -> tuple[dict, list[dict]]:
    from catalog.services.journal_issues import journal_contents_snapshot

    work = edition.work
    contributions = [
        {
            "person_id": str(row.person_id),
            "name": row.person.preferred_name,
            "person": {
                "id": str(row.person_id),
                "preferred_name": row.person.preferred_name,
                "original_name": row.person.original_name,
                "aliases": list(row.person.aliases or []),
                "authority_status": row.person.authority_status,
                "birth_year": row.person.birth_year,
                "death_year": row.person.death_year,
                "biography": row.person.biography,
                "portrait": str(row.person.portrait.name or ""),
                "scholar_slug": (
                    row.person.scholar_profile.slug
                    if hasattr(row.person, "scholar_profile")
                    and row.person.scholar_profile.editorial_status == "published"
                    else None
                ),
            },
            "role": row.role,
            "order": row.order,
        }
        for row in edition.contributions.filter(approved=True)
        .select_related("person", "person__scholar_profile")
        .order_by("order", "created_at", "id")
    ]
    disciplines = [
        {
            "id": str(row.discipline_id),
            "name": row.discipline.name,
            "slug": row.discipline.slug,
            "is_primary": row.is_primary,
        }
        for row in work.discipline_relations.filter(
            review_status="approved", discipline__editorial_status="published",
        )
        .select_related("discipline")
        .order_by("-is_primary", "discipline_id")
    ]
    subdisciplines = [
        {
            "id": str(row.subdiscipline_id),
            "name": row.subdiscipline.name,
            "slug": row.subdiscipline.slug,
            "is_primary": row.is_primary,
        }
        for row in work.subdiscipline_relations.filter(
            review_status="approved", subdiscipline__editorial_status="published",
        )
        .select_related("subdiscipline")
        .order_by("-is_primary", "subdiscipline_id")
    ]
    topics = [
        {
            "id": str(row.topic_id),
            "name": row.topic.name,
            "slug": row.topic.slug,
            "is_primary": row.is_primary,
        }
        for row in work.topic_relations.filter(
            review_status="approved", topic__editorial_status="published",
        )
        .select_related("topic")
        .order_by("-is_primary", "topic_id")
    ]
    nodes = [
        {
            "id": str(row.node_id),
            "name": row.node.canonical_name_zh or row.node.canonical_name_en,
            "foreign_name": row.node.canonical_name_en,
            "slug": row.node.slug,
            "type": row.node.node_type,
            "role": row.role,
            "is_primary": row.is_primary,
        }
        for row in work.node_relations.filter(status="published", node__status="published")
        .select_related("node")
        .order_by("-is_primary", "node_id", "role")
    ]
    asset, document_revision, quality_ready = _current_document(edition, content_asset_id=content_asset_id)
    decisions = [
        {
            "field": row.field_name,
            "status": row.status,
            "value": row.value,
            "confirmation_method": row.confirmation_method,
            "provenance": row.provenance,
            "confirmed_at": _json(row.confirmed_at),
        }
        for row in edition.field_decisions.filter(
            status__in=["confirmed", "not_applicable", "stale"]
        ).order_by("field_name")
    ]
    snapshot = {
        "journal_contents": journal_contents_snapshot(edition),
        "curated_claim_ids": [str(value) for value in work.curated_claims.filter(
            status="published",
        ).order_by("kind", "sort_order", "id").values_list("id", flat=True)],
        "work": {
            "id": str(work.id),
            "title": work.title,
            "subtitle": work.subtitle,
            "original_title": work.original_title,
            "uniform_title": work.uniform_title,
            "document_type": work.document_type,
            "language": work.language,
            "original_language": work.original_language,
            "abstract": work.abstract,
            "first_publication_date": _json(work.first_publication_date),
            "translation_of_id": _json(work.translation_of_id),
            "cover": str(work.cover.name or ""),
            "recommendation_image": str(work.recommendation_image.name or ""),
        },
        "edition": {
            "id": str(edition.id),
            "version_label": edition.version_label,
            "publication_date": _json(edition.publication_date),
            "publication_year": edition.publication_year,
            "publisher": edition.publisher,
            "publisher_authority_id": _json(edition.publisher_authority_id),
            "publication_place": edition.publication_place,
            "journal_title": edition.journal_title,
            "volume": edition.volume,
            "issue": edition.issue,
            "page_range": edition.page_range,
            "isbn": edition.isbn,
            "isbn10": edition.isbn10,
            "isbn13": edition.isbn13,
            "doi": edition.doi,
            "series": edition.series,
            "extent": edition.extent,
            "public_slug": edition.public_slug,
            "state": edition.state,
        },
        "contributions": contributions,
        "classification": {
            "disciplines": disciplines,
            "subdisciplines": subdisciplines,
        },
        "knowledge": {"topics": topics, "nodes": nodes},
        "document": {
            "asset_id": _json(asset.pk if asset else None),
            "asset_sha256": asset.sha256 if asset else "",
            "document_revision_id": _json(
                document_revision.pk if document_revision else None
            ),
            "document_revision": (
                document_revision.revision if document_revision else None
            ),
            "text_checksum": (
                document_revision.text_checksum if document_revision else ""
            ),
            "quality_ready": quality_ready,
        },
        "field_decisions": decisions,
    }
    related = []
    for row in contributions:
        related.append({"object_type": "person", "object_id": row["person_id"]})
    for object_type, rows in (
        ("discipline", disciplines),
        ("subdiscipline", subdisciplines),
        ("topic", topics),
        ("knowledge_node", nodes),
    ):
        related.extend(
            {"object_type": object_type, "object_id": row["id"]}
            for row in rows
        )
    if edition.publisher_authority_id:
        related.append(
            {
                "object_type": "publisher",
                "object_id": str(edition.publisher_authority_id),
            }
        )
    unique = {
        (row["object_type"], row["object_id"]): row for row in related
    }
    return snapshot, [unique[key] for key in sorted(unique)]


def _fingerprint(snapshot: dict) -> str:
    payload = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


HUMAN_CATALOG_RELATION_SOURCES = {
    "workflow_section_confirmation", "workflow_legacy_identity_adapter",
    "field_assistant", "field_assistant_inline", "manual_cataloging", "editorial",
}


def confirmed_bundle_links(edition: Edition, *, include_editorial_draft: bool = False, for_update: bool = False) -> dict[tuple[str, str], list]:
    """Current reviewed relationships, never the historical bundle checklist.

    A removed or still-machine-only relationship cannot publish its old draft
    entity. The preflight may overlay explicit saved revision selections; the
    publication transaction checks only the canonical rows it just applied.
    """
    from catalog.models import CatalogFieldDecision, EditorialRevision

    links: dict[tuple[str, str], list] = defaultdict(list)
    decisions = {row.field_name: row for row in edition.field_decisions.filter(
        status=CatalogFieldDecision.Status.CONFIRMED, confirmed_by__isnull=False, confirmed_at__isnull=False,
    )}

    def decided(field, identifier):
        decision = decisions.get(field)
        if decision is None:
            return False
        value = decision.value
        if isinstance(value, list):
            return str(identifier) in {str(row.get("id", row.get("person_id", "")) if isinstance(row, dict) else row) for row in value}
        if isinstance(value, dict):
            return str(identifier) == str(value.get("id", value.get("publisher_authority_id", "")))
        return str(identifier) == str(value)

    def human(row):
        return row.source in HUMAN_CATALOG_RELATION_SOURCES or bool(getattr(row, "reviewed_by_id", None) and getattr(row, "reviewed_at", None))

    def rows(queryset):
        return queryset.select_for_update().order_by("pk") if for_update else queryset

    roles = {"author": "authors", "translator": "translators", "chief_editor": "chief_editors", "editor": "editors", "annotator": "annotators", "photographer": "photographers"}
    for row in rows(edition.contributions.filter(approved=True)):
        if human(row) or decided(roles.get(row.role, "other_contributors"), row.person_id):
            links[("person", str(row.person_id))].append(row.pk)
    for row in rows(edition.work.topic_relations.filter(review_status="approved")):
        if human(row) or decided("topics", row.topic_id):
            links[("topic", str(row.topic_id))].append(row.pk)
    for row in rows(edition.work.node_relations.filter(status__in=["published", "pending"])):
        if human(row) or decided("theories", row.node_id):
            links[("knowledge_node", str(row.node_id))].append(row.pk)
    for row in rows(edition.work.knowledge_relations.filter(approved=True, review_status="approved")):
        if row.theory_school_id and (human(row) or decided("theories", row.theory_school_id)):
            links[("theory_school", str(row.theory_school_id))].append(row.pk)
        if row.topic_id and (human(row) or decided("topics", row.topic_id)):
            links[("topic", str(row.topic_id))].append(row.pk)
    if edition.publisher_authority_id and (decided("publisher", edition.publisher_authority_id) or "publisher" in decisions):
        links[("publisher", str(edition.publisher_authority_id))] = []
    if include_editorial_draft:
        draft = EditorialRevision.objects.filter(target_type="work", target_id=edition.work_id, status="draft").order_by("-revision").first()
        if draft is not None and draft.created_by_id:
            patch = dict(draft.patch or {})
            contributors = patch.get("contributors") or {}
            if str(contributors.get("edition_id")) == str(edition.pk) and "contributors" in (contributors.get("values") or {}):
                links = defaultdict(list, {key: ids for key, ids in links.items() if key[0] != "person"})
                for row in contributors["values"]["contributors"]:
                    links[("person", str(row["person_id"]))] = []
            knowledge = patch.get("knowledge") or {}
            for field, kind in (("topics", "topic"), ("nodes", "knowledge_node"), ("theories", "theory_school")):
                if field in knowledge:
                    links = defaultdict(list, {key: ids for key, ids in links.items() if key[0] != kind})
                    for row in knowledge[field]:
                        links[(kind, str(row["id"]))] = []
            bibliography = patch.get("bibliography") or {}
            if str(bibliography.get("edition_id")) == str(edition.pk) and "publisher_authority_id" in (bibliography.get("values") or {}):
                links = defaultdict(list, {key: ids for key, ids in links.items() if key[0] != "publisher"})
                identifier = bibliography["values"].get("publisher_authority_id")
                if identifier:
                    links[("publisher", str(identifier))] = []
    return dict(links)


def _publish_confirmed_bundle_aliases(entity, item, *, actor):
    from catalog.models import EnrichmentCandidate, KnowledgeNodeAlias, PersonNameVariant
    from catalog.services.query_lexicon.normalization import normalize_term

    if isinstance(entity, Person):
        model, related, field, id_field = PersonNameVariant, entity.name_variants, "name", "normalized_name"
    elif isinstance(entity, KnowledgeNode):
        model, related, field, id_field = KnowledgeNodeAlias, entity.aliases, "alias", "normalized_alias"
    else:
        return
    accepted = EnrichmentCandidate.objects.filter(
        status="accepted", reviewed_by__isnull=False, reviewed_at__isnull=False,
        accepted_authority_model=model._meta.label,
    ).values_list("accepted_authority_id", flat=True)
    # A PDF/Web label by itself is never enough. Only its exact reviewed
    # candidate or names explicitly entered in the inline form are promoted.
    for alias in related.select_for_update().filter(pk__in=accepted, is_verified=True):
        if alias.source_kind != model.SourceKind.EDITORIAL:
            alias.source_kind = model.SourceKind.EDITORIAL
            alias.save(update_fields=["source_kind", "updated_at"])
    snapshot = dict(item.snapshot or {})
    if snapshot.get("aliases_confirmed_by") and snapshot.get("aliases_confirmed_at"):
        for name in snapshot.get("confirmed_aliases") or []:
            clean = str(name).strip()
            if not clean:
                continue
            normalized = normalize_term(clean) if isinstance(entity, Person) else " ".join(clean.casefold().split())
            defaults = {field: clean, "source_kind": model.SourceKind.EDITORIAL, "is_verified": True, "created_by": actor}
            if isinstance(entity, Person):
                defaults.update(language="und", variant_type=PersonNameVariant.VariantType.ALIAS, displayable=True)
            related.update_or_create(**{id_field: normalized}, defaults=defaults)


def _publish_bundle_entities(
    bundle: PublicationBundle,
    *,
    actor=None,
) -> list[dict[str, str]]:
    """Promote inline-created authorities in the catalog transaction.

    The objects already exist as private drafts so relations can be edited in
    the Workbench.  Promotion happens only after the administrator starts the
    formal publication transaction and before its immutable snapshot is made.
    Any missing or incomplete object aborts the whole transaction.
    """

    if not bundle.edition_id:
        raise ValueError("发布包缺少当前馆藏版本，不能发布新增对象。")
    from catalog.models import Work

    bundle.edition.work = Work.objects.select_for_update().get(pk=bundle.edition.work_id)
    confirmed_links = confirmed_bundle_links(bundle.edition, include_editorial_draft=False, for_update=True)
    promoted: list[dict[str, str]] = []
    now = timezone.now()
    items = list(
        PublicationBundleItem.objects.select_for_update()
        .filter(bundle=bundle, action=PublicationBundleItem.Action.CREATE)
        .order_by("created_at", "pk")
    )
    for item in items:
        object_type = str(item.object_type or "").strip().casefold()
        if (object_type, str(item.object_id)) not in confirmed_links:
            item.snapshot = {**dict(item.snapshot or {}), "excluded_from_publication": "not_currently_confirmed_link"}
            item.save(update_fields=["snapshot", "updated_at"])
            continue
        if not item.minimum_complete or list(item.blockers or []):
            raise ValueError(f"新增对象“{item.label or item.object_id}”尚未达到发布要求。")
        object_type = str(item.object_type or "").strip().casefold()
        entity = None
        if object_type == "person":
            entity = Person.objects.select_for_update().filter(pk=item.object_id).first()
            if entity is None or not entity.preferred_name.strip():
                raise ValueError("新增学者不存在或姓名为空。")
            if entity.authority_status in {
                Person.AuthorityStatus.REJECTED,
                Person.AuthorityStatus.MERGED,
                Person.AuthorityStatus.ARCHIVED,
            }:
                raise ValueError(f"新增学者“{entity.preferred_name}”当前状态不能发布。")
            if entity.authority_status != Person.AuthorityStatus.VERIFIED:
                entity.authority_status = Person.AuthorityStatus.VERIFIED
                entity.save(update_fields=["authority_status", "updated_at"])
            profile = ScholarProfile.objects.select_for_update().filter(person=entity).first()
            if profile is None:
                raise ValueError(f"新增学者“{entity.preferred_name}”缺少学者资料。")
            if profile.editorial_status not in {"draft", "pending", "published"}:
                raise ValueError(f"新增学者“{entity.preferred_name}”的资料已下线，不能自动恢复。")
            if profile.editorial_status != "published":
                profile.editorial_status = "published"
                profile.save(update_fields=["editorial_status", "updated_at"])
        elif object_type == "topic":
            entity = Topic.objects.select_for_update().filter(pk=item.object_id).first()
            if entity is None or not entity.name.strip():
                raise ValueError("新增主题不存在或名称为空。")
            if entity.editorial_status not in {"draft", "pending", "published"}:
                raise ValueError("新增主题已下线，不能随馆藏恢复。")
            if entity.editorial_status != "published":
                entity.editorial_status = "published"
                entity.save(update_fields=["editorial_status", "updated_at"])
        elif object_type == "knowledge_node":
            entity = KnowledgeNode.objects.select_for_update().filter(pk=item.object_id).first()
            if entity is None or not (entity.canonical_name_zh or entity.canonical_name_en).strip():
                raise ValueError("新增理论节点不存在或名称为空。")
            if entity.status not in {"draft", "pending", "published"}:
                raise ValueError("新增理论节点已下线或拒绝，不能随馆藏恢复。")
            if entity.status != KnowledgePublicationStatus.PUBLISHED:
                entity.status = KnowledgePublicationStatus.PUBLISHED
                entity.reviewed_by = actor
                entity.published_at = now
                entity.save(
                    update_fields=["status", "reviewed_by", "published_at", "updated_at"]
                )
            if bundle.edition_id:
                WorkNodeRelation.objects.select_for_update().filter(
                    work_id=bundle.edition.work_id,
                    node=entity,
                    status=KnowledgePublicationStatus.PENDING,
                    id__in=confirmed_links[(object_type, str(item.object_id))],
                ).update(
                    status=KnowledgePublicationStatus.PUBLISHED,
                    reviewed_by=actor,
                    reviewed_at=now,
                    updated_at=now,
                )
        elif object_type == "theory_school":
            # Compatibility for draft items created before normalized theory
            # nodes became the only new-write target.
            entity = TheorySchool.objects.select_for_update().filter(pk=item.object_id).first()
            if entity is None or not entity.name.strip():
                raise ValueError("新增理论传统不存在或名称为空。")
            if entity.editorial_status not in {"draft", "pending", "published"}:
                raise ValueError("新增理论传统已下线，不能随馆藏恢复。")
            if entity.editorial_status != "published":
                entity.editorial_status = "published"
                entity.save(update_fields=["editorial_status", "updated_at"])
        elif object_type == "publisher":
            entity = PublisherAuthority.objects.select_for_update().filter(pk=item.object_id).first()
            if entity is None or not entity.canonical_name.strip():
                raise ValueError("新增出版社不存在或名称为空。")
            if entity.editorial_status not in {"draft", "pending", "published"}:
                raise ValueError("新增出版社已下线，不能随馆藏恢复。")
            if entity.editorial_status != "published":
                entity.editorial_status = "published"
                entity.save(update_fields=["editorial_status", "updated_at"])
        else:
            raise ValueError(f"发布包包含不受支持的新对象类型：{object_type or 'unknown'}。")
        _publish_confirmed_bundle_aliases(entity, item, actor=actor)
        item.snapshot = {
            **dict(item.snapshot or {}),
            "status": "published",
            "published_at": now.isoformat(),
        }
        item.snapshot.pop("excluded_from_publication", None)
        item.save(update_fields=["snapshot", "updated_at"])
        promoted.append(
            {
                "object_type": object_type,
                "object_id": str(entity.pk),
                "label": item.label,
            }
        )
    return promoted


def _delivery_plan(
    changed_fields: list[str],
    *,
    source_object_type: str = "edition",
    source_changed_fields: Iterable[str] | None = None,
    text_ready: bool,
    withdrawal: bool,
) -> dict[str, dict]:
    projections = projection_types_for(
        source_object_type,
        source_changed_fields if source_changed_fields is not None else changed_fields,
    )
    requirements: dict[str, set[str]] = defaultdict(set)
    for projection in projections:
        for consumer in PROJECTION_CONSUMERS.get(projection, ()):
            requirements[consumer].add(projection)

    # RAG is a logical consumer of formal metadata and, when eligible, the
    # same verified fulltext/semantic projections.  It never ingests a model
    # answer or an unconfirmed candidate.
    if ProjectionType.PUBLIC in projections:
        requirements[KnowledgeProjectionDelivery.Consumer.RAG].add(
            ProjectionType.PUBLIC
        )
    if text_ready and ProjectionType.FULLTEXT in projections:
        requirements[KnowledgeProjectionDelivery.Consumer.RAG].add(
            ProjectionType.FULLTEXT
        )
    if text_ready and ProjectionType.SEMANTIC in projections:
        requirements[KnowledgeProjectionDelivery.Consumer.RAG].add(
            ProjectionType.SEMANTIC
        )

    plan = {}
    text_consumers = {
        KnowledgeProjectionDelivery.Consumer.FULLTEXT,
        KnowledgeProjectionDelivery.Consumer.SEMANTIC,
        KnowledgeProjectionDelivery.Consumer.VIEWPOINT,
    }
    for consumer, required in requirements.items():
        skip = consumer in text_consumers and not text_ready and not withdrawal
        plan[consumer] = {
            "required_projections": sorted(required),
            "scope": (
                "withdrawal"
                if withdrawal
                else "metadata_and_fulltext"
                if text_ready
                else "metadata_only"
            ),
            "skip": skip,
        }
    return plan


def dispatch_knowledge_event(event_id) -> bool:
    from catalog.tasks import process_knowledge_publication_event

    try:
        process_knowledge_publication_event.apply_async(
            args=[str(event_id)],
            ignore_result=True,
        )
    except Exception as exc:
        KnowledgePublicationEvent.objects.filter(pk=event_id).update(
            last_error_code="queue_unavailable",
            last_error_message=str(exc)[:4000],
            next_attempt_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return False
    return True


@transaction.atomic
def create_entity_publication_event(
    *, object_type: str, object_id, event_type: str, changed_fields=None,
    related_entities=None, actor=None, idempotency_key: str, provenance=None,
) -> KnowledgePublicationEvent:
    """Wrap an explicit entity publication in the existing durable projections.

    A withdrawal uses ENTITY_UPDATED with a withdrawal provenance marker. It
    removes derived terms; it must never promote an ordinary draft implicitly.
    """
    kinds = {
        KnowledgePublicationEvent.EventType.ENTITY_PUBLISHED: "publish",
        KnowledgePublicationEvent.EventType.ENTITY_UPDATED: "update",
        KnowledgePublicationEvent.EventType.ENTITY_MERGED: "update",
    }
    if event_type not in kinds:
        raise ValueError("该入口只接受知识对象的正式发布事件。")
    from catalog.services.projection_refresh import TARGET_MODELS

    object_type = str(object_type).strip().casefold()
    model = TARGET_MODELS.get(object_type)
    if model is None or object_type in {"edition", "work", "asset"}:
        raise ValueError("不支持的知识对象。")
    target = model.objects.select_for_update().get(pk=object_id)
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 200:
        raise ValueError("知识发布必须提供有效幂等键。")
    existing = KnowledgePublicationEvent.objects.filter(idempotency_key=key).first()
    if existing:
        if (existing.object_type, str(existing.object_id), existing.event_type) != (object_type, str(target.pk), event_type):
            raise ValueError("幂等键已用于另一项知识发布。")
        return existing
    provenance = dict(provenance or {})
    public_status = getattr(target, "editorial_status", getattr(target, "status", ""))
    if isinstance(target, Person):
        public_status = "published" if target.authority_status == "verified" else target.authority_status
    withdrawing = bool(provenance.get("withdrawal"))
    if public_status not in {"published", "approved"} and not withdrawing:
        raise ValueError("草稿对象不能进入正式知识发布。")
    fields = sorted(set(str(value) for value in (changed_fields or [])))
    domain = record_canonical_change(
        object_type=object_type, object_id=target.pk,
        change_kind="withdraw" if withdrawing else kinds[event_type],
        changed_fields=fields, actor=actor, idempotency_key=f"knowledge-domain:{key}"[:200],
    )
    event = KnowledgePublicationEvent.objects.create(
        object_type=object_type, object_id=target.pk, event_type=event_type,
        domain_event=domain, changed_fields=fields,
        related_entities=_json(related_entities or []),
        payload={"publication_state": public_status, "canonical_revision": domain.canonical_revision, "provenance": _json(provenance)},
        idempotency_key=key, actor=actor, correlation_id=domain.correlation_id,
    )
    plan = _delivery_plan(fields, source_object_type=object_type, text_ready=False, withdrawal=withdrawing)
    now = timezone.now()
    KnowledgeProjectionDelivery.objects.bulk_create([
        KnowledgeProjectionDelivery(
            event=event, consumer=consumer, source_revision=domain.canonical_revision,
            idempotency_key=f"{event.pk}:{consumer}",
            status="skipped" if details["skip"] else "pending",
            completed_at=now if details["skip"] else None,
            result={"required_projections": details["required_projections"], "scope": details["scope"]},
        ) for consumer, details in sorted(plan.items())
    ])
    transaction.on_commit(lambda: dispatch_knowledge_event(event.pk))
    return event


@transaction.atomic
def create_catalog_publication_event(
    edition: Edition,
    *,
    event_type: str,
    changed_fields: Iterable[str] | None,
    actor=None,
    idempotency_key: str,
    bundle: PublicationBundle | None = None,
    source_object_type: str = "edition",
    source_object_id=None,
    source_changed_fields: Iterable[str] | None = None,
    expected_source_base_revision: int | None = None,
    provenance: dict | None = None,
    content_asset_id=None,
) -> KnowledgePublicationEvent:
    if event_type not in {
        KnowledgePublicationEvent.EventType.CATALOG_PUBLISHED,
        KnowledgePublicationEvent.EventType.CATALOG_UPDATED,
        KnowledgePublicationEvent.EventType.CATALOG_WITHDRAWN,
    }:
        raise ValueError("该入口只接受馆藏发布事件。")
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("知识发布必须提供幂等键。")
    source_object_type = str(source_object_type or "edition").strip().casefold()
    source_object_id = source_object_id or edition.pk
    source_fields = list(
        source_changed_fields if source_changed_fields is not None else changed_fields or ()
    )
    # Serialize the existence check with creation for repeated deliveries of
    # the same edition. Locking an absent event cannot protect that race.
    edition = (
        Edition.objects.select_for_update(of=("self",))
        .select_related("work", "active_catalog_revision")
        .get(pk=edition.pk)
    )
    existing = KnowledgePublicationEvent.objects.select_for_update().filter(
        idempotency_key=key
    ).first()
    if existing is not None:
        if (
            existing.catalog_revision is None
            or existing.catalog_revision.edition_id != edition.pk
            or existing.object_type != source_object_type
            or str(existing.object_id) != str(source_object_id)
            or existing.event_type != event_type
        ):
            raise ValueError("幂等键已用于另一项知识发布。")
        return existing

    old_active = edition.active_catalog_revision
    if old_active is not None:
        old_active = CatalogPublicationRevision.objects.select_for_update().get(
            pk=old_active.pk
        )
    fields = normalize_changed_fields(changed_fields, event_type=event_type)
    if content_asset_id:
        fields = sorted(set(fields) | {"document_revision", "fulltext_ready"})
    requested_content_change = bool(content_asset_id or CONTENT_FIELDS.intersection(fields))
    withdrawal = event_type == KnowledgePublicationEvent.EventType.CATALOG_WITHDRAWN
    pending_revisions = [] if withdrawal else list(
        CatalogPublicationRevision.objects.select_for_update(of=("self",)).select_related(
            "reader_asset", "document_revision", "bundle",
        ).filter(
            edition=edition,
            revision__gt=old_active.revision if old_active else 0,
            status__in=[
                CatalogPublicationRevision.Status.PREPARING,
                CatalogPublicationRevision.Status.FAILED,
                CatalogPublicationRevision.Status.SUPERSEDED,
            ],
        ).order_by("-revision")
    )
    pending_base = pending_revisions[0] if pending_revisions else None
    if pending_revisions:
        # These are already-confirmed formal changes, not editorial drafts.
        # A later metadata edit supersedes their activation and must therefore
        # also carry every consumer that is still missing from the active view.
        fields = sorted(set(fields).union(*(
            set(row.changed_fields or []) for row in pending_revisions
        )))
    system_content_update = (provenance or {}).get("source") in {"ocr_completion", "semantic_maintenance"}
    shared_work_update = (provenance or {}).get("source") == "shared_work_publication"
    bundle = (
        pending_base.bundle if shared_work_update and pending_base is not None
        else None if system_content_update or shared_work_update
        else bundle or ensure_publication_bundle(edition, actor=actor)
    )
    if not withdrawal and edition.state != PublicationState.PUBLISHED:
        raise ValueError("保存草稿不能产生正式馆藏发布事件。")
    promoted_entities = (
        [] if withdrawal or bundle is None or shared_work_update else _publish_bundle_entities(bundle, actor=actor)
    )
    snapshot, related = catalog_snapshot(edition, content_asset_id=content_asset_id)
    document_base = None if requested_content_change or withdrawal else (pending_base or old_active)
    if document_base is not None:
        # Metadata-only publication cannot fall back from a pending OCR/PDF
        # rendition to the older is_current Asset. Keep the captured pointers
        # and document snapshot together until the new revision activates.
        snapshot["document"] = dict((document_base.snapshot or {}).get("document") or {})
        _asset = document_base.reader_asset
        if _asset is None and snapshot["document"].get("asset_id"):
            _asset = edition.assets.filter(pk=snapshot["document"]["asset_id"]).first()
        document_revision = document_base.document_revision
        quality_ready = bool(
            _asset is not None and document_revision is not None
            and snapshot["document"].get("quality_ready")
            and (
                document_base.fulltext_ready
                or (pending_base is not None and (document_base.provenance or {}).get("requested_fulltext_ready"))
            )
        )
    else:
        _asset, document_revision, quality_ready = _current_document(edition, content_asset_id=content_asset_id)
        if not requested_content_change and "catalog_publish" not in fields and not withdrawal:
            # A legacy row without an active snapshot cannot acquire public
            # fulltext merely because its next edit happens to be a cover.
            quality_ready = False
    if system_content_update and (pending_base or old_active):
        # OCR may finish while an administrator has an unrelated draft open.
        # Only the document part may be sourced from that asynchronous job.
        formal_base = pending_base or old_active
        snapshot = {**formal_base.snapshot, "document": snapshot["document"]}
        related = list(formal_base.related_entities or [])
        if pending_base is not None:
            # These entities were already confirmed in the pending formal
            # publication. Preserve its bundle for completion, without
            # promoting unrelated entities from an open editorial draft.
            bundle = formal_base.bundle
    if promoted_entities:
        related = [
            *related,
            *[
                {
                    "object_type": row["object_type"],
                    "object_id": row["object_id"],
                }
                for row in promoted_entities
            ],
        ]
        related = list(
            {
                (row["object_type"], row["object_id"]): row
                for row in related
            }.values()
        )
    fingerprint = _fingerprint(snapshot)
    # Workbench publication first commits its Work EditorialRevision and then
    # invokes the existing Edition publication adapter in the same outer
    # transaction.  Reuse that explicitly marked pending snapshot so one
    # administrator action cannot emit two catalog revisions or two knowledge
    # events.  Ordinary catalog updates are never coalesced by recency alone.
    coalescing_candidates = (
        KnowledgePublicationEvent.objects.select_for_update()
        .select_related("catalog_revision")
        .filter(
            catalog_revision__edition=edition,
            catalog_revision__status=CatalogPublicationRevision.Status.PREPARING,
            catalog_revision__content_fingerprint=fingerprint,
            event_type=event_type,
            status__in=[
                KnowledgePublicationEvent.Status.PENDING,
                KnowledgePublicationEvent.Status.PROCESSING,
            ],
        )
        .order_by("-created_at")[:5]
    )
    for candidate in coalescing_candidates:
        candidate_provenance = dict(candidate.catalog_revision.provenance or {})
        if (
            key.startswith("catalog-publication:")
            and source_object_type == "edition"
            and expected_source_base_revision is None
            and not (provenance or {}).get("editorial_revision_id")
            and candidate_provenance.get("editorial_revision_id")
            and set(candidate.changed_fields or []) == set(fields)
        ):
            return candidate

    if system_content_update and old_active and old_active.fulltext_ready and not quality_ready:
        raise ValueError("新识别正文未达到质量要求，继续使用上一稳定正文版本。")
    content_changed = bool(CONTENT_FIELDS.intersection(fields))
    same_document = bool(
        old_active
        and old_active.document_revision_id
        and old_active.document_revision_id == getattr(document_revision, "pk", None)
    )
    carried_fulltext = bool(
        old_active
        and old_active.fulltext_ready
        and same_document
        and not content_changed
        and not withdrawal
    )
    next_revision = int(
        CatalogPublicationRevision.objects.filter(edition=edition).aggregate(
            maximum=Max("revision")
        )["maximum"]
        or 0
    ) + 1
    revision_status = (
        CatalogPublicationRevision.Status.WITHDRAWN
        if withdrawal
        else CatalogPublicationRevision.Status.PREPARING
    )
    revision = CatalogPublicationRevision.objects.create(
        edition=edition,
        revision=next_revision,
        status=revision_status,
        bundle=bundle,
        snapshot=snapshot,
        changed_fields=fields,
        related_entities=related,
        document_revision=document_revision,
        reader_asset=_asset,
        metadata_ready=not withdrawal,
        fulltext_ready=carried_fulltext,
        provenance={
            "source": "knowledge_publication_event",
            "event_type": event_type,
            "prior_active_revision_id": str(old_active.pk) if old_active else None,
            "requested_fulltext_ready": bool((quality_ready or carried_fulltext) and not withdrawal),
            "content_changed": content_changed,
            "inherited_pending_revision_ids": [str(row.pk) for row in pending_revisions],
            "promoted_entities": promoted_entities,
            **dict(provenance or {}),
        },
        content_fingerprint=fingerprint,
        created_by=actor,
        activated_at=None,
    )

    if revision_status == CatalogPublicationRevision.Status.WITHDRAWN:
        if (
            revision_status == CatalogPublicationRevision.Status.WITHDRAWN
            and old_active
            and old_active.status == CatalogPublicationRevision.Status.ACTIVE
        ):
            old_active.status = CatalogPublicationRevision.Status.SUPERSEDED
            old_active.superseded_at = timezone.now()
            old_active.save(update_fields=["status", "superseded_at", "updated_at"])
        edition.active_catalog_revision = revision
        edition.metadata_ready_at = None
        edition.fulltext_ready_at = None
    edition.intelligence_status = (
        IntelligenceStatus.WITHDRAWN if withdrawal else IntelligenceStatus.PROCESSING
    )
    edition.save(
        update_fields=[
            "active_catalog_revision",
            "metadata_ready_at",
            "fulltext_ready_at",
            "intelligence_status",
            "updated_at",
        ]
    )
    if bundle:
        bundle.status = PublicationBundle.Status.PUBLISHING
        bundle.save(update_fields=["status", "updated_at"])

    change_kind = "withdraw" if withdrawal else (
        "publish"
        if event_type == KnowledgePublicationEvent.EventType.CATALOG_PUBLISHED
        else "update"
    )
    domain_fields = fields
    domain_event = record_canonical_change(
        object_type=source_object_type,
        object_id=source_object_id,
        change_kind=change_kind,
        changed_fields=domain_fields,
        catalog_revision=revision,
        actor=actor,
        idempotency_key=f"knowledge-domain:{key}"[:200],
    )
    if (
        expected_source_base_revision is not None
        and domain_event.canonical_revision
        != int(expected_source_base_revision) + 1
    ):
        raise ValueError("正式内容版本推进异常。")
    event = KnowledgePublicationEvent.objects.create(
        event_type=event_type,
        object_type=source_object_type,
        object_id=source_object_id,
        catalog_revision=revision,
        domain_event=domain_event,
        changed_fields=fields,
        related_entities=related,
        payload={
            "edition_id": str(edition.id),
            "work_id": str(edition.work_id),
            "publication_state": edition.state,
            "requested_fulltext_ready": bool((quality_ready or carried_fulltext) and not withdrawal),
            "previous_active_revision_id": str(old_active.pk) if old_active else None,
        },
        idempotency_key=key,
        correlation_id=domain_event.correlation_id,
        actor=actor,
    )
    plan = _delivery_plan(
        fields,
        source_object_type=source_object_type,
        source_changed_fields=(
            fields
        ),
        text_ready=bool(quality_ready or carried_fulltext),
        withdrawal=withdrawal,
    )
    now = timezone.now()
    fulltext_needed = KnowledgeProjectionDelivery.Consumer.FULLTEXT in plan and not plan[KnowledgeProjectionDelivery.Consumer.FULLTEXT]["skip"]
    prior_index_id = None
    if old_active:
        prior_index_id = (old_active.provenance or {}).get("fulltext_index_revision_id")
        if not prior_index_id:
            prior_index_id = "legacy" if (old_active.provenance or {}).get("source") == "v304_safe_backfill" else str(old_active.pk)
    revision.provenance = {
        **revision.provenance,
        "fulltext_index_revision_id": str(revision.pk) if fulltext_needed else prior_index_id,
        "semantic_index_revision_id": (
            str(revision.pk)
            if KnowledgeProjectionDelivery.Consumer.SEMANTIC in plan and not plan[KnowledgeProjectionDelivery.Consumer.SEMANTIC]["skip"]
            else ((old_active.provenance or {}).get("semantic_index_revision_id") or ("legacy" if (old_active.provenance or {}).get("source") == "v304_safe_backfill" else str(old_active.pk))) if old_active else None
        ),
        "claim_index_revision_id": (
            str(revision.pk)
            if KnowledgeProjectionDelivery.Consumer.VIEWPOINT in plan and not plan[KnowledgeProjectionDelivery.Consumer.VIEWPOINT]["skip"]
            else ((old_active.provenance or {}).get("claim_index_revision_id") or ("legacy" if (old_active.provenance or {}).get("source") == "v304_safe_backfill" else str(old_active.pk))) if old_active else None
        ),
    }
    revision.save(update_fields=["provenance", "updated_at"])
    KnowledgeProjectionDelivery.objects.bulk_create(
        [
            KnowledgeProjectionDelivery(
                event=event,
                consumer=consumer,
                status=(
                    KnowledgeProjectionDelivery.Status.SKIPPED
                    if details["skip"]
                    else KnowledgeProjectionDelivery.Status.PENDING
                ),
                source_revision=domain_event.canonical_revision,
                idempotency_key=f"{event.pk}:{consumer}"[:220],
                completed_at=(now if details["skip"] else None),
                result={
                    "required_projections": details["required_projections"],
                    "scope": details["scope"],
                    "reason": (
                        "正文质量尚未达到公开检索条件"
                        if details["skip"]
                        else ""
                    ),
                },
            )
            for consumer, details in sorted(plan.items())
        ]
    )
    transaction.on_commit(lambda event_id=event.id: dispatch_knowledge_event(event_id))
    return event


def _claim_event(event_id) -> tuple[KnowledgePublicationEvent | None, uuid.UUID | None]:
    now = timezone.now()
    with transaction.atomic():
        event = (
            KnowledgePublicationEvent.objects.select_for_update()
            .filter(pk=event_id)
            .first()
        )
        if event is None or event.status in {
            KnowledgePublicationEvent.Status.COMPLETED,
            KnowledgePublicationEvent.Status.DEAD_LETTER,
        }:
            return event, None
        if event.lease_expires_at and event.lease_expires_at > now:
            return event, None
        token = uuid.uuid4()
        event.status = KnowledgePublicationEvent.Status.PROCESSING
        event.attempts += 1
        event.lease_token = token
        event.lease_expires_at = now + timedelta(
            seconds=max(30, int(getattr(settings, "KNOWLEDGE_EVENT_LEASE_SECONDS", 300)))
        )
        event.save(
            update_fields=[
                "status",
                "attempts",
                "lease_token",
                "lease_expires_at",
                "updated_at",
            ]
        )
        return event, token


def _activate_completed_revision(event: KnowledgePublicationEvent) -> None:
    revision = event.catalog_revision
    if revision is None:
        return
    edition = Edition.objects.select_for_update().get(pk=revision.edition_id)
    revision = CatalogPublicationRevision.objects.select_for_update().get(pk=revision.pk)
    # A slow older delivery must never resurrect withdrawn material or replace
    # a newer catalog revision that has already been requested.
    newer_exists = CatalogPublicationRevision.objects.filter(
        edition=edition, revision__gt=revision.revision,
    ).exists()
    if newer_exists or (edition.state != PublicationState.PUBLISHED and revision.status != CatalogPublicationRevision.Status.WITHDRAWN):
        if revision.status == CatalogPublicationRevision.Status.PREPARING:
            revision.status = CatalogPublicationRevision.Status.SUPERSEDED
            revision.superseded_at = timezone.now()
            revision.save(update_fields=["status", "superseded_at", "updated_at"])
        return
    if revision.status == CatalogPublicationRevision.Status.WITHDRAWN:
        edition.intelligence_status = IntelligenceStatus.WITHDRAWN
        edition.save(update_fields=["intelligence_status", "updated_at"])
        _sync_published_work_terms(edition)
        return
    requested_fulltext = bool(event.payload.get("requested_fulltext_ready"))
    if revision.status == CatalogPublicationRevision.Status.PREPARING:
        previous = (
            CatalogPublicationRevision.objects.select_for_update()
            .filter(edition=edition, status=CatalogPublicationRevision.Status.ACTIVE)
            .exclude(pk=revision.pk)
            .first()
        )
        if previous is not None:
            previous.status = CatalogPublicationRevision.Status.SUPERSEDED
            previous.superseded_at = timezone.now()
            previous.save(update_fields=["status", "superseded_at", "updated_at"])
        revision.status = CatalogPublicationRevision.Status.ACTIVE
        revision.activated_at = timezone.now()
    revision.metadata_ready = True
    revision.fulltext_ready = requested_fulltext or revision.fulltext_ready
    revision.failure_code = ""
    revision.failure_message = ""
    revision.save(
        update_fields=[
            "status",
            "activated_at",
            "metadata_ready",
            "fulltext_ready",
            "failure_code",
            "failure_message",
            "updated_at",
        ]
    )
    now = timezone.now()
    edition.active_catalog_revision = revision
    edition.metadata_ready_at = now
    edition.fulltext_ready_at = now if revision.fulltext_ready else None
    edition.intelligence_status = IntelligenceStatus.ACTIVE
    edition.save(
        update_fields=[
            "active_catalog_revision",
            "metadata_ready_at",
            "fulltext_ready_at",
            "intelligence_status",
            "updated_at",
        ]
    )
    if revision.reader_asset_id:
        Asset.objects.filter(edition=edition, kind=Asset.Kind.NORMALIZED, is_current=True).exclude(pk=revision.reader_asset_id).update(is_current=False, updated_at=now)
        Asset.objects.filter(pk=revision.reader_asset_id).update(is_current=True, updated_at=now)
        source_asset = revision.reader_asset.source_asset
        if source_asset and source_asset.kind == Asset.Kind.ORIGINAL:
            Asset.objects.filter(edition=edition, kind=Asset.Kind.ORIGINAL, is_current=True).exclude(pk=source_asset.pk).update(is_current=False, updated_at=now)
            Asset.objects.filter(pk=source_asset.pk).update(is_current=True, updated_at=now)
        reader_pdfs = Asset.objects.filter(edition=edition, kind=Asset.Kind.OCR_PDF, source_asset_id=revision.reader_asset_id, status=Asset.Status.READY)
        reader_pdf = reader_pdfs.order_by("-version", "-created_at").first()
        if reader_pdf:
            Asset.objects.filter(edition=edition, kind=Asset.Kind.OCR_PDF, is_current=True).exclude(pk=reader_pdf.pk).update(is_current=False, updated_at=now)
            Asset.objects.filter(pk=reader_pdf.pk).update(is_current=True, updated_at=now)
    # Work names are derived from the activated snapshot. Sync in the same
    # database transaction, after moving the pointer, so readers never get a
    # new title from the lexicon with the old public catalog revision.
    _sync_published_work_terms(edition)
    if revision.bundle_id:
        PublicationBundle.objects.filter(pk=revision.bundle_id).update(
            status=PublicationBundle.Status.PUBLISHED,
            published_by_id=event.actor_id,
            published_at=now,
            updated_at=now,
        )


def _sync_published_work_terms(edition: Edition) -> None:
    from catalog.services.query_lexicon.registry import EntityKey, WORK_ENTITY_TYPE
    from catalog.services.query_lexicon.sync import ensure_query_lexicon_state, sync_entity

    ensure_query_lexicon_state()
    sync_entity(EntityKey(WORK_ENTITY_TYPE, edition.work_id))


def _finish_event(
    event_id,
    token,
    *,
    pending: bool,
    failed: list[str],
) -> KnowledgePublicationEvent:
    now = timezone.now()
    with transaction.atomic():
        event = (
            KnowledgePublicationEvent.objects.select_for_update()
            .select_related("catalog_revision")
            .get(pk=event_id)
        )
        if event.lease_token != token:
            return event
        max_attempts = max(1, int(getattr(settings, "KNOWLEDGE_EVENT_MAX_ATTEMPTS", 8)))
        if failed:
            terminal = event.attempts >= max_attempts
            event.status = (
                KnowledgePublicationEvent.Status.DEAD_LETTER
                if terminal
                else KnowledgePublicationEvent.Status.FAILED
            )
            event.last_error_code = "projection_delivery_failed"
            event.last_error_message = ", ".join(sorted(failed))[:4000]
            event.next_attempt_at = (
                None
                if terminal
                else now + timedelta(seconds=min(3600, 30 * (2 ** (event.attempts - 1))))
            )
            if terminal and event.catalog_revision_id:
                revision = CatalogPublicationRevision.objects.select_for_update().get(
                    pk=event.catalog_revision_id
                )
                revision.failure_code = event.last_error_code
                revision.failure_message = event.last_error_message
                revision.failed_at = now
                if revision.status == CatalogPublicationRevision.Status.PREPARING:
                    revision.status = CatalogPublicationRevision.Status.FAILED
                revision.save(
                    update_fields=[
                        "status",
                        "failure_code",
                        "failure_message",
                        "failed_at",
                        "updated_at",
                    ]
                )
                latest = not CatalogPublicationRevision.objects.filter(
                    edition_id=revision.edition_id, revision__gt=revision.revision,
                ).exists()
                if latest:
                    Edition.objects.filter(pk=revision.edition_id).update(
                        intelligence_status=IntelligenceStatus.FAILED,
                        updated_at=now,
                    )
                if latest and revision.bundle_id:
                    PublicationBundle.objects.filter(pk=revision.bundle_id).update(
                        status=PublicationBundle.Status.FAILED,
                        updated_at=now,
                    )
        elif pending:
            event.status = KnowledgePublicationEvent.Status.PENDING
            event.next_attempt_at = now + timedelta(seconds=30)
            event.last_error_code = ""
            event.last_error_message = ""
        else:
            _activate_completed_revision(event)
            event.status = KnowledgePublicationEvent.Status.COMPLETED
            event.processed_at = now
            event.next_attempt_at = None
            event.last_error_code = ""
            event.last_error_message = ""
        event.lease_token = None
        event.lease_expires_at = None
        event.save(
            update_fields=[
                "status",
                "processed_at",
                "next_attempt_at",
                "last_error_code",
                "last_error_message",
                "lease_token",
                "lease_expires_at",
                "updated_at",
            ]
        )
        return event


def process_knowledge_event(event_id) -> KnowledgePublicationEvent | None:
    event, token = _claim_event(event_id)
    if event is None or token is None:
        return event
    deliveries = list(event.deliveries.order_by("consumer"))
    states = {
        row.projection_type: row
        for row in ProjectionState.objects.filter(
            object_type=event.object_type,
            object_id=event.object_id,
        )
    }
    pending = False
    failed = []
    now = timezone.now()
    for delivery in deliveries:
        if delivery.status == KnowledgeProjectionDelivery.Status.SKIPPED:
            continue
        requirements = list((delivery.result or {}).get("required_projections") or [])
        required_states = [states.get(name) for name in requirements]
        missing = [name for name, state in zip(requirements, required_states) if state is None]
        failed_states = [
            state
            for state in required_states
            if state is not None
            and state.status == ProjectionState.Status.FAILED
            and state.projected_revision < delivery.source_revision
        ]
        complete = bool(not missing) and all(
            state is not None and state.projected_revision >= delivery.source_revision
            for state in required_states
        )
        delivery.attempts += 1
        delivery.lease_token = token
        delivery.lease_expires_at = event.lease_expires_at
        if complete or not requirements:
            delivery.status = KnowledgeProjectionDelivery.Status.COMPLETED
            delivery.completed_at = now
            delivery.last_error_code = ""
            delivery.last_error_message = ""
        elif failed_states:
            delivery.status = KnowledgeProjectionDelivery.Status.FAILED
            delivery.last_error_code = "projection_failed"
            delivery.last_error_message = ", ".join(
                sorted(state.projection_type for state in failed_states)
            )
            failed.append(delivery.consumer)
        else:
            delivery.status = KnowledgeProjectionDelivery.Status.PENDING
            delivery.last_error_code = ""
            delivery.last_error_message = ""
            pending = True
        delivery.lease_token = None
        delivery.lease_expires_at = None
        delivery.save(
            update_fields=[
                "status",
                "attempts",
                "lease_token",
                "lease_expires_at",
                "completed_at",
                "last_error_code",
                "last_error_message",
                "updated_at",
            ]
        )
    return _finish_event(event.id, token, pending=pending, failed=failed)


def recover_knowledge_events(*, limit: int = 50) -> dict[str, int]:
    now = timezone.now()
    eligible = KnowledgePublicationEvent.objects.filter(
        status__in=[
            KnowledgePublicationEvent.Status.PENDING,
            KnowledgePublicationEvent.Status.FAILED,
            KnowledgePublicationEvent.Status.PROCESSING,
        ]
    ).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now),
        Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now),
    )
    event_ids = list(
        eligible.order_by("created_at").values_list("id", flat=True)[: max(1, limit)]
    )
    dispatched = sum(dispatch_knowledge_event(event_id) for event_id in event_ids)
    return {"candidates": len(event_ids), "dispatched": dispatched}


@transaction.atomic
def retry_knowledge_publication(event_id, *, actor) -> KnowledgePublicationEvent:
    """Resume the same failed event and projections without altering knowledge."""
    from common.capabilities import Capability, has_capability
    from ingestion.models import AuditEvent
    from catalog.services.dependency_engine import resolve_domain_change
    from catalog.services.projection_refresh import queue_projection_refresh

    event = KnowledgePublicationEvent.objects.select_for_update(of=("self",)).select_related("domain_event").get(pk=event_id)
    capability = Capability.PUBLISH_WORK if event.catalog_revision_id else Capability.PUBLISH_AUTHORITY
    if not has_capability(actor, capability):
        raise PermissionError("当前账户没有重新处理这项已发布内容的权限。")
    if event.status in {"pending", "processing", "completed"}:
        return event
    if event.status not in {"failed", "dead_letter"}:
        raise ValueError("这项内容当前不需要重新处理。")
    now = timezone.now()
    if event.lease_expires_at and event.lease_expires_at > now:
        raise ValueError("这项内容仍在处理中，请稍后再试。")
    if not event.domain_event_id:
        raise ValueError("发布记录缺少来源，请在系统诊断中核对。")
    revision = None
    if event.catalog_revision_id:
        revision = CatalogPublicationRevision.objects.select_for_update().get(pk=event.catalog_revision_id)
        if CatalogPublicationRevision.objects.filter(edition_id=revision.edition_id, revision__gt=revision.revision).exists():
            raise ValueError("已存在更新的馆藏修改，请重新处理最新内容。")
        if revision.status in {"superseded", "withdrawn"} and event.event_type != KnowledgePublicationEvent.EventType.CATALOG_WITHDRAWN:
            raise ValueError("这次更新已失效，不能重新激活。")
        if event.event_type != KnowledgePublicationEvent.EventType.CATALOG_WITHDRAWN and not Edition.objects.filter(pk=revision.edition_id, state="published").exists():
            raise ValueError("馆藏已经撤回，不能重新激活旧公开内容。")
    elif KnowledgePublicationEvent.objects.filter(object_type=event.object_type, object_id=event.object_id, created_at__gt=event.created_at).exists():
        raise ValueError("对象已有更新的发布记录，请重新处理最新内容。")
    before = {"status": event.status, "attempts": event.attempts, "error_code": event.last_error_code,
              "error_message": event.last_error_message, "revision_status": revision.status if revision else None,
              "deliveries": list(event.deliveries.values("consumer", "status", "attempts", "last_error_code", "last_error_message"))}
    if event.domain_event.processed_at is None:
        resolve_domain_change(event.domain_event_id)
        event.domain_event.refresh_from_db()
    queue_projection_refresh(target_type=event.object_type, target_id=str(event.object_id), actor=actor,
                             source_event=event.domain_event, force=True, preserve_attempts=True)
    ProjectionState.objects.filter(object_type=event.object_type, object_id=event.object_id, status="failed").update(
        status="stale", stale_reason="管理员请求重新处理", updated_at=now,
    )
    event.deliveries.exclude(status__in=["completed", "skipped"]).update(status="pending", lease_token=None, lease_expires_at=None, updated_at=now)
    if revision is not None:
        if revision.status == "failed":
            revision.status = "preparing"
            revision.save(update_fields=["status", "updated_at"])
        Edition.objects.filter(pk=revision.edition_id).update(intelligence_status=IntelligenceStatus.PROCESSING, updated_at=now)
        if revision.bundle_id:
            PublicationBundle.objects.filter(pk=revision.bundle_id, status="failed").update(status="publishing", updated_at=now)
    event.status = KnowledgePublicationEvent.Status.PENDING
    event.attempts = 0
    event.next_attempt_at = now
    event.lease_token = None
    event.lease_expires_at = None
    event.save(update_fields=["status", "attempts", "next_attempt_at", "lease_token", "lease_expires_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="retry_knowledge_publication", object_type="catalog.KnowledgePublicationEvent",
                              object_id=str(event.pk), before=before,
                              after={"status": event.status, "same_publication_event": True, "same_source_revision": True})
    transaction.on_commit(lambda: dispatch_knowledge_event(event.pk))
    return event
