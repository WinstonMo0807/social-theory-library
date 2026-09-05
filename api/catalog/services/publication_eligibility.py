"""Reader-facing eligibility derived from an activated catalog revision.

``Edition.state`` records the editorial publication decision.  It is not on
its own sufficient for public search or RAG because a newer revision may still
be preparing.  Every public consumer should use these predicates so the last
activated snapshot remains the serving boundary.
"""

from __future__ import annotations

from django.db.models import F, Q, QuerySet

from catalog.models import CatalogPublicationRevision, Edition, PublicationState


def _path(prefix: str, field: str) -> str:
    clean = str(prefix or "").strip("_")
    return f"{clean}__{field}" if clean else field


def public_edition_q(*, prefix: str = "", require_fulltext: bool = False) -> Q:
    """Return the shared activated-revision visibility predicate."""

    conditions = {
        _path(prefix, "state"): PublicationState.PUBLISHED,
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
        or revision.status != CatalogPublicationRevision.Status.ACTIVE
        or not revision.metadata_ready
        or (require_fulltext and not revision.fulltext_ready)
        or (require_fulltext and revision.document_revision_id is None)
    ):
        return {}
    return revision.snapshot if isinstance(revision.snapshot, dict) else {}


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


def active_document_q(*, asset_prefix: str) -> Q:
    """Require content to belong to the activated fulltext source asset."""

    return active_asset_q(asset_prefix=asset_prefix, require_fulltext=True)


def active_document_revision_q(*, revision_prefix: str) -> Q:
    """Require evidence to point at the exact activated document revision."""

    asset_prefix = _path(revision_prefix, "asset")
    edition_prefix = _path(asset_prefix, "edition")
    return public_edition_q(
        prefix=edition_prefix,
        require_fulltext=True,
    ) & Q(
        **{
            _path(revision_prefix, "id"): F(
                _path(edition_prefix, "active_catalog_revision__document_revision_id")
            )
        }
    )
