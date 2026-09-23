"use client";

import { RecycleControl } from "@/components/admin/recycle-control";
import { ProcessingError } from "@/components/admin/processing-error";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
import { fileProcessingStatusLabel } from "./file-presentation";

type SourceItem = {
  id: string;
  source_filename: string;
  status: string;
  edition: string | null;
  error_code: string;
  error_message: string;
  dispatch_status: string;
  dispatch_error?: string;
  staging_status?: string;
  retry_count?: number;
  attempts?: { id: string; stage: string; status: string; error_message?: string }[];
};

/** A legacy/unbound source remains actionable without inventing Work/Edition. */
export function UploadSourceContext({ itemId }: { itemId: string }) {
  const query = useSearchParams();
  const returnTo = safeAdminHref(query.get("return_to"), "/admin/review?source=upload");
  const result = useApiResource<SourceItem>(`/ingestion/items/${encodeURIComponent(itemId)}/`, getServerSessionCredential());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const item = result.data?.id === itemId ? result.data : null;
  async function retrySource() {
    if (busy || !item) return;
    setBusy(true);
    setMessage("");
    try {
      const receipt = await apiRequest<{ detail?: string }>(`/ingestion/items/${encodeURIComponent(item.id)}/retry/`, { method: "POST" }, getServerSessionCredential());
      setFailed(false);
      setMessage(`重试请求已接受。${receipt.detail || ""} 这不代表处理或公开已经完成，请核对下方最新状态。`);
      result.retry();
    } catch (reason) {
      setFailed(true);
      setMessage(reason instanceof Error ? reason.message : "未能重试原来源，记录仍保留。");
    } finally {
      setBusy(false);
    }
  }
  return <section className="admin-panel" aria-label="选定上传来源" style={{ marginBottom: 24, padding: 20 }}>
    <header><h2>选定上传来源</h2><Link href={returnTo}>返回原待办</Link></header>
    {message ? <p role={failed ? "alert" : "status"}>{message}</p> : null}
    {result.error ? <p role="alert">来源读取失败：{result.error}<button type="button" onClick={result.retry}>重试来源读取</button></p> : result.loading ? <p role="status">正在读取指定来源…</p> : !item ? <p role="alert">未取得与指定上传编号一致的记录，不会显示其他文件。</p> : <>
      <h3>{item.source_filename}</h3><RecycleControl kind="upload" id={item.id} name={item.source_filename} onDeleted={() => window.location.assign(returnTo)} /><p>{item.edition ? "书目已经建立，可以继续核对资料。" : "这个文件还没有生成书目。请先处理下面的问题。"}</p>
      <dl className="workflow-publication-summary"><div><dt>文件处理</dt><dd>{fileProcessingStatusLabel(item.status)}</dd></div><div><dt>后台任务</dt><dd>{fileProcessingStatusLabel(item.dispatch_status)}</dd></div><div><dt>重试记录</dt><dd>{item.retry_count ?? "待核实"}</dd></div></dl>
      {item.error_message || item.dispatch_error ? <ProcessingError code={item.error_code} message={item.error_message || item.dispatch_error || ""} /> : null}
      <p>如果原文件已经缺失，可以在下方重新上传。这里会保留之前的处理记录。</p>
      <div className="admin-title-actions"><button type="button" onClick={result.retry}>刷新来源状态</button>{item.status === "failed" || item.status === "received" ? <button type="button" disabled={busy} onClick={() => void retrySource()}>{busy ? "正在请求安全重试…" : "重试原来源任务"}</button> : null}{item.edition ? <Link href={withAdminReturn(`/admin/intake/${encodeURIComponent(item.id)}`, returnTo)}>进入当前版本复核</Link> : null}</div>
      <details><summary>来源与处理记录</summary><p>上传编号：{item.id}；错误类型：{item.error_code || "未记录错误"}；暂存：{item.staging_status || "不适用或尚未记录"}</p>{item.attempts?.map((attempt) => <p key={attempt.id}>{attempt.stage} · {fileProcessingStatusLabel(attempt.status)} {attempt.error_message}</p>)}</details>
    </>}
  </section>;
}
