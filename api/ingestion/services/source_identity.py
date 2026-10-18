"""Recognize an authorized, not-yet-active replacement from persisted lineage."""
from django.db.models import F

from catalog.models import Asset
from ingestion.models import UploadItem


def pending_replacement_source(asset, *, upload_item_id=None):
    """Return the intake authority for exactly these new PDF bytes.

    A replacement stays noncurrent until its publication event activates. Its
    old reader must still be the active source; a historical UploadItem alone
    never authorizes an old task to revive superseded bytes.
    """
    if asset.is_current or asset.kind != Asset.Kind.NORMALIZED or not asset.source_asset_id:
        return None
    items = UploadItem.objects.filter(
        edition_id=asset.edition_id, asset_id=asset.source_asset_id, sha256=asset.sha256,
        asset__kind=Asset.Kind.ORIGINAL, asset__sha256=asset.sha256,
        asset__edition_id=asset.edition_id,
        replacement_of_asset__edition_id=asset.edition_id,
        replacement_of_asset__kind=Asset.Kind.NORMALIZED,
        replacement_of_asset__is_current=True,
        edition__state="published", edition__active_catalog_revision__status="active",
        edition__active_catalog_revision__metadata_ready=True,
        edition__active_catalog_revision__edition_id=asset.edition_id,
        replacement_of_asset_id=F("edition__active_catalog_revision__reader_asset_id"),
    ).exclude(status__in=["withdrawn", "deleted"]).exclude(workflow_state__in=["cancelled", "archived"])
    if upload_item_id is not None:
        items = items.filter(pk=upload_item_id)
    return items.order_by("-created_at").first()
