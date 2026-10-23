"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Bell, CircleAlert, FileText, RefreshCw } from "lucide-react";
import { normalizePublicResourceUrl } from "@/lib/api";
import { safeFeedbackPath, feedbackPathFromInput } from "@/lib/api/feedback.client";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { sourceDate, sourceFollowsPath, sourceStatusLabel, type PublicSourceStatus, type SourceFollowsPage } from "@/lib/api/source-follows.client";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { usePublicSource } from "./feedback-source-card";
import { SourceFollowControl, useSourceFollowCommands } from "./source-follow-control";
import styles from "./source-status.module.css";

export function SupportSourceStatus({ source }: { source: string }) {
  const router = useRouter(), [inputError, setInputError] = useState("");
  const path = safeFeedbackPath(source), current = usePublicSource(path);
  return <section className={styles.status} aria-label="核对公开来源"><h2>来源信息</h2>
    <p>本页面显示当前内容的来源与公开状态，帮助你判断可用性。</p>
    <form onSubmit={event => {
      event.preventDefault();
      const next = feedbackPathFromInput(String(new FormData(event.currentTarget).get("source") || ""), window.location.origin);
      if (!next) { setInputError("请粘贴本站公开页面地址或路径，不支持账户资料、后台或外部链接。"); return; }
      setInputError(""); router.push(`/help/source?${new URLSearchParams({ source: next })}`);
    }}><label>站内原文、书目、学者或主题页面地址<input name="source" key={path} defaultValue={path} maxLength={2048} placeholder="粘贴页面地址，或 /reader/文件标识?page=88" /></label><button type="submit">读取来源信息</button></form>
    {inputError ? <p role="alert">{inputError}</p> : null}
    {source && !path ? <p role="alert">请输入站内公开页面路径。不会读取账户资料或外部链接。</p> : null}
    {current.loading ? <p role="status">正在核对公开来源…</p> : null}
    {current.error ? <div role="alert"><p>当前无法读取来源状态。未据此判断来源已经失效。</p><p>{current.error}</p><button onClick={current.reload}><RefreshCw size={15} />重新读取</button></div> : null}
    {current.source ? <><SourceStatusSummary source={current.source} />
      <div className={styles.notice}><CircleAlert size={22} aria-hidden="true" /><p>{current.source.notice}{current.source.status === "unavailable" ? " 来源尚未恢复时，请勿使用旧片段生成新的正式引用。" : ""}</p></div>
      <div className={styles.footer}>{current.source.reader_url ? <Link className={styles.primary} href={current.source.reader_url + (current.source.status === "available" ? new URL(path, "https://library.invalid").search : "")}>打开当前原文</Link> : null}
        {current.source.scholar_profile_id && current.source.href ? <Link className={styles.primary} href={current.source.href}>查看学者档案</Link> : null}
        {current.source.topic_id && current.source.href ? <Link className={styles.primary} href={current.source.href}>查看主题档案</Link> : null}
        <Link className={styles.primary} href={`/feedback?category=content&path=${encodeURIComponent(path)}`}>提交来源纠错</Link>
        <button onClick={current.reload}><RefreshCw size={15} />重新读取</button>
      </div>
      {/^\/(?:reader|works|scholars|topics)\/[^/]+$/.test(current.source.canonical_path) ? <SourceSubscription source={current.source} /> : null}
    </> : !path ? <p>关联一份公开原文或书目后，显示本次核对结果。</p> : null}
  </section>;
}

export function SourceStatusSummary({ source }: { source: PublicSourceStatus }) {
  return <div className={styles.summary}>{source.cover_url ? <img src={normalizePublicResourceUrl(source.cover_url)} alt={`${source.title}${source.scholar_profile_id ? "肖像" : "封面"}`} width={92} height={134} /> : <div className={styles.noCover}><FileText size={38} aria-hidden="true" /></div>}
    <div><h3>{source.title}</h3>{source.authors.length ? <p>{source.authors.join("、")}</p> : null}<dl>
      <div><dt>来源类型</dt><dd>{source.source_type || "尚未核对"}{source.version_label ? ` · ${source.version_label}` : ""}</dd></div>
      <div><dt>来源状态</dt><dd data-state={source.status}>{sourceStatusLabel[source.status]}</dd></div>
      {source.location ? <div><dt>原文位置</dt><dd>{source.location}</dd></div> : null}
      <div><dt>更新时间</dt><dd>{sourceDate(source.updated_at)}</dd></div>
      <div><dt>核对时间</dt><dd>{sourceDate(source.checked_at)}</dd></div>
    </dl></div>
  </div>;
}

function SourceSubscription({ source }: { source: PublicSourceStatus }) {
  const { state: session, retry } = useSessionBootstrap();
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : null;
  const commands = useSourceFollowCommands(owner);
  const selector = source.scholar_profile_id ? `scholar_profile_id=${encodeURIComponent(source.scholar_profile_id)}` : source.topic_id ? `topic_id=${encodeURIComponent(source.topic_id)}` : `path=${encodeURIComponent(source.canonical_path)}`;
  const records = usePersistentWorkspace<SourceFollowsPage>(`${sourceFollowsPath}?${selector}`, owner);
  const row = records.data?.results[0] ?? null;
  if (session.status === "unauthenticated") return <div className={styles.subscription}><Link href={`/login?next=${encodeURIComponent(`/help/source?source=${encodeURIComponent(source.path)}`)}`}><Bell size={16} />登录后订阅更新</Link><p>订阅保存在本人账户中，仅提供站内更新。</p></div>;
  if (!owner) return <div className={styles.subscription}><p>{session.message || "正在核对登录状态…"}</p>{session.status !== "loading" ? <button onClick={retry}>重新验证</button> : null}</div>;
  return <div className={styles.subscription}>{records.error ? <p role="alert">{records.error}<button onClick={records.reload}>重新读取订阅</button></p> : null}
    {records.loading ? <p role="status">正在读取本人订阅…</p> : null}
    {records.data ? <><SourceFollowControl key={`${owner}:${source.scholar_profile_id || source.topic_id || source.canonical_path}`} ownerId={owner} path={source.canonical_path} scholarProfileId={source.scholar_profile_id} topicId={source.topic_id} commands={commands} row={row} canSubscribe={source.can_subscribe} onSaved={records.reload} onReload={records.reload} />
      {row?.updates_paused ? <p>来源更新记录已在隐私设置中暂停。已有记录仍保留。</p> : null}
      {!row && !source.can_subscribe ? <p>当前不能核对公开来源身份，暂不能新增订阅。</p> : null}
      <p>更新仅保存在站内，<Link href="/account/source-updates">查看来源订阅</Link>。可在<Link href="/account/settings/privacy">隐私与资料</Link>中管理保存、导出与删除。</p></> : null}
  </div>;
}
