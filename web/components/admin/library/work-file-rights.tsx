"use client";

import { confirmAction } from "@/lib/ui-dialog";

import { createRequestKey } from "../../../lib/request-key";
import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { updateWorkFileRights } from "@/lib/api/work-files.client";
import type { WorkFilesState } from "@/lib/api/work-files.types";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import styles from "./work-files.module.css";

export function WorkFileRightsDialog({ state, ownerId, onClose, onSaved, onRefresh }: {
  state: WorkFilesState; ownerId: string; onClose: () => void; onSaved: () => void; onRefresh: () => void;
}) {
  const current = state.edition!.rights;
  const [base, setBase] = useState(current), [note, setNote] = useState(current.note);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const inFlight = useRef(false), alive = useRef(true), receipt = useRef<{ key: string; request: string } | null>(null);
  useEffect(() => {
    alive.current = true;
    const unsubscribe = subscribeToSessionChanges(() => { alive.current = false; });
    return () => { alive.current = false; unsubscribe(); };
  }, []);
  const dirty = note !== base.note, stale = base.source_asset_id !== current.source_asset_id || base.updated_at !== current.updated_at;
  useUnsavedForm(dirty, false);
  const close = async () => { if (!inFlight.current && (!dirty || (await confirmAction("版权说明尚未保存，确定放弃修改吗？")))) onClose(); };
  async function save() {
    if (inFlight.current || stale || !dirty || !base.source_asset_id || !base.updated_at || !current.can_edit) return;
    const input = { expected_asset_updated_at: base.updated_at, rights_note: note };
    const key = JSON.stringify([base.source_asset_id, input]);
    const request_key = receipt.current?.key === key ? receipt.current.request : createRequestKey();
    receipt.current = { key, request: request_key }; inFlight.current = true; setBusy(true); setError("");
    try {
      const result = await withPrivateOwner(ownerId, () => updateWorkFileRights(state.edition!.id, base.source_asset_id!, { ...input, request_key }));
      if (!alive.current) return;
      if (result.asset_id !== base.source_asset_id || result.request_key !== request_key) throw new Error("尚未确认此文件的版权说明保存结果，请保留本次请求重试。");
      onSaved();
    } catch (reason) {
      if (alive.current) { setError(reason instanceof Error ? reason.message : "版权说明未保存，输入仍保留。"); if (reason instanceof ApiRequestError && reason.status === 409) onRefresh(); }
    } finally { inFlight.current = false; if (alive.current) setBusy(false); }
  }
  return <Dialog open className={styles.dialog} aria-labelledby="file-rights-title" onRequestClose={close}>
    <header><div><h2 id="file-rights-title">编辑版权与授权说明</h2><p>{state.work.title} · 当前所选文件</p></div><button aria-label="关闭版权说明" disabled={busy} onClick={close}><X size={18} /></button></header>
    <form onSubmit={event => { event.preventDefault(); void save(); }}>
      <label>文件来源与授权依据<textarea value={note} maxLength={4000} disabled={busy} onChange={event => setNote(event.target.value)} placeholder="记录文件来源、权利人或授权依据" /></label>
      <p className={styles.muted}>说明保留在这份文件的维护记录中。当前访问策略保持原样；保存说明不代表取得授权或完成公开发布。</p>
      {error ? <p role="alert" className={styles.error}>{error}</p> : null}
      {stale ? <div className={styles.warning}><p>文件或版权说明已更新。当前输入保留，请核对最新说明。</p><blockquote>{current.note || "最新记录暂无说明。"}</blockquote><button type="button" disabled={busy || !current.can_edit} onClick={() => { setBase(current); receipt.current = null; setError(""); }}>已核对，保留输入并采用最新文件基准</button></div> : null}
      <footer><button type="button" disabled={busy} onClick={close}>取消</button><button className={styles.primary} disabled={busy || stale || !dirty || !current.can_edit}>{busy ? "正在保存…" : "保存版权说明"}</button></footer>
    </form>
  </Dialog>;
}
