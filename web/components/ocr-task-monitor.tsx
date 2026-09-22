"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PauseCircle, Play, RotateCcw } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { OcrProgressDisplay, type OcrProgress } from "./admin/workflow/edition-ocr-control";

type Row = { id: string; title: string; edition_label: string; workbench_url: string; status: string; stats: Record<string, unknown>; ocr_progress: OcrProgress };
type Snapshot = { results: Row[]; count: number; page: number; pages: number; counts: Record<string, number>; can_manage: boolean; paused: boolean; checked_at: string };
const endpoint = "/ingestion/processing-center/";
const statuses = [["", "全部"], ["failed", "失败待重试"], ["running", "正在识别"], ["pending", "排队"], ["paused", "已暂停"]] as const;

export function OcrTaskMonitor() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [input, setInput] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState("");
  const [revision, setRevision] = useState(0);
  const inFlight = useRef(false);
  const token = getServerSessionCredential();
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | null = null;
    async function poll() {
      if (document.hidden) { timer = setTimeout(poll, 2000); return; }
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 12000);
      try {
        const result = await apiRequest<Snapshot>(`${endpoint}?${new URLSearchParams({ ocr_monitor: "1", status, page: String(page), q: query })}`, { signal: controller.signal }, token);
        if (!disposed) { setSnapshot(result); setError(""); }
      } catch (reason) {
        if (!disposed) setError(`${reason instanceof Error ? reason.message : "进度读取失败"}。保留上次记录，正在重新读取。`);
      } finally {
        clearTimeout(timeout);
        if (!disposed) timer = setTimeout(poll, 2000);
      }
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); };
  }, [status, page, query, revision, token]);

  async function act(row: Row, action: "retry" | "pause" | "resume") {
    if (inFlight.current) return;
    inFlight.current = true; setPending(row.id); setMessage("");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const legacyResume = action === "resume" && row.stats.requested_mode !== "all_pages";
      await apiRequest(endpoint, { method: "POST", signal: controller.signal, body: JSON.stringify({
        action: legacyResume ? "resolve_paused_ocr" : action, source: "processing_job", job_id: row.id,
        ...(legacyResume ? { decision: "resume", reason: "管理员在 OCR 控制区继续未完成页面" } : {}),
      }) }, token);
      setMessage(action === "pause" ? "已请求安全暂停，当前页保存后停止。" : "已从保存进度重新排队，已完成页面保留。可离开页面，书库会继续处理。");
      setStatus(""); setPage(1); setRevision(value => value + 1);
    } catch (reason) {
      setMessage(controller.signal.aborted ? "操作响应超时，请先查看自动更新的任务状态，不必重复提交。" : reason instanceof Error ? reason.message : "操作未完成，请重试。");
    } finally { clearTimeout(timeout); inFlight.current = false; setPending(""); }
  }
  return <section className="admin-panel ocr-task-monitor" id="ocr-tasks" aria-labelledby="ocr-monitor-title">
    <header><div><h2 id="ocr-monitor-title">OCR 识别与重试</h2><p>直接重试未完成页面，保留已经识别的文字。</p></div><span>{snapshot ? `每 2 秒更新 · ${new Date(snapshot.checked_at).toLocaleTimeString("zh-CN")}` : "正在读取任务…"}</span></header>
    <nav className="processing-status-tabs" aria-label="OCR 任务状态">{statuses.map(([value, label]) => <button key={value} type="button" aria-pressed={status === value} className={status === value ? "active" : ""} onClick={() => { setStatus(value); setPage(1); setSnapshot(null); }}>{label}{value && snapshot ? ` ${snapshot.counts[value] || 0}` : ""}</button>)}</nav>
    <form className="processing-search" onSubmit={event => { event.preventDefault(); setQuery(input.trim()); setPage(1); setSnapshot(null); }}><label>查找馆藏<input value={input} onChange={event => setInput(event.target.value)} placeholder="书名或文件名" /></label><button type="submit">查找</button></form>
    {snapshot?.paused ? <p role="status">OCR 已全局暂停。请先在下方“全库文字识别开关”允许运行，再重试所选任务。</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {message ? <p role="status">{message}</p> : null}
    <div className="ocr-monitor-jobs">{snapshot?.results.map(row => <article key={row.id} data-status={row.status}>
      <header><div><h3>{row.title || "馆藏 PDF"}</h3><p>{row.edition_label}</p></div>{snapshot.can_manage ? <div className="catalog-ocr-actions">
        {row.status === "failed" || row.status === "paused" ? <button className="button" type="button" disabled={Boolean(pending) || snapshot.paused || !row.ocr_progress.can_resume} onClick={() => void act(row, row.status === "failed" ? "retry" : "resume")}>{row.status === "failed" ? <RotateCcw size={14} /> : <Play size={14} />}{pending === row.id ? "正在提交…" : row.status === "failed" ? "重试未完成页面" : "继续识别"}</button> : null}
        {row.ocr_progress.can_pause ? <button className="button secondary" type="button" disabled={Boolean(pending)} onClick={() => void act(row, "pause")}><PauseCircle size={14} />安全暂停</button> : null}
      </div> : null}</header>
      <OcrProgressDisplay job={row.ocr_progress} compact />
      {row.ocr_progress.resume_reason ? <p>{row.ocr_progress.resume_reason}</p> : null}
      {row.workbench_url ? <Link href={row.workbench_url}>查看馆藏版本与文件</Link> : null}
    </article>)}</div>
    {snapshot && !snapshot.results.length ? <p>当前范围没有 OCR 任务。</p> : null}
    <nav className="catalog-ocr-actions" aria-label="OCR 任务分页"><span>{snapshot ? `共 ${snapshot.count} 项 · 第 ${snapshot.page} / ${snapshot.pages} 页` : "正在读取…"}</span><button type="button" disabled={!snapshot || snapshot.page <= 1} onClick={() => { setPage(snapshot!.page - 1); setSnapshot(null); }}>上一页</button><button type="button" disabled={!snapshot || snapshot.page >= snapshot.pages} onClick={() => { setPage(snapshot!.page + 1); setSnapshot(null); }}>下一页</button></nav>
  </section>;
}
