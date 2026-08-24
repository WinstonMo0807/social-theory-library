import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const studioUrl = new URL("../components/knowledge-workspace.tsx", import.meta.url);
const shellUrl = new URL("../components/admin-shell.tsx", import.meta.url);
const nodeEditorUrl = new URL("../components/theory-system-admin.tsx", import.meta.url);
const taxonomyEditorUrl = new URL("../components/knowledge-admin.tsx", import.meta.url);
const lifecycleUrl = new URL("../components/entity-lifecycle-actions.tsx", import.meta.url);
const readingPathEditorUrl = new URL("../components/admin/curation/reading-path-workbench.tsx", import.meta.url);
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
  assert.match(studio, /href="\/admin\/theory-nodes"/);
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

  for (const label of ["正式内容", "关系", "Evidence", "Claims", "AI candidates", "EditorialRevision", "前台影响", "Preview"]) {
    assert.match(studio, new RegExp(label));
  }
  for (const objectType of ["theory", "concept", "debate", "scholar", "subdiscipline", "topic", "reading_path", "work"]) {
    assert.match(studio, new RegExp(`${objectType}:`));
  }
  assert.match(studio, /DerivedClaim · Shadow/);
  assert.match(studio, /不会自动写入正式知识/);
  assert.match(studio, /查看原文/);
  assert.match(studio, /printed_page_label/);
  assert.match(studio, /实际前台位置/);
  assert.match(studio, /projection_states/);
  assert.match(studio, /published_changes_require_revision/);
  assert.match(studio, /确认发布此修订/);
  assert.match(studio, /onPublishRevision/);
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
});

test("Knowledge Studio inherits editorial tokens and collapses on narrow screens", async () => {
  const styles = await readFile(stylesUrl, "utf8");

  assert.match(styles, /\[data-ui-scope="editorial-v2"\] \.knowledge-studio/);
  assert.match(styles, /var\(--stl2-paper-strong\)/);
  assert.match(styles, /var\(--stl2-line\)/);
  assert.match(styles, /@media \(max-width: 760px\)[\s\S]*\.knowledge-studio-layout/);
  assert.match(styles, /@media \(max-width: 760px\)[\s\S]*grid-template-columns: 1fr/);
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
