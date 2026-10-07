import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime.js";
import { PathnameContext, SearchParamsContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime.js";

registerHooks({load(url, context, nextLoad) {
  if (url.endsWith(".module.css")) return {format:"module",source:"export default {};",shortCircuit:true};
  return nextLoad(url,context);
}});
const { ScholarDirectoryTable, TopicDirectoryTable, ScholarsAdmin, TaxonomyAdmin } = await import("../components/admin-sections.tsx");

test("scholar table preserves identity and dates while public links require actual public eligibility", () => {
  const rows = [
    {id:"public",slug:"published-person",preferred_name:"已公开学者",original_name:"Published Person",birth_year:1864,death_year:1920,portrait:"",public_eligible:true,public_visibility_reason:"",editorial_status:"published"},
    {id:"unverified",slug:"unverified-person",preferred_name:"待确认学者",original_name:"",birth_year:1900,death_year:null,portrait:"",public_eligible:false,public_visibility_reason:"人物身份未确认",editorial_status:"published"},
    {id:"draft",slug:"draft-person",preferred_name:"草稿学者",original_name:"",birth_year:null,death_year:null,portrait:"",public_eligible:false,public_visibility_reason:"",editorial_status:"draft"},
  ];
  const html = renderToStaticMarkup(React.createElement(ScholarDirectoryTable,{scholars:rows,selectedId:"unverified",onSelect(){}}));
  assert.equal((html.match(/<th scope="col">/g)||[]).length,4);
  assert.equal((html.match(/data-selected="true"/g)||[]).length,1);
  assert.match(html,/Published Person/);
  assert.match(html,/1864 – 1920/);
  assert.match(html,/href="\/scholars\/published-person"/);
  assert.doesNotMatch(html,/href="\/scholars\/(unverified-person|draft-person)"/);
  for(const row of rows)assert.match(html,new RegExp(`href="/admin/scholars/${row.id}"`));
  assert.match(html,/人物身份未确认/);
  assert.equal((html.match(/data-empty="true"/g)||[]).length,3);
  assert.doesNotMatch(html,/tiny-portrait|theory-symbol|placeholder|<img |删除/);
});

test("topic table retains actual descriptions, editable rows and explicit unpublished state without invented images", () => {
  const rows = [
    {id:"one",slug:"one",name:"真实研究主题",description:"保存的主题介绍",hero_image:"",editorial_status:"published"},
    {id:"two",slug:"two",name:"尚未公开的主题",description:"",hero_image:"",editorial_status:"draft"},
  ];
  const html = renderToStaticMarkup(React.createElement(TopicDirectoryTable,{topics:rows,selectedId:"two",onSelect(){}}));
  assert.equal((html.match(/<th scope="col">/g)||[]).length,4);
  assert.match(html,/保存的主题介绍/);
  assert.match(html,/已公开/);
  assert.match(html,/未公开/);
  assert.equal((html.match(/>查看<\/button>/g)||[]).length,2);
  assert.match(html,/href="\/admin\/topics\/two"/);
  assert.doesNotMatch(html,/href="\/topics\//);
  assert.equal((html.match(/data-empty="true"/g)||[]).length,2);
  assert.doesNotMatch(html,/尚未填写说明|关联馆藏|theory-symbol|placeholder|<img /);
});

test("directory pages preserve URL search and pagination context with the reference search controls", () => {
  const render = (Component, path, params, props = {}) => renderToStaticMarkup(
    React.createElement(AppRouterContext.Provider,{value:{push(){},replace(){},prefetch(){}}},
      React.createElement(PathnameContext.Provider,{value:path},
        React.createElement(SearchParamsContext.Provider,{value:new URLSearchParams(params)},React.createElement(Component,props)))));
  const scholars = render(ScholarsAdmin,"/admin/scholars","q=Mead&page=2");
  assert.match(scholars,/>学者列表<\/h1>/);
  assert.match(scholars,/aria-label="搜索学者姓名、原名或关键词"[^>]*value="Mead"/);
  assert.match(scholars,/href="\/admin\/scholars\?q=Mead&amp;page=1"/);
  assert.doesNotMatch(scholars,/人物资料|tiny-portrait|删除/);
  const topics = render(TaxonomyAdmin,"/admin/topics","q=institutions&topics_page=2",{mode:"topic"});
  assert.match(topics,/>主题管理<\/h1>/);
  assert.match(topics,/href="\/admin\/topics\/new"/);
  assert.match(topics,/aria-label="搜索主题名称或关键词"[^>]*value="institutions"/);
  assert.match(topics,/href="\/admin\/topics\?q=institutions&amp;topics_page=1"/);
  assert.doesNotMatch(topics,/知识组织|theory-symbol/);
});
