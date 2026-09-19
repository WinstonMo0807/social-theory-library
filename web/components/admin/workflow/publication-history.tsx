"use client";

import { useRef, useState } from "react";
import type { components } from "@/lib/api/generated/schema";
import { apiRequest } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { createRequestKey } from "@/lib/request-key";

type Revision = components["schemas"]["PublicationHistoryItem"];

export function PublicationHistory({ editionId, token, canPublish, onChanged }: {
  editionId: string; token: string | null; canPublish: boolean; onChanged: () => Promise<void>;
}) {
  const { data, error, loading, retry } = useApiResource<Revision[]>(`/catalog/admin/editions/${editionId}/publication/history/`, token);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const requests = useRef(new Map<string, string>());
  const submitting = useRef(false);
  async function restore(row: Revision) {
    if (submitting.current) return;
    const reason = window.prompt(`准备恢复第 ${row.revision} 次公开内容。请填写原因，当前草稿和原文件会保留。`);
    if (!reason?.trim() || busy) return;
    submitting.current = true;
    setBusy(true);
    try {
      const identity = JSON.stringify([editionId, row.id, reason.trim()]);
      const requestKey = requests.current.get(identity) ?? createRequestKey();
      requests.current.set(identity, requestKey);
      await apiRequest(`/catalog/admin/editions/${editionId}/publication/rollback/`, {
        method: "POST", body: JSON.stringify({ revision_id: row.id, reason: reason.trim(), request_key: requestKey }),
      }, token);
      requests.current.delete(identity);
      setMessage("已提交恢复。处理完成前，当前公开内容继续服务。");
      await onChanged();
      retry();
    } catch (failure) {
      setMessage(failure instanceof Error ? failure.message : "未能提交恢复，请重试。");
    } finally { submitting.current = false; setBusy(false); }
  }
  return <details className="admin-panel"><summary>公开版本历史</summary>
    {loading ? <p role="status">正在读取历史…</p> : null}
    {error ? <p role="alert">{error}<button type="button" onClick={retry}>重试</button></p> : null}
    {data?.map((row) => <article key={row.id}><strong>第 {row.revision} 次发布</strong><p>{row.title}</p>
      {row.is_current ? <span>当前公开</span> : row.can_rollback ? <button type="button" disabled={!canPublish || busy} onClick={() => void restore(row)}>恢复此公开版本</button> : <span>未曾正式公开，不能恢复</span>}
    </article>)}
    {data && !data.length ? <p>尚无公开版本。</p> : null}
    {message ? <p role="status">{message}</p> : null}
  </details>;
}
