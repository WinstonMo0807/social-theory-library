import assert from "node:assert/strict";
import test from "node:test";
import { buildCandidateActionBody, candidateRejectionAction, resolveCandidateActionDescriptors } from "../components/admin/research/candidate-action-contract.ts";
import { normalizeEvidenceEnvelope } from "../components/admin/research/evidence-envelope.ts";

test("shared field candidate actions preserve exact field, object and edited value", () => {
  for (const field of ["title", "authors", "publisher", "publication_place", "publication_year", "isbn", "doi", "disciplines", "subdisciplines", "theory_schools", "topics"]) {
    const candidate = { field_name: field, proposed_value: "原建议", action_descriptors: [{ action: "accept_with_edit", url: "/catalog/admin/candidate/decision/", payload: { field_name: field, edition_id: "current-edition" }, value_field: "proposed_value" }] };
    const [action] = resolveCandidateActionDescriptors(candidate);
    assert.deepEqual(buildCandidateActionBody(action, "人工校改"), { field_name: field, edition_id: "current-edition", action: "accept_with_edit", proposed_value: "人工校改" });
    assert.equal(candidate.proposed_value, "原建议");
  }
});

test("shared suggestions keep manual-lock rejection, defer and explicit evidence actions", () => {
  const rows = resolveCandidateActionDescriptors({ action_descriptors: [
    { action: "accept", availability: { available: false, reason: "字段已人工锁定" } },
    { action: "reject", payload: { candidate_id: "candidate-1" } },
    { action: "defer" }, { action: "inspect", method: "GET" },
  ] });
  assert.equal(rows[0].disabled, true);
  assert.equal(rows[0].disabledReason, "字段已人工锁定");
  const body = buildCandidateActionBody(candidateRejectionAction(rows[1], "edition_mismatch", "不是当前译本"));
  assert.deepEqual(body, { candidate_id: "candidate-1", reason: "版本不符：不是当前译本", action: "reject" });
  assert.equal(rows[2].action, "defer");
  assert.equal(rows[3].method, "GET");
});

test("long evidence survives shared DTO normalization with original source and page identity", () => {
  const originalText = "完整中文证据与出处。".repeat(80);
  const evidence = normalizeEvidenceEnvelope({ id: "evidence", supporting_text: originalText, source: { work_title: "当前作品", asset_id: "asset-original" }, locator: { page: 41, printed_page_label: "三十九" }, quality: { stale: true, stale_reason: "新文档版本待核对" } });
  assert.equal(evidence.text, originalText);
  assert.equal(evidence.title, "当前作品");
  assert.equal(evidence.page, "41");
  assert.equal(evidence.printedPageLabel, "三十九");
  assert.equal(evidence.readerUrl, "/reader/asset-original?page=41");
  assert.equal(evidence.stale, true);
  assert.equal(evidence.staleReason, "新文档版本待核对");
});
