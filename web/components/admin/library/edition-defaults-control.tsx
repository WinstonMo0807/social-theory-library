"use client";

import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { ConfirmDialog } from "@/components/confirm-dialog";

type EditionOption = {
  id: string;
  label: string;
  version_label: string;
  publication_year: number | null;
  publisher: string;
  is_primary: boolean;
  public: boolean;
  public_state: string;
  reader_ready: boolean;
  download_ready: boolean;
};

type DefaultsPayload = {
  work_id: string;
  title: string;
  reader_default_edition_id: string | null;
  download_default_edition_id: string | null;
  effective_reader_edition_id: string | null;
  effective_download_edition_id: string | null;
  options: EditionOption[];
  detail: string;
};

function optionLabel(option: EditionOption) {
  const tags = [option.is_primary ? "主版本" : "", !option.public ? "尚未公开" : "", option.public && !option.reader_ready ? "阅读文件未就绪" : ""].filter(Boolean);
  return `${option.label}${tags.length ? `（${tags.join(" · ")}）` : ""}`;
}

export function EditionDefaultsControl({ workId }: { workId: string }) {
  const endpoint = `/catalog/admin/works/${encodeURIComponent(workId)}/edition-defaults/`;
  const resource = useApiResource<DefaultsPayload>(endpoint, getServerSessionCredential());
  const [reader, setReader] = useState("");
  const [download, setDownload] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!resource.data) return;
    const timer = window.setTimeout(() => {
      setReader(resource.data?.reader_default_edition_id || "");
      setDownload(resource.data?.download_default_edition_id || "");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [resource.data]);

  async function save() {
    if (!resource.data || busy) return;
    setBusy(true);
    setMessage("");
    const requestId = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    try {
      const saved = await apiRequest<DefaultsPayload & { saved?: boolean; request_id?: string }>(endpoint, {
        method: "PUT",
        body: JSON.stringify({ reader_default_edition_id: reader || null, download_default_edition_id: download || null, confirmed: true, request_id: requestId }),
      }, getServerSessionCredential());
      setReader(saved.reader_default_edition_id || "");
      setDownload(saved.download_default_edition_id || "");
      setMessage(`已保存出版版本设置${saved.request_id ? `（请求 ${saved.request_id.slice(0, 8)}）` : ""}。读者入口会按各自选择生效。`);
      setOpen(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "出版版本设置保存失败，请重试。当前选择仍保留。");
    } finally {
      setBusy(false);
    }
  }

  return <section className="edition-defaults-control admin-panel" aria-labelledby="edition-defaults-title">
    <header><div><h2 id="edition-defaults-title">出版版本管理</h2><p>{resource.data?.title ? `《${resource.data.title}》` : "当前作品"}可以分别指定在线阅读和下载默认版本。未单独选择时跟随公开主版本。</p></div><button type="button" className="button secondary" onClick={resource.retry} disabled={resource.loading}>重新读取</button></header>
    {resource.loading ? <p role="status">正在读取出版版本…</p> : null}
    {resource.error ? <p className="form-message" role="alert">{resource.error} <button type="button" onClick={resource.retry}>重试</button></p> : null}
    {resource.data ? <>
      <div className="edition-defaults-grid">
        <label><span>在线阅读默认版本</span><select value={reader} onChange={event => setReader(event.target.value)}><option value="">跟随公开主版本（推荐）</option>{resource.data.options.map(option => <option key={`reader:${option.id}`} value={option.id} disabled={!option.public || !option.reader_ready}>{optionLabel(option)}</option>)}</select><small>读者点击“在线阅读”时打开这个版本的阅读文件。</small></label>
        <label><span>下载默认版本</span><select value={download} onChange={event => setDownload(event.target.value)}><option value="">跟随公开主版本（推荐）</option>{resource.data.options.map(option => <option key={`download:${option.id}`} value={option.id} disabled={!option.public || !option.download_ready}>{optionLabel(option)}</option>)}</select><small>读者点击“下载”时使用这个版本；需要通过文件验证。</small></label>
      </div>
      <div className="edition-defaults-effective"><span>当前在线阅读：{resource.data.options.find(option => option.id === (resource.data?.effective_reader_edition_id || ""))?.label || "暂无可用公开版本"}</span><span>当前下载：{resource.data.options.find(option => option.id === (resource.data?.effective_download_edition_id || ""))?.label || "暂无可用公开版本"}</span></div>
      <footer><span>{resource.data.detail}</span><button type="button" className="button" onClick={() => setOpen(true)} disabled={busy || (reader === (resource.data.reader_default_edition_id || "") && download === (resource.data.download_default_edition_id || ""))}>保存出版版本设置</button></footer>
    </> : null}
    {message ? <p className="form-message" role="status">{message}</p> : null}
    <ConfirmDialog open={open} title="保存出版版本设置？" description="这会改变读者进入在线阅读和下载时默认使用的出版版本。不会发布草稿，也不会删除或覆盖其他版本。" details={[`在线阅读：${resource.data?.options.find(option => option.id === reader)?.label || "跟随公开主版本"}`, `下载：${resource.data?.options.find(option => option.id === download)?.label || "跟随公开主版本"}`]} confirmLabel="确认保存" pending={busy} onCancel={() => setOpen(false)} onConfirm={() => void save()} />
  </section>;
}
