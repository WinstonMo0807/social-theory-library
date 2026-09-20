import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const studioUrl = new URL("../components/knowledge-workspace.tsx", import.meta.url);
const diagnosticUrl = new URL("../components/knowledge-workspace-diagnostics.tsx", import.meta.url);
const editorialStudioUrl = new URL("../components/knowledge-workspace.tsx", import.meta.url);
const shellUrl = new URL("../components/admin-shell.tsx", import.meta.url);
const nodeEditorUrl = new URL("../components/theory-system-admin.tsx", import.meta.url);
const taxonomyEditorUrl = new URL("../components/knowledge-admin.tsx", import.meta.url);
const adminSectionsUrl = new URL("../components/admin-sections.tsx", import.meta.url);
const objectContextUrl = new URL("../components/admin/knowledge/knowledge-object-context-panel.tsx", import.meta.url);
const lifecycleUrl = new URL("../components/entity-lifecycle-actions.tsx", import.meta.url);
const readingPathEditorUrl = new URL("../components/admin/curation/reading-path-workbench.tsx", import.meta.url);
const knowledgePreviewUrl = new URL("../components/admin/preview/knowledge-page-preview.tsx", import.meta.url);
const knowledgePreviewPageUrl = new URL("../app/admin/preview/knowledge/[objectType]/[objectId]/page.tsx", import.meta.url);
const publicPageUrls = [
  "../app/theories/disciplines/[slug]/page.tsx",
  "../app/subdisciplines/[slug]/page.tsx",
  "../app/theories/nodes/[slug]/page.tsx",
  "../app/theories/reading-paths/[slug]/page.tsx",
  "../app/scholars/[slug]/page.tsx",
  "../app/topics/[slug]/page.tsx",
].map((path) => new URL(path, import.meta.url));
const stylesUrl = new URL("../app/editorial-workspaces.css", import.meta.url);

test("retired Knowledge Studio preserves specialist object editing destinations", async () => {
  const [studio, shell, nodeEditor, taxonomyEditor, readingPathEditor] = await Promise.all([
    readFile(editorialStudioUrl, "utf8"),
    readFile(shellUrl, "utf8"),
    readFile(nodeEditorUrl, "utf8"),
    readFile(taxonomyEditorUrl, "utf8"),
    readFile(readingPathEditorUrl, "utf8"),
  ]);

  assert.doesNotMatch(shell, /\["\/admin\/knowledge",/);
  const legacy = await readFile(new URL("../components/admin/knowledge/knowledge-legacy-redirect.tsx", import.meta.url), "utf8");
  assert.match(legacy,/object_type/);
  assert.match(legacy,/object_id/);
  assert.match(legacy,/window\.location\.hash/);
  assert.match(studio, /href="\/admin\/theories"/);
  assert.match(studio, /href="\/admin\/scholars"/);
  assert.match(studio, /href="\/admin\/topics"/);
  assert.match(studio, /完整编辑/);
  assert.match(studio, /\/admin\/system-health\/knowledge/);
  assert.match(nodeEditor, /search\.get\("node"\)/);
  assert.match(nodeEditor, /已从 知识管理 打开这个理论或概念资料/);
  assert.match(taxonomyEditor, /searchParams\.get\("subdiscipline"\)/);
  assert.match(taxonomyEditor, /已打开所选子学科/);
  assert.match(readingPathEditor, /searchParams\.get\("path"\)/);
  assert.match(readingPathEditor, /encodeURIComponent\(requestedPath\)/);
});

test("the actual primary Studio owns public scope, editorial sections and publication", async () => {
  const studio = await readFile(studioUrl, "utf8");

  for (const label of ["基本资料", "相关内容", "观点与讨论", "发布与记录", "页面内容"]) {
    assert.match(studio, new RegExp(label));
  }
  for (const objectType of ["theory", "concept", "debate", "scholar", "discipline", "subdiscipline", "topic", "reading_path", "work"]) {
    assert.match(studio, new RegExp(`${objectType}:`));
  }
  assert.match(studio, /<PublicPageTree control=\{selection\.public_control\}/);
  assert.match(studio, /<AssistanceUsagePanel/);
  assert.match(studio, /<CurationFieldAssistant/);
  assert.match(studio, /ReaderEvidence/);
  assert.match(studio, /确认发布本次编辑/);
  assert.match(studio, /onPublish/);
  assert.match(studio, /有修改还没有发布/);
});

test("Scholar Discipline Theory and Topic share the bounded object Inspector", async () => {
  const [panel, nodeEditor, disciplineEditor, adminSections] = await Promise.all([
    readFile(objectContextUrl, "utf8"),
    readFile(nodeEditorUrl, "utf8"),
    readFile(taxonomyEditorUrl, "utf8"),
    readFile(adminSectionsUrl, "utf8"),
  ]);

  for (const source of [nodeEditor, disciplineEditor, adminSections]) {
    assert.match(source, /KnowledgeObjectContextPanel/);
  }
  for (const objectType of ["scholar", "discipline", "topic"]) {
    assert.match(adminSections + disciplineEditor, new RegExp(`objectType="${objectType}"`));
  }
  assert.match(nodeEditor, /knowledgeStudioNodeType/);
  for (const feature of ["前台内容完整度", "knowledgeUpdates", "EvidenceEnvelopeCard", "curatedClaims", "revisions", "projectionStates"]) {
    assert.match(panel, new RegExp(feature));
  }
  assert.match(panel, /CandidateDecisionBar/);
  assert.match(panel, /EvidenceEnvelopeCard/);
  assert.match(panel, /\/catalog\/admin\/knowledge-workspace\//);
});

test("Knowledge Studio requests a bounded selected-object read model", async () => {
  const studio = await readFile(studioUrl, "utf8");

  assert.match(studio, /limit: "40"/);
  assert.match(studio, /params\.set\("selected_type", selectedType\)/);
  assert.match(studio, /params\.set\("selected_id", selectedId\)/);
  assert.match(studio, /\/catalog\/admin\/knowledge-workspace\//);
  assert.match(studio, /subdiscipline: "子学科"/);
  assert.match(studio, /reading_path: "阅读路径"/);
  assert.match(studio, /work: "作品"/);
  assert.match(studio, /Object\.entries\(objectLabels\)/);
  assert.match(studio, /aria-label="内容导航"/);
  assert.match(studio, /studio\.selection_error/);
});

test("professional diagnostics retain identity and source checks without a parallel editor", async () => {
  const diagnostics = await readFile(diagnosticUrl, "utf8");
  assert.match(diagnostics, /useApiResource<KnowledgePayload>/);
  assert.match(diagnostics, /params\.set\("selected_type", kind\)/);
  assert.match(diagnostics, /params\.set\("selected_id", objectId\)/);
  assert.match(diagnostics, /source_revision/);
  assert.match(diagnostics, /projected_revision/);
  assert.match(diagnostics, /EvidenceEnvelopeCard/);
  assert.match(diagnostics, /返回当前对象工作台/);
  assert.match(diagnostics, /无法找到指定对象，没有显示其他对象的结果/);
  assert.doesNotMatch(diagnostics, /apiRequest\(|CandidateDecisionBar|async function publishRevision|async function decideCandidate/);
  assert.doesNotMatch(diagnostics, /id="studio-canonical"|id="studio-preview"/);
});

test("Knowledge Studio inherits editorial tokens and collapses on narrow screens", async () => {
  const styles = await readFile(stylesUrl, "utf8");

  assert.match(styles, /\[data-ui-scope="editorial-v2"\] \.knowledge-studio/);
  assert.match(styles, /var\(--stl2-paper-strong\)/);
  assert.match(styles, /var\(--stl2-line\)/);
  assert.match(styles, /@media \(max-width: 760px\)[\s\S]*\.knowledge-studio-layout/);
  assert.match(styles, /@media \(max-width: 760px\)[\s\S]*grid-template-columns: 1fr/);
  assert.match(styles, /\.knowledge-studio-section-nav/);
  assert.match(styles, /\.knowledge-studio-object-types/);
});

test("published subdiscipline edits remain revision drafts until explicit publication", async () => {
  const [taxonomyEditor, lifecycle] = await Promise.all([
    readFile(taxonomyEditorUrl, "utf8"),
    readFile(lifecycleUrl, "utf8"),
  ]);

  assert.match(taxonomyEditor, /saved\.editorial_revision/);
  assert.match(taxonomyEditor, /读者页面未改变/);
  assert.match(taxonomyEditor, /editorial_status: draftOnly \? \(editing\?\.editorial_status \?\? "draft"\)/);
  assert.match(lifecycle, /LifecycleRevisionResponse/);
  assert.match(lifecycle, /下线草稿已保存/);
  assert.match(lifecycle, /内容管理中预览，再确认发布/);
});

test("Reading Path keeps explicit learning goals and prerequisites inside revisions", async () => {
  const readingPathEditor = await readFile(readingPathEditorUrl, "utf8");

  assert.match(readingPathEditor, /learning_goal/);
  assert.match(readingPathEditor, /prerequisite/);
  assert.match(readingPathEditor, /学习目标/);
  assert.match(readingPathEditor, /前置要求/);
  assert.match(readingPathEditor, /saved\.editorial_revision/);
  assert.match(readingPathEditor, /确认发布后更新公开页面/);
  assert.match(readingPathEditor, /draft_stage_groups/);
  assert.match(readingPathEditor, /撤回草稿/);
});

test("protected knowledge preview renders the same six public detail components", async () => {
  const [preview, previewPage, ...publicPages] = await Promise.all([
    readFile(knowledgePreviewUrl, "utf8"),
    readFile(knowledgePreviewPageUrl, "utf8"),
    ...publicPageUrls.map((url) => readFile(url, "utf8")),
  ]);
  const components = [
    "DisciplinePublicView",
    "SubdisciplinePublicView",
    "KnowledgeNodePublicView",
    "ReadingPathPublicView",
    "ScholarPublicView",
    "TopicPublicView",
  ];
  for (const [index, component] of components.entries()) {
    assert.match(preview, new RegExp(component));
    assert.match(publicPages[index], new RegExp(component));
  }
  assert.match(preview, /\/catalog\/admin\/knowledge-preview\//);
  assert.match(preview, /admin-knowledge-page-preview-body" inert/);
  assert.match(preview, /预览内的保存、询问、Reader 和跨页链接均已停用/);
  assert.match(previewPage, /robots: \{ index: false, follow: false \}/);
});
