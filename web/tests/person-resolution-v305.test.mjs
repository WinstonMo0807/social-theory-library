import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { canConfirmPersonMerge, isPersonId, rollbackState, personApi, personPage } from "../lib/api/person-resolution.ts";

const source = "30500000-0000-4000-8000-000000000011", target = "30500000-0000-4000-8000-000000000012";
const preview = { source: { id: source }, target: { id: target }, fingerprint: "a".repeat(64), execution_policy: "person-merge-noncolliding-v1", merge_execution_available: true, complete_reference_listing: true, review_issues: [], identity_conflicts: [] };

test("merge confirmation requires the exact displayed pair and supported complete preview", () => {
  assert.equal(canConfirmPersonMerge(preview, source, target), true);
  for (const change of [{ source: { id: target } }, { target: null }, { execution_policy: "future-policy" }, { fingerprint: "bad" }, { complete_reference_listing: false }, { merge_execution_available: false }, { review_issues: [{ detail: "pending" }] }, { identity_conflicts: [{}] }]) {
    assert.equal(canConfirmPersonMerge({ ...preview, ...change }, source, target), false);
  }
  assert.equal(canConfirmPersonMerge(preview, source, source), false);
});

test("rollback rejects malformed, contradictory or already completed eligibility", () => {
  const good = { status: "applied", rollback: { can_rollback: true, fingerprint: "b".repeat(64), blockers: [] } };
  assert.equal(rollbackState(good).canRollback, true);
  for (const rollback of [null, true, [], { can_rollback: true, fingerprint: "b".repeat(64) }, { ...good.rollback, blockers: [12] }, { ...good.rollback, fingerprint: "bad" }, { ...good.rollback, blockers: ["later human change"] }]) {
    assert.equal(rollbackState({ ...good, rollback }).canRollback, false);
  }
  assert.equal(rollbackState({ ...good, status: "rolled_back" }).canRollback, false);
});

test("person navigation and query are encoded without becoming API parameters", () => {
  assert.equal(isPersonId(source), true);
  assert.equal(isPersonId(`${source}/merge`), false);
  assert.equal(personApi.search("a&limit=999"), "/catalog/admin/people/?search=a%26limit%3D999&limit=20");
  assert.equal(personPage(source, target), `/admin/people?source=${source}&target=${target}`);
  assert.equal(personPage(), "/admin/people");
});

test("person option links do not prefetch unrelated record and metadata pages", async () => {
  const content = await readFile(new URL("../components/admin/knowledge/person-resolution-workspace.tsx", import.meta.url), "utf8");
  const links = [...content.matchAll(/<Link\b[^>]+>/g)];
  assert.ok(links.length > 0);
  for (const [link] of links) assert.match(link, /prefetch=\{false\}/);
  assert.doesNotMatch(content, /<h3 role="status"/);
});
