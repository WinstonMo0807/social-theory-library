"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EntityPicker, type EntityValue } from "../forms/workflow-fields";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";

export type OcrProgress = {
  id: string; status: string; phase: string; phase_label: string; completed_pages: number | null;
  total_pages: number | null; percent: number | null; active_pages: number[];
  updated_at: string; started_at: string | null; phase_elapsed_seconds: number; stale: boolean; error: string;
  source_asset_id: string; result_asset_id: string; public_result: string; workbench_url: string; warnings: string[];
  can_pause: boolean; can_resume: boolean; can_cancel: boolean; resume_reason?: string;
};
type OcrFile = { id: string; filename: string; version: number; page_count: number; source_version: string; can_run: boolean; reason: string };
type OcrContext = { edition_id: string; work_id: string; title: string; title_has_unpublished_changes?: boolean; edition_label: string; can_run: boolean; denied_reason: string; paused: boolean; provider_label: string; files: OcrFile[]; jobs: OcrProgress[]; job_count: number; page: number; total_pages: number; active_job_id: string; checked_at: string };
const endpoint = "/ingestion/processing-center/";

export function ocrPageRanges(indexes: number[]) {
  const values = [...new Set(indexes)].sort((a, b) => a - b);
  const ranges: string[] = [];
  for (let position = 0; position < values.length; position += 1) {
    const first = values[position];
    let last = first;
    while (values[position + 1] === last + 1) last = values[++position];
    ranges.push(first === last ? String(first) : `${first}–${last}`);
  }
  return ranges.join("、") || "无";
}

export function OcrProgressDisplay({ job, compact = false }: { job: OcrProgress; compact?: boolean }) {
  return <div className="catalog-ocr-progress" data-ocr-status={job.status}>
    <strong>{job.phase_label}</strong>
    <progress aria-label="已完成 OCR 页数" max={job.total_pages || 1} value={job.completed_pages === null ? undefined : job.completed_pages} />
    <p>{job.completed_pages === null || job.total_pages === null ? "尚无可靠页数，等待任务报告。" : `已识别 ${job.completed_pages} / ${job.total_pages} 页（${job.percent}%）`}{job.active_pages.length ? job.active_pages.length <= 5 ? `，当前处理第 ${ocrPageRanges(job.active_pages)} 页。` : `，正在处理 ${job.active_pages.length} 页。` : ""}</p>
    {job.active_pages.length > 5 ? <details><summary>查看当前处理的页码范围</summary><p>{ocrPageRanges(job.active_pages)}</p></details> : null}
    <p>任务最近更新：<time dateTime={job.updated_at}>{new Date(job.updated_at).toLocaleString("zh-CN")}</time>。{job.stale ? "当前页尚未返回新结果，页数暂未增加。" : "进度按实际保存页数更新。"}</p>
    {job.status === "running" || job.status === "pending" ? <p>本阶段已等待 {job.phase_elapsed_seconds} 秒。页面仍会自动查询，不需要重复点击开始。</p> : null}
    {job.error ? <details open={!compact}><summary>上次失败原因</summary><p>{job.error}</p><p>这是该次任务的错误记录，不代表 OCR 服务当前仍不可用。</p></details> : null}
    {!compact ? <p>{job.public_result}</p> : null}
    {job.warnings?.length ? <details><summary>其他处理提醒</summary>{job.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</details> : null}
    {!compact && job.workbench_url ? <Link href={job.workbench_url}>查看这个版本的公开更新结果</Link> : null}
  </div>;
}

/** Both entry points read the same persisted job; no health probes or external calls on polling. */
export function EditionOcrControl({ editionId, workId = "" }: { editionId: string; workId?: string }) {
  return <EditionOcrControlState key={`${workId}:${editionId}`} editionId={editionId} workId={workId} />;
}

function EditionOcrControlState({ editionId, workId }: { editionId: string; workId: string }) {
  const [data, setData] = useState<OcrContext | null>(null);
  const [fileId, setFileId] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const inFlight = useRef(false);
  const request = useRef<{ file: string; version: string; id: string } | null>(null);
  const token = getServerSessionCredential();
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | null = null;
    async function poll() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 12_000);
      try {
        const result = await apiRequest<OcrContext>(`${endpoint}?ocr_edition_id=${encodeURIComponent(editionId)}&work_id=${encodeURIComponent(workId)}&ocr_page=${historyPage}`, { signal: controller.signal }, token);
        if (!disposed) { setData(result); setError(""); }
      } catch (reason) {
        if (!disposed) setError(`${reason instanceof Error ? reason.message : "进度读取失败"}。最后一次结果保留，正在自动重试；请勿反复提交识别。`);
      } finally {
        clearTimeout(timeout);
        if (!disposed) timer = setTimeout(poll, document.hidden ? 10_000 : 2_000);
      }
    }
    if (editionId) void poll();
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); };
  }, [editionId, workId, historyPage, refresh, token]);
  const current = data?.edition_id === editionId && data.page === historyPage ? data : null;
  const file = current?.files.find((row) => row.id === fileId);
  const jobs = current?.jobs ?? [];
  const active = current?.active_job_id || jobs.find((job) => ["pending", "running", "paused"].includes(job.status))?.id;
  async function action(actionName: string, job?: OcrProgress) {
    if (inFlight.current || !current || (!job && !file)) return;
    if (actionName === "cancel_catalog_ocr" && !window.confirm(`取消《${current.title}》这次文字识别？原 PDF、已保存文字和读者记录都会保留。`)) return;
    inFlight.current = true; setPending(true); setError("");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15_000);
    try {
      if (!job && (!request.current || request.current.file !== file!.id)) request.current = { file: file!.id, version: file!.source_version, id: createRequestKey() };
      const receipt = await apiRequest<{ job: OcrProgress; replayed?: boolean }>(endpoint, { method: "POST", signal: controller.signal, body: JSON.stringify(job ? {
        action: actionName, edition_id: editionId, job_id: job.id,
      } : {
        action: "start_ocr", edition_id: editionId, asset_id: request.current!.file,
        source_version: request.current!.version, request_id: request.current!.id, confirmed: true,
      }) }, token);
      setMessage(receipt.replayed ? "已找回之前提交的任务，没有重复识别。" : job ? "任务操作已保存，请查看下方实际状态。" : "识别任务已建立，可以离开本页；重新打开仍可查看进度。不是已经识别完成。");
      setHistoryPage(1);
      setData((value) => value?.edition_id === editionId ? { ...value, active_job_id: ["pending", "running", "paused"].includes(receipt.job.status) ? receipt.job.id : "", jobs: [receipt.job, ...value.jobs.filter((row) => row.id !== receipt.job.id)], job_count: Math.max(1, value.job_count) } : value);
      request.current = null; setConfirm(false);
    } catch (reason) {
      setConfirm(false);
      setError(controller.signal.aborted ? "提交响应超时，任务可能已经建立。请先查看任务；再次确认提交会使用同一次请求，不会重复识别。" : reason instanceof Error ? reason.message : "操作失败，请重试同一次请求。");
    } finally { clearTimeout(timeout); inFlight.current = false; setPending(false); }
  }
  return <section className="catalog-ocr-control" aria-label="馆藏 PDF 文字识别">
    <h3>重新识别 PDF 文字</h3>
    <p>对当前出版版本的 PDF 重新进行全文 OCR。书目信息和人工确认内容不变，原文件、旧页标识及读者笔记保留。</p>
    {!current && !error ? <p role="status">正在读取这个版本的文件和任务…</p> : null}
    {error ? <div role="alert"><p>{error}</p><button type="button" onClick={() => setRefresh((n) => n + 1)}>重新读取进度</button></div> : null}
    {current ? <>
      <p><strong>{current.title}</strong> · {current.edition_label}</p>
      {current.title_has_unpublished_changes ? <p>这里显示已保存的新馆藏名称，尚未发布；仍对应原来的作品、出版版本和文件。</p> : null}
      <label><span>需要识别的 PDF</span><select value={fileId} disabled={pending} onChange={(event) => { setFileId(event.target.value); request.current = null; setMessage(""); }}>
        <option value="">请选择文件</option>
        {current.files.map((row) => <option key={row.id} value={row.id} disabled={!row.can_run}>{row.filename} · 文件版本 {row.version} · {row.page_count} 页{row.reason ? ` · ${row.reason}` : ""}</option>)}
      </select></label>
      {file ? <p>{file.filename}，共 {file.page_count} 页。将使用{current.provider_label}。</p> : null}
      {!current.files.length ? <p>这个版本还没有可识别的阅读 PDF，请先补充文件并完成校验。</p> : null}
      {!current.can_run ? <p>{current.denied_reason}</p> : null}
      {current.paused ? <p>OCR 已全局暂停，新任务会保存为暂停状态；不会擅自恢复其他任务。</p> : null}
      <button type="button" className="button secondary" disabled={!file?.can_run || !current.can_run || pending || Boolean(active)} onClick={() => setConfirm(true)}>重新识别整份 PDF</button>
      {active ? <p>本版本已有未结束任务，请先完成、继续或取消该任务，避免重复识别。{historyPage > 1 ? <button type="button" onClick={() => setHistoryPage(1)}>返回最近任务</button> : null}</p> : null}
      {message ? <p role="status">{message}</p> : null}
      <p>每 2 秒查询一次实际结果。最近读取：<time dateTime={current.checked_at}>{new Date(current.checked_at).toLocaleTimeString("zh-CN")}</time>；这不是 OCR 完成时间。</p>
      {jobs.length ? <div className="catalog-ocr-jobs">{jobs.map((job, index) => <details key={job.id} open={index === 0}>
        <summary>{index === 0 ? "最近一次识别" : "历史识别"} · {job.phase_label}</summary>
        <OcrProgressDisplay job={job} />
        <div className="catalog-ocr-actions">
          {job.can_pause ? <button type="button" disabled={pending} onClick={() => void action("pause_catalog_ocr", job)}>安全暂停</button> : null}
          {job.can_resume ? <button type="button" disabled={pending || current.paused} onClick={() => void action("resume_catalog_ocr", job)}>{job.status === "failed" ? "从失败处继续" : "继续识别"}</button> : null}
          {job.can_cancel ? <button type="button" disabled={pending} onClick={() => void action("cancel_catalog_ocr", job)}>取消本次识别</button> : null}
        </div>
      </details>)}</div> : <p>此版本暂无 OCR 任务。</p>}
      <nav className="catalog-ocr-actions" aria-label="OCR 记录分页"><span>共 {current.job_count} 次识别，第 {current.page} / {current.total_pages} 页</span><button type="button" disabled={current.page <= 1} onClick={() => setHistoryPage(current.page - 1)}>上一页识别记录</button><button type="button" disabled={current.page >= current.total_pages} onClick={() => setHistoryPage(current.page + 1)}>下一页识别记录</button></nav>
      <Link href={`/admin/processing?surface=documents&work=${current.work_id}&edition=${editionId}`}>在处理中心查看这个版本</Link>
    </> : null}
    <ConfirmDialog open={confirm} title="确认重新识别整份 PDF" description={`${file?.filename ?? ""} · ${file?.page_count ?? 0} 页。将调用${current?.provider_label ?? "当前配置的 OCR 服务"}，可能耗时或产生服务费用。`} details={["仅提交当前出版版本，不修改书目字段或人工锁。", "已公开内容在新结果准备好并通过公开更新流程之前保持原样；识别失败不会替换稳定旧版。", "识别页数达到 100% 后，仍需整理文字和阅读文件，公开更新结果会单独显示。"]} confirmLabel={pending ? "正在提交…" : "确认开始识别"} pending={pending} onCancel={() => setConfirm(false)} onConfirm={() => action("start_ocr")} />
  </section>;
}

export function CatalogOcrPicker() {
  const parameters = useSearchParams();
  const initialWork = parameters.get("work") || "";
  const [works, setWorks] = useState<EntityValue[]>(initialWork ? [{ id: initialWork, name: "已选馆藏" }] : []);
  const [edition, setEdition] = useState(parameters.get("edition") || "");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CollectionPage<WorkLibraryRow> | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const work = works.at(-1)?.id ?? "";
  useEffect(() => {
    const controller = new AbortController();
    if (work) void apiRequest<CollectionPage<WorkLibraryRow>>(`/catalog/admin/library/works/?view=editions&work_id=${encodeURIComponent(work)}&page=${page}`, { signal: controller.signal }, getServerSessionCredential()).then((result) => { if (!controller.signal.aborted) setData(result); }).catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "版本读取失败"); });
    return () => controller.abort();
  }, [work, page, refresh]);
  return <section className="catalog-ocr-picker admin-panel" aria-label="按馆藏 PDF 识别文字">
    <h2>选择馆藏 PDF 进行文字识别</h2><p>已发布和未发布馆藏都可选择。无需寻找上传编号，选择作品和出版版本即可。</p>
    <EntityPicker label="需要识别的馆藏" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" values={works} onChange={(values) => { setWorks(values.slice(-1)); setEdition(""); setPage(1); setData(null); setError(""); }} />
    {error ? <p role="alert">{error}<button type="button" onClick={() => setRefresh((n) => n + 1)}>重试版本查询</button></p> : null}
    {work ? <><label><span>需要识别的出版版本</span><select value={edition} onChange={(event) => setEdition(event.target.value)} disabled={!data}>
      <option value="">请选择出版版本</option>
      {edition && !data?.results.some((row) => row.id === edition) ? <option value={edition}>已选版本（在其他分页）</option> : null}
      {data?.results.map((row) => <option key={row.id} value={row.id}>{row.label || "出版信息待补"}{row.is_primary ? "（主版本）" : ""}</option>)}
    </select></label><nav className="catalog-ocr-actions" aria-label="OCR 出版版本分页"><span>{data ? `共 ${data.count} 个版本，第 ${page} 页` : "正在读取…"}</span><button type="button" disabled={!data?.previous} onClick={() => { setData(null); setError(""); setPage((n) => n - 1); }}>上一页版本</button><button type="button" disabled={!data?.next} onClick={() => { setData(null); setError(""); setPage((n) => n + 1); }}>下一页版本</button></nav></> : null}
    {work && edition ? <EditionOcrControl key={edition} editionId={edition} workId={work} /> : null}
  </section>;
}
