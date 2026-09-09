from copy import deepcopy

import pytest

from catalog.models import CatalogingSession, Edition, Work
from ingestion.models import DecisionLog, EntityResolutionCandidate, UploadBatch, UploadItem
from ingestion.services.catalog_reconciliation import effective_catalog_reconciliation
from ingestion.services.entity_resolution_decisions import decide_entity_resolution, revert_entity_resolution_decision
from ingestion.services.pipeline import _create_or_update_catalog


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("context", ["upload", "session"])
def test_effective_work_identity_follows_current_human_choice_and_revert(admin_user, context):
    provisional = Work.objects.create(title="待判断作品", document_type="book", language="zh-CN")
    target = Work.objects.create(title="已有规范作品", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=provisional)
    report = {"catalog_reconciliation": {"mode": "ambiguous", "requires_review": True, "conflicts": ["原始同名证据"]}}
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, edition=edition, source_filename="reconcile.pdf", preflight_summary=deepcopy(report))
    session = CatalogingSession.objects.create(source_type="manual", edition=edition, created_by=admin_user) if context == "session" else None
    candidate = EntityResolutionCandidate.objects.create(
        upload_item=item if context == "upload" else None, cataloging_session=session,
        target_type="work", source_name="待判断作品", candidate_entity_type="work",
        candidate_entity_id=str(target.pk), label=target.title,
    )
    assert effective_catalog_reconciliation(item)["requires_review"] is True
    decide_entity_resolution(candidate, action="link_existing", target_type="work", target_id=str(target.pk), actor=admin_user)
    item.refresh_from_db()
    effective = effective_catalog_reconciliation(item)
    assert effective["mode"] == "existing_work" and effective["requires_review"] is False
    assert effective["resolution_candidate_id"] == str(candidate.pk)
    assert item.preflight_summary == report
    result = _create_or_update_catalog(item, {"title": "重跑的错误题名", "language": "en", "document_type": "book"}, [], "")
    target.refresh_from_db()
    assert result.work_id == target.pk
    assert target.title == "已有规范作品" and target.language == "zh-CN"
    decision = DecisionLog.objects.get(resolution_candidate=candidate, action="link_existing")
    revert_entity_resolution_decision(decision, actor=admin_user, reason="恢复原待审身份")
    item.refresh_from_db()
    assert item.edition.work_id == provisional.pk
    assert effective_catalog_reconciliation(item)["requires_review"] is True
    assert item.preflight_summary == report
    assert Work.objects.filter(pk=target.pk).exists()


def test_unreviewed_or_unrelated_choice_does_not_claim_identity_is_resolved(admin_user):
    from django.utils import timezone

    work = Work.objects.create(title="当前作品", document_type="book")
    unrelated = Work.objects.create(title="其他作品", document_type="book")
    edition = Edition.objects.create(work=work)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, edition=edition, source_filename="unreviewed.pdf", preflight_summary={"catalog_reconciliation": {"mode": "ambiguous", "requires_review": True}})
    row = EntityResolutionCandidate.objects.create(
        upload_item=item, target_type="work", candidate_entity_type="work", candidate_entity_id=str(work.pk),
        source_name=work.title, label=work.title, status="linked",
    )
    assert effective_catalog_reconciliation(item)["requires_review"] is True
    row.reviewed_by = admin_user
    row.reviewed_at = timezone.now()
    row.candidate_entity_id = str(unrelated.pk)
    row.save()
    assert effective_catalog_reconciliation(item)["requires_review"] is True


def test_work_choice_cannot_downgrade_existing_edition_protection(admin_user):
    work = Work.objects.create(title="复用整版的原题名", document_type="book")
    edition = Edition.objects.create(work=work, publisher="原出版社", publication_year=1999)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    report = {"catalog_reconciliation": {"mode": "existing_edition", "requires_review": False}}
    item = UploadItem.objects.create(batch=batch, edition=edition, source_filename="same-edition.pdf", preflight_summary=report)
    row = EntityResolutionCandidate.objects.create(
        upload_item=item, target_type="work", candidate_entity_type="work", candidate_entity_id=str(work.pk),
        source_name=work.title, label=work.title,
    )
    decide_entity_resolution(row, action="link_existing", target_type="work", target_id=str(work.pk), actor=admin_user)
    item.refresh_from_db()
    assert effective_catalog_reconciliation(item)["mode"] == "existing_edition"
    _create_or_update_catalog(item, {"title": "新文件识别值", "publisher": "新文件出版社", "publication_year": 2026}, [], "")
    edition.refresh_from_db()
    work.refresh_from_db()
    assert work.title == "复用整版的原题名"
    assert edition.publisher == "原出版社" and edition.publication_year == 1999
