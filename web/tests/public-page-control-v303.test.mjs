import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("Scholar Theory and Topic public routes remain registered and previewable", async () => {
  const [registry, preview, pageTree] = await Promise.all([
    read("../../api/catalog/services/public_knowledge_control.py"),
    read("../components/admin/preview/knowledge-page-preview.tsx"),
    read("../components/admin/knowledge/public-page-tree.tsx"),
  ]);
  const routeFiles = [
    "../app/scholars/[slug]/page.tsx",
    "../app/scholars/[slug]/[section]/page.tsx",
    "../app/theories/nodes/[slug]/page.tsx",
    "../app/theories/graph/page.tsx",
    "../app/theories/timeline/page.tsx",
    "../app/theories/disciplines/[slug]/page.tsx",
    "../app/theories/reading-paths/[slug]/page.tsx",
    "../app/topics/[slug]/page.tsx",
    "../app/topics/[slug]/[section]/page.tsx",
  ];
  await Promise.all(routeFiles.map((path) => access(new URL(path, import.meta.url))));

  for (const route of [
    "/scholars/{slug}/frequently-read",
    "/theories/graph?center={slug}",
    "/theories/reading-paths/{path_slug}",
    "/topics/{slug}/reading-paths",
  ]) {
    assert.match(registry, new RegExp(route.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(registry, /ADMIN_FIELD_NO_PUBLIC_CONSUMER/);
  assert.match(registry, /PUBLIC_RELATION_SOURCE_UNCLEAR/);
  assert.match(registry, /LEGACY_PUBLIC_ROUTE_ACTIVE/);
  assert.match(preview, /ScholarSectionPublicView/);
  assert.match(preview, /TopicSectionPublicView/);
  assert.match(preview, /TheoryGraphExplorer/);
  assert.match(preview, /TheoryTimelinePublicList/);
  assert.match(preview, /secondary_preview/);
  assert.match(preview, /legacy_theory_schools/);
  assert.match(preview, /publicationStatusLabel/);
  assert.doesNotMatch(preview, /timeline=\{\[\]\} allPaths=\{\[\]\}/);
  assert.match(preview, /data-module-id/);
  assert.match(pageTree, /page\.preview\.supported/);
  assert.match(pageTree, /后台字段用于哪些公开位置/);
  assert.match(pageTree, /Legacy fallback 正在使用/);
});

test("public evidence entry points preserve a Reader highlight locator", async () => {
  const [topic, viewpoint, explore, ask, modeSwitch] = await Promise.all([
    read("../components/public/topic-public-view.tsx"),
    read("../app/explore/opinions/page.tsx"),
    read("../app/explore/page.tsx"),
    read("../components/explore-ask-client.tsx"),
    read("../components/search-mode-switch.tsx"),
  ]);
  assert.match(topic, /passage=\$\{encodeURIComponent\(excerpt\.id\)\}/);
  assert.match(viewpoint, /阅读原文/);
  assert.match(explore, /passage=\$\{encodeURIComponent\(passage\.id\)\}/);
  assert.match(ask, /source\.reader_url/);
  assert.match(ask, /SearchModeSwitch mode="ask"/);
  assert.match(modeSwitch, /原文检索/);
  assert.match(modeSwitch, /观点检索/);
  assert.match(modeSwitch, /向书库提问/);
});
