import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("hybrid search weight copy preserves the semantic_ratio API contract", async () => {
  const source = await readFile(
    new URL("../components/admin-sections.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /混合检索权重 \{Math\.round\(semanticRuntime\.semantic_ratio \* 100\)\}%/);
  assert.match(source, /type="range" min="0" max="1" step="0\.01"/);
  assert.match(source, /semantic_ratio: semanticRuntime\.semantic_ratio/);
  assert.match(source, /不是检索质量分数/);
  assert.match(source, /测试查询会显示服务端实际采用的数值/);
  assert.match(source, /disabled=\{semanticRuntime\.engine !== "meilisearch_hybrid"\}/);
  assert.match(source, /semanticRuntime\.model_health\?\.available === false \? <small className="attempt-error">混合检索权重当前不会生效/);
});

test("semantic administration uses hybrid search weight consistently", async () => {
  const sources = await Promise.all([
    "../components/admin-sections.tsx",
    "../components/semantic-index-admin.tsx",
    "../components/processing-center.tsx",
  ].map((path) => readFile(new URL(path, import.meta.url), "utf8")));
  const combined = sources.join("\n");

  assert.doesNotMatch(combined, /语义结果融合占比|实际语义占比|<dt>语义占比<\/dt>/);
  assert.match(sources[0], /混合检索权重/);
  assert.match(sources[1], /实际混合检索权重/);
  assert.match(sources[2], /<dt>混合检索权重<\/dt>/);
  sources.forEach((source) => assert.match(source, /不是检索质量分数/));
});

test("semantic index switch uses a validated candidate and explicit confirmation", async () => {
  const source = await readFile(
    new URL("../components/semantic-index-admin.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /建立快照候选/);
  assert.match(source, /验证并切换/);
  assert.match(source, /confirmed: true/);
  assert.match(source, /当前活动索引将保留为已停用版本/);
});

test("semantic administration exposes a real evaluation workflow and no fake reranker field", async () => {
  const [indexSource, settingsSource] = await Promise.all([
    readFile(new URL("../components/semantic-index-admin.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(indexSource, /馆内检索评估/);
  assert.match(indexSource, /mode: "dry_run"/);
  assert.match(indexSource, /mode: "enqueue"/);
  assert.match(indexSource, /至少要把一个结果标为具有证据价值或直接回应/);
  assert.match(indexSource, /不会切换或删除任何索引版本/);
  assert.match(indexSource, /Recall@20/);
  assert.match(indexSource, /nDCG@10/);
  assert.match(indexSource, /Precision@5/);
  assert.match(indexSource, /Top 5 有用结果/);
  assert.match(indexSource, /Top 3 直接回应/);
  assert.match(settingsSource, /<option value="rules">内置规则重排<\/option>/);
  assert.match(settingsSource, /不能只保存一个模型名称/);
  assert.doesNotMatch(settingsSource, /<span>重排方式<\/span><input/);
});

test("semantic admin distinguishes loading, unverified model state and server-confirmed fallback", async () => {
  const [indexSource, settingsSource] = await Promise.all([
    readFile(new URL("../components/semantic-index-admin.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(indexSource, /value \?\? "—"/);
  assert.match(indexSource, /语义模型不可用/);
  assert.match(indexSource, /请以下方测试查询结果为准/);
  assert.match(indexSource, /setTestResult\(null\)/);
  assert.match(indexSource, /aria-busy=\{busy === "test"\}/);
  assert.match(indexSource, /服务端确认使用关键词检索/);
  assert.match(indexSource, /indexStatusLabels/);
  assert.match(indexSource, /evaluationStatusLabels/);
  assert.match(settingsSource, /const semanticRuntimeReady = Boolean/);
  assert.match(settingsSource, /载入完成前不会显示或保存默认值/);
  assert.match(settingsSource, /if \(!token \|\| !semanticRuntimeReady\)/);
});

test("admin navigation uses the approved groups and only real routes", async () => {
  const source = await readFile(
    new URL("../components/admin-shell.tsx", import.meta.url),
    "utf8",
  );
  const navigationStart = source.indexOf("const navigation = [");
  const navigationEnd = source.indexOf("const administratorOnlyRoutes", navigationStart);
  assert.ok(navigationStart >= 0 && navigationEnd > navigationStart);
  const navigationSource = source.slice(navigationStart, navigationEnd);

  const expectedGroups = [
    ["概览", ["/admin", "/admin/analytics"]],
    ["上架", ["/admin/uploads", "/admin/review", "/admin/processing"]],
    ["馆藏", ["/admin/library"]],
    ["学者与机构", ["/admin/scholars"]],
    ["理论知识", [
      "/admin/disciplines",
      "/admin/subdisciplines",
      "/admin/theory-nodes",
      "/admin/theory-relations",
      "/admin/theory-timeline",
      "/admin/topics",
      "/admin/reading-paths",
    ]],
    ["搜索与模型", ["/admin/semantic-index"]],
    ["发布", ["/admin/publication", "/admin/recommendations", "/admin/about"]],
    ["系统", [
      "/admin/system-health",
      "/admin/users",
      "/admin/distribution",
      "/admin/settings",
    ]],
  ];

  const groupPositions = expectedGroups.map(([group]) => {
    const position = navigationSource.indexOf(`["${group}", [`);
    assert.ok(position >= 0, `${group} group exists`);
    return position;
  });
  assert.deepEqual(
    groupPositions,
    [...groupPositions].sort((left, right) => left - right),
    "admin groups follow the approved order",
  );

  const allRoutes = [];
  expectedGroups.forEach(([group, expectedRoutes], index) => {
    const groupStart = groupPositions[index];
    const groupEnd = groupPositions[index + 1] ?? navigationSource.length;
    const groupSource = navigationSource.slice(groupStart, groupEnd);
    const actualRoutes = [...groupSource.matchAll(/\["(\/admin[^"]*)",\s*[A-Za-z]+,/g)]
      .map((match) => match[1]);
    assert.deepEqual(actualRoutes, expectedRoutes, `${group} contains only its existing entries`);
    allRoutes.push(...actualRoutes);
  });

  assert.equal(new Set(allRoutes).size, allRoutes.length, "navigation routes are unique");
  await Promise.all(allRoutes.map((href) => access(new URL(
    href === "/admin" ? "../app/admin/page.tsx" : `../app${href}/page.tsx`,
    import.meta.url,
  ))));
});

test("admin navigation does not prefetch every management page at once", async () => {
  const source = await readFile(new URL("../components/admin-shell.tsx", import.meta.url), "utf8");
  assert.match(source, /visibleLinks\.map[\s\S]*prefetch=\{false\}/);
  assert.match(source, /admin-processing-link[\s\S]*prefetch=\{false\}/);
});

test("shared public navigation avoids anonymous API bursts from route prefetch", async () => {
  const [header, footer] = await Promise.all([
    readFile(new URL("../components/site-header.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/site-footer.tsx", import.meta.url), "utf8"),
  ]);
  assert.doesNotMatch(header, /<Link(?![^>]*prefetch=\{false\})[^>]*>/);
  assert.doesNotMatch(footer, /<Link(?![^>]*prefetch=\{false\})[^>]*>/);
});

test("publication filters keep the detail pane on a visible item", async () => {
  const source = await readFile(
    new URL("../components/publication-desk.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /const active = filtered\.find\(\(item\) => item\.id === selectedId\) \?\? filtered\[0\] \?\? null/);
  assert.match(source, /className=\{item\.id === active\?\.id \? "active" : ""\}/);
});

test("admin-only navigation permissions remain explicit after regrouping", async () => {
  const source = await readFile(
    new URL("../components/admin-shell.tsx", import.meta.url),
    "utf8",
  );
  const permissionStart = source.indexOf("const administratorOnlyRoutes");
  const permissionEnd = source.indexOf("export function AdminShell", permissionStart);
  const permissionSource = source.slice(permissionStart, permissionEnd);
  const routes = [...permissionSource.matchAll(/"(\/admin[^"]*)"/g)]
    .map((match) => match[1]);

  assert.deepEqual(routes, [
    "/admin/system-health",
    "/admin/semantic-index",
    "/admin/analytics",
    "/admin/users",
    "/admin/distribution",
    "/admin/settings",
  ]);
  assert.match(source, /user\.role === "admin" \|\| !administratorOnlyRoutes\.has\(href\)/);
});

test("shared admin UI primitives expose text states and keyboard-safe controls", async () => {
  const source = await readFile(
    new URL("../components/admin-ui.tsx", import.meta.url),
    "utf8",
  );

  [
    "PageHeader",
    "StatusBadge",
    "EmptyState",
    "FormSection",
    "StickyActionBar",
    "CandidateCard",
    "EvidenceChip",
    "ConfidenceBar",
  ].forEach((name) => assert.match(source, new RegExp(`export function ${name}\\(`)));

  assert.match(source, /aria-label=\{ariaLabel \?\? `状态：\$\{label\}`\}/);
  assert.match(source, /<i aria-hidden="true" \/>/);
  assert.match(source, /role="status"/);
  assert.match(source, /role="region" aria-label=\{label\}/);
  assert.match(source, /<button className=\{classes\} type="button" onClick=\{onActivate\}/);
  assert.match(source, /role="progressbar"/);
  assert.match(source, /<details className="admin-ui-candidate-evidence">/);
  assert.match(source, /<summary>\{evidenceSummary\}<\/summary>/);
  assert.match(source, /aria-valuenow=\{percent\}/);
});

test("structured admin editors replace delimiter-driven core forms without changing payload shapes", async () => {
  const [shared, sections, knowledge, theory] = await Promise.all([
    readFile(new URL("../components/structured-editors.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/knowledge-admin.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/theory-system-admin.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(shared, /export function StringListEditor/);
  assert.match(shared, /export function StructuredRowsEditor/);
  assert.match(shared, /aria-label=\{`移除\$\{itemLabel\} \$\{index \+ 1\}`\}/);
  assert.match(sections, /label="生平与重要发表"/);
  assert.match(sections, /\{ key: "type", label: "类型", options: scholarTimelineTypes \}/);
  assert.match(sections, /formatScholarTimelineEvent\(row\.type, row\.event\)/);
  assert.match(theory, /language: item\.language \|\| "zh-CN"/);
  assert.match(theory, /alias_type: item\.alias_type \|\| "alias"/);
  assert.doesNotMatch([sections, knowledge, theory].join("\n"), /每行一项|每行“/);
});

test("authority suggestions debounce, limit results and only fill editable drafts", async () => {
  const [shared, sections, knowledge, theory] = await Promise.all([
    readFile(new URL("../components/structured-editors.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/knowledge-admin.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/theory-system-admin.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(shared, /authority-suggestions\/\?entity_type=\$\{encodeURIComponent\(entityType\)\}&q=\$\{encodeURIComponent\(normalizedQuery\)\}/);
  assert.match(shared, /\}, 650\)/);
  assert.match(shared, /\.slice\(0, 3\)/);
  assert.match(shared, /采用后只填入当前草稿，仍需单独保存和发布/);
  assert.match(shared, /typeof entry === "string"/);
  assert.match(shared, /text\(row\.name\) \|\| text\(row\.alias\)/);
  assert.match(sections, /entityType="person"/);
  assert.match(knowledge, /entityType="discipline"/);
  assert.match(knowledge, /entityType="subdiscipline"/);
  assert.match(theory, /entityType=\{draft\.node_type === "theory_tradition"/);
  assert.doesNotMatch(shared, /editorial_status|publication_status|published_at/);
});

test("scholar summary and full biography remain distinct on the public profile", async () => {
  const [serverApi, page] = await Promise.all([
    readFile(new URL("../lib/server-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/scholars/[slug]/page.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(serverApi, /shortDescription: payload\.short_description \|\| payload\.person\.biography/);
  assert.match(page, /<p className="biography">\{shortDescription\}<\/p>/);
  assert.match(page, /<p>\{scholar\.biography\}<\/p>/);
});

test("admin primitives are integrated without fixed-width dashboard overflow", async () => {
  const [dashboard, styles] = await Promise.all([
    readFile(new URL("../components/admin-dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /import \{ EmptyState, PageHeader, StatusBadge, type StatusTone \} from "\.\/admin-ui"/);
  assert.match(dashboard, /<PageHeader/);
  assert.match(dashboard, /<StatusBadge/);
  assert.match(dashboard, /<EmptyState compact title="尚无上传记录"/);
  assert.doesNotMatch(dashboard, /<CheckCircle2/);

  assert.match(styles, /--admin-control-height: 38px/);
  assert.match(styles, /\.admin-ui-page-header,[\s\S]*?min-width: 0;[\s\S]*?max-width: 100%;/);
  assert.match(styles, /\.admin-ui-page-header \{[\s\S]*?flex-wrap: wrap;/);
  assert.match(styles, /\.admin-ui-sticky-action-bar \{[\s\S]*?flex-wrap: wrap;/);
  assert.match(styles, /@media \(min-width: 821px\) \{[\s\S]*?\.candidate-panel \{[\s\S]*?max-height: calc\(100dvh - 76px\);[\s\S]*?overscroll-behavior: contain;/);
  assert.match(styles, /\.candidate-panel > header \{[\s\S]*?position: sticky;[\s\S]*?top: 0;/);
  assert.match(styles, /@media \(max-width: 1280px\) \{[\s\S]*?\.metric-grid \{[\s\S]*?repeat\(3, 1fr\)/);
});

test("metadata review exposes auditable candidate lifecycle and real decisions", async () => {
  const source = await readFile(
    new URL("../components/metadata-review.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /type CandidateLifecycle = "proposed" \| "accepted" \| "rejected" \| "superseded"/);
  assert.match(source, /score_factors: Record<string, unknown>/);
  assert.match(source, /evidence_records: CandidateEvidence\[\]/);
  assert.match(source, /<MetadataCandidateScoreFactors factors=\{candidate\.score_factors \?\? \{\}\} \/>/);
  assert.match(source, /<MetadataCandidateEvidenceList candidate=\{candidate\}/);
  assert.match(source, /pageLabel=\{pageLabel\}/);
  assert.match(source, /candidateLifecycleLabels\[lifecycle\]/);
  assert.match(source, /\/ingestion\/items\/\$\{itemId\}\/metadata-candidates\/\$\{candidate\.id\}\/decision\//);
  assert.match(source, /body: JSON\.stringify\(\{ action \}\)/);
  assert.match(source, />填入表单<\/button>/);
  assert.match(source, /"reject"/);
  assert.match(source, /恢复待审/);
  assert.match(source, /填入表单不等于最终接受/);
  assert.doesNotMatch(source, /采用此值/);
});

test("metadata review uses confirmed entity decisions and review-only bibliographic imports", async () => {
  const source = await readFile(
    new URL("../components/metadata-review.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /entity_resolution_candidates: EntityResolutionCandidate\[\]/);
  assert.match(source, /同名不会自动合并/);
  assert.match(source, /同名不(?:会)?自动合并/);
  assert.match(source, /保存复核内容时建立草稿档案，发布前仍需核对/);
  assert.match(source, /现阶段只用于核对/);
  assert.match(source, /entity-resolution-candidates\/\$\{candidate\.id\}\/decision\//);
  assert.match(source, /confirm_identity: action === "link_existing" && candidate\.target_type === "person"/);
  assert.match(source, /系统不会把草稿或未解析名称直接公开/);
  assert.match(source, /\/ingestion\/items\/\$\{itemId\}\/metadata-import\//);
  assert.match(source, /支持单条 RIS、BibTeX、CSL-JSON、sidecar JSON 与安全 YAML/);
  assert.match(source, /导入内容只形成待审候选，不会直接覆盖馆藏/);
});

test("candidate evidence and action layouts wrap inside the review sidebar", async () => {
  const styles = await readFile(
    new URL("../app/globals.css", import.meta.url),
    "utf8",
  );

  assert.match(styles, /\.candidate-panel > header \{[\s\S]*?flex-wrap: wrap;/);
  assert.match(styles, /\.candidate-count-summary \{[\s\S]*?overflow-wrap: anywhere;/);
  assert.match(styles, /\.candidate-panel \.admin-ui-candidate-card > footer \{[\s\S]*?flex-wrap: wrap;/);
  assert.match(styles, /\.metadata-candidate-evidence-record \.admin-ui-evidence-chip > span \{[\s\S]*?white-space: normal;/);
  assert.match(styles, /grid-template-columns: repeat\(auto-fit, minmax\(min\(8rem, 100%\), 1fr\)\)/);
});
