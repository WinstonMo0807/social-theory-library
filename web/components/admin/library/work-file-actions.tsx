"use client";

import { confirmAction } from "@/lib/ui-dialog";


import { LoadingState } from "@/components/ui/loading-state";
import { createRequestKey } from "../../../lib/request-key";
import { Check, FileText, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";
import { ApiRequestError, subscribeToSessionChanges, type UploadProgress } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { adoptWorkFile, createWorkEdition, prepareFileAdoption, readWorkFileReceipt, uploadWorkFile, workFileBytes } from "@/lib/api/work-files.client";
import type { FileAdoptPreview, FileAdoptResult, WorkFile, WorkFileUploadResult, WorkFilesState } from "@/lib/api/work-files.types";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { WorkFilePdf } from "./work-file-preview";
import styles from "./work-files.module.css";

function useActionLifetime(request?: RefObject<AbortController | null>) {
  const alive = useRef(true);
  useEffect(() => { alive.current = true; const clear = () => { alive.current = false; request?.current?.abort(); }; const unsubscribe = subscribeToSessionChanges(clear); return () => { clear(); unsubscribe(); }; }, [request]);
  return alive;
}
const failure = (reason: unknown) => reason instanceof Error ? reason.message : "操作尚未完成，当前输入保留。";

export function NewWorkEditionDialog({ state, ownerId, onClose, onCreated, onRefresh }: {
  state: WorkFilesState; ownerId: string; onClose: () => void; onCreated: (editionId: string) => void; onRefresh: () => void;
}) {
  const [label, setLabel] = useState(""), [year, setYear] = useState(""), [publisher, setPublisher] = useState("");
  const [base, setBase] = useState(state.work.updated_at), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const receipt = useRef<{ fingerprint: string; id: string } | null>(null), alive = useActionLifetime();
  const dirty = Boolean(label || year || publisher), stale = base !== state.work.updated_at;
  useUnsavedForm(dirty, false);
  const close = async () => { if (!busy && (!dirty || (await confirmAction("新增版本尚未保存，确定放弃当前输入吗？")))) onClose(); };
  async function save() {
    if (busy || stale || !label.trim()) return;
    const value = { expected_work_updated_at: base, version_label: label.trim(), publication_year: year ? Number(year) : null, publisher: publisher.trim() };
    const fingerprint = JSON.stringify(value);
    const request_key = receipt.current?.fingerprint === fingerprint ? receipt.current.id : createRequestKey();
    receipt.current = { fingerprint, id: request_key }; setBusy(true); setError("");
    try {
      const result = await withPrivateOwner(ownerId, () => createWorkEdition(state.work.id, { ...value, request_key }));
      if (!alive.current) return;
      if (result.work_id !== state.work.id || result.request_key !== request_key) throw new Error("返回结果与当前作品不一致，请重新核对。");
      onCreated(result.edition_id);
    } catch (reason) { if (alive.current) { setError(failure(reason)); if (reason instanceof ApiRequestError && reason.status === 409) onRefresh(); } }
    finally { if (alive.current) setBusy(false); }
  }
  return <Dialog open className={styles.dialog} aria-labelledby="new-edition-title" onRequestClose={close}><header><div><h2 id="new-edition-title">新增出版版本</h2><p>归入《{state.work.title}》，保留现有出版版本。</p></div><button aria-label="关闭新增版本" disabled={busy} onClick={close}><X size={18} /></button></header>
    <form onSubmit={event => { event.preventDefault(); void save(); }}><label>版本名称<input required maxLength={120} value={label} disabled={busy} onChange={event => setLabel(event.target.value)} placeholder="例如初版、修订版或不同译本" /></label><div className={styles.twoFields}><label>出版年<input type="number" min={1} max={9999} value={year} disabled={busy} onChange={event => setYear(event.target.value)} /></label><label>出版机构<input maxLength={300} value={publisher} disabled={busy} onChange={event => setPublisher(event.target.value)} /></label></div><p className={styles.muted}>新版本先保存为草稿。责任者、出版信息和版权可继续在版本信息中完善；不会自动设为主版本或公开。</p>{error ? <p role="alert" className={styles.error}>{error}</p> : null}{stale ? <div className={styles.warning}><p>作品已经更新，请核对最新版本列表后继续。当前输入保留。</p><button type="button" onClick={() => { setBase(state.work.updated_at); receipt.current = null; setError(""); }}>已核对，采用最新作品信息</button></div> : null}<footer><button type="button" disabled={busy} onClick={close}>取消</button><button className={styles.primary} disabled={busy || stale || !state.capabilities.can_edit}>{busy ? "正在保存…" : "建立版本草稿"}</button></footer></form>
  </Dialog>;
}

export function AdoptWorkFileDialog({ editionId, file, ownerId, onClose, onChanged }: {
  editionId: string; file: WorkFile; ownerId: string; onClose: () => void; onChanged: () => void;
}) {
  const [preview, setPreview] = useState<FileAdoptPreview | null>(null), [result, setResult] = useState<FileAdoptResult | null>(null);
  const [attempt, setAttempt] = useState(0), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [acknowledged, setAcknowledged] = useState(""), alive = useActionLifetime();
  useEffect(() => {
    let current = true;
    void withPrivateOwner(ownerId, () => prepareFileAdoption(editionId, file.id)).then(value => {
      if (!current || !alive.current) return;
      if (value.target_asset_id !== file.id || value.edition_id !== editionId) throw new Error("返回的文件影响不属于当前版本。");
      setPreview(value); setError("");
    }).catch(reason => { if (current && alive.current) setError(failure(reason)); });
    return () => { current = false; };
  }, [editionId, file.id, ownerId, attempt, alive]);
  async function confirm() {
    if (!preview || busy || acknowledged !== preview.fingerprint || !preview.can_adopt || result) return;
    setBusy(true); setError("");
    try {
      const receipt = await withPrivateOwner(ownerId, () => adoptWorkFile(editionId, file.id, { request_key: preview.request_key, fingerprint: preview.fingerprint, confirm: true }));
      if (!alive.current) return;
      if (receipt.request_key !== preview.request_key || receipt.target_asset_id !== file.id || receipt.edition_id !== editionId || !receipt.command_accepted) throw new Error("尚未确认此次文件采用结果，请使用原请求重试。");
      setResult(receipt); onChanged();
    } catch (reason) { if (alive.current) setError(failure(reason)); }
    finally { if (alive.current) setBusy(false); }
  }
  const close = () => { if (!busy) onClose(); };
  return <Dialog open className={styles.dialog} aria-labelledby="adopt-file-title" onRequestClose={close}><header><div><h2 id="adopt-file-title">确认阅读文件与引用影响</h2><p>{file.filename || "所选阅读文件"} · 第 {file.version} 份</p></div><button aria-label="关闭文件采用" disabled={busy} onClick={close}><X size={18} /></button></header>{error ? <p role="alert" className={styles.error}>{error}</p> : null}{result ? <div className={styles.success} role="status"><Check size={22} /><h3>{result.effective ? "所选文件已生效" : "采用请求已保存"}</h3><p>{result.detail}</p><p>请在发布历史核对最终状态。旧文件与历史引用保留。</p></div> : preview ? <><p className={styles.warning}>采用只更换这个出版版本的阅读文件。请先核对原件内容、版本归属及下面的实际影响。</p><ul className={styles.impactList}>{preview.impact.map((value, index) => <li key={index}>{value}</li>)}</ul>{preview.blocking.map((value, index) => <p className={styles.error} key={index}>{value}</p>)}{preview.already_current ? <p role="status">这份文件已经是当前阅读文件，无需重复采用。</p> : <label className={styles.check}><input type="checkbox" disabled={busy || !preview.can_adopt} checked={acknowledged === preview.fingerprint} onChange={event => setAcknowledged(event.target.checked ? preview.fingerprint : "")} />已核对文件归属和引用影响，确认采用。</label>}</> : <LoadingState role="status">正在读取文件影响…</LoadingState>}<footer><button disabled={busy} onClick={close}>{result ? "返回文件与历史" : "继续核对"}</button>{!result ? <><button disabled={busy} onClick={() => { setPreview(null); setAcknowledged(""); setAttempt(value => value + 1); }}>重新读取影响</button><button className={styles.primary} disabled={busy || !preview?.can_adopt || preview.already_current || acknowledged !== preview.fingerprint} onClick={() => void confirm()}>{busy ? "正在提交…" : error ? "重试同一采用请求" : "确认采用"}</button></> : null}</footer></Dialog>;
}

export function UploadWorkFileDialog({ state, ownerId, action, onClose, onAccepted, onRefresh, defaultGenerateReader=true }: {
  state: WorkFilesState; ownerId: string; action: "supplement" | "replace"; onClose: () => void; onAccepted: (result: WorkFileUploadResult) => void; onRefresh: () => void; defaultGenerateReader?:boolean;
}) {
  const initial = state.edition!;
  const [base, setBase] = useState(initial), [file, setFile] = useState<File | null>(null), [reader, setReader] = useState(defaultGenerateReader);
  const [step, setStep] = useState<"upload" | "confirm" | "result">("upload"), [accepted, setAccepted] = useState<WorkFileUploadResult | null>(null);
  const [localPreview, setLocalPreview] = useState<{ file: File; url: string } | null>(null), [progress, setProgress] = useState<UploadProgress | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [outcome, setOutcome] = useState<"" | "unknown" | "not_found">("");
  const transfer = useRef<AbortController | null>(null);
  const [acknowledged, setAcknowledged] = useState(false), nonce = useRef<{ key: string; id: string; file: File } | null>(null), alive = useActionLifetime(transfer);
  const extension = file?.name.split(".").at(-1)?.toLowerCase().replace(/^tif$/, "tiff");
  const format = state.capabilities.formats.find(value => value.extension === extension);
  const invalid = file ? !format?.available ? format?.reason || "当前不支持保存这个文件格式。" : !file.size ? "所选文件为空，请重新选择。" : file.size > format.max_bytes ? `文件超过此格式 ${workFileBytes(format.max_bytes)} 的上限。` : action === "replace" && !format.can_generate_reader ? "此格式当前无法生成阅读副本，不能替换阅读文件；可返回上级改用补充文件保留原件。" : "" : "";
  const generateReader = Boolean((action === "replace" || reader) && format?.can_generate_reader);
  const localPdf = localPreview?.file === file ? localPreview.url : "";
  const stale = base.updated_at !== initial.updated_at || base.current_reader_asset_id !== initial.current_reader_asset_id;
  const dirty = Boolean(file && !accepted);
  useUnsavedForm(dirty, false);
  useEffect(() => {
    if (!localPreview) return;
    const { url } = localPreview;
    const unsubscribe = subscribeToSessionChanges(() => { URL.revokeObjectURL(url); setLocalPreview(null); });
    return () => { URL.revokeObjectURL(url); unsubscribe(); };
  }, [localPreview]);
  const close = async () => {
    if (busy) return;
    if (outcome === "unknown") { void checkReceipt(); return; }
    if (!dirty || (await confirmAction(outcome ? "尚未查到本次请求，服务器仍可能稍后完成。确定返回文件记录核对吗？请勿另建相同文件请求。" : "文件请求尚未保存，确定放弃此次选择吗？"))) onClose();
  };
  function choose(value: File | null) {
    if (busy || outcome) return;
    if (localPreview) URL.revokeObjectURL(localPreview.url);
    setLocalPreview(value?.name.toLowerCase().endsWith(".pdf") ? { file: value, url: URL.createObjectURL(value) } : null);
    setFile(value); setError(""); setAcknowledged(false); setStep("upload"); nonce.current = null;
  }
  function acceptReceipt(receipt: WorkFileUploadResult, requestKey: string) {
    if (receipt.edition_id !== base.id || receipt.work_id !== state.work.id || receipt.request_key !== requestKey || !receipt.accepted) throw new Error("返回结果与此文件请求不一致，请先查询本次请求。");
    setOutcome(""); setAccepted(receipt); setStep("result"); onAccepted(receipt);
  }
  async function checkReceipt() {
    if (transfer.current || !nonce.current || !alive.current) return;
    const controller = new AbortController(), requestKey = nonce.current.id;
    transfer.current = controller; setBusy(true); setError("");
    try {
      const receipt = await withPrivateOwner(ownerId, () => readWorkFileReceipt(base.id, requestKey, controller.signal), controller.signal);
      if (alive.current) acceptReceipt(receipt, requestKey);
    } catch (reason) {
      if (alive.current) {
        if (reason instanceof ApiRequestError && reason.status === 404) { setOutcome("not_found"); setError("当前尚未查到本次请求，服务器仍可能在处理。可再次查询，或沿用同一请求编号重试；不会另建请求。"); }
        else { setOutcome("unknown"); setError(failure(reason)); }
      }
    } finally { transfer.current = null; if (alive.current) setBusy(false); }
  }
  async function submit() {
    if (outcome === "unknown") { await checkReceipt(); return; }
    if (!file || invalid || transfer.current || (stale && !outcome) || !acknowledged || !alive.current) return;
    const key = JSON.stringify({ edition: base.id, updated: base.updated_at, reader: base.current_reader_asset_id, action, generateReader });
    const requestKey = nonce.current?.key === key && nonce.current.file === file ? nonce.current.id : createRequestKey();
    nonce.current = { key, id: requestKey, file };
    const controller = new AbortController(); transfer.current = controller;
    setBusy(true); setError(""); setProgress(null);
    const body = new FormData(); body.append("file", file); body.append("action", action); body.append("request_key", requestKey); body.append("confirm", "true"); body.append("expected_updated_at", base.updated_at); body.append("generate_reader", String(generateReader));
    if (base.current_reader_asset_id) body.append("expected_reader_asset_id", base.current_reader_asset_id);
    try {
      const receipt = await withPrivateOwner(ownerId, () => uploadWorkFile(base.id, body, value => { if (alive.current) setProgress(value); }, controller.signal), controller.signal);
      if (!alive.current) return;
      acceptReceipt(receipt, requestKey);
    } catch (reason) { if (alive.current) {
      const knownRejected = reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500 && ![408, 429].includes(reason.status);
      setOutcome(knownRejected ? "" : "unknown"); setError(failure(reason));
      if (reason instanceof ApiRequestError && reason.status === 409) onRefresh();
    } }
    finally { transfer.current = null; if (alive.current) setBusy(false); }
  }
  const edition = state.editions.find(row => row.id === base.id);
  return <Dialog open className={`${styles.dialog} ${styles.uploadDrawer}`} aria-labelledby="upload-file-title" onRequestClose={close}><header><h2 id="upload-file-title">{action === "replace" ? "替换文件与预览" : "补充文件与预览"}</h2><button aria-label="关闭文件上传" disabled={busy} onClick={close}><X size={18} /></button></header><ol className={styles.steps}>{[["upload", "上传与预览"], ["confirm", "确认影响"], ["result", "请求已保存"]].map(([key, text], index) => <li key={key} aria-current={step === key ? "step" : undefined}><span>{index + 1}</span>{text}</li>)}</ol><section className={styles.selectedVersion}><small>当前版本</small><div className={styles.selectedVersionBody}>{edition?.cover_url ? <img src={edition.cover_url} alt={`${edition.version_label || state.work.title}封面`} /> : null}<div><strong>{edition?.version_label || edition?.label || "当前出版版本"}{edition?.is_primary ? <span className={styles.badge}>主版本</span> : null}</strong><p>{edition?.publication_year || "年份待补"} · {edition?.original_count || 0} 个原件 · {edition?.reader_count || 0} 个阅读副本</p></div></div></section>
    {step !== "result" ? <>{step === "upload" ? <><label className={styles.dropzone} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (event.dataTransfer.files.length > 1) setError("本次请选择一份文件，其他文件可分别补充。"); else choose(event.dataTransfer.files[0] || null); }}><Upload size={24} /><strong>点击选择文件或拖到此处</strong><span>{state.capabilities.formats.filter(value => value.available).map(value => `${value.extension.toUpperCase()} ${workFileBytes(value.max_bytes)}`).join(" · ") || "当前没有可用的文件上传格式"}</span><input aria-label="选择当前版本的新文件" type="file" accept={state.capabilities.formats.filter(value => value.available).flatMap(value => value.extension === "tiff" ? [".tif", ".tiff"] : [`.${value.extension}`]).join(",")} disabled={busy || Boolean(outcome) || !state.capabilities.can_edit} onChange={event => { choose(event.target.files?.[0] || null); event.target.value = ""; }} /></label>{file ? <div className={styles.chosenFile}><FileText size={24} /><div><strong>{file.name}</strong><small>{workFileBytes(file.size)}</small></div><button aria-label="移除所选文件" disabled={busy || Boolean(outcome)} onClick={() => choose(null)}><X size={14} /></button></div> : null}{file && !invalid ? <><label className={styles.check}><input type="checkbox" checked={generateReader} disabled={busy || Boolean(outcome) || action === "replace" || !format?.can_generate_reader} onChange={event => { setReader(event.target.checked); setAcknowledged(false); }} />生成可阅读的 PDF 副本{action === "replace" ? "（替换文件必须生成）" : ""}</label>{!format?.can_generate_reader ? <p className={styles.warning}>{format?.reason || "此格式当前仅能保留原件，尚不能生成阅读副本。"}</p> : format.max_derived_bytes ? <p className={styles.muted}>转换后阅读文件上限 {workFileBytes(format.max_derived_bytes)}。原件单独保留，转换失败可查看原因。</p> : null}{extension === "pdf" && localPdf ? <WorkFilePdf key={localPdf} url={localPdf} atlasIntake /> : <p className={styles.muted}>原件将在保存后处理。只有实际生成并校验的 PDF 才能分页预览。</p>}</> : null}</> : <><div className={styles.chosenFile}><FileText size={22} /><div><strong>{file?.name}</strong><small>{file ? workFileBytes(file.size) : ""}</small></div></div><h3>请核对本次文件影响</h3><ul className={styles.impactList}><li>新上传的原件单独保存。旧原件和历史引用保留。</li><li>{generateReader ? "生成的阅读副本需要检查后明确采用，上传完成不会直接切换公开文件。" : "本次仅保留原件，不生成或采用新的阅读文件。"}</li><li>已公开的阅读文件在处理期间继续服务；处理失败可以恢复原任务。</li><li>书目与人工确认字段不因新增文件而自动覆盖。</li></ul><label className={styles.check}><input type="checkbox" checked={acknowledged} disabled={busy || Boolean(outcome)} onChange={event => setAcknowledged(event.target.checked)} />已核对出版版本、所选文件与历史保留说明。</label></>}
    {invalid || error ? <p className={styles.error} role="alert">{invalid || error}</p> : null}{action === "replace" && file && !format?.can_generate_reader ? <button disabled={busy} onClick={close}>返回上级，改用补充文件</button> : null}{outcome ? <div className={styles.warning}><p>服务器可能已经接收文件。先查询本次请求，未查到时仍沿用原编号重试。</p><button disabled={busy} onClick={() => void checkReceipt()}>重新查询本次请求</button></div> : null}{stale ? <div className={styles.warning}><p>当前版本或阅读文件已变化，所选文件仍保留。请重新核对影响。</p><button disabled={busy || Boolean(outcome)} onClick={() => { setBase(initial); setAcknowledged(false); nonce.current = null; setStep("confirm"); setError(""); }}>已核对，使用最新版本信息</button></div> : null}{busy ? <div role="status"><p>{progress ? `已上传 ${workFileBytes(progress.loaded)} / ${workFileBytes(progress.total)}，等待服务器确认文件请求。` : "正在提交文件请求…"}</p>{progress?.total ? <progress max={progress.total} value={progress.loaded} aria-label="实际文件上传字节" /> : null}<button type="button" onClick={() => transfer.current?.abort()}>取消传输并保留请求</button><p className={styles.muted}>取消只停止当前传输或等待；服务器可能已经接收，随后请查询结果。</p></div> : null}<footer><button disabled={busy || Boolean(outcome)} onClick={step === "confirm" ? () => { setStep("upload"); setAcknowledged(false); } : close}>{step === "confirm" ? "返回文件预览" : "取消"}</button>{step === "upload" ? <button className={styles.primary} disabled={!file || Boolean(invalid) || busy || stale} onClick={() => setStep("confirm")}>下一步：确认影响</button> : <button className={styles.primary} disabled={!acknowledged || busy || (stale && !outcome) || Boolean(invalid) || !state.capabilities.can_edit} onClick={() => void submit()}>{busy ? "正在核对请求…" : outcome === "unknown" ? "查询本次请求" : error ? "重试同一文件请求" : "保存原件并开始处理"}</button>}</footer></> : <div className={styles.success} role="status"><Check size={28} /><h3>文件请求已保存</h3><p>{accepted?.detail}</p><p>继续在文件历史中查看实际处理结果，完成核对后再采用阅读文件。</p><footer><button className={styles.primary} onClick={onClose}>前往文件与处理记录</button></footer></div>}
  </Dialog>;
}
