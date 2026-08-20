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

test("classification and knowledge use the research picker without manual UUID fields", async () => {
  const editor = await readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8");
  assert.match(editor, /ResearchSuggestionPanel[\s\S]*step="classification"/);
  assert.match(editor, /ResearchEntityPicker label="主要学科"/);
  assert.match(editor, /ResearchEntityPicker label="关联对象"/);
  assert.doesNotMatch(editor, /label="正式对象 ID"/);
  assert.match(editor, /step="curation"/);
  assert.match(editor, /step="bibliography"/);
});

test("candidate inspector separates evidence, match basis and lexicon impact", async () => {
  const inspector = await readFile(new URL("../components/admin/inspector/workflow-inspector.tsx", import.meta.url), "utf8");
  assert.match(inspector, /匹配依据/);
  assert.match(inspector, /词典影响/);
  assert.match(inspector, /搜索摘要不是 Evidence/);
  assert.match(inspector, /QueryLexicon sync/);
  assert.match(inspector, /candidate\.decision_url/);
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
});
