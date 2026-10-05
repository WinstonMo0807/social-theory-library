"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { apiBlob, apiRequest, getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EntityPicker, type EntityValue } from "../forms/workflow-fields";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import { SavedEditionCover } from "../preview/selected-work-preview";

export type OcrProgress = {
  id: string; status: string; phase: string; phase_label: string; completed_pages: number | null;
  total_pages: number | null; percent: number | null; active_pages: number[];
  updated_at: string; started_at: string | null; phase_elapsed_seconds: number; stale: boolean; error: string;
  source_asset_id: string; result_asset_id: string; public_result: string; workbench_url: string; warnings: string[];
  can_pause: boolean; can_resume: boolean; can_cancel: boolean; resume_reason?: string;
  heartbeat_at?: string | null; worker_alive?: boolean; service_activity?: string;
};
type OcrFile = { id: string; filename: string; version: number; page_count: number; source_version: string; can_run: boolean; reason: string };
type OcrTextPreview = {job_id:string;page_index:number;asset_id:string;saved:boolean;text:string;updated_at:string|null};
type OcrContext = { edition_id: string; work_id: string; title: string; title_has_unpublished_changes?: boolean; edition_label: string; can_run: boolean; denied_reason: string; paused: boolean; provider_label: string; files: OcrFile[]; jobs: OcrProgress[]; job_count: number; page: number; total_pages: number; active_job_id: string; checked_at: string; text_preview?:OcrTextPreview|null };
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
    <p>结果最近保存：<time dateTime={job.updated_at}>{new Date(job.updated_at).toLocaleString("zh-CN")}</time>。进度按实际保存页数更新。</p>
    {job.status === "running" ? <p role="status">{job.worker_alive ? "后台执行进程在线。" : job.stale ? "暂未收到后台心跳，可能已中断，正在检查。" : "正在等待后台心跳。"}{job.service_activity === "running" ? "OCR 服务正在识别当前页。" : job.service_activity === "queued" ? "当前页正在 OCR 服务内排队。" : job.service_activity === "unavailable" ? "尚未取得 OCR 服务内部状态，不能据此认定识别已停止。" : ""}{job.heartbeat_at ? ` 最近心跳 ${new Date(job.heartbeat_at).toLocaleTimeString("zh-CN")}` : ""}</p> : null}
    {job.status === "running" || job.status === "pending" ? <p>本阶段已等待 {job.phase_elapsed_seconds} 秒。页面仍会自动查询，不需要重复点击开始。</p> : null}
    {job.error ? <details open={!compact}><summary>上次失败原因</summary><p>{job.error}</p><p>这是该次任务的错误记录，不代表 OCR 服务当前仍不可用。</p></details> : null}
    {!compact ? <p>{job.public_result}</p> : null}
    {job.warnings?.length ? <details><summary>其他处理提醒</summary>{job.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</details> : null}
    {!compact && job.workbench_url ? <Link href={job.workbench_url}>查看这个版本的公开更新结果</Link> : null}
  </div>;
}

/** Both entry points read the same persisted job; no health probes or external calls on polling. */
export function EditionOcrControl({ editionId, workId = "", fullPage = false }: { editionId: string; workId?: string; fullPage?:boolean }) {
  return <EditionOcrControlState key={`${workId}:${editionId}`} editionId={editionId} workId={workId} fullPage={fullPage} />;
}

function EditionOcrControlState({ editionId, workId, fullPage }: { editionId: string; workId: string; fullPage:boolean }) {
  const [data, setData] = useState<OcrContext | null>(null);
  const [fileId, setFileId] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [previewPage,setPreviewPage] = useState(1);
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
        const result = await apiRequest<OcrContext>(`${endpoint}?ocr_edition_id=${encodeURIComponent(editionId)}&work_id=${encodeURIComponent(workId)}&ocr_page=${historyPage}${fullPage ? `&ocr_preview_page=${previewPage}` : ""}`, { signal: controller.signal }, token);
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
  }, [editionId, workId, historyPage, refresh, token, fullPage, previewPage]);
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
  const latest = jobs[0];
  const stage = latest ? ["finalizing","pdf","publishing","complete"].includes(latest.phase) || latest.status==="succeeded" ? 3 : latest.phase==="preparing" ? 1 : 2 : 1;
  const previewAsset = latest?.source_asset_id || file?.id || current?.files[0]?.id || "";
  return <section className={`catalog-ocr-control ${fullPage ? "ocr-reference-page" : ""}`} aria-label="馆藏 PDF 文字识别">
    {fullPage ? <header className="ocr-reference-book"><SavedEditionCover editionId={editionId} title={current?.title || ""}/><div><h1>{current?.title || "识别书中文字"}</h1><p>{current?.edition_label}</p></div><Link className="button secondary" href="/admin/library">← 返回馆藏列表</Link></header> : null}
    <div className={fullPage ? "ocr-reference-grid" : undefined}><div className={fullPage ? "admin-panel ocr-reference-progress" : undefined}>
    {fullPage ? <><header><h2>识别进度</h2><span>当前：第 {stage} / 3 步</span></header><ol className="reference-step-strip">{["检查文件","识别文字","整理阅读文件"].map((label,index)=><li key={label} aria-current={stage===index+1 ? "step" : undefined}><b>{stage>index+1 ? "✓" : index+1}</b><span>{label}</span></li>)}</ol></> : null}
    <details className="ocr-reference-start" open={!latest || !fullPage}><summary>选择文件与识别设置</summary>
    <h3>重新识别 PDF 文字</h3>
    <p>对当前出版版本的 PDF 重新进行全文 OCR。书目信息和人工确认内容不变，原文件、旧页标识及读者笔记保留。</p>
    {!current && !error ? <p role="status">正在读取这个版本的文件和任务…</p> : null}
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
    </> : null}</details>
    {error ? <div role="alert"><p>{error}</p><button type="button" onClick={() => setRefresh((n) => n + 1)}>重新读取进度</button></div> : null}
    {current ? <>
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
      <nav className="catalog-ocr-actions" aria-label="OCR 记录分页"><span>共 {current.job_count} 次识别，第 {current.page} / {current.total_pages} 页</span><button type="button" disabled={current.page <= 1} onClick={() => {setPreviewPage(1);setHistoryPage(current.page - 1);}}>上一页识别记录</button><button type="button" disabled={current.page >= current.total_pages} onClick={() => {setPreviewPage(1);setHistoryPage(current.page + 1);}}>下一页识别记录</button></nav>
      <Link href={`/admin/processing?surface=documents&work=${current.work_id}&edition=${editionId}`}>在处理中心查看这个版本</Link>
      {!fullPage ? <Link className="button secondary" href={`/admin/library/ocr?work=${current.work_id}&edition=${editionId}`}>打开文字识别工作页 →</Link> : <aside className="ocr-reference-reader-change"><h3>读者会有什么变化</h3><p>{latest?.public_result || "识别结果保存后，仍需核对阅读文件与公开更新状态。"}</p><p>识别过程保留原 PDF、已保存文字和读者记录。</p></aside>}
    </> : null}
    </div>{fullPage ? <OcrContentPreview key={previewAsset} assetId={previewAsset} page={previewPage} pages={latest?.total_pages || current?.files.find(row=>row.id===previewAsset)?.page_count || 1} textPreview={current?.text_preview?.page_index===previewPage ? current.text_preview : null} onPage={setPreviewPage} token={token}/> : null}</div>
    <ConfirmDialog open={confirm} title="确认重新识别整份 PDF" description={`${file?.filename ?? ""} · ${file?.page_count ?? 0} 页。将调用${current?.provider_label ?? "当前配置的 OCR 服务"}，可能耗时或产生服务费用。`} details={["仅提交当前出版版本，不修改书目字段或人工锁。", "已公开内容在新结果准备好并通过公开更新流程之前保持原样；识别失败不会替换稳定旧版。", "识别页数达到 100% 后，仍需整理文字和阅读文件，公开更新结果会单独显示。"]} confirmLabel={pending ? "正在提交…" : "确认开始识别"} pending={pending} onCancel={() => setConfirm(false)} onConfirm={() => action("start_ocr")} />
  </section>;
}

function OcrContentPreview({assetId,page,pages,textPreview,onPage,token}: {assetId:string;page:number;pages:number;textPreview:OcrTextPreview|null;onPage:(page:number)=>void;token:string|null}) {
  const [tab,setTab]=useState("pdf"),[url,setUrl]=useState(""),[error,setError]=useState("");
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{
    if(!assetId || !token)return;
    let active=true,objectUrl="";
    void apiBlob(`/distribution/admin/assets/${assetId}/preview/`,token).then(blob=>{objectUrl=URL.createObjectURL(blob);if(active){setUrl(objectUrl);setError("");}else URL.revokeObjectURL(objectUrl);}).catch(reason=>{if(active)setError(reason instanceof Error ? reason.message : "PDF 读取失败");});
    return ()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[assetId,token,attempt]);
  return <section className="admin-panel ocr-reference-preview"><header><h2>识别内容预览</h2><nav aria-label="识别预览内容"><button type="button" aria-pressed={tab==="pdf"} onClick={()=>setTab("pdf")}>原 PDF 页面</button><button type="button" aria-pressed={tab==="text"} onClick={()=>setTab("text")}>提取的文字</button></nav></header>
    <div className="ocr-reference-page-controls"><button type="button" disabled={page<=1} onClick={()=>onPage(page-1)}>‹</button><label>第 <input type="number" min={1} max={pages} value={page} onChange={event=>{const next=Number(event.target.value);if(Number.isInteger(next)&&next>0&&next<=pages)onPage(next);}}/> / {pages} 页</label><button type="button" disabled={page>=pages} onClick={()=>onPage(page+1)}>›</button></div>
    {tab==="pdf" ? error ? <p role="alert">{error}<button type="button" onClick={()=>setAttempt(value=>value+1)}>重试</button></p> : url ? <iframe title={`原 PDF 第 ${page} 页`} src={`${url}#page=${page}&view=FitH`}/> : <p role="status">{assetId ? "正在读取原 PDF…" : "尚未选择可预览的 PDF。"}</p> : textPreview?.saved ? <div className="ocr-reference-text"><small>本次任务已保存的文字{textPreview.updated_at ? ` · ${new Date(textPreview.updated_at).toLocaleString("zh-CN")}` : ""}</small><pre>{textPreview.text || "本页识别结果为空。"}</pre></div> : <p className="empty-state">本次任务尚无这一页的已保存文字。</p>}
  </section>;
}

export function CatalogOcrPicker({fullPage=false}: {fullPage?:boolean}) {
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
  return <section className={`catalog-ocr-picker ${fullPage ? "ocr-reference-picker" : "admin-panel"}`} aria-label="按馆藏 PDF 识别文字">
    <details className="ocr-reference-selection" open={!fullPage || !work || !edition}><summary>选择馆藏与出版版本</summary>
    <h2>选择馆藏 PDF 进行文字识别</h2><p>已发布和未发布馆藏都可选择。无需寻找上传编号，选择作品和出版版本即可。</p>
    <EntityPicker label="需要识别的馆藏" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" values={works} onChange={(values) => { setWorks(values.slice(-1)); setEdition(""); setPage(1); setData(null); setError(""); }} />
    {error ? <p role="alert">{error}<button type="button" onClick={() => setRefresh((n) => n + 1)}>重试版本查询</button></p> : null}
    {work ? <><label><span>需要识别的出版版本</span><select value={edition} onChange={(event) => setEdition(event.target.value)} disabled={!data}>
      <option value="">请选择出版版本</option>
      {edition && !data?.results.some((row) => row.id === edition) ? <option value={edition}>已选版本（在其他分页）</option> : null}
      {data?.results.map((row) => <option key={row.id} value={row.id}>{row.label || "出版信息待补"}{row.is_primary ? "（主版本）" : ""}</option>)}
    </select></label><nav className="catalog-ocr-actions" aria-label="OCR 出版版本分页"><span>{data ? `共 ${data.count} 个版本，第 ${page} 页` : "正在读取…"}</span><button type="button" disabled={!data?.previous} onClick={() => { setData(null); setError(""); setPage((n) => n - 1); }}>上一页版本</button><button type="button" disabled={!data?.next} onClick={() => { setData(null); setError(""); setPage((n) => n + 1); }}>下一页版本</button></nav></> : null}
    </details>{work && edition ? <EditionOcrControl key={edition} editionId={edition} workId={work} fullPage={fullPage}/> : null}
  </section>;
}
