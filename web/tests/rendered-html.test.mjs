import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import test, { after } from "node:test";

import { defaultSiteConfig } from "../lib/site-config.ts";

const sampleWork = {
  id: "work-fixture",
  document_type: "book",
  title: "社会理论测试馆藏",
  subtitle: "",
  abstract: "由测试 API 明确提供的馆藏记录。",
  language: "zh-CN",
  cover: "",
  recommendation_image: "",
  edition: {
    id: "edition-fixture",
    public_slug: "fixture-work",
    publication_year: 2026,
    publisher: "测试出版社",
    journal_title: "",
    contributors: [{
      role: "author",
      person: {
        preferred_name: "皮埃尔·布迪厄",
        original_name: "Pierre Bourdieu",
        aliases: [],
        scholar_slug: "pierre-bourdieu",
      },
    }],
    readable_asset: { id: "asset-discipline", page_count: 436 },
  },
  theories: [{ name: "实践理论", slug: "practice-theory" }],
  topics: [{ name: "监控与社会", slug: "surveillance-and-society" }],
  disciplines: [{ name: "社会学", slug: "sociology", is_primary: true }],
  subdisciplines: [],
};

const sampleScholar = {
  slug: "pierre-bourdieu",
  person: {
    id: "scholar-fixture",
    preferred_name: "皮埃尔·布迪厄",
    original_name: "Pierre Bourdieu",
    aliases: [],
    birth_year: 1930,
    death_year: 2002,
    biography: "法国社会学家。",
  },
  short_description: "实践理论研究者",
  affiliations: [],
  key_concerns: ["实践", "场域"],
  timeline: [],
  featured_quote: "",
  quote_source: "",
  works: [sampleWork],
  curated: {
    essential_works: [],
    key_concepts: [],
    concept_map: [],
    network: [],
    frequently_read_scholars: [],
    related_theories: [],
  },
};

const recommendedScholar = {
  ...sampleScholar,
  slug: "recommended-outside-first-page",
  person: {
    ...sampleScholar.person,
    id: "recommended-scholar-fixture",
    preferred_name: "推荐页外学者",
    original_name: "Recommended Scholar",
    birth_year: 1912,
    death_year: 1999,
    biography: "这位学者不在学者列表第一页，但由当前推荐快照指定。",
  },
  short_description: "用于验证推荐详情按 slug 精确加载。",
  key_concerns: ["社会理论"],
};

const sampleTheory = {
  id: "theory-fixture",
  slug: "practice-theory",
  name: "实践理论",
  description: "测试 API 提供的理论条目。",
  symbol: "实",
  foreign_name: "Theory of Practice",
  entity_level: "tradition",
  formation_period: "20 世纪",
  core_questions: [],
  key_themes: [],
  hero_image: "",
  disciplines: [],
  subdisciplines: [],
  hierarchy: { parents: [], branches: [] },
  relations: [],
  timeline: [],
  work_count: 1,
  scholar_count: 1,
  works: [sampleWork],
  scholars: [sampleScholar],
};

const sampleTopic = {
  id: "topic-fixture",
  slug: "surveillance-and-society",
  name: "监控与社会",
  description: "测试 API 提供的问题主题。",
  problem_statement: "监控技术如何改变社会关系？",
  core_questions: [],
  research_dimensions: [],
  methods: [],
  formation_context: "数字社会",
  hero_image: "",
  disciplines: [],
  subdisciplines: [],
  linked_theories: [],
  key_concepts: ["监控"],
  timeline: [],
  work_count: 1,
  works: [sampleWork],
  scholars: [sampleScholar],
  theories: [sampleTheory],
  passages: [],
  curated: {
    hero_caption: "",
    foundational_works: [],
    recent_works: [],
    related_scholars: [],
    linked_theories: [],
    reading_paths: [],
    featured_passage_id: "",
    featured_passage_reason: "",
    featured_passage_evidence: {},
  },
};

const emptyFacets = {
  document_types: [], authors: [], years: [], languages: [], access: [],
  theories: [], topics: [], concepts: [],
};

function paginated(results) {
  return { count: results.length, next: null, previous: null, results };
}

function fixturePayload(pathname) {
  if (pathname === "/api/catalog/site-config/") return defaultSiteConfig;
  if (pathname === "/api/catalog/site-stats/") return { documents: 1, scholars: 1, knowledge_objects: 2, last_updated: null, last_updated_label: "测试", version: "2.7" };
  if (pathname === "/api/catalog/hot-searches/") return { period_days: 30, results: [] };
  if (pathname === "/api/catalog/works/") return paginated([sampleWork]);
  if (pathname === "/api/catalog/scholars/") return paginated([sampleScholar]);
  if (pathname === "/api/catalog/scholars/pierre-bourdieu/") return sampleScholar;
  if (pathname === "/api/catalog/scholars/recommended-outside-first-page/") return recommendedScholar;
  if (pathname === "/api/catalog/theory-schools/") return paginated([sampleTheory]);
  if (pathname === "/api/catalog/theory-schools/practice-theory/") return sampleTheory;
  if (pathname === "/api/catalog/topics/") return paginated([sampleTopic]);
  if (pathname === "/api/catalog/topics/surveillance-and-society/") return sampleTopic;
  if (pathname === "/api/catalog/recommendations/") return {
    shared_for_all_readers: true,
    rotation_days: 3,
    placements: {
      home_scholars: {
        id: "home-scholars-policy",
        placement: "home_scholars",
        title: "首页学者",
        item_count: 4,
        rotation_days: 3,
        enabled: true,
        last_generated_at: "2026-08-15T00:00:00Z",
        next_refresh_at: "2026-08-18T00:00:00Z",
        current: {
          id: "home-scholars-snapshot",
          starts_at: "2026-08-15T00:00:00Z",
          expires_at: "2026-08-18T00:00:00Z",
          source: "automatic",
          items: [{
            id: "home-scholars-item",
            position: 0,
            reason: "三天自动轮换",
            image_override: "",
            target_type: "scholar",
            target: {
              id: "recommended-scholar-fixture",
              name: "推荐页外学者",
              slug: "recommended-outside-first-page",
              description: "用于验证推荐详情按 slug 精确加载。",
            },
          }],
        },
      },
    },
  };
  if (pathname === "/api/catalog/about-blocks/") return { ...paginated([]), configured: false };
  if (pathname === "/api/catalog/search/") return {
    implementation_version: "scoped-search-fixture",
    context: "global",
    visibility: "public",
    query: "",
    total: 1,
    latency_ms: 1,
    groups: [{
      context: "theories",
      label: "理论",
      backend: "database",
      count: 1,
      results: [{
        context: "theories",
        entity_type: "knowledge_node",
        id: "theory-node-fixture",
        title: "实践理论",
        subtitle: "Theory of Practice",
        description: "测试理论节点",
        url: "/theories/nodes/practice-theory",
        match: { type: "exact", query: "实践理论", highlights: ["实践理论"] },
        metadata: { slug: "practice-theory", node_type: "theory_tradition" },
      }],
      pagination: { page: 1, limit: 24, total: 1, total_pages: 1 },
    }],
    counts: { works: 1, books: 1, articles: 0, theses: 0, reports: 0, scholars: 1, topics: 1, theories: 1, passages: 0 },
    works: [sampleWork], scholars: [sampleScholar],
    topics: [{ id: sampleTopic.id, name: sampleTopic.name, slug: sampleTopic.slug, description: sampleTopic.description, work_count: 1 }],
    theories: [{ id: sampleTheory.id, name: sampleTheory.name, slug: sampleTheory.slug, description: sampleTheory.description, work_count: 1 }],
    passages: [], facets: emptyFacets,
    pagination: { page: 1, page_size: 24, limit: 24, total: 1, total_pages: 1 },
  };
  if (pathname === "/api/catalog/semantic-search/") return {
    query: "农业现代化与组织依赖", engine: "keyword_fallback", fallback_used: true,
    fallback_reason: "fixture_keyword_mode", notice: "测试 API 使用关键词降级。",
    count: 0, work_count: 0,
    understanding: { type: "研究问题", terms: ["农业现代化", "组织依赖"], related_concepts: [], rewrites: [], rewrite_source: "" },
    query_rewrite_enabled: false, facets: emptyFacets, results: [],
  };
  if (pathname === "/api/catalog/assets/asset-discipline/manifest/") return {
    asset_id: "asset-discipline", edition_id: "edition-fixture", page_count: 436,
    publication_status: "published", ocr_status: "not_required", semantic_index_status: "ready",
    page_label_status: "ready", reader_rendition_policy: "auto", work: sampleWork,
    outline: [], related_scholars: [], related_theories: [], related_topics: [],
  };
  if (pathname === "/api/catalog/theory-system/overview/") return {
    disciplines: [], browse: {}, reading_paths: [],
    recent: { nodes: [], timeline_events: [], work_relations: [] },
  };
  if (pathname === "/api/catalog/theory-system/disciplines/sociology/") return {
    discipline: { id: "discipline-fixture", code: "SOC", name: "社会学", foreign_name: "Sociology", slug: "sociology", description: "社会关系研究", hero_image: "" },
    counts: {}, active_type: "theory_tradition", nodes: [], lineage: [], reading_paths: [],
  };
  if (pathname === "/api/catalog/theory-system/graph/") return { center: null, nodes: [], edges: [], depth: 1, limit: 20, truncated: false };
  if (pathname === "/api/catalog/theory-graph/") return { nodes: [], edges: [] };
  if (pathname === "/api/catalog/knowledge-matrix/") return { disciplines: [], entry_modes: [], counts: { disciplines: 0, theories: 0, subdisciplines: 0, topics: 0 } };
  if (pathname === "/api/catalog/disciplines/" || pathname === "/api/catalog/subdisciplines/" || pathname === "/api/catalog/theory-system/nodes/" || pathname === "/api/catalog/theory-system/timeline/" || pathname === "/api/catalog/theory-system/reading-paths/" || pathname === "/api/catalog/theory-timeline/") return paginated([]);
  return null;
}

const fixtureServer = createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  const payload = fixturePayload(url.pathname);
  response.statusCode = payload === null ? 404 : 200;
  response.setHeader("content-type", "application/json; charset=utf-8");
  response.end(JSON.stringify(payload ?? { detail: `Unhandled fixture route: ${url.pathname}` }));
});
await new Promise((resolve) => fixtureServer.listen(0, "127.0.0.1", resolve));
const fixtureAddress = fixtureServer.address();
process.env.INTERNAL_API_URL = `http://127.0.0.1:${fixtureAddress.port}/api`;
after(() => new Promise((resolve, reject) => fixtureServer.close((error) => error ? reject(error) : resolve())));

let workerPromise;

async function getWorker() {
  if (!workerPromise) {
    const workerUrl = new URL("../dist/server/index.js", import.meta.url);
    workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
    workerPromise = import(workerUrl.href).then(({ default: worker }) => worker);
  }
  return workerPromise;
}

async function render(path = "/") {
  const worker = await getWorker();
  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the Chinese public home without starter artifacts", async () => {
  const response = await render("/");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<html[^>]*lang="zh-CN"/i);
  assert.match(html, /社会理论如何被感知/);
  assert.match(html, /阅读就是方法/);
  assert.match(html, /精选馆藏/);
  assert.match(html, /理论流派/);
  assert.match(html, /推荐页外学者/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|react-loading-skeleton/i);
  assert.match(html, /name="robots"[^>]*noindex/i);
});

test("legacy browser favicon fallback is a valid static icon", async () => {
  const icon = await readFile(new URL("../public/favicon.ico", import.meta.url));
  assert.equal(icon.readUInt16LE(0), 0);
  assert.equal(icon.readUInt16LE(2), 1);
  assert.equal(icon.readUInt16LE(4), 1);
  assert.equal(icon.readUInt32LE(18), 22);
});

test("server-renders all reference families as real routes", async () => {
  const expectations = [
    ["/explore?q=权力", /搜索书库/],
    ["/theory-schools", /从三大学科进入理论世界/],
    ["/scholars/pierre-bourdieu", /Pierre Bourdieu/i],
    ["/topics/surveillance-and-society", /监控与社会/],
    ["/reader/asset-discipline?page=34", /文档内搜索/],
    ["/reader/asset-discipline?page=34", /连续阅读/],
    ["/admin", /正在验证管理权限/],
    ["/login", /登录读者账户/],
  ];
  for (const [path, marker] of expectations) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    assert.match(await response.text(), marker, path);
  }
});

test("scholar profile renders the concise introduction and full biography from separate fields", async () => {
  const response = await render("/scholars/pierre-bourdieu");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /实践理论研究者/);
  assert.match(html, /法国社会学家/);
});

test("scholar directory keeps recommendations separate and resolves scholars outside the first list page", async () => {
  const response = await render("/scholars?q=布迪厄");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /学者推荐/);
  assert.match(html, /推荐页外学者/);
  assert.match(html, /全部学者|搜索结果/);
  assert.match(html, /皮埃尔·布迪厄/);

  const source = await readFile(
    new URL("../app/scholars/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /recommendedScholars\[0\]/);
  assert.match(source, /recommendedScholars\.slice\(1, 3\)/);
  assert.match(source, /primaryRecommendation \? \(/);
  assert.match(source, /supportingRecommendations\.length \? \(/);
  assert.match(source, /本轮暂无重点推荐/);
});

test("recommendation administration exposes explicit ordering and paged scholar search controls", async () => {
  const source = await readFile(
    new URL("../components/knowledge-admin.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /人工选择与排序/);
  assert.match(source, /moveSelected\(index, -1\)/);
  assert.match(source, /moveSelected\(index, 1\)/);
  assert.match(source, /搜索公开学者/);
  assert.match(source, /scholars\.data\?\.previous/);
  assert.match(source, /scholars\.data\?\.next/);
  assert.doesNotMatch(source, /admin\/scholars\/\?page_size=100/);
});

test("homepage and scholar directory consume only valid scholars from the shared snapshot", async () => {
  const [homeSource, scholarSource, apiSource] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/scholars/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/server-api.ts", import.meta.url), "utf8"),
  ]);
  assert.match(homeSource, /const shownScholars = recommendedScholars/);
  assert.doesNotMatch(homeSource, /loadScholars/);
  assert.doesNotMatch(homeSource, /\[\.\.\.scholars, \.\.\.recommendedScholars\]/);
  assert.match(scholarSource, /loadRecommendedScholars\(bundle, 3\)/);

  const helperStart = apiSource.indexOf("export async function loadRecommendedScholars");
  const helperEnd = apiSource.indexOf("const coverStyles", helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart);
  const helperSource = apiSource.slice(helperStart, helperEnd);
  assert.match(helperSource, /recommendationSlugs\(bundle, "home_scholars", "scholar"\)/);
  assert.match(helperSource, /if \(detail\) return detail\.scholar/);
  assert.match(helperSource, /return null/);
  assert.doesNotMatch(helperSource, /target\.name|target\.description/);
});

test("renders the three search modes and the editable about page", async () => {
  const semantic = await render("/explore?mode=semantic&q=农业现代化与组织依赖");
  assert.equal(semantic.status, 200);
  const semanticHtml = await semantic.text();
  assert.match(semanticHtml, /原文检索/);
  assert.match(semanticHtml, /观点检索/);
  assert.match(semanticHtml, /向书库提问/);
  assert.match(semanticHtml, /匹配原因|查询理解|相似原文/);
  assert.doesNotMatch(semanticHtml, /观点相同程度/);

  const about = await render("/about");
  assert.equal(about.status, 200);
  const aboutHtml = await about.text();
  assert.match(aboutHtml, /从原文出发/);
  assert.match(aboutHtml, /为什么建设这座书库/);
  assert.match(aboutHtml, /资料如何进入书库/);
  assert.match(aboutHtml, /当前版本/);
});

test("server-renders the normalized theory system and keeps the legacy route", async () => {
  const expectations = [
    ["/theories", /从三大学科进入理论世界/],
    ["/theories/disciplines/sociology", /理论传统|该分类尚无公开条目/],
    ["/theories/timeline", /社会理论历史时间轴/],
    ["/theories/graph", /社会理论图谱/],
    ["/theory-schools", /从三大学科进入理论世界/],
  ];
  for (const [path, marker] of expectations) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    const html = await response.text();
    assert.match(html, marker, path);
    assert.doesNotMatch(html, />\s*(?:undefined|NaN 部|NaN 个)\s*</i, path);
  }
});

test("server-renders every normalized theory administration entry", async () => {
  const expectations = [
    ["/admin/theory-nodes", /正在验证管理权限|理论节点管理/],
    ["/admin/theory-relations", /正在验证管理权限|理论关系与审核/],
    ["/admin/theory-timeline", /正在验证管理权限|时间轴事件管理/],
    ["/admin/reading-paths", /正在验证管理权限|阅读路径管理/],
  ];
  for (const [path, marker] of expectations) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    assert.match(await response.text(), marker, path);
  }
});

test("server-renders the repaired processing, health, analytics and settings entries", async () => {
  const expectations = [
    ["/admin/processing", /正在验证管理权限|处理中心/],
    ["/admin/system-health", /正在验证管理权限|System Health/],
    ["/admin/analytics", /正在验证管理权限|阅读与搜索统计/],
    ["/admin/semantic-index", /正在验证管理权限|语义索引/],
    ["/admin/settings", /正在验证管理权限|系统设置/],
  ];
  for (const [path, marker] of expectations) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    assert.match(await response.text(), marker, path);
  }
});

test("reader selection menu puts clean copy first without removing reading tools", async () => {
  const source = await readFile(
    new URL("../components/reader-shell.tsx", import.meta.url),
    "utf8",
  );
  const menuStart = source.indexOf('className="reader-selection-menu"');
  const menuEnd = source.indexOf("</div>", menuStart);
  assert.ok(menuStart >= 0 && menuEnd > menuStart, "reader selection menu source exists");

  const menuSource = source.slice(menuStart, menuEnd);
  const orderedActions = ["复制", "高亮", "划线", "笔记", "书签"];
  const actionPositions = orderedActions.map((label) => {
    const position = menuSource.indexOf(`/>${label}</button>`);
    assert.ok(position >= 0, `${label} action remains available`);
    return position;
  });
  assert.deepEqual(
    actionPositions,
    [...actionPositions].sort((left, right) => left - right),
    "copy is the first selection action",
  );

  assert.match(menuSource, /cleanCopy\(selectionTools\.quote\)/);
  assert.match(menuSource, /beginAnnotation\("highlight", selectionTools\)/);
  assert.match(menuSource, /beginAnnotation\("underline", selectionTools\)/);
  assert.match(menuSource, /beginAnnotation\("note", selectionTools\)/);
  assert.match(menuSource, /toggleBookmark\(selectionTools\)/);
  assert.match(source, /onCopy=\{handleDocumentCopy\}/);
  assert.match(source, /onClick=\{copyCitation\}/);
});

test("reader suppresses only expected PDF.js cancellations during responsive rerenders", async () => {
  const source = await readFile(
    new URL("../components/pdf-continuous-viewer.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /reason\.name === "RenderingCancelledException"/);
  assert.match(source, /window\.addEventListener\("unhandledrejection", handleUnhandledRejection\)/);
  assert.match(source, /isPdfRenderingCancellation\(event\.reason\)\) event\.preventDefault\(\)/);
  assert.match(source, /window\.removeEventListener\("unhandledrejection", handleUnhandledRejection\)/);
});

test("reader serializes independent progress and history writes", async () => {
  const source = await readFile(
    new URL("../components/reader-shell.tsx", import.meta.url),
    "utf8",
  );
  const progressStart = source.indexOf('"/reading/progress/"');
  const historyStart = source.indexOf('"/reading/history/"', progressStart);
  assert.ok(progressStart >= 0 && historyStart > progressStart);

  const persistenceSource = source.slice(progressStart, historyStart + 520);
  assert.match(persistenceSource, /await apiRequest/);
  assert.doesNotMatch(persistenceSource, /Promise\.all/);
  assert.equal((persistenceSource.match(/\.catch\(\(\) => undefined\)/g) ?? []).length, 2);
});

test("reader center renders five recent positions and saved-item progress", async () => {
  const source = await readFile(
    new URL("../components/reader-center.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /\.slice\(0, 5\)/);
  assert.match(source, /按最后阅读时间保留最近 5 项/);
  assert.match(source, /reading_progress: ProgressSnapshot \| null/);
  assert.match(source, /saved\.reading_progress/);
  assert.match(source, /`\/reader\/\$\{progress\.asset\}\?page=\$\{progress\.current_page\}`/);
});
