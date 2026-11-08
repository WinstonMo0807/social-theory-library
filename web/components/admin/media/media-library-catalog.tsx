"use client";

import { confirmAction } from "@/lib/ui-dialog";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Image as ImageIcon, Search, Upload } from "lucide-react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { subscribeToSessionChanges } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useCatalogCommand } from "../workflow/use-intake-command";
import { PrivateMediaImage } from "./media-crop";
import { ownedRequest, useOwnedRead } from "./media-requests";
import frame from "./media-workspace.module.css";
import styles from "./media-library.module.css";

type Media = components["schemas"]["MediaAsset"];
type Metadata = components["schemas"]["LibraryMediaCommandRequest"]["metadata"];
type Receipt = components["schemas"]["LibraryMediaReceipt"];
type Command = Omit<components["schemas"]["LibraryMediaCommandRequest"], "request_id">;
type References = { count: number; scope: string; results: { id: string; kind: string; label: string; detail: string; editor_url: string; public_url: string }[] };
type State = Omit<components["schemas"]["LibraryMediaState"], "references"> & { references: References };
type Collection = components["schemas"]["MediaCollection"];
const textFields = ["alt_text", "source_label", "source_url", "rights", "license", "credit"] as const;
const fieldLabels = { alt_text: "替代文字", source_label: "来源说明", source_url: "来源网址", rights: "使用权说明", license: "许可", credit: "署名" };
const referenceLabels: Record<string, string> = { current_public: "当前公开使用", draft: "待发布草稿", history: "历史引用", canonical: "当前对象选图" };
function metadataOf(media: Media): Metadata {
  return { alt_text: media.alt_text || "", source_label: media.source_label || "", source_url: media.source_url || "", rights: media.rights || "",
    license: media.license || "", credit: media.credit || "", focal_x: media.focal_x ?? 0.5, focal_y: media.focal_y ?? 0.5 };
}
const dateLabel = (value: string) => new Date(value).toLocaleString("zh-CN");

export function MediaLibraryCatalog({ initialMediaId }: { initialMediaId: string }) {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return user ? <Catalog key={`${user.id}:${epoch}:${initialMediaId}`} owner={String(user.id)} initialMediaId={initialMediaId} canEdit={hasAdminCapability(user, "can_edit_metadata")} /> : <LoadingState role="status">正在核对当前管理账户…</LoadingState>;
}

function Catalog({ owner, initialMediaId, canEdit }: { owner: string; initialMediaId: string; canEdit: boolean }) {
  const [selected, setSelected] = useState(initialMediaId), [query, setQuery] = useState(""), [submitted, setSubmitted] = useState("");
  const [page, setPage] = useState(1), [tab, setTab] = useState("library"), [dirty, setDirty] = useState(false), [blocked, setBlocked] = useState(false);
  const [switchTo, setSwitchTo] = useState(""), [uploading, setUploading] = useState(false), [message, setMessage] = useState("");
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => { const controller = new AbortController(); lifetime.current = controller; return () => controller.abort(); }, []);
  const collection = useOwnedRead<Collection>(owner, `/catalog/admin/media/collection/?${new URLSearchParams({ q: submitted, page: String(page) })}`);
  const mediaId = selected;
  const locked = blocked || uploading;
  useUnsavedForm(uploading, false);
  const select = (id: string) => { setSelected(id); setDirty(false); setBlocked(false); setSwitchTo(""); };
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!canEdit || locked || dirty) return;
    const form = event.currentTarget, controller = lifetime.current;
    setUploading(true); setMessage("");
    try {
      const media = await ownedRequest<Media>(owner, "/catalog/admin/media/", { method: "POST", body: new FormData(form), signal: controller?.signal });
      if (controller?.signal.aborted) return;
      select(media.id); collection.retry(); form.reset(); setTab("library");
      setMessage("图片已保存到原媒体库，原件保留。可继续补充出处，再从使用对象进入裁切与发布。");
    } catch (error) { if (!controller?.signal.aborted) setMessage(`${error instanceof Error ? error.message : "上传结果暂未确认。"} 文件选择保留；重传同一图片会按原文件摘要复用。`); }
    finally { if (!controller?.signal.aborted) setUploading(false); }
  }
  return <div className={frame.workspace}>
    <div className={frame.toolbar}><nav aria-label="媒体位置"><Link href="/admin/editorial">内容</Link><span>›</span><span>封面与媒体资料</span></nav><span>{dirty ? "有未保存的资料" : "原件与已发布修订保留"}</span></div>
    <header className={frame.header}><div><h1>封面与媒体资料</h1></div><div><span>素材库</span><strong>{collection.data ? `${collection.data.count} 张图片` : "正在读取"}</strong></div></header>
    <nav className={frame.tabs} aria-label="媒体来源"><button aria-current={tab === "library" ? "page" : undefined} onClick={() => setTab("library")}>复用媒体</button><button aria-current={tab === "upload" ? "page" : undefined} onClick={() => setTab("upload")}>上传或来源</button></nav>
    {message ? <p className={frame.feedback} role="status">{message}</p> : null}
    {!canEdit ? <p className={frame.note}>当前账户可查看媒体，修改需要材料编辑权限。</p> : null}
    <div className={`${frame.columns} ${styles.catalogColumns}`}>
      <section className={frame.sources} aria-label="图片列表"><h2>{tab === "upload" ? "上传图片" : "选择图片"}</h2>
        {tab === "upload" ? <form className={styles.form} onSubmit={upload}><label>图片文件<input name="image" type="file" accept="image/jpeg,image/png,image/webp" required disabled={!canEdit || locked || dirty} /></label><label>替代文字<input name="alt_text" maxLength={1000} disabled={!canEdit || locked || dirty} /></label><small>JPEG、PNG 或 WebP，最大 20 MB。相同原件复用已有素材。</small>{dirty ? <p>请先保存当前资料，再上传并选择其他图片。</p> : null}<button type="submit" disabled={!canEdit || locked || dirty}><Upload size={14} />{uploading ? "正在上传…" : "上传图片"}</button></form> : null}
        <form className={styles.search} onSubmit={event => { event.preventDefault(); setSubmitted(query.trim()); setPage(1); }}><label htmlFor="media-library-query">查找已有图片</label><div><input id="media-library-query" value={query} onChange={event => setQuery(event.target.value)} maxLength={200} placeholder="图片说明、来源或署名" /><button type="submit" aria-label="搜索图片"><Search size={16} /></button></div></form>
        {collection.error ? <p role="alert">{collection.error}<button onClick={() => { setPage(1); collection.retry(); }}>从第一页重新读取</button></p> : !collection.data ? <LoadingState role="status">正在读取媒体…</LoadingState> : <>
          <div className={styles.gallery}>{collection.data.results.map(row => <button type="button" key={row.id} aria-pressed={mediaId === row.id} disabled={locked} onClick={() => { if (row.id !== mediaId) { if (dirty) setSwitchTo(row.id); else select(row.id); } }}>
            <PrivateMediaImage owner={owner} path={row.renditions?.[0]?.url || `/catalog/admin/media/${row.id}/source/`} alt={row.alt_text || "图片"} /><span>{row.alt_text || row.source_label || "未填写说明"}</span><small>{row.width} × {row.height}</small></button>)}</div>
          {!collection.data.count ? <p className={frame.note}>{submitted ? "没有匹配的图片。可缩短关键词，或清空搜索查看全部素材。" : "图片库尚无素材。上传后再填写来源，已有馆藏图片仍可从对应对象进入。"}</p> : null}
          <nav className={styles.pagination} aria-label="媒体分页"><button disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>{collection.data.page} / {collection.data.pages}</span><button disabled={page >= collection.data.pages} onClick={() => setPage(value => value + 1)}>下一页</button></nav>
        </>}
      </section>
      {mediaId ? <EditorLoader key={mediaId} owner={owner} mediaId={mediaId} canEdit={canEdit && !uploading} onDirtyChange={setDirty} onBlockChange={setBlocked} /> : <section className={styles.empty}><ImageIcon size={40} strokeWidth={1} /><h2>选择一张图片</h2><p>查看原图、出处和使用位置。</p></section>}
    </div>
    <ConfirmDialog open={Boolean(switchTo)} title="切换图片前尚有未保存资料" description="已保存的来源和原件会保留，本次尚未保存的填写将放弃。" confirmLabel="放弃填写并切换" onCancel={() => setSwitchTo("")} onConfirm={() => select(switchTo)} />
  </div>;
}

type EditorProps = { owner: string; mediaId: string; canEdit: boolean; onDirtyChange: (value: boolean) => void; onBlockChange: (value: boolean) => void };
function EditorLoader(props: EditorProps) {
  const resource = useOwnedRead<State>(props.owner, `/catalog/admin/media/${props.mediaId}/workspace/`);
  return resource.data ? <LibraryEditor {...props} initial={resource.data} /> : <section className={styles.empty}>{resource.error ? <p role="alert">{resource.error}<button onClick={resource.retry}>重新读取当前图片</button></p> : <LoadingState role="status">正在核对图片与历史…</LoadingState>}</section>;
}

function LibraryEditor({ owner, mediaId, canEdit, initial, onDirtyChange, onBlockChange }: EditorProps & { initial: State }) {
  const [data, setData] = useState(initial), [base, setBase] = useState(initial.media.updated_at), [draft, setDraft] = useState(metadataOf(initial.media));
  const [saved, setSaved] = useState(draft), [message, setMessage] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false), [stopping, setStopping] = useState(false), [imageAttempt, setImageAttempt] = useState(0);
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => { const controller = new AbortController(); lifetime.current = controller; return () => controller.abort(); }, []);
  const path = `/catalog/admin/media/${mediaId}/workspace/`;
  const command = useCatalogCommand<Command, Receipt>(owner, path, `stl-media-library:${owner}:${mediaId}`, result => result.media_id === mediaId);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved), blocked = busy || command.busy || !command.ready || Boolean(command.recovery), locked = blocked || !canEdit;
  const conflict = base !== data.media.updated_at;
  useUnsavedForm(dirty || Boolean(command.recovery), false);
  useEffect(() => { onDirtyChange(dirty); onBlockChange(blocked); }, [dirty, blocked, onDirtyChange, onBlockChange]);
  function update<K extends keyof Metadata>(key: K, value: Metadata[K]) { setDraft(current => ({ ...current, [key]: value })); setMessage(""); }
  async function refresh(historyPage = data.history.page) {
    const next = await ownedRequest<State>(owner, `${path}?history_page=${historyPage}`, { signal: lifetime.current?.signal });
    if (!lifetime.current?.signal.aborted) setData(next);
    return next;
  }
  async function reload(page = data.history.page) {
    if (busy) return; setBusy(true); setError("");
    try { await refresh(page); } catch (reason) { if (!lifetime.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "资料读取失败，填写仍保留。"); }
    finally { if (!lifetime.current?.signal.aborted) setBusy(false); }
  }
  async function accept(result: Receipt | null) {
    if (!result || lifetime.current?.signal.aborted) return;
    setStopping(false);
    if (result.state === "cancelled") { setMessage("原待定请求已停止，本次填写仍保留。"); return; }
    setBusy(true);
    try {
      const next = await refresh(1); if (lifetime.current?.signal.aborted) return;
      if (next.media.updated_at === result.updated_at) {
        const metadata = metadataOf(next.media); setDraft(metadata); setSaved(metadata); setBase(next.media.updated_at);
        setMessage("图片出处已保存。已使用的图片仍保留原裁切和出处，请到使用页面核对并更新。");
      } else setMessage("原请求已完成，但这张图片后来又有修改。你的填写保留，请核对最新资料后继续。");
    } catch (reason) { if (!lifetime.current?.signal.aborted) setError(`已查询保存结果，但最新资料未读回。${reason instanceof Error ? reason.message : "请重新读取。"}`); }
    finally { if (!lifetime.current?.signal.aborted) setBusy(false); }
  }
  function save(event?: FormEvent) { event?.preventDefault(); if (locked || !dirty || conflict) return; setError(""); void command.send({ expected_updated_at: base, metadata: draft }).then(accept); }
  async function stop() {
    if (busy || command.busy || !command.recovery) return;
    setError(""); await accept(await command.lookup(true));
  }
  async function loadHistory(values: Record<string, unknown>) {
    if (dirty && !(await confirmAction("载入历史资料会替换本次填写中的对应字段，继续吗？"))) return;
    const fields: Partial<Metadata> = {};
    for (const key of textFields) if (typeof values[key] === "string") fields[key] = values[key];
    for (const key of ["focal_x", "focal_y"] as const) if (typeof values[key] === "number" && values[key] >= 0 && values[key] <= 1) fields[key] = values[key];
    setDraft(current => ({ ...current, ...fields }));
    setMessage("历史资料已填入对应字段，尚未保存。没有记录的字段保持本次填写。");
  }
  return <>
    <section className={styles.previewArea}><h2>当前原图</h2><div className={`${frame.currentImage} ${styles.original}`}><PrivateMediaImage key={imageAttempt} owner={owner} path={`/catalog/admin/media/${mediaId}/source/`} alt={data.media.alt_text || "原始图片"} /></div><button type="button" onClick={() => setImageAttempt(value => value + 1)}>重新读取图片</button>
      <p className={frame.note}>{data.media.width} × {data.media.height} · {(data.media.byte_size / 1024 / 1024).toFixed(2)} MB<br />上传于 {dateLabel(data.media.created_at)}<br />资料更新于 {dateLabel(data.media.updated_at)}</p>
      <section className={styles.references}><h3>图片使用位置</h3><p>{data.references.scope}</p>{data.references.results.map(row => <article key={row.id}><strong>{row.label}</strong><small>{referenceLabels[row.kind] || "已有引用"} · {row.detail}</small>{row.editor_url ? <Link href={row.editor_url}>进入使用对象调整裁切与用途 →</Link> : null}</article>)}{!data.references.count ? <p>当前可见范围内没有已登记的使用关系。请从相应对象的选图入口选择此素材；素材上传本身不会发布图片。</p> : null}</section>
    </section>
    <section className={frame.information}><h2>图片信息</h2><p className={frame.note}>这里只修改素材来源。已保存的封面、肖像和页面图片修订各自保留出处与裁切。</p>
      {message || error || command.error ? <div className={frame.feedback} role={error || command.error ? "alert" : "status"}>{error || command.error || message}<button disabled={busy || command.busy} onClick={() => void reload()}>读取最新资料</button></div> : null}
      {command.recovery ? <aside className={frame.feedback}><p>上次保存结果尚未确认，先核对原请求。</p><button disabled={busy || command.busy} onClick={() => void command.lookup().then(accept)}>查询原结果</button>{command.canRetry ? <button disabled={busy || command.busy} onClick={() => void command.send().then(accept)}>重试原请求</button> : null}<button disabled={busy || command.busy} onClick={() => setStopping(true)}>停止未执行请求</button></aside> : null}
      {conflict ? <aside className={frame.feedback}><strong>来源资料已有更新，当前填写保留</strong><dl className={styles.latest}>{textFields.filter(key => draft[key] !== data.media[key]).map(key => <div key={key}><dt>{fieldLabels[key]} · 最新保存</dt><dd>{data.media[key] || "未填写"}</dd></div>)}</dl><button disabled={locked} onClick={() => { setBase(data.media.updated_at); setSaved(metadataOf(data.media)); setMessage("已按最新版本继续，请核对本次填写后保存。"); }}>已核对，保留填写继续</button></aside> : null}
      <form className={styles.form} onSubmit={save}><fieldset disabled={locked}>
        {textFields.map(key => <label key={key}>{fieldLabels[key]}{key === "alt_text" || key === "rights" ? <textarea value={draft[key]} rows={key === "rights" ? 3 : 4} maxLength={key === "rights" ? 4000 : 1000} onChange={event => update(key, event.target.value)} /> : <input type={key === "source_url" ? "url" : "text"} value={draft[key]} maxLength={key === "source_label" ? 300 : key === "license" ? 200 : key === "credit" ? 500 : 1000} onChange={event => update(key, event.target.value)} />}</label>)}
        <details data-disclosure="collection"><summary>默认焦点</summary><p>供以后新建裁切时使用，既有图片修订不变。</p>{(["focal_x", "focal_y"] as const).map(key => <label key={key}>{key === "focal_x" ? "水平焦点" : "垂直焦点"}<input type="range" min={0} max={1} step={0.01} value={draft[key]} onChange={event => update(key, Number(event.target.value))} /></label>)}</details>
        <button className={frame.primary} type="submit" disabled={locked || !dirty || conflict}>{command.busy ? "正在保存…" : "保存来源资料"}</button>
      </fieldset></form>
    </section>
    <section className={styles.history}><header><h2>来源资料历史</h2><span>共 {data.history.count} 次</span></header><p className={frame.note}>载入记录只填写右侧字段，保存后才生效；不会切换任何页面图片或覆盖原件。</p>{data.history.results.map(row => <article key={row.id}><strong>{dateLabel(row.created_at)}</strong><p>{textFields.filter(key => key in row.after).map(key => fieldLabels[key]).join("、") || "焦点资料"}</p><button disabled={locked} onClick={() => loadHistory(row.before)}>载入修改前</button><button disabled={locked} onClick={() => loadHistory(row.after)}>载入修改后</button></article>)}{!data.history.count ? <p>尚无来源资料修改记录，原图仍保留。</p> : null}<nav className={styles.pagination} aria-label="来源资料历史分页"><button disabled={busy || data.history.page <= 1} onClick={() => void reload(data.history.page - 1)}>上一页</button><span>{data.history.page} / {data.history.pages}</span><button disabled={busy || data.history.page >= data.history.pages} onClick={() => void reload(data.history.page + 1)}>下一页</button></nav></section>
    <div className={frame.mobileSave}><button className={frame.primary} disabled={locked || !dirty || conflict} onClick={save}>保存来源资料</button></div>
    <ConfirmDialog open={stopping} title="停止未执行的来源保存？" description="已经保存的资料不会撤回。若原请求已完成，将返回原结果；若尚未执行，停止后晚到的请求不能再修改资料。" confirmLabel="停止原请求" pending={busy || command.busy} onCancel={() => setStopping(false)} onConfirm={stop} />
  </>;
}
