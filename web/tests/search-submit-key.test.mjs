import assert from "node:assert/strict";
import test from "node:test";
import { submitSearchOnEnter } from "../lib/search-submit-key.ts";

function press(overrides = {}, disabled = false) {
  const calls = { prevented: 0, submitted: 0 };
  const submitter = { disabled };
  const form = { querySelector: () => submitter, requestSubmit: element => { assert.equal(element, submitter); calls.submitted++; } };
  submitSearchOnEnter({ key: "Enter", nativeEvent: { isComposing: false, keyCode: 13 }, currentTarget: { form }, preventDefault: () => calls.prevented++, ...overrides });
  return calls;
}
test("Enter uses the original submitter once and respects pending/disabled state", () => {
  assert.deepEqual(press(), { prevented: 1, submitted: 1 });
  assert.equal(press({}, true).submitted, 0);
  assert.equal(press({ repeat: true }).submitted, 0);
});
test("IME composition and newline shortcuts never submit search", () => {
  for (const event of [{ shiftKey: true }, { ctrlKey: true }, { metaKey: true }, { altKey: true }, { nativeEvent: { isComposing: true, keyCode: 13 } }, { nativeEvent: { isComposing: false, keyCode: 229 } }, { key: "a" }]) {
    assert.deepEqual(press(event), { prevented: 0, submitted: 0 });
  }
});
