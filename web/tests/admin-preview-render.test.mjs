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
