"""Reader-facing eligibility derived from an activated catalog revision.

``Edition.state`` records the editorial publication decision.  It is not on
its own sufficient for public search or RAG because a newer revision may still
be preparing.  Every public consumer should use these predicates so the last
activated snapshot remains the serving boundary.
"""

from __future__ import annotations

from uuid import UUID

from django.db.models import F, Q, QuerySet

from catalog.models import (
    CatalogPublicationRevision, Discipline, Edition, KnowledgeNode,
    PublicationState, Subdiscipline, Topic,
)


def _path(prefix: str, field: str) -> str:
    clean = str(prefix or "").strip("_")
    return f"{clean}__{field}" if clean else field


def public_edition_q(*, prefix: str = "", require_fulltext: bool = False) -> Q:
    """Return the shared activated-revision visibility predicate."""

    conditions = {
        _path(prefix, "state"): PublicationState.PUBLISHED,
        _path(prefix, "active_catalog_revision__edition_id"): F(_path(prefix, "id")),
        _path(prefix, "active_catalog_revision__status"): (
            CatalogPublicationRevision.Status.ACTIVE
        ),
        _path(prefix, "active_catalog_revision__metadata_ready"): True,
    }
    if require_fulltext:
        conditions.update(
            {
                _path(prefix, "active_catalog_revision__fulltext_ready"): True,
                _path(
                    prefix,
                    "active_catalog_revision__document_revision__isnull",
                ): False,
            }
        )
    return Q(**conditions)


def public_editions(*, require_fulltext: bool = False) -> QuerySet:
    return Edition.objects.filter(
        public_edition_q(require_fulltext=require_fulltext)
    ).select_related(
        "work",
        "active_catalog_revision",
        "active_catalog_revision__reader_asset",
        "active_catalog_revision__document_revision",
    )


def public_taxonomy_snapshot(snapshot: dict) -> dict:
    """Mask withdrawn taxonomy at read time without rewriting past revisions.

    An approved relationship cannot publish its endpoint. Snapshots preserve
    the confirmed labels, but current entity eligibility remains mandatory.
    No process-wide cache is used so withdrawal takes effect on the next read.
    """
    result = dict(snapshot)
    for section, field, model, status_field in (
        ("classification", "disciplines", Discipline, "editorial_status"),
        ("classification", "subdisciplines", Subdiscipline, "editorial_status"),
        ("knowledge", "topics", Topic, "editorial_status"),
        ("knowledge", "nodes", KnowledgeNode, "status"),
    ):
        values = result.get(section)
        if not isinstance(values, dict) or field not in values:
            continue
        rows = values.get(field)
        rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        identifiers = set()
        for row in rows:
            try:
                identifiers.add(UUID(str(row.get("id"))))
            except (ValueError, TypeError, AttributeError):
                continue
        published = {
            str(value) for value in model.objects.filter(
                pk__in=identifiers, **{status_field: "published"},
            ).values_list("pk", flat=True)
        } if identifiers else set()
        result[section] = {
            **values,
            field: [row for row in rows if str(row.get("id")) in published],
        }
    return result


def active_catalog_snapshot(
    edition: Edition | None,
    *,
    require_fulltext: bool = False,
) -> dict:
    """Return an activated snapshot, or an empty mapping when not eligible."""

    if edition is None or edition.state != PublicationState.PUBLISHED:
        return {}
    revision = getattr(edition, "active_catalog_revision", None)
    if (
        revision is None
        or revision.edition_id != edition.pk
        or revision.status != CatalogPublicationRevision.Status.ACTIVE
        or not revision.metadata_ready
        or (require_fulltext and not revision.fulltext_ready)
        or (require_fulltext and revision.document_revision_id is None)
    ):
        return {}
    if not isinstance(revision.snapshot, dict):
        return {}
    snapshot = public_taxonomy_snapshot(revision.snapshot)
    from catalog.services.academic_projection import published_knowledge_nodes
    knowledge = snapshot.get("knowledge") or {}
    snapshot["knowledge"] = {**knowledge, "nodes": published_knowledge_nodes(edition.work_id, knowledge.get("nodes") or [])}
    return snapshot


def active_asset_q(*, asset_prefix: str, require_fulltext: bool = False) -> Q:
    """Require an Asset to be the reader source captured by the active revision."""

    edition_prefix = _path(asset_prefix, "edition")
    return public_edition_q(
        prefix=edition_prefix,
        require_fulltext=require_fulltext,
    ) & Q(
        **{
            _path(asset_prefix, "id"): F(
                _path(
                    edition_prefix,
                    "active_catalog_revision__reader_asset_id",
                )
            )
        }
    )


def active_document_q(*, asset_prefix: str, require_fulltext: bool = True) -> Q:
    """Require content to belong to the activated fulltext source asset."""

    return active_asset_q(asset_prefix=asset_prefix, require_fulltext=require_fulltext)


def active_document_revision_q(*, revision_prefix: str, require_fulltext: bool = True) -> Q:
    """Require evidence to point at the exact activated document revision."""

    asset_prefix = _path(revision_prefix, "asset")
    edition_prefix = _path(asset_prefix, "edition")
    return public_edition_q(
        prefix=edition_prefix,
        require_fulltext=require_fulltext,
    ) & Q(
        **{
            _path(revision_prefix, "id"): F(
                _path(edition_prefix, "active_catalog_revision__document_revision_id")
            )
        }
    )


def current_retrieval_source_q(*, asset_prefix: str, access_statuses, require_fulltext: bool = True) -> Q:
    """Exact readable source for retrieval; None access is reserved for index workers.

    Metadata-only publication keeps its separate eligibility. An explicit empty
    access set matches no source, including when restoring an older search.
    Exact reader references may opt out of search readiness, but still require
    the active document, matching file checksum, and the caller's access set.
    """
    revision_prefix = _path(asset_prefix, "edition__active_catalog_revision__document_revision")
    condition = active_asset_q(asset_prefix=asset_prefix, require_fulltext=require_fulltext) & Q(**{
        _path(asset_prefix, "kind"): "normalized",
        _path(asset_prefix, "status"): "ready",
        _path(asset_prefix, "validation_status"): "valid",
        _path(revision_prefix, "asset_id"): F(_path(asset_prefix, "id")),
        _path(revision_prefix, "is_active"): True,
        _path(revision_prefix, "source_checksum"): F(_path(asset_prefix, "sha256")),
    }) & ~Q(**{_path(asset_prefix, "file"): ""}) & ~Q(**{_path(asset_prefix, "sha256"): ""})
    if access_statuses is not None:
        condition &= Q(**{_path(asset_prefix, "access_status__in"): access_statuses})
    return condition
