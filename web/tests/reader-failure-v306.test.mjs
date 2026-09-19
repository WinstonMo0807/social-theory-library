import assert from "node:assert/strict";
import test from "node:test";
import { readerFailure, readerReturnPath } from "../lib/api/reader-failure.ts";

test("reader errors distinguish access, masked missing, waiting, throttling and unavailable service", () => {
  for (const [status, kind, retryable] of [[401,"authentication",true],[403,"forbidden",false],[404,"unavailable",true],[410,"unavailable",true],[409,"waiting",true],[429,"rate_limited",true],[503,"service_unavailable",true],[undefined,"service_unavailable",true]]) {
    const failure = readerFailure(status);
    assert.equal(failure.kind, kind);
    assert.equal(failure.retryable, retryable);
    assert.ok(failure.detail.length > 10);
  }
  assert.notEqual(readerFailure(403).detail, readerFailure(503).detail);
  assert.match(readerFailure(503).detail, /不表示文献未上架/);
});

test("reader recovery preserves exact asset and all supported evidence anchors", () => {
  const path = readerReturnPath("asset/opaque", {page:"21",q:"社会 关系",focus:"span",passage:"passage-1",evidence:"evidence-1"});
  const parsed = new URL(path, "https://local.test");
  assert.equal(parsed.pathname, "/reader/asset%2Fopaque");
  assert.equal(parsed.searchParams.get("page"), "21");
  assert.equal(parsed.searchParams.get("q"), "社会 关系");
  assert.equal(parsed.searchParams.get("passage"), "passage-1");
  assert.equal(parsed.searchParams.get("evidence"), "evidence-1");
});
