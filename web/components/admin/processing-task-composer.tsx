"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import type { OCROptions } from "@/lib/api/ocr-workspace.client";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { CatalogOcrPicker, ocrPageRanges } from "./workflow/edition-ocr-control";
import { useCatalogCommand } from "./workflow/use-intake-command";
import styles from "./processing-workspace.module.css";

type Source = components["schemas"]["ProcessingSource"];
type Creation = Omit<components["schemas"]["ProcessingCreationRequest"], "request_id">;
type Receipt = components["schemas"]["ProcessingReceipt"];
export type ProcessingTaskSeed = { workId?: string; editionId?: string; assetId?: string; taskType?: "ocr" | "outline" };
const endpoint = "/ingestion/processing-workspace/";
const languages = [["ch", "简体中文"], ["en", "英语"], ["chinese_cht", "繁体中文"]];

/** A bounded input over real PDF page ordinals, never printed page labels. */
export function parseProcessingPages(input: string, pageCount: number): number[] {
  if (!input.trim() || input.length > 10000) throw Error("请填写有效 PDF 页序，例如 1–3、8、12–15。");
  const pages = new Set<number>();
  for (const token of input.trim().split(/[,，、;；\s]+/)) {
    const match = /^(\d+)(?:[-–—](\d+))?$/.exec(token);
    if (!match) throw Error(`页序「${token}」无法识别，请用数字和短横线填写。`);
    const first = Number(match[1]), last = Number(match[2] || match[1]);
    if (!Number.isSafeInteger(first) || !Number.isSafeInteger(last) || first < 1 || last < first || last > pageCount || last - first >= 20000) throw Error(`页序必须位于 1 至 ${pageCount}，每次最多选择 20000 页。`);
    for (let page = first; page <= last; page++) { pages.add(page); if (pages.size > 20000) throw Error("每次最多选择 20000 页。"); }
  }
  return [...pages].sort((a, b) => a - b);
}

export function ProcessingTaskComposer({ owner, seed = {}, onCreated }: { owner: string; seed?: ProcessingTaskSeed; onCreated: (receipt: Receipt, message: string) => void }) {
  const command = useCatalogCommand<Creation, Receipt>(owner, endpoint, `stl-processing-create:${owner}`);
  const [confirmation, setConfirmation] = useState<{ body: Creation; label: string; provider: string } | null>(null);
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const locked = !command.ready || command.busy || Boolean(command.recovery) || Boolean(confirmation);
  function accept(result: Receipt | null) {
    if (!result) return;
    setConfirmation(null); setRefresh(value => value + 1);
    if (result.state === "cancelled") setNotice("原待定请求已停止，已经创建的任务仍按真实回执处理。");
    else onCreated(result, result.result && typeof result.result === "object" && "message" in result.result && typeof result.result.message === "string" ? result.result.message : "任务已登记，请查看实际进度。");
  }
  async function submit(body?: Creation) {
    const result = await command.send(body);
    accept(result);
    // The request payload stays in the command hook if its outcome is unknown.
    setConfirmation(null); setRefresh(value => value + 1);
  }
  return <div className={styles.composer}>
    <p className={styles.note}>处理任务绑定具体文件与设置。已有任务可从断点继续；重新运行会登记新的处理记录。</p>
    {command.error ? <p role="alert" className={styles.notice}>{command.error}</p> : null}
    {notice ? <p role="status" className={styles.notice}>{notice}</p> : null}
    {command.recovery ? <div className={styles.notice} role="status"><p>上次请求结果尚待确认，先查回记录。停止待定请求只阻止尚未执行的提交；已建立的任务需从任务详情取消。</p><div className={styles.actions}><button type="button" disabled={command.busy} onClick={() => void command.lookup().then(accept)}>查回原请求</button>{command.canRetry ? <button type="button" disabled={command.busy} onClick={() => void submit()}>重送同一请求</button> : null}<button type="button" disabled={command.busy} onClick={() => void command.lookup(true).then(accept)}>停止待定请求</button></div></div> : null}
    <CatalogOcrPicker disabled={locked} initialWorkId={seed.workId} initialEditionId={seed.editionId} renderEdition={(editionId, workId) => <SourceForm key={`${editionId}:${workId}`} owner={owner} editionId={editionId} workId={workId} seed={seed} refresh={refresh} disabled={locked} onReview={(body, label, provider) => { setNotice(""); setConfirmation({ body, label, provider }); }} />} />
    {confirmation ? <section className={styles.taskReview} aria-label="确认处理范围"><h3>确认本次处理</h3><p>{confirmation.label}</p><dl className={styles.facts}><div><dt>处理内容</dt><dd>{confirmation.body.task_type === "ocr" ? confirmation.body.page_indexes ? `PDF 第 ${ocrPageRanges(confirmation.body.page_indexes)} 页` : "整份 PDF 的未受保护页面" : "当前文件的完整章节目录"}</dd></div>{confirmation.body.task_type === "ocr" ? <><div><dt>识别服务</dt><dd>{confirmation.provider}</dd></div><div><dt>语言</dt><dd>{languages.filter(([id]) => confirmation.body.task_options?.languages.includes(id as "ch")).map(([, label]) => label).join("、")}</dd></div><div><dt>后续操作</dt><dd>{confirmation.body.align_concepts ? "完成后生成概念关系待审候选" : "跳过本任务的概念对齐"}</dd></div><div><dt>人工保护</dt><dd>人工确认文字始终保留。{confirmation.body.task_options?.skip_reviewed ? "跳过当前来源已核验页。" : "重做已核验页，新结果需要重新核验。"}</dd></div></> : null}</dl><p>{confirmation.body.task_type === "ocr" ? "所选页会交给当前配置的识别服务。结果沿原发布流程处理，失败不会替换稳定公开文件。" : "自动提取保存为目录候选，不覆盖人工确认目录；请在目录工作台核对并采用。"}</p><div className={styles.actions}><button type="button" disabled={command.busy} onClick={() => setConfirmation(null)}>返回修改</button><button type="button" className={styles.primary} disabled={command.busy || Boolean(command.recovery)} onClick={() => void submit(confirmation.body)}>确认并建立任务</button></div></section> : null}
    <p className={styles.note}>检索索引沿公开来源自动增量更新。全库候选版本、版本切换与索引修复在<Link href="/admin/processing/semantic-index">检索索引维护</Link>中明确操作。</p>
  </div>;
}

function SourceForm({ owner, editionId, workId, seed, refresh, disabled, onReview }: { owner: string; editionId: string; workId: string; seed: ProcessingTaskSeed; refresh: number; disabled: boolean; onReview: (body: Creation, label: string, provider: string) => void }) {
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<Source>(path, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), [owner]);
  const resource = usePersistentWorkspace<Source>(`${endpoint}sources/${editionId}/?refresh=${refresh}`, owner, data => data.active_job_id ? 5000 : null, load);
  const [fileId, setFileId] = useState(seed.assetId || ""), [kind, setKind] = useState<"ocr" | "outline">(seed.taskType || "ocr");
  const [alignConcepts, setAlignConcepts] = useState(true);
  const [scope, setScope] = useState("all"), [pages, setPages] = useState(""), [error, setError] = useState("");
  const [options, setOptions] = useState<OCROptions>({ languages: ["ch", "en", "chinese_cht"], layout: true, quality_threshold: .75, detect_spreads: true, detect_garbled: true, skip_reviewed: true });
  const data = resource.data?.work_id === workId ? resource.data : null;
  const file = data?.files.find(row => row.id === (fileId || (data.files.length === 1 ? data.files[0].id : "")));
  function review() {
    if (!file || !data || disabled) return;
    try {
      const body: Creation = { action: "create", task_type: kind, asset_id: file.id, source_version: file.source_version, confirmed: true };
      if (kind === "ocr") { body.align_concepts = alignConcepts; body.task_options = options as Creation["task_options"]; if (scope === "pages") body.page_indexes = parseProcessingPages(pages, file.page_count); }
      setError(""); onReview(body, `${data.title} · ${data.edition_label} · ${file.filename} · 文件版本 ${file.version}`, data.provider_label);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "请核对处理范围。"); }
  }
  return <section className={styles.taskConfiguration}><header><h3>文件与处理设置</h3><button type="button" disabled={disabled} onClick={resource.reload}>读取最新文件</button></header>
    {resource.error || error ? <p role="alert" className={styles.notice}>{resource.error || error}</p> : null}
    {!data ? <p role="status">正在读取这个出版版本的当前文件…</p> : <>
      <fieldset disabled={disabled}><legend className={styles.srOnly}>本次任务配置</legend><label>处理文件<select value={file?.id || fileId} onChange={event => { setFileId(event.target.value); setError(""); }}><option value="">选择当前 PDF</option>{data.files.map(row => <option key={row.id} value={row.id} disabled={!row.can_run}>{row.filename} · 版本 {row.version} · {row.page_count} 页{row.reason ? ` · ${row.reason}` : ""}</option>)}</select></label>
      {!data.files.length ? <p className={styles.notice}>尚无可处理的当前 PDF。请从<Link href={`/admin/library/works/${workId}/files?edition=${editionId}`}>文件管理</Link>补充文件并完成校验。</p> : null}
      {fileId && !file ? <p className={styles.notice}>原任务文件已不在当前可用列表，请明确选择现用文件。旧文件与任务记录保留。</p> : null}
      <label>任务类型<select value={kind} onChange={event => setKind(event.target.value as "ocr" | "outline")}><option value="ocr">OCR 文字识别</option><option value="outline">章节目录提取</option></select></label>
      {kind === "ocr" ? <><label>处理范围<select value={scope} onChange={event => setScope(event.target.value)}><option value="all">整份 PDF</option><option value="pages">指定 PDF 页序</option></select></label>{scope === "pages" ? <label>PDF 页序<input value={pages} maxLength={10000} onChange={event => setPages(event.target.value)} placeholder="例如 1–3、8、12–15"/><small>按 PDF 实际页序填写，不使用印刷页码。人工确认文字始终跳过。</small></label> : null}
      <div className={styles.taskOptions}><fieldset><legend>识别语言</legend>{languages.map(([value, label]) => <label key={value}><input type="checkbox" checked={options.languages.includes(value)} disabled={options.languages.length === 1 && options.languages.includes(value)} onChange={event => setOptions(current => ({ ...current, languages: event.target.checked ? [...current.languages, value] : current.languages.filter(item => item !== value) }))}/>{label}</label>)}</fieldset><div>{([["layout", "请求版面分析"], ["skip_reviewed", "跳过当前来源已核验页"], ["detect_spreads", "标出疑似双页合扫"], ["detect_garbled", "标出乱码替换符"]] as const).map(([key, label]) => <label key={key}><input type="checkbox" checked={options[key]} onChange={event => setOptions(current => ({ ...current, [key]: event.target.checked }))}/>{label}</label>)}<label>待校对置信度阈值<select value={options.quality_threshold} onChange={event => setOptions(current => ({ ...current, quality_threshold: Number(event.target.value) }))}>{[.5, .65, .75, .85, .9, .95].map(value => <option key={value} value={value}>{value.toFixed(2)}</option>)}</select></label></div></div>
      <label className={styles.followupChoice}><input type="checkbox" checked={alignConcepts} onChange={event => setAlignConcepts(event.target.checked)}/><span>完成后自动开始概念对齐（基于馆内术语表）</span></label><p className={styles.note}>概念对齐保存为待审候选，保留已有人工决定；文字识别与检索更新沿原流程处理。</p>
      <p className={styles.note}>语言与版面策略传给现有服务；质量阈值用于提示人工核对，不代表正确率。人工文字与原 PDF 保留。</p>{data.paused ? <p className={styles.notice}>OCR 当前全局暂停，新任务会保留为暂停状态。</p> : null}{data.active_job_id ? <p className={styles.notice}>本出版版本已有未结束的 OCR 任务。<Link href={`/admin/processing?task_id=${data.active_job_id}&task_source=processing_job`}>查看任务并继续或取消</Link></p> : null}</> : <p className={styles.notice}>提取当前 PDF 的章节结构并保存候选，同一文件正在提取时复用原任务。人工确认目录继续保留。</p>}
      {!data.can_run ? <p className={styles.notice}>{data.denied_reason}</p> : null}<button type="button" className={styles.primary} disabled={!data.can_run || !file?.can_run || (kind === "ocr" && Boolean(data.active_job_id))} onClick={review}>核对处理范围</button></fieldset>
    </>}
  </section>;
}
