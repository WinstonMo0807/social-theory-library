from uuid import uuid4
import pytest
from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services.knowledge_sources import build_structure, current_structure, node_text
from catalog.services.document_structure import install_structure, ADAPTER_VERSION, DOCLING_VERSION
from catalog.services.knowledge_source_updates import schedule_source_update, execute_source_update

pytestmark=pytest.mark.django_db


def test_outline_remap_retains_cross_page_and_footnote_sources(source):
    parsed={"schema":ADAPTER_VERSION,"parser_version":DOCLING_VERSION,"source_checksum":source.source_checksum,
        "heading_hierarchy_enabled":True,"ocr_performed":False,"status":"success","pages":[1,2],"items":[
        {"ref":"#/texts/0","label":"text","text":"跨页引文前半跨页引文后半",
         "prov":[{"page_no":1,"charspan":[0,6]},{"page_no":2,"charspan":[6,12]}]},
        {"ref":"#/texts/1","label":"footnote","text":"原始  文本","prov":[{"page_no":2,"charspan":[0,6]}]}]}
    old=install_structure(source,parsed)
    paragraph=old.nodes.get(source__docling_ref="#/texts/0")
    note=old.nodes.get(kind="footnote")
    m.DocumentNodeReference.objects.create(source=paragraph,target=note,label="经校核的注号",provenance={"manual":True})
    old_nodes=list(old.nodes.values_list("pk",flat=True))
    outline=m.DocumentOutlineRevision.objects.get(document_revision=source,is_active=True)
    outline.is_active=False;outline.save()
    new=m.DocumentOutlineRevision.objects.create(asset=source.asset,document_revision=source,revision=2,
        source_checksum=source.source_checksum,is_active=True,nodes=[{**n,"level":1} for n in outline.nodes])
    result=current_structure(source,prepare=True)
    assert result.outline_revision==new and result.parser=="docling_outline_remap"
    copy=result.nodes.get(source__retained_from_node=str(paragraph.pk))
    assert copy.segments.count()==2 and node_text(copy)==node_text(paragraph)
    assert copy.outgoing_references.get().target.kind=="footnote"
    assert copy.parent.title=="第一章 测试"
    assert list(old.nodes.values_list("pk",flat=True))==old_nodes
    assert current_structure(source,prepare=True).pk==result.pk


def test_source_update_is_idempotent_and_stops_superseded_outline(source):
    job=schedule_source_update(source)
    assert schedule_source_update(source).pk==job.pk
    m.DocumentOutlineRevision.objects.filter(document_revision=source).update(is_active=False)
    execute_source_update(job.pk,job.task_id)
    job.refresh_from_db()
    assert job.status=="canceled" and job.error_code=="source_superseded"
    current=schedule_source_update(source)
    execute_source_update(current.pk,current.task_id)
    current.refresh_from_db()
    assert current.status=="succeeded" and current.stats["model_calls"]==0
    assert current.stats["index_state"]=="unpublished_or_no_active_index"


def test_manual_assertion_enters_same_review_and_apply(source,admin_user):
    from catalog.services.knowledge_workspace import submit_assertion_draft
    from catalog.services.intelligence_changes import review,apply
    build_structure(source)
    key=uuid4()
    payload={"text":"人工解释须有固定原文","expression":"editorial_judgment","predicate":"qualifies",
        "conditions":{"population":"此处明确讨论的人群"},"evidence":[{"stance":"qualifies",
            "segments":[{"page_number":1,"start":0,"end":2,"exact":"前言"}]}]}
    draft=submit_assertion_draft(source,payload,admin_user,request_id=key)
    assert draft.origin=="human" and draft.items.count()==2
    assert not m.Assertion.objects.exists() and not m.KnowledgePage.objects.exists()
    assert submit_assertion_draft(source,payload,admin_user,request_id=key).pk==draft.pk
    ids=list(map(str,draft.items.values_list("pk",flat=True)))
    draft=review(draft.pk,[{"id":v,"decision":"accepted"} for v in ids],admin_user,expected_version=1)
    receipt=apply(draft.pk,ids,admin_user,request_id=uuid4(),expected_version=draft.version)
    assert not receipt["blocked"] and m.Assertion.objects.count()==1
    statement=m.Assertion.objects.get()
    assert statement.conditions==payload["conditions"] and statement.evidence.get().stance=="qualifies"
    assert statement.status==m.KnowledgePage.objects.get().status=="draft"


def test_corrected_outline_remaps_raw_spelling_without_losing_parser_sections(source):
    from catalog.services.knowledge_sources import _outline_heading
    observation={"source":"generated_heading","title":"第一章 测试","pdf_page":1,
        "source_locator":{"geometry_status":"validated","normalized_bbox":[.1,.2,.8,.25]}}
    corrected={"title":"第一章 测试与说明","source":"manual","calibration_status":"confirmed",
        "pdf_page":1,"candidate_sources":[observation]}
    assert _outline_heading("第一章 测试\n正文",corrected)==("第一章 测试与说明",0)
    assert _outline_heading("第一章 测试\n正文",{**corrected,"pdf_page":2})[1] is None
    assert _outline_heading("第一章 测试\n第一章 测试",corrected)[1] is None
    other={**observation,"title":"第二节 范围"}
    assert _outline_heading("第一章 测试\n第二节 范围",{**corrected,"candidate_sources":[observation,other]})[1] is None
    assert _outline_heading("第一章 测试",{**corrected,"normalized_position":[.7,.7]})[1] is None
    parsed={"schema":ADAPTER_VERSION,"parser_version":DOCLING_VERSION,"source_checksum":source.source_checksum,
        "heading_hierarchy_enabled":True,"ocr_performed":False,"status":"success","pages":[1,2],"items":[
        {"ref":"#/texts/section","label":"section_header","level":1,"text":"跨页引文前半",
         "prov":[{"page_no":1,"charspan":[0,6]}]},
        {"ref":"#/texts/body","label":"text","text":"原始  文本","prov":[{"page_no":2,"charspan":[0,6]}]}]}
    old=install_structure(source,parsed)
    child=old.nodes.get(source__docling_ref="#/texts/section")
    assert child.kind=="section" and child.parent.title=="第一章 测试"
    outline=old.outline_revision;outline.is_active=False;outline.save()
    nodes=[{**n,**corrected} if n["id"]=="b" else n for n in outline.nodes]
    m.DocumentOutlineRevision.objects.create(asset=source.asset,document_revision=source,revision=2,
        source_checksum=source.source_checksum,is_active=True,nodes=nodes)
    new=current_structure(source,prepare=True)
    assert new.nodes.get(source__outline_id="b").title==corrected["title"]
    retained=new.nodes.get(source__retained_from_node=str(child.pk))
    assert retained.parent.title==corrected["title"] and retained.kind=="section"
    assert node_text(retained)==node_text(child)
    assert old.nodes.get(pk=child.pk).parent.title=="第一章 测试"


def test_reparse_replaces_only_scoped_parser_headings_and_keeps_old_anchor(source):
    from catalog.services.knowledge_sources import create_anchor,locator_payload,digest
    from catalog.services.document_intelligence import document_text_checksum
    source.asset.page_count=3;source.asset.save()
    texts=["书名页眉的同一段落\n\n"+p.text for p in m.Page.objects.filter(asset=source.asset).order_by("index")]
    for p,text in zip(m.Page.objects.filter(asset=source.asset).order_by("index"),texts):p.text=text;p.save()
    m.Page.objects.create(asset=source.asset,index=3,text="书名页眉的同一段落\n\n第三页正文",text_source="embedded")
    source.text_checksum=document_text_checksum(source.asset);source.save()
    header="书名页眉的同一段落"
    parsed={"schema":ADAPTER_VERSION,"parser_version":DOCLING_VERSION,"source_checksum":source.source_checksum,
        "heading_hierarchy_enabled":True,"ocr_performed":False,"status":"success","pages":[1,2],"items":[
        {"ref":"header","label":"section_header","level":1,"text":header,
         "prov":[{"page_no":2,"charspan":[0,len(header)],"bbox":{"t":960,"b":930,"coord_origin":"BOTTOMLEFT"}}]},
        {"ref":"body","label":"text","text":"原始  文本","prov":[{"page_no":2,"charspan":[0,6]}]}]}
    old=install_structure(source,parsed)
    bad=old.nodes.get(source__docling_ref="header")
    assert bad.title==header  # Historical packet had no verified page dimensions.
    anchor=create_anchor(source,[{"page_number":2,"start":0,"end":len(header),"node_id":str(bad.pk)}])
    before=locator_payload(anchor)
    updated=install_structure(source,{**parsed,"pages":[2,2],"page_sizes":{"2":{"width":700,"height":1000}}})
    assert not updated.nodes.filter(title=header).exists()
    assert any(r['page']==2 and r['start']==0 and r['end']==len(header) for r in updated.coverage['ignored_ranges'])
    assert updated.nodes.filter(source__outline_id="b").exists()
    assert locator_payload(anchor)==before and old.nodes.filter(pk=bad.pk).exists()
    assert digest(source.page_snapshots.get(page_number=2).text)==source.page_snapshots.get(page_number=2).content_hash
