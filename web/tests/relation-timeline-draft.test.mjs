import assert from "node:assert/strict";
import test from "node:test";
import {buildRelationPayload,buildTimelinePayload,timelineToDraft,emptyTimelineDraft} from "../lib/relation-timeline-draft.ts";

const subject={id:"subject-row",relation_type:"subject",node:"node",discipline:null,scholar:null,work:null,evidence:"proof",description:"人工主体说明",sort_order:17};
const context={id:"context-row",relation_type:"context",node:null,discipline:"discipline",scholar:null,work:null,evidence:null,description:"人工背景说明",sort_order:29};
const author={id:"author-row",relation_type:"context",node:null,discipline:null,scholar:"author",work:null,evidence:null,description:"人工人物说明",sort_order:31};
const work={id:"work-row",relation_type:"evidence",node:null,discipline:null,scholar:null,work:"related-work",evidence:null,description:"人工作品说明",sort_order:35};
const saved={id:"event",title:"原事件",description:"原说明",event_type:"theoretical_turn",start_year:1930,end_year:1931,date_label:"原时期",orientation:"left",source:"原出处",evidence_asset:"file",evidence_page:35,evidence_printed_label:"卷二35",evidence_text:"人工原文",confidence:.67,review_status:"approved",display_order:23,discipline:"legacy-discipline",theory_school:"legacy-school",subdiscipline:"legacy-sub",scholar:null,work:null,relations:[subject,context,author,work]};

test("editing reference event text omits hidden identity, evidence, review and relationship fields",()=>{
  assert.deepEqual(buildTimelinePayload({...timelineToDraft(saved),description:"新说明"},saved),{description:"新说明"});
  assert.deepEqual(buildTimelinePayload(timelineToDraft(saved),saved),{});
});
test("a new association retains original descriptions, evidence, ordering and all other entity kinds",()=>{
  const payload=buildTimelinePayload({...timelineToDraft(saved),nodes:["node","new-node"]},saved);
  assert.deepEqual(Object.keys(payload),["relations"]);
  for (const [index,row] of saved.relations.entries()) assert.deepEqual(payload.relations[index],Object.fromEntries(Object.entries(row).filter(([key])=>key!=="id")));
  assert.equal(payload.relations[4].sort_order,36);
  assert.equal(payload.relations[0].evidence,"proof");
});
test("only explicitly removed node associations disappear and selection order does not renumber existing rows",()=>{
  const payload=buildTimelinePayload({...timelineToDraft(saved),nodes:[]},saved);
  assert.deepEqual(payload.relations.map(row=>row.sort_order),[29,31,35]);
  const multiple={...saved,relations:[subject,{...subject,id:"second-kind",relation_type:"context"},context,author,work]};
  assert.deepEqual(timelineToDraft(multiple).nodes,["node"]);
  assert.deepEqual(buildTimelinePayload(timelineToDraft(multiple),multiple),{});
});
test("changing the actual source file submits its explicit work and edition context",()=>{
  const source={...saved,evidence_file:{id:"file",work_id:"source-work",edition_id:"edition",work_title:"出处",edition_label:"版本",filename:"source.pdf",version:2,page_count:80,reader_href:"/reader/file?page=35",detail:"有效出处"}};
  assert.deepEqual(buildTimelinePayload({...timelineToDraft(source),evidence_asset:"new-file",evidence_page:"7"},source),{evidence_page:7,evidence_asset:"new-file",evidence_work_id:"source-work",evidence_edition_id:"edition"});
});
test("normalized author and work labels are not promoted into legacy event foreign keys by text saving",()=>{
  const draft=timelineToDraft(saved);
  assert.equal(draft.scholar,"author");
  assert.equal(draft.work,"related-work");
  assert.deepEqual(buildTimelinePayload({...draft,title:"新标题"},saved),{title:"新标题"});
});
test("new events remain suggested and use unique normalized subjects",()=>{
  const payload=buildTimelinePayload({...emptyTimelineDraft,title:"隔离事件",nodes:["node","node"]},null);
  assert.equal(payload.review_status,"suggested");
  assert.equal(payload.relations.length,1);
  assert.equal("orientation" in payload,false);
});
test("relation explanation changes do not rewrite direction, confidence or publication status",()=>{
  const row={source_node:"source",target_node:"target",relation_type:"inherited_from",direction:"directed",description:"原说明",evidence_source:"原出处",confidence:.73,status:"published"};
  assert.deepEqual(buildRelationPayload({...row,description:"新说明"},row),{description:"新说明"});
  assert.deepEqual(buildRelationPayload(row,row),{});
});
