import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  buildCandidateActionBody,
  parseCandidateEditableValue,
  resolveCandidateActionDescriptors,
} from "../components/admin/research/candidate-action-contract.ts";
import { normalizeEvidenceEnvelope } from "../components/admin/research/evidence-envelope.ts";

test("candidate descriptors take precedence and preserve edited payload contracts", () => {
  const candidate = {
    kind: "ordinary_metadata",
    proposed_value: { title: "旧题名" },
    decision_url: "/legacy/decision/",
    available_actions: ["accept", "reject"],
    action_descriptors: [{
      action: "accept_with_edit",
      label: "编辑后采用",
      endpoint: "/descriptor/decision/",
      method: "patch",
      payload: { reason: "field-contract" },
      edit_field: "candidate_value",
    }],
  };
  const actions = resolveCandidateActionDescriptors(candidate);
  assert.equal(actions.length, 1);
  assert.equal(actions[0].source, "descriptor");
  assert.equal(actions[0].url, "/descriptor/decision/");
  assert.equal(actions[0].method, "PATCH");
  assert.equal(actions[0].editable, true);
  assert.deepEqual(
    buildCandidateActionBody(actions[0], { title: "新题名" }, { action: "legacy" }),
    { action: "accept_with_edit", reason: "field-contract", candidate_value: { title: "新题名" } },
  );
  assert.deepEqual(parseCandidateEditableValue('{"title":"新题名"}', candidate.proposed_value), { title: "新题名" });
});

test("legacy available actions remain a bounded fallback", () => {
  const actions = resolveCandidateActionDescriptors({
    entity_type: "person",
    decision_url: "/decision/",
    available_actions: ["link_existing", "create_draft", "reject", "reject"],
  });
  assert.deepEqual(actions.map((row) => row.action), ["link_existing", "create_draft", "reject"]);
  assert.equal(actions[0].label, "关联已有学者");
  assert.equal(actions[1].label, "创建新学者主页");
  assert.equal(actions[2].tone, "danger");
});

test("descriptor availability disables actions and surfaces the backend reason", () => {
  const actions = resolveCandidateActionDescriptors({
    action_descriptors: [{
      key: "accept",
      label: "采用",
      endpoint: "/decision/",
      availability: {
        available: false,
        reason: "当前证据要求尚未满足。",
      },
    }],
  });
  assert.equal(actions.length, 1);
  assert.equal(actions[0].disabled, true);
  assert.equal(actions[0].disabledReason, "当前证据要求尚未满足。");
});

test("EvidenceEnvelope normalization keeps PDF locator, quality and OCR provenance", () => {
  const evidence = normalizeEvidenceEnvelope({
    id: "evidence-1",
    source: { work_title: "馆藏作品", authors: ["作者"], asset_id: "asset-1" },
    text: "可核对的原文。",
    locator: { page: 12, printed_page_label: "xi", section: "序言", start_offset: 10, end_offset: 42, bbox: [1, 2, 3, 4] },
    quality: { score: 0.87, stale: false, body_fetched: true },
    provenance: { extraction_method: "ocr", extraction_version: "3", ocr_provider: "paddle", ocr_model: "model", ocr_version: "v1" },
    reader_url: "/reader/asset-1?page=12",
    pdf_url: "/api/catalog/assets/asset-1/manifest/",
  });
  assert.equal(evidence.page, "12");
  assert.equal(evidence.printedPageLabel, "xi");
  assert.deepEqual(evidence.locatorDetails, ["字符 10–42", "页内坐标 1, 2, 3, 4"]);
  assert.equal(evidence.qualityScore, 0.87);
  assert.deepEqual(evidence.qualityDetails, ["已取得正文"]);
  assert.equal(evidence.ocrProvider, "paddle");
  assert.equal(evidence.readerUrl, "/reader/asset-1?page=12");
  assert.equal(evidence.pdfUrl, "/api/catalog/assets/asset-1/manifest/");
});

test("Wave A consumers share decisions and evidence while Admin Shell narrows normal staff IA", async () => {
  const [panel, inspector, review, shell] = await Promise.all([
    readFile(new URL("../components/admin/research/research-suggestion-panel.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/inspector/workflow-inspector.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/candidate-review.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin-shell.tsx", import.meta.url), "utf8"),
  ]);
  for (const source of [panel, inspector, review]) assert.match(source, /CandidateDecisionBar/);
  for (const source of [inspector, review]) assert.match(source, /EvidenceEnvelopeCard/);
  assert.match(panel, /decision_descriptor/);
  assert.match(inspector, /edited_value/);
  assert.match(shell, /const staffRoles = \["admin", "editor"\]/);
  assert.match(shell, /"\/admin\/processing": \["can_view_system_status"\]/);
  assert.doesNotMatch(shell, /\["\/admin\/subdisciplines",/);
  assert.doesNotMatch(shell, /\["系统高级",/);
  assert.doesNotMatch(shell, /\["\/admin\/query-lexicon", Search, "QueryLexicon"\]/);
  assert.doesNotMatch(shell, /\["\/admin\/semantic-index", ScanSearch, "语义索引"\]/);
});
