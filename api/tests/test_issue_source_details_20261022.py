"""Readonly edition identity and source display; run at unified acceptance."""
from uuid import uuid4

import pytest

from catalog.services import editorial_issues as ledger
from catalog.services.editorial_blocks import resolve_target
from .test_v307_editorial_issues import public_edition

pytestmark = pytest.mark.django_db


def test_source_metadata_and_cover_follow_exact_published_edition():
    rendition = str(uuid4())
    edition = public_edition(snapshot={"work": {"title": "已公开资料", "cover_media": {"primary_rendition_id": rendition}},
        "edition": {"version_label": "确认版次", "publisher": "确认出版社", "publication_year": 1999},
        "contributions": [{"role": "author", "name": "版本作者"},
                          {"role": "author", "name": "章作者不能标整书", "scope": {"kind": "chapter", "chapters": []}},
                          {"role": "translator", "name": "译者不能标作者"}]})
    edition.publisher, edition.publication_year = "尚未公开的新出版社", 2026
    edition.save(update_fields=["publisher", "publication_year"])
    target, source = resolve_target({"type": "work", "id": str(edition.work_id), "edition_id": str(edition.pk)}, public=True)
    assert target["edition_id"] == str(edition.pk)
    assert source["authors"] == ["版本作者"]
    assert source["publisher"] == "确认出版社" and source["publication_year"] == 1999
    assert f"edition_id={edition.pk}" in source["image_url"] and f"rendition={rendition}" in source["image_url"]
    _, backstage = resolve_target(target)
    assert backstage["title"] == "已公开资料" and backstage["edition_label"] == "确认版次"
    assert backstage["publisher"] == source["publisher"]


def test_withdrawn_source_does_not_expose_old_public_cover():
    edition = public_edition(snapshot={"work": {"title": "已撤回资料", "cover": "legacy.jpg"}, "edition": {"publication_year": 1999}})
    edition.state = "draft"
    edition.save(update_fields=["state"])
    _, source = resolve_target({"type": "work", "id": str(edition.work_id), "edition_id": str(edition.pk)})
    assert not source["public_eligible"] and not source["image_url"]
    assert source["authors"] == [] and source["publication_year"] is None


def test_source_display_fields_are_derived_not_persisted(admin_user):
    edition = public_edition(snapshot={"work": {"title": "只读来源", "cover": "legacy.jpg"}, "edition": {"publisher": "正式出版社"}})
    target, source = resolve_target({"type": "work", "id": str(edition.work_id), "edition_id": str(edition.pk)}, public=True)
    issue = ledger.create_issue({"title": "来源展示验收", "body_blocks": [{"type": "work", "text": "人工导读", "target": target,
        "resolved_sources": [{**source, "publisher": "客户端伪造出版社"}]}]}, admin_user)
    saved = ledger.issue_draft_payload(issue)["body_blocks"][0]
    assert "resolved_sources" not in saved and "image_url" not in saved
    resolved = ledger.issue_payload(issue)["body_blocks"][0]["resolved_sources"][0]
    assert resolved["publisher"] == "正式出版社"


def test_span_author_and_reader_link_remain_bound_to_exact_page_and_revision():
    from catalog.models import EvidenceSpan
    from .test_contribution_retrieval_20261021 import responsibility_source
    edition, asset, active, people, _ = responsibility_source()
    page = asset.pages.get(index=1)
    span = EvidenceSpan.objects.create(document_revision=active.document_revision, page=page, page_number=1,
        original_text="只供来源验收的原文", normalized_text="只供来源验收的原文", start_offset=0, end_offset=10,
        content_hash="c" * 64, section="已核实第一章")
    target, source = resolve_target({"type": "span", "id": str(span.pk), "document_revision_id": str(active.document_revision_id)}, public=True)
    assert source["authors"] == [people[0].preferred_name, people[1].preferred_name]
    assert source["section"] == "已核实第一章"
    assert "page=1" in source["reader_url"] and f"revision={active.document_revision_id}" in source["reader_url"]
    assert target["document_revision_id"] == str(active.document_revision_id)
