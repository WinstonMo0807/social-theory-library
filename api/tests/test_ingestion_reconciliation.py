import pytest

from catalog.models import Contribution, Edition, Person, ScholarProfile, Work
from ingestion.models import EntityResolutionCandidate, ReviewTask, UploadBatch, UploadItem
from ingestion.services.metadata import Candidate
from ingestion.services.pipeline import _create_or_update_catalog
from ingestion.services.reconciliation import find_entity_matches, propose_author_reconciliation


pytestmark = pytest.mark.django_db


def make_item(admin_user, filename="reconciliation.pdf"):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(batch=batch, source_filename=filename)


def test_name_only_author_match_is_never_merged_automatically(admin_user):
    existing = Person.objects.create(
        preferred_name="王明",
        sort_name="王明",
        birth_year=1911,
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    item = make_item(admin_user)

    count = propose_author_reconciliation(item, ["王明"])

    assert count == 2
    rows = list(item.entity_resolution_candidates.order_by("-match_score"))
    assert rows[0].candidate_entity_id == str(existing.id)
    assert rows[0].status == EntityResolutionCandidate.Status.PROPOSED
    assert "同名" in rows[0].conflicts[0]
    assert rows[1].candidate_entity_type == "person_draft"
    assert Person.objects.count() == 1
    assert ReviewTask.objects.filter(upload_item=item, task_type="entity_resolution").count() == 1


def test_pipeline_keeps_author_as_candidate_without_public_scholar_side_effect(admin_user):
    item = make_item(admin_user, "candidate-only.pdf")
    candidates = [
        Candidate("title", "候选上架图书", "first_pages", 0.8, {"page": 1}),
        Candidate("authors", ["候选作者"], "first_pages", 0.7, {"page": 1}),
        Candidate("document_type", "book", "first_pages", 0.8, {"page": 1}),
    ]
    selected = {
        "title": "候选上架图书",
        "authors": ["候选作者"],
        "document_type": "book",
    }

    edition = _create_or_update_catalog(item, selected, candidates, "无受控词命中的文本")

    assert Work.objects.filter(pk=edition.work_id).exists()
    assert Edition.objects.filter(pk=edition.pk).exists()
    assert Person.objects.count() == 0
    assert ScholarProfile.objects.count() == 0
    assert not edition.contributions.exists()
    assert item.entity_resolution_candidates.filter(
        target_type="person",
        source_name="候选作者",
        candidate_entity_type="person_draft",
    ).exists()


def test_work_and_publisher_reconciliation_return_explainable_candidates(admin_user):
    existing_work = Work.objects.create(document_type="book", title="社会学的想象力", language="zh-CN")
    Edition.objects.create(work=existing_work, publication_year=2008, isbn="9780000000001")

    matches = find_entity_matches(target_type="work", source_name="社会学的想象力")

    assert matches[0]["entity_id"] == str(existing_work.id)
    assert matches[0]["score"] >= 0.8
    assert matches[0]["supporting_properties"]["edition_count"] == 1
    assert matches[0]["conflicts"]


def test_strong_isbn_reuses_existing_edition_without_overwriting_catalog(admin_user):
    work = Work.objects.create(document_type="book", title="已有版本", language="zh-CN")
    existing = Edition.objects.create(
        work=work,
        publication_year=2019,
        publisher="原出版社",
        isbn="978-7-1234-5678-9",
        isbn13="9787123456789",
    )
    item = make_item(admin_user, "new-scan.pdf")
    selected = {
        "title": "错误 OCR 题名",
        "document_type": "book",
        "publication_year": 2020,
        "publisher": "错误候选出版社",
        "isbn": "9787123456789",
    }

    edition = _create_or_update_catalog(item, selected, [], "")

    assert edition.pk == existing.pk
    existing.refresh_from_db()
    assert existing.work.title == "已有版本"
    assert existing.publication_year == 2019
    assert existing.publisher == "原出版社"
    item.refresh_from_db()
    assert item.preflight_summary["catalog_reconciliation"]["mode"] == "existing_edition"


def test_same_work_new_edition_requires_title_and_confirmed_author(admin_user):
    work = Work.objects.create(document_type="book", title="乡土中国", language="zh-CN")
    old_edition = Edition.objects.create(work=work, publication_year=2006)
    author = Person.objects.create(
        preferred_name="费孝通",
        sort_name="费孝通",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    Contribution.objects.create(
        edition=old_edition,
        person=author,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )
    item = make_item(admin_user, "new-edition.pdf")
    selected = {
        "title": "乡土中国",
        "document_type": "book",
        "authors": ["费孝通"],
        "publication_year": 2024,
        "isbn": "9787300000000",
    }

    edition = _create_or_update_catalog(item, selected, [], "")

    assert edition.pk != old_edition.pk
    assert edition.work_id == work.id
    assert Work.objects.filter(title="乡土中国").count() == 1
    assert edition.isbn13 == "9787300000000"
    item.refresh_from_db()
    assert item.preflight_summary["catalog_reconciliation"]["mode"] == "existing_work"


def test_same_title_without_strong_identity_stays_separate_and_requests_review(admin_user):
    Work.objects.create(document_type="book", title="社会理论", language="zh-CN")
    item = make_item(admin_user, "ambiguous-title.pdf")
    selected = {
        "title": "社会理论",
        "document_type": "book",
        "authors": ["未核验作者"],
    }

    edition = _create_or_update_catalog(item, selected, [], "")

    assert Work.objects.filter(title="社会理论").count() == 2
    assert edition.work.title == "社会理论"
    item.refresh_from_db()
    summary = item.preflight_summary["catalog_reconciliation"]
    assert summary["mode"] == "ambiguous"
    assert summary["requires_review"] is True
    assert item.review_tasks.filter(task_type="entity_resolution", target_type="work").exists()
