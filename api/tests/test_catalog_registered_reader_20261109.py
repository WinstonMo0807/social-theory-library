"""Activated catalog reader links follow the current caller's file access."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import AnonymousUser

from catalog.catalog_search_serializers import CatalogEditionSerializer
from catalog.models import Asset, Edition, Work
from catalog.public_work_detail import PublicWorkDetailSerializer
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def published_asset(access):
    work = Work.objects.create(title="Synthetic registered catalog work")
    edition = Edition.objects.create(work=work, state="published", is_primary=True,
                                     public_slug=f"session-{uuid4()}")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready",
        validation_status="valid", access_status=access, file="test/reader.pdf",
        is_current=True, page_count=12, sha256=uuid4().hex * 2)
    activate_catalog_revision(edition, reader_asset=asset)
    return work, edition, asset


@pytest.mark.parametrize("actor", ["anonymous", "reader", "admin"])
@pytest.mark.parametrize("access", ["public", "inherit", "registered", "restricted", "private"])
def test_current_caller_gets_only_permitted_catalog_reader(access, actor, reader_user, admin_user):
    _, edition, asset = published_asset(access)
    user = {"anonymous": AnonymousUser(), "reader": reader_user, "admin": admin_user}[actor]
    data = CatalogEditionSerializer(edition, context={"request": SimpleNamespace(user=user)}).data
    allowed = access in {"public", "inherit"} or (access == "registered" and actor != "anonymous")
    assert bool(data["readable_asset"]) == allowed
    assert data["availability"] == ("readable" if allowed else "metadata")
    if allowed:
        assert data["readable_asset"]["id"] == str(asset.pk)
    if access == "private":
        assert data["access_state"] == "metadata"


@pytest.mark.parametrize("invalid", ["not_ready", "invalid", "empty_file", "wrong_snapshot"])
def test_signed_in_reader_still_requires_exact_ready_asset(invalid, reader_user, monkeypatch):
    _, edition, asset = published_asset("registered")
    if invalid == "not_ready": asset.status = "processing"
    elif invalid == "invalid": asset.validation_status = "invalid"
    elif invalid == "empty_file": asset.file = ""
    else:
        from copy import deepcopy
        snapshot = deepcopy(edition.active_catalog_revision.snapshot)
        snapshot["document"]["asset_id"] = str(uuid4())
        monkeypatch.setattr("catalog.catalog_search_serializers.active_catalog_snapshot", lambda _: snapshot)
    asset.save()
    edition.refresh_from_db()
    data = CatalogEditionSerializer(edition, context={"request": SimpleNamespace(user=reader_user)}).data
    assert data["readable_asset"] is None


def test_registered_outline_and_reader_share_access_rule(reader_user, monkeypatch):
    work, edition, asset = published_asset("registered")
    seen = []
    def outline(current, *, access_statuses):
        seen.append((current.pk, set(access_statuses)))
        return [{"title": "Synthetic chapter"}]
    monkeypatch.setattr("catalog.services.document_outline.public_outline", outline)
    context = {"selected_edition": edition, "request": SimpleNamespace(user=reader_user)}
    assert PublicWorkDetailSerializer(context=context).get_outline(work) == [{"title": "Synthetic chapter"}]
    assert seen == [(asset.pk, {"public", "inherit", "registered"})]
    context["request"] = SimpleNamespace(user=AnonymousUser())
    assert PublicWorkDetailSerializer(context=context).get_outline(work) == []
    assert len(seen) == 1
