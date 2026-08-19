import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("explore has a landing page, canonical SSR routes and legacy mode compatibility", async () => {
  const [page, landing] = await Promise.all([
    read("../app/explore/page.tsx"),
    read("../components/explore-landing.tsx"),
    access(new URL("../app/explore/original/page.tsx", import.meta.url)),
    access(new URL("../app/explore/opinions/page.tsx", import.meta.url)),
    access(new URL("../app/explore/ask/page.tsx", import.meta.url)),
  ]);

  assert.match(page, /if \(!Object\.keys\(params\)\.length\)/);
  assert.match(page, /requestedMode === "semantic" \|\| requestedMode === "ask"/);
  assert.match(landing, /href: "\/explore\/original"/);
  assert.match(landing, /href: "\/explore\/opinions"/);
  assert.match(landing, /href: "\/explore\/ask"/);
  assert.match(landing, /className=\{`explore-entry-card \$\{entry\.visualClass\}`\} href=\{entry\.href\}/);
  assert.match(landing, /explore-architecture-hero-v1\.webp/);
  assert.match(landing, /explore-magnifier-v1\.webp/);
  assert.match(landing, /explore-door-v1\.webp/);
  assert.match(landing, /explore-dialogue-v1\.webp/);
});

test("exact search uses real hot searches and preserves passage focus", async () => {
  const page = await read("../app/explore/page.tsx");

  assert.match(page, /loadHotSearches\(\)/);
  assert.match(page, /<h2>推荐搜索<\/h2>/);
  assert.doesNotMatch(page, /<h2>最近搜索<\/h2>/);
  assert.match(page, /passage=\$\{encodeURIComponent\(passage\.id\)\}/);
  assert.match(page, /className="passage-results-list passage-results-table" role="table"/);
  assert.match(page, /className="sort-form exact-aside-sort"/);
  assert.match(page, /<BookCard work=\{work\} exploreActions/);
  assert.match(page, /<ExactMobileFilters/);
  assert.match(page, /<SemanticMobileFilters/);
});

test("opinion search presents auditable candidates without calibrated relevance claims", async () => {
  const [page, css, serverApi, labels] = await Promise.all([
    read("../app/explore/page.tsx"),
    read("../app/globals.css"),
    read("../lib/server-api.ts"),
    read("../lib/semantic-search-ui.ts"),
  ]);

  assert.match(page, /优先核对的原文/);
  assert.match(page, /更多候选原文/);
  assert.match(page, /这里只并排呈现真实证据，不推断作者支持或反对某一立场/);
  assert.match(page, /服务端已确认本次查询使用关键词检索/);
  assert.match(page, /results\.service_unavailable \|\| results\.fallback_reason === "api_unavailable"/);
  assert.doesNotMatch(page, /结果已降级为关键词检索/);
  assert.match(serverApi, /engine: "unavailable"/);
  assert.match(serverApi, /fallback_used: false/);
  assert.match(serverApi, /无法验证关键词或语义检索是否已经执行/);
  assert.match(labels, /高度相关: "优先候选"/);
  assert.match(page, /semanticResponseLabel\(item\)/);
  assert.match(page, /className="semantic-snippet"/);
  assert.match(page, /className="semantic-comparison-excerpt"/);
  assert.match(page, /<summary>查看上下文<\/summary>/);
  assert.doesNotMatch(page, /回到原页/);
  assert.doesNotMatch(page, />核对原文 <ArrowRight/);
  assert.match(page, /回到原文/);
  assert.match(page, /aria-label=\{`打开《\$\{item\.title\}》PDF 第 \$\{item\.page_index\} 页核对原文`\}/);
  assert.match(page, /const preservedForFilters = entriesExcept/);
  assert.match(css, /\.semantic-top-evidence \.semantic-snippet[\s\S]*-webkit-line-clamp: 5/);
  assert.doesNotMatch(css, /\.semantic-result-card\.compact \.semantic-context[\s\S]*display: none/);
});

test("opinion search has a restrained two-stage accessible loading state", async () => {
  const [loading, css] = await Promise.all([
    read("../app/explore/opinions/loading.tsx"),
    read("../app/globals.css"),
  ]);

  assert.match(loading, /正在匹配馆藏原文/);
  assert.match(loading, /正在比较候选原文/);
  assert.match(loading, /role="status" aria-live="polite" aria-atomic="true"/);
  assert.match(css, /\.semantic-loading-indicator[\s\S]*animation: semantic-loading-pulse/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});

test("library assistant follows the authenticated status and SSE API contract", async () => {
  const client = await read("../components/explore-ask-client.tsx");

  assert.match(client, /\/reading\/library-assistant\/status\//);
  assert.match(client, /\/reading\/library-conversations\//);
  assert.match(client, /messages\/stream\//);
  assert.match(client, /\/reading\/library-messages\/\$\{messageId\}\/sources\//);
  assert.match(client, /event === "meta"|streamEvent === "meta"/);
  assert.match(client, /streamEvent === "delta"/);
  assert.match(client, /streamEvent === "sources"/);
  assert.match(client, /streamEvent === "done"/);
  assert.match(client, /streamEvent === "error"/);
  assert.match(client, /问答模型尚未配置/);
  assert.match(client, /已有会话与来源仍可查看/);
  assert.match(client, /apiStreamRequest/);
  assert.match(client, /disabled=\{!canGenerate\}/);
  assert.match(client, /\/login\?next=\/explore\/ask/);
  assert.match(client, /useSessionBootstrap/);
  assert.doesNotMatch(client, /apiRequest[^\n]*\/auth\/me\//);
  assert.match(client, /\/reading\/library-assistant\/connection\//);
  assert.match(client, /type="password"/);
  assert.match(client, /密钥只会在本次请求中提交给书库服务器/);
  assert.doesNotMatch(client, /localStorage/);
  assert.doesNotMatch(client, /experimental_v2/);
});

test("explore workspaces use the reference-aligned responsive three-column composition", async () => {
  const [page, css] = await Promise.all([
    read("../app/explore/page.tsx"),
    read("../app/globals.css"),
  ]);

  assert.match(page, /className="explore-workbench-head exact-workbench-head"/);
  assert.match(page, /className="explore-workbench-head semantic-workbench-head"/);
  assert.match(page, /className="semantic-source-mark"/);
  assert.match(page, /item\.cover_url/);
  assert.match(page, /<details className="semantic-more-evidence" open>/);
  assert.match(page, /className="semantic-aside-explainer"/);
  assert.match(css, /\.search-layout,[\s\S]*\.semantic-search-layout[\s\S]*grid-template-columns: minmax\(210px, 245px\) minmax\(0, 1fr\) minmax\(220px, 260px\)/);
  assert.match(css, /\.explore-entry-card\.magnifier \.explore-entry-visual/);
  assert.match(css, /\.explore-entry-card\.dialogue::before/);
  assert.match(css, /\.explore-entry-badge/);
  assert.match(css, /\.ask-configuration-workspace/);
});

test("explore motion and responsive filters remain accessible", async () => {
  const css = await read("../app/globals.css");

  assert.match(css, /\.explore-entry-card[\s\S]*transition: transform 190ms/);
  assert.match(css, /\.explore-entry-card:focus-visible/);
  assert.match(css, /\.mobile-filter-disclosure[\s\S]*display: none/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*\.mobile-filter-disclosure[\s\S]*display: block/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});
