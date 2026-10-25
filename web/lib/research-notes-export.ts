import type { ProjectData, ResearchRecord, ResolvedEvidence, TurnData } from "./api/research.client";

const heading = (value: string) => value.replace(/[\r\n]+/g, " ").replace(/[\\`*_<>\[\]#|]/g, "\\$&");
const note = (value: unknown) => typeof value === "string" ? value.trim() : "";

/** Only saved reader-authored notes; model proposals and original-text payloads are excluded. */
export function researchNotesMarkdown(record: ResearchRecord<ProjectData> & { turns?: ResearchRecord<TurnData>[] }): string | null {
  const sections: string[] = [];
  const sources = new Map<string, ResolvedEvidence>();
  for (const ref of [...record.data.selections, ...(record.turns || []).flatMap(turn => [...(turn.data.selected_refs || []), ...(turn.data.result_refs || [])])]) {
    if (ref.reference_id) sources.set(ref.reference_id, ref);
  }
  const label = (ref: ResolvedEvidence | undefined, id: string) => {
    if (!ref || ref.source_status !== "available") return `来源待核对 · 引用标识 ${heading(id)}`;
    return heading(ref.citation || [ref.title || "原文材料", ref.pdf_page ? `PDF 第 ${ref.pdf_page} 页` : ""].filter(Boolean).join(" · "));
  };
  const sourceLabel = (id: string) => label(sources.get(id), id);
  if (note(record.data.notes)) sections.push(`## 研究笔记\n\n${note(record.data.notes)}`);
  for (const [id, value] of Object.entries(record.data.selection_notes || {})) {
    if (note(value)) sections.push(`## 选材备注\n\n${label(record.data.selection_note_sources?.[id], id)}\n\n${note(value)}`);
  }
  for (const cell of record.data.comparison?.cells || []) {
    if (!note(cell.note)) continue;
    sections.push(`## 比较笔记 · ${heading(cell.dimension)}\n\n${note(cell.note)}${cell.reference_ids?.length ? `\n\n依据：\n\n${cell.reference_ids.map(id => `- ${sourceLabel(id)}`).join("\n")}` : "\n\n尚未关联原文依据。"}`);
  }
  for (const turn of record.turns || []) {
    if (note(turn.data.replay_note)) sections.push(`## 轮次笔记 · ${heading(note(turn.data.replay_title) || turn.data.question || "研究轮次")}\n\n${note(turn.data.replay_note)}`);
  }
  if (!sections.length) return null;
  return `# ${heading(record.data.title || record.data.question || "研究笔记")}\n\n仅包含本次读取时服务器已保存的本人笔记与来源书目信息。未保存输入、模型待确认草稿和原文正文不在本文件中。\n\n${sections.join("\n\n---\n\n")}\n`;
}
