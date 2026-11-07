"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { ArrowRight, Check, FileText, LockKeyhole, RefreshCw, X } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import type { Paginated } from "@/lib/api/pagination";
import { commandCitationAudit, createCitationAudit, type AuditCapabilities, type AuditCheck, type AuditData, type ResearchRecord } from "@/lib/api/research.client";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { isTaskRunning } from "@/lib/api/task-polling";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { AuditBreadcrumb, AuditFrame, AuditGate, AuditProgress, auditStatuses } from "./citation-audit-shared";
import { CitationPrivateSourcePicker } from "./citation-private-sources";

const DEFAULT_CHECKS: AuditCheck[] = ["citation_identification", "bibliography_identity", "version_page"];
const MAX_UPLOAD_BYTES = 12 * 1024 * 1024;
// Fixed interface copy from final PDF 208; availability still comes from the API.
const CHECK_COPY: Record<string, { label: string; description: string }> = {
  citation_identification: { label: "引文识别", description: "识别文中引文与参考文献条目" },
  bibliography_identity: { label: "书目身份", description: "匹配馆藏与版本来源，确认书目信息" },
  version_page: { label: "版本页码", description: "核对版本与页码准确性" },
  scan_ocr: { label: "扫描文字识别", description: "提取全文图文内容" },
  deep_analysis: { label: "深入分析", description: "分析引文的准确性与完整性" },
};
const SCOPE_COPY: Record<string, { label: string; description: string }> = {
  private_materials: { label: "馆藏及本人选定材料", description: "在本馆藏资源范围内，并包含您选定的个人文献（不对外公开）。" },
  public_library: { label: "仅馆藏资源", description: "仅使用本馆藏资源检查。" },
};

function fileSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}

export function CitationAuditUpload() {
  return <AuditGate next="/account/citation-audits">{(ownerId, retrySession) => <AuditUploadWorkspace ownerId={ownerId} retrySession={retrySession} />}</AuditGate>;
}

function AuditUploadWorkspace({ ownerId, retrySession }: { ownerId: string; retrySession: () => void }) {
  const [page, setPage] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [checks, setChecks] = useState<AuditCheck[]>(DEFAULT_CHECKS);
  const [scope, setScope] = useState("public_library");
  const [privateSourceIds, setPrivateSourceIds] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [identityError, setIdentityError] = useState("");
  const [submitted, setSubmitted] = useState<{ id: string; fingerprint: string } | null>(null);
  const [action, setAction] = useState("");
  const [actionError, setActionError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const alive = useRef(false);
  const pending = useRef(false);
  const request = useRef<{ file: File | null; fingerprint: string; id: string }>({ file: null, fingerprint: "", id: "" });
  const capabilities = usePersistentWorkspace<AuditCapabilities>("/reading/citation-audits/capabilities/", ownerId);
  const tasks = usePersistentWorkspace<Paginated<ResearchRecord<AuditData>>>(`/reading/citation-audits/?page=${page}`, ownerId,
    data => data.results.some(row => isTaskRunning(row.status)) ? 3000 : null);

  useEffect(() => {
    alive.current = true;
    const clearPrivateInput = () => {
      alive.current = false;
      request.current = { file: null, fingerprint: "", id: "" };
      setFile(null); setPrivateSourceIds([]); setSubmitted(null); setError(""); setActionError(""); setBusy(false);
      if (input.current) input.current.value = "";
    };
    let verifying = false;
    const verify = async () => {
      if (!alive.current || verifying || document.visibilityState !== "visible") return;
      verifying = true;
      try { await withPrivateOwner(ownerId, async () => undefined); }
      catch (reason) {
        if (!alive.current) return;
        clearPrivateInput();
        setIdentityError(reason instanceof Error ? reason.message : "登录状态暂时无法验证，请重新登录后继续。");
      } finally { verifying = false; }
    };
    const off = subscribeToSessionChanges(clearPrivateInput);
    window.addEventListener("focus", verify);
    window.addEventListener("pageshow", verify);
    document.addEventListener("visibilitychange", verify);
    return () => { alive.current = false; off(); window.removeEventListener("focus", verify); window.removeEventListener("pageshow", verify); document.removeEventListener("visibilitychange", verify); };
  }, [ownerId]);

  const options = (capabilities.data?.checks || []).map(option => ({ ...option, ...CHECK_COPY[option.id] }));
  const scopes = [...(capabilities.data?.scopes || [])].sort((a, b) => Number(b.id === "private_materials") - Number(a.id === "private_materials")).map(option => ({ ...option, ...SCOPE_COPY[option.id] }));
  const enabledChecks = checks.filter(check => options.some(option => option.id === check && option.available));
  const fingerprint = JSON.stringify({ checks: enabledChecks, scope, private_source_ids: scope === "private_materials" ? [...privateSourceIds].sort() : [] });
  const alreadySubmitted = submitted?.fingerprint === fingerprint;
  const limit = Math.min(MAX_UPLOAD_BYTES, capabilities.data?.max_upload_bytes || MAX_UPLOAD_BYTES);
  const allChecked = options.filter(option => option.available && option.id !== "deep_analysis").every(option => enabledChecks.includes(option.id as AuditCheck));
  const selectedTask = submitted ? tasks.data?.results.find(row => row.id === submitted.id) : undefined;

  function chooseFile(candidate?: File) {
    if (!candidate || pending.current || !alive.current) return;
    if (!/\.(pdf|docx)$/i.test(candidate.name)) { setError("请选择 PDF 或 DOCX 文件，原先选择的文件仍保留。"); return; }
    if (candidate.size === 0 || candidate.size > limit) { setError(`请选择大小大于 0 且不超过 ${fileSize(limit)} 的稿件。`); return; }
    setFile(candidate); setError(""); setSubmitted(null);
    request.current = { file: null, fingerprint: "", id: "" };
  }

  function dropped(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); setDragging(false);
    if (event.dataTransfer.files.length > 1) { setError("每个任务只接收一份稿件，请逐份提交。"); return; }
    chooseFile(event.dataTransfer.files[0]);
  }

  function toggleCheck(check: AuditCheck, selected: boolean) {
    setChecks(previous => {
      const next = new Set(previous);
      if (selected) { next.add(check); if (check === "version_page") next.add("bibliography_identity"); }
      else { next.delete(check); if (check === "bibliography_identity") next.delete("version_page"); }
      return Array.from(next);
    });
  }

  function handleFailure(reason: unknown, fallback: string, actionFailure = false) {
    if (reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403].includes(reason.status)) {
      alive.current = false; setFile(null); setSubmitted(null);
      request.current = { file: null, fingerprint: "", id: "" };
      if (input.current) input.current.value = "";
      setIdentityError(reason instanceof Error ? reason.message : "登录状态已变化，请重新验证。");
      return;
    }
    const message = reason instanceof Error ? reason.message : fallback;
    if (actionFailure) setActionError(message); else setError(message);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !capabilities.data || pending.current || !alive.current || alreadySubmitted) return;
    if (!enabledChecks.includes("citation_identification") || !capabilities.data.scopes.some(option => option.id === scope && option.available)) {
      setError("当前检查项或来源范围不可用，请重新读取可用能力后提交。"); return;
    }
    if (scope === "private_materials" && !privateSourceIds.length) { setError("请明确勾选至少一份已解析的本人来源，或选择仅馆藏范围。"); return; }
    pending.current = true; setBusy(true); setError("");
    if (request.current.file !== file || request.current.fingerprint !== fingerprint) request.current = { file, fingerprint, id: createRequestKey() };
    try {
      const record = await withPrivateOwner(ownerId, () => createCitationAudit(file, request.current.id, undefined, { checks: enabledChecks, scope, private_source_ids: scope === "private_materials" ? privateSourceIds : [] }));
      if (!alive.current) return;
      setSubmitted({ id: record.id, fingerprint }); setPage(1); tasks.reload();
    } catch (reason) { if (alive.current) handleFailure(reason, "稿件未能提交，文件与检查项仍保留，请重试。"); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }

  async function command(record: ResearchRecord<AuditData>, kind: "cancel" | "retry") {
    if (pending.current || !alive.current) return;
    pending.current = true; setAction(record.id); setActionError("");
    try {
      await withPrivateOwner(ownerId, () => commandCitationAudit(record.id, { action: kind, expected_revision: record.revision }));
      if (alive.current) tasks.reload();
    } catch (reason) {
      if (!alive.current) return;
      handleFailure(reason, "任务操作未完成，已保存的结果仍保留。", true);
      if (reason instanceof ApiRequestError && reason.status === 409) tasks.reload();
    } finally { pending.current = false; if (alive.current) setAction(""); }
  }

  if (identityError) return <AuditFrame><div className="stl4-research-state" role="alert"><h2>登录状态需要重新验证</h2><p>{identityError}</p><button type="button" onClick={retrySession}>重新验证登录</button></div></AuditFrame>;

  return <AuditFrame className="stl4-audit-upload-page">
    <AuditBreadcrumb />
    <header className="stl4-audit-upload-heading"><h1>引文体检：提交与任务</h1></header>
    <div className="stl4-audit-upload-grid">
      <form className="stl4-audit-upload-form" onSubmit={submit} aria-busy={busy}>
        <section aria-labelledby="audit-upload-title">
          <h2 id="audit-upload-title" className="stl4-audit-step-title"><span>1</span>上传稿件</h2>
          <div className={`stl4-audit-dropzone${dragging ? " is-dragging" : ""}`} onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={dropped}>
            <FileText size={48} strokeWidth={1.1} aria-hidden="true" /><strong><span className="stl4-audit-desktop-upload-copy">拖拽文件到此处，或点击上传</span><span className="stl4-audit-mobile-upload-copy">点击上传文件</span></strong>
            <p>支持 PDF、DOCX（最大 {Number((limit / 1024 / 1024).toFixed(2))} MiB）<br />仅本人可见，不进入公共馆藏。</p>
            <input ref={input} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" aria-label="选择待检查稿件" disabled={busy || Boolean(action)} onChange={event => chooseFile(event.target.files?.[0])} />
            <button type="button" className="is-primary" disabled={busy || Boolean(action)} onClick={() => input.current?.click()}>{file ? "更换文件" : "选择文件"}</button>
          </div>
          {file ? <>
            <div className="stl4-audit-selected-file"><FileText size={25} aria-hidden="true" /><div><strong>{file.name}</strong><span>{fileSize(file.size)}</span></div><button type="button" aria-label="移除已选稿件" disabled={busy || Boolean(action)} onClick={() => { setFile(null); setSubmitted(null); setError(""); request.current = { file: null, fingerprint: "", id: "" }; if (input.current) input.current.value = ""; }}><X size={16} /></button></div>
            <div className="stl4-audit-manuscript-stats"><h3>稿件概况 <span>（仅显示字数与段落数）</span></h3><dl><div><dt>段落数</dt><dd>{selectedTask?.data.manuscript_stats?.paragraph_count?.toLocaleString("zh-CN") ?? "待解析"}</dd></div><div><dt>字数</dt><dd>{selectedTask?.data.manuscript_stats?.char_count?.toLocaleString("zh-CN") ?? "待解析"}</dd></div></dl></div>
          </> : null}
        </section>
        <section aria-labelledby="audit-checks-title">
          <div className="stl4-audit-step-heading"><h2 id="audit-checks-title" className="stl4-audit-step-title"><span>2</span>选择检查项</h2><p>选择需要的检查项，按需进行。</p><label className="stl4-audit-select-all"><input type="checkbox" checked={Boolean(options.length) && allChecked} disabled={!options.length || busy || Boolean(action)} onChange={event => setChecks(options.filter(option => option.available && option.id !== "deep_analysis" && (event.target.checked || option.required)).map(option => option.id as AuditCheck))} />全选</label></div>
          {capabilities.loading ? <p className="stl4-audit-upload-notice" role="status">正在读取当前可用的检查项…</p> : capabilities.error ? <div className="stl4-audit-upload-error" role="alert"><p>{capabilities.error}</p><button type="button" onClick={capabilities.reload}>重新读取检查项</button></div> : <>
            <div className="stl4-audit-check-options">{options.map(option => <label key={option.id} className={`${!option.available ? "is-unavailable" : ""}${enabledChecks.includes(option.id as AuditCheck) ? " is-selected" : ""}`}><input type="checkbox" checked={enabledChecks.includes(option.id as AuditCheck)} disabled={!option.available || option.required || busy || Boolean(action) || option.id === "deep_analysis"} onChange={event => toggleCheck(option.id as AuditCheck, event.target.checked)} /><span><strong>{option.label}</strong><small>{option.description}</small>{!option.available ? <em>暂未开放</em> : null}</span></label>)}</div>
            <p className="stl4-audit-upload-notice">基础核对可提交；扫描识别与深入分析按服务能力开放。</p>
          </>}
        </section>
        <section aria-labelledby="audit-scope-title">
          <h2 id="audit-scope-title" className="stl4-audit-step-title"><span>3</span>选择来源范围</h2>
          <div className="stl4-audit-scope-options">{scopes.map(option => <label key={option.id} className={!option.available ? "is-unavailable" : ""}><input type="radio" name="audit-scope" value={option.id} checked={scope === option.id && option.available} disabled={!option.available || busy || Boolean(action)} onChange={() => setScope(option.id)} /><span><strong>{option.label}</strong><small>{option.description}</small></span></label>)}</div>
          {scope === "private_materials" ? <CitationPrivateSourcePicker ownerId={ownerId} selectedIds={privateSourceIds} onChange={setPrivateSourceIds} disabled={busy || Boolean(action)} /> : null}
        </section>
        {error ? <div className="stl4-audit-upload-error" role="alert">{error}</div> : null}
        {submitted && alreadySubmitted ? <div className="stl4-audit-upload-success" role="status"><Check size={16} />稿件已提交，任务和解析结果会持续保存。<Link href={`/account/citation-audits/${submitted.id}/parse`}>查看任务 <ArrowRight size={13} /></Link></div> : null}
        <div className="stl4-audit-upload-submit"><button type="submit" className="is-primary" disabled={!file || !capabilities.data || Boolean(capabilities.error) || busy || Boolean(action) || alreadySubmitted}>{busy ? "正在提交稿件…" : alreadySubmitted ? "已提交检查" : "提交检查"}<ArrowRight size={20} /></button></div>
      </form>
      <aside className="stl4-audit-upload-tasks" aria-labelledby="audit-tasks-title">
        <header><h2 id="audit-tasks-title">我的任务{tasks.data ? `（${tasks.data.count}）` : ""}</h2><span><LockKeyhole size={12} />仅本人可见</span><button type="button" aria-label="刷新任务列表" disabled={tasks.loading || busy || Boolean(action)} onClick={tasks.reload}><RefreshCw size={14} /></button></header>
        {tasks.error ? <div className="stl4-audit-upload-error" role="alert"><p>{tasks.error}</p><button type="button" onClick={tasks.reload}>{tasks.pollPaused ? "继续读取进度" : "重新读取任务"}</button></div> : null}
        {actionError ? <p className="stl4-audit-upload-error" role="alert">{actionError}</p> : null}
        {tasks.loading ? <LoadingState className="stl4-audit-upload-empty" role="status">正在读取任务…</LoadingState> : tasks.data?.results.length ? <div className="stl4-audit-task-list">{tasks.data.results.map(record => <article key={record.id} className="stl4-audit-task">
          <div className="stl4-audit-task-file"><FileText size={23} aria-hidden="true" /><div><h3>{record.data.filename}</h3><p>{typeof record.data.file_size_bytes === "number" ? fileSize(record.data.file_size_bytes) : record.data.filetype?.toUpperCase()}<time dateTime={record.created_at}>{new Date(record.created_at).toLocaleDateString("zh-CN")}</time></p></div></div>
          {isTaskRunning(record.status) ? <AuditProgress record={record} /> : <div className={`stl4-audit-task-status${record.status === "completed" ? " is-complete" : ""}`}><span aria-hidden="true">{record.status === "completed" ? <Check size={15} /> : "·"}</span><strong>{auditStatuses[record.status || ""] || "任务已保存"}</strong></div>}
          {record.status === "partial" ? <p className="stl4-audit-task-hint">已解析内容保留，未识别或未匹配的部分可在报告中继续核对。</p> : record.status === "failed" ? <p className="stl4-audit-task-hint">本次处理未完成，已保存结果保留。可以重试或先查看。</p> : null}
          <div className="stl4-audit-task-actions"><Link href={`/account/citation-audits/${record.id}${isTaskRunning(record.status) ? "/parse" : ""}`}>{isTaskRunning(record.status) ? "查看任务" : record.status === "completed" || record.status === "partial" ? "查看报告" : "查看已保存结果"}</Link>{isTaskRunning(record.status) ? <button type="button" className="is-cancel" disabled={Boolean(action) || busy} onClick={() => void command(record, "cancel")}>{action === record.id ? "正在取消…" : "取消任务"}</button> : ["failed", "canceled", "cancelled", "partial"].includes(record.status || "") ? <button type="button" disabled={Boolean(action) || busy} onClick={() => void command(record, "retry")}>{action === record.id ? "正在重试…" : "重试任务"}</button> : null}</div>
        </article>)}</div> : !tasks.error ? <div className="stl4-audit-upload-empty"><FileText size={26} aria-hidden="true" /><h3>还没有引文体检任务</h3><p>上传稿件并选择检查项，任务会保存在这里。</p></div> : null}
        {tasks.data && (page > 1 || tasks.data.next) ? <nav className="stl4-audit-task-pagination" aria-label="任务分页"><button type="button" disabled={page <= 1 || Boolean(action)} onClick={() => setPage(value => Math.max(1, value - 1))}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!tasks.data.next || Boolean(action)} onClick={() => setPage(value => value + 1)}>下一页</button></nav> : null}
        <p className="stl4-audit-upload-notice">本地服务处理，会使用设备资源。取消后保留已完成结果。</p>
      </aside>
    </div>
  </AuditFrame>;
}
