"use client";
import { submitSearchOnEnter } from "@/lib/search-submit-key";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Search, RefreshCw } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { cancelResearchTurn, changeResearchSelection, retryResearchTurn, startResearchTurn, type QueryScope } from "@/lib/api/research.client";
import { researchEvidenceKey, researchEvidenceReference, researchReaderHref } from "@/lib/api/research-evidence";
import { isTaskRunning } from "@/lib/api/task-polling";
import type { useResearchProject } from "./use-research-project";

type Workspace = ReturnType<typeof useResearchProject>;
export type ComparisonSearchTarget = { dimension: string; columnId?: string; title?: string };
const states: Record<string, string> = { queued: "等待检索", running: "正在寻找材料", completed: "本轮检索已完成", partial: "部分材料已取得", failed: "本轮检索未完成", canceled: "本轮已取消" };

export function ResearchComparisonSearch({ workspace, target, onClose }: { workspace: Workspace; target: ComparisonSearchTarget; onClose: () => void }) {
  const { record, turns, pending, run, requestId, actionError } = workspace;
  const initial = target.dimension ? `围绕“${target.dimension}”寻找可用于比较的原文证据${target.title ? `，重点核对《${target.title}》` : ""}。` : (record?.data.question || "");
  const [baseline] = useState(initial.length <= 1200 ? initial : "");
  const [question, setQuestion] = useState(baseline);
  const [scope, setScope] = useState<"library" | "works">("library");
  const [discard, setDiscard] = useState(false);
  useUnsavedForm([question, scope], [baseline, "library"]);
  if (!record) return null;
  const works = [...new Set(record.data.selections.filter(ref => ref.source_status === "available" && ref.work_id).map(ref => ref.work_id!))];
  const parent = turns.find(turn => turn.id === record.data.last_turn_id);
  const valid = question.trim().length >= 2 && question.length <= 1200 && (scope === "library" || works.length > 0);
  function close() {
    if (pending) return;
    if (question !== baseline || scope !== "library") setDiscard(true); else onClose();
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!record || !valid || pending) return;
    const chosen: QueryScope = scope === "library" ? { kind: "library", filters: {} } : { kind: "works", filters: { work_ids: works } };
    const data = { question: question.trim(), scope: chosen, mode: "search" as const,
      ...(parent ? { parent_id: parent.id } : {}),
      return_context: { kind: "comparison_gap", dimension: target.dimension, ...(target.columnId ? { column_id: target.columnId } : {}) } };
    const ok = await run(() => startResearchTurn(record.id, { ...data, expected_revision: record.revision,
      request_id: requestId(JSON.stringify(data)) }), "寻找新证据的轮次已保存。旧选材和比较笔记保留，新结果需要逐条核对后加入。");
    if (ok) onClose();
  }
  return <>
    <Dialog open onRequestClose={close} className="stl4-research-dialog" aria-labelledby="comparison-search-title">
      <form onSubmit={event => void submit(event)}>
        <h2 id="comparison-search-title">扩展寻找新证据</h2>
        {target.dimension ? <p>比较维度：{target.dimension}{target.title ? ` · ${target.title}` : ""}</p> : null}
        <label htmlFor="comparison-search-question">需要补充什么材料？</label>
        <textarea onKeyDown={submitSearchOnEnter} enterKeyHint="search" title="回车检索，Shift + 回车换行" id="comparison-search-question" value={question} onChange={event => setQuestion(event.target.value)} minLength={2} maxLength={1200} rows={4} required disabled={pending}/>
        <fieldset className="stl4-comparison-search-scope"><legend>本轮检索范围</legend>
          <label><input type="radio" name="comparison-search-scope" checked={scope === "library"} disabled={pending} onChange={() => setScope("library")}/>全馆可访问文献</label>
          <label><input type="radio" name="comparison-search-scope" checked={scope === "works"} disabled={pending || !works.length} onChange={() => setScope("works")}/>已选作品的可访问版本（{works.length}部）</label>
        </fieldset>
        <p>检索会新增研究轮次，保留旧结果。选定作品范围包含其可访问版本，结果不会自动填入比较格，也不会改写你的判断。</p>
        {actionError ? <p role="alert">{actionError} 输入仍保留。<button type="button" disabled={pending} onClick={workspace.refresh}>刷新状态后重试</button></p> : null}
        <footer><button type="button" disabled={pending} onClick={close}>返回</button><button type="submit" disabled={pending || !valid}>{pending ? "正在提交……" : "开始寻找"}</button></footer>
      </form>
    </Dialog>
    <ConfirmDialog open={discard} title="放弃尚未提交的问题？" description="已保存的研究、选材和比较记录仍会保留。" confirmLabel="放弃本次填写" cancelLabel="继续填写" onCancel={() => setDiscard(false)} onConfirm={onClose}/>
  </>;
}

export function ResearchComparisonActivity({ workspace }: { workspace: Workspace }) {
  const { record, turns, pending, run, requestId, refresh, pollPaused } = workspace;
  const [selectedTurn, setSelectedTurn] = useState("");
  const rows = turns.filter(turn => turn.data.return_context?.kind === "comparison_gap");
  const current = rows.find(turn => turn.id === selectedTurn) || rows.at(-1);
  if (!record || !current) return null;
  const selected = new Set(record.data.selections.map(researchEvidenceKey));
  const references = [...new Map((current.data.result_refs || []).map(ref => [researchEvidenceKey(ref), ref])).values()];
  const running = isTaskRunning(current.status);
  async function retry() {
    if (!record || !current) return;
    let nextId = "";
    const ok = await run(async () => { const next = await retryResearchTurn(current.id, { expected_revision: record.revision,
      request_id: requestId(`comparison-retry:${current.id}`) }); nextId = next.id; }, "新轮次已排队，上一轮材料继续保留。");
    if (ok) setSelectedTurn(nextId);
  }
  return <section className="stl4-comparison-search-results" aria-label="寻找新证据的进度">
    <header><div><strong>{states[current.status || ""] || "研究轮次"}</strong><p>{current.data.question}</p></div>
      <div className="stl4-comparison-inline-actions">
        {running ? <button type="button" disabled={pending} onClick={() => void run(() => cancelResearchTurn(current.id), "已取消本轮，已取得的材料继续保留。")}>取消本轮</button> : ["failed", "partial", "canceled"].includes(current.status || "") ? <button type="button" disabled={pending} onClick={() => void retry()}>重新检索</button> : null}
        <button type="button" disabled={pending} onClick={refresh}><RefreshCw size={13}/>{pollPaused ? "继续更新" : "刷新"}</button>
      </div>
    </header>
    {rows.length > 1 ? <label>补充检索轮次<select value={current.id} onChange={event => setSelectedTurn(event.target.value)}>{rows.map((turn, index) => <option key={turn.id} value={turn.id}>{index + 1} · {turn.data.question}</option>)}</select></label> : null}
    <details><summary><Search size={13}/>本轮材料（{references.length}）· 核对后加入选材</summary>
      {references.map(ref => { const key = researchEvidenceKey(ref), added = selected.has(key), href = researchReaderHref(ref); return <article key={key}>
        <h3>{ref.title || "原文证据"}</h3><p>{ref.source_status === "available" ? ref.quote || ref.text || "请打开原文核对。" : "来源暂不可用，保留原引用身份。"}</p>
        <div className="stl4-comparison-inline-actions">{href ? <Link href={href} target="_blank" rel="noreferrer">查看原文</Link> : null}
          <button type="button" disabled={pending || added || ref.source_status !== "available"} onClick={() => void run(() => changeResearchSelection(record.id, { expected_revision: record.revision, expected_owner_id: workspace.session.user?.id,
            request_id: requestId(`comparison-selection:${record.id}:${key}`), action: "add", references: [researchEvidenceReference(ref)] }), "已加入当前选材。请在对应比较格中明确选入依据，已有判断继续保留。")}>{added ? "已加入选材" : "加入选材"}</button>
        </div>
      </article>; })}
      {!references.length ? <p>{running ? "仍在寻找材料，已有比较可以继续阅读。" : "本轮没有取得可展示的材料，可调整问题或检索范围后继续。没有结果不代表观点不成立。"}</p> : null}
    </details>
    <Link href={`/account/research/${record.id}?turn=${current.id}`}>在持续研究中查看完整轮次 →</Link>
  </section>;
}
