import assert from "node:assert/strict";
import test from "node:test";
import { evidenceCurationSavePayload, topicEvidenceAnnotationProblem, topicEvidenceRows } from "../lib/api/evidence-curation.types.ts";

test("curation saves preserve source references without sending original text or locators", () => {
  const draft = {
    edit_version: "revision-current", title: "Do not overwrite parent title",
    items: [{ id: "reference-1", source_type: "span", source_id: "span-1", group_title: "分组", reason: "关联说明", order: 99,
      text: "Injected editable source text", page_start: 123,
      source: { text: "Protected original", context_before: "Protected context", asset_id: "original-pdf", public_eligible: true } }],
  };
  assert.deepEqual(evidenceCurationSavePayload(draft), {
    edit_version: "revision-current", items: [{ id: "reference-1", source_type: "span", source_id: "span-1", group_title: "分组", reason: "关联说明", order: 0 }],
  });
  assert.equal(draft.items[0].source.text, "Protected original");
  assert.equal(draft.items[0].order, 99, "serialization must not mutate loaded drafts");
});

test("new sources keep exact identities and removing all references is an explicit empty draft", () => {
  assert.deepEqual(evidenceCurationSavePayload({ edit_version: "v2", items: [
    { source_type: "passage", source_id: "p-second", group_title: "", reason: "", order: 17 },
    { source_type: "span", source_id: "s-first", group_title: "", reason: "", order: 3 },
  ] }).items, [
    { source_type: "passage", source_id: "p-second", group_title: "", reason: "", order: 0 },
    { source_type: "span", source_id: "s-first", group_title: "", reason: "", order: 1 },
  ]);
  assert.deepEqual(evidenceCurationSavePayload({ edit_version: "v3", items: [] }), { edit_version: "v3", items: [] });
});

test("topic annotations require content while existing long text remains unchanged", () => {
  const item = {source_type:"passage",source_id:"p-1",group_title:"分组".repeat(30),reason:"保留原有说明".repeat(100),order:0,source:{text:"只读来源"}};
  assert.equal(topicEvidenceAnnotationProblem([item]), "");
  assert.equal(topicEvidenceAnnotationProblem([{...item,group_title:"  "}]), "请为每段原文填写分组名称。");
  assert.equal(topicEvidenceAnnotationProblem([{...item,reason:"\n "}]), "请为每段原文填写阅读说明。");
  assert.equal(topicEvidenceAnnotationProblem([]), "", "an explicitly empty draft can still be saved");
  assert.equal(evidenceCurationSavePayload({edit_version:"v1",items:[item]}).items[0].reason,item.reason);
});

test("book display sorting preserves editorial indices, source references and input order", () => {
  const sources = [{id:"p-1",work_id:"work-z",work_title:"Z"},{id:"s-2",work_id:"work-a",work_title:"A"},{id:"p-3",work_id:"work-a",work_title:"A"}];
  const items = sources.map((source,index)=>({id:`ref-${index}`,source_type:index===1?"span":"passage",source_id:source.id,group_title:`group-${index}`,reason:"说明",order:index,source}));
  const sorted=topicEvidenceRows(items,"book");
  assert.deepEqual(sorted.map(row=>row.index),[1,2,0]);
  assert.strictEqual(sorted[0].item,items[1]);
  assert.strictEqual(sorted[2].item.source,items[0].source);
  assert.deepEqual(items.map(row=>row.id),["ref-0","ref-1","ref-2"]);
  assert.deepEqual(topicEvidenceRows(items,"editorial").map(row=>row.index),[0,1,2]);
  assert.deepEqual(evidenceCurationSavePayload({edit_version:"v1",items}).items.map(row=>row.source_id),["p-1","s-2","p-3"]);
});
