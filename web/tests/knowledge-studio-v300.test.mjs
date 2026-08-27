import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const studioUrl = new URL("../components/knowledge-workspace.tsx", import.meta.url);
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

test("Knowledge Studio is the primary knowledge entry and reuses specialist editors", async () => {
  const [studio, shell, nodeEditor, taxonomyEditor, readingPathEditor] = await Promise.all([
    readFile(studioUrl, "utf8"),
    readFile(shellUrl, "utf8"),
    readFile(nodeEditorUrl, "utf8"),
    readFile(taxonomyEditorUrl, "utf8"),
    readFile(readingPathEditorUrl, "utf8"),
  ]);

  assert.match(shell, /\["\/admin\/knowledge", Sparkles, "Knowledge Studio"\]/);
  assert.match(studio, /href="\/admin\/theories"/);
  assert.match(studio, /href="\/admin\/scholars"/);
  assert.match(studio, /href="\/admin\/topics"/);
  assert.match(studio, /进入专门编辑器/);
  assert.match(nodeEditor, /search\.get\("node"\)/);
  assert.match(nodeEditor, /已从 Knowledge Studio 打开这个规范节点/);
  assert.match(taxonomyEditor, /searchParams\.get\("subdiscipline"\)/);
  assert.match(taxonomyEditor, /已从 Knowledge Studio 打开这个子学科/);
  assert.match(readingPathEditor, /searchParams\.get\("path"\)/);
  assert.match(readingPathEditor, /已从 Knowledge Studio 打开这条阅读路径/);
});

test("Knowledge Studio presents every required evidence-led object section", async () => {
  const studio = await readFile(studioUrl, "utf8");

  for (const label of ["正式内容", "关系", "Evidence", "Claims", "AI/Research 候选", "EditorialRevision", "前台影响", "Preview"]) {
    assert.match(studio, new RegExp(label));
  }
  for (const objectType of ["theory", "concept", "debate", "scholar", "discipline", "subdiscipline", "topic", "reading_path", "work"]) {
    assert.match(studio, new RegExp(`${objectType}:`));
  }
  assert.match(studio, /DerivedClaim · Shadow/);
  assert.match(studio, /不会自动写入正式知识/);
  assert.match(studio, /EvidenceEnvelopeCard/);
  assert.match(studio, /实际前台位置/);
  assert.match(studio, /impact\?\.projection_states/);
  assert.match(studio, /impact\?\.modules/);
  assert.match(studio, /当前 API 未提供 dependency 和 projection 元数据/);
  assert.match(studio, /published_changes_require_revision/);
  assert.match(studio, /确认发布此修订/);
  assert.match(studio, /onPublishRevision/);
  assert.match(studio, /Knowledge Growth/);
  assert.match(studio, /knowledge_update_suggestions/);
  assert.match(studio, /为什么现在处理/);
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
  for (const feature of ["前台内容完整度", "Knowledge Growth", "Evidence", "Claims", "Revision 与 Preview", "前台影响与投影"]) {
    assert.match(panel, new RegExp(feature));
  }
  assert.match(panel, /CandidateDecisionBar/);
  assert.match(panel, /EvidenceEnvelopeCard/);
  assert.match(panel, /\/catalog\/admin\/knowledge-workspace\//);
});

test("Knowledge Studio requests a bounded selected-object read model", async () => {
  const studio = await readFile(studioUrl, "utf8");

  assert.match(studio, /limit: "40"/);
  assert.match(studio, /params\.set\("selected_type", selected\.type\)/);
  assert.match(studio, /params\.set\("selected_id", selected\.id\)/);
  assert.match(studio, /\/catalog\/admin\/knowledge-workspace\//);
  assert.match(studio, /payload\.new_authority\.slice\(0, 20\)/);
  assert.match(studio, /subdiscipline: "子学科"/);
  assert.match(studio, /reading_path: "阅读路径"/);
  assert.match(studio, /work: "重要作品"/);
  assert.match(studio, /studio\.object_types\.map/);
  assert.match(studio, /aria-label="知识对象导航"/);
  assert.match(studio, /studio\.selection_error/);
});

test("Knowledge Studio distinguishes empty sections from backend capabilities that are not connected", async () => {
  const studio = await readFile(studioUrl, "utf8");

  for (const state of [
    "尚未建立正式关系",
    "当前对象类型尚未接通关系汇总",
    "尚无人工采用的策展命题",
    "当前对象类型尚未接通 CuratedClaim 汇总",
    "本页不会伪造预览",
    "统一人工决定",
  ]) assert.match(studio, new RegExp(state));

  assert.match(studio, /CandidateDecisionBar/);
  assert.match(studio, /generated_candidates/);

  for (const sectionId of ["studio-canonical", "studio-candidates", "studio-growth", "studio-evidence", "studio-claims", "studio-relations", "studio-revisions", "studio-impact", "studio-preview"]) {
    assert.match(studio, new RegExp(sectionId));
  }
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
  assert.match(taxonomyEditor, /正式页面尚未改变/);
  assert.match(taxonomyEditor, /editing\?\.editorial_status === "published"/);
  assert.match(lifecycle, /LifecycleRevisionResponse/);
  assert.match(lifecycle, /已建立 Revision/);
  assert.match(lifecycle, /Knowledge Studio 预览并确认发布/);
});

test("Reading Path keeps explicit learning goals and prerequisites inside revisions", async () => {
  const readingPathEditor = await readFile(readingPathEditorUrl, "utf8");

  assert.match(readingPathEditor, /learning_goal/);
  assert.match(readingPathEditor, /prerequisite/);
  assert.match(readingPathEditor, /学习目标/);
  assert.match(readingPathEditor, /前置要求/);
  assert.match(readingPathEditor, /saved\.editorial_revision/);
  assert.match(readingPathEditor, /正式页面尚未改变/);
  assert.match(readingPathEditor, /draft_stage_groups/);
  assert.match(readingPathEditor, /下线草稿/);
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
