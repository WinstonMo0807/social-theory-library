// Acceptance definition only; run in the final acceptance window.
import assert from "node:assert/strict";
import { movePathMaterial, movePathStage } from "../components/admin/curation/path-stage-order.ts";

const a = { key: "a", id: "stable-a", dependencies: [] };
const b = { key: "b", id: "stable-b", dependencies: [{ item_id: "stable-a", kind: "learning_order" }] };
const c = { key: "c", id: "stable-c", dependencies: [] };
const original = [{ key: "one", items: [a, b] }, { key: "two", items: [c] }];
const moved = movePathMaterial(original, "b", "two", "c");
assert.deepEqual(moved.map(row => row.items.map(item => item.key)), [["a"], ["b", "c"]]);
assert.equal(moved[1].items[0], b);
assert.equal(moved[1].items[0].dependencies[0].item_id, a.id);
assert.deepEqual(original[0].items, [a, b]);
assert.equal(movePathMaterial(original, "b", "two", "missing"), original);
assert.deepEqual(movePathMaterial(original, "a", "one")[0].items, [b, a]);
assert.deepEqual(movePathStage(original, "two", "one").map(row => row.key), ["two", "one"]);
