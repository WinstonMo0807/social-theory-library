import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { ApiRequestError } from "../lib/api.ts";
import { canKeepDiscoveryContext, discoveryCoverageRows, readDiscoveryContext, readDiscoverySearch } from "../lib/api/discovery.client.ts";
import { privateRequest, readResearchRecord, retryResearchTurn } from "../lib/api/research.client.ts";
import { availableEvidenceAnchors } from "../lib/api/research-navigation.ts";
import { readerReturnPath } from "../lib/api/reader-failure.ts";
import { pollBudgetExpired, taskPollDelay, TASK_POLL_BUDGET_MS } from "../lib/api/task-polling.ts";
import { validateReaderPage } from "../components/reader/use-reader-document.ts";
import { validateReaderFocus, validateReaderSearch } from "../components/reader/use-reader-search.ts";
import { buildReaderPageOverlays } from "../components/reader/use-reader-page-overlays.ts";

const reference = { asset_id: "asset-a", document_revision_id: "revision-a", pdf_page: 2, source_status: "available", evidence_span_id: "span-a" };
const passage = { id: "indexed-a", asset_id: "asset-a", document_revision_id: "revision-a", excerpt: "Synthetic text", pdf_page: 2 };
function mockFetch(t, callback) {
  const original = globalThis.fetch;
  globalThis.fetch = callback;
  t.after(() => { globalThis.fetch = original; });
}

test("partial, failed, canceled and paused tasks stop despite a stale polling hint; plan enhancement is independent", () => {
  for (const status of ["partial", "completed", "succeeded", "failed", "canceled", "cancelled", "paused", "unavailable"]) {
    assert.equal(taskPollDelay({ status, poll_after_ms: 2000 }), null, status);
  }
  for (const status of ["queued", "pending", "running"]) assert.equal(taskPollDelay({ status, poll_after_ms: 1500 }), 1500);
  assert.equal(taskPollDelay({ status: "completed", enhancement_status: "queued", poll_after_ms: 2000 }), 2000);
  assert.equal(taskPollDelay({ status: "running", poll_after_ms: Infinity }), null);
  assert.equal(taskPollDelay({ status: "running", poll_after_ms: null }), null);
  assert.equal(taskPollDelay({ status: "running", poll_after_ms: 1 }), 1000);
  assert.equal(pollBudgetExpired(1234, 1234 + TASK_POLL_BUDGET_MS - 1), false);
  assert.equal(pollBudgetExpired(1234, 1234 + TASK_POLL_BUDGET_MS), true);
});

test("coverage separates OCR-unready holdings from fully indexed eligible holdings and unknown counts", () => {
  const rows = discoveryCoverageRows({ published_editions: 7, bibliographic_editions: 0, text_pending_editions: 3,
    eligible_editions: 4, indexed_editions: 4, vector_editions: 4, pending_editions: 0, index_pending_editions: 0, vector_pending_editions: 0, partial: true });
  const byKey = Object.fromEntries(rows.map(row => [row.key, row]));
  assert.equal(byKey.published_editions.value, 7);
  assert.equal(byKey.text_pending_editions.value, 3);
  assert.equal(byKey.eligible_editions.label, "全文已具备资格");
  assert.equal(byKey.indexed_editions.value, 4);
  assert.equal(byKey.bibliographic_editions.value, 0);
  assert.equal(byKey.pending_editions, undefined);
  assert.deepEqual(discoveryCoverageRows(undefined), []);
  assert.deepEqual(discoveryCoverageRows({ pending_editions: 2 }), [{ key: "pending_editions", label: "等待索引更新", value: 2 }]);
});

test("Discovery revalidation invalidates removed or replaced context while preserving backend partial state", async t => {
  const calls = [];
  mockFetch(t, async (url, options) => {
    calls.push({ url, options });
    if (String(url).includes("context/")) return Response.json({ detail: "来源已撤回" }, { status: 404 });
    return Response.json({ id: "session-a", status: "partial", passages: [], source_changed: true,
      coverage_summary: { text_pending_editions: 3, partial: true }, poll_after_ms: null });
  });
  const result = await readDiscoverySearch("session-a", "synthetic-capability", { limit: 3 });
  assert.equal(result.status, "partial");
  assert.equal(result.coverage_summary.text_pending_editions, 3);
  assert.equal(canKeepDiscoveryContext(passage, result), false);
  assert.equal(canKeepDiscoveryContext(passage, { passages: [{ ...passage }], source_changed: false }), true);
  assert.equal(canKeepDiscoveryContext(passage, { passages: [{ ...passage, document_revision_id: "revision-b" }] }), false);
  assert.equal(canKeepDiscoveryContext(passage, { passages: [{ ...passage, excerpt: "changed text" }] }), false);
  await assert.rejects(readDiscoveryContext("session-a", "synthetic-capability", "indexed-a"), error => error instanceof ApiRequestError && error.status === 404);
  assert.ok(calls.every(call => call.options.cache === "no-store" && call.options.headers.get("X-Discovery-Token") === "synthetic-capability"));
});

test("private research rereads current source eligibility and preserves human decisions on unavailable evidence", async t => {
  let calls = 0;
  mockFetch(t, async () => Response.json({ id: "turn-a", revision: 5, status: "partial", poll_after_ms: null,
    data: { result_refs: [{ ...reference, source_status: calls++ ? "source_changed" : "available" }],
      analysis: [{ id: "judgment-a", decision: { relation: "qualification", note: "Synthetic human decision" } }] } }));
  const first = await readResearchRecord("research-turns", "turn-a");
  assert.equal(availableEvidenceAnchors(first.data.result_refs[0], "asset-a", "revision-a").length, 1);
  const updated = await readResearchRecord("research-turns", "turn-a");
  assert.deepEqual(availableEvidenceAnchors(updated.data.result_refs[0], "asset-a", "revision-a"), []);
  assert.deepEqual(updated.data.analysis, first.data.analysis);
  assert.equal(taskPollDelay(updated), null);
});

test("research retry failures propagate, and caller-owned idempotency and revision survive an ambiguous retry", async t => {
  const calls = [];
  mockFetch(t, async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    if (calls.length > 2) return Response.json({ detail: "修订已变化，保留输入" }, { status: 409 });
    return calls.length === 1 ? Response.json({ detail: "调度状态暂不可读取" }, { status: 503 })
      : Response.json({ id: "turn-b", revision: 1, status: "queued", data: {}, poll_after_ms: 2000 });
  });
  const command = { expected_revision: 5, request_id: "6d761e25-1ae3-412a-b3b7-ebee74728f97" };
  await assert.rejects(retryResearchTurn("turn-a", command), error => error.status === 503);
  const result = await retryResearchTurn("turn-a", command);
  assert.equal(result.id, "turn-b");
  assert.equal(result.status, "queued");
  assert.deepEqual(calls[0], calls[1]);
  await assert.rejects(retryResearchTurn("turn-a", command), error => error.status === 409 && /保留输入/.test(error.message));
});

test("Reader rejects wrong file, wrong page, changed revision and missing published text before caching", () => {
  const page = { page_id: "page-a", asset_id: "asset-a", document_revision_id: "revision-a", page_index: 2, text: "Synthetic original" };
  assert.equal(validateReaderPage(page, "asset-a", "revision-a", 2), page);
  for (const change of [{ asset_id: "asset-b" }, { page_index: 3 }, { document_revision_id: "revision-b" }, { document_revision_id: null }, { document_revision_id: undefined }]) {
    assert.throws(() => validateReaderPage({ ...page, ...change }, "asset-a", "revision-a", 2), error => error.status === 409);
  }
});

test("Reader focus requires same revision and explicit geometry; legacy URLs retain safe page navigation", () => {
  const focus = { id: "span-a", asset_id: "asset-a", document_revision_id: "revision-a", page_index: 2, bbox: [10, 20, 30, 40] };
  assert.deepEqual(validateReaderFocus(focus, "asset-a", "revision-a").bbox, []);
  assert.deepEqual(validateReaderFocus({ ...focus, coordinate_space: "pymupdf_unrotated" }, "asset-a", "revision-a").bbox, []);
  assert.deepEqual(validateReaderFocus({ ...focus, normalized_bbox: [.1, .2, .3, .4], geometry_status: "validated" }, "asset-a", "revision-a").normalized_bbox, [.1, .2, .3, .4]);
  assert.throws(() => validateReaderFocus(focus, "asset-a", "revision-b"), error => error.status === 409);
  assert.throws(() => validateReaderFocus({ ...focus, page_index: 0 }, "asset-a", "revision-a"), error => error.status === 409);
  const matches = [{ page_index: 2, highlights: [{ bbox: focus.bbox }], blocks: [] }];
  assert.deepEqual(validateReaderSearch({ asset_id: "asset-a", document_revision_id: "revision-a", matches }, "asset-a", "revision-a"), matches);
  assert.deepEqual(validateReaderSearch({ matches }, "asset-a", "revision-a")[0].highlights, []);
  assert.throws(() => validateReaderSearch({ asset_id: "asset-b", matches }, "asset-a", "revision-a"), error => error.status === 409);
});

test("research anchor overlays require server-validated geometry and cannot infer it from page text source", () => {
  const anchor = { id: "span-a", asset_id: "asset-a", page_index: 2, width: 500, height: 700, bbox: [10, 20, 30, 40], text_source: "embedded" };
  const options = { annotations: [], focusedAnnotationId: "", pagePayloads: {}, passageFocus: null, researchAnchors: [anchor], query: "", searchMatches: [] };
  assert.deepEqual(buildReaderPageOverlays(options)[2].highlights, []);
  assert.deepEqual(buildReaderPageOverlays({ ...options, researchAnchors: [{ ...anchor, coordinate_space: "pymupdf_unrotated" }] })[2].highlights, []);
  const explicit = buildReaderPageOverlays({ ...options, researchAnchors: [{ ...anchor, normalized_bbox: [.1, .2, .3, .4], geometry_status: "validated" }] })[2].highlights;
  assert.equal(explicit.length, 1);
  assert.deepEqual(explicit[0].normalized_bbox, [.1, .2, .3, .4]);
});

test("private reads honor caller cancellation and keep a bounded request signal", async t => {
  mockFetch(t, async (_url, options) => {
    assert.equal(options.cache, "no-store");
    assert.ok(options.signal instanceof AbortSignal);
    return await new Promise((_resolve, reject) => options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true }));
  });
  const controller = new AbortController();
  const pending = privateRequest("/reading/research-turns/turn-a/", { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, error => error instanceof ApiRequestError && error.status === 0);
});

test("login return retains page, formal revision, research identity and nested return position", () => {
  const path = readerReturnPath("asset-a", { page: "25", q: "农业组织化", revision: "revision-a", research_project: "project-a",
    research_turn: "turn-a", reference: "span-a", return_to: "/explore/opinions?q=农业组织化&position=8" });
  const login = new URL(`/login?${new URLSearchParams({ next: path })}`, "https://library.invalid");
  const restored = new URL(login.searchParams.get("next"), login);
  assert.equal(restored.pathname, "/reader/asset-a");
  assert.equal(restored.searchParams.get("page"), "25");
  assert.equal(restored.searchParams.get("research_turn"), "turn-a");
  assert.equal(restored.searchParams.get("revision"), "revision-a");
  assert.equal(restored.searchParams.get("return_to"), "/explore/opinions?q=农业组织化&position=8");
});

test("strict generated Reader contract includes formal source identity for focus, search, manifest and page", async () => {
  const schema = JSON.parse(await readFile(new URL("../../api/openapi/schema.json", import.meta.url), "utf8"));
  const definitions = schema.components.schemas;
  for (const name of ["ReaderFocus", "ReaderDocumentSearch", "ReaderManifest", "ReaderPageContent"]) {
    assert.ok(definitions[name]?.properties.asset_id, `${name}.asset_id`);
    assert.ok(definitions[name]?.properties.document_revision_id, `${name}.document_revision_id`);
  }
  for (const name of ["ReaderFocus", "ReaderTextBlock"]) {
    assert.ok(definitions[name]?.properties.normalized_bbox, `${name}.normalized_bbox`);
    assert.ok(definitions[name]?.properties.geometry_status, `${name}.geometry_status`);
  }
  assert.ok(definitions.ReaderPageContent.properties.geometry);
  assert.ok(definitions.ReaderSearchMatch.properties.geometry);
});
