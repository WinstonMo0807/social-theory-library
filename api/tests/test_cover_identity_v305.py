from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.models import Asset, CatalogFieldDecision, CoverCandidate, Edition, Work
from catalog.services.covers import CoverCandidateUnavailable, select_cover_candidate


pytestmark = pytest.mark.django_db


def test_cover_from_previous_work_is_rejected_after_edition_is_relinked(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    previous = Work.objects.create(title="识别时的临时作品", document_type="book", language="zh-CN")
    current = Work.objects.create(title="后来人工关联的作品", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=previous)
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", sha256="b" * 64)
    output = BytesIO()
    Image.new("RGB", (20, 30), "white").save(output, format="JPEG")
    candidate = CoverCandidate.objects.create(
        work=previous, asset=asset, page_index=1,
        thumbnail=SimpleUploadedFile("old-cover.jpg", output.getvalue(), content_type="image/jpeg"),
    )
    edition.work = current
    edition.save(update_fields=["work", "updated_at"])
    with pytest.raises(CoverCandidateUnavailable, match="作品已变化"):
        select_cover_candidate(candidate, actor=admin_user, edition_id=edition.pk)
    previous.refresh_from_db()
    current.refresh_from_db()
    candidate.refresh_from_db()
    assert not previous.cover and not current.cover
    assert candidate.selected is False
    assert not CatalogFieldDecision.objects.filter(edition=edition, field_name="cover").exists()
    assert candidate.thumbnail.storage.exists(candidate.thumbnail.name)


def test_current_work_cover_still_saves_with_the_original_thumbnail_preserved(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="归属一致的作品", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", sha256="c" * 64)
    output = BytesIO()
    Image.new("RGB", (20, 30), "white").save(output, format="JPEG")
    candidate = CoverCandidate.objects.create(
        work=work, asset=asset, page_index=1,
        thumbnail=SimpleUploadedFile("current-cover.jpg", output.getvalue(), content_type="image/jpeg"),
    )
    selected = select_cover_candidate(candidate, actor=admin_user, edition_id=edition.pk)
    assert selected["saved"] is True
    work.refresh_from_db()
    candidate.refresh_from_db()
    assert work.cover and work.cover.storage.exists(work.cover.name)
    assert candidate.selected is True
    assert candidate.thumbnail.storage.exists(candidate.thumbnail.name)
    assert CatalogFieldDecision.objects.get(edition=edition, field_name="cover").confirmed_by == admin_user
