import assert from "node:assert/strict";
import test from "node:test";
import {buildTheoryNodePayload,theoryNodeToDraft} from "../lib/theory-node-draft.ts";

const saved={node_type:"theory_tradition",canonical_name_zh:"原理论",canonical_name_en:"Original Theory",slug:"保留旧地址",aliases:[{alias:"原别名",language:"de",alias_type:"translation"}],summary:"原简介",definition:"原定义",core_questions:["原问题"],basic_propositions:["原命题"],theoretical_boundary:"原边界",start_year:1920,end_year:1980,period_label:"原时期",parent:"parent",primary_discipline:"primary",status:"published",sort_order:9,
  discipline_links:[{discipline:{id:"primary"},relation_type:"primary",discipline_specific_summary:"主要学科人工说明",sort_order:3,status:"published"},{discipline:{id:"related"},relation_type:"transferred",discipline_specific_summary:"跨学科人工说明",sort_order:7,status:"published"}],
  subdiscipline_links:[{subdiscipline:{id:"sub"},is_primary:true,relation_role:"home",source:"人工确认",confidence:.73,sort_order:8,status:"published"}],
  topic_links:[{topic:{id:"topic"},relation_label:"人工关系",source:"馆藏原文",confidence:.68,sort_order:6,status:"published"}]};

test("reference basic fields send only changed content and preserve hidden identity and relationships",()=>{
  const draft={...theoryNodeToDraft(saved),canonical_name_zh:"修改名称",summary:"修改简介"};
  assert.deepEqual(buildTheoryNodePayload(draft,saved),{canonical_name_zh:"修改名称",summary:"修改简介"});
  assert.deepEqual(buildTheoryNodePayload(theoryNodeToDraft(saved),saved),{});
});
test("adding a discipline retains primary and transferred relationships without rewriting metadata",()=>{
  const draft={...theoryNodeToDraft(saved),related_disciplines:["related","new"]};
  const payload=buildTheoryNodePayload(draft,saved);
  assert.deepEqual(Object.keys(payload),["discipline_links"]);
  assert.deepEqual(payload.discipline_links.slice(0,2),saved.discipline_links.map(row=>({discipline_id:row.discipline.id,relation_type:row.relation_type,discipline_specific_summary:row.discipline_specific_summary,sort_order:row.sort_order,status:row.status})));
  assert.equal(payload.discipline_links[2].status,"pending");
});
test("new subdiscipline and topic links preserve existing evidence, confidence, order and review state",()=>{
  const draft={...theoryNodeToDraft(saved),subdisciplines:["sub","new-sub"],topics:["topic","new-topic"]};
  const payload=buildTheoryNodePayload(draft,saved);
  assert.deepEqual(Object.keys(payload),["subdiscipline_links","topic_links"]);
  assert.deepEqual(payload.subdiscipline_links[0],{subdiscipline_id:"sub",is_primary:true,relation_role:"home",source:"人工确认",confidence:.73,sort_order:8,status:"published"});
  assert.deepEqual(payload.topic_links[0],{topic_id:"topic",relation_label:"人工关系",source:"馆藏原文",confidence:.68,sort_order:6,status:"published"});
  assert.equal(payload.subdiscipline_links[1].status,"pending");
  assert.equal(payload.topic_links[1].status,"pending");
});
test("changing aliases does not transmit unrelated classifications or publication status",()=>{
  const draft={...theoryNodeToDraft(saved),aliases:[...saved.aliases,{alias:" 新别名 ",language:"fr",alias_type:"alias"}]};
  assert.deepEqual(buildTheoryNodePayload(draft,saved),{aliases:[saved.aliases[0],{alias:"新别名",language:"fr",alias_type:"alias"}]});
});
test("only explicitly removed topic links are omitted while unchanged collections are preserved",()=>{
  const draft={...theoryNodeToDraft(saved),topics:[]};
  assert.deepEqual(buildTheoryNodePayload(draft,saved),{topic_links:[]});
});
test("a new reference draft can use server address generation and never publishes through saving",()=>{
  const draft={...theoryNodeToDraft(saved),slug:"",related_disciplines:[],subdisciplines:[],topics:[],aliases:[]};
  const payload=buildTheoryNodePayload(draft,null);
  assert.equal(payload.status,"draft");
  assert.equal("slug" in payload,false);
  assert.equal(payload.start_year,1920);
});
