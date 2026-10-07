import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

registerHooks({ load(url, context, nextLoad) {
  if (url.endsWith(".module.css")) return { format: "module", source: "export default {};", shortCircuit: true };
  return nextLoad(url, context);
} });
const { moveScholarWork, selectScholarWork, loadScholarWorkOptions, ScholarEssentialWorks, ScholarWorkPicker } = await import("../components/admin/knowledge/scholar-essential-works.tsx");

test("scholar book reordering preserves every existing choice and never mutates saved order", () => {
  const saved = Object.freeze(["a", "b", "c", "legacy-fourth"]);
  assert.deepEqual(moveScholarWork(saved, "c", 0), ["c", "a", "b", "legacy-fourth"]);
  assert.deepEqual(moveScholarWork(saved, "a", 2), ["b", "c", "a", "legacy-fourth"]);
  assert.equal(moveScholarWork(saved, "unknown", 1), saved);
  assert.equal(moveScholarWork(saved, "a", -1), saved);
  assert.equal(moveScholarWork(saved, "c", 4), saved);
});

test("scholar cards render saved order and real bibliographic fields, unsupported reasons stay empty", () => {
  const works = [
    { id: "a", title: "甲书", original_title: "Original A", cover: "/api/protected-cover/a", edition: { publisher: "甲出版社", publication_year: 2001, contributors: [{ role: "author", person: { preferred_name: "作者甲" } }] } },
    { id: "b", title: "乙书", original_title: "", cover: "", edition: null },
  ];
  const html = renderToStaticMarkup(React.createElement(ScholarEssentialWorks, { selected: ["b", "a"], options: works, works, onChange() {}, onResolve() {} }));
  assert.ok(html.indexOf('data-work-id="b"') < html.indexOf('data-work-id="a"'));
  assert.equal((html.match(/<img /g) || []).length, 1);
  assert.match(html, /Original A/);
  assert.match(html, /作者甲 著/);
  assert.match(html, /甲出版社 · 2001 年版/);
  assert.equal((html.match(/<textarea[^>]*disabled=""[^>]*><\/textarea>/g) || []).length, 3);
  assert.equal((html.match(/draggable="true"/g) || []).length, 2);
  assert.match(html, /当前位置 1/);
  assert.doesNotMatch(html, /经济与社会|新教伦理|mock|placeholder-cover/);
});

test("search choices replace only the chosen slot, reject duplicates and preserve historical extra works", () => {
  const saved = Object.freeze(["a", "b", "c", "legacy-fourth"]);
  assert.deepEqual(selectScholarWork(saved, 1, "searched-work"), ["a", "searched-work", "c", "legacy-fourth"]);
  assert.equal(selectScholarWork(saved, 1, "a"), saved);
  assert.deepEqual(selectScholarWork(saved, 1, ""), ["a", "c", "legacy-fourth"]);
  assert.deepEqual(selectScholarWork([], 2, "first-work"), ["first-work"]);
  assert.deepEqual(selectScholarWork(["a", "b"], 2, "c"), ["a", "b", "c"]);
  assert.equal(selectScholarWork(saved, 4, "extra"), saved);
});

test("empty scholar suggestions still expose real catalog search and pagination after opening a card", () => {
  const html = renderToStaticMarkup(React.createElement(ScholarWorkPicker, {
    index: 0, current: "", selected: [], suggestions: [], onSelect() {}, onClose() {},
  }));
  assert.match(html, /type="search"/);
  assert.match(html, /书名、作者或 ISBN/);
  assert.match(html, /第 1 本重要文献搜索结果/);
  assert.match(html, /上一页/);
  assert.match(html, /下一页/);
  assert.doesNotMatch(html, /AI|外部|生成/);
});

test("catalog lookup uses q and requested page with normal authentication, accepts works without editions and exposes failures", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  const payload = { count: 41, page: 2, page_size: 40, total_pages: 2, next: null, previous: "?page=1", results: [{ id: "work-41", title: "无版本的真实馆藏", primary_edition: null }] };
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return Response.json(payload);
  };
  try {
    const controller = new AbortController();
    const result = await loadScholarWorkOptions("  同名书 & 作者  ", 2, controller.signal);
    const url = new URL(calls[0].url, "http://localhost");
    assert.equal(url.pathname, "/api/catalog/admin/library/works/");
    assert.equal(url.searchParams.get("q"), "同名书 & 作者");
    assert.equal(url.searchParams.get("page"), "2");
    assert.equal(url.searchParams.has("view"), false);
    assert.equal(calls[0].options.credentials, "include");
    assert.equal(calls[0].options.signal, controller.signal);
    assert.deepEqual(result, payload);
    assert.equal(selectScholarWork([], 0, result.results[0].id)[0], "work-41");
    globalThis.fetch = async () => Response.json({ detail: "无馆藏权限" }, { status: 403 });
    await assert.rejects(loadScholarWorkOptions("", 1), reason => reason.status === 403);
  } finally { globalThis.fetch = originalFetch; }
});
