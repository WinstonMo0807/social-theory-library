import assert from "node:assert/strict";
import test from "node:test";
import { loadSavedCover } from "../lib/saved-cover.ts";

test("saved list covers pace requests, omit cancelled rows and preserve protected failures", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options, at: Date.now() });
    return String(url).includes("failed")
      ? Response.json({ detail: "图片读取失败" }, { status: 503 })
      : new Response(new Blob(["cover"]), { status: 200 });
  };
  try {
    const cancelled = new AbortController();
    const results = Promise.allSettled([
      loadSavedCover("/api/catalog/admin/works/first/recommendation-image/?slot=cover", "cookie-session", new AbortController().signal),
      loadSavedCover("/api/catalog/admin/works/cancelled/recommendation-image/?slot=cover", "cookie-session", cancelled.signal),
      loadSavedCover("/api/catalog/admin/works/failed/recommendation-image/?slot=cover", "cookie-session", new AbortController().signal),
    ]);
    cancelled.abort();
    const [success, skipped, failure] = await results;
    assert.equal(success.status, "fulfilled");
    assert.equal(await success.value.text(), "cover");
    assert.equal(skipped.reason.name, "AbortError");
    assert.equal(failure.reason.status, 503);
    assert.equal(calls.length, 2);
    assert.equal(calls[0].url, "/api/catalog/admin/works/first/recommendation-image/?slot=cover");
    assert.ok(calls[1].at - calls[0].at >= 950);
    assert.equal(calls[0].options.credentials, "include");
    assert.equal(calls[0].options.headers.has("Authorization"), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
