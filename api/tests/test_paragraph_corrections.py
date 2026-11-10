from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError, PermissionDenied

from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services.knowledge_sources import build_structure, create_anchor, locator, current_structure, node_text
from catalog.services.paragraph_corrections import correct_paragraph, paragraph_ranges
from catalog.services.document_structure import install_structure, ADAPTER_VERSION, DOCLING_VERSION

pytestmark = pytest.mark.django_db


def join_args(source):
    structure = build_structure(source)
    nodes = [n for n in structure.nodes.filter(kind="paragraph").prefetch_related("segments__page") if node_text(n).startswith("跨页引文")]
    assert len(nodes) == 2
    return {"node_ids": [str(n.pk) for n in nodes], "base_hash": structure.input_hash,
        "reason": "测试夹具：已核对连续正文", "request_id": uuid4()}


def parsed(source, pages, text, page):
    return {"schema": ADAPTER_VERSION, "parser_version": DOCLING_VERSION, "source_checksum": source.source_checksum,
        "heading_hierarchy_enabled": True, "ocr_performed": False, "status": "success", "pages": pages,
        "items": [{"ref": "#/texts/0", "label": "text", "text": text, "prov": [{"page_no": page, "charspan": [0,len(text)]}]}]}


def test_join_preserves_original_anchor_notes_replay_and_undo(source, admin_user):
    args = join_args(source)
    old = current_structure(source)
    body = old.nodes.get(pk=args["node_ids"][1])
    note = old.nodes.get(kind="paragraph", source__method="raw_blank_lines", segments__page__page_number=2, segments__start=16)
    m.DocumentNodeReference.objects.create(source=body,target=note,label="夹具注释",provenance={"test":True})
    anchor = create_anchor(source, [{"page_number":2,"start":0,"end":6,"node_id":str(body.pk)}])
    original = locator(anchor,admin_user,editorial=True)
    result = correct_paragraph(source,admin_user,**args)
    latest = current_structure(source)
    joined = latest.nodes.get(pk=result["correction"]["node_id"])
    assert node_text(joined) == "跨页引文前半\n跨页引文后半"
    assert joined.outgoing_references.get().label == "夹具注释"
    assert len(result["locator"]["segments"]) == 2
    assert latest.coverage["verified_cross_page_items"] == 1
    assert locator(anchor,admin_user,editorial=True) == original
    count = source.structures.count()
    assert correct_paragraph(source,admin_user,**args) == result
    assert source.structures.count() == count
    with pytest.raises(ValidationError, match="不同"):
        correct_paragraph(source,admin_user,**{**args,"reason":"different request"})
    with pytest.raises(ValidationError, match="新版本"):
        correct_paragraph(source,admin_user,**{**args,"request_id":uuid4()})
    undo = correct_paragraph(source,admin_user,node_ids=[],base_hash=latest.input_hash,reason="撤销夹具校正",request_id=uuid4(),operation="undo")
    assert undo["locator"] is None
    restored=current_structure(source)
    assert [node_text(n) for n in restored.nodes.all()] == [node_text(n) for n in old.nodes.all()]
    assert not restored.nodes.filter(source__human_corrected=True).exists()
    assert joined.segments.count() == 2 and locator(anchor,admin_user,editorial=True) == original


def test_manual_paragraph_survives_outline_and_blocks_overlapping_parser(source, admin_user):
    result=correct_paragraph(source,admin_user,**join_args(source))
    with pytest.raises(ValidationError,match="人工校正"):
        install_structure(source,parsed(source,[1,2],"跨页引文前半",1))
    outline=m.DocumentOutlineRevision.objects.get(document_revision=source,is_active=True)
    outline.is_active=False;outline.save()
    m.DocumentOutlineRevision.objects.create(asset=source.asset,document_revision=source,revision=2,
        source_checksum=source.source_checksum,is_active=True,nodes=deepcopy(outline.nodes))
    remapped=current_structure(source,prepare=True)
    assert remapped.parser == "human_outline_remap"
    node=remapped.nodes.get(source__human_corrected=True)
    assert node_text(node) == "跨页引文前半\n跨页引文后半"
    assert remapped.coverage.get("human_correction") is None  # Cannot undo across an outline edit.


def test_unrelated_parser_range_keeps_manual_paragraph(source,admin_user):
    # Add a third page before snapshots are frozen, then parse only that page.
    m.Page.objects.create(asset=source.asset,index=3,text="另一个真实范围的测试夹具",text_source="embedded")
    source.asset.page_count=3;source.asset.save()
    from catalog.services.document_intelligence import document_text_checksum
    source.text_checksum=document_text_checksum(source.asset);source.save()
    result=correct_paragraph(source,admin_user,**join_args(source))
    updated=install_structure(source,parsed(source,[3,3],"另一个真实范围的测试夹具",3))
    assert updated.nodes.get(source__human_corrected=True).segments.count() == 2
    assert updated.coverage["verified_cross_page_items"] == 1


def test_validation_and_editor_permissions(source,admin_user,django_user_model):
    args=join_args(source)
    reader=django_user_model.objects.create_user(username="paragraph-reader")
    with pytest.raises(PermissionDenied):
        correct_paragraph(source,reader,**args)
    with pytest.raises(ValidationError):
        correct_paragraph(source,admin_user,**{**args,"node_ids":args["node_ids"][:1]})
    with pytest.raises(ValidationError):
        paragraph_ranges(source,admin_user,[0,2])
    rows=paragraph_ranges(source,admin_user,[1,2])
    assert rows["base_hash"]==args["base_hash"] and rows["paragraphs"]
    source.is_active=False;source.save()
    with pytest.raises(ValidationError,match="历史正文"):
        correct_paragraph(source,admin_user,**args)


def test_restructuring_keeps_pinned_wiki_evidence_current(source,admin_user):
    from catalog.services.knowledge_workspace import source_hash, invalidate_source, page_workspace
    from catalog.services.knowledge_sources import digest
    args=join_args(source)
    page=m.KnowledgePage.objects.create(work=source.asset.edition.work,slug="pinned-evidence",title="固定原文")
    dependency=m.KnowledgeBlockDependency.objects.create(page=page,block_id=uuid4(),source_type="document_revision",source_id=source.pk,
        source_hash=digest({"text_checksum":source.text_checksum,"is_active":True,"structure_hash":args["base_hash"]}))
    before=source_hash("document_revision",source.pk)
    correct_paragraph(source,admin_user,**args)
    assert source_hash("document_revision",source.pk)==before
    invalidate_source("document_revision",source.pk)
    dependency.refresh_from_db()
    assert not dependency.stale and dependency.source_hash==before
    source.is_active=False;source.save()
    invalidate_source("document_revision",source.pk)
    dependency.refresh_from_db()
    assert dependency.stale
