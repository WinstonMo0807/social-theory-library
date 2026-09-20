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
  id: "scholar-profile-fixture",
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
  id: "recommended-scholar-profile-fixture",
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

function fixturePayload(pathname, query = new URLSearchParams()) {
  if (pathname === "/api/catalog/site-config/") return defaultSiteConfig;
  if (pathname === "/api/catalog/recommendation-issues/") return {count:0,next:null,previous:null,results:[],current:null};
  if (pathname === "/api/catalog/site-stats/") return { documents: 1, scholars: 1, knowledge_objects: 2, last_updated: null, last_updated_label: "测试", version: "2.8.1" };
  if (pathname === "/api/catalog/hot-searches/") return { period_days: 30, results: [] };
  if (pathname === "/api/catalog/works/") return paginated([sampleWork]);
  if (pathname === "/api/catalog/scholars/") return paginated([sampleScholar]);
  if (pathname === "/api/catalog/scholars/pierre-bourdieu/") return sampleScholar;
  if (pathname === "/api/catalog/scholars/recommended-outside-first-page/") return recommendedScholar;
  if (pathname === "/api/catalog/scholar-relations/") return paginated([{id:"shared-scholar-relation",source_scholar:sampleScholar.id,target_scholar:recommendedScholar.id,source_name:sampleScholar.person.preferred_name,target_name:recommendedScholar.person.preferred_name,source_slug:sampleScholar.slug,target_slug:recommendedScholar.slug,relation_type:"comparative_reading",direction:"undirected",summary:"测试馆藏的比较阅读关系",source:"隔离测试文献第 3 页",status:"published"}]);
  if (pathname === "/api/catalog/theory-schools/") return paginated([sampleTheory]);
  if (pathname === "/api/catalog/theory-schools/practice-theory/") return sampleTheory;
  if (pathname === "/api/catalog/theory-schools/mapped-practice/") return {...sampleTheory,slug:"mapped-practice",canonical_node_url:"/theories/nodes/canonical-practice"};
  if (pathname === "/api/catalog/theory-system/nodes/" && query.get("q") === "directory-fixture") return {count:49,next:"?page=3",previous:"?page=1",results:[{id:"directory-node",slug:"directory-concept",node_type:"concept",canonical_name_zh:"目录分页测试概念",summary:"由测试 API 返回的第二页条目。",related_disciplines:[],representative_scholars:[],work_count:1}]};
  if (pathname === "/api/catalog/topics/") return paginated([sampleTopic]);
  if (pathname === "/api/catalog/topics/surveillance-and-society/") return sampleTopic;
  if (pathname === "/api/catalog/topics/recommended-topic-outside-first-page/") return { ...sampleTopic, id: "recommended-topic-fixture", slug: "recommended-topic-outside-first-page", name: "目录页外精选主题" };
  if (pathname === "/api/catalog/topics/cleared-evidence/") return { ...sampleTopic, id: "topic-cleared", slug: "cleared-evidence", passages: [{ id: "retired-passage", title: "旧摘录不应复活", text: "旧摘录不应复活", snippet: "旧摘录不应复活", page_index: 1, asset_id: "asset-old" }] };
  const curationMatch = pathname.match(/^\/api\/catalog\/evidence-curation\/(scholar|topic|node)\/([^/]+)\/$/);
  if (curationMatch) {
    const [, object_type, object_id] = curationMatch;
    const configured = object_id === "scholar-profile-fixture" || object_id === "topic-cleared";
    return { configured, object_type, object_id, title: "原文策展测试", items: object_id === "scholar-profile-fixture" ? [{ id: "reference-fixture", source_type: "span", source_id: "span-fixture", group_title: "从原文理解实践", reason: "管理员明确填写的关联理由", order: 0, source: { id: "span-fixture", source_type: "span", text: "策展接口发布的真实测试原文。", work_id: sampleWork.id, work_title: sampleWork.title, edition_id: "edition-fixture", edition_label: "测试出版社 2026 精确版本", asset_id: "asset-discipline", page_start: 34, page_end: 34, printed_label: "21", reader_url: "/reader/asset-discipline?page=34", public_eligible: true } }] : [] };
  }
  if (pathname === "/api/catalog/recommendations/") return {
    shared_for_all_readers: true,
    rotation_days: 3,
    placements: {
      home_topics: { id: "home-topics-policy", placement: "home_topics", title: "精选主题", item_count: 5, enabled: true,
        current: { id: "home-topics-snapshot", items: [{ id: "home-topics-item", position: 0, reason: "明确策展", image_override: "", target_type: "topic", target: { id: "recommended-topic-fixture", slug: "recommended-topic-outside-first-page", name: "目录页外精选主题" } }] } },
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
  if (pathname === "/api/catalog/theory-system/nodes/secondary-page-fixture/") return {
    id:"secondary-page-node",slug:"secondary-page-fixture",node_type:"theory_tradition",canonical_name_zh:"次级分页测试理论",canonical_name_en:"",summary:"测试次级页面的真实分页。",definition:"",core_questions:[],basic_propositions:["命题一","命题二","命题三","命题四","命题五","第六条命题必须保留"],theoretical_boundary:"",primary_discipline:null,related_disciplines:[],subdiscipline_links:[],topic_links:[],representative_scholars:[],period_label:"",work_count:0,work_groups:{},direct_relations:[],evidence:[],curated_claims:{core_viewpoint:[],major_criticism:[],major_response:[]},cover_url:"",updated_at:null,
  };
  if (pathname === "/api/catalog/theory-system/reading-paths/" && query.get("node") === "secondary-page-fixture") return {
    count:25,next:null,previous:"?page=1",results:[{id:"path-second-page",slug:"path-second-page",title:"第二页关联阅读路径",introduction:"先筛选该理论再分页。",items:[{id:"path-item",reading_order:1,stage_name:"开始阅读",stage_description:"",node_data:{id:"secondary-page-node",canonical_name_zh:"次级分页测试理论"},work_data:null}]}],
  };
  if (pathname === "/api/catalog/theory-system/timeline/" && query.get("node") === "secondary-page-fixture") return {
    count:25,next:null,previous:"?page=1",results:[{id:"event-second-page",date_label:"1990",start_year:1990,title:"第二页关联理论事件",description:"保留真实事件入口。"}],
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

const requestedFixtureRoutes = [];
const fixtureServer = createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  requestedFixtureRoutes.push(`${url.pathname}${url.search}`);
  const payload = fixturePayload(url.pathname, url.searchParams);
  response.statusCode = payload === null ? 404 : 200;
  response.setHeader("content-type", "application/json; charset=utf-8");
  // Each SSR request may race metadata and layout fetches; avoid sharing a short-lived fixture socket.
  response.setHeader("connection", "close");
  response.end(JSON.stringify(payload ?? { detail: `Unhandled fixture route: ${url.pathname}` }));
});
await new Promise((resolve) => fixtureServer.listen(0, "127.0.0.1", resolve));
const fixtureAddress = fixtureServer.address();
process.env.INTERNAL_API_URL = `http://127.0.0.1:${fixtureAddress.port}/api`;
after(() => new Promise((resolve, reject) => fixtureServer.close((error) => error ? reject(error) : resolve())));

let workerPromise;
const renderErrors = [];
globalThis.__VINEXT_onRequestErrorHandler__ = error => { renderErrors.push(error.message); };
after(() => { delete globalThis.__VINEXT_onRequestErrorHandler__; });

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
  assert.match(html, /<h2>本期书库推荐<\/h2>/);
  assert.doesNotMatch(html, /<h2[^>]*>精选馆藏/);
  assert.match(html, /理论流派/);
  assert.match(html, /推荐页外学者/);
  assert.match(html, /目录页外精选主题/);
  assert.match(html, /href="\/topics\/recommended-topic-outside-first-page"/);
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
  const response = await render("/scholars");
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
  assert.match(source, /<ScholarDirectoryRecommendations/);
  assert.match(source, /loadRecommendedScholars\(bundle, 4\)/);
  const directory=await render("/scholars?q=布迪厄&view=directory");
  assert.equal(directory.status,200);
  const directoryHtml=await directory.text();
  assert.match(directoryHtml,/皮埃尔·布迪厄/);
  assert.doesNotMatch(directoryHtml,/学者推荐/);

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
  assert.match(source, /candidateResource\.data\?\.previous/);
  assert.match(source, /candidateResource\.data\?\.next/);
  assert.doesNotMatch(source, /admin\/scholars\/\?page_size=100/);
});

test("homepage and scholar directory combine confirmed recommendations with actual public scholar records", async () => {
  const [homeSource, scholarSource, apiSource] = await Promise.all([
    readFile(new URL("../lib/api/home.server.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/scholars/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/api/recommendations.server.ts", import.meta.url), "utf8"),
  ]);
  assert.match(homeSource, /loadRecommendedScholars\(bundle, 6\)/);
  assert.match(homeSource, /loadScholars\(\)/);
  assert.match(homeSource, /selectedScholars\.some/);
  assert.match(scholarSource, /loadRecommendedScholars\(bundle, 4\)/);

  const helperStart = apiSource.indexOf("export async function loadRecommendedScholars");
  assert.ok(helperStart >= 0);
  const helperSource = apiSource.slice(helperStart);
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
    ["/theories", /<h1>理论流派<\/h1>/],
    ["/theories/disciplines/sociology", /理论传统|该分类尚无公开条目/],
    ["/theories/timeline", /社会理论历史时间轴/],
    ["/theories/graph", /社会理论图谱/],
    ["/theory-schools", /从三大学科进入理论世界/],
  ];
  for (const [path, marker] of expectations) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    const html = await response.text();
    assert.ok(!html.includes("这部分内容没有正常载入"), `${path}: ${renderErrors.join("; ")}; fixture calls ${requestedFixtureRoutes.join(", ")}`);
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
    ["/admin/processing/health", /正在验证管理权限|System Health/],
    ["/admin/analytics", /正在验证管理权限|阅读与搜索统计/],
    ["/admin/processing/semantic-index", /正在验证管理权限|语义索引/],
    ["/admin/processing/settings", /正在验证管理权限|处理设置/],
  ];
  for (const [path, marker] of expectations) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    assert.match(await response.text(), marker, path);
  }
  for (const [legacy, destination] of [["/admin/system-health", "/admin/processing/health"], ["/admin/semantic-index", "/admin/processing/semantic-index"]]) {
    const response = await render(`${legacy}?return_to=%2Fadmin`);
    assert.equal(response.status, 307, legacy);
    const location = new URL(response.headers.get("location"), "http://localhost");
    assert.equal(`${location.pathname}${location.search}`, `${destination}?return_to=%2Fadmin`, legacy);
  }
});

test("published evidence uses the shared curation endpoint and explicit clearing does not revive legacy passages", async () => {
  const response = await render("/scholars/pierre-bourdieu/evidence");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /策展接口发布的真实测试原文/);
  assert.match(html, /管理员明确填写的关联理由/);
  assert.match(html, /测试出版社 2026 精确版本/);
  assert.match(html, /reader\/asset-discipline\?page=34/);
  assert.ok(requestedFixtureRoutes.some(route => route === "/api/catalog/evidence-curation/scholar/scholar-profile-fixture/"));
  const cleared = await render("/topics/cleared-evidence/passages");
  assert.equal(cleared.status, 200);
  const clearedHtml = await cleared.text();
  assert.match(clearedHtml, /尚未策展原文/);
  // Serialized RSC data may still retain the legacy object; only rendered copy must be absent.
  const visibleHtml = clearedHtml.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");
  assert.doesNotMatch(visibleHtml, /旧摘录不应复活/);
});

test("normalized directory preserves filters and ordering across API pagination", async () => {
  const response = await render("/theories/directory?type=concept&discipline=sociology&q=directory-fixture&sort=updated&page=2");
  assert.equal(response.status,200);
  const html = await response.text();
  assert.match(html,/目录分页测试概念/);
  assert.match(html,/最近更新/);
  const links = Array.from(html.matchAll(/href="([^"]*theories\/directory\?[^"]*)"/g), match => new URL(match[1].replaceAll("&amp;","&"),"http://localhost"));
  for (const page of ["1","3"]) assert.ok(links.some(link => link.searchParams.get("page") === page && link.searchParams.get("type") === "concept" && link.searchParams.get("discipline") === "sociology" && link.searchParams.get("q") === "directory-fixture" && link.searchParams.get("sort") === "updated"));
  assert.ok(requestedFixtureRoutes.some(route => { const url = new URL(route,"http://localhost"); return url.pathname === "/api/catalog/theory-system/nodes/" && url.searchParams.get("page") === "2" && url.searchParams.get("sort") === "updated"; }));
});

test("legacy theory details follow only explicit canonical mappings and retain section context", async () => {
  for (const [path,destination] of [["/theory-schools/mapped-practice?from=topic","/theories/nodes/canonical-practice?from=topic"],["/theory-schools/mapped-practice/reading-list?from=topic","/theories/nodes/canonical-practice/works?from=topic"],["/theory-schools/mapped-practice/scholars","/theories/nodes/canonical-practice#scholars"]]) {
    const response = await render(path);
    assert.equal(response.status,307,path);
    const location = new URL(response.headers.get("location"),"http://localhost");
    assert.equal(`${location.pathname}${location.search}${location.hash}`,destination);
  }
  const unmapped = await render("/theory-schools/practice-theory");
  assert.equal(unmapped.status,200);
  assert.match(await unmapped.text(),/此历史条目尚待确认与规范理论的关联/);
});

test("timeline rejects reversed years before requesting an event page", async () => {
  const start = requestedFixtureRoutes.length;
  const response = await render("/theories/timeline?year_from=2000&year_to=1900");
  assert.equal(response.status,200);
  assert.match(await response.text(),/起始年不能晚于结束年/);
  assert.ok(!requestedFixtureRoutes.slice(start).some(route => route.startsWith("/api/catalog/theory-system/timeline/")));
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
    const nativePosition = menuSource.indexOf(`/>${label}</button>`);
    const actionButtonPosition = menuSource.indexOf(`/>${label}</ActionButton>`);
    const position = Math.max(nativePosition, actionButtonPosition);
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
    new URL("../components/reader/use-reader-progress.ts", import.meta.url),
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

test("theory secondary pages preserve associated paths and events beyond the first API page", async () => {
  for (const [section,label,endpoint] of [["works","第二页关联阅读路径","reading-paths"],["timeline","第二页关联理论事件","timeline"]]) {
    const response=await render(`/theories/nodes/secondary-page-fixture/${section}?page=2`);
    assert.equal(response.status,200);
    const html=await response.text();
    assert.match(html,new RegExp(label));
    const links=Array.from(html.matchAll(/href="([^"]+)"/g),match=>new URL(match[1].replaceAll("&amp;","&"),"http://localhost"));
    assert.ok(links.some(link=>link.pathname===`/theories/nodes/secondary-page-fixture/${section}`&&link.searchParams.get("page")==="1"));
    assert.ok(requestedFixtureRoutes.some(value=>{const url=new URL(value,"http://localhost");return url.pathname===`/api/catalog/theory-system/${endpoint}/`&&url.searchParams.get("node")==="secondary-page-fixture"&&url.searchParams.get("page")==="2";}));
  }
  const response=await render("/theories/nodes/secondary-page-fixture/propositions");
  assert.equal(response.status,200);
  assert.match(await response.text(),/第六条命题必须保留/);
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
