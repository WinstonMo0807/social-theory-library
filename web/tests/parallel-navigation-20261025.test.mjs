// Deferred acceptance; deliberately not run during implementation.
import assert from "node:assert/strict";
import test from "node:test";
import { parallelEvidenceHref, parallelFocusMatches, parallelSourceMatches } from "../lib/api/parallel-navigation.ts";

const source = { source_status: "available", asset_id: "source-file", document_revision_id: "source-revision", pdf_page: 17, evidence_span_id: "source-span" };
const target = { state: "available", asset_id: "translation-file", document_revision_id: "translation-revision" };

test("handoff pins each file revision without assuming matching page numbers", () => {
  const url = new URL(parallelEvidenceHref(source, target), "https://library.invalid");
  assert.equal(url.pathname, "/reader/source-file");
  for (const [key, value] of Object.entries({ mode: "parallel", page: "17", revision: "source-revision", focus: "source-span", right_asset: "translation-file", right_revision: "translation-revision" })) assert.equal(url.searchParams.get(key), value);
  assert.equal(url.searchParams.has("right_page"), false);
  assert.equal(parallelEvidenceHref({ ...source, source_status: "unavailable" }, target), "");
});

test("multianchor links use the first exact anchor and carry its subrange", () => {
  const anchor = { ...source, evidence_span_id: undefined, selection_start: 110, selection_end: 165 };
  const url = new URL(parallelEvidenceHref({ ...source, anchors: [anchor, { ...source, pdf_page: 18 }] }), "https://library.invalid");
  assert.equal(url.searchParams.get("focus"), "source-file:17:range:110:165");
  assert.equal(parallelSourceMatches(target, target.asset_id, "old-revision"), false);
  assert.equal(parallelSourceMatches(target, target.asset_id, target.document_revision_id), true);
});

test("subrange focus matches the containing paragraph and rejects unrelated identities", () => {
  const segment = { id: "paragraph", reference: { ...source, evidence_span_id: undefined, selection_start: 100, selection_end: 200 } };
  assert.equal(parallelFocusMatches(segment, "source-file:17:range:110:165"), true);
  for (const focus of ["source-file:18:range:110:165", "other:17:range:110:165", "source-file:17:range:200:240", "source-file:17:range:150:110", "source-file:17:range:110:165:extra", ""]) assert.equal(parallelFocusMatches(segment, focus), false);
  assert.equal(parallelFocusMatches({ id: "span-row", reference: source }, "source-span"), true);
  assert.equal(parallelFocusMatches({ id: "span-row", reference: source }, "other-span"), false);
});
