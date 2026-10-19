"use client";

import { useEffect, useRef, useState } from "react";
import { Bell, BellOff, Check, RefreshCw } from "lucide-react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { commandSourceFollow, type SourceCommand, type SourceFollow } from "@/lib/api/source-follows.client";
import styles from "./source-status.module.css";

export function SourceFollowControl({ ownerId, path, row, canSubscribe, onSaved, onReload }: {
  ownerId: string; path: string; row: SourceFollow | null; canSubscribe: boolean;
  onSaved: (row: SourceFollow) => void; onReload: () => void;
}) {
  const [state, setState] = useState<"idle" | "pending" | "unknown" | "invalid">("idle");
  const [message, setMessage] = useState("");
  const operation = useRef<SourceCommand | null>(null), controller = useRef<AbortController | null>(null), epoch = useRef(0);
  useEffect(() => {
    epoch.current += 1;
    const unsubscribe = subscribeToSessionChanges(() => { epoch.current += 1; controller.current?.abort(); operation.current = null; setState("invalid"); setMessage("登录状态已变化，请重新验证后查看来源订阅。"); });
    return () => { epoch.current += 1; controller.current?.abort(); unsubscribe(); };
  }, [ownerId, path]);
  async function execute(action?: SourceCommand["action"]) {
    if (controller.current || state === "invalid") return;
    if (action) operation.current = { path, action, expected_revision: row?.revision ?? 0, request_id: crypto.randomUUID() };
    const input = operation.current;
    if (!input) return;
    const request = new AbortController(), version = epoch.current;
    controller.current = request; setState("pending"); setMessage("");
    try {
      const result = await withPrivateOwner(ownerId, () => commandSourceFollow(input, ownerId, request.signal), request.signal);
      if (request.signal.aborted || epoch.current !== version) return;
      if (result.owner_id !== ownerId || result.path !== path) throw new PrivateOwnerVerificationError("来源记录身份无法核对，请重新验证。", 403);
      operation.current = null; setState("idle"); onSaved(result);
      const changedAgain = input.action === "subscribe" ? !result.active : input.action === "unsubscribe" ? result.active : result.unread_count > 0;
      setMessage(changedAgain ? "本次请求已处理，此来源已有后续变化。请以重新读取的当前状态为准。" : input.action === "subscribe" ? "已订阅来源更新，可在我的资料中查看。" : input.action === "unsubscribe" ? "已取消订阅，已有记录保留。" : "已将当前更新标记为已读。");
    } catch (reason) {
      if (epoch.current !== version) return;
      const invalid = reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403, 404, 410].includes(reason.status);
      const uncertain = !invalid && (!(reason instanceof ApiRequestError) || reason.status === 0 || reason.status >= 500 || [408, 429].includes(reason.status));
      setState(invalid ? "invalid" : uncertain ? "unknown" : "idle");
      if (!uncertain) operation.current = null;
      setMessage(uncertain ? "尚未确认操作结果。原请求已保留，请重试本次操作，避免重复订阅或取消。" : reason instanceof Error ? reason.message : "操作尚未完成，请重试。");
      if (invalid || reason instanceof ApiRequestError && reason.status === 409) onReload();
    } finally { if (controller.current === request) controller.current = null; }
  }
  const disabled = state !== "idle";
  return <div className={styles.controls}>
    <div className={styles.actions}>
      {row?.active ? <button disabled={disabled} onClick={() => void execute("unsubscribe")}><BellOff size={16} />取消订阅</button>
        : <button disabled={disabled || !canSubscribe} onClick={() => void execute("subscribe")}><Bell size={16} />{row ? "重新订阅更新" : "订阅更新"}</button>}
      {row && row.unread_count > 0 ? <button disabled={disabled} onClick={() => void execute("mark_read")}><Check size={16} />标为已读</button> : null}
      {state === "unknown" ? <button onClick={() => void execute()}><RefreshCw size={15} />重试本次操作</button> : null}
      {state === "pending" ? <span role="status">正在保存…</span> : null}
    </div>
    {message ? <p role={state === "unknown" || state === "invalid" ? "alert" : "status"}>{message}</p> : null}
  </div>;
}
