"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Upload, Search } from "lucide-react";
import { AdminPublicPreviewFrame } from "../admin-public-preview-frame";
import { PageHeader } from "@/components/admin-ui";
import { Dialog } from "@/components/ui/dialog";
import { safeAdminHref } from "@/lib/admin-route-context";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { components } from "@/lib/api/generated/schema";
import { scholarPortraitEndpoint, selectScholarPortrait, type ScholarPortraitState } from "@/lib/api/scholar-media";
import { knowledgeImageEndpoint, selectKnowledgeImage, type KnowledgeImageState, type KnowledgeImageType } from "@/lib/api/knowledge-media";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import styles from "./media-library.module.css";

type Media = components["schemas"]["MediaAsset"];
type Rendition = components["schemas"]["MediaRendition"];
type MediaCollection = { count: number; page: number; pages: number; page_size: number; results: Media[] };
type MediaReferences = { count: number; scope: string; results: Array<{ id: string; kind: string; label: string; detail: string; editor_url: string; public_url: string }> };
const referenceLabels: Record<string, string> = { current_public: "当前公开使用", draft: "待发布草稿", history: "历史引用，保留用于回退", canonical: "当前对象选图" };

type Destination = { kind: "work"; editionId: string; slot: "cover" | "recommendation" } | { kind: "scholar"; data: ScholarPortraitState } | { kind: "knowledge"; data: KnowledgeImageState };

function MediaEditor({ media, onSaved, destination, onDirty, onBusy }: { media: Media; onSaved: () => void; destination: Destination | null; onDirty: (value:boolean)=>void; onBusy: (value:boolean)=>void }) {
  const referenceResource = useApiResource<{ references: MediaReferences }>(`/catalog/admin/media/${media.id}/`, getServerSessionCredential());
  const label = destination?.kind === "scholar" ? "肖像" : destination?.kind === "knowledge" ? "页面图片" : destination?.slot === "recommendation" ? "推荐图例" : "封面";
  const returnLabel = destination?.kind === "scholar" ? "返回学者页面" : destination?.kind === "knowledge" ? "返回编辑页面" : "返回编目工作台";
  const choiceLabel = destination?.kind === "scholar" ? `用作${destination.data.name}的肖像` : destination?.kind === "knowledge" ? `用作${destination.data.name}的页面图片` : `用作当前作品${label}`;
  const [workbenchUrl, setWorkbenchUrl] = useState("");
  const [focalX, setFocalX] = useState(media.focal_x ?? 0.5);
  const [focalY, setFocalY] = useState(media.focal_y ?? 0.5);
  const [preview, setPreview] = useState<Rendition | null>(media.renditions?.[0] ?? null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [dirty,setDirty]=useState(false);
  useUnsavedForm(dirty,false);
  useEffect(()=>onDirty(dirty),[dirty,onDirty]);
  useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
  const [editVersion, setEditVersion] = useState(media.updated_at);
  const [fingerprint, setFingerprint] = useState(destination && destination.kind !== "work" ? destination.data.fingerprint : "");
  const references = referenceResource.data?.references.results || [];
  const currentReferences = references.filter(row => row.kind !== "history");
  const historyReferences = references.filter(row => row.kind === "history");
  function completeSelection(href: string, detail: string) {
    const target = safeAdminHref(href, "");
    setWorkbenchUrl(target);
    setMessage(detail);
    if (target) window.location.assign(target);
  }
  const referenceCard = (row: MediaReferences["results"][number]) => <article key={row.id}><div><strong>{row.label}</strong><p>{referenceLabels[row.kind] || "使用记录"} · {row.detail}</p></div><div>{row.editor_url ? <Link href={row.editor_url}>返回编辑页面</Link> : null}{row.public_url ? <Link href={row.public_url} target="_blank">在前台查看 ↗</Link> : null}</div></article>;
  async function chooseImage() {
    if (!destination || busy || dirty) return;
    setBusy(true);
    try {
      if (destination.kind === "scholar") {
        const scholar = destination.data;
        const result = await selectScholarPortrait(scholar.scholar_id, { media_id: media.id, expected_person_id: scholar.person_id, fingerprint });
        setFingerprint(result.fingerprint);
        completeSelection(result.editor_url, "肖像已保存到学者草稿。请返回学者页面核对后发布，原图片保留。");
        return;
      }
      if (destination.kind === "knowledge") {
        const object = destination.data;
        const result = await selectKnowledgeImage(object.object_type, object.object_id, media.id, fingerprint);
        setFingerprint(result.fingerprint);
        completeSelection(result.editor_url, "图片已保存到编辑草稿。请返回对象页面确认发布，原图保留。");
        return;
      }
      const result = await apiRequest<components["schemas"]["CoverMediaSelectionResult"]>(`/catalog/admin/editions/${encodeURIComponent(destination.editionId)}/media/${destination.slot}/`, {
        method: "POST", body: JSON.stringify({ media_id: media.id }),
      }, getServerSessionCredential());
      completeSelection(result.workbench_url, `${label}已保存到书目草稿。请返回工作台核对后发布。`);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "图片关联失败。"); }
    finally { setBusy(false); }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const text = (key: string) => String(form.get(key) ?? "");
    setBusy(true);
    setMessage("");
    let metadataSaved=false;
    try {
      const saved = await apiRequest<Media>(`/catalog/admin/media/${media.id}/`, { method: "PATCH", body: JSON.stringify({
        alt_text: text("alt_text"), source_label: text("source_label"), source_url: text("source_url"),
        rights: text("rights"), license: text("license"), credit: text("credit"), focal_x: focalX, focal_y: focalY,
        expected_updated_at: editVersion,
      }) }, getServerSessionCredential());
      setEditVersion(saved.updated_at);
      setDirty(false);
      metadataSaved=true;
      onSaved();
      const next = await apiRequest<Rendition>(`/catalog/admin/media/${media.id}/renditions/`, {
        method: "POST", body: JSON.stringify({ kind: text("kind"), width: Number(form.get("width")) }),
      }, getServerSessionCredential());
      setPreview(next);
      setMessage("图片信息已保存。请回到使用这张图片的页面发布修改。");
      onSaved();
    } catch (reason) {
      setMessage(`${metadataSaved ? "图片资料已经保存，但显示预览生成失败。" : "保存尚未完成，已填写内容仍保留。"}${reason instanceof Error ? reason.message : "请重试。"}`);
    } finally { setBusy(false); }
  }
  return <section className={`admin-panel ${styles.inspector}`}><h2>已选择的图片</h2><div className={styles.selectedSummary}>{preview ? <img src={normalizePublicResourceUrl(preview.url)} alt={media.alt_text || "图片"}/> : <span/>}<div><h3>{media.alt_text || media.source_label || "未填写说明"}</h3><dl><dt>图片类型</dt><dd>—</dd><dt>尺寸</dt><dd>{media.width} × {media.height}</dd><dt>文件格式</dt><dd>{media.media_type.replace("image/", "").toUpperCase()}</dd><dt>上传时间</dt><dd>{new Date(media.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</dd><dt>上传者</dt><dd>—</dd></dl></div></div>
    <section className={styles.references} aria-label="媒体当前使用位置"><h3>使用位置</h3><p>当前用于以下内容</p>{referenceResource.error ? <p role="alert">{referenceResource.error}<button type="button" onClick={referenceResource.retry}>重新读取引用</button></p> : referenceResource.loading ? <p role="status">正在读取真实引用…</p> : currentReferences.length ? currentReferences.map(referenceCard) : <p>—</p>}</section>
    <section className={styles.usagePreview}><h3>在前台的显示效果</h3><div><AdminPublicPreviewFrame title="详情页中" src={references.find(row=>row.kind==="current_public" && row.public_url)?.public_url || null} emptyMessage="—"/><section className={styles.cardPreview}><h4>卡片中</h4><div aria-label="独立卡片预览尚无契约">—</div></section></div></section>
    <section className={styles.history}><h3>历史版本</h3><div aria-label="历史图片版本尚无契约">—</div>{historyReferences.length ? <details><summary>历史引用（{historyReferences.length}）</summary><p>{referenceResource.data?.references.scope}</p>{historyReferences.map(referenceCard)}</details> : null}</section>
    <details className={styles.metadata}><summary>图片信息与裁切设置</summary><form className={styles.form} onChange={()=>setDirty(true)} onSubmit={save} aria-busy={busy}>
      <label>图片说明<input name="alt_text" defaultValue={media.alt_text} maxLength={1000} autoComplete="off" /></label>
      <label>来源名称<input name="source_label" defaultValue={media.source_label} maxLength={300} autoComplete="off" /></label>
      <label>来源网址<input name="source_url" defaultValue={media.source_url} type="url" autoComplete="off" /></label>
      <label>使用权说明<textarea name="rights" defaultValue={media.rights} rows={2} /></label>
      <div className={styles.controls}><label>许可<input name="license" defaultValue={media.license} maxLength={200} /></label><label>署名<input name="credit" defaultValue={media.credit} maxLength={500} /></label></div>
      <div className={styles.controls}><label>水平焦点<input type="range" min={0} max={1} step={0.01} value={focalX} onChange={(event) => setFocalX(Number(event.target.value))} /></label><label>垂直焦点<input type="range" min={0} max={1} step={0.01} value={focalY} onChange={(event) => setFocalY(Number(event.target.value))} /></label></div>
      <div className={styles.controls}><label>预览用途<select name="kind" defaultValue={destination?.kind === "scholar" ? "portrait" : destination?.kind === "knowledge" ? "hero" : "cover"}><option value="cover">书封，保持比例</option><option value="portrait">肖像</option><option value="hero">横幅</option><option value="card">卡片</option></select></label><label>预览宽度<select name="width" defaultValue="640"><option value="320">320 px</option><option value="640">640 px</option><option value="1280">1280 px</option></select></label></div>
      <button className="button" type="submit" disabled={busy}>{busy ? "正在保存…" : "保存资料并生成预览"}</button>
    </form></details>
    {message ? <p className={styles.message} role="status">{message}</p> : null}
    {destination ? <form id="media-selection-form" aria-label={choiceLabel} onSubmit={event => { event.preventDefault(); void chooseImage(); }} /> : null}
    {workbenchUrl ? <Link className="button secondary" prefetch={false} href={workbenchUrl}>{returnLabel}</Link> : null}
    <details><summary>当前图片衍生版本</summary>{preview ? <picture><source type="image/webp" srcSet={normalizePublicResourceUrl(preview.url)} /><img className={styles.preview} src={normalizePublicResourceUrl(preview.url)} alt={media.alt_text || "媒体预览"} width={preview.width} height={preview.height} /></picture> : <p>暂无衍生图。</p>}</details>
  </section>;
}

export function MediaLibrary() {
  const params = useSearchParams();
  const editionId = params.get("edition");
  const scholarId = params.get("scholar");
  const objectType = params.get("object_type"), objectId = params.get("object_id");
  const knownObjectType = objectType === "knowledge_node" || objectType === "reading_path" || objectType === "discipline" || objectType === "subdiscipline";
  const requestedSlot = params.get("slot") ?? "cover";
  const slot = requestedSlot === "recommendation" ? "recommendation" : "cover";
  const validSlot = (requestedSlot === "cover" || requestedSlot === "recommendation") && [scholarId, editionId, objectId].filter(Boolean).length <= 1 && (objectType || objectId ? knownObjectType && Boolean(objectId) : true);
  const scholarState = useApiResource<ScholarPortraitState>(validSlot && scholarId ? scholarPortraitEndpoint(scholarId) : "", getServerSessionCredential());
  const objectState = useApiResource<KnowledgeImageState>(validSlot && knownObjectType && objectId ? knowledgeImageEndpoint(objectType as KnowledgeImageType, objectId) : "", getServerSessionCredential());
  const destination: Destination | null = scholarId && scholarState.data ? { kind: "scholar", data: scholarState.data } : objectId && objectState.data ? { kind: "knowledge", data: objectState.data } : editionId ? { kind: "work", editionId, slot } : null;
  const destinationError = scholarId ? scholarState.error : objectId ? objectState.error : "";
  const loadingDestination = Boolean(scholarId || objectId) && !destination;
  const [page, setPage] = useState(1);
  const [search,setSearch]=useState("");
  const { data: collection, loading, error, retry } = useApiResource<MediaCollection>(`/catalog/admin/media/collection/?page=${page}&q=${encodeURIComponent(search)}`, getServerSessionCredential(), String(page));
  const data = collection?.results;
  const [editorDirty,setEditorDirty]=useState(false);
  const [editorBusy,setEditorBusy]=useState(false);
  const [selectedMedia, setSelectedMedia] = useState<Media | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectionEpoch, setSelectionEpoch] = useState(0);
  const selectedId = selectedMedia?.id;
  // A refresh must not unmount the active form or discard the new rendition.
  const selected = data?.find((row) => row.id === selectedId) ?? selectedMedia;
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || editorBusy || (editorDirty && !window.confirm("当前图片资料尚未保存，放弃并上传新图吗？"))) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    try {
      const row = await apiRequest<Media>("/catalog/admin/media/", { method: "POST", body: form }, getServerSessionCredential());
      setSelectedMedia(row);
      setEditorDirty(false);
      setSelectionEpoch(value => value + 1);
      setUploadOpen(false);
      retry();
      setMessage("图片已进入媒体库，原件会保留。请选择用途后再关联馆藏。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "上传失败，请重试。");
    } finally { setBusy(false); }
  }
  const returnHref = safeAdminHref(params.get("return_to") || (destination && destination.kind !== "work" ? destination.data.editor_url : ""), "/admin/library");
  return <div className={`admin-page ${styles.page}`}><PageHeader title="图片库" description="管理书籍封面、学者肖像与页面配图，查看使用位置" actions={<button className="button" type="button" disabled={busy || editorBusy} onClick={() => setUploadOpen(true)}><Upload size={18}/>上传图片</button>}/>
    <Dialog open={uploadOpen} onRequestClose={() => { if (!busy) setUploadOpen(false); }} className={styles.uploadDialog} aria-labelledby="media-upload-title"><header><h2 id="media-upload-title">上传图片</h2><button type="button" disabled={busy} onClick={() => setUploadOpen(false)}>关闭</button></header><form className={styles.form} onSubmit={upload} aria-busy={busy}><label>图片文件<input name="image" type="file" accept="image/jpeg,image/png,image/webp" required /></label><label>图片说明<input name="alt_text" maxLength={1000} /></label><button type="submit" className="button" disabled={busy}>{busy ? "上传中…" : "上传图片"}</button></form>{message ? <p role="status">{message}</p> : null}</Dialog>
    <div className={styles.layout}><section className={`admin-panel ${styles.collection}`}><div className={styles.collectionTools}><nav aria-label="图片分类"><button type="button" aria-current="true">全部图片</button>{["封面", "学者肖像", "页面配图"].map(label => <button type="button" disabled title="用途分类尚无独立查询字段" key={label}>{label}</button>)}</nav><form role="search" onSubmit={event=>{event.preventDefault();setSearch(String(new FormData(event.currentTarget).get("q") || ""));setPage(1);}}><button type="submit" aria-label="搜索图片"><Search size={17}/></button><input name="q" aria-label="搜索图片名称" placeholder="搜索图片名称"/></form></div>
      {message ? <p role="status">{message}</p> : null}
      {error ? <p role="alert">{error}<button type="button" onClick={retry}>重新读取</button></p> : null}
      {loading ? <p role="status">正在读取媒体…</p> : null}
      {collection ? <p className={styles.count}>共 {collection.count} 张图片{search ? ` · 搜索：${search}` : ""}</p> : null}
      <div className={styles.gallery}>{data?.map((row) => <button type="button" key={row.id} aria-pressed={selectedId === row.id} disabled={busy || editorBusy} onClick={() => {if(row.id===selectedId)return;if(editorDirty && !window.confirm("当前图片资料尚未保存，放弃并切换图片吗？"))return;setEditorDirty(false);setSelectedMedia(row);}}>
        {row.renditions?.[0] ? <picture><source type="image/webp" srcSet={normalizePublicResourceUrl(row.renditions[0].url)} /><img className={styles.thumbnail} src={normalizePublicResourceUrl(row.renditions[0].url)} alt={row.alt_text || "图片"} width={row.renditions[0].width} height={row.renditions[0].height} loading="lazy" /></picture> : <div className={styles.thumbnail} aria-hidden="true"/>}
        <span>{row.alt_text || row.source_label || "未填写说明"}</span><small>{row.width} × {row.height} · {row.media_type.replace("image/", "").toUpperCase()}</small>
      </button>)}</div>
      {collection && collection.pages > 1 ? <nav className={styles.pagination} aria-label="媒体分页"><button type="button" disabled={loading || page <= 1} onClick={() => setPage(page - 1)}>上一页</button><span>第 {collection.page}/{collection.pages} 页</span><button type="button" disabled={loading || page >= collection.pages} onClick={() => setPage(page + 1)}>下一页</button></nav> : null}
    </section>{!validSlot ? <p role="alert">图片用途或对象不明确，请返回编辑页面重新选择。</p> : destinationError ? <p role="alert">{destinationError}<button type="button" onClick={scholarId ? scholarState.retry : objectState.retry}>重新读取编辑对象</button></p> : loadingDestination ? <p role="status">正在读取编辑对象…</p> : selected ? <MediaEditor key={`${selected.id}:${editionId}:${slot}:${scholarId}:${scholarState.data?.person_id}:${objectType}:${objectId}:${selectionEpoch}`} media={selected} onSaved={retry} onDirty={setEditorDirty} onBusy={setEditorBusy} destination={destination} /> : <section className={`admin-panel ${styles.inspector}`}><h2>已选择的图片</h2><p>请从左侧选择图片，查看资料和实际使用位置。</p></section>}</div>
    <footer className={styles.footer}><Link className="button secondary" href={returnHref} onClick={event => { if (busy || editorBusy || (editorDirty && !window.confirm("当前图片资料尚未保存，放弃并返回编辑页面吗？"))) event.preventDefault(); }}>取消，返回编辑页面</Link><button type="submit" form="media-selection-form" className="button" disabled={!validSlot || !selected || !destination || loadingDestination || busy || editorBusy || editorDirty} title={editorDirty ? "请先保存图片资料" : !destination ? "请从编辑页面进入图片库后选择用途" : undefined}>选择这张图片，返回编辑页面</button></footer>
  </div>;
}
