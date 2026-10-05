import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { normalizeEditorialRevision } from "../components/admin/workflow/workflow-types.ts";
import { preservingAdminRedirect } from "../lib/admin-route-context.ts";

import {
  bibliographyFields,
  dirtyFieldCount,
  dirtyFieldsAfterSave,
  invalidatedResearchFields,
  mergeRemoteDrafts,
  workflowFieldConflicts,
  resolveWorkflowConflicts,
  nextWorkflowStep,
  sectionPresentations,
  stepFromHash,
  validateWorkflowSection,
  withDirtyField,
  workflowHashUrl,
} from "../components/admin/workflow/workflow-state.ts";

const steps = [
  { key: "file", status: "complete" },
  { key: "work", status: "complete" },
  { key: "bibliography", status: "available" },
  { key: "contributors", status: "pending" },
  { key: "classification", status: "pending" },
  { key: "knowledge", status: "pending" },
  { key: "reader", status: "pending" },
  { key: "curation", status: "pending" },
  { key: "publication", status: "pending" },
];

test("save acknowledgement preserves edits typed while the request was in flight", () => {
  const submitted = Object.fromEntries(steps.map(({key})=>[key,{}]));
  submitted.work = {title:"提交时的题名", abstract:"已提交简介"};
  submitted.contributors = {items:[{display_name:"甲"}]};
  const current = structuredClone(submitted);
  current.work.title = "保存期间继续输入";
  current.bibliography.publisher = "保存期间补的出版社";
  current.contributors.items[0].display_name = "乙";
  const dirty = {work:["title","abstract"], bibliography:["publisher"], contributors:["items.0.display_name"]};
  const remaining = dirtyFieldsAfterSave(current,submitted,dirty);
  assert.deepEqual(remaining.work,["title"]);
  assert.deepEqual(remaining.bibliography,["publisher"]);
  assert.deepEqual(remaining.contributors,["items.0.display_name"]);
  const remote = structuredClone(submitted);
  remote.work.expected_updated_at = "new-version";
  const merged = mergeRemoteDrafts(current,remote,remaining);
  assert.equal(merged.work.title,"保存期间继续输入");
  assert.equal(merged.work.expected_updated_at,"new-version");
  assert.equal(merged.bibliography.publisher,"保存期间补的出版社");
  assert.equal(merged.contributors.items[0].display_name,"乙");
  assert.equal(submitted.work.title,"提交时的题名");
});

test("workflow payload preserves an editorial revision that can be published", () => {
  const revision = normalizeEditorialRevision({
    id: "revision-1",
    target_type: "work",
    target_id: "work-1",
    base_revision: 2,
    current_revision: 2,
    revision: 3,
    changed_fields: ["title", "bibliography"],
    status: "draft",
    has_conflict: false,
    publish_url: "/api/catalog/admin/editorial-revisions/revision-1/publish/",
  });

  assert.equal(revision?.id, "revision-1");
  assert.equal(revision?.status, "draft");
  assert.deepEqual(revision?.changed_fields, ["title", "bibliography"]);
  assert.match(revision?.publish_url ?? "", /publish/);
});

test("hybrid progressive workflow collapses completed steps and previews only the next step", () => {
  const presentation = sectionPresentations(steps, "bibliography");
  assert.equal(presentation.file, "summary");
  assert.equal(presentation.work, "summary");
  assert.equal(presentation.bibliography, "current");
  assert.equal(presentation.contributors, "preview");
  assert.equal(presentation.classification, "collapsed");
  assert.equal(nextWorkflowStep("bibliography", steps), "contributors");
});

test("workflow hash uses replaceable single-page step addresses", () => {
  assert.equal(stepFromHash("#knowledge", "file"), "curation");
  assert.equal(stepFromHash("#not-a-step", "bibliography"), "bibliography");
  assert.equal(
    workflowHashUrl("https://library.test/admin/intake/abc?q=1#file", "reader"),
    "/admin/intake/abc?q=1#reader",
  );
});

test("journal and book bibliography fields stay type-specific", () => {
  assert.deepEqual(
    bibliographyFields("journal_article"),
    ["publication_date", "publication_year", "journal_title", "volume", "issue", "page_range", "doi"],
  );
  assert.ok(bibliographyFields("book").includes("isbn13"));
  assert.ok(!bibliographyFields("book").includes("journal_title"));
  assert.equal(
    validateWorkflowSection("bibliography", { publication_year: 2026 }, "journal_article")[0].field,
    "journal_title",
  );
  assert.equal(
    validateWorkflowSection("bibliography", { publication_year: 2026, journal_title: "社会学研究" }, "journal_article").length,
    0,
  );
});

test("remote refresh preserves only locally dirty canonical fields", () => {
  const blank = () => ({ file: {}, work: {}, bibliography: {}, contributors: {}, classification: {}, knowledge: {}, reader: {}, curation: {}, publication: {} });
  const local = blank();
  local.work = { title: "未保存题名", language: "zh-CN" };
  local.bibliography = { publication_year: 2025 };
  const remote = blank();
  remote.work = { title: "服务器题名", language: "en" };
  remote.bibliography = { publication_year: 2026 };
  let dirty = withDirtyField({}, "work", "title");
  dirty = withDirtyField(dirty, "bibliography", "publication_year");
  const merged = mergeRemoteDrafts(local, remote, dirty);
  assert.equal(merged.work.title, "未保存题名");
  assert.equal(merged.work.language, "en");
  assert.equal(merged.bibliography.publication_year, 2025);
  assert.equal(dirtyFieldCount(dirty), 2);
});

test("draft title changes invalidate dependent bibliographic research without hiding unrelated fields", () => {
  const invalidated = invalidatedResearchFields({ work: ["title"] });
  assert.ok(invalidated.has("original_title"));
  assert.ok(invalidated.has("contributors"));
  assert.ok(invalidated.has("publisher"));
  assert.ok(invalidated.has("publication_date"));
  assert.ok(!invalidated.has("primary_disciplines"));
});

test("concurrent refresh requires a choice for overlapping edits and preserves unrelated remote updates", () => {
  const base = Object.fromEntries(steps.map(({ key }) => [key, {}]));
  base.work = { title: "原题名", abstract: "原简介", language: "zh-CN" };
  base.bibliography = { journal_contents: [{ title: "原论文" }], publisher: "原出版社" };
  const local = structuredClone(base);
  local.work.title = "本地题名";
  local.work.abstract = "本地简介";
  local.bibliography.journal_contents[0].title = "本地论文";
  const remote = structuredClone(base);
  remote.work.abstract = "他人简介";
  remote.work.language = "en";
  remote.bibliography.journal_contents[0].title = "他人论文";
  remote.bibliography.publisher = "新出版社";
  const dirty = { work: ["title", "abstract"], bibliography: ["journal_contents.0.title"] };
  const before = JSON.stringify({ local, remote, dirty, base });
  const conflicts = workflowFieldConflicts(local, remote, dirty, base);
  assert.deepEqual(conflicts.map(({ step, path }) => `${step}.${path}`), ["work.abstract", "bibliography.journal_contents.0.title"]);
  assert.throws(() => resolveWorkflowConflicts(local, remote, dirty, conflicts, { "work.abstract": "local" }), /逐项选择/);
  const resolved = resolveWorkflowConflicts(local, remote, dirty, conflicts, { "work.abstract": "local", "bibliography.journal_contents.0.title": "remote" });
  assert.equal(resolved.drafts.work.title, "本地题名");
  assert.equal(resolved.drafts.work.abstract, "本地简介");
  assert.equal(resolved.drafts.work.language, "en");
  assert.equal(resolved.drafts.bibliography.journal_contents[0].title, "他人论文");
  assert.equal(resolved.drafts.bibliography.publisher, "新出版社");
  assert.deepEqual(resolved.dirty, { ...Object.fromEntries(steps.map(({ key }) => [key, []])), work: ["title", "abstract"] });
  assert.equal(JSON.stringify({ local, remote, dirty, base }), before);
  // A rejected save must explicitly rebase even edits that were disjoint.
  assert.equal(workflowFieldConflicts(local, remote, dirty).length, 3);
  assert.equal(workflowFieldConflicts(remote, remote, dirty, base).length, 0);
});

test("section validation blocks continuation before backend save", () => {
  assert.deepEqual(
    validateWorkflowSection("work", { title: "", document_type: "book", language: "zh-CN" }),
    [{ field: "title", message: "请填写作品题名。" }],
  );
  assert.equal(validateWorkflowSection("classification", { confirmed: false }).length, 0);
  assert.equal(validateWorkflowSection("knowledge", { confirmed: false }).length, 0);
  assert.equal(
    validateWorkflowSection("knowledge", { confirmed: true }).length,
    0,
  );
  assert.equal(
    validateWorkflowSection("contributors", { items: [] }).length,
    0,
  );
  assert.equal(
    validateWorkflowSection("contributors", { items: [{ display_name: "", role: "translator", person_id: null }] }).length,
    0,
  );
  assert.deepEqual(
    validateWorkflowSection("contributors", { items: [{ display_name: "候选作者", role: "author", person_id: null }] }),
    [{ field: "items.0.person_id", message: "请为作者“候选作者”选择已有的人物；没有记录时点击下方“新建”。" }],
  );
});

test("contributor editor keeps unresolved candidates outside canonical rows", async () => {
  const [editor, fields] = await Promise.all([
    readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/forms/workflow-fields.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(editor, /label="作者" values=\{authorItems\} emptyValue=\{blank\("author"\)\}/);
  assert.match(editor, /label="译者" values=\{translatorItems\} create=\{\(\) => blank\("translator"\)\}/);
  assert.doesNotMatch(editor, /translatorItems\.length \? translatorItems : \[blank\("translator"\)\]/);
  assert.match(editor, /WorkflowFieldAssistant[^\n]*fieldName="author"/);
  assert.match(editor, /WorkflowFieldAssistant[^\n]*fieldName="translator"/);
  assert.match(editor, /person_id: person\?\.id \?\? null/);
  assert.match(fields, /showsEmptyValue/);
});

test("persistent navigation, contextual curation and publication choices use canonical routes", async () => {
  const [shell, editor, curation, reviewRoute, publicationRoute] = await Promise.all([
    readFile(new URL("../components/admin-shell.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/curation/work-curation-editor.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/review/[itemId]/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/publication/[itemId]/page.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(shell, /const focusMode = false/);
  assert.match(editor, /window\.history\.replaceState/);
  assert.match(editor, /发布并处理下一项/);
  assert.match(editor, /发布作品/);
  assert.match(editor, /发布并处理下一项/);
  assert.match(editor, /beforeunload/);
  assert.match(editor, /保存草稿并退出/);
  assert.match(editor, /不保存并退出/);
  assert.match(editor, /继续编辑/);
  assert.match(editor, /作品首次出版日期/);
  assert.match(editor, /本版本出版日期/);
  assert.match(editor, /保存草稿/);
  assert.match(editor, /发布前检查/);
  assert.match(editor, /发布作品/);
  assert.match(curation, /更多策展内容/);
  assert.match(editor, /理论传统与理论节点/);
  assert.match(curation, /学者与知识关系/);
  assert.match(curation, /相关争论在知识对象中继续策展/);
  assert.match(curation, /正式发布前只在当前草稿中使用/);
  assert.match(curation, /reading-path-placements\/\$\{placement\.id\}/);
  assert.match(curation, /reading_path_id: selectedPath/);
  assert.match(curation, /stage_id: selectedStage/);
  assert.match(curation, /action: "pin"/);
  assert.match(reviewRoute, /preservingAdminRedirect/);
  assert.match(publicationRoute, /preservingAdminRedirect/);
  const context = { edition: "edition-2", return_to: "/admin/review?page=2" };
  assert.equal(new URL(preservingAdminRedirect("/admin/intake/item-1", context, "bibliography"), "https://test.invalid").hash, "#bibliography");
  assert.equal(new URL(preservingAdminRedirect("/admin/intake/item-1", context, "publication"), "https://test.invalid").hash, "#publication");
});
