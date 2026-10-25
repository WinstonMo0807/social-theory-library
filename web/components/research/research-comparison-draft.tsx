"use client";

import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { cancelResearchTurn, generateResearchComparison, retryResearchTurn, type ComparisonDraft } from "@/lib/api/research.client";
import { researchEvidenceKey } from "@/lib/api/research-evidence";
import { comparisonColumns } from "@/lib/api/research-comparison";
import { isTaskRunning } from "@/lib/api/task-polling";
import type { useResearchProject } from "./use-research-project";

type Workspace = ReturnType<typeof useResearchProject>;
type Candidate = ComparisonDraft["rows"][number];
const states: Record<string, string> = { queued: "比较草稿等待生成", running: "正在生成比较草稿", completed: "比较草稿待核对", partial: "部分草稿待核对", failed: "比较草稿生成未完成", canceled: "比较草稿生成已取消" };

export function ResearchComparisonGenerate({ workspace, dimension, onClose }: { workspace: Workspace; dimension: string; onClose: () => void }) {
  const { record, pending, run, requestId, actionError } = workspace;
  const [ids, setIds] = useState<string[]>(() => [...new Set((record?.data.comparison?.cells || []).filter(cell => cell.dimension === dimension).flatMap(cell => cell.reference_ids || []))].filter(id => record?.data.selections.some(ref => researchEvidenceKey(ref) === id && ref.source_status === "available")));
  if (!record) return null;
  const readable = record.data.selections.filter(ref => ref.source_status === "available");
  const valid = ids.length > 0 && ids.length <= 20 && ids.every(id => readable.some(ref => researchEvidenceKey(ref) === id)) && (record.data.comparison?.dimensions || []).includes(dimension);
  return <Dialog open onRequestClose={() => { if (!pending) onClose(); }} className="stl4-research-dialog stl4-comparison-editor" aria-labelledby="comparison-generate-title">
    <form onSubmit={event => { event.preventDefault(); if (!valid) return; const data = { dimension, reference_ids: ids }; void run(() => generateResearchComparison(record.id, { ...data, expected_revision: record.revision, request_id: requestId(JSON.stringify(data)) }), "比较草稿已加入原研究队列，已有笔记保留。").then(ok => { if (ok) onClose(); }); }}>
      <h2 id="comparison-generate-title">生成比较草稿</h2><p>维度：{dimension}。只把你明确选择的原文交给本地分析服务，不传入你的研究笔记。</p>
      <fieldset><legend>本次依据（已选 {ids.length} / 最多20条）</legend>{readable.map(ref => { const key = researchEvidenceKey(ref); return <label className="stl4-comparison-source" key={key}><input type="checkbox" checked={ids.includes(key)} disabled={pending || !ids.includes(key) && ids.length >= 20} onChange={event => setIds(rows => event.target.checked ? [...rows, key] : rows.filter(id => id !== key))}/><span><strong>{ref.title || "原文材料"} · PDF 第 {ref.pdf_page || "—"} 页</strong><span>{ref.quote || ref.text || "打开原文核对"}</span></span></label>; })}{!readable.length ? <p>还没有可用原文。请先加入选材，或重新核对已变化的来源。</p> : null}</fieldset>
      <p>草稿与本人判断分开保存。生成结束后逐条核对、编辑，再另存为比较笔记。超过原文或模型预算时会保留未完成状态，不截断材料或改用远程服务。</p>
      {actionError ? <p role="alert">{actionError}<button type="button" disabled={pending} onClick={workspace.refresh}>读取最新研究状态</button></p> : null}
      <footer><button type="button" disabled={pending} onClick={onClose}>返回</button><button type="submit" disabled={pending || !valid || record.archived}>{pending ? "正在提交……" : "使用所选原文生成"}</button></footer>
    </form>
  </Dialog>;
}

export function ResearchComparisonDrafts({ workspace, dimension, onReview }: { workspace: Workspace; dimension: string; onReview: (dimension: string, candidate: Candidate) => void }) {
  const { record, turns, pending, run, requestId, refresh, pollPaused } = workspace;
  const [chosen, setChosen] = useState("");
  const drafts = turns.filter(turn => turn.data.return_context?.kind === "comparison_draft" && turn.data.return_context.dimension === dimension);
  const current = drafts.find(turn => turn.id === chosen) || drafts.at(-1);
  const draft = current?.data.comparison_draft as ComparisonDraft | undefined;
  if (!record || !current || !draft) return null;
  const columns = comparisonColumns(record.data.selections, record.data.comparison?.cells || []);
  const available = new Map(record.data.selections.map(ref => [researchEvidenceKey(ref), ref]));
  const canRetry = ["failed", "partial", "canceled"].includes(current.status || "");
  async function retry() {
    if (!record || !current) return;
    let id = "";
    const ok = await run(async () => { const next = await retryResearchTurn(current.id, { expected_revision: record.revision, request_id: requestId(`comparison-draft-retry:${current.id}`) }); id = next.id; }, "已新增草稿生成轮次，上一轮草稿与本人笔记保留。");
    if (ok) setChosen(id);
  }
  return <section className="stl4-comparison-search-results" aria-label="模型比较草稿">
    <header><div><strong>{states[current.status || ""] || "比较草稿"}</strong><p>生成维度：{draft.dimension} · 仅本人可见</p></div><div className="stl4-comparison-inline-actions">
      {isTaskRunning(current.status) ? <button type="button" disabled={pending} onClick={() => void run(() => cancelResearchTurn(current.id), "已取消生成。已有草稿和本人输入保留。")}>取消生成</button> : null}
      {canRetry ? <button type="button" disabled={pending || record.archived} onClick={() => void retry()}>重新生成</button> : null}
      <button type="button" disabled={pending} onClick={refresh}>{pollPaused ? "继续更新" : "刷新"}</button>
    </div></header>
    {drafts.length > 1 ? <label>生成记录<select value={current.id} onChange={event => setChosen(event.target.value)}>{drafts.map((turn, index) => <option value={turn.id} key={turn.id}>第 {index + 1} 次 · {states[turn.status || ""] || "已保存"}</option>)}</select></label> : null}
    <p>{draft.notice}</p>
    {current.status === "failed" ? <p role="alert">本轮未取得完整可用草稿。可核对本地模型服务、所选原文和材料范围后重试，原比较笔记未改动。</p> : null}
    {draft.missing_columns ? <p>本轮还有 {draft.missing_columns} 个文献列未取得有效草稿，已完成部分保留。</p> : null}
    {draft.rows.map(row => { const column = columns.find(item => item.id === row.column_id); const usable = draft.source_status === "available" && row.reference_ids.every(id => available.get(id)?.source_status === "available") && Boolean(column) && (record.data.comparison?.dimensions || []).includes(draft.dimension); return <article key={row.column_id}>
      <h3>{column?.title || "原选材列已移除"} · {row.evidence_state === "insufficient" ? "材料不足，待补证据" : "模型草稿，待本人核对"}</h3>
      <p>{row.note || "生成所用来源已变化，暂不能采用这条草稿。"}</p>
      <button type="button" className="stl4-research-secondary" disabled={pending || !usable || (record.data.comparison?.cells.length || 0) >= 200} onClick={() => onReview(draft.dimension, row)}>核对原文并编辑</button>
    </article>; })}
  </section>;
}
