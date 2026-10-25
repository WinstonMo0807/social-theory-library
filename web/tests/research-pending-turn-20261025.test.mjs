// Deferred acceptance; defined but not run during development.
import test from "node:test";
import assert from "node:assert/strict";
import { parsePendingResearchTurn, parseResearchScopeDraft, parseResearchReferenceDraft } from "../lib/research-pending-turn.ts";

const project = "11111111-1111-4111-8111-111111111111";
const parent = "22222222-2222-4222-8222-222222222222";
const request = "33333333-3333-4333-8333-333333333333";
const ref = { asset_id: project, document_revision_id: parent, evidence_span_id: null, pdf_page: 4, content_hash: "a".repeat(64), selection_start: 0, selection_end: 8 };
const pending = { branch: true, command: { projectId: project, data: { request_id: request, expected_revision: 7, parent_id: parent, question: "这些原文有哪些边界", mode: "search", scope: { kind: "passages", filters: { year_min: 1990 }, allow_neighbors: false, references: [ref] } } } };

test("a restored request preserves exact identity, original revision, range and parent", () => {
  const parsed = parsePendingResearchTurn(pending, project);
  assert.deepEqual(parsed, pending);
  assert.deepEqual(parsePendingResearchTurn(JSON.parse(JSON.stringify(parsed)), project), parsed);
  assert.throws(() => parsePendingResearchTurn(pending, parent));
  assert.throws(() => parsePendingResearchTurn({ ...pending, command: { ...pending.command, data: { ...pending.command.data, parent_id: undefined } } }, project));
});
test("local commands never persist source text or unrelated response fields", () => {
  assert.deepEqual(parseResearchReferenceDraft({ ...ref, quote: "private text", reader_url: "javascript:bad", token: "synthetic-extra" }), ref);
  assert.deepEqual(parseResearchReferenceDraft({ anchors: [{ ...ref, quote: "text" }] }), { anchors: [ref] });
  assert.throws(() => parseResearchReferenceDraft({ anchors: [{ anchors: [ref] }] }));
});
test("invalid scopes never silently widen into a library search", () => {
  for (const scope of [{ kind: "passages", references: [] }, { kind: "works", filters: {} }, { kind: "unknown" }, { kind: "filtered", filters: { unsupported: "value" } }]) assert.throws(() => parseResearchScopeDraft(scope));
  for (const broken of [{ ...ref, selection_end: 0 }, { ...ref, content_hash: "invalid" }, { ...ref, asset_id: "../../other" }]) assert.throws(() => parseResearchReferenceDraft(broken));
});
