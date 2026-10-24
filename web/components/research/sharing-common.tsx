"use client";
import { MediaPlacement } from "@/components/media-placement";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { sectionLabels, type ShareContent, type SharePreview } from "@/lib/api/sharing.client";
import { ResearchCenterNav } from "./research-center-nav";
import styles from "./sharing.module.css";

export function SharingAccount({ children, next }: { children: (owner: string, capabilities: string[]) => ReactNode; next: string }) {
  const { state, retry } = useSessionBootstrap();
  const [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  useEffect(() => { if (state.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(next)}`); }, [state.status, next]);
  if (state.status !== "authenticated" || !state.user) return <main className={styles.page}><h1>分享与小组</h1><p role="status">{state.message || "正在核对登录状态…"}</p>{["temporary_error", "forbidden"].includes(state.status) ? <button onClick={retry}>重新核对登录</button> : null}</main>;
  return <main className={styles.page} key={`${state.user.id}:${epoch}`}><ResearchCenterNav active="sharing" /><nav className={styles.subnav} aria-label="协作与隐私"><Link href="/account/sharing">分享记录</Link><Link href="/account/groups">我的小组</Link><Link href="/account/settings/privacy">隐私与资料</Link></nav>{children(String(state.user.id), state.user.capabilities || [])}</main>;
}

export function useSharingAction(owner: string) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [invalid, setInvalid] = useState(false);
  const controller = useRef<AbortController | null>(null), sending = useRef(false);
  useEffect(() => {
    const abort = new AbortController(); controller.current = abort;
    const off = subscribeToSessionChanges(() => abort.abort());
    return () => { abort.abort(); off(); };
  }, [owner]);
  async function run<T>(action: (signal: AbortSignal) => Promise<T>, done: (value: T) => void, failed?: (reason: unknown) => void) {
    const signal = controller.current?.signal;
    if (sending.current || !signal || signal.aborted) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      const result = await withPrivateOwner(owner, () => action(signal), signal);
      if (!signal.aborted) done(result);
    } catch (reason) {
      if (!signal.aborted) {
        if (reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403].includes(reason.status)) setInvalid(true);
        setMessage(reason instanceof Error ? reason.message : "操作没有完成，请保留输入后重试。"); failed?.(reason);
      }
    } finally { sending.current = false; if (!signal.aborted) setBusy(false); }
  }
  return { busy, message, setMessage, invalid, run };
}

export function SharingPagination({ page, total, disabled, onPage }: { page: number; total: number; disabled?: boolean; onPage: (page: number) => void }) {
  if (total <= 1) return null;
  return <nav className={styles.pagination} aria-label="分页"><button disabled={disabled || page <= 1} onClick={() => onPage(page - 1)}>上一页</button><span>{page}/{total}</span><button disabled={disabled || page >= total} onClick={() => onPage(page + 1)}>下一页</button></nav>;
}

export function SharedSummary({ value, showTitle = true }: { value: Pick<ShareContent | SharePreview, "source" | "sections" | "message" | "excluded">; showTitle?: boolean }) {
  return <div className={styles.summary}>{showTitle ? <h2>{value.source.title}</h2> : null}{(Object.keys(sectionLabels) as Array<keyof typeof sectionLabels>).map(section => value.sections[section].length ? <section key={section}><h3>{sectionLabels[section]} <small>{value.sections[section].length} 项</small></h3>{value.sections[section].map((item, index) => {
    const cover = typeof item.work?.cover_url === "string" ? item.work.cover_url : null;
    const reader = typeof item.reference?.reader_url === "string" ? item.reference.reader_url : null;
    const citation = typeof item.reference?.citation === "string" ? item.reference.citation : null;
    return <article key={index}>{cover ? <MediaPlacement uses={item.work?.cover_media?.display_uses} fallback={null}><Image unoptimized width={48} height={68} src={cover} alt="文献封面" /></MediaPlacement> : null}<div><strong>{item.title}</strong>{item.text ? <p>{item.text}</p> : <p className={styles.muted}>分享书目信息，原文请从书库访问。</p>}{item.truncated ? <small>只包含此处显示的前 2000 字。</small> : null}{item.tags?.length ? <small>{item.tags.join(" · ")}</small> : null}{citation ? <small>{citation}</small> : null}{reader ? <Link href={reader}>查看公开原文</Link> : typeof item.work?.href === "string" ? <Link href={item.work.href}>查看公开书目</Link> : null}</div></article>;
  })}</section> : null)}{value.message ? <section><h3>附言</h3><p>{value.message}</p></section> : null}<p className={styles.muted}>不包含：{value.excluded.join("、")}。</p></div>;
}
