import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  bibliographyFields,
  dirtyFieldCount,
  mergeRemoteDrafts,
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
  assert.equal(stepFromHash("#knowledge", "file"), "knowledge");
  assert.equal(stepFromHash("#not-a-step", "bibliography"), "bibliography");
  assert.equal(
    workflowHashUrl("https://library.test/admin/intake/abc?q=1#file", "reader"),
    "/admin/intake/abc?q=1#reader",
  );
});

test("journal and book bibliography fields stay type-specific", () => {
  assert.deepEqual(
    bibliographyFields("journal_article"),
    ["publication_year", "journal_title", "volume", "issue", "page_range", "doi"],
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

test("section validation blocks continuation before backend save", () => {
  assert.deepEqual(
    validateWorkflowSection("work", { title: "", document_type: "book", language: "zh-CN" }),
    [{ field: "title", message: "请填写作品题名。" }],
  );
  assert.equal(
    validateWorkflowSection("classification", { confirmed: false })[0].field,
    "confirmed",
  );
  assert.equal(
    validateWorkflowSection("knowledge", { confirmed: true }).length,
    0,
  );
});

test("focus mode, contextual curation and publication choices use canonical routes", async () => {
  const [shell, editor, curation, reviewRoute, publicationRoute] = await Promise.all([
    readFile(new URL("../components/admin-shell.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/curation/work-curation-editor.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/review/[itemId]/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/publication/[itemId]/page.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(shell, /focusMode = \/\^\\\/admin/);
  assert.match(editor, /window\.history\.replaceState/);
  assert.match(editor, /发布并处理下一项/);
  assert.match(editor, /发布并留在当前项/);
  assert.match(editor, /beforeunload/);
  assert.match(curation, /reading-path-placements\/\$\{placement\.id\}/);
  assert.match(curation, /reading_path_id: selectedPath/);
  assert.match(curation, /stage_id: selectedStage/);
  assert.match(curation, /action: "pin"/);
  assert.match(reviewRoute, /#bibliography/);
  assert.match(publicationRoute, /#publication/);
});
