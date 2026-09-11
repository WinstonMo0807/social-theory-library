"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/admin-ui";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { components } from "@/lib/api/generated/schema";
import { scholarPortraitEndpoint, selectScholarPortrait, type ScholarPortraitState } from "@/lib/api/scholar-media";
import styles from "./media-library.module.css";

type Media = components["schemas"]["MediaAsset"];
type Rendition = components["schemas"]["MediaRendition"];

function MediaEditor({ media, onSaved, editionId, slot, scholar }: { media: Media; onSaved: () => void; editionId: string | null; slot: "cover" | "recommendation"; scholar: ScholarPortraitState | null }) {
  const label = scholar ? "肖像" : slot === "cover" ? "封面" : "推荐图例";
  const [workbenchUrl, setWorkbenchUrl] = useState("");
  const [focalX, setFocalX] = useState(media.focal_x ?? 0.5);
  const [focalY, setFocalY] = useState(media.focal_y ?? 0.5);
  const [preview, setPreview] = useState<Rendition | null>(media.renditions?.[0] ?? null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [editVersion, setEditVersion] = useState(media.updated_at);
  const [portraitFingerprint, setPortraitFingerprint] = useState(scholar?.fingerprint || "");
  async function chooseImage() {
    if ((!editionId && !scholar) || busy) return;
    setBusy(true);
    try {
      if (scholar) {
        const result = await selectScholarPortrait(scholar.scholar_id, { media_id: media.id, expected_person_id: scholar.person_id, fingerprint: portraitFingerprint });
        setPortraitFingerprint(result.fingerprint);
        setWorkbenchUrl(result.editor_url);
        setMessage("肖像已保存到学者草稿。请返回学者页面核对后发布，原图片保留。");
        return;
      }
      if (!editionId) return;
      const result = await apiRequest<components["schemas"]["CoverMediaSelectionResult"]>(`/catalog/admin/editions/${encodeURIComponent(editionId)}/media/${slot}/`, {
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
      setMessage("媒体资料已保存。此操作不会直接更改公开书目。");
      onSaved();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败，已填写内容仍保留。");
    } finally { setBusy(false); }
  }
  return <section className="admin-panel"><h2>媒体资料与预览</h2>
    <form className={styles.form} onSubmit={save} aria-busy={busy}>
      <label>图片说明<input name="alt_text" defaultValue={media.alt_text} maxLength={1000} autoComplete="off" /></label>
      <label>来源名称<input name="source_label" defaultValue={media.source_label} maxLength={300} autoComplete="off" /></label>
      <label>来源网址<input name="source_url" defaultValue={media.source_url} type="url" autoComplete="off" /></label>
      <label>使用权说明<textarea name="rights" defaultValue={media.rights} rows={2} /></label>
      <div className={styles.controls}><label>许可<input name="license" defaultValue={media.license} maxLength={200} /></label><label>署名<input name="credit" defaultValue={media.credit} maxLength={500} /></label></div>
      <div className={styles.controls}><label>水平焦点<input type="range" min={0} max={1} step={0.01} value={focalX} onChange={(event) => setFocalX(Number(event.target.value))} /></label><label>垂直焦点<input type="range" min={0} max={1} step={0.01} value={focalY} onChange={(event) => setFocalY(Number(event.target.value))} /></label></div>
      <div className={styles.controls}><label>预览用途<select name="kind" defaultValue={scholar ? "portrait" : "cover"}><option value="cover">书封，保持比例</option><option value="portrait">肖像</option><option value="hero">横幅</option><option value="card">卡片</option></select></label><label>预览宽度<select name="width" defaultValue="640"><option value="320">320 px</option><option value="640">640 px</option><option value="1280">1280 px</option></select></label></div>
      <button className="button" type="submit" disabled={busy}>{busy ? "正在保存…" : "保存资料并生成预览"}</button>
    </form>
    {message ? <p className={styles.message} role="status">{message}</p> : null}
    {editionId || scholar ? <button className="button" type="button" disabled={busy} onClick={() => void chooseImage()}>{scholar ? `用作${scholar.name}的肖像` : `用作当前作品${label}`}</button> : null}
    {workbenchUrl ? <Link className="button secondary" prefetch={false} href={workbenchUrl}>{scholar ? "返回学者页面" : "返回编目工作台"}</Link> : null}
    {preview ? <picture><source type="image/webp" srcSet={normalizePublicResourceUrl(preview.url)} /><img className={styles.preview} src={normalizePublicResourceUrl(preview.url)} alt={media.alt_text || "媒体预览"} width={preview.width} height={preview.height} /></picture> : <p>暂无衍生图。</p>}
  </section>;
}

export function MediaLibrary() {
  const params = useSearchParams();
  const editionId = params.get("edition");
  const scholarId = params.get("scholar");
  const scholarState = useApiResource<ScholarPortraitState>(scholarId ? scholarPortraitEndpoint(scholarId) : "", getServerSessionCredential());
  const requestedSlot = params.get("slot") ?? "cover";
  const slot = requestedSlot === "recommendation" ? "recommendation" : "cover";
  const validSlot = (requestedSlot === "cover" || requestedSlot === "recommendation") && !(scholarId && editionId);
  const { data, loading, error, retry } = useApiResource<Media[]>("/catalog/admin/media/", getServerSessionCredential());
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
  return <div className="admin-page"><PageHeader title="媒体库" description="保存图片原件、来源与使用说明，生成适合页面的衍生图。" />
    <div className={styles.layout}><section className="admin-panel"><h2>上传或选择图片</h2>
      <form className={styles.form} onSubmit={upload} aria-busy={busy}><label>图片文件<input name="image" type="file" accept="image/jpeg,image/png,image/webp" required /></label><label>图片说明<input name="alt_text" maxLength={1000} /></label><button type="submit" className="button" disabled={busy}>{busy ? "上传中…" : "上传图片"}</button></form>
      {message ? <p role="status">{message}</p> : null}
      {error ? <p role="alert">{error}<button type="button" onClick={retry}>重新读取</button></p> : null}
      {loading ? <p role="status">正在读取媒体…</p> : null}
      <div className={styles.gallery}>{data?.map((row) => <button type="button" key={row.id} aria-pressed={selectedId === row.id} disabled={busy} onClick={() => setSelectedMedia(row)}>
        {row.renditions?.[0] ? <picture><source type="image/webp" srcSet={normalizePublicResourceUrl(row.renditions[0].url)} /><img className={styles.thumbnail} src={normalizePublicResourceUrl(row.renditions[0].url)} alt={row.alt_text || "图片"} width={row.renditions[0].width} height={row.renditions[0].height} loading="lazy" /></picture> : null}
        <span>{row.alt_text || row.source_label || "未填写说明"}</span><small>{row.width} × {row.height}</small>
      </button>)}</div>
    </section>{!validSlot ? <p role="alert">图片用途或对象不明确，请返回编辑页面重新选择。</p> : scholarId && scholarState.error ? <p role="alert">{scholarState.error}<button type="button" onClick={scholarState.retry}>重新读取学者</button></p> : scholarId && !scholarState.data ? <p role="status">正在读取学者身份…</p> : selected ? <MediaEditor key={`${selected.id}:${editionId}:${slot}:${scholarId}:${scholarState.data?.person_id}`} media={selected} onSaved={retry} editionId={editionId} slot={slot} scholar={scholarId ? scholarState.data : null} /> : <section className="admin-panel"><h2>选择媒体</h2><p>可在此查看来源、使用说明和裁切预览。未关联并发布的图片不会出现在公开页面中。</p></section>}</div>
  </div>;
}
