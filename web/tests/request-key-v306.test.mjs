import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";
import { createRequestKey } from "../lib/request-key.ts";

test("request UUID works without secure-context randomUUID on the HTTP LAN entry", () => {
  const provider = { getRandomValues: (bytes) => webcrypto.getRandomValues(bytes) };
  const keys = new Set(Array.from({ length: 100 }, () => createRequestKey(provider)));
  assert.equal(keys.size, 100);
  for (const key of keys) assert.match(key, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test("request key uses native UUID when provided and never invents an unsafe fallback", () => {
  const key = webcrypto.randomUUID();
  assert.equal(createRequestKey({ randomUUID: () => key }), key);
  assert.throws(() => createRequestKey({}), /操作编号/);
});
