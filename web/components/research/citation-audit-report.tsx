"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Download, FileText, RefreshCw, Search } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { subscribeToSessionChanges } from "@/lib/api";
import { commandCitationAudit, downloadAuditOriginal, exportResearchRecord, type AuditData, type AuditDecision, type ResearchRecord } from "@/lib/api/research.client";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useResearchRecord } from "@/lib/api/use-persistent-workspace";
import { isTaskRunning } from "@/lib/api/task-polling";
import { AuditBreadcrumb, AuditEvidenceNotice, AuditFrame, AuditGate, AuditProgress, auditCategories, auditCategory, auditDecisions, auditLocation, type AuditCategory } from "./citation-audit-shared";
import { CitationManuscriptPreview } from "./citation-manuscript-preview";
import { CitationAuditPrint } from "./citation-audit-print";
import { CitationAuditVersions } from "./citation-audit-versions";

export type AuditCommand = Omit<Parameters<typeof commandCitationAudit>[1], "expected_revision">;
const message = (reason: unknown) => reason instanceof Error ? reason.message : "操作未完成，请重试。";

export function useAuditWorkspace(id: string, ownerId: string) {
  const workspace = useResearchRecord<AuditData>("citation-audits", id, ownerId);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [externalBusy, setExternalBusy] = useState(false);
  const [printRecord, setPrintRecord] = useState<ResearchRecord<AuditData> | null>(null);
  const alive = useRef(false);
  const hasRecord = Boolean(workspace.data);
  useEffect(() => { alive.current = true; const off = subscribeToSessionChanges(() => { alive.current = false; setActionError(""); setNotice(""); setPrintRecord(null); document.body.classList.remove("stl4-print-audit"); }); return () => { alive.current = false; off(); }; }, []);
  useEffect(() => {
    if (!printRecord) return;
    const cleanup = () => { document.body.classList.remove("stl4-print-audit"); setPrintRecord(null); };
    if (hasRecord) document.body.classList.add("stl4-print-audit");
    const frame = requestAnimationFrame(() => {
      if (!alive.current || !hasRecord) { cleanup(); return; }
      try { window.print(); } catch (reason) { setActionError(message(reason)); cleanup(); }
    });
    window.addEventListener("afterprint", cleanup);
    return () => { cancelAnimationFrame(frame); document.body.classList.remove("stl4-print-audit"); window.removeEventListener("afterprint", cleanup); };
  }, [printRecord, hasRecord]);
  async function command(data: AuditCommand, revision = workspace.data?.revision) {
    if (!revision || workspace.pending || externalBusy || !alive.current) return false;
    setActionError(""); setNotice("");
    try {
      const result = await workspace.mutate(JSON.stringify(data), () => commandCitationAudit(id, { ...data, expected_revision: revision }));
      if (!result || !alive.current) return false;
      setNotice(data.action === "decision" ? "人工决定已保存。原稿未被修改。" : data.action === "cancel" ? "任务已取消，已完成结果保留。" : "已提交，任务进度会自动更新。");
      return true;
    } catch (reason) { if (alive.current) setActionError(message(reason)); return false; }
  }
  async function download(kind: "original" | "report" | "print") {
    if (externalBusy || !workspace.data || !alive.current) return;
    setExternalBusy(true); setActionError("");
    try {
      const current = workspace.data;
      const result = await withPrivateOwner(ownerId, async () => kind === "original" ? await downloadAuditOriginal(id) : await exportResearchRecord<AuditData>("citation-audits", id));
      if (!alive.current) return;
      if (kind === "print" && !("blob" in result)) { setPrintRecord(result); return; }
      const blob = "blob" in result ? result.blob : new Blob([JSON.stringify(result, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url;
      anchor.download = kind === "original" ? current.data.filename : `${current.data.filename}.citation-audit.json`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { if (alive.current) setActionError(message(reason)); }
    finally { if (alive.current) setExternalBusy(false); }
  }
  return { ...workspace, actionError, notice, printRecord, busy: workspace.pending || externalBusy || Boolean(printRecord), command, download };
}

export function CitationAuditReport({ id }: { id: string }) {
  return <AuditGate next={`/account/citation-audits/${id}`}>{(ownerId, retrySession) => <Report id={id} ownerId={ownerId} retrySession={retrySession} />}</AuditGate>;
}

export function AuditUnavailable({ error, retry }: { error: string; retry: () => void }) {
  return <AuditFrame><div className="stl4-research-state" role={error ? "alert" : "status"}><h2>{error ? "体检资料暂时不可用" : "正在读取体检资料…"}</h2>{error ? <><p>{error}</p><button onClick={retry}>重新验证登录并读取</button><Link href="/account/citation-audits">返回任务列表</Link></> : null}</div></AuditFrame>;
}

export function AuditMessages({ workspace }: { workspace: ReturnType<typeof useAuditWorkspace> }) {
  return <>{workspace.error || workspace.actionError ? <p className="stl4-audit-alert" role="alert">{workspace.actionError || workspace.error}<button onClick={workspace.reload} disabled={workspace.busy}>重新读取</button></p> : null}{workspace.notice ? <p className="stl4-audit-notice" role="status">{workspace.notice}</p> : null}{workspace.conflict ? <p role="alert">任务已在其他操作中更新。你的编辑仍保留，请核对最新结果后再决定是否保存。</p> : null}</>;
}

function Report({ id, ownerId, retrySession }: { id: string; ownerId: string; retrySession: () => void }) {
  const workspace = useAuditWorkspace(id, ownerId);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<AuditCategory>("all");
  const [location, setLocation] = useState("");
  const [entryFilter, setEntryFilter] = useState("");
  const [page, setPage] = useState(1);
  const [selection, setSelection] = useState<{ ids: string[]; revision: number }>({ ids: [], revision: 0 });
  const [editor, setEditor] = useState<{ ids: string[]; revision: number } | null>(null);
  const [preview, setPreview] = useState(false);
  const record = workspace.data;
  if (!record) return <AuditUnavailable error={workspace.error} retry={retrySession} />;
  const data = record.data;
  const rows = data.occurrences || [];
  const entries = new Map((data.bibliography || []).map(row => [row.id, row]));
  const running = isTaskRunning(record.status);
  const filtered = rows.filter(row => (filter === "all" || auditCategory(row) === filter)
    && (!entryFilter || row.entry_ids.includes(entryFilter))
    && (!location || (location === "pdf" ? Boolean(row.location.pdf_page) : location === "note" ? Boolean(row.location.note_id != null || row.location.part?.includes("note")) : !row.location.pdf_page && !row.location.part?.includes("note")))
    && (!query.trim() || [row.quote, row.context, row.raw, ...row.entry_ids.map(key => entries.get(key)?.raw)].join(" ").toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())));
  const pages = Math.max(1, Math.ceil(filtered.length / 25));
  const currentPage = Math.min(page, pages);
  const shown = filtered.slice((currentPage - 1) * 25, currentPage * 25);
  const staleSelection = selection.ids.length > 0 && selection.revision !== record.revision;
  const selected = selection.ids.filter(key => rows.some(row => row.id === key));
  function toggle(ids: string[], checked: boolean) {
    setSelection({ ids: checked ? Array.from(new Set([...(selection.revision === record?.revision ? selection.ids : []), ...ids])) : selection.ids.filter(key => !ids.includes(key)), revision: record!.revision });
  }
  return <AuditFrame><AuditBreadcrumb id={id} /><header className="stl4-audit-heading"><div><h1>论文体检报告总览</h1><p>逐项理解哪里已核对，哪里仍需回到原文。</p></div><div className="stl4-audit-manuscript"><FileText size={27} /><div><strong>{data.filename}</strong><span>稿件版本 {data.manuscript_revision || 1} · {data.filetype.toUpperCase()}</span><time dateTime={record.updated_at}>更新于 {new Date(record.updated_at).toLocaleString("zh-CN")}</time></div></div></header>
    <AuditMessages workspace={workspace} />
    <CitationAuditVersions key={record.id} record={record} ownerId={ownerId} disabled={workspace.busy} onRefresh={workspace.reload} retrySession={retrySession} />
    <AuditProgress record={record} />
    <details className="stl4-audit-diagnostics" onToggle={event => setPreview(event.currentTarget.open)}><summary>查看稿件与解析预览</summary>{preview ? <CitationManuscriptPreview record={record} ownerId={ownerId} /> : null}</details>
    <div className="stl4-audit-toolbar"><Link className="stl4-audit-button" href={`/account/citation-audits/${id}/parse`}>解析与书目核对</Link><span>已识别 {rows.length} 处引文 · {data.bibliography?.length || 0} 条参考文献</span><div><button disabled={workspace.busy} onClick={() => void workspace.download("original")}>下载原稿</button><button disabled={workspace.busy} onClick={() => void workspace.download("report")}><Download size={14} />导出报告 JSON</button><button disabled={workspace.busy} onClick={() => void workspace.download("print")}>打印 / 保存 PDF</button><button disabled={workspace.busy} onClick={workspace.reload}><RefreshCw size={14} />读取进度</button>{running ? <button disabled={workspace.busy} onClick={() => void workspace.command({ action: "cancel" })}>取消任务</button> : <button disabled={workspace.busy} onClick={() => void workspace.command({ action: "retry" })}>重新检查</button>}</div></div>
    <p className="stl4-audit-caption">{data.report_notice || "文字匹配、来源身份和人工决定分别记录；未找到原文不等于引文错误。"}</p>
    <nav className="stl4-audit-counts" aria-label="报告分类">{Object.entries(auditCategories).map(([key, label]) => <button key={key} aria-pressed={filter === key} onClick={() => { setFilter(key as AuditCategory); setPage(1); }}><strong>{key === "all" ? rows.length : rows.filter(row => auditCategory(row) === key).length}</strong><span>{label}</span></button>)}</nav>
    <div className="stl4-audit-filters"><label className="stl4-audit-search"><Search size={15} /><input value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} aria-label="搜索引文或参考文献" placeholder="搜索引文、书名或作者" /></label><label>稿件位置<select value={location} onChange={event => { setLocation(event.target.value); setPage(1); }}><option value="">全部位置</option><option value="body">正文段落</option><option value="note">脚注与尾注</option><option value="pdf">PDF 页面</option></select></label><label>书目<select value={entryFilter} onChange={event => { setEntryFilter(event.target.value); setPage(1); }}><option value="">全部参考文献</option>{data.bibliography.map(entry => <option key={entry.id} value={entry.id}>{entry.raw.slice(0, 100)}</option>)}</select></label><button onClick={() => { setQuery(""); setLocation(""); setEntryFilter(""); setFilter("all"); setPage(1); }}>重置</button></div>
    {filtered.length ? <div className="stl4-audit-table-wrap"><table className="stl4-audit-table"><thead><tr><th><input type="checkbox" aria-label="选择本页引文" checked={shown.length > 0 && !staleSelection && shown.every(row => selected.includes(row.id))} onChange={event => toggle(shown.map(row => row.id), event.target.checked)} /></th><th>稿件位置</th><th>引文文字与来源</th><th>检查状态</th><th>简要说明</th><th>操作</th></tr></thead><tbody>{shown.map(row => <tr key={row.id} data-selected={selected.includes(row.id) || undefined}><td><input type="checkbox" aria-label={`选择${auditLocation(row.location)}`} checked={selected.includes(row.id)} onChange={event => toggle([row.id], event.target.checked)} /></td><td><strong>{auditLocation(row.location)}</strong></td><td><p>{row.quote || row.raw || row.context}</p><small>{row.entry_ids.map(key => entries.get(key)?.raw).filter(Boolean).join("；") || "参考文献对应关系待确认"}</small></td><td><span className="stl4-audit-state" data-state={auditCategory(row)}>{auditCategories[auditCategory(row)]}</span></td><td><AuditEvidenceNotice row={row} /><p>{row.decision?.note || row.findings.map(finding => finding.message).filter(Boolean).join(" ") || "尚未完成检查。"}</p></td><td><Link className="stl4-audit-button" href={`/account/citation-audits/${id}/issues/${row.id}`}>核验详情</Link></td></tr>)}</tbody></table></div> : <div className="stl4-research-empty"><h2>{rows.length ? "没有符合筛选条件的引文" : running ? "稿件正在解析" : "没有可展示的引文位置"}</h2><p>{rows.length ? "调整筛选条件可查看其他结果。" : "未识别到引文不能说明稿件没有问题；请查看解析提示和原稿。"}</p></div>}
    <footer className="stl4-audit-actions"><span>已选择 {selected.length} 项</span><button disabled={!selected.length || running || workspace.busy || staleSelection} onClick={() => setEditor({ ids: selected, revision: record.revision })}>批量人工复核</button><button disabled={!selected.length || running || workspace.busy || staleSelection} onClick={async () => { if (await workspace.command({ action: "retry", occurrence_ids: selected }, selection.revision)) setSelection({ ids: [], revision: 0 }); }}>仅重查所选</button>{staleSelection ? <><span role="status">报告已有更新，请重新选择。</span><button onClick={() => setSelection({ ids: [], revision: 0 })}>清空选择</button></> : null}<div className="stl4-audit-pagination"><button disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>上一页</button><span>{currentPage} / {pages}</span><button disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}>下一页</button></div></footer>
    <AuditDiagnostics record={record} />
    {workspace.printRecord ? <CitationAuditPrint record={workspace.printRecord} /> : null}
    <Dialog className="stl4-audit-dialog" open={Boolean(editor)} onRequestClose={() => { if (!workspace.busy) setEditor(null); }} aria-labelledby="audit-batch-title">{editor ? <DecisionForm key={editor.ids.join()} title="批量人工复核" titleId="audit-batch-title" count={editor.ids.length} busy={workspace.busy || running} stale={editor.revision !== record.revision} error={workspace.actionError} onReload={() => setEditor({ ...editor, revision: record.revision })} onCancel={() => setEditor(null)} onSave={async (decision, note, correctedText) => { if (await workspace.command({ action: "decision", occurrence_ids: editor.ids, decision, note, ...(correctedText !== undefined ? { corrected_text: correctedText } : {}) }, editor.revision)) { setEditor(null); setSelection({ ids: [], revision: 0 }); } }} /> : null}</Dialog>
  </AuditFrame>;
}

export function DecisionForm({ title, titleId, count = 1, initial, busy, stale, error, onReload, onCancel, onSave }: {
  title: string; titleId: string; count?: number; initial?: AuditDecision | null; busy: boolean; stale: boolean; error: string;
  onReload: () => void; onCancel: () => void; onSave: (decision: AuditDecision["value"], note: string, correctedText?: string) => Promise<void>;
}) {
  const [value, setValue] = useState<AuditDecision["value"]>(initial?.value || "needs_review");
  const [note, setNote] = useState(initial?.note || "");
  const [correctedText, setCorrectedText] = useState(initial?.corrected_text || "");
  function submit(event: FormEvent) { event.preventDefault(); if (!busy && !stale) void onSave(value, note, count === 1 && value === "corrected" ? correctedText : undefined); }
  return <form onSubmit={submit}><h2 id={titleId}>{title}</h2><p>为 {count} 处引文保存你的决定。修正说明单独保存，原稿保持原样。</p><fieldset disabled={busy}><legend>人工决定</legend>{Object.entries(auditDecisions).map(([key, label]) => <label key={key}><input type="radio" name="audit-decision" value={key} checked={value === key} onChange={() => setValue(key as AuditDecision["value"])} />{label}</label>)}</fieldset>{count === 1 && value === "corrected" ? <label>本人校正的引文文字<textarea disabled={busy} maxLength={4000} rows={4} value={correctedText} onChange={event => setCorrectedText(event.target.value)} /></label> : null}<label>复核笔记或修正说明<textarea disabled={busy} maxLength={4000} rows={5} value={note} onChange={event => setNote(event.target.value)} /></label>{stale ? <p role="alert">报告已有更新，输入已保留。<button type="button" onClick={onReload}>我已核对最新结果，沿用当前输入</button></p> : null}{error ? <p role="alert">{error}</p> : null}<footer><button type="button" disabled={busy} onClick={onCancel}>取消</button><button type="submit" className="is-primary" disabled={busy || stale}>保存人工决定</button></footer></form>;
}

export function AuditDiagnostics({ record }: { record: ResearchRecord<AuditData> }) {
  const data = record.data;
  return <section className="stl4-audit-diagnostics"><h2>解析与检查范围</h2>{data.warnings?.length ? <ul>{data.warnings.map((warning, index) => <li key={`${warning.code}:${index}`}>{warning.message}</li>)}</ul> : <p>当前没有额外解析提示。仍请逐项核对未完成的原文和书目。</p>}{data.location_notice ? <p>{data.location_notice}</p> : null}{data.ocr_progress?.total ? <p>文字识别 {data.ocr_progress.processed || 0} / {data.ocr_progress.total} 项，完成 {data.ocr_progress.completed || 0} 项，失败 {data.ocr_progress.failed || 0} 项，未取得文字 {data.ocr_progress.no_text || 0} 项。</p> : null}{data.parse_history?.length ? <details><summary>前次解析记录（{data.parse_history.length} 版）</summary><p>重新解析后仍保留旧引文、书目和人工记录。导出报告可取得完整历史。</p>{data.parse_history.map((version, index) => <section key={index}><h3>历史解析 {index + 1}</h3>{version.occurrences?.filter(row => row.decision).map(row => <p key={row.id}>{auditLocation(row.location)}：{row.quote || row.raw} · {row.decision ? auditDecisions[row.decision.value] : ""} {row.decision?.note}{row.decision?.corrected_text ? ` · 本人校正：${row.decision.corrected_text}` : ""}</p>)}</section>)}</details> : null}</section>;
}
