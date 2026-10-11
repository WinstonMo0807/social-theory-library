import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PathnameContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime.js";

registerHooks({ load(url, context, nextLoad) {
  if (url.endsWith(".module.css")) return { format: "module", source: "export default new Proxy({}, { get: (_, key) => key });", shortCircuit: true };
  return nextLoad(url, context);
} });
const { WorkDetailView } = await import("../components/work-detail-view.tsx");
const { PublicSessionProvider } = await import("../components/public-session-provider.tsx");
const { adaptApiWork } = await import("../lib/public-data-adapters.ts");
const { adaptPreviewWork, previewChangeSections } = await import("../components/admin/preview/work-page-preview.tsx");
const work = {
  id: "reading-asset", workId: "work", editionId: "edition", downloadAssetId: "download-asset", readerHref: "/reader/default-reader",
  title: "测试题名", originalTitle: "Original title", slug: "sample", author: "已确认作者", year: "2026", publisher: "已确认出版社",
  kind: "图书", school: "社会理论", summary: "已保存简介", cover: "dark", coverImage: "/api/cover/test", pages: 20,
  authors: [{ name: "已确认作者", slug: "author", originalName: "Original author", biography: "已保存作者介绍" }],
  topics: [{ name: "已确认主题", slug: "topic" }], outline: [{ index: 3, printed_label: "1", chapter_title: "真实目录项" }],
};
const render = (presentation, preview = true, value = work) => renderToStaticMarkup(React.createElement(PathnameContext.Provider, { value: "/works/sample" },
  React.createElement(PublicSessionProvider, null, React.createElement(WorkDetailView, { presentation, work: value, footer: null,
    preview: preview ? { publicationState: "draft", pdfPreviewUrl: "/private.pdf", returnHref: "/admin" } : undefined }))));

test("01/08/10/55 share data with their reference-specific content navigation", () => {
  const expectations = {
    contents: ["内容简介", "作者介绍", "目录", "版本信息", "相关图书"],
    bibliography: ["目录", "版本信息", "相关推荐"],
    reading: ["目录", "作者简介", "版本信息", "相关图书"],
    publication: ["内容简介", "目录", "版本信息", "相关书目", "相关主题"],
  };
  for (const [presentation, labels] of Object.entries(expectations)) {
    const html = render(presentation);
    const tabs = [...html.matchAll(/<button[^>]*role="tab"[^>]*>([\s\S]*?)<\/button>/g)];
    assert.deepEqual(tabs.map(match => match[1].replace(/<svg[\s\S]*<\/svg>/g, "")), labels);
    assert.equal((html.match(/role="tabpanel"/g) || []).length, labels.length);
    assert.equal(tabs.filter(match => match[0].includes('aria-selected="true"')).length, 1);
    for (const tab of tabs) {
      const panelId = tab[0].match(/aria-controls="([^"]+)"/)[1];
      assert.ok(html.includes(`id="${panelId}"`));
    }
    assert.match(html, /已保存简介/);
    assert.match(html, /真实目录项/);
    assert.doesNotMatch(html, /href="\/(reader|scholars)\//);
    assert.doesNotMatch(html, /id="citation"/);
    assert.match(html, /class="cover"><div class="book-cover/);
  }
  assert.match(render("contents"), /在本书中/);
  assert.match(render("contents"), /aria-orientation="vertical"/);
  assert.match(render("reading"), /<aside[^>]*><h2>在本馆阅读/);
  assert.match(render("publication"), /<aside[^>]*><h2>关于本书/);
  assert.match(render("bibliography"), /Original author/);
});

test("public reading, download, saved-work and citation remain available; no fabricated author biography", () => {
  const html = render("publication", false);
  assert.match(html, /href="\/reader\/default-reader"/);
  assert.match(html, /href="\/reader\/default-reader\?page=3"/);
  assert.match(html, /<button[^>]*>.*?下载 PDF/s);
  assert.match(html, /aria-label="收藏"/);
  assert.match(html, /id="citation"/);
  assert.match(render("contents"), /已保存作者介绍/);
  const missing = render("contents", true, { ...work, coverImage: undefined, authors: [{ name: "已确认作者" }] });
  assert.doesNotMatch(missing, /已保存作者介绍|book-cover-image/);
  assert.match(missing, /aria-label="封面待补"/);
});

test("public API author biography mapping preserves missing values without new requests", () => {
  const value = { id: "work", title: "题名", document_type: "book", abstract: "简介", theories: [], topics: [], disciplines: [{ name: "社会学" }], subdisciplines: [{ name: "社会理论" }], edition: {
    id: "edition", contributors: [{ role: "author", person: { preferred_name: "作者", original_name: "Author", biography: "真实作者介绍" } }],
  } };
  const mapped = adaptApiWork(value);
  assert.equal(mapped.authors[0].biography, "真实作者介绍");
  assert.equal(mapped.authors[0].originalName, "Author");
  assert.deepEqual(mapped.categories, ["社会学", "社会理论"]);
  delete value.edition.contributors[0].person.biography;
  assert.equal(adaptApiWork(value).authors[0].biography, undefined);
});

test("nonbook public and saved preview show the corresponding bibliographic fields without borrowing another edition", () => {
  for (const [document_type, kind, expected] of [
    ["journal_article", "期刊论文", ["已确认期刊", "原卷", "原期", "10–20", "10.0000/saved"]],
    ["journal_issue", "整期期刊", ["已确认期刊", "原卷", "原期", "10–20"]],
    ["thesis", "学位论文", ["已确认大学", "博士"]],
    ["report", "研究报告", ["已确认责任机构"]],
  ]) {
    const value = {id:"work",title:"已保存非图书",document_type,theories:[],topics:[],edition:{
      id:"selected-edition", contributors:[], journal_title:"已确认期刊",volume:"原卷",issue:"原期",page_range:"10–20",doi:"10.0000/saved",
      degree_institution:"已确认大学",degree_type:"博士",report_institution:"已确认责任机构",
    }, reader_edition:{id:"different-reader",readable_asset:{id:"other-file",page_count:99}}};
    const preview = adaptPreviewWork(value);
    assert.equal(preview.editionId,"selected-edition");
    assert.equal(preview.pages,0);
    for (const adapted of [preview,adaptApiWork(value)]) {
      assert.equal(adapted.kind,kind);
      const html = render("publication",true,adapted);
      for (const field of expected) assert.ok(html.includes(field),`${document_type}: ${field}`);
      assert.doesNotMatch(html,/<dt>ISBN<\/dt>|关于本书/);
    }
    if (document_type === "journal_issue") assert.equal(preview.author,"期刊编辑部");
  }
});

test("preview changes link each saved section back to its corresponding workbench step",()=>{
  const fields=["title","bibliography","recommendation_image","abstract","contributors","classification","knowledge","reader"];
  const changes=previewChangeSections(fields,"研究报告");
  const located=Object.fromEntries(changes.flatMap(section=>section.fields.map(field=>[field,section.step])));
  assert.deepEqual(located,{title:"work",bibliography:"bibliography",recommendation_image:"work",abstract:"work",contributors:"contributors",classification:"classification",knowledge:"curation",reader:"reader"});
  assert.equal(changes.flatMap(section=>section.fields).length,fields.length);
  assert.ok(changes.some(section=>section.title === "文献封面"));
});
