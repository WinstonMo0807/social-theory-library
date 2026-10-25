// Deferred acceptance: only definitions, no execution during this development stage.
import test from "node:test";
import assert from "node:assert/strict";
import { researchNotesMarkdown } from "../lib/research-notes-export.ts";

const record = { id: "project", revision: 1, data: { title: "合成研究", question: "问题", selections: [], scope: { kind: "library" } }, turns: [] };
test("notes export does not substitute an AI proposal or source text for saved notes", () => {
  const value = { ...record, turns: [{ id: "turn", data: { question: "问题", result_refs: [{ reference_id: "ref", source_status: "available", quote: "原文不得自动导出" }], comparison_draft: { rows: [{ note: "尚未采用的模型建议" }] } } }] };
  assert.equal(researchNotesMarkdown(value), null);
  const output = researchNotesMarkdown({ ...value, data: { ...value.data, notes: "读者已保存判断" } });
  assert.match(output, /读者已保存判断/);
  assert.doesNotMatch(output, /原文不得自动导出|尚未采用的模型建议/);
});
test("saved comparison, material and turn notes survive while withdrawn sources are labeled", () => {
  const output = researchNotesMarkdown({ ...record, data: { ...record.data, selection_notes: { withdrawn: "历史选材备注" }, comparison: { cells: [{ dimension: "条件", note: "已保存的比较", reference_ids: ["withdrawn"] }] } }, turns: [{ id: "turn", data: { question: "原问题", replay_note: "轮次笔记", result_refs: [{ reference_id: "withdrawn", source_status: "unavailable", title: "不应导出的旧标题", quote: "不应导出的旧引文" }] } }] });
  for (const text of ["历史选材备注", "已保存的比较", "轮次笔记", "来源待核对"]) assert.ok(output.includes(text));
  assert.doesNotMatch(output, /不应导出的旧标题|不应导出的旧引文/);
});
