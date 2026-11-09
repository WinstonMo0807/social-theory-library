"""A draft parent may preview published evidence without becoming public."""
from types import SimpleNamespace
from hashlib import sha256

import pytest
from django.http import Http404
from rest_framework.exceptions import PermissionDenied

from catalog.models import EditorialRevision, EvidenceSpan
from catalog.services.public_scholars import preview_scholar, public_scholar_detail
from catalog.services.shared_curation import curation_payload, preview_published_curation, save_curation, publish_curation
from .test_public_scholars_20261021 import profile
from .test_reading_paths_20261021 import source

pytestmark = pytest.mark.django_db


def draft_with_quote(actor):
    scholar = profile()
    _, _, asset, revision = source()
    page = asset.pages.get(index=1)
    page.text = "Synthetic evidence for a draft parent."
    page.save(update_fields=["text"])
    span = EvidenceSpan.objects.create(document_revision=revision.document_revision,
        page=page, page_number=1, original_text=page.text, normalized_text=page.text,
        start_offset=0, end_offset=len(page.text), content_hash=sha256(page.text.encode()).hexdigest())
    saved = save_curation("scholar", scholar.pk, {"edit_version": "0", "items": [
        {"source_type": "span", "source_id": str(span.pk)}]}, actor)
    publish_curation("scholar", scholar.pk, saved["edit_version"], actor)
    quote = saved["items"][0]
    scholar.editorial_status = "draft"
    scholar.save(update_fields=["editorial_status"])
    return scholar, quote


def test_draft_parent_previews_original_without_publishing_or_mutation(admin_user):
    scholar, quote = draft_with_quote(admin_user)
    before = EditorialRevision.objects.count()
    result = preview_scholar(scholar, request=SimpleNamespace(user=admin_user))
    assert result["evidence"]["count"] == 1
    assert result["evidence"]["results"][0]["id"] == quote["id"]
    scholar.refresh_from_db()
    assert scholar.editorial_status == "draft"
    assert EditorialRevision.objects.count() == before
    with pytest.raises(Http404):
        public_scholar_detail(scholar.slug)
    with pytest.raises(Http404):
        curation_payload("scholar", scholar.pk, public=True)


@pytest.mark.parametrize("hidden", ["restricted", "stale"])
def test_preview_still_excludes_unavailable_or_stale_sources(admin_user, hidden):
    scholar, quote = draft_with_quote(admin_user)
    span = EvidenceSpan.objects.get(pk=quote["source_id"])
    if hidden == "restricted":
        span.page.asset.access_status = "restricted"
        span.page.asset.save(update_fields=["access_status"])
    else:
        span.is_stale = True
        span.save(update_fields=["is_stale"])
    result = preview_scholar(scholar, request=SimpleNamespace(user=admin_user))
    assert result["evidence"]["count"] == 0


def test_published_evidence_preview_requires_backoffice(admin_user, reader_user):
    scholar, _ = draft_with_quote(admin_user)
    for request in [None, SimpleNamespace(user=reader_user)]:
        with pytest.raises(PermissionDenied):
            preview_published_curation("scholar", scholar.pk, request=request)
