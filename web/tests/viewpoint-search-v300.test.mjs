import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

// The old stance groups were intentionally retired by 3.0.8. Keep the source,
// revision, reader and scope protections while checking the successor contract.
test("viewpoint discovery retains original text, revision identity and honest reader locators", async () => {
  const [types, client, page, view] = await Promise.all([
    read("../lib/api/discovery.types.ts"), read("../lib/api/discovery.client.ts"),
    read("../app/explore/opinions/page.tsx"), read("../components/discovery-search-workspace.tsx"),
  ]);
  assert.match(page, /DiscoverySearchWorkspace/);
  assert.match(types, /document_revision_id: string/);
  assert.match(types, /asset_id: string/);
  assert.match(types, /pdf_page: number/);
  assert.match(types, /locator_precision: string/);
  assert.match(client, /\/catalog\/discovery-search\//);
  assert.match(client, /X-Discovery-Token/);
  assert.match(client, /cache: "no-store"/);
  assert.doesNotMatch(client, /params\.set\([^\n]*[Tt]oken/);
  assert.match(view, /<blockquote>\{item\.excerpt\}<\/blockquote>/);
  assert.match(view, /internalHref\(item\.reader_url\)/);
  assert.match(view, /href=\{reader\}/);
  assert.match(view, /阅读原文/);
  assert.match(view, /readDiscoveryContext\(current\.id, tokenRef\.current, item\.id\)/);
  assert.match(view, /阅读原始 PDF/);
  assert.match(view, /按页定位/);
  assert.match(view, /OCR 识别/);
  assert.doesNotMatch(view, /Math\.round\(item\.(quality_score|score)|dangerouslySetInnerHTML/);
});

test("discovery separates its three channels, background expansion and stable more-results paging", async () => {
  const [view, client, styles] = await Promise.all([
    read("../components/discovery-search-workspace.tsx"), read("../lib/api/discovery.client.ts"),
    read("../app/explore/opinions/viewpoint-search.module.css"),
  ]);
  assert.match(view, /shownRef = useRef\(3\)/);
  assert.match(view, /result\?\.passages\.map/);
  assert.match(view, /result\?\.entities\.map/);
  assert.match(view, /result\?\.curation\.map/);
  assert.match(view, /cursor: current\.next_cursor/);
  assert.match(view, /limit: shownRef\.current/);
  assert.match(view, /readDiscoverySearch\(current\.id, tokenRef\.current, \{ limit \}\)/);
  assert.match(client, /action: "expand" \| "cancel"/);
  assert.match(view, /actOnDiscoverySearch\(current\.id, tokenRef\.current, action\)/);
  assert.match(view, /subscribeToSessionChanges/);
  assert.match(view, /invalidSession\(reason\)/);
  for (const state of ["queued", "running", "partial", "completed", "failed", "canceled"]) {
    assert.match(view, new RegExp(`${state}:`));
  }
  assert.match(view, /portrait_url && !portraitFailed/);
  assert.match(view, /来源：\{item\.source_title\}/);
  assert.doesNotMatch(view, /stanceSections|query_claim|Claim Engine|data-stance|assistant-message/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(styles, /@media \(max-width: 560px\)/);
});

test("discovery filters preserve existing source IDs, years and legacy route scope", async () => {
  const [page, view, client] = await Promise.all([
    read("../app/explore/opinions/page.tsx"), read("../components/discovery-search-workspace.tsx"),
    read("../lib/api/discovery.client.ts"),
  ]);
  for (const parameter of ["source_type", "scholar", "author", "theory", "topic", "concept", "language", "year_min", "year_max", "work_id"]) {
    assert.match(page, new RegExp(`"${parameter}"`));
  }
  assert.match(page, /if \(!filters\.work_id && params\.work\) filters\.work_id = params\.work/);
  assert.match(page, /legacyRelation=\{Boolean\(params\.relation\)\}/);
  assert.match(view, /name="year_min" min="1" max="3000"/);
  assert.match(view, /name="year_max" min="1" max="3000"/);
  assert.match(view, /value="journal_article"/);
  assert.match(view, /facets\?\.authors/);
  assert.match(view, /facets\?\.theories/);
  assert.match(view, /facets\?\.topics/);
  assert.match(view, /name=\{name\} value=\{entry\}/);
  assert.match(view, /retryParams\.append\(name, entry\)/);
  assert.match(client, /JSON\.stringify\(\{ q, filters \}\)/);
});
