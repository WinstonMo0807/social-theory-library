"use client";

import { useState, type FormEvent } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { useActionGuard } from "@/lib/use-action-guard";
type Media = components["schemas"]["MediaAsset"];
type Page = { results: Media[]; pages: number; page: number; count: number };

export function InlineMediaPicker({ onSelect }: { onSelect: (id: string, url: string) => void }) {
  const { startAction, finishAction } = useActionGuard();
  const [data, setData] = useState<Page | null>(null), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  async function load(page = 1) {
    if (!startAction("media")) return;
    setBusy(true); setMessage("");
    try { setData(await apiRequest<Page>(`/catalog/admin/media/collection/?page=${page}`, {}, getServerSessionCredential())); }
    catch (error) { setMessage(error instanceof Error ? error.message : "图片读取失败"); }
    finally { setBusy(false); finishAction("media"); }
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!startAction("media")) return;
    setBusy(true); setMessage("");
    try {
      const media = await apiRequest<Media>("/catalog/admin/media/", { method: "POST", body: new FormData(event.currentTarget) }, getServerSessionCredential());
      await choose(media);
    } catch (error) { setMessage(error instanceof Error ? error.message : "图片上传失败"); }
    finally { setBusy(false); finishAction("media"); }
  }
  async function choose(media: Media) {
    const rendition = await apiRequest<components["schemas"]["MediaRendition"]>(`/catalog/admin/media/${media.id}/renditions/`, { method: "POST", body: JSON.stringify({ kind: "hero", width: 1280 }) }, getServerSessionCredential());
    onSelect(rendition.id, normalizePublicResourceUrl(rendition.url)); setMessage("已填入当前表单；保存草稿后保留，发布后才公开。");
  }
  async function select(media: Media) {
    if (!startAction("media")) return;
    setBusy(true);
    try {
      await choose(media);
    } catch (error) { setMessage(error instanceof Error ? error.message : "选图失败"); }
    finally { setBusy(false); finishAction("media"); }
  }
  return <section className="inline-media-picker"><button className="button secondary" type="button" onClick={() => load()} disabled={busy}>选择已有图片</button><form onSubmit={upload}><label>上传图片<input type="file" name="image" accept="image/jpeg,image/png,image/webp" required /></label><label>图片说明<input name="alt_text" /></label><button className="button secondary" disabled={busy}>上传并填入</button></form>{data ? <><div className="inline-media-grid">{data.results.map(media => <button type="button" key={media.id} onClick={() => select(media)} disabled={busy}>{media.renditions[0] ? <img src={normalizePublicResourceUrl(media.renditions[0].url)} alt={media.alt_text || "图片"} /> : <span>{media.alt_text || "选择图片"}</span>}</button>)}</div><div className="issue-pagination"><button disabled={busy || data.page <= 1} onClick={() => load(data.page - 1)}>上一页</button><span>{data.page} / {data.pages}</span><button disabled={busy || data.page >= data.pages} onClick={() => load(data.page + 1)}>下一页</button></div></> : null}{message ? <p role="status">{message}</p> : null}</section>;
}
