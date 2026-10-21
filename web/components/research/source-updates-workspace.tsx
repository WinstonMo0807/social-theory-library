"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bell, ChevronLeft, ChevronRight, History, RefreshCw, X } from "lucide-react";
import { subscribeToSessionChanges } from "@/lib/api";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { sourceDate, sourceFollowsPath, sourceStatusLabel, type SourceFollow, type SourceFollowsPage } from "@/lib/api/source-follows.client";
import { SourceFollowControl, useSourceFollowCommands, type SourceFollowCommands } from "@/components/public/source-follow-control";
import { SourceStatusSummary } from "@/components/public/support-source-status";
import { Dialog } from "@/components/ui/dialog";
import { ResearchCenterNav } from "./research-center-nav";
import styles from "./source-updates.module.css";

export function SourceUpdatesWorkspace() {
  const { state: session, retry } = useSessionBootstrap();
  const commands = useSourceFollowCommands(session.status === "authenticated" && session.user ? String(session.user.id) : null);
  const [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  if (session.status !== "authenticated" || !session.user) return <div className={styles.page}><h1>来源订阅</h1><p role="status">{session.message || (session.status === "unauthenticated" ? "登录后可以查看本人订阅的来源更新。" : "正在验证登录状态…")}</p>{session.status === "unauthenticated" ? <Link href="/login?next=%2Faccount%2Fsource-updates">登录后继续</Link> : session.status !== "loading" ? <button onClick={retry}>重新验证</button> : null}</div>;
  return <SourceUpdatesContent key={`${session.user.id}:${epoch}`} ownerId={String(session.user.id)} commands={commands} />;
}

function SourceUpdatesContent({ ownerId, commands }: { ownerId: string; commands: SourceFollowCommands }) {
  const [page, setPage] = useState(1), [historyId, setHistoryId] = useState<string | null>(null);
  const records = usePersistentWorkspace<SourceFollowsPage>(`${sourceFollowsPath}?page=${page}`, ownerId);
  const data = records.data;
  return <div className={styles.page}><div className={styles.breadcrumb}><Link href="/account">我的资料</Link><ChevronRight size={13} /><span>来源订阅</span></div>
    <header className={styles.header}><div><span>MY LIBRARY</span><h1>来源订阅</h1><p>查看来源与已关注学者的公开状态及正式更新。</p></div><Link href="/account/settings/privacy">隐私与资料</Link></header>
    <ResearchCenterNav active="sources" />
    <div className={styles.toolbar}><p>{data ? `共 ${data.count} 项来源记录` : "正在读取来源记录"}</p><button onClick={records.reload}><RefreshCw size={15} />刷新当前页</button></div>
    <p className={styles.notice}>{data?.notice || "订阅仅保存在本人账户中。不会自动发送邮件，也不会保存原文内容。"}</p>
    {records.error ? <p role="alert" className={styles.error}>{records.error}</p> : null}
    {records.loading ? <p role="status" className={styles.empty}>正在读取本人来源订阅…</p> : null}
    {data?.results.length === 0 ? <div className={styles.empty}><Bell size={30} /><h2>{data.count ? "本页没有来源记录" : "还没有订阅来源"}</h2><p>在来源说明中核对一份公开原文后，可以订阅它的更新。</p><Link href="/help/source">查看来源说明</Link></div> : null}
    <div className={styles.list}>{data?.results.map(row => <article key={row.id} className={styles.row} aria-label={row.source.title}>
      <div className={styles.rowHeading}><span>{row.active ? "正在订阅" : "已取消订阅"}{row.updates_paused ? " · 已暂停保存更新" : ""}</span>{row.unread_count ? <strong>{row.unread_count} 条未读更新</strong> : null}</div>
      <SourceStatusSummary source={row.source} />
      <p className={styles.quiet}>最近检查：{sourceDate(row.last_checked_at)}{row.check_error ? " · 上次检查未完成，保留既有记录；请刷新重试。" : ""}</p>
      <p className={styles.quiet}>{row.source.notice}</p>
      <div className={styles.rowActions}><SourceFollowControl key={`${ownerId}:${row.id}`} ownerId={ownerId} path={row.path} scholarProfileId={row.scholar_profile_id} commands={commands} row={row} canSubscribe={row.source.can_subscribe} onSaved={records.reload} onReload={records.reload} />
        <nav aria-label={`${row.source.title}相关操作`}><button onClick={() => setHistoryId(row.id)}><History size={15} />查看状态历史</button><Link href={`/help/source?source=${encodeURIComponent(row.path)}`}>来源说明</Link>{row.source.reader_url ? <Link href={row.source.reader_url}>打开当前原文</Link> : row.scholar_profile_id && row.source.href ? <Link href={row.source.href}>查看学者档案</Link> : null}</nav></div>
    </article>)}</div>
    {data ? Array.from(commands.memory.current.entries()).filter(([, operation]) => operation.owner === ownerId && !data.results.some(row => operation.input.scholar_profile_id ? row.scholar_profile_id === operation.input.scholar_profile_id : row.path === operation.input.path)).map(([key, operation]) => <section key={key} className={styles.notice}><p>有一项原操作尚待核对，相关记录可能已移到其他页或被删除。</p><SourceFollowControl ownerId={ownerId} path={operation.input.path} scholarProfileId={operation.input.scholar_profile_id} row={null} canSubscribe={false} commands={commands} onSaved={records.reload} onReload={records.reload} /></section>) : null}
    {data && data.count > data.page_size ? <nav className={styles.pagination} aria-label="来源订阅分页"><button disabled={page === 1} onClick={() => setPage(value => value - 1)}><ChevronLeft size={15} />上一页</button><span>第 {page} 页 / 共 {Math.ceil(data.count / data.page_size)} 页</span><button disabled={page * data.page_size >= data.count} onClick={() => setPage(value => value + 1)}>下一页<ChevronRight size={15} /></button></nav> : null}
    {historyId ? <SourceHistory key={historyId} id={historyId} ownerId={ownerId} onClose={() => setHistoryId(null)} /> : null}
  </div>;
}

function SourceHistory({ id, ownerId, onClose }: { id: string; ownerId: string; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const workspace = usePersistentWorkspace<SourceFollow>(`${sourceFollowsPath}${encodeURIComponent(id)}/?history_page=${page}`, ownerId);
  const row = workspace.data;
  const status = (value: string) => sourceStatusLabel[value as keyof typeof sourceStatusLabel] || "未记录";
  return <Dialog open onRequestClose={onClose} className={styles.dialog} aria-labelledby="source-history-title"><header><h2 id="source-history-title">来源状态历史</h2><button aria-label="关闭来源历史" onClick={onClose}><X size={20} /></button></header>
    <p>记录每次实际观察到的状态变化，不表示状态变化的精确发生时间。</p>
    {workspace.error ? <p role="alert">{workspace.error}<button onClick={workspace.reload}>重新读取</button></p> : null}
    {workspace.loading ? <p role="status">正在读取历史…</p> : null}
    {row ? <><h3>{row.source.title}</h3><ol>{row.history.results.map(event => <li key={event.id}><div><strong>{{ subscribe: "订阅来源更新", unsubscribe: "取消订阅", mark_read: "标记为已读", changed: "观察到来源变化", delete: "删除关注记录" }[event.action]}</strong><time dateTime={event.observed_at}>{sourceDate(event.observed_at)}</time></div>{event.action === "changed" ? <p>{event.before_status === event.after_status ? `公开资料或正式版本已更新，当前状态：${status(event.after_status)}` : `${status(event.before_status)} → ${status(event.after_status)}`}</p> : null}</li>)}</ol>
      {row.history.count > row.history.page_size ? <nav className={styles.pagination} aria-label="状态历史分页"><button disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页</span><button disabled={page * row.history.page_size >= row.history.count} onClick={() => setPage(value => value + 1)}>下一页</button></nav> : null}</> : null}
    <footer><button onClick={onClose}>关闭</button></footer>
  </Dialog>;
}
