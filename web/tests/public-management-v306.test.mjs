import assert from "node:assert/strict";
import test from "node:test";
import { buildCandidateActionBody, candidateRejectionAction, candidateRejectionReasons } from "../components/admin/research/candidate-action-contract.ts";

test("rejection choices retain endpoint/action and persist distinct human reasons", () => {
  const descriptor = { action: "reject", url: "/same-existing-endpoint/", method: "POST", payload: { action: "reject", reason: "old-fixed-reason", candidate_id: "candidate" } };
  const bodies = Object.keys(candidateRejectionReasons).map((reason) => {
    const action = candidateRejectionAction(descriptor, reason, reason === "other" ? "材料需要另行核对" : "");
    assert.equal(action.url, descriptor.url);
    assert.equal(action.method, "POST");
    const body = buildCandidateActionBody(action);
    assert.equal(body.action, "reject");
    assert.equal(body.candidate_id, "candidate");
    return body;
  });
  assert.equal(new Set(bodies.map((body) => body.reason)).size, 5);
  assert.equal(descriptor.payload.reason, "old-fixed-reason");
  assert.throws(() => candidateRejectionAction(descriptor, "other", " "));
  assert.throws(() => candidateRejectionAction(descriptor, "unknown"));
});
