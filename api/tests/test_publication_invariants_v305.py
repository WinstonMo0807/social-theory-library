from hashlib import sha256

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import CatalogPublicationRevision, Edition, PublicationState, Work
from catalog.services.knowledge_publication import create_catalog_publication_event
from catalog.services.publication_eligibility import (
    active_catalog_snapshot,
    public_edition_q,
    public_editions,
)


pytestmark = pytest.mark.django_db


def published_edition(title):
    work = Work.objects.create(title=title, document_type="book", language="zh-CN")
    edition = Edition.objects.create(
        work=work, state=PublicationState.PUBLISHED, public_slug=f"v305-{work.pk}",
    )
    revision = CatalogPublicationRevision.objects.create(
        edition=edition, revision=1, status=CatalogPublicationRevision.Status.ACTIVE,
        metadata_ready=True, snapshot={"work": {"id": str(work.pk), "title": title}},
        content_fingerprint=sha256(title.encode()).hexdigest(), activated_at=timezone.now(),
    )
    edition.active_catalog_revision = revision
    edition.save(update_fields=["active_catalog_revision", "updated_at"])
    return edition, revision


def test_public_selectors_reject_cross_edition_pointer_without_modifying_history():
    first, original = published_edition("第一本已发布作品")
    other, unrelated = published_edition("另一版本的内容")
    # Model the inconsistent historical/database state that a selector must
    # fail closed on. A nullable FK alone cannot express this cross-row rule.
    Edition.objects.filter(pk=first.pk).update(active_catalog_revision=unrelated)
    first.refresh_from_db()

    assert active_catalog_snapshot(first) == {}
    assert not public_editions().filter(pk=first.pk).exists()
    assert not Work.objects.filter(public_edition_q(prefix="editions"), pk=first.work_id).exists()
    assert public_editions().filter(pk=other.pk).exists()
    original.refresh_from_db()
    unrelated.refresh_from_db()
    assert original.snapshot["work"]["title"] == "第一本已发布作品"
    assert unrelated.snapshot["work"]["title"] == "另一版本的内容"


def test_public_detail_does_not_serve_another_editions_snapshot(api_client):
    edition, _original = published_edition("公开记录")
    _other, unrelated = published_edition("不属于这本书")
    Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=unrelated)
    response = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
    assert response.status_code == 404


def test_publication_rejects_invalid_prior_pointer_without_new_event():
    edition, original = published_edition("原记录")
    _other, unrelated = published_edition("其他记录")
    Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=unrelated)
    before = edition.catalog_revisions.count()
    with pytest.raises(ValueError, match="不属于"):
        create_catalog_publication_event(
            edition, event_type="catalog_updated", changed_fields=["cover"],
            idempotency_key="v305:invalid-prior-pointer",
        )
    assert edition.catalog_revisions.count() == before
    assert not edition.catalog_revisions.filter(knowledge_events__isnull=False).exists()
    original.refresh_from_db()
    assert original.status == CatalogPublicationRevision.Status.ACTIVE


@pytest.mark.parametrize("status,metadata_ready", [
    ("preparing", True), ("failed", True), ("withdrawn", False), ("active", False),
])
def test_non_serving_revision_is_never_exposed(status, metadata_ready):
    edition, revision = published_edition("稳定公开资格")
    revision.status = status
    revision.metadata_ready = metadata_ready
    revision.save(update_fields=["status", "metadata_ready", "updated_at"])
    edition.refresh_from_db()
    assert active_catalog_snapshot(edition) == {}
    assert not public_editions().filter(pk=edition.pk).exists()


def test_database_keeps_only_one_active_revision_per_edition():
    edition, _revision = published_edition("唯一公开修订")
    with pytest.raises(IntegrityError), transaction.atomic():
        CatalogPublicationRevision.objects.create(
            edition=edition, revision=2, status="active", metadata_ready=True,
            content_fingerprint="a" * 64,
        )


def test_draft_changes_and_failed_new_revision_do_not_replace_public_snapshot():
    edition, original = published_edition("读者仍看到的原题名")
    edition.work.title = "后台草稿新题名"
    edition.work.save()
    CatalogPublicationRevision.objects.create(
        edition=edition, revision=2, status="failed", metadata_ready=False,
        snapshot={"work": {"title": "准备失败的题名"}}, content_fingerprint="b" * 64,
    )
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == original.pk
    assert active_catalog_snapshot(edition)["work"]["title"] == "读者仍看到的原题名"
    assert public_editions().filter(pk=edition.pk).exists()
