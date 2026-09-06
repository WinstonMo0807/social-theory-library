import assert from "node:assert/strict";
import test from "node:test";
import { updateContextState } from "../lib/use-context-state.ts";

test("late field lookup cannot overwrite another field context", () => {
  const current = { key: "edition-b:author", value: ["accepted-b"] };
  assert.equal(updateContextState(current, "edition-a:author", ["late-a"]), current);
});

test("stale functional update is not evaluated", () => {
  const current = { key: "new-query", value: 0 };
  const updated = updateContextState(current, "old-query", () => { throw new Error("stale callback ran"); });
  assert.equal(updated, current);
});

test("current scope supports functional updates and preserves equal-state identity", () => {
  const current = { key: "session:field", value: 1 };
  assert.deepEqual(updateContextState(current, current.key, (value) => value + 1), { key: current.key, value: 2 });
  assert.equal(updateContextState(current, current.key, 1), current);
});
