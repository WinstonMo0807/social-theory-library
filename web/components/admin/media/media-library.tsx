"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/admin-ui";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { components } from "@/lib/api/generated/schema";
import { scholarPortraitEndpoint, selectScholarPortrait, type ScholarPortraitState } from "@/lib/api/scholar-media";
import { knowledgeImageEndpoint, selectKnowledgeImage, type KnowledgeImageState, type KnowledgeImageType } from "@/lib/api/knowledge-media";
import styles from "./media-library.module.css";

type Media = components["schemas"]["MediaAsset"];
type Rendition = components["schemas"]["MediaRendition"];
type MediaCollection = { count: number; page: number; pages: number; page_size: number; results: Media[] };
type MediaReferences = { count: number; scope: string; results: Array<{ id: string; kind: string; label: string; detail: string; editor_url: string; public_url: string }> };
const referenceLabels: Record<string, string> = { current_public: "当前公开使用", draft: "待发布草稿", history: "历史引用，保留用于回退", canonical: "当前对象选图" };

type Destination = { kind: "work"; editionId: string; slot: "cover" | "recommendation" } | { kind: "scholar"; data: ScholarPortraitState } | { kind: "knowledge"; data: KnowledgeImageState };

function MediaEditor({ media, onSaved, destination }: { media: Media; onSaved: () => void; destination: Destination | null }) {
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
  const [editVersion, setEditVersion] = useState(media.updated_at);
  const [fingerprint, setFingerprint] = useState(destination && destination.kind !== "work" ? destination.data.fingerprint : "");
  async function chooseImage() {
    if (!destination || busy) return;
    setBusy(true);
    try {
      if (destination.kind === "scholar") {
        const scholar = destination.data;
        const result = await selectScholarPortrait(scholar.scholar_id, { media_id: media.id, expected_person_id: scholar.person_id, fingerprint });
        setFingerprint(result.fingerprint);
        setWorkbenchUrl(result.editor_url);
        setMessage("肖像已保存到学者草稿。请返回学者页面核对后发布，原图片保留。");
        return;
      }
      if (destination.kind === "knowledge") {
        const object = destination.data;
        const result = await selectKnowledgeImage(object.object_type, object.object_id, media.id, fingerprint);
        setFingerprint(result.fingerprint); setWorkbenchUrl(result.editor_url);
        setMessage("图片已保存到编辑草稿。请返回对象页面确认发布，原图保留。");
        return;
      }
      const result = await apiRequest<components["schemas"]["CoverMediaSelectionResult"]>(`/catalog/admin/editions/${encodeURIComponent(destination.editionId)}/media/${destination.slot}/`, {
        method: "POST", body: JSON.stringify({ media_id: media.id }),
      }, getServerSessionCredential());
      setWorkbenchUrl(result.workbench_url);
      setMessage(`${label}已保存到书目草稿。请返回工作台核对后发布。`);
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
    try {
      const saved = await apiRequest<Media>(`/catalog/admin/media/${media.id}/`, { method: "PATCH", body: JSON.stringify({
        alt_text: text("alt_text"), source_label: text("source_label"), source_url: text("source_url"),
        rights: text("rights"), license: text("license"), credit: text("credit"), focal_x: focalX, focal_y: focalY,
        expected_updated_at: editVersion,
      }) }, getServerSessionCredential());
      setEditVersion(saved.updated_at);
      const next = await apiRequest<Rendition>(`/catalog/admin/media/${media.id}/renditions/`, {
        method: "POST", body: JSON.stringify({ kind: text("kind"), width: Number(form.get("width")) }),
      }, getServerSessionCredential());
      setPreview(next);
      setMessage("图片信息已保存。请回到使用这张图片的页面发布修改。");
      onSaved();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败，已填写内容仍保留。");
    } finally { setBusy(false); }
  }
  return <section className="admin-panel"><h2>图片信息与预览</h2>
    <section aria-label="媒体当前与历史使用位置"><h3>在哪里使用</h3>{referenceResource.error ? <p role="alert">{referenceResource.error}<button type="button" onClick={referenceResource.retry}>重新读取引用</button></p> : referenceResource.loading ? <p>正在读取真实引用…</p> : referenceResource.data?.references ? <><p>{referenceResource.data.references.scope}</p><p>{referenceResource.data.references.count} 条引用。草稿选择、当前公开和历史使用分别列出。</p>{referenceResource.data.references.results.map((row) => <article key={row.id}><strong>{row.label}</strong><p>{referenceLabels[row.kind] || row.kind} · {row.detail}</p>{row.editor_url ? <Link href={row.editor_url}>打开使用对象</Link> : null}{row.public_url ? <> · <Link href={row.public_url} target="_blank">核验公开位置</Link></> : null}</article>)}{!referenceResource.data.references.count ? <p>尚未关联到馆藏或知识对象，可先选择明确用途再回对象页面发布。</p> : null}</> : null}</section>
    <form className={styles.form} onSubmit={save} aria-busy={busy}>
      <label>图片说明<input name="alt_text" defaultValue={media.alt_text} maxLength={1000} autoComplete="off" /></label>
      <label>来源名称<input name="source_label" defaultValue={media.source_label} maxLength={300} autoComplete="off" /></label>
      <label>来源网址<input name="source_url" defaultValue={media.source_url} type="url" autoComplete="off" /></label>
      <label>使用权说明<textarea name="rights" defaultValue={media.rights} rows={2} /></label>
      <div className={styles.controls}><label>许可<input name="license" defaultValue={media.license} maxLength={200} /></label><label>署名<input name="credit" defaultValue={media.credit} maxLength={500} /></label></div>
      <div className={styles.controls}><label>水平焦点<input type="range" min={0} max={1} step={0.01} value={focalX} onChange={(event) => setFocalX(Number(event.target.value))} /></label><label>垂直焦点<input type="range" min={0} max={1} step={0.01} value={focalY} onChange={(event) => setFocalY(Number(event.target.value))} /></label></div>
      <div className={styles.controls}><label>预览用途<select name="kind" defaultValue={destination?.kind === "scholar" ? "portrait" : destination?.kind === "knowledge" ? "hero" : "cover"}><option value="cover">书封，保持比例</option><option value="portrait">肖像</option><option value="hero">横幅</option><option value="card">卡片</option></select></label><label>预览宽度<select name="width" defaultValue="640"><option value="320">320 px</option><option value="640">640 px</option><option value="1280">1280 px</option></select></label></div>
      <button className="button" type="submit" disabled={busy}>{busy ? "正在保存…" : "保存资料并生成预览"}</button>
    </form>
    {message ? <p className={styles.message} role="status">{message}</p> : null}
    {destination ? <button className="button" type="button" disabled={busy} onClick={() => void chooseImage()}>{choiceLabel}</button> : null}
    {workbenchUrl ? <Link className="button secondary" prefetch={false} href={workbenchUrl}>{returnLabel}</Link> : null}
    {preview ? <picture><source type="image/webp" srcSet={normalizePublicResourceUrl(preview.url)} /><img className={styles.preview} src={normalizePublicResourceUrl(preview.url)} alt={media.alt_text || "媒体预览"} width={preview.width} height={preview.height} /></picture> : <p>暂无衍生图。</p>}
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
  const { data: collection, loading, error, retry } = useApiResource<MediaCollection>(`/catalog/admin/media/collection/?page=${page}`, getServerSessionCredential(), String(page));
  const data = collection?.results;
  const [selectedMedia, setSelectedMedia] = useState<Media | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const selectedId = selectedMedia?.id;
  // A refresh must not unmount the active form or discard the new rendition.
  const selected = data?.find((row) => row.id === selectedId) ?? selectedMedia;
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    try {
      const row = await apiRequest<Media>("/catalog/admin/media/", { method: "POST", body: form }, getServerSessionCredential());
      setSelectedMedia(row);
      retry();
      setMessage("图片已进入媒体库，原件会保留。请选择用途后再关联馆藏。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "上传失败，请重试。");
    } finally { setBusy(false); }
  }
  return <div className="admin-page"><PageHeader title="图片库" description="上传图片，填写来源，查看图片正用在哪些页面。" />
    <div className={styles.layout}><section className="admin-panel"><h2>上传或选择图片</h2>
      <form className={styles.form} onSubmit={upload} aria-busy={busy}><label>图片文件<input name="image" type="file" accept="image/jpeg,image/png,image/webp" required /></label><label>图片说明<input name="alt_text" maxLength={1000} /></label><button type="submit" className="button" disabled={busy}>{busy ? "上传中…" : "上传图片"}</button></form>
      {message ? <p role="status">{message}</p> : null}
      {error ? <p role="alert">{error}<button type="button" onClick={retry}>重新读取</button></p> : null}
      {loading ? <p role="status">正在读取媒体…</p> : null}
      {collection ? <nav className={styles.controls} aria-label="媒体分页"><button type="button" disabled={loading || page <= 1} onClick={() => setPage(page - 1)}>上一页</button><span>共 {collection.count} 项 · 第 {collection.page}/{collection.pages} 页</span><button type="button" disabled={loading || page >= collection.pages} onClick={() => setPage(page + 1)}>下一页</button></nav> : null}
      <div className={styles.gallery}>{data?.map((row) => <button type="button" key={row.id} aria-pressed={selectedId === row.id} disabled={busy} onClick={() => setSelectedMedia(row)}>
        {row.renditions?.[0] ? <picture><source type="image/webp" srcSet={normalizePublicResourceUrl(row.renditions[0].url)} /><img className={styles.thumbnail} src={normalizePublicResourceUrl(row.renditions[0].url)} alt={row.alt_text || "图片"} width={row.renditions[0].width} height={row.renditions[0].height} loading="lazy" /></picture> : null}
        <span>{row.alt_text || row.source_label || "未填写说明"}</span><small>{row.width} × {row.height}</small>
      </button>)}</div>
    </section>{!validSlot ? <p role="alert">图片用途或对象不明确，请返回编辑页面重新选择。</p> : destinationError ? <p role="alert">{destinationError}<button type="button" onClick={scholarId ? scholarState.retry : objectState.retry}>重新读取编辑对象</button></p> : loadingDestination ? <p role="status">正在读取编辑对象…</p> : selected ? <MediaEditor key={`${selected.id}:${editionId}:${slot}:${scholarId}:${scholarState.data?.person_id}:${objectType}:${objectId}`} media={selected} onSaved={retry} destination={destination} /> : <section className="admin-panel"><h2>选择媒体</h2><p>可在此查看来源、使用说明和裁切预览。未关联并发布的图片不会出现在公开页面中。</p></section>}</div>
  </div>;
}
