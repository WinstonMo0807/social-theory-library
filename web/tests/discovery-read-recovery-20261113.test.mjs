import assert from "node:assert/strict";
import test from "node:test";
import { ApiRequestError } from "../lib/api.ts";
import { canRetryDiscoveryRead, readDiscoverySearch } from "../lib/api/discovery.client.ts";

test("a timed out progress read stays a timeout and never creates another search", async t => {
  const timeout = AbortSignal.abort(new DOMException("Synthetic timeout", "TimeoutError"));
  t.mock.method(AbortSignal, "timeout", milliseconds => {
    assert.equal(milliseconds, 45000);
    return timeout;
  });
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url: String(url), method: options.method || "GET", token: options.headers.get("X-Discovery-Token") });
    throw options.signal.reason;
  });
  await assert.rejects(readDiscoverySearch("synthetic-session", "synthetic-capability"), reason => {
    assert.ok(reason instanceof ApiRequestError);
    assert.match(reason.message, /等待超时/);
    assert.doesNotMatch(reason.message, /已取消/);
    assert.equal(canRetryDiscoveryRead(reason, 1), true);
    return true;
  });
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /discovery-search\/synthetic-session\//);
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].token, "synthetic-capability");
});

test("transient progress failures retry within a bound, permission and expired sessions stop", () => {
  for (const status of [0, 408, 429, 502, 503, 504]) {
    const reason = new ApiRequestError("Synthetic transient failure", status);
    assert.equal(canRetryDiscoveryRead(reason, 1), true);
    assert.equal(canRetryDiscoveryRead(reason, 2), true);
    assert.equal(canRetryDiscoveryRead(reason, 3), false);
  }
  for (const status of [400, 401, 403, 404, 410]) {
    assert.equal(canRetryDiscoveryRead(new ApiRequestError("Synthetic terminal failure", status), 1), false);
  }
  assert.equal(canRetryDiscoveryRead(new Error("Unknown failure"), 1), false);
});
