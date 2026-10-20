import assert from "node:assert/strict";
import test from "node:test";
import { readAllPages } from "../lib/api/read-all-pages.ts";

// Synthetic responses only. Written for unified acceptance; not run during development.
function json(status, payload) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

function browser(t, fetch) {
  const originals = new Map(["window", "fetch"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    location: { protocol: "https:", hostname: "library.test", origin: "https://library.test", port: "" },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, dispatchEvent() {},
  } });
  Object.defineProperty(globalThis, "fetch", { configurable: true, value: fetch });
  t.after(() => {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
}

test("all private pages carry the same owner and stay on the original collection", async t => {
  const calls = [];
  browser(t, async (path, options) => {
    calls.push(path);
    assert.equal(options.headers.get("X-Reader-Owner"), "17");
    assert.equal(options.cache, "no-store");
    return json(200, calls.length === 1
      ? { results: [{ id: "first" }], next: "https://internal.test/api/reading/saved/?work_ids=synthetic&page=2" }
      : { results: [{ id: "second" }], next: null });
  });
  assert.deepEqual(await readAllPages("/reading/saved/?work_ids=synthetic", "cookie-session", undefined, "17"), [{ id: "first" }, { id: "second" }]);
  assert.deepEqual(calls, ["/api/reading/saved/?work_ids=synthetic", "/api/reading/saved/?work_ids=synthetic&page=2"]);
});

test("an A to B to A cookie change rejects the whole read instead of mixing private pages", async t => {
  let cookieOwner = "17";
  let calls = 0;
  browser(t, async (_path, options) => {
    calls += 1;
    const expected = options.headers.get("X-Reader-Owner");
    if (calls === 1) {
      cookieOwner = "29";
      return json(200, { results: [{ id: "A-first" }], next: "?page=2" });
    }
    const payload = expected !== cookieOwner
      ? json(403, { detail: "登录账户已变化" })
      : json(200, { results: [{ id: "B-private" }], next: null });
    cookieOwner = "17";
    return payload;
  });
  await assert.rejects(readAllPages("/reading/lists/", "cookie-session", undefined, "17"), /账户已变化/);
  assert.equal(cookieOwner, "17");
  assert.equal(calls, 2);
});

test("private pagination never refreshes or replays a 401", async t => {
  const paths = [];
  browser(t, async path => {
    paths.push(path);
    return json(401, { detail: "登录已过期" });
  });
  await assert.rejects(readAllPages("/reading/saved/", "cookie-session", undefined, "17"), /登录已过期/);
  assert.deepEqual(paths, ["/api/reading/saved/"]);
});

test("missing owner is rejected before any private request", async t => {
  let calls = 0;
  browser(t, async () => { calls += 1; return json(200, []); });
  await assert.rejects(readAllPages("/reading/saved/", "cookie-session", undefined, ""), /确认登录账户/);
  assert.equal(calls, 0);
});
