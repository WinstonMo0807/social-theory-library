"use client";

import { LoadingState } from "@/components/ui/loading-state";
import { submitSearchOnEnter } from "@/lib/search-submit-key";

import Link from "next/link";
import { ArrowRight, CircleAlert, Download, GitBranch, History, LoaderCircle, LockKeyhole, Pencil, Share2, RefreshCw, Save, Search, Send, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ApiRequestError } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { researchNotesMarkdown } from "@/lib/research-notes-export";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ResearchProjectNotes } from "./research-project-notes";
import { ResearchPromptRecovery } from "./research-prompt-recovery";
import { useResearchTabDraft } from "./use-research-tab-draft";
import { ResearchTabRecovery } from "./research-tab-recovery";
import { useResearchSelectionDraft } from "./research-selection-draft";
import { ResearchEvidenceCard, ResearchEvidenceCover, researchDocumentTypes, researchEvidenceLocation } from "./research-evidence-card";
import { parsePendingResearchTurn, parseResearchBranchDraft, type PendingResearchTurn, type ResearchBranchDraft } from "@/lib/research-pending-turn";
import { cancelResearchTurn, changeResearchSelection, exportResearchRecord, lookupResearchTurnRequest, sendResearchTurnCommand, retryResearchTurn, type ResearchTurnCommand, updateResearchProject, type ProjectData, type QueryScope, type ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceKey, researchEvidenceReference, researchReaderHref, researchScopeLabel, researchScopeInput } from "@/lib/api/research-evidence";
import { isTaskRunning } from "@/lib/api/task-polling";
import { useResearchProject } from "./use-research-project";
import { ResearchMemoryReminders } from "./research-memory-reminders";

const statuses: Record<string, string> = { completed: "已完成", complete: "已完成", running: "处理中", queued: "排队中", pending: "等待中", partial: "部分完成", failed: "处理失败", canceled: "已取消", cancelled: "已取消" };
const titleOf = (ref: ResolvedEvidence, index: number) => ref.title?.trim() || `原文证据 ${index + 1}`;
const locationOf = researchEvidenceLocation;
const savedDate = (value: string) => Number.isFinite(new Date(value).getTime()) ? new Date(value).toLocaleDateString("zh-CN") : "保存时间待核对";

export function ResearchSessionDetail({ id, initialTurn = "" }: { id: string; initialTurn?: string }) {
  const workspace = useResearchProject(id, true);
  if (workspace.error || ["forbidden", "temporary_error"].includes(workspace.session.status)) {
    return <Frame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={24} /><h2>研究会话暂时不可用</h2><p>{workspace.error || workspace.session.message}</p><button onClick={workspace.refresh}><RefreshCw size={15} />重新读取</button></div></Frame>;
  }
  if (!workspace.record) return <Frame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><LoadingState>正在读取研究会话……</LoadingState></div></Frame>;
  return <Workspace key={`${workspace.session.user?.id}:${id}:${initialTurn}`} workspace={workspace} initialTurn={initialTurn} />;
}

function Workspace({ workspace, initialTurn }: { workspace: ReturnType<typeof useResearchProject>; initialTurn: string }) {
  const { record, turns, pending, run, refresh, requestId, notice, actionError, pollPaused } = workspace;
  const [submission, setSubmission] = useState<PendingResearchTurn | null>(null);
  const [localError, setLocalError] = useState("");
  const exportController = useRef<AbortController | null>(null);
  useEffect(() => () => exportController.current?.abort(), []);
  const owner = String(workspace.session.user?.id || ""), projectId = record?.id || "";
  const parsePending = useCallback((value: unknown) => parsePendingResearchTurn(value, projectId), [projectId]);
  const receipt = useResearchTabDraft({ owner, project: projectId, kind: "turn-request", value: submission, parseInput: parsePending });
  const requestLocked = pending || submission !== null || !receipt.scanned || Boolean(receipt.recovery) || Boolean(receipt.error);
  const selectionDraft = useResearchSelectionDraft(workspace, requestLocked);
  const editingLocked = requestLocked || selectionDraft.hasDraft;
  const [activeId, setActiveId] = useState(initialTurn);
  const [question, setQuestion] = useState("");
  const [scopeChoice, setScopeChoice] = useState<"saved" | "selected" | "library">("saved");
  const [pane, setPane] = useState("evidence");
  const [branchTarget, setBranchTarget] = useState<{ id: string; question: string; number: number | null; scope: QueryScope; scopeText: string } | null>(null);
  const [discardBranch, setDiscardBranch] = useState(false);
  const [branchOpen, setBranchOpen] = useState(false);
  const [branchQuestion, setBranchQuestion] = useState("");
  const branchStorage = useResearchTabDraft({ owner, project: projectId, kind: "branch-input", value: branchOpen && branchTarget && branchQuestion ? { question: branchQuestion, parent_id: branchTarget.id, scope: researchScopeInput(branchTarget.scope) } : null, parseInput: parseResearchBranchDraft });
  const [query, setQuery] = useState("");
  const [questionEditor,setQuestionEditor]=useState<{question:string;revision:number}|null>(null);
  const [onlySelected, setOnlySelected] = useState(false);
  const [documentType, setDocumentType] = useState("");
  const [sort, setSort] = useState("returned");
  useUnsavedForm({ question, branchQuestion, editingQuestion:questionEditor?.question||"", unresolved: Boolean(submission) }, { question: "", branchQuestion: "", editingQuestion:"", unresolved: false });
  const current = turns.find((turn) => turn.id === activeId) || turns.find((turn) => turn.id === record?.data.last_turn_id) || turns.at(-1);
  const selected = record?.data.selections ?? [];
  const selectedKeys = selectionDraft.selectedKeys;
  const candidates = useMemo(() => {
    const seen = new Set<string>();
    return (current?.data.result_refs ?? []).filter((ref) => { const key = researchEvidenceKey(ref); if (seen.has(key)) return false; seen.add(key); return true; });
  }, [current]);
  if (!record) return null;
  const activeStatus = current?.status || "saved";
  const documentTypes = Array.from(new Set(candidates.map(ref => ref.document_type || "unknown")));
  const shown = candidates.filter((ref) => (!onlySelected || selectedKeys.has(researchEvidenceKey(ref))) && (!documentType || (ref.document_type || "unknown") === documentType) && (!query.trim() || `${ref.title || ""} ${(ref.authors || []).join(" ")} ${ref.source_status === "available" ? ref.quote || ref.text || "" : ""}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())));
  if (sort === "year") shown.sort((a,b) => (b.publication_year || 0) - (a.publication_year || 0));
  if (sort === "title") shown.sort((a,b) => (a.title || "").localeCompare(b.title || "", "zh-CN"));
  const currentNumber = turns.findIndex((turn) => turn.id === current?.id) + 1;
  const availableSelected = selected.filter((ref) => ref.source_status === "available");
  const unavailableSelected = selected.length - availableSelected.length;
  const chosenScope: QueryScope = scopeChoice === "library" ? { kind: "library", filters: {} } : scopeChoice === "selected" ? { kind: "passages", references: availableSelected.map(researchEvidenceReference), allow_neighbors: false } : record.data.scope;
  const validScope = scopeChoice !== "selected" || availableSelected.length > 0;
  const scopeText = scopeChoice === "selected" ? `当前可用选材（${availableSelected.length}条）` : researchScopeLabel(chosenScope);

  function closeBranch() {
    if (editingLocked) return;
    if (branchQuestion.trim()) { setDiscardBranch(true); return; }
    setBranchOpen(false); setBranchTarget(null); setBranchQuestion("");
  }

  async function submit(event: FormEvent, branch = false) {
    event.preventDefault();
    if (!record || !branch && !validScope || editingLocked) return;
    const text = (branch ? branchQuestion : question).trim();
    if (text.length < 2 || branch && !branchTarget) return;
    const parentId = branch ? branchTarget?.id : current?.id;
    const scope = branch && branchTarget ? branchTarget.scope : chosenScope;
    try {
      const cleanScope = researchScopeInput(scope);
      const command: ResearchTurnCommand = { projectId: record.id,
        ...(!branch && current && JSON.stringify(current.data.scope) !== JSON.stringify(chosenScope) ? { expandTurnId: current.id } : {}),
        data: { expected_revision: record.revision, request_id: requestId(JSON.stringify({ text, scope: cleanScope, parent: parentId, branch })),
          question: text, scope: cleanScope, ...(parentId ? { parent_id: parentId } : {}), mode: "search" } };
      const attempt = parsePendingResearchTurn({ command, branch }, record.id);
      if (current) setActiveId(current.id);
      setLocalError(""); setSubmission(attempt);
      if (receipt.enabled) receipt.capture(attempt);
      if (branch && branchStorage.enabled) branchStorage.capture({ question: text, parent_id: parentId!, scope: cleanScope });
      await send(attempt);
    } catch (reason) { setLocalError(reason instanceof Error ? reason.message : "本次请求未能准备好，输入仍保留。"); }
  }
  function acceptSubmission(id: string, branch: boolean) {
    receipt.capture(null); setSubmission(null); setActiveId(id); setPane("evidence");
    if (branch) {
      const stored = branchStorage.recovery?.input;
      if (stored && stored.question.trim() === branchQuestion.trim() && stored.parent_id === branchTarget?.id && JSON.stringify(stored.scope) === JSON.stringify(researchScopeInput(branchTarget.scope))) branchStorage.clear();
      else branchStorage.capture(null);
      setBranchOpen(false); setBranchQuestion(""); setBranchTarget(null);
    } else setQuestion("");
  }
  async function send(attempt: NonNullable<typeof submission>) {
    let nextId = "", rejected = false;
    const ok = await run(async () => {
      try {
        const next = await sendResearchTurnCommand(attempt.command, String(workspace.session.user!.id));
        if (next.request_id !== attempt.command.data.request_id || next.project_id !== attempt.command.projectId) throw new Error("提交操作结果未能核对，请保留原请求后查询。");
        nextId = next.id;
      } catch (reason) {
        rejected = reason instanceof ApiRequestError && !(reason instanceof PrivateOwnerVerificationError) && reason.status >= 400 && reason.status < 500 && ![408,429].includes(reason.status);
        throw reason;
      }
    }, attempt.branch ? "已从选定轮次建立分支，原材料继续保留。" : "新的研究轮次已加入队列，进度会自动更新。");
    if (ok) acceptSubmission(nextId, attempt.branch); else if (rejected) { receipt.capture(null); setSubmission(null); }
  }
  async function lookupSubmission() {
    if (!submission) return;
    let nextId = "";
    const ok = await run(async () => {
      const found = await lookupResearchTurnRequest(submission.command.projectId, submission.command.data.request_id, String(workspace.session.user!.id));
      if (!found) throw new Error("尚未找到原请求结果，请稍后查询或重试原请求；不会改用新的请求标识。");
      nextId = found.id;
    }, "已查询原请求及研究轮次，没有重复新建。");
    if (ok) acceptSubmission(nextId, submission.branch);
  }
  async function retry() {
    if (!record || !current) return;
    let nextId = "";
    const ok = await run(async () => {
      const next = await retryResearchTurn(current.id, { expected_revision: record.revision, request_id: requestId(`retry:${current.id}`) }); nextId = next.id;
    }, "已重新排队，上一轮材料仍然保留。");
    if (ok) { setActiveId(nextId); setPane("evidence"); }
  }
  async function saveScope() {
    if (!record || editingLocked || !validScope) return;
    const ok = await run(() => updateResearchProject(record.id, { expected_revision: record.revision, scope: researchScopeInput(chosenScope) }, owner), "已保存后续研究范围，既有轮次和未发送追问保留。");
    if (ok) setScopeChoice("saved");
  }
  async function saveProjectQuestion(event:FormEvent) {
    event.preventDefault();
    if(!record||!questionEditor||editingLocked||!questionEditor.question.trim())return;
    const ok=await run(()=>updateResearchProject(record.id,{expected_revision:questionEditor.revision,question:questionEditor.question.trim()},owner),"研究问题已保存，既有轮次和材料保留。");
    if(ok)setQuestionEditor(null);
  }
  async function exportNotes() {
    if (!record || requestLocked) return;
    exportController.current?.abort();
    const controller = new AbortController(); exportController.current = controller;
    await run(async () => {
      const payload = await withPrivateOwner(owner, () => exportResearchRecord<ProjectData>("research-projects", record.id, owner, controller.signal), controller.signal);
      if (payload.id !== record.id) throw new Error("导出研究的身份无法核对，请重新读取。");
      const markdown = researchNotesMarkdown(payload);
      if (!markdown) throw new Error("这份研究还没有服务器已保存的笔记。请先保存研究笔记、选材备注或比较笔记。");
      const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `research-notes-${record.id}.md`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "已生成已保存笔记的 Markdown 下载文件；当前未保存输入未包含在内。");
  }
  function selection(ref: ResolvedEvidence, remove: boolean) {
    if (!record || selectionDraft.blocked) return;
    if (selectionDraft.shouldStage()) { selectionDraft.stage(ref, remove); return; }
    void run(() => changeResearchSelection(record.id, { expected_owner_id: Number(owner), request_id: requestId(`selection:${remove}:${researchEvidenceKey(ref)}`), expected_revision: record.revision, action: remove ? "remove" : "add", ...(remove ? { reference_id: researchEvidenceKey(ref) } : { references: [researchEvidenceReference(ref)] }) }), remove ? "已从当前选材移除。" : "已加入选材，来源身份和版本已重新核对。");
  }
  function restoreBranch(value: ResearchBranchDraft) {
    const parentIndex = turns.findIndex(turn => turn.id === value.parent_id);
    setBranchQuestion(value.question);
    setBranchTarget({ id: value.parent_id, number: parentIndex < 0 ? null : parentIndex + 1, question: turns[parentIndex]?.data.question || "原轮次信息待核对", scope: value.scope, scopeText: researchScopeLabel(value.scope) });
    setBranchOpen(true);
  }
  function restoreSubmission(value: PendingResearchTurn) {
    setSubmission(value); setLocalError("");
    if (!value.branch) setQuestion(value.command.data.question);
    else restoreBranch({ question: value.command.data.question, parent_id: value.command.data.parent_id!, scope: value.command.data.scope });
  }
  const branchControls = <ResearchTabRecovery storage={branchStorage} label="分支草稿" description="仅保留问题文字、原父轮次和范围定位，不暂存原文；恢复不会自动建立分支。" pending={editingLocked} onRestore={restoreBranch} preview={value => <p className="stl4-research-notes-copy">{value.question || "空白分支问题"} · {researchScopeLabel(value.scope)}</p>}/>;
  const receiptAtTop = Boolean(submission || receipt.recovery || receipt.error);
  const receiptControls = <ResearchTabRecovery storage={receipt} label="未确认请求" description="仅保留本次问题、范围与来源定位、原请求标识，不暂存原文或凭据。恢复后先查询，再决定是否原样重试。" pending={pending} onRestore={restoreSubmission} preview={value => <p className="stl4-research-notes-copy">{value.command.data.question} · {researchScopeLabel(value.command.data.scope)}{value.branch ? " · 分支请求" : ""}</p>} discardDescription="仅清除此标签页的查询记录，不会取消服务器可能已经接收的任务。请先在研究过程核对原轮次，避免清除后重复提交同一问题。"/>;
  const statusText = current?.data.return_context?.kind === "comparison_draft" ? "本轮为比较草稿生成。可在证据比较中查看草稿，已有选材和本人笔记保留。" : isTaskRunning(activeStatus) ? "正在核对来源与页码，已有材料仍可阅读。" : activeStatus === "partial" ? "部分检索已完成，可保留现有材料并重试。" : activeStatus === "failed" ? "本轮未完成，问题与材料已保留。" : ["canceled", "cancelled"].includes(activeStatus) ? "本轮已取消，原有轮次与选材继续保留。" : current ? "可以继续核对来源、选择材料或提出后续问题。" : "提交问题后开始第一轮研究。";
  return <Frame>
    <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/home">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><Link href="/account/research">我的研究</Link><span>/</span><strong>持续研究</strong></nav>
    <header className="stl4-research-heading stl4-research-workspace-heading"><div className="stl4-research-heading-copy"><h1>持续研究工作区 <span className="stl4-research-privacy"><LockKeyhole size={14}/>仅本人可见</span></h1></div><div className="stl4-research-workspace-tools"><button type="button" disabled={requestLocked} onClick={()=>void exportNotes()}><Download size={14}/>导出笔记</button><Link href={`/account/sharing/new?kind=research&source=${record.id}`}><Share2 size={14}/>分享</Link><Link href={`/account/research/${record.id}/history`}><History size={14}/>查看与恢复历史</Link><button type="button" disabled={editingLocked || !validScope} onClick={()=>void saveScope()}><Save size={14}/>保存当前范围</button><small>导出与历史只包含已保存资料；追问需另行发送。</small></div></header>
    <section className="stl4-research-workspace" aria-label="持续研究工作区" data-workspace-pane={pane}>

      {submission ? <div className="stl4-research-source-notice" role="status"><strong>{pending ? "正在提交原请求" : "原请求结果待核对"}</strong><p className="stl4-research-notes-copy">{submission.command.data.question}</p><p>本次问题与范围已固定。服务器可能已经接收，请先查询；重试沿用原请求，不会再建一轮。{receipt.enabled && receipt.savedAt && !receipt.error ? "已按你的允许保留本标签页恢复记录。" : "尚无已确认的本机恢复记录，离开本页可能丢失查询入口。"}</p><div className="stl4-comparison-inline-actions"><button type="button" disabled={pending} onClick={()=>void lookupSubmission()}>查询原请求</button><button type="button" disabled={pending} onClick={()=>void send(submission)}>重试原请求</button></div></div> : null}
      {receiptAtTop && !branchOpen ? receiptControls : null}
      {!branchOpen && (branchStorage.recovery || branchStorage.error) ? branchControls : null}
      {selectionDraft.panel}
      <div className={`stl4-research-status-panel status-${activeStatus}`} role="status"><div><strong>{statuses[activeStatus] || "尚未开始"}</strong><span>{statusText}</span></div><div className="stl4-research-status-actions">{current && isTaskRunning(activeStatus) ? <button disabled={requestLocked} onClick={() => void run(() => cancelResearchTurn(current.id), "本轮已取消，已取得的材料继续保留。")}>取消本轮</button> : null}{current && ["failed", "partial", "canceled", "cancelled"].includes(activeStatus) ? <button disabled={editingLocked} onClick={() => void retry()}><RefreshCw size={14} />重新检索</button> : null}<button disabled={requestLocked} onClick={refresh}><RefreshCw size={14} />{pollPaused ? "继续更新" : "刷新"}</button></div></div>
      {unavailableSelected ? <div className="stl4-research-source-notice" role="status"><strong>{unavailableSelected} 条选材的来源待重新核对</strong><p>旧引用身份和已保存笔记仍保留，不会自动换成另一版本。请在选材中核对，重新选取的材料会作为新引用保存。</p><button type="button" className="stl4-research-secondary" onClick={()=>setPane("materials")}>查看选材</button><Link href="/explore" target="_blank" rel="noreferrer">查找当前可用文献</Link></div> : null}
      <nav className="stl4-research-pane-switch" aria-label="研究工作区视图">{[["questions", "追问与范围"], ["evidence", `证据（${candidates.length}）`], ["materials", `选材（${selected.length}）`], ["notes", "笔记"]].map(([value,label])=><button type="button" key={value} aria-pressed={pane===value} onClick={()=>setPane(value)}>{label}</button>)}</nav>
      <div className="stl4-research-workspace-grid">
        <aside className="stl4-research-turns" aria-label="研究轮次"><section className="stl4-research-project-question"><header><h2>研究题目</h2><button type="button" disabled={editingLocked} onClick={()=>setQuestionEditor({question:record.data.question||record.data.title,revision:record.revision})}><Pencil size={12}/>编辑</button></header><p>{record.data.question||record.data.title||"未命名研究"}</p></section><header><h2>问题路径</h2><span>{turns.length} 轮</span></header>{turns.length ? <ol>{turns.map((turn, index) => <li key={turn.id} data-branch={Boolean(turn.parent_id&&turn.parent_id!==turns[index-1]?.id)||undefined} className={turn.id === current?.id ? "is-active" : undefined}><button type="button" aria-current={turn.id === current?.id ? "step" : undefined} onClick={() => { setActiveId(turn.id); setQuery(""); setDocumentType(""); setPane("evidence"); }}><span aria-hidden="true"/><div><b>第 {index+1} 轮{turn.id===current?.id?" · 当前":""}</b><strong>{turn.data.question || "未命名问题"}</strong><small>{statuses[turn.status || ""] || "已保存"}{turn.parent_id ? (turns.some(row=>row.id===turn.parent_id) ? ` · 承接第 ${turns.findIndex((row) => row.id === turn.parent_id) + 1} 轮` : " · 原父轮次待核对") : ""}</small><time dateTime={turn.created_at}>{savedDate(turn.created_at)}</time></div></button></li>)}</ol> : <p>从下方提交第一个研究问题。</p>}<button type="button" className="stl4-research-secondary" disabled={editingLocked || !branchStorage.scanned || Boolean(branchStorage.recovery) || Boolean(branchStorage.error) || !current || !validScope} onClick={() => { if (current && validScope) { setBranchTarget({ id: current.id, question: current.data.question, number: currentNumber, scope: chosenScope, scopeText }); setBranchQuestion(""); setBranchOpen(true); } }}><GitBranch size={13} />从本轮建立分支</button></aside>
        <div className="stl4-research-results">      <form className="stl4-research-prompt" onSubmit={(event) => void submit(event)}><label htmlFor="research-follow-up">{current ? `承接第 ${currentNumber} 轮继续提问` : "提出研究问题"}</label><div><textarea onKeyDown={submitSearchOnEnter} enterKeyHint="search" title="回车检索，Shift + 回车换行" id="research-follow-up" value={question} disabled={requestLocked} onChange={(event) => setQuestion(event.target.value)} placeholder="基于原文材料继续追问……" minLength={2} maxLength={1200} rows={2} required /><button type="submit" disabled={editingLocked || question.trim().length < 2 || !validScope}>{pending ? <LoaderCircle className="stl4-spin" size={15} /> : <Send size={15} />}发送</button></div><fieldset className="stl4-research-scope"><legend>下一轮检索范围</legend>{([["saved", "已保存的范围"], ["selected", "仅当前选材"], ["library", "扩展至全馆"]] as const).map(([value, label]) => <label key={value}><input type="radio" name="research-scope" value={value} checked={scopeChoice === value} disabled={editingLocked} onChange={() => setScopeChoice(value)} />{label}</label>)}<button type="button" className="stl4-research-text-button" disabled={editingLocked || !validScope || scopeChoice === "saved"} onClick={() => void saveScope()}>保存为后续范围</button></fieldset><p className="stl4-research-scope-caption">{scopeText}{!validScope ? " · 请先加入可用原文材料" : ""}</p><ResearchPromptRecovery owner={String(workspace.session.user!.id)} project={record.id} input={{question,scope:scopeChoice}} disabled={requestLocked} onRestore={value=>{setQuestion(value.question);setScopeChoice(value.scope);}} onReconnect={()=>{if(!editingLocked)refresh();}}/></form><div className="stl4-research-results-head"><div><p className="stl4-research-kicker">{current ? `第 ${currentNumber} 轮 · ${researchScopeLabel(current.data.scope)}` : "研究问题"}</p><h2>{current?.data.question || record.data.question || "开始一项研究"}</h2></div><Link href={`/account/research/${record.id}/counter-evidence`}>检验一个判断</Link><Link href={`/account/research/${record.id}/compare`}>打开证据比较 <ArrowRight size={14} /></Link></div>
          <div className="stl4-research-filter-row"><label className="stl4-research-result-search"><Search size={14} /><input aria-label="在本轮材料中查找" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`查找本轮材料（${candidates.length}）`} /></label><label>文献类型<select value={documentType} onChange={event=>setDocumentType(event.target.value)}><option value="">全部类型</option>{documentTypes.map(type=><option key={type} value={type}>{researchDocumentTypes[type] || "类型待核对"}</option>)}</select></label><label>排序<select value={sort} onChange={event=>setSort(event.target.value)}><option value="returned">检索顺序</option><option value="year">出版时间</option><option value="title">题名</option></select></label><label><input type="checkbox" checked={onlySelected} onChange={(event) => setOnlySelected(event.target.checked)} />仅看已选</label></div>
          {shown.length ? <div className="stl4-research-evidence-list">{shown.map((ref, index) => { const key = researchEvidenceKey(ref); const selectedAlready = selectedKeys.has(key); const href = researchReaderHref(ref, { projectId: record.id, turnId: current?.id, returnTo: `/account/research/${record.id}${current ? `?turn=${current.id}` : ""}` }); return <ResearchEvidenceCard key={key} reference={ref} index={index} href={href} selected={selectedAlready} status={selectionDraft.statusFor(key)} disabled={selectionDraft.blocked || !selectedAlready && ref.source_status !== "available"} onToggle={() => selection(ref, selectedAlready)}/>; })}</div> : <div className="stl4-research-empty"><Search size={24} /><h2>{candidates.length ? "没有匹配的材料" : isTaskRunning(activeStatus) ? "研究正在进行" : "还没有可展示的证据"}</h2><p>{candidates.length ? "可以调整关键词、文献类型或取消仅看已选。" : "提交问题后，可在这里查看原文和页码。"}</p></div>}
        </div>
        <section className="stl4-research-workspace-notes"><ResearchProjectNotes workspace={{ ...workspace, pending: requestLocked }}/> </section>
        <aside className="stl4-research-selected" aria-label="当前选材"><header><h2>当前选材</h2><span>{selected.length}</span></header>{selected.length ? <ol>{selected.map((ref, index) => <li key={researchEvidenceKey(ref)}><ResearchEvidenceCover reference={ref} small/><div><strong>{titleOf(ref, index)}</strong>{ref.source_status === "available" ? <small>{[ref.authors?.join("、"),ref.publication_year].filter(Boolean).join(" · ") || "出版信息待核对"}</small> : null}<small>{locationOf(ref)}{ref.source_status !== "available" ? " · 来源待核对" : ""}</small></div><button aria-label={`移除${titleOf(ref, index)}`} disabled={selectionDraft.blocked || Boolean(selectionDraft.statusFor(researchEvidenceKey(ref)))} onClick={() => selection(ref, true)}><X size={14} /></button></li>)}</ol> : <p>从本轮证据中选择材料。</p>}<Link className="stl4-research-secondary" href={`/account/research/${record.id}/history`}>研究过程回放 <ArrowRight size={14} /></Link><Link className="stl4-research-secondary" href={`/account/research/${record.id}/compare`}>比较当前选材 <ArrowRight size={14} /></Link><Link className="stl4-research-secondary" href={`/account/sharing/new?kind=research&source=${record.id}`}>分享或提交策划 <ArrowRight size={14} /></Link><ResearchMemoryReminders turn={current?.data} /></aside>
      </div>

      {!receiptAtTop && !branchOpen ? <details className="stl4-research-prompt-recovery"><summary>未确认请求的断网恢复设置</summary>{receiptControls}</details> : null}
      {localError ? <p className="stl4-research-action-message is-error" role="alert">{localError}</p> : null}
      {notice ? <p className="stl4-research-action-message" role="status">{notice}</p> : null}{actionError ? <p className="stl4-research-action-message is-error" role="alert">{actionError} 输入内容仍保留，请刷新状态后重试。</p> : null}
    </section>
    <Dialog open={questionEditor!==null} onRequestClose={()=>{if(!pending&&(!questionEditor||questionEditor.question===(record.data.question||record.data.title)||window.confirm("放弃尚未保存的研究问题修改？")))setQuestionEditor(null);}} className="stl4-research-dialog" aria-labelledby="project-question-title"><form onSubmit={event=>void saveProjectQuestion(event)}><h2 id="project-question-title">编辑研究题目</h2><label>研究问题<textarea maxLength={4000} required value={questionEditor?.question||""} disabled={pending} onChange={event=>setQuestionEditor(value=>value?{...value,question:event.target.value}:null)} rows={5}/></label><p>已有轮次、选材和笔记保留；后续追问继续由你单独发送。</p>{actionError?<p role="alert">{actionError}</p>:null}<footer><button type="button" disabled={pending} onClick={()=>{if(!questionEditor||questionEditor.question===(record.data.question||record.data.title)||window.confirm("放弃尚未保存的研究问题修改？"))setQuestionEditor(null);}}>取消</button><button type="submit" disabled={editingLocked||!questionEditor?.question.trim()}>保存修改</button></footer></form></Dialog>
    <Dialog open={branchOpen} onRequestClose={closeBranch} className="stl4-research-dialog" aria-labelledby="research-branch-title"><form onSubmit={(event) => void submit(event, true)}><h2 id="research-branch-title">{branchTarget?.number ? `从第 ${branchTarget.number} 轮建立分支` : "从原轮次建立分支"}</h2><p>{branchTarget?.question}</p><label htmlFor="research-branch-question">新的研究问题</label><textarea id="research-branch-question" value={branchQuestion} disabled={editingLocked} onChange={(event) => setBranchQuestion(event.target.value)} minLength={2} maxLength={1200} rows={4} required /><p>范围：{branchTarget?.scopeText}。原问题和已收集材料继续保留。</p>{localError ? <p role="alert">{localError}</p> : null}{actionError ? <p role="alert">{actionError}</p> : null}{branchOpen ? <details className="stl4-research-prompt-recovery"><summary>分支断网恢复设置</summary>{branchControls}{receiptControls}</details> : null}{submission?.branch ? <div className="stl4-comparison-inline-actions"><button type="button" disabled={pending} onClick={()=>void lookupSubmission()}>查询原请求</button><button type="button" disabled={pending} onClick={()=>void send(submission)}>重试原请求</button></div> : null}<footer><button type="button" disabled={editingLocked} onClick={closeBranch}>返回</button><button type="submit" disabled={editingLocked || !branchTarget || branchQuestion.trim().length < 2}>{pending ? "正在创建……" : "建立分支"}</button></footer></form></Dialog>
    <ConfirmDialog open={discardBranch} title="放弃尚未提交的分支问题？" description="原研究轮次、材料和笔记都会保留。本次分支问题和对应的本机草稿将清除。" confirmLabel="放弃本次填写" cancelLabel="继续填写" pending={editingLocked} onCancel={()=>setDiscardBranch(false)} onConfirm={()=>{branchStorage.clear();setDiscardBranch(false);setBranchOpen(false);setBranchQuestion("");setBranchTarget(null);}}/>
  </Frame>;
}
function Frame({ children }: { children: ReactNode }) { return <div className="stl4-research-page stl4-research-continuous"><div className="stl4-research-detail-shell">{children}</div></div>; }
