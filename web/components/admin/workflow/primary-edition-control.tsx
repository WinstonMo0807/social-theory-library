"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { apiRequest } from "@/lib/api";
import { safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
import { primaryEditionRequest, type PrimaryEditionPreview, type PrimaryEditionResult } from "@/lib/api/primary-edition";

export function PrimaryEditionControl({ editionId, credential, canPublish, disabled, returnTo, onChanged }: { editionId: string; credential: string | null; canPublish: boolean; disabled: boolean; returnTo: string; onChanged: () => Promise<unknown> }) {
  const [preview, setPreview] = useState<PrimaryEditionPreview | null>(null);
  const [result, setResult] = useState<PrimaryEditionResult | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const endpoint = `/catalog/admin/editions/${encodeURIComponent(editionId)}/primary/`;
  async function prepare() {
    if (inFlight.current || disabled || !canPublish) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const next = await apiRequest<PrimaryEditionPreview>(endpoint, {}, credential);
      if (next.edition_id !== editionId) throw new Error("预览返回了其他出版版本，已停止操作。");
      setPreview(next);
      setOpen(next.can_select && !next.already_primary);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "未能读取主版本影响预览。");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  async function confirm() {
    if (!preview || disabled || !canPublish || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const receipt = await apiRequest<PrimaryEditionResult>(endpoint, { method: "POST", body: JSON.stringify(primaryEditionRequest(preview, editionId)) }, credential);
      if (receipt.edition_id !== editionId || receipt.request_key !== preview.request_key || receipt.command_accepted !== true) throw new Error("返回结果与本次请求不一致，未确认切换成功。请用同一请求再次核验。");
      setResult(receipt);
      setOpen(false);
      await onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "暂未确认切换结果。保留原请求，可安全重试。");
      // Keep preview.request_key and fingerprint even after a timeout.
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return <div className="workflow-v306-primary-control">
    <button type="button" disabled={disabled || busy || !canPublish} onClick={() => void prepare()}>{busy && !open ? "正在核对主版本…" : "主版本设置"}</button>
    {disabled ? <small>请先保存当前修改，再核对主版本。</small> : !canPublish ? <small>当前角色不能更改作品主版本。</small> : null}
    {error && !open ? <p role="alert">{error}{preview?.can_select ? <button type="button" disabled={busy || disabled} onClick={() => setOpen(true)}>重试同一切换请求</button> : null}</p> : null}
    {preview?.already_primary ? <p role="status">当前已经是唯一主版本，没有执行重复修改。</p> : null}
    {preview && !preview.can_select ? <div role="alert"><strong>当前不能更改主版本</strong><ul>{preview.blocking.map((value) => <li key={value}>{value}</li>)}</ul><button type="button" disabled={busy || disabled} onClick={() => void prepare()}>重新读取切换条件</button></div> : null}
    {result ? <div role="status"><p>{result.detail}</p><p>作品列表：{result.listing_effective ? "所选版本已生效" : "当前未由所选版本展示"}；关联更新：{result.projections_complete ? "已完成" : "尚未全部完成"}。</p>{result.listing_effective && result.public_url ? <Link href={result.public_url} target="_blank">核验公开作品</Link> : null}{result.events.map((event) => { const href = safeAdminHref(event.href, ""); return href ? <Link key={event.id} href={withAdminReturn(href, returnTo)}>查看关联版本处理结果（{event.status}）</Link> : <span key={event.id}>发布记录 {event.id}：{event.status}</span>; })}</div> : null}
    <ConfirmDialog open={open} title="确认更改作品主版本" description="只切换作品列表使用的已公开版本，不发布其他草稿。请核对所选版本和影响。" confirmLabel={error ? "重试同一切换请求" : "确认更改主版本"} pending={busy || disabled} details={preview ? [`作品：${preview.title}`, `所选版本：${preview.editions.find((edition) => edition.id === editionId)?.version_label || "出版版本"}`, ...preview.impact, ...(error ? [`未确认结果：${error}。重试保留同一请求编号和预检指纹。`] : [])] : []} onCancel={() => setOpen(false)} onConfirm={confirm} />
  </div>;
}
