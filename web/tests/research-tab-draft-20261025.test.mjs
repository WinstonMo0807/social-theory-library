// Deferred acceptance only; no development-stage execution.
import test from "node:test";
import assert from "node:assert/strict";
import { parseResearchNoteDraft, parseResearchTabDraft, researchTabDraftKey } from "../lib/research-tab-draft.ts";

const draft = { text: "离线补充的判断", initial: "原笔记", revision: 9 };
const record = { version: 1, owner: "7", project: "project-a", kind: "notes", at: 1792886400000, input: draft };
test("offline notes retain their original revision and remain within one owner/project/kind", () => {
  assert.deepEqual(parseResearchTabDraft(JSON.stringify(record), "7", "project-a", "notes", parseResearchNoteDraft), record);
  for (const [owner, project, kind] of [["8", "project-a", "notes"], ["7", "project-b", "notes"], ["7", "project-a", "turn"]]) {
    assert.throws(() => parseResearchTabDraft(JSON.stringify(record), owner, project, kind, parseResearchNoteDraft));
    assert.notEqual(researchTabDraftKey(owner, project, kind), researchTabDraftKey("7", "project-a", "notes"));
  }
});
test("only authored notes and the editing baseline are restored, including an explicit empty replacement", () => {
  assert.deepEqual(parseResearchNoteDraft({ ...draft, source_text: "must not persist", token: "synthetic-extra" }), draft);
  assert.equal(parseResearchNoteDraft({ ...draft, text: "" }).text, "");
  for (const input of [null, { ...draft, text: "x".repeat(20001) }, { ...draft, revision: 0 }, { ...draft, revision: 2.5 }]) assert.throws(() => parseResearchNoteDraft(input));
});
test("invalid envelopes fail without a replacement value", () => {
  for (const raw of ["broken", "x".repeat(300001), JSON.stringify({ ...record, at: -1 }), JSON.stringify({ ...record, version: 2 })]) assert.throws(() => parseResearchTabDraft(raw, "7", "project-a", "notes", parseResearchNoteDraft));
  assert.equal(parseResearchTabDraft(null, "7", "project-a", "notes", parseResearchNoteDraft), null);
});
