"""Small source-contract regressions; synthetic text is not business acceptance."""
import pytest
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import ValidationError
from catalog.models import (Work, Edition, Asset, Page, DocumentRevision, DocumentOutlineRevision,
    DocumentNode, RevisionPage, Entity, Assertion, AssertionParticipant, AssertionSource)
from catalog.services.document_intelligence import document_text_checksum
from catalog.services.knowledge_sources import build_structure, create_anchor, locator, snapshot_revision


@pytest.fixture
def source(db):
    work = Work.objects.create(title="来源契约测试")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", page_count=2)
    Page.objects.create(asset=asset, index=1, text="前言\n\n甲😀乙\n\n第一章 测试\n\n跨页引文前半", normalized_text="p1", text_source="embedded")
    Page.objects.create(asset=asset, index=2, text="跨页引文后半\n\n第二节 范围\n\n原始  文本", normalized_text="p2", text_source="embedded")
    revision = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum="f"*64, text_checksum=document_text_checksum(asset))
    DocumentOutlineRevision.objects.create(asset=asset, document_revision=revision, revision=1, source_checksum="f"*64,
        is_active=True, nodes=[{"id":"a", "title":"前言", "pdf_page":1, "level":1},
            {"id":"b", "title":"第一章 测试", "pdf_page":1, "level":1},
            {"id":"c", "title":"第二节 范围", "pdf_page":2, "level":2}])
    return revision


@pytest.mark.django_db
def test_raw_snapshots_cross_page_and_history(source, admin_user):
    structure = build_structure(source)
    assert structure.coverage["mapped_headings"] == 3
    chapter = structure.nodes.get(kind="chapter")
    assert chapter.segments.count() == 2
    pages = list(source.page_snapshots.all())
    text = "跨页引文前半"
    anchor = create_anchor(source, [{"page_number":1,"start":pages[0].text.index(text),"end":len(pages[0].text),"exact":text},
        {"page_number":2,"start":0,"end":6,"exact":"跨页引文后半"}])
    payload = locator(anchor, admin_user, editorial=True)
    assert len(payload["segments"]) == 2
    assert all(s["geometry"] == {} for s in payload["segments"])
    Page.objects.filter(asset=source.asset).update(text="新正文")
    DocumentRevision.objects.filter(pk=source.pk).update(is_active=False)
    assert locator(anchor, admin_user, editorial=True)["exact"] == payload["exact"]
    with pytest.raises(ModelValidationError):
        RevisionPage.objects.filter(pk=pages[0].pk).update(text="禁止覆盖")


@pytest.mark.django_db
def test_codepoint_and_exact_quote(source):
    snapshot_revision(source)
    page = source.page_snapshots.first()
    start = page.text.index("😀")
    anchor = create_anchor(source, [{"page_number":1,"start":start,"end":start+1,"exact":"😀"}])
    assert anchor.segments.get().end - anchor.segments.get().start == 1
    with pytest.raises(ValidationError):
        create_anchor(source, [{"page_number":1,"start":start,"end":start+2,"exact":"😀"}])


@pytest.mark.django_db
def test_unrecoverable_history_does_not_read_latest(source):
    source.is_active = False
    source.save()
    with pytest.raises(ValidationError):
        snapshot_revision(source)


@pytest.mark.django_db
def test_same_name_and_source_specific_assertions(source):
    one = Entity.objects.create(kind="person", label="同名")
    two = Entity.objects.create(kind="person", label="同名")
    assert one.pk != two.pk
    for predicate in ["uses", "criticizes"]:
        statement = Assertion.objects.create(text=predicate, predicate=predicate)
        AssertionParticipant.objects.create(assertion=statement, role="subject", entity=one)
        AssertionSource.objects.create(assertion=statement, work=source.asset.edition.work, edition=source.asset.edition,
            document_revision=source)
    assert one.assertion_participations.count() == 2
