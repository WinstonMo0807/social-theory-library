import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  canDirectlySelectResearchSuggestion,
  groupResearchSuggestions,
  isEvidenceSuggestion,
  isSelectableResearchSuggestion,
} from "../components/admin/research/research-suggestion-state.ts";


test("research suggestions preserve source groups instead of mixing confidence ranks", () => {
  const grouped = groupResearchSuggestions([
    { id: "web", field_name: "related_disciplines", source_tier: "research_lead", confidence: 0.95 },
    { id: "pdf", field_name: "related_disciplines", source_tier: "pdf_evidence", confidence: 0.6 },
    { id: "local", field_name: "related_disciplines", source_tier: "in_library", confidence: 0.4 },
    { id: "lexicon", field_name: "related_disciplines", source_tier: "query_lexicon", confidence: 0.8 },
  ], "related_disciplines");
  assert.deepEqual(grouped.map(([key]) => key), [
    "in_library",
    "query_lexicon",
    "pdf_evidence",
    "research_lead",
  ]);
});

test("research leads cannot be selected or treated as evidence", () => {
  const lead = {
    id: "lead",
    entity_id: "00000000-0000-0000-0000-000000000001",
    source_tier: "research_lead",
    evidence_status: "lead_only",
  };
  assert.equal(isSelectableResearchSuggestion(lead), false);
  assert.equal(isEvidenceSuggestion(lead), false);
  assert.equal(isEvidenceSuggestion({ id: "pdf", source_tier: "pdf_evidence" }), true);
  assert.equal(isSelectableResearchSuggestion({ id: "local", entity_id: "entity", source_tier: "in_library" }), true);
  assert.equal(canDirectlySelectResearchSuggestion({ id: "lexicon", entity_id: "entity", source_tier: "query_lexicon" }), true);
  assert.equal(canDirectlySelectResearchSuggestion({ id: "local", entity_id: "entity", source_tier: "in_library" }), true);
  assert.equal(canDirectlySelectResearchSuggestion({ id: "resolution", entity_id: "entity", source_tier: "in_library", decision_url: "/decision/" }), false);
  assert.equal(canDirectlySelectResearchSuggestion({ id: "pdf", entity_id: "entity", source_tier: "pdf_evidence" }), false);
});

test("classification uses canonical pickers and curation keeps explicit evidence suggestions", async () => {
  const editor = await readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8");
  const curation = await readFile(new URL("../components/admin/curation/work-curation-editor.tsx", import.meta.url), "utf8");
  assert.match(editor, /EntityPicker[\s\S]*?label="主要学科"/);
  assert.doesNotMatch(editor, /label="正式对象 ID"/);
  assert.match(editor, /WorkflowFieldAssistant/);
  assert.match(editor, /<WorkCurationEditor/);
  assert.match(curation, /更多策展内容/);
  assert.match(curation, /CurationFieldAssistant/);
  assert.match(curation, /EntityPicker[\s\S]*搜索馆内阅读路径/);
});

test("front matter authors and translators stay role-aware and require an individual decision", async () => {
  const editor = await readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8");
  assert.match(editor, /\["authors", "translators"\]\.includes\(field\)/);
  assert.match(editor, /field === "authors" \? "author" : "translator"/);
  assert.match(editor, /fieldName="author"/);
  assert.match(editor, /fieldName="translator"/);
  assert.match(editor, /beforeAction=\{props.beforeFieldAction\}/);
  assert.match(editor, /onFill=\{fieldName in FILL_FIELD_LABELS \? props.fillSuggestion : undefined\}/);
});

test("candidate inspector separates evidence and match basis from system diagnostics", async () => {
  const inspector = await readFile(new URL("../components/admin/inspector/workflow-inspector.tsx", import.meta.url), "utf8");
  const actions = await readFile(new URL("../components/admin/research/candidate-action-contract.ts", import.meta.url), "utf8");
  assert.match(inspector, /匹配依据/);
  assert.match(inspector, /取得可靠正文依据前不能采用/);
  assert.match(inspector, /CandidateDecisionBar/);
  assert.match(actions, /action_descriptors/);
  assert.match(inspector, /EvidenceEnvelopeCard/);
  assert.match(actions, /candidate\.decision_url/);
});

test("entity picker supports keyboard entry and human-readable status", async () => {
  const fields = await readFile(new URL("../components/admin/forms/workflow-fields.tsx", import.meta.url), "utf8");
  assert.match(fields, /event\.key === "Escape"/);
  assert.match(fields, /event\.key === "ArrowDown"/);
  assert.match(fields, /event\.key === "Enter"/);
  assert.match(fields, /aria-autocomplete="list"/);
  assert.match(fields, /published: "已发布"/);
});

test("step research is a shared action and does not navigate away from workflow", async () => {
  const panel = await readFile(new URL("../components/admin/research/research-suggestion-panel.tsx", import.meta.url), "utf8");
  assert.match(panel, /联网补充本节/);
  assert.match(panel, /method: "POST"/);
  assert.match(panel, /建议不会自动写入正式字段/);
  assert.doesNotMatch(panel, /window\.location|router\.push/);
  assert.match(panel, /draft_session_id: draftSessionId/);
  assert.match(panel, /setPayload\(\{ status: "stale"/);
});

test("candidate workspace exposes every result and converts evidenced web leads before adoption", async () => {
  const panel = await readFile(new URL("../components/admin/research/research-suggestion-panel.tsx", import.meta.url), "utf8");
  const decisionBar = await readFile(new URL("../components/admin/research/candidate-decision-bar.tsx", import.meta.url), "utf8");
  const actionContract = await readFile(new URL("../components/admin/research/candidate-action-contract.ts", import.meta.url), "utf8");
  const shared = `${panel}\n${decisionBar}\n${actionContract}`;
  assert.match(panel, /expanded \? rows : rows\.slice\(0, 5\)/);
  assert.match(panel, /展开全部 \$\{rows\.length\} 项/);
  assert.match(panel, /candidate\.verify_url/);
  assert.match(panel, /candidate\.verify_payload/);
  assert.match(panel, /research\/candidates\/\$\{encodeURIComponent/);
  assert.match(shared, /核实此结果/);
  assert.match(shared, /修改后采用/);
  assert.match(shared, /查看依据/);
  assert.match(shared, /拒绝\/不采用/);
  assert.match(panel, /<CandidateDecisionBar/);
  assert.match(decisionBar, /确认修改并采用/);
  assert.match(actionContract, /action_descriptors/);
  assert.match(panel, /ToastHost/);
});

test("research actions respect capability and refresh after a candidate decision", async () => {
  const editor = await readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8");
  const panel = await readFile(new URL("../components/admin/research/research-suggestion-panel.tsx", import.meta.url), "utf8");
  assert.match(editor, /capabilities\?\.includes\("can_run_enrichment"\)/);
  assert.match(editor, /ResearchSuggestionCapabilityContext\.Provider value=\{canRunResearch\}/);
  assert.match(panel, /disabled=\{!canRunResearch \|\| loading \|\| running \|\| nonTerminalRun \|\| !credential\}/);
  assert.match(editor, /rows\.filter\(\(row\) => String\(row\.id\) !== String\(candidate\.id\)\)/);
  assert.match(editor, /setInspector\(null\)/);
  assert.match(editor, /RESEARCH_SUGGESTION_REFRESH_EVENT/);
  assert.match(panel, /addEventListener\(RESEARCH_SUGGESTION_REFRESH_EVENT, reload\)/);
});
