"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useAdminSession } from "@/lib/admin-session";
import type { components } from "@/lib/api/generated/schema";
import { useActionGuard } from "@/lib/use-action-guard";
import { useUnsavedForm } from "@/lib/use-unsaved-form";

type Media = components["schemas"]["MediaAsset"];
type Page = { results: Media[]; pages: number; page: number; count: number };
const fields = [["alt_text", "图片说明", 1000], ["source_label", "出处名称", 300], ["source_url", "出处链接", 1000], ["license", "使用许可", 200], ["rights", "权利说明", 4000], ["credit", "图片署名", 500]] as const;
type Metadata = Record<(typeof fields)[number][0], string>;
const metadataOf = (media: Media): Metadata => Object.fromEntries(fields.map(([key]) => [key, media[key] || ""])) as Metadata;

export function InlineMediaPicker({ onSelect, selectedRenditionId, kind = "hero", onDirtyChange, selectionMessage }: { onSelect: (id: string, url: string) => void; selectedRenditionId?: string | null; kind?: "hero" | "portrait" | "card"; onDirtyChange?: (dirty: boolean) => void; selectionMessage?: string }) {
  const user = useAdminSession(), owner = user ? String(user.id) : "";
  const selectLatest = useRef(onSelect);
  useEffect(() => { selectLatest.current = onSelect; }, [onSelect]);
  const root = useRef<HTMLElement | null>(null), lifetime = useRef<AbortController | null>(null);
  const { startAction, finishAction } = useActionGuard();
  const [data, setData] = useState<Page | null>(null), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [editing, setEditing] = useState<Media | null>(null), [metadata, setMetadata] = useState<Metadata | null>(null);
  const dirty = useUnsavedForm(metadata, editing ? metadataOf(editing) : null);
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    const unsubscribe = subscribeToSessionChanges(() => { controller.abort(); setData(null); setEditing(null); setMetadata(null); setMessage("账户已变化，请重新打开素材。"); });
    return () => { controller.abort(); unsubscribe(); };
  }, [owner]);
  async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
    const signal = AbortSignal.any([lifetime.current!.signal, AbortSignal.timeout(25000)]);
    return withPrivateOwner(owner, () => apiRequest<T>(url, { ...init, signal, headers: { ...init.headers, "X-Editor-Owner": owner } }, getServerSessionCredential()), signal);
  }
  async function act(work: () => Promise<void>) {
    if (!owner || lifetime.current?.signal.aborted || root.current?.closest("fieldset[disabled]") || !startAction("media")) return;
    setBusy(true); setMessage("");
    try { await work(); }
    catch (error) { if (!lifetime.current?.signal.aborted) setMessage(error instanceof Error ? error.message : "图片操作未确认完成，请重新读取素材核对。"); }
    finally { setBusy(false); finishAction("media"); }
  }
  function open(media: Media) {
    if (dirty && !window.confirm("放弃尚未保存的图片资料，重新读取吗？")) return;
    setEditing(media); setMetadata(metadataOf(media));
  }
  async function load(page = 1) {
    await act(async () => { setData(await request<Page>(`/catalog/admin/media/collection/?page=${page}`)); });
  }
  async function current() {
    await act(async () => {
      const result = await request<Page>(`/catalog/admin/media/collection/?rendition_id=${encodeURIComponent(selectedRenditionId || "")}`);
      if (!result.results.length) { setMessage("当前图片版本已不可用，请重新选择。"); return; }
      open(result.results[0]);
    });
  }
  async function choose(media: Media) {
    const rendition = await request<components["schemas"]["MediaRendition"]>(`/catalog/admin/media/${media.id}/renditions/`, { method: "POST", body: JSON.stringify({ kind, width: 1280 }) });
    if (lifetime.current?.signal.aborted) return;
    if (root.current?.closest("fieldset[disabled]")) { setMessage("图片版本已生成。当前页面正在保存或核对，请完成后重新填入。"); return; }
    selectLatest.current(rendition.id, normalizePublicResourceUrl(rendition.url));
    setMessage(selectionMessage || "已填入当前表单；保存草稿后保留，发布后才公开。已发布的图片版本保持原样。");
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const body = new FormData(event.currentTarget);
    await act(async () => {
      const media = await request<Media>("/catalog/admin/media/", { method: "POST", body });
      open(media); await choose(media);
    });
  }
  async function saveMetadata(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!editing || !metadata) return;
    await act(async () => {
      const media = await request<Media>(`/catalog/admin/media/${editing.id}/`, { method: "PATCH", body: JSON.stringify({ ...metadata, expected_updated_at: editing.updated_at }) });
      setEditing(media); setMetadata(metadataOf(media));
      setData(previous => previous ? { ...previous, results: previous.results.map(row => row.id === media.id ? media : row) } : null);
      await choose(media);
    });
  }
  return <section className="inline-media-picker" ref={root}>
    <button className="button secondary" type="button" onClick={() => void load()} disabled={busy}>选择已有图片</button>
    {selectedRenditionId ? <button className="button secondary" type="button" onClick={() => void current()} disabled={busy}>编辑当前图片出处</button> : null}
    <form onSubmit={upload}><fieldset disabled={busy || dirty}><label>上传图片<input type="file" name="image" accept="image/jpeg,image/png,image/webp" required /></label><label>图片说明<input name="alt_text" maxLength={1000} /></label><details><summary>图片出处与使用说明</summary>{fields.slice(1).map(([key, label, limit]) => <label key={key}>{label}<input type={key === "source_url" ? "url" : "text"} name={key} maxLength={limit} /></label>)}</details><button className="button secondary">上传并填入</button></fieldset></form>
    {data ? <><div className="inline-media-grid">{data.results.map(media => <div key={media.id}><button type="button" onClick={() => void act(() => choose(media))} disabled={busy || dirty} aria-label={`选用${media.alt_text || "图片"}`}>{media.renditions[0] ? <img src={normalizePublicResourceUrl(media.renditions[0].url)} alt={media.alt_text || "图片"} /> : <span>{media.alt_text || "选择图片"}</span>}</button><button type="button" onClick={() => open(media)} disabled={busy}>编辑出处</button></div>)}</div><div className="issue-pagination"><button type="button" disabled={busy || data.page <= 1} onClick={() => void load(data.page - 1)}>上一页</button><span>{data.page} / {data.pages}</span><button type="button" disabled={busy || data.page >= data.pages} onClick={() => void load(data.page + 1)}>下一页</button></div></> : null}
    {editing && metadata ? <form onSubmit={saveMetadata}><fieldset disabled={busy}><legend>图片出处与使用说明</legend><p>保存会更新素材资料并填入新的图片版本。已有文章保留原图片，需分别确认更新。</p>{fields.map(([key, label, limit]) => <label key={key}>{label}{key === "rights" ? <textarea maxLength={limit} value={metadata[key]} onChange={event => setMetadata({ ...metadata, [key]: event.target.value })} /> : <input type={key === "source_url" ? "url" : "text"} maxLength={limit} value={metadata[key]} onChange={event => setMetadata({ ...metadata, [key]: event.target.value })} />}</label>)}<button className="button secondary">保存资料并填入</button><button type="button" onClick={() => void act(async () => open(await request<Media>(`/catalog/admin/media/${editing.id}/`)))}>重新读取资料</button></fieldset></form> : null}
    {message ? <p role="status">{message}</p> : null}
  </section>;
}
