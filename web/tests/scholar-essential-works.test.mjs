import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

registerHooks({ load(url, context, nextLoad) {
  if (url.endsWith(".module.css")) return { format: "module", source: "export default {};", shortCircuit: true };
  return nextLoad(url, context);
} });
const { moveScholarWork, ScholarEssentialWorks } = await import("../components/admin/knowledge/scholar-essential-works.tsx");

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
