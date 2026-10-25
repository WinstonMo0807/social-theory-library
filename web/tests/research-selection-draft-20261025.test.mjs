// Defined for final acceptance, not executed during development.
import test from "node:test";
import assert from "node:assert/strict";
import { parseResearchSelectionDraft } from "../lib/research-selection-draft.ts";

const span = "11111111-1111-4111-8111-111111111111";
const requestId = "22222222-2222-4222-8222-222222222222";
const draft = { revision: 5, additions: [{ key: span, title: "合成材料", reference: { evidence_span_id: span } }], removals: [{ key: "old-reference", title: "原选材" }], requestId };
test("selection recovery retains its pinned request and discards source bodies", () => {
  assert.deepEqual(parseResearchSelectionDraft(draft), draft);
  assert.deepEqual(parseResearchSelectionDraft({ ...draft, additions: [{ ...draft.additions[0], quote: "discard", reference: { evidence_span_id: span, quote: "discard" } }], token: "discard" }), draft);
});
test("duplicate, contradictory, excessive or malformed changes cannot be restored", () => {
  for (const value of [{ ...draft, revision: 0 }, { ...draft, requestId: "other/path" }, { ...draft, removals: [{ key: span, title: "conflict" }] }, { ...draft, additions: Array(401).fill(draft.additions[0]) }, { revision: 1, additions: [], removals: [] }]) assert.throws(() => parseResearchSelectionDraft(value));
});
