import assert from "node:assert/strict";
import test from "node:test";
import { readGuestRecords, saveGuestRecord } from "../lib/guest-records.ts";

const entries = new Map();
Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
  getItem: key => entries.get(key) ?? null,
  setItem: (key, value) => entries.set(key, value),
} });
globalThis.window = new EventTarget();
const source = { kind: "reading", asset_id: "bfeac4ed-f076-46fa-afb5-98a169eaa003", revision_id: "e8ee0110-aa62-425a-8e4b-dc5a033b6a4d", pdf_page: 2 };

test("moving a guest reading position keeps one record and never mutates an already used import identity", () => {
  entries.clear();
  assert.equal(saveGuestRecord(source), true);
  const original = readGuestRecords().records[0];
  assert.equal(saveGuestRecord({ ...source, pdf_page: 8 }), true);
  const current = readGuestRecords().records;
  assert.equal(current.length, 1);
  assert.notEqual(current[0].id, original.id);
  assert.equal(current[0].pdf_page, 8);
  assert.equal(original.pdf_page, 2);
  assert.equal(saveGuestRecord({ ...source, revision_id: "8b79965b-b426-4fbb-ab79-a9bdc8346a1e" }), true);
  assert.equal(readGuestRecords().records.length, 2);
});

test("unsupported or damaged local records are preserved and never silently replaced", () => {
  entries.clear();
  entries.set("stl:guest-records:v1", '{"version":8,"records":[]}');
  assert.equal(readGuestRecords().available, false);
  assert.equal(saveGuestRecord(source), false);
  assert.equal(entries.get("stl:guest-records:v1"), '{"version":8,"records":[]}');
});
