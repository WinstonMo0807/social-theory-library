import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { annotationReceiptMatches, useReaderRecords } from "../components/reader/use-reader-records.ts";
import { useReaderSearch } from "../components/reader/use-reader-search.ts";

// Synthetic hook state contracts. Authored for unified acceptance, not run in development.
const noop = () => {};

function RecordsProbe({ authenticated = true, owner = 17 }) {
  const records = useReaderRecords({
    assetId: "synthetic-asset", initialFocus: "", readerAuthenticated: authenticated, readerId: owner,
    page: 1, pagePayloads: {}, captureSelection: () => null,
    setSelectionTools: noop, setPage: noop, jumpToPage: noop, setLeftPanel: noop,
    setSidebarTab: noop, setGate: noop, setCopyStatus: noop, setCopyStatusState: noop,
  });
  return createElement("output", {
    "data-loading": records.recordsLoading,
    "data-ready": records.recordsReady,
    "data-stopped": records.recordsStopped,
    "data-count": records.annotations.length + records.bookmarks.length,
    "data-draft": records.annotationDraft === null ? "none" : "present",
  });
}

function SearchProbe({ query }) {
  const search = useReaderSearch({
    assetId: "synthetic-asset", documentRevisionId: "synthetic-revision",
    initialQuery: query, initialPassage: "", initialEvidence: "",
    requestPagePayload: noop, jumpToPage: noop,
  });
  return createElement("output", {
    "data-loading": search.searchLoading,
    "data-count": search.searchMatches.length,
    "data-error": search.searchError,
    "data-candidates": search.searchCandidatesOpen,
  });
}

test("private records start pending rather than asserting an empty personal library", () => {
  const markup = renderToStaticMarkup(createElement(RecordsProbe));
  assert.match(markup, /data-loading="true"/);
  assert.match(markup, /data-ready="false"/);
  assert.match(markup, /data-count="0"/);
  assert.match(markup, /data-draft="none"/);
});

test("an unauthenticated reader receives neither private records nor a stuck loading state", () => {
  const markup = renderToStaticMarkup(createElement(RecordsProbe, { authenticated: false }));
  assert.match(markup, /data-loading="false"/);
  assert.match(markup, /data-ready="false"/);
  assert.match(markup, /data-count="0"/);
});

test("a nonempty initial query is pending during debounce, while whitespace is idle", () => {
  const pending = renderToStaticMarkup(createElement(SearchProbe, { query: "测试词" }));
  assert.match(pending, /data-loading="true"/);
  assert.match(pending, /data-count="0"/);
  assert.match(pending, /data-error=""/);
  const idle = renderToStaticMarkup(createElement(SearchProbe, { query: " \t " }));
  assert.match(idle, /data-loading="false"/);
  assert.match(idle, /data-candidates="false"/);
});

test("an unknown save is confirmed only by its exact UUID, source, private content and selector", () => {
  const payload = {
    request_id: "20000000-0000-4000-8000-000000000001", asset: "synthetic-asset", page: "synthetic-page",
    kind: "note", quote: "合成测试原文", body: "合成测试笔记", tags: ["测试标签"], color: "yellow",
    selector: { type: "TextQuoteSelector", exact: "合成测试原文", page_index: 3, bboxes: [[1, 2, 3, 4]] },
  };
  const record = {
    id: payload.request_id, asset: payload.asset, page: payload.page, kind: payload.kind,
    quote: payload.quote, body_text: payload.body, tags: payload.tags, color: payload.color,
    // PostgreSQL JSONB may reorder object keys without changing the selector.
    selector: { bboxes: [[1, 2, 3, 4]], page_index: 3, exact: payload.quote, type: "TextQuoteSelector" },
  };
  assert.equal(annotationReceiptMatches(record, payload), true);
  for (const change of [
    { id: "other-request" }, { asset: "other-asset" }, { page: "other-page" }, { kind: "highlight" },
    { quote: "其他原文" }, { body_text: "其他笔记" }, { tags: [] }, { color: "blue" },
    { selector: { ...record.selector, page_index: 4 } },
    { selector: { ...record.selector, bboxes: [[1, 2, 30, 40]] } },
    { selector: { ...record.selector, exact: "其他原文" } },
    { selector: { ...record.selector, added: "unexpected" } },
  ]) assert.equal(annotationReceiptMatches({ ...record, ...change }, payload), false);
});
