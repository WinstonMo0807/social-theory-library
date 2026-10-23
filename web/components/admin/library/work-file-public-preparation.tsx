"use client";

import { createRequestKey } from "../../../lib/request-key";
import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { prepareWorkFilePublic } from "@/lib/api/work-files.client";
import type { WorkFile } from "@/lib/api/work-files.types";
import { Dialog } from "@/components/ui/dialog";
import styles from "./work-files.module.css";

export function WorkFilePublicPreparation({ editionId, file, ownerId, onClose, onChanged }: {
  editionId: string; file: WorkFile; ownerId: string; onClose: () => void; onChanged: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [result, setResult] = useState<{ status: string; detail: string } | null>(null);
  const alive = useRef(true), inFlight = useRef(false), request = useRef("");
  useEffect(() => {
    alive.current = true;
    const unsubscribe = subscribeToSessionChanges(() => { alive.current = false; });
    return () => { alive.current = false; unsubscribe(); };
  }, []);
  const close = () => { if (!inFlight.current) onClose(); };
  async function prepare() {
    if (inFlight.current || !confirmed || result || !file.public_preparation.can_prepare) return;
    if (!request.current) request.current = createRequestKey();
    const request_key = request.current;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const response = await withPrivateOwner(ownerId, () => prepareWorkFilePublic(editionId, file.id, { request_key, expected_asset_updated_at: file.updated_at, confirm: true }));
      if (!alive.current) return;
      if (response.request_key !== request_key || response.asset_id !== file.id) throw new Error("尚未确认本次文件准备请求，请保留同一请求重试。");
      setResult(response); onChanged();
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "请求尚未确认，请使用同一请求重试。"); }
    finally { inFlight.current = false; if (alive.current) setBusy(false); }
  }
  return <Dialog open className={styles.dialog} aria-labelledby="prepare-public-file-title" onRequestClose={close}>
    <header><div><h2 id="prepare-public-file-title">准备公开阅读文件</h2><p>{file.filename || "所选阅读副本"}</p></div><button aria-label="关闭公开文件准备" disabled={busy} onClick={close}><X size={18} /></button></header>
    {result ? <div className={styles.success} role="status"><h3>{result.status === "ready" ? "分发副本已就绪" : "文件准备请求已保存"}</h3><p>{result.detail}</p><p>回到文件列表查看实际状态，准备完成后再明确采用或发布。</p></div> : <>
      <p className={styles.warning}>这一步会把所选阅读副本传到已配置的公开分发存储。只有已核对权利、允许公开阅读的文件才能继续。</p>
      <p className={styles.muted}>此操作准备分发副本；书目和当前阅读入口仍由后续采用或发布决定。仅保存原件和草稿选择不会触发这项操作。</p>
      <label className={styles.check}><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />已核对文件内容与权利，允许将此阅读副本传入公开分发存储。</label>
    </>}
    {error ? <p role="alert" className={styles.error}>{error}</p> : null}
    <footer><button disabled={busy} onClick={close}>{result ? "返回文件与任务" : "返回核对"}</button>{!result ? <button className={styles.primary} disabled={!confirmed || busy || !file.public_preparation.can_prepare} onClick={() => void prepare()}>{busy ? "正在保存请求…" : error ? "重试同一准备请求" : "确认准备公开副本"}</button> : null}</footer>
  </Dialog>;
}
