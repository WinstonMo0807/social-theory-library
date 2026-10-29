"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { Bell, BellOff, Check, RefreshCw } from "lucide-react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { commandSourceFollow, findSourceFollowReceipt, loadPublicSource, loadSourceFollows, type SourceCommand, type SourceFollow, type PublicSourceStatus } from "@/lib/api/source-follows.client";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { usePublicSession } from "@/components/public-session-provider";
import styles from "./source-status.module.css";

type PendingCommand = { owner: string; input: SourceCommand; dispatched: boolean };
export type SourceFollowCommands = { memory: RefObject<Map<string, PendingCommand>>; changed: () => void };
const commandKey = (path: string, profile?: string | null, topic?: string | null) => profile ? `scholar:${profile}` : topic ? `topic:${topic}` : path;

/** Keep only command identities in memory, above session-driven child remounts. */
export function useSourceFollowCommands(owner?: string | null): SourceFollowCommands {
  const memory = useRef(new Map<string, PendingCommand>());
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

export function SourceFollowControl({ ownerId, path, scholarProfileId, topicId, row, canSubscribe, onSaved, onReload, commands, className }: {
  ownerId: string; path: string; scholarProfileId?: string | null; topicId?: string | null; row: SourceFollow | null; canSubscribe: boolean;
  onSaved: (row: SourceFollow | null) => void; onReload: () => void; commands: SourceFollowCommands; className?: string;
}) {
  const key = commandKey(path, scholarProfileId, topicId);
  const [state, setState] = useState<"idle" | "pending" | "unknown">(() => commands.memory.current.get(key)?.owner === ownerId ? "unknown" : "idle");
  const [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null), epoch = useRef(0);
  useEffect(() => {
    epoch.current += 1;
    const unsubscribe = subscribeToSessionChanges(() => {
      epoch.current += 1; controller.current?.abort();
      if (commands.memory.current.get(key)?.owner === ownerId) {
        setState("unknown"); setMessage("登录状态正在重新核验。原操作仍保留，请核对原操作后再继续。");
      }
    });
    return () => { epoch.current += 1; controller.current?.abort(); unsubscribe(); };
  }, [ownerId, key, commands.memory]);
  async function execute(action?: SourceCommand["action"]) {
    if (controller.current) return;
    let pending = commands.memory.current.get(key);
    if (pending?.owner !== ownerId) pending = undefined;
    if (!pending && action) {
      pending = { owner: ownerId, dispatched: false, input: { path, ...(scholarProfileId ? { scholar_profile_id: scholarProfileId } : {}), ...(topicId ? { topic_id: topicId } : {}), action, expected_revision: row?.revision ?? 0, request_id: createRequestKey() } };
      commands.memory.current.set(key, pending); commands.changed();
    }
    if (!pending) return;
    const operation = pending, input = operation.input;
    const request = new AbortController(), version = epoch.current;
    controller.current = request; setState("pending"); setMessage("");
    try {
      let result;
      if (operation.dispatched) {
        try { result = await findSourceFollowReceipt(input.request_id, ownerId, request.signal); }
        catch (reason) {
          // Only a verified missing receipt permits replay of this exact nonce.
          if (reason instanceof PrivateOwnerVerificationError || !(reason instanceof ApiRequestError) || reason.status !== 404) throw reason;
        }
      }
      result ??= await commandSourceFollow(input, ownerId, request.signal, () => { operation.dispatched = true; });
      if (request.signal.aborted || epoch.current !== version) return;
      const current = result.record;
      if (result.receipt.request_id !== input.request_id || result.receipt.deleted !== (current === null)
        || current && (current.owner_id !== ownerId || (input.scholar_profile_id ? current.scholar_profile_id !== input.scholar_profile_id : input.topic_id ? current.topic_id !== input.topic_id : current.path !== input.path))) {
        throw new Error("暂未查到操作结果，请保留请求编号后重试。");
      }
      commands.memory.current.delete(key); commands.changed(); setState("idle"); onSaved(current);
      setMessage(result.receipt.deleted ? "原操作已处理，记录随后已删除。不会重新建立关注。" : input.action === "subscribe" ? "已保存关注，可在我的资料中查看更新。" : input.action === "unsubscribe" ? "已取消关注，已有记录保留。" : "已将当前更新标记为已读。");
    } catch (reason) {
      if (epoch.current !== version) return;
      const uncertain = reason instanceof PrivateOwnerVerificationError || !(reason instanceof ApiRequestError) || reason.status === 0 || reason.status >= 500 || [408, 429].includes(reason.status);
      setState(uncertain ? "unknown" : "idle");
      if (!uncertain) { commands.memory.current.delete(key); commands.changed(); }
      setMessage(uncertain ? "尚未确认操作结果。原请求已保留，请核对原操作，避免重复关注或取消。" : reason instanceof Error ? reason.message : "操作尚未完成，请重试。");
      if (reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403, 409].includes(reason.status)) onReload();
    } finally { if (controller.current === request) controller.current = null; }
  }
  const disabled = state !== "idle", entity = !!(scholarProfileId || topicId);
  return <div className={styles.controls}>
    <div className={styles.actions}>
      {row?.active ? <button className={className} disabled={disabled} onClick={() => void execute("unsubscribe")}><BellOff size={16} />{entity ? "已关注 · 取消关注" : "取消订阅"}</button>
        : <button className={className} disabled={disabled || !canSubscribe} onClick={() => void execute("subscribe")}><Bell size={16} />{scholarProfileId ? "关注学者" : topicId ? "关注主题" : row ? "重新订阅更新" : "订阅更新"}</button>}
      {row && row.unread_count > 0 ? <button disabled={disabled} onClick={() => void execute("mark_read")}><Check size={16} />标为已读</button> : null}
      {state === "unknown" ? <button onClick={() => void execute()}><RefreshCw size={15} />核对原操作</button> : null}
      {state === "pending" ? <span role="status">正在保存…</span> : null}
    </div>
    {message ? <p role={state === "unknown" ? "alert" : "status"}>{message}</p> : null}
  </div>;
}

export function ScholarFollowButton(props: { profileId: string; href: string; className?: string; preview?: boolean }) {
  if (props.preview) return <button className={props.className} disabled title="管理预览不执行私人关注"><Bell size={16} />关注学者</button>;
  return <EntityFollowAction {...props} kind="scholar" entityId={props.profileId} />;
}

export function TopicFollowButton(props: { topicId: string; href: string; className?: string; preview?: boolean }) {
  if (props.preview) return <button className={props.className} disabled title="管理预览不执行私人关注"><Bell size={16} />关注主题</button>;
  return <EntityFollowAction {...props} kind="topic" entityId={props.topicId} />;
}

function EntityFollowAction({ kind, entityId, href, className }: { kind: "scholar" | "topic"; entityId: string; href: string; className?: string }) {
  const { state: session, retry } = usePublicSession();
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : null;
  const commands = useSourceFollowCommands(owner);
  const identity = `${kind}:${entityId}`, label = kind === "topic" ? "关注主题" : "关注学者";
  const [data, setData] = useState<{ owner: string; identity: string; attempt: number; row: SourceFollow | null; source: PublicSourceStatus } | null>(null);
  const [error, setError] = useState(""), [attempt, setAttempt] = useState(0);
  const reload = () => { setError(""); setAttempt(value => value + 1); };
  useEffect(() => {
    if (!owner) return;
    const controller = new AbortController(), unsubscribe = subscribeToSessionChanges(() => { controller.abort(); setData(null); setError(""); });
    const selector = { [kind === "topic" ? "topic_id" : "scholar_profile_id"]: entityId };
    Promise.all([loadPublicSource(href, controller.signal, kind === "scholar" ? entityId : undefined, kind === "topic" ? entityId : undefined), loadSourceFollows(owner, controller.signal, selector)])
      .then(([source, page]) => { if (!controller.signal.aborted) setData({ owner, identity, attempt, row: page.results[0] ?? null, source }); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "关注状态未能读取。"); });
    return () => { controller.abort(); unsubscribe(); };
  }, [owner, kind, entityId, identity, href, attempt]);
  if (session.status === "unauthenticated") return <Link className={className} href={`/login?next=${encodeURIComponent(href)}`}><Bell size={16} />{label}</Link>;
  if (!owner) return <div><button className={className} disabled><Bell size={16} />{label}</button>{session.status !== "loading" ? <button onClick={retry}>重新验证登录</button> : null}</div>;
  const current = data?.owner === owner && data.identity === identity && data.attempt === attempt ? data : null;
  return <div>{current ? <SourceFollowControl key={`${owner}:${identity}`} ownerId={owner} path={current.source.canonical_path || href} scholarProfileId={kind === "scholar" ? entityId : undefined} topicId={kind === "topic" ? entityId : undefined}
    row={current.row} canSubscribe={current.source.can_subscribe} commands={commands} className={className} onSaved={reload} onReload={reload} />
    : <button className={className} disabled><Bell size={16} />正在读取关注…</button>}
    {error ? <p role="alert">{error}<button onClick={reload}>重新读取</button></p> : null}
  </div>;
}
