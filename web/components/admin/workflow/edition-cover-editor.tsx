"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiBlob, apiRequest, ApiRequestError } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import styles from "./edition-cover-editor.module.css";

type Cover = { id: string; page_index: number; thumbnail_url: string; selected: boolean; reasons: string[] };
type CoverState = { edition_id: string; work_id: string; fingerprint: string; asset_id: string | null; source_checksum: string | null; page_count: number; state: string; poll: boolean; is_default: boolean; has_unpublished_cover: boolean; image_url: string; results: Cover[]; detail?: string; preview_candidate?: Cover | null };

function CoverImage({ url, alt, token }: { url: string; alt: string; token: string | null }) {
  const [image, setImage] = useState<{ url: string; token: string | null; src: string; failed: boolean } | null>(null);
  useEffect(() => {
    let active = true, objectUrl = "";
    if (url) void apiBlob(url, token).then((blob) => { objectUrl = URL.createObjectURL(blob); if (active) setImage({ url, token, src: objectUrl, failed: false }); else URL.revokeObjectURL(objectUrl); }).catch(() => { if (active) setImage({ url, token, src: "", failed: true }); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url, token]);
  const current = image?.url === url && image.token === token ? image : null;
  return current?.src ? <Image className={styles.image} src={current.src} width={190} height={240} unoptimized alt={alt} /> : <div className={styles.placeholder}>{current?.failed ? "图片暂时无法读取，请刷新后重试" : "正在读取图片…"}</div>;
}

type EditionCoverEditorProps = {
  editionId: string; workId: string; documentType: string; token: string | null; canEdit: boolean;
  beforeAction: () => Promise<boolean>; onSaved: () => void | Promise<void>;
};

export function EditionCoverEditor(props: EditionCoverEditorProps) {
  return <EditionCoverEditorState key={`${props.workId}:${props.editionId}`} {...props} />;
}

function EditionCoverEditorState({ editionId, workId, documentType, token, canEdit, beforeAction, onSaved }: EditionCoverEditorProps) {
  const [data, setData] = useState<CoverState | null>(null);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState("");
  const [page, setPage] = useState("1");
  const [file, setFile] = useState<File | null>(null);
  const [manual, setManual] = useState<Cover | null>(null);
  const [expanded, setExpanded] = useState(false);
  const active = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const retry = useRef<{ signature: string; requestKey: string } | null>(null);
  const url = `/catalog/admin/editions/${editionId}/cover/`;
  useUnsavedForm(file ? [file.name, file.size, file.lastModified] : null, null);
  const reload = useCallback((signal?: AbortSignal) => {
    return apiRequest<CoverState>(url, { signal }, token).then(value => {
      if (value.edition_id !== editionId || value.work_id !== workId) throw new Error("封面不属于当前作品或版本，请重新进入。");
      if (!signal?.aborted) setData(value);
    });
  }, [url, token, editionId, workId]);
  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal).catch((error) => { if (!controller.signal.aborted) { setFailed(true); setMessage(error instanceof Error ? error.message : "封面读取失败。可继续使用默认样式。"); } });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    if (!data?.poll || busy) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => { void reload(controller.signal).catch(() => { if (!controller.signal.aborted) { setFailed(true); setMessage("封面状态暂时无法更新，请点击刷新。不会影响其他填写。"); } }); }, 2500);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [data, busy, reload]);

  async function command(action: string, candidate?: Cover) {
    if (!data || active.current || !canEdit) return;
    if (["select", "upload", "default"].includes(action) && !await beforeAction()) { setFailed(true); setMessage("请先保存本页填写，再单独保存封面。当前填写不会自动提交。"); return; }
    if (active.current) return;
    if (action === "upload" && !file) return;
    active.current = true; setBusy(action); setFailed(false); setMessage("");
    const body = { action, fingerprint: data.fingerprint, asset_id: data.asset_id ?? "", source_checksum: data.source_checksum ?? "", page_index: page, candidate_id: candidate?.id ?? "" };
    const signature = JSON.stringify([body, action === "upload" && file ? [file.name, file.size, file.lastModified] : null]);
    if (retry.current?.signature !== signature) retry.current = { signature, requestKey: createRequestKey() };
    let submitted = false;
    try {
      let requestBody: string | FormData = JSON.stringify({ ...body, request_key: retry.current.requestKey });
      if (action === "upload" && file) { const form = new FormData(); for (const [key, value] of Object.entries({ ...body, request_key: retry.current.requestKey })) form.append(key, value); form.append("image", file); requestBody = form; }
      const result = await apiRequest<CoverState>(url, { method: "POST", body: requestBody }, token);
      submitted = true; retry.current = null; setData(result); setMessage(result.detail || "封面操作已完成。");
      if (action === "preview_page") setManual(result.preview_candidate ?? null);
      if (["select", "upload", "default"].includes(action)) { setManual(null); if (action === "upload") { setFile(null); if (fileInput.current) fileInput.current.value = ""; } await onSaved(); }
    } catch (error) {
      setFailed(true);
      if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) { retry.current = null; if (error.status === 409) await reload().catch(() => undefined); }
      setMessage(submitted ? "封面已保存，但其他页面信息暂未刷新。请刷新查看，不必重复上传。" : error instanceof Error ? error.message : "操作暂未完成。可以使用同一请求重试，当前封面仍保留。");
    } finally { active.current = false; setBusy(""); }
  }
  const locked = !canEdit || Boolean(busy) || !data;
  const options = data?.results ?? [];
  const renderOption = (option: Cover, manualChoice = false) => <article className={styles.choice} key={option.id}>
    <CoverImage url={option.thumbnail_url} alt={`PDF第${option.page_index}页封面候选`} token={token} />
    <strong>PDF 第 {option.page_index} 页</strong><small>{option.reasons?.slice(0, 2).join("；") || "来自当前PDF"}</small>
    <button type="button" disabled={locked || option.selected} onClick={() => void command("select", option)}>{option.selected ? "已选用这一页" : manualChoice ? "用这一页作封面" : "选作封面"}</button>
  </article>;
  return <section className={styles.editor} aria-label="当前版本封面">
    <header className={styles.header}><h3>封面（可选）</h3><button type="button" disabled={Boolean(busy)} onClick={() => void reload().catch((error) => { setFailed(true); setMessage(String(error.message)); })}>刷新封面</button></header>
    <p>PDF入队后会先校验文件并准备候选，不用等全文OCR。候选仅供选择，不会自动替换你选好的封面。{!["book", "journal_issue"].includes(documentType) ? "论文等没有独立封面时，可以直接保持默认样式。" : "没有合适封面也可正常上架。"}</p>
    {message ? <p className={styles.message} role={failed ? "alert" : "status"}>{message}</p> : null}
    <div className={styles.current}><div>{data?.image_url ? <CoverImage url={data.image_url} alt="当前保存的封面" token={token} /> : <div className={styles.placeholder}>默认样式<br />按题名显示，无需封面图片</div>}</div><div>
      <p>{data?.has_unpublished_cover ? "已保存封面修改，正式发布后读者才会看到。" : data?.is_default ? "当前使用默认样式。" : data ? "当前保存的封面" : "正在读取当前版本…"}</p>
      <label><span>上传封面图片</span><input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" disabled={locked} onChange={(event) => { setFile(event.target.files?.[0] ?? null); retry.current = null; }} /></label>
      <p>支持 JPEG、PNG、WebP，最多12 MB。这里只保存封面，不会发布书目。</p>
      <div className={styles.actions}><button type="button" disabled={locked || !file} onClick={() => void command("upload")}>{busy === "upload" ? "正在保存封面…" : "上传并保存封面"}</button><button type="button" disabled={locked} onClick={() => void command("default")}>使用默认样式，不选封面</button><Link href={`/admin/media?edition=${encodeURIComponent(editionId)}&slot=cover`}>从媒体库选封面</Link></div>
    </div></div>
    <h4>系统推荐的PDF页面</h4>
    {data?.poll ? <p role="status">正在准备封面候选，页面会自动更新。你可以先填写其他资料。</p> : null}
    {data?.state === "failed" ? <p role="alert">这次封面分析未完成。可重新准备候选、指定PDF页或上传图片，不影响上架。</p> : null}
    {options.length ? <div className={styles.choices}>{(expanded ? options : options.slice(0, 3)).map((option) => renderOption(option))}</div> : <p>{data?.asset_id ? "暂时没有候选，可点击准备候选或指定PDF页。" : "PDF尚未准备好。可先上传封面图片，或保持默认样式。"}</p>}
    <div className={styles.actions}>{options.length > 3 ? <button type="button" onClick={() => setExpanded(!expanded)}>{expanded ? "收起候选" : `查看全部${options.length}张候选`}</button> : null}<button type="button" disabled={locked || !data?.asset_id} onClick={() => void command("regenerate")}>{busy === "regenerate" ? "正在分析PDF页面…" : options.length ? "重新准备封面候选" : "准备封面候选"}</button></div>
    <div className={styles.manual}><label><span>自己选择PDF页</span><input aria-label="封面PDF页码" type="number" min={1} max={data?.page_count || undefined} value={page} disabled={locked || !data?.asset_id} onChange={(event) => setPage(event.target.value)} /><span>{data?.page_count ? `共${data.page_count}页` : "按PDF实际页序，不是书上印的页码"}</span><button type="button" disabled={locked || !data?.asset_id || !Number.isInteger(Number(page)) || Number(page) < 1} onClick={() => void command("preview_page")}>{busy === "preview_page" ? "正在准备这一页…" : "预览这一页"}</button></label>{manual ? <div className={styles.choices}>{renderOption(manual, true)}</div> : null}</div>
  </section>;
}
