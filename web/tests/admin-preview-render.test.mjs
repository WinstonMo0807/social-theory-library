import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PathnameContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime.js";

// Node does not load stylesheet modules; the actual components still render.
registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith(".module.css")) return { format: "module", source: "export default {};", shortCircuit: true };
    return nextLoad(url, context);
  },
});
const { SiteHeader } = await import("../components/site-header.tsx");
const { PublicSessionProvider } = await import("../components/public-session-provider.tsx");
const { WorkDetailView } = await import("../components/work-detail-view.tsx");
const { SubdisciplinePublicView } = await import("../components/public/subdiscipline-public-view.tsx");
const { DisciplinePublicView } = await import("../components/public/discipline-public-view.tsx");
const { KnowledgeNodePublicView } = await import("../components/public/knowledge-node-public-view.tsx");

test("preview headers cannot navigate or expose session controls, public headers remain active", () => {
  const render = preview => renderToStaticMarkup(React.createElement(PathnameContext.Provider, { value: "/explore" },
    React.createElement(PublicSessionProvider, null, React.createElement(SiteHeader, { preview, previewPath: "/explore" }))));
  const preview = render(true);
  const published = render(false);
  assert.match(preview, /<header[^>]*inert=""/);
  assert.match(preview, /aria-expanded="false"/);
  assert.doesNotMatch(preview, /退出登录|site-menu-panel/);
  assert.doesNotMatch(published, /<header[^>]*inert/);
  assert.match(published, /href="\/explore"/);
});

test("work previews preserve tabs while protecting topic and footer navigation", () => {
  const work = { id: "asset", workId: "work", title: "馆藏样本", slug: "sample", author: "作者", year: "2026", kind: "图书", school: "社会理论", summary: "简介", cover: "paper", pages: 20, topics: [{ name: "主题", slug: "topic" }], authors: [{ name: "作者", slug: "author" }] };
  const footer = React.createElement("footer", null, React.createElement("a", { href: "/about" }, "关于"));
  const render = preview => renderToStaticMarkup(React.createElement(PathnameContext.Provider, { value: "/works/sample" }, React.createElement(PublicSessionProvider, null, React.createElement(WorkDetailView, { work, footer, preview: preview ? { publicationState: "draft", pdfPreviewUrl: "", returnHref: "/admin" } : undefined }))));
  const preview = render(true);
  const published = render(false);
  assert.match(preview, /<div inert=""><div class="tag-list">/);
  assert.match(preview, /<div inert=""><footer><a href="\/about">/);
  assert.match(preview, /<button[^>]*role="tab"/);
  assert.doesNotMatch(preview, /href="\/(reader|scholars)\//);
  assert.match(published, /href="\/reader\/asset"/);
  assert.match(published, /href="\/scholars\/author"/);
  assert.doesNotMatch(published, /inert=""/);
});

test("subdiscipline renders saved questions and real links while missing media stays empty", () => {
  const item = {id:"sub",name:"历史社会学",slug:"history",discipline:{id:"discipline",name:"社会学",slug:"sociology"},description:"实际保存的简介",hero_image:"",research_object:"",core_questions:["历史过程如何改变制度？"],theories:[{id:"theory",name:"制度理论",slug:"institutions"}],scholars:[{id:"scholar",name:"已关联学者",slug:"related-scholar"}],works:[]};
  const html=renderToStaticMarkup(React.createElement(SubdisciplinePublicView,{item,footer:null}));
  assert.match(html,/历史过程如何改变制度？/);
  assert.match(html,/href="\/theory-schools\/institutions"/);
  assert.match(html,/href="\/scholars\/related-scholar"/);
  assert.match(html,/background-image:none/);
  assert.doesNotMatch(html,/architectural-image|待考|待管理员补充/);
});

test("discipline scalar previews do not claim unloaded theory collections are empty", () => {
  const payload={discipline:{id:"sociology",name:"社会学",slug:"sociology",description:"已保存简介",hero_image:""},counts:{theory_traditions:1,subdisciplines:1,scholars:0,works:5},nodes:[],lineage:[],reading_paths:[]};
  const render=collectionsAvailable=>renderToStaticMarkup(React.createElement(DisciplinePublicView,{payload,activeType:"theory_tradition",slug:"sociology",footer:null,collectionsAvailable,subdisciplines:[{id:"history",name:"历史社会学",slug:"history"}]}));
  const preview=render(false);
  assert.match(preview,/已保存简介/);
  assert.match(preview,/href="\/subdisciplines\/history"/);
  assert.doesNotMatch(preview,/该分类尚无公开条目|theory-discipline-directory|理论系统快捷入口/);
  assert.match(render(true),/该分类尚无公开条目/);
});

test("theory overview uses the edited summary and actual relations while unsupported concepts stay empty",()=>{
  const node={id:"theory",node_type:"theory_tradition",canonical_name_zh:"保存的理论",canonical_name_en:"Saved Theory",slug:"saved-theory",summary:"当前编辑的简介",definition:"不应替代简介的完整定义",cover_url:"",cover_media:null,primary_discipline:{id:"discipline",name:"实际学科",slug:"actual-discipline"},related_disciplines:[],core_questions:["真实保存的问题"],representative_scholars:[{id:"person",name:"实际学者",original_name:"Actual Scholar",scholar_slug:"actual-scholar",portrait_url:""}],work_groups:{},subdiscipline_links:[],topic_links:[{topic:{id:"topic",name:"不能冒充核心概念的主题",slug:"topic"}}]};
  const html=renderToStaticMarkup(React.createElement(PathnameContext.Provider,{value:"/theories/nodes/saved-theory"},React.createElement(PublicSessionProvider,null,React.createElement(KnowledgeNodePublicView,{node,timeline:[],allPaths:[],slug:node.slug,footer:null}))));
  assert.match(html,/当前编辑的简介/);
  assert.match(html,/真实保存的问题/);
  assert.match(html,/href="\/theories\/disciplines\/actual-discipline"/);
  assert.match(html,/href="\/scholars\/actual-scholar"/);
  assert.match(html,/Actual Scholar/);
  assert.match(html,/核心概念/);
  assert.doesNotMatch(html,/不应替代简介的完整定义|不能冒充核心概念的主题|深入了解|architectural-image/);
});
