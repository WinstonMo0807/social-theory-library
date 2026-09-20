import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";
import { readStyleSource } from "../scripts/style-source.mjs";
import { selectedQueueItem } from "../lib/api/admin-collections.ts";
import { buildCandidateActionBody, resolveCandidateActionDescriptors } from "../components/admin/research/candidate-action-contract.ts";
import { normalizeEvidenceEnvelope } from "../components/admin/research/evidence-envelope.ts";

test("user administration exposes only Reader Editor and Administrator roles", async () => {
  const [sections, shell] = await Promise.all([
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin-shell.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(sections, /<option value="reader">读者<\/option>/);
  assert.match(sections, /<option value="editor">编辑<\/option>/);
  assert.match(sections, /<option value="admin">管理员<\/option>/);
  assert.doesNotMatch(sections, /<option value="reviewer">/);
  assert.doesNotMatch(shell, /user\.role === "reviewer" \? "审核者"/);
  assert.match(sections, /只有 System Owner 可以授予或撤销 Administrator/);
});

test("admin footer uses the shared 3.0.7 cataloging version", async () => {
  const [shell, version] = await Promise.all([
    readFile(new URL("../components/admin-shell.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/version.ts", import.meta.url), "utf8"),
  ]);

  assert.match(version, /WEB_APP_VERSION = "3\.0\.7"/);
  assert.match(version, /ADMIN_VERSION_LABEL = "v3\.0\.7 馆藏管理与公开发布"/);
  assert.match(shell, /import \{ ADMIN_VERSION_LABEL \} from "@\/lib\/version"/);
  assert.match(shell, /<span>\{ADMIN_VERSION_LABEL\}<\/span>/);
  assert.doesNotMatch(shell, /v2\.7(?:\.1)? 持续增长架构/);
});

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

test("admin navigation uses the thirteen approved entries and only real routes", async () => {
  const source=await readFile(new URL("../components/admin-shell.tsx",import.meta.url),"utf8");
  const navigation=source.slice(source.indexOf("const navigation = ["),source.indexOf("const routeCapabilities"));
  const routes=[...navigation.matchAll(/\["(\/admin[^"]*)",\s*[A-Za-z]+,/g)].map(match=>match[1]);
  assert.deepEqual(routes,["/admin","/admin/uploads","/admin/review","/admin/theories","/admin/scholars","/admin/topics","/admin/recommendations","/admin/about","/admin/processing","/admin/storage","/admin/backups","/admin/analytics","/admin/users"]);
  assert.equal(new Set(routes).size,13);
  assert.doesNotMatch(navigation,/\/admin\/(?:knowledge|theory-timeline|people|settings|media)"/);
  await Promise.all(routes.map(route=>access(new URL(route === "/admin" ? "../app/admin/page.tsx" : `../app${route}/page.tsx`,import.meta.url))));
});

test("AI settings expose every 3.0 capability and immutable Prompt revisions", async () => {
  const [settings, prompts] = await Promise.all([
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/prompt-registry-admin.tsx", import.meta.url), "utf8"),
  ]);

  for (const capability of [
    "entity_reasoning",
    "claim_extraction",
    "claim_attribution",
    "claim_stance",
    "rerank",
    "theory_reasoning",
    "knowledge_relation_reasoning",
    "debate_discovery",
    "reading_path_generation",
    "curation_reasoning",
  ]) {
    assert.match(settings, new RegExp(`\\| "${capability}"`));
  }
  assert.match(settings, /失败回退 profile/);
  assert.match(settings, /Credential alias/);
  assert.match(settings, /<PromptRegistryAdmin \/>/);
  assert.match(prompts, /action: "create_revision"/);
  assert.match(prompts, /action: "activate"/);
  assert.match(prompts, /建立草稿修订/);
  assert.match(prompts, /不会修改 Canonical Knowledge/);
});

test("admin navigation does not prefetch every management page at once", async () => {
  const source = await readFile(new URL("../components/admin-shell.tsx", import.meta.url), "utf8");
  assert.match(source, /navigation\.filter[\s\S]*\.map[\s\S]*prefetch=\{false\}/);
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
  assert.match(source, /selectedQueueItem/);
  assert.equal(selectedQueueItem([{ id: "edition:1" }, { id: "edition:2" }], "edition:2").id, "edition:2");
  assert.equal(selectedQueueItem([{ id: "edition:1" }], "edition:2"), null);
  assert.equal(selectedQueueItem([{ id: "edition:1" }], ""), null);
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
    "/admin/processing",
    "/admin/status",
    "/admin/system-health",
    "/admin/query-lexicon",
    "/admin/semantic-index",
    "/admin/analytics",
    "/admin/users",
    "/admin/distribution",
    "/admin/storage",
    "/admin/backups",
    "/admin/settings",
  ]);
  assert.match(source, /user\.role === "admin" \|\| !administratorOnlyRoutes\.has\(href\.split/);
  assert.match(source, /"\/admin\/processing": \["can_view_system_status"\]/);
  assert.match(source, /"\/admin\/query-lexicon": \["can_view_query_lexicon"\]/);
  assert.match(source, /"\/admin\/semantic-index": \["can_view_semantic_index"\]/);
});

test("query lexicon and semantic index keep ordinary admin views read-only", async () => {
  const [lexicon, semantic] = await Promise.all([
    readFile(new URL("../components/query-lexicon-workspace.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/semantic-index-admin.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(lexicon, /payload\?\.permissions\?\.can_manage/);
  assert.match(lexicon, /正式同步由超级管理员执行/);
  assert.match(semantic, /data\?\.permissions\.can_manage/);
  assert.match(semantic, /索引构建与切换由超级管理员执行/);
  assert.match(semantic, /version\.status === "ready" && data\.permissions\.can_manage/);
});

test("web container installs dependencies before source-dependent lifecycle scripts", async () => {
  const source = await readFile(new URL("../Dockerfile", import.meta.url), "utf8");
  assert.match(source, /npm ci --ignore-scripts/);
  assert.match(source, /COPY \. \./);
  assert.match(source, /npm prune --omit=dev --ignore-scripts/);
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

test("authority identity suggestions require an explicit request and never fill drafts", async () => {
  const [shared, sections, knowledge, theory] = await Promise.all([
    readFile(new URL("../components/structured-editors.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/knowledge-admin.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/theory-system-admin.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(shared, /authority-suggestions\/\?entity_type=\$\{encodeURIComponent\(entityType\)\}&q=\$\{encodeURIComponent\(request\.query\)\}/);
  assert.match(shared, /查找权威对象/);
  assert.match(shared, /setRequest\(\{ query: normalizedQuery, nonce:/);
  assert.doesNotMatch(shared, /\}, 650\)/);
  assert.match(shared, /\.slice\(0, 3\)/);
  assert.match(shared, /只用于确认“查的是谁”。[\s\S]*字段写入必须进入候选审核/);
  assert.match(shared, /result\.source_url/);
  assert.doesNotMatch(shared, /onApply/);
  assert.match(shared, /typeof entry === "string"/);
  assert.match(shared, /text\(row\.name\) \|\| text\(row\.alias\)/);
  assert.match(sections, /authorityType="person"/);
  assert.match(knowledge, /entityType="discipline"/);
  assert.match(knowledge, /entityType="subdiscipline"/);
  assert.match(theory, /authorityType=\{draft\.node_type === "theory_tradition"/);
  const assistant = await readFile(new URL("../components/admin/curation/curation-field-assistant.tsx", import.meta.url), "utf8");
  assert.match(assistant, /async function adopt[\s\S]*onApply\?\./);
  assert.match(assistant, /onClick=\{\(\) => choose\(candidate\)/);
  assert.match(assistant, /void adopt\(review,/);
  assert.doesNotMatch(shared, /editorial_status|publication_status|published_at/);
});

test("scholar summary and full biography remain distinct on the public profile", async () => {
  const [adapter, page, view] = await Promise.all([
    readFile(new URL("../lib/public-data-adapters.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/scholars/[slug]/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/public/scholar-public-view.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(adapter, /shortDescription: payload\.short_description \|\| payload\.person\.biography/);
  assert.match(page, /<ScholarPublicView/);
  assert.match(view, /<p>\{data\.shortDescription\}<\/p>/);
  assert.match(view, /scholar\.biography\.slice\(0,240\)/);
  assert.match(view,/href\("biography"\)/);
});

test("admin primitives are integrated without fixed-width dashboard overflow", async () => {
  const [dashboard, styles] = await Promise.all([
    readFile(new URL("../components/admin-dashboard.tsx", import.meta.url), "utf8"),
    readStyleSource(),
  ]);

  assert.match(dashboard, /import \{ PageHeader, StatusBadge \} from "\.\/admin-ui"/);
  assert.match(dashboard, /<PageHeader/);
  assert.match(dashboard, /<StatusBadge/);
  assert.match(dashboard, /尚无上传记录/);
  assert.doesNotMatch(dashboard, /<CheckCircle2/);

  assert.match(styles, /--admin-control-height: var\(--stl-control-height\)/);
  assert.match(styles, /--stl-control-height: 38px/);
  assert.match(styles, /\.admin-ui-page-header,[\s\S]*?min-width: 0;[\s\S]*?max-width: 100%;/);
  assert.match(styles, /\.admin-ui-page-header \{[\s\S]*?flex-wrap: wrap;/);
  assert.match(styles, /\.admin-ui-sticky-action-bar \{[\s\S]*?flex-wrap: wrap;/);
  assert.match(styles, /@media \(min-width: 821px\) \{[\s\S]*?\.candidate-panel \{[\s\S]*?max-height: calc\(100dvh - 76px\);[\s\S]*?overscroll-behavior: contain;/);
  assert.match(styles, /\.candidate-panel > header \{[\s\S]*?position: sticky;[\s\S]*?top: 0;/);
  assert.match(styles, /@media \(max-width: 1280px\) \{[\s\S]*?\.metric-grid \{[\s\S]*?repeat\(3, 1fr\)/);
});

test("shared review contract keeps lifecycle records separate from explicit decisions and evidence", () => {
  for (const lifecycle of ["proposed", "accepted", "rejected", "superseded"]) {
    const candidate = { status: lifecycle, action_descriptors: [{ action: "reject", url: "/catalog/admin/research/candidates/one/decision/", payload: { candidate_id: "one" } }] };
    const [descriptor] = resolveCandidateActionDescriptors(candidate);
    assert.deepEqual(buildCandidateActionBody(descriptor), { candidate_id: "one", action: "reject" });
    assert.equal(candidate.status, lifecycle);
  }
  const evidence = normalizeEvidenceEnvelope({ supporting_text: "完整的候选依据", source: { work_title: "准确作品", asset_id: "original" }, locator: { page: 9, printed_page_label: "7" }, quality: { score: 0.5, body_fetched: true } });
  assert.equal(evidence.text, "完整的候选依据");
  assert.equal(evidence.printedPageLabel, "7");
  assert.equal(evidence.readerUrl, "/reader/original?page=9");
  assert.equal(evidence.qualityScore, 0.5);
});

test("shared identity decisions require server descriptors and preserve confirmation and candidate-only import", async () => {
  const [link] = resolveCandidateActionDescriptors({ entity_type: "person", action_descriptors: [{ action: "link_existing", payload: { person_id: "selected-person", confirm_identity: true } }] });
  assert.deepEqual(buildCandidateActionBody(link), { person_id: "selected-person", confirm_identity: true, action: "link_existing" });
  assert.deepEqual(resolveCandidateActionDescriptors({ proposed_value: "同名人物" }), []);
  const uploads = await readFile(new URL("../components/admin-upload.tsx", import.meta.url), "utf8");
  assert.match(uploads, /metadata-import/);
  const editor = await readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8");
  assert.match(editor, /buildCandidateActionBody/);
  assert.match(editor, /confirm_identity/);
});

test("candidate evidence and action layouts wrap inside the review sidebar", async () => {
  const styles = readStyleSource();

  assert.match(styles, /\.candidate-panel > header \{[\s\S]*?flex-wrap: wrap;/);
  assert.match(styles, /\.candidate-count-summary \{[\s\S]*?overflow-wrap: anywhere;/);
  assert.match(styles, /\.candidate-panel \.admin-ui-candidate-card > footer \{[\s\S]*?flex-wrap: wrap;/);
  assert.match(styles, /\.metadata-candidate-evidence-record \.admin-ui-evidence-chip > span \{[\s\S]*?white-space: normal;/);
  assert.match(styles, /grid-template-columns: repeat\(auto-fit, minmax\(min\(8rem, 100%\), 1fr\)\)/);
});
