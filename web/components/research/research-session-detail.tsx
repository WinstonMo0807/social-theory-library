"use client";

import Link from "next/link";
import { ArrowRight, CircleAlert, GitBranch, LoaderCircle, RefreshCw, Search, Send, X } from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ResearchProjectNotes } from "./research-project-notes";
import { cancelResearchTurn, changeResearchSelection, expandResearchTurn, retryResearchTurn, startResearchTurn, updateResearchProject, type QueryScope, type ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceKey, researchEvidenceReference, researchReaderHref, researchScopeLabel } from "@/lib/api/research-evidence";
import { isTaskRunning } from "@/lib/api/task-polling";
import { ResearchCenterNav } from "./research-center-nav";
import { useResearchProject } from "./use-research-project";
import { ResearchMemoryReminders } from "./research-memory-reminders";

const statuses: Record<string, string> = { completed: "已完成", complete: "已完成", running: "处理中", queued: "排队中", pending: "等待中", partial: "部分完成", failed: "处理失败", canceled: "已取消", cancelled: "已取消" };
const titleOf = (ref: ResolvedEvidence, index: number) => ref.title?.trim() || `原文证据 ${index + 1}`;
const locationOf = (ref: ResolvedEvidence) => ref.pdf_page ? `PDF 第 ${ref.pdf_page} 页` : "原文段落";

export function ResearchSessionDetail({ id, initialTurn = "" }: { id: string; initialTurn?: string }) {
  const workspace = useResearchProject(id, true);
  if (workspace.error || ["forbidden", "temporary_error"].includes(workspace.session.status)) {
    return <Frame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={24} /><h2>研究会话暂时不可用</h2><p>{workspace.error || workspace.session.message}</p><button onClick={workspace.refresh}><RefreshCw size={15} />重新读取</button></div></Frame>;
  }
  if (!workspace.record) return <Frame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><p>正在读取研究会话……</p></div></Frame>;
  return <Workspace key={`${workspace.session.user?.id}:${id}:${initialTurn}`} workspace={workspace} initialTurn={initialTurn} />;
}

function Workspace({ workspace, initialTurn }: { workspace: ReturnType<typeof useResearchProject>; initialTurn: string }) {
  const { record, turns, pending, run, refresh, requestId, notice, actionError, pollPaused } = workspace;
  const [activeId, setActiveId] = useState(initialTurn);
  const [question, setQuestion] = useState("");
  const [scopeChoice, setScopeChoice] = useState<"saved" | "selected" | "library">("saved");
  const [pane, setPane] = useState("evidence");
  const [branchTarget, setBranchTarget] = useState<{ id: string; question: string; number: number; scope: QueryScope; scopeText: string } | null>(null);
  const [discardBranch, setDiscardBranch] = useState(false);
  const [branchOpen, setBranchOpen] = useState(false);
  const [branchQuestion, setBranchQuestion] = useState("");
  const [query, setQuery] = useState("");
  const [onlySelected, setOnlySelected] = useState(false);
  useUnsavedForm({ question, branchQuestion }, { question: "", branchQuestion: "" });
  const current = turns.find((turn) => turn.id === activeId) || turns.find((turn) => turn.id === record?.data.last_turn_id) || turns.at(-1);
  const selected = record?.data.selections ?? [];
  const selectedKeys = new Set(selected.map(researchEvidenceKey));
  const candidates = useMemo(() => {
    const seen = new Set<string>();
    return (current?.data.result_refs ?? []).filter((ref) => { const key = researchEvidenceKey(ref); if (seen.has(key)) return false; seen.add(key); return true; });
  }, [current]);
  if (!record) return null;
  const activeStatus = current?.status || "saved";
  const shown = candidates.filter((ref) => (!onlySelected || selectedKeys.has(researchEvidenceKey(ref))) && (!query.trim() || `${ref.title || ""} ${ref.source_status === "available" ? ref.quote || ref.text || "" : ""}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())));
  const currentNumber = turns.findIndex((turn) => turn.id === current?.id) + 1;
  const availableSelected = selected.filter((ref) => ref.source_status === "available");
  const unavailableSelected = selected.length - availableSelected.length;
  const chosenScope: QueryScope = scopeChoice === "library" ? { kind: "library", filters: {} } : scopeChoice === "selected" ? { kind: "passages", references: availableSelected.map(researchEvidenceReference), allow_neighbors: false } : record.data.scope;
  const validScope = scopeChoice !== "selected" || availableSelected.length > 0;
  const scopeText = scopeChoice === "selected" ? `当前可用选材（${availableSelected.length}条）` : researchScopeLabel(chosenScope);

  function closeBranch() {
    if (pending) return;
    if (branchQuestion.trim()) { setDiscardBranch(true); return; }
    setBranchOpen(false); setBranchTarget(null); setBranchQuestion("");
  }

  async function submit(event: FormEvent, branch = false) {
    event.preventDefault();
    if (!record || !branch && !validScope || pending) return;
    const text = (branch ? branchQuestion : question).trim();
    if (text.length < 2 || branch && !branchTarget) return;
    const parentId = branch ? branchTarget?.id : current?.id;
    const scope = branch && branchTarget ? branchTarget.scope : chosenScope;
    let nextId = "";
    if (current) setActiveId(current.id);
    const data = { expected_revision: record.revision, request_id: requestId(JSON.stringify({ text, scope, parent: parentId, branch })), question: text, scope };
    const ok = await run(async () => {
      const next = !branch && current && JSON.stringify(current.data.scope) !== JSON.stringify(chosenScope)
        ? await expandResearchTurn(current.id, data)
        : await startResearchTurn(record.id, { ...data, ...(parentId ? { parent_id: parentId } : {}), mode: "search" });
      nextId = next.id;
    }, branch ? "已从选定轮次建立分支，原有轮次和材料继续保留。" : "新的研究轮次已加入队列，进度会自动更新。" );
    if (ok) { setActiveId(nextId); setPane("evidence"); if (branch) { setBranchOpen(false); setBranchQuestion(""); setBranchTarget(null); } else setQuestion(""); }
  }
  async function retry() {
    if (!record || !current) return;
    let nextId = "";
    const ok = await run(async () => {
      const next = await retryResearchTurn(current.id, { expected_revision: record.revision, request_id: requestId(`retry:${current.id}`) }); nextId = next.id;
    }, "已重新排队，上一轮材料仍然保留。");
    if (ok) { setActiveId(nextId); setPane("evidence"); }
  }
  function selection(ref: ResolvedEvidence, remove: boolean) {
    if (!record) return;
    void run(() => changeResearchSelection(record.id, { expected_revision: record.revision, action: remove ? "remove" : "add", ...(remove ? { reference_id: researchEvidenceKey(ref) } : { references: [researchEvidenceReference(ref)] }) }), remove ? "已从当前选材移除。" : "已加入选材，来源身份和版本已重新核对。");
  }
  const statusText = isTaskRunning(activeStatus) ? "正在核对来源与页码，已有材料仍可阅读。" : activeStatus === "partial" ? "部分检索已完成，可保留现有材料并重试。" : activeStatus === "failed" ? "本轮未完成，问题与材料已保留。" : ["canceled", "cancelled"].includes(activeStatus) ? "本轮已取消，原有轮次与选材继续保留。" : current ? "可以继续核对来源、选择材料或提出后续问题。" : "提交问题后开始第一轮研究。";
  return <Frame>
    <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><Link href="/account/research">我的研究</Link><span>/</span><strong>持续研究</strong></nav>
    <header className="stl4-research-heading stl4-research-workspace-heading"><h1>持续研究工作区</h1><p>{record.data.title || record.data.question || "未命名研究"}</p><span className="stl4-research-privacy">仅本人可见 · 问题、选材和比较记录保存在此会话</span></header>
    <section className="stl4-research-workspace" aria-label="持续研究工作区" data-workspace-pane={pane}>
      <ResearchCenterNav active="research" />
      <div className={`stl4-research-status-panel status-${activeStatus}`} role="status"><div><strong>{statuses[activeStatus] || "尚未开始"}</strong><span>{statusText}</span></div><div className="stl4-research-status-actions">{current && isTaskRunning(activeStatus) ? <button disabled={pending} onClick={() => void run(() => cancelResearchTurn(current.id), "本轮已取消，已取得的材料继续保留。")}>取消本轮</button> : null}{current && ["failed", "partial", "canceled", "cancelled"].includes(activeStatus) ? <button disabled={pending} onClick={() => void retry()}><RefreshCw size={14} />重新检索</button> : null}<button disabled={pending} onClick={refresh}><RefreshCw size={14} />{pollPaused ? "继续更新" : "刷新"}</button></div></div>
      {unavailableSelected ? <div className="stl4-research-source-notice" role="status"><strong>{unavailableSelected} 条选材的来源待重新核对</strong><p>旧引用身份和已保存笔记仍保留，不会自动换成另一版本。请在选材中核对，重新选取的材料会作为新引用保存。</p><button type="button" className="stl4-research-secondary" onClick={()=>setPane("materials")}>查看选材</button><Link href="/explore" target="_blank" rel="noreferrer">查找当前可用文献</Link></div> : null}
      <nav className="stl4-research-pane-switch" aria-label="研究工作区视图">{[["questions", "问题"], ["evidence", `证据（${candidates.length}）`], ["materials", `选材（${selected.length}）`], ["notes", "笔记"]].map(([value,label])=><button type="button" key={value} aria-pressed={pane===value} onClick={()=>setPane(value)}>{label}</button>)}</nav>
      <div className="stl4-research-workspace-grid">
        <aside className="stl4-research-turns" aria-label="研究轮次"><header><h2>问题路径</h2><span>{turns.length} 轮</span></header>{turns.length ? <ol>{turns.map((turn, index) => <li key={turn.id} className={turn.id === current?.id ? "is-active" : undefined}><button type="button" aria-current={turn.id === current?.id ? "step" : undefined} onClick={() => { setActiveId(turn.id); setQuery(""); setPane("evidence"); }}><span>{index + 1}</span><div><strong>{turn.data.question || "未命名问题"}</strong><small>{statuses[turn.status || ""] || "已保存"}{turn.parent_id ? ` · 承接第 ${turns.findIndex((row) => row.id === turn.parent_id) + 1} 轮` : ""}</small></div></button></li>)}</ol> : <p>从下方提交第一个研究问题。</p>}<button type="button" className="stl4-research-secondary" disabled={pending || !current || !validScope} onClick={() => { if (current && validScope) { setBranchTarget({ id: current.id, question: current.data.question, number: currentNumber, scope: chosenScope, scopeText }); setBranchQuestion(""); setBranchOpen(true); } }}><GitBranch size={13} />从本轮建立分支</button></aside>
        <div className="stl4-research-results"><div className="stl4-research-results-head"><div><p className="stl4-research-kicker">{current ? `第 ${currentNumber} 轮 · ${researchScopeLabel(current.data.scope)}` : "研究问题"}</p><h2>{current?.data.question || record.data.question || "开始一项研究"}</h2></div><Link href={`/account/research/${record.id}/counter-evidence`}>检验一个判断</Link><Link href={`/account/research/${record.id}/compare`}>打开证据比较 <ArrowRight size={14} /></Link></div>
          <div className="stl4-research-filter-row"><label className="stl4-research-result-search"><Search size={14} /><input aria-label="在本轮材料中查找" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`查找本轮材料（${candidates.length}）`} /></label><label><input type="checkbox" checked={onlySelected} onChange={(event) => setOnlySelected(event.target.checked)} />仅看已选</label></div>
          {shown.length ? <div className="stl4-research-evidence-list">{shown.map((ref, index) => { const key = researchEvidenceKey(ref); const selectedAlready = selectedKeys.has(key); const href = researchReaderHref(ref, { projectId: record.id, turnId: current?.id, returnTo: `/account/research/${record.id}${current ? `?turn=${current.id}` : ""}` }); return <article className="stl4-research-evidence" key={key}><div className="stl4-evidence-number">{String(index + 1).padStart(2, "0")}</div><div className="stl4-evidence-copy"><h3>{titleOf(ref, index)}</h3><p>{ref.source_status === "available" ? ref.quote || ref.text || "打开原文核对这条材料。" : "来源已变化或暂不可用，保留材料身份供后续核对。"}</p><small>{locationOf(ref)} · {ref.source_status === "available" ? "可定位" : "待重新核对"}</small></div><div className="stl4-evidence-actions">{href ? <Link href={href}>查看原文 <ArrowRight size={14} /></Link> : null}<button type="button" aria-pressed={selectedAlready} className={selectedAlready ? "is-selected" : undefined} disabled={pending || !selectedAlready && ref.source_status !== "available"} onClick={() => selection(ref, selectedAlready)}>{selectedAlready ? "已选 · 移除" : "加入选材"}</button></div></article>; })}</div> : <div className="stl4-research-empty"><Search size={24} /><h2>{candidates.length ? "没有匹配的材料" : isTaskRunning(activeStatus) ? "研究正在进行" : "还没有可展示的证据"}</h2><p>{candidates.length ? "可以调整关键词或取消仅看已选。" : "提交或继续问题后，真实来源和页码会出现在这里。"}</p></div>}
        </div>
        <section className="stl4-research-workspace-notes"><ResearchProjectNotes workspace={workspace}/></section>
        <aside className="stl4-research-selected" aria-label="当前选材"><header><h2>当前选材</h2><span>{selected.length}</span></header>{selected.length ? <ol>{selected.map((ref, index) => <li key={researchEvidenceKey(ref)}><div><strong>{titleOf(ref, index)}</strong><small>{locationOf(ref)}{ref.source_status !== "available" ? " · 来源待核对" : ""}</small></div><button aria-label={`移除${titleOf(ref, index)}`} disabled={pending} onClick={() => selection(ref, true)}><X size={14} /></button></li>)}</ol> : <p>从本轮证据中选择材料。</p>}<Link className="stl4-research-secondary" href={`/account/research/${record.id}/history`}>研究过程回放 <ArrowRight size={14} /></Link><Link className="stl4-research-secondary" href={`/account/research/${record.id}/compare`}>比较当前选材 <ArrowRight size={14} /></Link><Link className="stl4-research-secondary" href={`/account/sharing/new?kind=research&source=${record.id}`}>分享或提交策划 <ArrowRight size={14} /></Link><ResearchMemoryReminders turn={current?.data} /></aside>
      </div>
      <form className="stl4-research-prompt" onSubmit={(event) => void submit(event)}><label htmlFor="research-follow-up">{current ? `承接第 ${currentNumber} 轮继续提问` : "提出研究问题"}</label><div><textarea id="research-follow-up" value={question} disabled={pending} onChange={(event) => setQuestion(event.target.value)} placeholder="基于原文材料继续追问……" minLength={2} maxLength={1200} rows={2} required /><button type="submit" disabled={pending || question.trim().length < 2 || !validScope}>{pending ? <LoaderCircle className="stl4-spin" size={15} /> : <Send size={15} />}发送</button></div><fieldset className="stl4-research-scope"><legend>下一轮检索范围</legend>{([["saved", "已保存的范围"], ["selected", "仅当前选材"], ["library", "扩展至全馆"]] as const).map(([value, label]) => <label key={value}><input type="radio" name="research-scope" value={value} checked={scopeChoice === value} disabled={pending} onChange={() => setScopeChoice(value)} />{label}</label>)}<button type="button" className="stl4-research-text-button" disabled={pending || !validScope || scopeChoice === "saved"} onClick={() => void run(() => updateResearchProject(record.id, { expected_revision: record.revision, scope: chosenScope }), "已保存后续研究范围，既有轮次不变。").then((ok) => { if (ok) setScopeChoice("saved"); })}>保存为后续范围</button></fieldset><p className="stl4-research-scope-caption">{scopeText}{!validScope ? " · 请先加入可用原文材料" : ""}</p></form>
      {notice ? <p className="stl4-research-action-message" role="status">{notice}</p> : null}{actionError ? <p className="stl4-research-action-message is-error" role="alert">{actionError} 输入内容仍保留，请刷新状态后重试。</p> : null}
    </section>
    <Dialog open={branchOpen} onRequestClose={closeBranch} className="stl4-research-dialog" aria-labelledby="research-branch-title"><form onSubmit={(event) => void submit(event, true)}><h2 id="research-branch-title">从第 {branchTarget?.number} 轮建立分支</h2><p>{branchTarget?.question}</p><label htmlFor="research-branch-question">新的研究问题</label><textarea id="research-branch-question" value={branchQuestion} disabled={pending} onChange={(event) => setBranchQuestion(event.target.value)} minLength={2} maxLength={1200} rows={4} required /><p>范围：{branchTarget?.scopeText}。原问题和已收集材料继续保留。</p>{actionError ? <p role="alert">{actionError}</p> : null}<footer><button type="button" disabled={pending} onClick={closeBranch}>返回</button><button type="submit" disabled={pending || !branchTarget || branchQuestion.trim().length < 2}>{pending ? "正在创建……" : "建立分支"}</button></footer></form></Dialog>
    <ConfirmDialog open={discardBranch} title="放弃尚未提交的分支问题？" description="原研究轮次、材料和笔记都会保留。" confirmLabel="放弃本次填写" cancelLabel="继续填写" pending={pending} onCancel={()=>setDiscardBranch(false)} onConfirm={()=>{setDiscardBranch(false);setBranchOpen(false);setBranchQuestion("");setBranchTarget(null);}}/>
  </Frame>;
}
function Frame({ children }: { children: ReactNode }) { return <div className="stl4-research-page"><div className="stl4-research-detail-shell">{children}</div></div>; }
