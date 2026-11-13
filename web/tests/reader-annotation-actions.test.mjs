import assert from "node:assert/strict";
import test from "node:test";
import { readerAnnotationTargets } from "../lib/reader-annotation-targets.ts";
import { bookResearchSelections } from "../components/reader/use-reader-materials.ts";
import { buildReaderPageOverlays } from "../components/reader/use-reader-page-overlays.ts";

test("displayed hit targets preserve overlapping annotations and deduplicate multiline boxes", () => {
  const element = (id, left, top, width, height) => ({ dataset:{readerAnnotationId:id}, getBoundingClientRect:()=>({left,top,width,height,right:left+width,bottom:top+height}) });
  const root={querySelectorAll:()=>[element("highlight",100,120,150,18),element("highlight",100,140,200,18),element("note",120,125,80,15),element(undefined,90,100,400,100),element("hidden",140,130,0,0)]};
  assert.deepEqual(readerAnnotationTargets(root,150,132),["highlight","note"]);
  assert.deepEqual(readerAnnotationTargets(root,110,150),["highlight"]);
  assert.deepEqual(readerAnnotationTargets(root,500,500),[]);
});

test("private annotation ids do not attach to search or research evidence", () => {
  const annotation={id:"own",kind:"highlight",page:"page",selector:{page_index:2,bboxes:[[10,20,30,40],[10,50,30,60]]},quote:"原文",body_text:""};
  const overlays=buildReaderPageOverlays({annotations:[annotation],focusedAnnotationId:"",pagePayloads:{2:{width:600,height:800,blocks:[]}},passageFocus:null,query:"",searchMatches:[]});
  assert.deepEqual(overlays[2].highlights.map(row=>row.annotationId),["own","own"]);
  const cleared=buildReaderPageOverlays({annotations:[],focusedAnnotationId:"",pagePayloads:{2:{width:600,height:800,blocks:[]}},passageFocus:null,query:"",searchMatches:[]});
  assert.equal(cleared[2].highlights.length,0);
});

test("in-book research selections retain project identity and match every anchor without including other books", () => {
  const ref=(id,asset)=>({reference_id:id,asset_id:asset,source_status:"available"});
  const composite={reference_id:"mixed",source_status:"available",anchors:[ref("other","other"),ref("book","book")]};
  const projects=[{id:"project1",data:{selections:[ref("one","book"),ref("two","other"),composite]}},{id:"project2",data:{selections:[ref("one","book")]}}];
  const result=bookResearchSelections(projects,"book");
  assert.deepEqual(result.map(row=>[row.project.id,row.reference.reference_id]),[["project1","one"],["project1","mixed"],["project2","one"]]);
  assert.equal(bookResearchSelections(projects,"absent").length,0);
  assert.equal(projects[0].data.selections.length,3);
});
