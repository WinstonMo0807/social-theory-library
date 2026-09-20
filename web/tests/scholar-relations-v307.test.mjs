import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ScholarRelationNetwork } from "../components/scholar-relation-network.tsx";

globalThis.React = React;
const relation = {id:"shared-relation",source_scholar:"scholar-a",target_scholar:"scholar-b",source_name:"学者甲",target_name:"学者乙",source_slug:"scholar-a",target_slug:"scholar-b",relation_type:"influence",direction:"directed",summary:"可核对的关系说明",source:"合成测试文献第 12 页",status:"published",edit_version:"fixture"};
const render = (centerScholarId, row=relation) => renderToStaticMarkup(React.createElement(ScholarRelationNetwork,{relations:[row],centerScholarId,initialSelectedId:row.id}));

test("both scholar pages keep the same relation identity, direction and source",()=>{
  for(const scholar of ["scholar-a","scholar-b"]) {
    const html=render(scholar);
    assert.match(html,/data-relation-id="shared-relation"/);
    assert.match(html,/aria-label="学者甲 → 学者乙：影响"/);
    assert.match(html,/合成测试文献第 12 页/);
    assert.match(html,/可核对的关系说明/);
    assert.match(html,/href="\/scholars\/scholar-a"/);
    assert.match(html,/href="\/scholars\/scholar-b"/);
    assert.match(html,/marker-end="url\(#/);
    assert.doesNotMatch(html,/marker-start=/);
  }
});

test("bidirectional and undirected relations render distinct arrow semantics",()=>{
  const bidirectional=render("scholar-a",{...relation,direction:"bidirectional"});
  assert.match(bidirectional,/学者甲 ↔ 学者乙/);
  assert.match(bidirectional,/marker-start="url\(#/);
  assert.match(bidirectional,/marker-end="url\(#/);
  const undirected=render("scholar-b",{...relation,direction:"undirected"});
  assert.match(undirected,/学者甲 — 学者乙/);
  assert.doesNotMatch(undirected,/marker-start=|marker-end=/);
});

test("an incomplete private relation preview remains visibly a draft",()=>{
  const html=render("scholar-a",{...relation,status:"draft",summary:"",source:"",has_unpublished_changes:true});
  assert.match(html,/草稿/);
  assert.match(html,/尚未补充依据，保持草稿/);
  assert.doesNotMatch(html,/已发布/);
});

test("a withdrawn relationship preview retains its source with an explicit archived status",()=>{
  const html=render("scholar-a",{...relation,status:"archived",has_unpublished_changes:true});
  assert.match(html,/已撤下/);
  assert.match(html,/可核对的关系说明/);
  assert.match(html,/合成测试文献第 12 页/);
  assert.doesNotMatch(html,/已发布/);
});
