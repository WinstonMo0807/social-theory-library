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

export function CoverImage({ url, alt, token }: { url: string; alt: string; token: string | null }) {
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
  onDone?: () => void; onPreviewImage?: (src: string | null) => void;
};

export function EditionCoverEditor(props: EditionCoverEditorProps) {
  return <EditionCoverEditorState key={`${props.workId}:${props.editionId}`} {...props} />;
}

function EditionCoverEditorState({ editionId, workId, documentType, token, canEdit, onSaved, onDone, onPreviewImage }: EditionCoverEditorProps) {
  const [data, setData] = useState<CoverState | null>(null);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState("");
  const [page, setPage] = useState("1");
  const [file, setFile] = useState<File | null>(null);
  const [manual, setManual] = useState<Cover | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState("pdf");
  const [chosen, setChosen] = useState<Cover | null>(null);
  const active = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const retry = useRef<{ signature: string; requestKey: string } | null>(null);
  const url = `/catalog/admin/editions/${editionId}/cover/`;
  useUnsavedForm(file || chosen || (tab==="default" && data && !data.is_default) ? [file?.name,file?.size,file?.lastModified,chosen?.id,tab] : null, null);
  useEffect(()=>{
    if(!onPreviewImage)return;
    let active=true,objectUrl="";
    if(tab==="default")onPreviewImage("");
    else if(tab==="upload" && file){objectUrl=URL.createObjectURL(file);onPreviewImage(objectUrl);}
    else if(tab==="pdf" && chosen)void apiBlob(chosen.thumbnail_url,token).then(blob=>{objectUrl=URL.createObjectURL(blob);if(active)onPreviewImage(objectUrl);else URL.revokeObjectURL(objectUrl);}).catch(()=>{if(active){setFailed(true);setMessage("所选页面预览读取失败，请重试。");}});
    else onPreviewImage(null);
    return()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl);onPreviewImage(null);};
  },[tab,file,chosen,token,onPreviewImage]);
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
      if (["select", "upload", "default"].includes(action)) { setManual(null); if (action === "upload") { setFile(null); if (fileInput.current) fileInput.current.value = ""; } await onSaved(); setChosen(null); onDone?.(); }
    } catch (error) {
      setFailed(true);
      if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) { retry.current = null; if (error.status === 409) await reload().catch(() => undefined); }
      setMessage(submitted ? "封面已保存，但其他页面信息暂未刷新。请刷新查看，不必重复上传。" : error instanceof Error ? error.message : "操作暂未完成。可以使用同一请求重试，当前封面仍保留。");
    } finally { active.current = false; setBusy(""); }
  }
  const locked = !canEdit || Boolean(busy) || !data;
  const options = [...(data?.results ?? [])].sort((a,b)=>a.page_index-b.page_index);
  const renderOption = (option: Cover) => <button type="button" className={styles.choice} key={option.id} aria-pressed={chosen ? chosen.id===option.id : option.selected} disabled={locked} onClick={()=>setChosen(option)}>
    <CoverImage url={option.thumbnail_url} alt={`PDF第${option.page_index}页`} token={token}/><strong>第 {option.page_index} 页</strong><small>{option.selected ? "当前封面" : ""}</small>
  </button>;
  return <section className={styles.editor} aria-label="当前版本封面">
    <header className={styles.header}><h3>选择封面</h3><button type="button" disabled={Boolean(busy)} onClick={()=>void reload().catch(error=>{setFailed(true);setMessage(String(error.message));})}>刷新</button></header>
    <p>为本书选择合适的封面，读者将在图书详情页和搜索结果中看到。{!["book","journal_issue"].includes(documentType) ? "没有独立封面时，可保持默认样式。" : ""}</p>
    <nav className={styles.tabs} aria-label="封面来源">{[["pdf","PDF中选页"],["upload","上传图片"],["default","默认封面"]].map(([id,label])=><button type="button" key={id} aria-pressed={tab===id} disabled={Boolean(busy)} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    {message ? <p className={styles.message} role={failed ? "alert" : "status"}>{message}</p> : null}
    <div hidden={tab!=="pdf"}><h4>从PDF中选择封面页</h4>{data?.poll ? <p role="status">正在准备封面候选，可以先填写其他资料。</p> : null}{data?.state==="failed" ? <p role="alert">封面分析未完成，可以重新准备候选、指定PDF页或上传图片。</p> : null}
      {options.length ? <div className={styles.choices}>{(expanded ? options : options.slice(0,6)).map(renderOption)}</div> : <p>{data?.asset_id ? "暂时没有候选，可准备候选或指定PDF页。" : "PDF尚未准备好，可先上传图片或使用默认样式。"}</p>}
      <div className={styles.actions}>{options.length>6 ? <button type="button" onClick={()=>setExpanded(!expanded)}>{expanded ? "收起页面" : `查看全部${options.length}页`}</button> : null}<button type="button" disabled={locked || !data?.asset_id} onClick={()=>void command("regenerate")}>准备封面候选</button></div>
      <div className={styles.manual}><label>指定页码<input aria-label="封面PDF页码" type="number" min={1} max={data?.page_count || undefined} value={page} disabled={locked || !data?.asset_id} onChange={event=>setPage(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();if(!locked && data?.asset_id && Number.isInteger(Number(page)) && Number(page)>=1 && Number(page)<=data.page_count)void command("preview_page");}}}/><span>页 {data?.page_count ? `（共${data.page_count}页）` : ""}</span><button type="button" disabled={locked || !data?.asset_id || !Number.isInteger(Number(page)) || Number(page)<1 || Number(page)>data.page_count} onClick={()=>void command("preview_page")}>预览这一页</button></label>{manual ? <div className={styles.choices}>{renderOption(manual)}</div> : null}</div>
    </div>
    <div hidden={tab!=="upload"} className={styles.upload}><label>上传封面图片<input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" disabled={locked} onChange={event=>{setFile(event.target.files?.[0] ?? null);retry.current=null;}}/></label><p>支持 JPEG、PNG、WebP，最多12 MB。</p><Link href={`/admin/media?edition=${encodeURIComponent(editionId)}&slot=cover`}>从图片库选择</Link></div>
    <div hidden={tab!=="default"}><p>按题名显示，不设置封面图片。已保存的原图与历史仍保留。</p></div>
    <p className={styles.message}>此操作只保存封面，不会修改其他步骤的书目信息。其他未保存输入仍保留。</p>
    <footer className={styles.actions}><button type="button" disabled={Boolean(busy)} onClick={()=>{if((file || chosen || (tab==="default" && data && !data.is_default)) && !window.confirm("封面选择尚未保存，放弃并返回吗？"))return;onDone?.();}}>上一步</button><button type="button" disabled={locked || (tab==="pdf" ? !chosen : tab==="upload" ? !file : false)} onClick={()=>void command(tab==="pdf" ? "select" : tab==="upload" ? "upload" : "default",chosen || undefined)}>{busy ? "正在保存…" : "保存封面并返回 →"}</button></footer>
  </section>;
}
