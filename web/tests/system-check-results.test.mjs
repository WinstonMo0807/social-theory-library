import assert from "node:assert/strict";
import test from "node:test";
import { systemCheckResults } from "../components/admin-system-health.tsx";

const connected = { checked_at: "2026-10-10T00:00:00Z", components: Object.fromEntries(["storage", "meilisearch", "public_catalog_freshness"].map(key => [key, { available: true, configured: true, last_error: "", last_successful_check: null, detail: "" }])) };
const selfTest = { started_at: "2026-10-10T00:01:00Z", duration_seconds: 1, all_available: true, steps: { pdf_parse: { available: true }, page_retrieval: { available: true }, ocr: { available: true }, meilisearch_write_search: { available: true, probe_cleaned: true }, embedding: { available: true } } };

test("connected services do not mark queries or public page visits as passed", () => {
  const before = structuredClone(connected);
  const rows = systemCheckResults(connected, null);
  assert.deepEqual(rows.map(row => row.available), [true, null, null]);
  assert.equal(rows[0].status, "抽查可读取");
  assert.equal(rows[1].status, "检索待测");
  assert.equal(rows[2].status, "访问待核实");
  assert.deepEqual(connected, before);
});

test("actual self-test steps and cleanup determine results while visits remain unverified", () => {
  const earlier = structuredClone(connected);
  earlier.components.public_catalog_freshness.available = false;
  assert.deepEqual(systemCheckResults(earlier, selfTest).map(row => row.available), [true, true, null]);
  const failed = structuredClone(selfTest);
  failed.steps.ocr = { available: false, error: "OCR check failed" };
  failed.steps.meilisearch_write_search.probe_cleaned = false;
  const rows = systemCheckResults(connected, failed);
  assert.deepEqual(rows.map(row => row.available), [false, false, null]);
  assert.match(rows[0].detail, /OCR check failed/);
  assert.match(rows[1].detail, /清理未完成/);
  assert.equal(failed.all_available, true);
});

test("missing steps and absent cleanup evidence stay unknown", () => {
  assert.deepEqual(systemCheckResults(null, null).map(row => row.available), [null, null, null]);
  const incomplete = structuredClone(selfTest);
  delete incomplete.steps.ocr;
  delete incomplete.steps.meilisearch_write_search.probe_cleaned;
  assert.deepEqual(systemCheckResults(connected, incomplete).map(row => row.available), [null, null, null]);
});
