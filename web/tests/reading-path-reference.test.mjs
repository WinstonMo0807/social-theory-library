import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

registerHooks({ load(url, context, nextLoad) {
  if (url.endsWith(".module.css")) return { format:"module", source:"export default {};", shortCircuit:true };
  return nextLoad(url, context);
} });
const { moveReadingPathEntry, readingPathStageGroups } = await import("../components/admin/curation/reading-path-workbench.tsx");
const { loadLibraryWorkPreview } = await import("../components/admin/knowledge/scholar-essential-works.tsx");
const { ReadingPathPublicView } = await import("../components/public/reading-path-public-view.tsx");
const item = (id, work, reason = "已确认的推荐理由") => Object.freeze({ key:id, id, work, work_name:work || "", node:null, node_name:"", recommendation_reason:reason, prerequisite:"已确认前置要求", editorial_note:"私人编辑备注", is_required:true });

test("reordering keeps all legacy items and their identity, evidence and private notes", () => {
  const saved = Object.freeze([item("a","work-a"),item("b","work-b"),item("legacy","work-c")]);
  const reordered = moveReadingPathEntry(saved,2,0);
  assert.deepEqual(reordered.map(row=>row.id),["legacy","a","b"]);
  assert.equal(reordered[0],saved[2]);
  assert.equal(moveReadingPathEntry(saved,-1,0),saved);
  assert.equal(moveReadingPathEntry(saved,3,0),saved);
  const payload = readingPathStageGroups([{key:"stage",id:"stage",name:"核心著作",description:"原阶段说明",items:reordered}]);
  assert.deepEqual(payload[0].items.map(row=>[row.id,row.position,row.recommendation_reason,row.prerequisite,row.editorial_note]),[
    ["legacy",0,"已确认的推荐理由","已确认前置要求","私人编辑备注"],
    ["a",1,"已确认的推荐理由","已确认前置要求","私人编辑备注"],
    ["b",2,"已确认的推荐理由","已确认前置要求","私人编辑备注"],
  ]);
  assert.deepEqual(saved.map(row=>row.id),["a","b","legacy"]);
});

test("a clean placeholder permits saving the introduction, entered text is never silently discarded", () => {
  const placeholder = Object.freeze({key:"blank",node:null,work:null,recommendation_reason:"",prerequisite:"",editorial_note:"",is_required:false});
  const stages = [{key:"stage",name:"第 1 阶段",description:"原说明",items:[placeholder]}];
  assert.deepEqual(readingPathStageGroups(stages)[0].items,[]);
  assert.equal(stages[0].items.length,1);
  assert.throws(()=>readingPathStageGroups([{...stages[0],items:[{...placeholder,recommendation_reason:"尚未选书的人工说明"}]}]),/填写的说明已保留/);
});

test("library preview resolves the exact work and normal authenticated edition, with cancellation", async () => {
  const originalFetch=globalThis.fetch,calls=[];
  globalThis.fetch=async (url,options)=>{calls.push({url,options});return Response.json(calls.length===1 ? {results:[{id:"other",primary_edition:{id:"wrong"}},{id:"selected",title:"实际书目",primary_edition:{id:"edition"}}]} : {work:{id:"selected",title:"实际书目"}});};
  try {
    const controller=new AbortController(),resolved=await loadLibraryWorkPreview("selected",controller.signal);
    assert.equal(resolved.work.id,"selected");
    assert.equal(new URL(calls[0].url,"http://localhost").searchParams.get("work_id"),"selected");
    assert.equal(new URL(calls[1].url,"http://localhost").pathname,"/api/catalog/admin/page-preview/editions/edition/");
    assert.ok(calls.every(call=>call.options.credentials==="include" && call.options.signal===controller.signal));
  } finally {globalThis.fetch=originalFetch;}
});

test("missing edition stays empty and unavailable or mismatched previews fail visibly", async () => {
  const originalFetch=globalThis.fetch;
  try {
    globalThis.fetch=async()=>Response.json({results:[{id:"selected",title:"无版本书目",primary_edition:null}]});
    assert.equal((await loadLibraryWorkPreview("selected")).work,null);
    globalThis.fetch=async()=>Response.json({detail:"无馆藏权限"},{status:403});
    await assert.rejects(loadLibraryWorkPreview("selected"),reason=>reason.status===403);
    let calls=0;
    globalThis.fetch=async()=>Response.json(++calls===1 ? {results:[{id:"selected",primary_edition:{id:"edition"}}]} : {work:{id:"other"}});
    await assert.rejects(loadLibraryWorkPreview("selected"),/读取结果不完整/);
  } finally {globalThis.fetch=originalFetch;}
});

test("same-named stages remain separate and only the chosen preview stage is highlighted", () => {
  const work={id:"work",title:"馆藏著作",author:"馆藏作者",publisher:"真实出版社",year:2006,cover_url:"",detail_href:"/works/real",reader_href:null};
  const path={title:"已保存阅读路径",slug:"path",introduction:"原路径说明",cover_url:"",audience:"后台保留的受众",estimated_reading:"后台保留的时长",items:[{id:"a",stage:"first",stage_name:"核心著作",stage_description:"阶段甲",work_data:work,recommendation_reason:"后台保留的理由",prerequisite:"后台保留的前置阅读",editorial_note:"禁止公开的备注"},{id:"b",stage:"second",stage_name:"核心著作",stage_description:"阶段乙",work_data:{...work,id:"work-b"}},{id:"c",stage:"second",stage_name:"核心著作",stage_description:"阶段乙",node_data:{canonical_name_zh:"已选理论",slug:""}}]};
  const render=previewStage=>renderToStaticMarkup(React.createElement(ReadingPathPublicView,{path,footer:null,previewStage}));
  assert.equal((render(1).match(/<h2>/g)||[]).length,2);
  assert.equal((render(1).match(/data-preview-selected="true"/g)||[]).length,1);
  assert.doesNotMatch(render(),/data-preview-selected="true"|禁止公开的备注|后台保留的|architectural-image|href="\/theories\/nodes\/"/);
  assert.match(render(1),/真实出版社 · 2006 年版/);
  assert.match(render(1),/馆藏作者 著/);
});
