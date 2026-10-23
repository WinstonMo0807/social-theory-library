"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { booklistRequest, type BooklistSummary } from "@/lib/api/booklists.client";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { PlanSettingsForm, type PlanSettings } from "./reading-plan-form";

type Preview = { owner_id: string; list_id: string; expected_version: string; source_token: string; ready: boolean;
  items: { item_id: string; title: string; source_status: string; reader_url: string | null }[] };
type Result = { owner_id: string; request_id: string; record_id: string | null; deleted: boolean };
type Intent = PlanSettings & { request_id: string; expected_version: string; source_token: string; item_ids?: string[] };

export function BooklistPlanForm({ owner, row, selected, onBusy, onClose }: { owner: string; row: BooklistSummary; selected: string[]; onBusy: (value: boolean) => void; onClose: () => void }) {
  const router = useRouter();
  const params = new URLSearchParams({ expected_version: row.version });
  selected.forEach(id => params.append("item_ids", id));
  const load = useCallback((path: string, signal: AbortSignal) => booklistRequest<Preview>(owner, path, { signal }), [owner]);
  const source = usePersistentWorkspace(`/reading/lists/${row.id}/plan-preview/?${params}`, owner, undefined, load);
  const data = source.error ? null : source.data;
  const [requestId, setRequestId] = useState<string | null>(null), [canRetry, setCanRetry] = useState(false), [broken, setBroken] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const intent = useRef<Intent | null>(null), controller = useRef<AbortController | null>(null), sending = useRef(false);
  const key = `stl-booklist-plan-request:${owner}:${row.id}`;
  useEffect(() => {
    const abort = new AbortController(); controller.current = abort;
    const off = subscribeToSessionChanges(() => abort.abort());
    queueMicrotask(() => {
      if (abort.signal.aborted) return;
      try {
        const id = sessionStorage.getItem(key);
        if (!id) return;
        if (!/^[\da-f-]{36}$/i.test(id)) throw Error("原计划请求记录格式异常，请先核对我的阅读计划。");
        setRequestId(id); setMessage("上次计划请求尚未取得明确回执，请先查回原结果。");
      } catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "原计划请求不可用。"); }
    });
    return () => { abort.abort(); off(); };
  }, [key]);
  function clear() { sessionStorage.removeItem(key); setRequestId(null); setCanRetry(false); setBroken(false); intent.current = null; }
  async function submit(settings?: PlanSettings, lookup = false) {
    const parent = controller.current;
    if (!parent || parent.signal.aborted || sending.current || broken) return;
    const command = intent.current || (settings && data?.ready ? { ...settings, expected_version: row.version, source_token: data.source_token,
      request_id: createRequestKey(), ...(selected.length ? { item_ids: [...selected] } : {}) } : null);
    const id = lookup ? requestId : command?.request_id;
    if (!id || !lookup && !command) return;
    sending.current = true; setBusy(true); onBusy(true); setMessage("");
    const signal = AbortSignal.any([parent.signal, AbortSignal.timeout(30000)]);
    try {
      sessionStorage.setItem(key, id); setRequestId(id);
      if (!lookup && command) { intent.current = command; setCanRetry(true); }
      const result = await withPrivateOwner(owner, () => booklistRequest<Result>(owner, lookup
        ? `/reading/lists/plan-receipt/?request_id=${encodeURIComponent(id)}` : `/reading/lists/${row.id}/create-plan/`,
      { signal, ...(lookup ? {} : { method: "POST", body: JSON.stringify(command) }) }), signal);
      if (result.owner_id !== owner || result.request_id !== id) throw Error("计划回执与当前账户或原请求不符。");
      clear();
      if (result.record_id) router.push(`/account/plans/${result.record_id}`);
      else setMessage("原请求已经完成，但计划后来被删除。本次核对没有重新创建计划。");
    } catch (reason) {
      if (parent.signal.aborted) return;
      if (!lookup && reason instanceof ApiRequestError && [400, 403, 404, 409].includes(reason.status)) { clear(); source.reload(); }
      setMessage(reason instanceof Error ? reason.message : "计划结果尚未确认，请查回原结果。");
    } finally { sending.current = false; if (!parent.signal.aborted) { setBusy(false); onBusy(false); } }
  }
  return <div>
    <p>{selected.length ? `使用所选 ${selected.length} 部作品` : "使用这份书单的全部作品"}，保留书单顺序与当前公开版本。生成的私人计划独立保存，之后移除书单作品不会删除计划。</p>
    {source.error ? <p role="alert">{source.error}<button onClick={source.reload}>重新核对材料</button></p> : !data ? <p role="status">正在核对作品及可读版本…</p> : <details open={!data.ready}><summary>{data.items.length} 部作品 · {data.ready ? "可生成计划" : "存在不可读的来源"}</summary><ul>{data.items.map(item => <li key={item.item_id}>{item.reader_url ? <Link href={item.reader_url} target="_blank" rel="noopener">{item.title}</Link> : item.title} · {item.source_status === "available" ? "可读" : "当前不可读，请返回书单调整选择"}</li>)}</ul></details>}
    {message ? <p role="status">{message}</p> : null}
    {requestId || broken ? <div><p>先核对原操作，再生成新的计划。</p>{requestId ? <button disabled={busy || broken} onClick={() => void submit(undefined, true)}>核对原计划结果</button> : null}{canRetry ? <button disabled={busy || broken} onClick={() => void submit()}>用原请求重试</button> : null}<Link href="/account/plans" target="_blank" rel="noopener">查看我的阅读计划</Link><button disabled={busy} onClick={() => { if (window.confirm("已核对服务端计划？清除本机请求记录不会撤销已经生成的计划。")) clear(); }}>核对后清除本机记录</button></div> : null}
    <PlanSettingsForm preserveSourceOrder ownerId={owner} defaultGoal={row.goal} busy={busy || Boolean(requestId) || broken || !data?.ready} onSave={settings => void submit(settings)} onCancel={onClose} />
  </div>;
}
