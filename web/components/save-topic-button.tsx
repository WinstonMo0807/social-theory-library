"use client";

import { createRequestKey } from "../lib/request-key";
import Link from "next/link";
import { Bookmark } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { commandTopicSave, loadTopicSave, type TopicSaveCommand, type TopicSaveState } from "@/lib/api/topic-saves.client";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { usePublicSession } from "./public-session-provider";

type PendingTopicSave = { owner: string; input: TopicSaveCommand; dispatched: boolean };
export type TopicSaveCommands = { memory: RefObject<Map<string, PendingTopicSave>>; changed: () => void };

/** Keep command identities above account verification remounts, without browser storage. */
export function useTopicSaveCommands(owner?: string | null): TopicSaveCommands {
  const memory = useRef(new Map<string, PendingTopicSave>());
  const [pending, setPending] = useState(false);
  const changed = useCallback(() => setPending(memory.current.size > 0), []);
  useUnsavedForm(pending, false);
  useEffect(() => {
    if (!owner) return;
    for (const [key, value] of memory.current) if (value.owner !== owner) memory.current.delete(key);
    changed();
  }, [owner, changed]);
  return { memory, changed };
}

/** Collection only. Topic update subscriptions use TopicFollowButton. */
export function SaveTopicButton({ topicId, onChange, commands: sharedCommands }: { topicId: string; onChange?: (saved: boolean) => void; commands?: TopicSaveCommands }) {
  const { state: session, retry } = usePublicSession();
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : null;
  const localCommands = useTopicSaveCommands(owner), commands = sharedCommands ?? localCommands;
  const [data, setData] = useState<TopicSaveState | null>(null), [error, setError] = useState("");
  const [busy, setBusy] = useState(false), [unknown, setUnknown] = useState(() => commands.memory.current.get(topicId)?.owner === owner), [attempt, setAttempt] = useState(0);
  const command = useRef<AbortController | null>(null), epoch = useRef(0);
  useEffect(() => {
    const unsubscribe = subscribeToSessionChanges(() => {
      epoch.current += 1; command.current?.abort(); setData(null); setError(""); setBusy(false);
      setUnknown(Boolean(commands.memory.current.get(topicId))); setAttempt(value => value + 1);
    });
    return () => { epoch.current += 1; command.current?.abort(); unsubscribe(); };
  }, [commands.memory, topicId]);
  useEffect(() => {
    if (!owner) return;
    const controller = new AbortController();
    loadTopicSave(topicId, owner, controller.signal).then(result => {
      if (!controller.signal.aborted) { setData(result); setError(""); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "主题收藏未能读取。"); });
    return () => controller.abort();
  }, [owner, topicId, attempt]);
  const current = data?.owner_id === owner && data.topic_id === topicId ? data : null;

  async function toggle() {
    if (!owner || command.current) return;
    let operation = commands.memory.current.get(topicId);
    if (!operation || operation.owner !== owner) {
      if (!current) return;
      operation = { owner, input: { topic: topicId, saved: !current.saved, expected_version: current.version, request_id: createRequestKey() }, dispatched: false };
      commands.memory.current.set(topicId, operation); commands.changed();
    }
    const controller = new AbortController(), generation = epoch.current;
    command.current = controller; setBusy(true); setUnknown(true); setError("");
    try {
      let result: TopicSaveState | undefined;
      if (operation.dispatched) {
        try { result = await loadTopicSave(operation.input.topic, owner, controller.signal, operation.input.request_id); }
        catch (reason) {
          if (reason instanceof PrivateOwnerVerificationError || !(reason instanceof ApiRequestError) || reason.status !== 404) throw reason;
        }
      }
      result ??= await commandTopicSave(operation.input, owner, controller.signal, () => { operation.dispatched = true; });
      if (controller.signal.aborted || epoch.current !== generation) return;
      if (result.topic_id !== operation.input.topic || result.receipt?.request_id !== operation.input.request_id
        || result.receipt.applied_saved !== operation.input.saved || result.saved !== Boolean(result.record)) throw new Error("原收藏操作结果无法核对，请保留原请求。");
      commands.memory.current.delete(topicId); commands.changed(); setUnknown(false); setData(result); onChange?.(result.saved);
    } catch (reason) {
      if (epoch.current !== generation) return;
      const uncertain = reason instanceof PrivateOwnerVerificationError || !(reason instanceof ApiRequestError) || reason.status === 0 || reason.status >= 500 || [408, 429].includes(reason.status);
      if (!uncertain) { commands.memory.current.delete(topicId); commands.changed(); setUnknown(false); setData(null); setAttempt(value => value + 1); }
      setError(uncertain ? "收藏结果尚未确认。原请求已保留，请核对原操作。" : reason instanceof Error ? reason.message : "主题收藏未能保存。");
    } finally { if (command.current === controller) command.current = null; if (epoch.current === generation) setBusy(false); }
  }

  if (session.status === "unauthenticated") return <Link className="button secondary" href={`/login?next=${encodeURIComponent(typeof window === "undefined" ? "/topics" : window.location.pathname)}`}>收藏主题<Bookmark size={16} /></Link>;
  if (!owner) return <span><button className="button secondary" disabled>收藏主题<Bookmark size={16} /></button>{session.status !== "loading" ? <button onClick={retry}>重新验证登录</button> : null}</span>;
  const recovering = unknown && commands.memory.current.get(topicId)?.owner === owner;
  return <span><button className={`button secondary ${current?.saved ? "saved" : ""}`} type="button" aria-pressed={Boolean(current?.saved)}
    disabled={busy || !recovering && (!current || !current.saved && !current.can_save)} onClick={() => void toggle()}>
    {busy ? "正在保存…" : recovering ? "核对原收藏操作" : current?.saved ? "已收藏 · 取消收藏" : "收藏主题"}<Bookmark size={16} fill={current?.saved ? "currentColor" : "none"} />
  </button>{error ? <span role="alert">{error}{!recovering ? <button onClick={() => setAttempt(value => value + 1)}>重新读取</button> : null}</span> : null}</span>;
}
