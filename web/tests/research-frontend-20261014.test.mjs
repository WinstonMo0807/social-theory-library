import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { nextCollectionPath, readAllPages } from "../lib/api/read-all-pages.ts";
import { prepareOutline, filterOutline, outlinePosition } from "../lib/api/document-outline.ts";
import { availableEvidenceAnchors, evidenceIdentity, researchReaderHref, safeResearchReturn, readerContextHref } from "../lib/api/research-navigation.ts";
import { passageReference, changeResearchSelection, createCitationAudit, readCitationOCR, commandReadingPlan, updateResearchSubclaims } from "../lib/api/research.client.ts";
import { prepareLocalResearchTransfer, readLocalResearchSnapshot } from "../lib/api/local-research-transfer.ts";
import { adoptOutline, changePlacements, actOnEditorialAssistance } from "../lib/api/curation-workspace.client.ts";

test("pagination reads records after 24 and never forwards a supplied host", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return Response.json(calls.length === 1
      ? { count: 25, results: Array.from({ length: 24 }, (_, id) => ({ id })), next: "https://untrusted.invalid/api/reading/annotations/?asset=a&p=2" }
      : { count: 25, results: [{ id: 24 }], next: null });
  };
  try {
    const rows = await readAllPages("/reading/annotations/?asset=a", "cookie-session");
    assert.equal(rows.length, 25); assert.equal(rows[24].id, 24);
    assert.equal(calls[1][0], "/api/reading/annotations/?asset=a&p=2");
    assert.equal(calls[1][1].cache, "no-store");
    assert.ok(calls[1][1].signal instanceof AbortSignal);
    assert.equal(calls[1][1].headers.get("Authorization"), null);
  } finally { globalThis.fetch = original; }
});

test("pagination rejects an endpoint switch and repeating pages instead of silently truncating", async () => {
  assert.throws(() => nextCollectionPath("/reading/annotations/", "/api/auth/me/"), /不同/);
  assert.throws(() => nextCollectionPath("/reading/annotations/?asset=a", "/api/reading/annotations/?asset=b&p=2"), /范围/);
  const original = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ results: [{ id: 1 }], next: "/api/reading/annotations/?p=1" });
  try { await assert.rejects(readAllPages("/reading/annotations/?p=1", "cookie-session"), /完整读取/); }
  finally { globalThis.fetch = original; }
  const aborted = new AbortController(); aborted.abort();
  await assert.rejects(readAllPages("/reading/annotations/", "cookie-session", aborted.signal), { name: "AbortError" });
});

test("outline identities keep same-page duplicates and ancestor-aware search", () => {
  const nodes = prepareOutline([
    { id: "root", index: 3, chapter_title: "第一部分", printed_label: "1", level: 1 },
    { id: "a", parent_id: "root", index: 3, chapter_title: "组织", printed_label: "1", level: 2 },
    { id: "b", parent_id: "root", index: 3, chapter_title: "组织", printed_label: "1", level: 2 },
    { id: "c", index: 8, chapter_title: "附录", printed_label: "vi", level: 1 },
  ]);
  assert.deepEqual(filterOutline(nodes, "", new Set(["root"])).map(row => row.id), ["root", "c"]);
  assert.deepEqual(filterOutline(nodes, "组织", new Set(["root"])).map(row => row.id), ["root", "a", "b"]);
  assert.deepEqual(filterOutline(nodes, "vi", new Set()).map(row => row.id), ["c"]);
  assert.equal(filterOutline(nodes, "missing", new Set()).length, 0);
});

test("outline positions respect coordinate spaces and rotated native source bounds", () => {
  assert.deepEqual(outlinePosition({ normalized_position: [.4, .6] }), [.4, .6]);
  assert.deepEqual(outlinePosition({ pdf_position: [40, 60], coordinate_space: "pymupdf_toc", page_geometry: { pdf_width: 100, pdf_height: 200 } }), [.4, .3]);
  assert.equal(outlinePosition({ pdf_position: [40, 60], coordinate_space: "unknown", page_geometry: { pdf_width: 100, pdf_height: 200 } }), undefined);
  const source = { bbox: [20, 60, 40, 80], source_width: 200, source_height: 100, coordinate_space: "pymupdf_unrotated" };
  assert.deepEqual(outlinePosition({ source_locator: source, page_geometry: { rotation: 90, cropbox: [0, 0, 100, 200] } }), [.6, .2]);
  assert.deepEqual(outlinePosition({ source_locator: source, page_geometry: { rotation: 270, cropbox: [0, 0, 100, 200] } }), [.3, .6]);
  assert.equal(outlinePosition({ source_locator: source, page_geometry: { rotation: 90 } }), undefined);
  assert.equal(outlinePosition({ source_locator: { ...source, geometry_status: "unknown" }, page_geometry: { rotation: 90, cropbox: [0, 0, 100, 200] } }), undefined);
});

const anchor = { evidence_span_id: "span", asset_id: "asset", document_revision_id: "rev", pdf_page: 3, source_status: "available" };
test("multi-anchor identity matches the server and refuses mixed or stale sources", async () => {
  const second = { ...anchor, evidence_span_id: "span-2", pdf_page: 4 };
  const reference = { ...anchor, anchors: [anchor, second] };
  assert.equal(await evidenceIdentity(reference), `anchors:${createHash("sha256").update("span|span-2").digest("hex")}`);
  assert.equal(availableEvidenceAnchors(reference, "asset", "rev").length, 2);
  assert.equal(availableEvidenceAnchors(reference, "asset", "new-rev").length, 0);
  assert.equal(availableEvidenceAnchors({ ...reference, anchors: [anchor, { ...second, source_status: "unavailable" }] }, "asset", "rev").length, 0);
  const href = await researchReaderHref(reference, { projectId: "project", returnTo: "/research/project?turn=t" });
  const url = new URL(href, "https://local.invalid");
  assert.equal(url.searchParams.get("revision"), "rev");
  assert.equal(url.searchParams.get("research_project"), "project");
  assert.equal(url.searchParams.get("return_to"), "/research/project?turn=t");
  assert.equal(safeResearchReturn("//outside.invalid"), "");
  assert.equal(safeResearchReturn("/admin/users"), "");
  assert.equal(safeResearchReturn("/research\\outside"), "");
});

const passage = { id: "discovery-result", evidence_span_id: "span", asset_id: "asset", document_revision_id: "rev", pdf_page: 3, work: { id: "work", title: "书" } };
test("Discovery selection uses an actual evidence identity, never a result-card id", () => {
  assert.equal(passageReference(passage).evidence_span_id, "span");
  assert.equal(passageReference({ ...passage, evidence_span_id: undefined }).evidence_span_id, undefined);
  assert.equal(passageReference(passage).document_revision_id, "rev");
});

test("local transfer preserves branching and source identity without deleting the old snapshot", () => {
  const store = { version: 1, comparison: { principle: "本人比较" }, research: [{ id: "local-research", title: "如何理解农业组织化", selected: [passage], active: "t2", turns: [
    { id: "t1", query: "农业组织化", scope: "all", selectedIds: [], results: [passage], created: "2026-10-14", status: "completed", notice: "" },
    { id: "t2", parent: "t1", query: "它的限定条件是什么", scope: "selected", selectedIds: [passage.id], results: [passage], created: "2026-10-14", status: "running", notice: "已有结果" },
  ] }] };
  const raw = JSON.stringify(store);
  let reads = 0;
  const snapshot = readLocalResearchSnapshot({ getItem: () => { reads++; return raw; } });
  const payload = prepareLocalResearchTransfer(snapshot.store, "local-research", "stable-request");
  assert.equal(reads, 1); assert.equal(snapshot.raw, raw); assert.equal(JSON.stringify(store), raw);
  assert.equal(payload.turns[1].parent_local_id, "t1");
  assert.deepEqual(payload.turns[1].scope.filters.work_ids, ["work"]);
  assert.equal(payload.turns[1].selected_references[0].evidence_span_id, "span");
  assert.ok(payload.notes.includes("本人比较")); assert.equal(payload.request_id, "stable-request");
  assert.throws(() => prepareLocalResearchTransfer({ ...store, research: [{ ...store.research[0], selected: [{ ...passage, document_revision_id: "" }] }] }, "local-research", "request"), /正式文件/);
});

test("private and admin mutations preserve exact revisions, request keys and route contracts", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push([url, options]); return Response.json({ id: "result" }); };
  try {
    await changeResearchSelection("project", { expected_revision: 7, action: "add", references: [anchor] });
    await commandReadingPlan("plan", { expected_revision: 3, action: "retry" });
    await updateResearchSubclaims("turn", { expected_revision: 2, subclaims: [{ id: "child", proposition: "农业组织化存在条件" }] });
    await readCitationOCR("audit", "page-1");
    await adoptOutline("asset", { expected_revision: 9, request_id: "request", revision_id: "revision", action: "restore" });
    await changePlacements("scholar", "scholar", { action: "move", item_id: "item", position: 1, expected_revision: "version", request_id: "same-request" });
    await actOnEditorialAssistance("issue", "job", { action: "adopt", edit_version: "edit-v", suggestion_ids: ["suggestion"] });
    assert.equal(calls[0][0], "/api/reading/research-projects/project/selections/");
    assert.equal(JSON.parse(calls[0][1].body).expected_revision, 7);
    assert.equal(calls[1][0], "/api/reading/reading-plans/plan/command/");
    assert.equal(calls[2][0], "/api/reading/research-turns/turn/subclaims/");
    assert.equal(calls[3][0], "/api/reading/citation-audits/audit/ocr/?unit_id=page-1");
    assert.equal(JSON.parse(calls[4][1].body).revision_id, "revision");
    assert.equal(JSON.parse(calls[5][1].body).request_id, "same-request");
    assert.equal(calls[6][0], "/api/catalog/admin/recommendation-issues/issue/assistant/job/");
    assert.ok(calls.every(([, options]) => options.cache === "no-store"));
    assert.ok(calls.every(([, options]) => options.signal instanceof AbortSignal));
  } finally { globalThis.fetch = original; }
});

test("citation upload uses multipart and keeps the explicit idempotency key", async () => {
  const original = globalThis.fetch;
  let sent;
  globalThis.fetch = async (url, options) => { sent = { url, options }; return Response.json({ id: "audit" }); };
  try {
    await createCitationAudit(new File(["content"], "manuscript.docx"), "same-request", "project");
    assert.equal(sent.options.headers.get("Content-Type"), null);
    assert.equal(sent.options.body.get("request_id"), "same-request");
    assert.equal(sent.options.body.get("file").name, "manuscript.docx");
    assert.equal(sent.options.body.get("project_id"), "project");
  } finally { globalThis.fetch = original; }
});

test("public and private reading return paths keep their scope without accepting external destinations", () => {
  for (const path of ["/topics/agriculture/evidence?page=2", "/theories/reading-paths/classics?stage=second", "/account/plans/plan"]) {
    assert.equal(safeResearchReturn(path), path);
    const url = new URL(readerContextHref("/reader/asset?page=8&revision=rev", { returnTo: path }), "https://library.invalid");
    assert.equal(url.searchParams.get("return_to"), path);
    assert.equal(url.searchParams.get("page"), "8");
  }
  for (const path of ["//outside.invalid", "/admin/users", "/topics/../../admin", "/theories/graph"]) assert.equal(safeResearchReturn(path), "");
  assert.equal(readerContextHref("https://outside.invalid/reader/asset", { returnTo: "/account" }), "");
  assert.equal(readerContextHref("/reader/../admin/users", {}), "");
});
