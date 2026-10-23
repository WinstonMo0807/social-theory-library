"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { Bookmark, Copy, Quote, Share2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { knowledgeSaveRequest, loadKnowledgeCitation, type KnowledgeCitation, type KnowledgeSaveCommand,
  type KnowledgeSaveState } from "@/lib/api/knowledge-actions.client";
import type { KnowledgeNodeDetail } from "@/lib/api/knowledge.types";
import { usePublicSession } from "@/components/public-session-provider";
import { Dialog } from "@/components/ui/dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import styles from "./knowledge-node-actions.module.css";

type NodeIdentity = Pick<KnowledgeNodeDetail, "id" | "canonical_name_zh" | "slug">;
type PendingSave = { owner: string; nodeId: string; command: KnowledgeSaveCommand };

export function KnowledgeNodeActions({ node }: { node: NodeIdentity }) {
  const { state: session } = usePublicSession();
  const [epoch, setEpoch] = useState(0);
  const memory = useRef<PendingSave | null>(null);
  const [pending, setPending] = useState<PendingSave | null>(null);
  const retain = useCallback((value: PendingSave | null) => { memory.current = value; setPending(value); }, []);
  useUnsavedForm({ pending: !!pending }, { pending: false });
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : null;
  useEffect(() => {
    if (memory.current && (owner && memory.current.owner !== owner || memory.current.nodeId !== node.id)) retain(null);
  }, [owner, node.id, retain]);
  return <Actions key={`${node.id}:${owner}:${epoch}`} node={node} owner={owner}
    initialCommand={pending?.owner === owner && pending.nodeId === node.id ? pending.command : null} retain={retain}
    ready={session.status === "authenticated" || session.status === "unauthenticated"} />;
}

function Actions({ node, owner, ready, initialCommand, retain }: { node: NodeIdentity; owner: string | null; ready: boolean; initialCommand: KnowledgeSaveCommand | null; retain: (value: PendingSave | null) => void }) {
  const [state, setState] = useState<KnowledgeSaveState | null>(null);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState<KnowledgeSaveCommand | null>(initialCommand);
  const [saveError, setSaveError] = useState("");
  const [notice, setNotice] = useState("");
  const [panel, setPanel] = useState<"citation" | "share" | null>(null);
  const [citation, setCitation] = useState<KnowledgeCitation | null>(null);
  const [citationBusy, setCitationBusy] = useState(false);
  const [citationError, setCitationError] = useState("");
  const [shareUrl, setShareUrl] = useState("");
  const abort = useRef<AbortController | null>(null);
  const citationAbort = useRef<AbortController | null>(null);
  const live = useRef(true);
  const actionLock = useRef(false);
  useEffect(() => {
    live.current = true;
    const controller = new AbortController();
    abort.current = controller;
    if (owner) knowledgeSaveRequest(node.id, owner, controller.signal).then(value => {
      if (!controller.signal.aborted) setState(value);
    }).catch(error => {
      if (!controller.signal.aborted) setSaveError(error instanceof Error ? error.message : "未能读取收藏状态。");
    });
    return () => { live.current = false; abort.current?.abort(); citationAbort.current?.abort(); };
  }, [node.id, owner]);

  async function save(recover = false) {
    if (!owner || actionLock.current) return;
    actionLock.current = true; setBusy(true); setSaveError(""); setNotice("");
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    let operation = unknown;
    let receiptChecked = false;
    try {
      if (recover || !state) {
        const current = await knowledgeSaveRequest(node.id, owner, controller.signal, undefined, operation?.request_id);
        if (!live.current || controller.signal.aborted) return;
        receiptChecked = true;
        setState(current);
        if (!operation) return;
        if (current.receipt?.request_id === operation.request_id && current.receipt.applied_saved === operation.saved) {
          retain(null); setUnknown(null); setNotice("已核对原操作，当前收藏状态已更新。"); return;
        }
        if (current.version !== operation.expected_version) {
          retain(null); setUnknown(null); setSaveError("收藏已在其他页面改变，已读取当前状态。"); return;
        }
      }
      operation ??= { saved: !state?.saved, expected_version: state?.version ?? "0", request_id: createRequestKey() };
      retain({ owner, nodeId: node.id, command: operation });
      const value = await knowledgeSaveRequest(node.id, owner, controller.signal, operation);
      if (!live.current || controller.signal.aborted) return;
      if (value.receipt?.request_id !== operation.request_id || value.receipt.applied_saved !== operation.saved) {
        throw new Error("暂时无法确认原操作的回执。");
      }
      retain(null); setState(value); setUnknown(null); setNotice(value.saved ? "已收藏此条目。" : "已取消收藏。");
    } catch (error) {
      if (!live.current || controller.signal.aborted) return;
      const definite = (!unknown || receiptChecked) && error instanceof ApiRequestError && [400, 401, 403, 404, 409, 422].includes(error.status);
      if (operation && !definite) setUnknown(operation);
      if (definite) { retain(null); setState(null); setUnknown(null); }
      setSaveError(operation && !definite ? "结果暂未确认，请核对原操作后再修改收藏。" :
        error instanceof Error ? error.message : "收藏暂不可用，请重新核对。");
    } finally {
      actionLock.current = false;
      if (live.current) setBusy(false);
    }
  }

  async function openCitation() {
    setPanel("citation"); setCitation(null); setCitationError(""); setCitationBusy(true);
    citationAbort.current?.abort();
    const controller = new AbortController(); citationAbort.current = controller;
    try {
      const value = await loadKnowledgeCitation(node.slug, controller.signal);
      if (!controller.signal.aborted && live.current) {
        if (value.node_id !== node.id) throw new Error("条目身份已变化，请重新读取此页。");
        setCitation(value);
      }
    } catch (error) {
      if (!controller.signal.aborted && live.current) setCitationError(error instanceof Error ? error.message : "未能获取引用。");
    } finally {
      if (!controller.signal.aborted && live.current) setCitationBusy(false);
    }
  }

  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); if (live.current) setNotice("已复制。"); }
    catch { if (live.current) setNotice("浏览器未允许复制，请在文本框中选择并复制。"); }
  }

  return <div className={styles.root}>
    <div className={styles.actions}>
      {!owner && ready ? <Link href={`/login?next=${encodeURIComponent(`/theories/nodes/${node.slug}`)}`}><Bookmark size={15} />收藏</Link> :
        <button type="button" aria-pressed={Boolean(state?.saved)} disabled={!ready || busy || !owner || !state && !saveError}
          onClick={() => void save(Boolean(unknown) || !state)}><Bookmark size={15} fill={state?.saved ? "currentColor" : "none"} />
          {busy ? "核对中…" : unknown ? "核对原操作" : !state && saveError ? "重读收藏状态" : state?.saved ? "已收藏" : "收藏"}</button>}
      <button type="button" onClick={() => void openCitation()}><Quote size={15} />引用</button>
      <button type="button" onClick={() => { setShareUrl(new URL(`/theories/nodes/${encodeURIComponent(node.slug)}`, window.location.origin).href); setPanel("share"); }}><Share2 size={15} />分享</button>
    </div>
    {saveError ? <p className={styles.message} role="alert">{saveError}</p> : null}
    {unknown && !saveError ? <p className={styles.message} role="alert">原收藏操作尚未确认，请先核对原操作；离开本页会失去查回入口。</p> : null}
    {notice ? <p className={styles.message} role="status">{notice}</p> : null}
    <Dialog open={panel !== null} onRequestClose={() => { setPanel(null); citationAbort.current?.abort(); }}
      className={styles.dialog} aria-labelledby={`knowledge-actions-${node.id}`}>
      <header><h2 id={`knowledge-actions-${node.id}`}>{panel === "citation" ? "引用此条目" : "分享此条目"}</h2>
        <button type="button" aria-label="关闭" onClick={() => { setPanel(null); citationAbort.current?.abort(); }}><X size={18} /></button></header>
      {panel === "citation" ? <>
        {citationBusy ? <p role="status">正在核对当前公开条目…</p> : citationError ? <div role="alert"><p>{citationError}</p><button onClick={() => void openCitation()}>重新获取</button></div> :
          citation ? <><p>{citation.notice}</p><textarea aria-label="条目引用" readOnly value={citation.text} rows={5} />
            <button type="button" onClick={() => void copy(citation.text)}><Copy size={15} />复制条目引用</button></> : null}
      </> : <><p>{node.canonical_name_zh}</p><input aria-label="条目链接" readOnly value={shareUrl} />
        <button type="button" onClick={() => void copy(shareUrl)}><Copy size={15} />复制链接</button></>}
      {notice ? <p role="status">{notice}</p> : null}
    </Dialog>
  </div>;
}
