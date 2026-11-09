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
