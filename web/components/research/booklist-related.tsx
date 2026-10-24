"use client";

import Link from "next/link";
import Image from "next/image";
import { UserRound } from "lucide-react";
import { useCallback, useState } from "react";
import { MediaPlacement } from "@/components/media-placement";
import { booklistRequest, type BooklistPublicLink, type BooklistRelated, type BooklistRelatedSection, type BooklistSummary } from "@/lib/api/booklists.client";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import styles from "./reader-booklists.module.css";

const titles = { plans: "阅读计划", notes: "笔记与书签", topics: "相关主题", scholars: "相关学者" };
const states: Record<string, string> = { pending: "待阅读", reading: "阅读中", completed: "已完成", archived: "已归档" };
type TopicActions = { busy: boolean; onAddTopic: () => void; onRemoveTopic: (id: string) => void };

export function BooklistLinkedPanel({ owner, row, view, onRefresh, ...topics }: { onRefresh: () => void; owner: string; row: BooklistSummary; view: "plans" | "notes" | "related" } & TopicActions) {
  if (view === "related") return <div className={styles.linkedColumns}>
    <RelatedSection key={`topics:${row.version}`} owner={owner} row={row} onRefresh={onRefresh} section="topics" {...topics} />
    <RelatedSection key={`scholars:${row.version}`} owner={owner} row={row} onRefresh={onRefresh} section="scholars" />
  </div>;
  return <RelatedSection key={`${view}:${row.version}`} owner={owner} row={row} onRefresh={onRefresh} section={view} />;
}

export function BooklistPublicSidebar({ owner, row, onMore, onRefresh, ...topics }: { onRefresh: () => void; owner: string; row: BooklistSummary; onMore: () => void } & TopicActions) {
  return <><RelatedSection key={`topics:${row.version}`} owner={owner} row={row} onRefresh={onRefresh} section="topics" compact onMore={onMore} {...topics} />
    <RelatedSection key={`scholars:${row.version}`} owner={owner} row={row} onRefresh={onRefresh} section="scholars" compact onMore={onMore} /></>;
}

function RelatedSection({ owner, row, section, compact = false, onMore, onRefresh, busy, onAddTopic, onRemoveTopic }: {
  owner: string; row: BooklistSummary; section: BooklistRelatedSection; compact?: boolean; onMore?: () => void; onRefresh: () => void;
} & Partial<TopicActions>) {
  const [page, setPage] = useState(1);
  const query = new URLSearchParams({ expected_version: row.version, section, page: String(page) });
  const load = useCallback(async (path: string, signal: AbortSignal) => {
    const value = await booklistRequest<BooklistRelated>(owner, path, { signal });
    if (value.owner_id !== owner || value.list_id !== row.id || value.version !== row.version || value.section !== section)
      throw new Error("关联内容与当前书单不符，请重新读取书单。");
    return value;
  }, [owner, row.id, row.version, section]);
  const resource = usePersistentWorkspace(`/reading/lists/${row.id}/related/?${query}`, owner, undefined, load);
  const data = resource.error ? null : resource.data;
  const entries = data ? section === "topics" ? data.topics : section === "scholars" ? data.scholars : [] : [];
  const noteHref = (category: string, id: string) => `/account/notes?${new URLSearchParams({ booklist: row.id, category, record: id })}`;
  return <section className={styles.linkedSection} aria-label={titles[section]}>
    <h2>{titles[section]}{data ? <small>{data.count}</small> : null}{section === "topics" && onAddTopic ? <button disabled={busy} onClick={onAddTopic}>添加</button> : null}{compact && data && data.count > 3 ? <button onClick={onMore}>查看全部 →</button> : null}</h2>
    {resource.error ? <div role="alert" className={styles.notice}><p>{resource.error}</p><button onClick={() => { setPage(1); resource.reload(); onRefresh(); }}>重新读取</button></div>
      : !data ? <p role="status" className={styles.hint}>正在读取{titles[section]}…</p>
      : <>
        {!compact ? <p className={styles.hint}>{data.notice}</p> : null}
        {data.count === 0 ? <p className={styles.hint}>{section === "plans" ? "还没有从本书单生成阅读计划。" : section === "notes" ? "这些作品下还没有本人的笔记或书签。" : section === "topics" ? "当前公开版本还没有关联主题。" : "当前公开署名还没有可访问的学者档案。"}</p> : null}
        {section === "plans" ? <div className={styles.linkedRows}>{data.plans.map(plan => <article key={plan.id}>
          <h3><Link href={plan.href}>{plan.title}</Link></h3><p>{states[plan.status] || "状态待核对"} · 更新于 {new Date(plan.updated_at).toLocaleDateString("zh-CN")}</p><Link href={plan.href}>打开阅读计划 →</Link>
        </article>)}</div> : null}
        {section === "notes" ? <div className={styles.linkedRows}>{data.notes.map(note => <article key={note.key}>
          <small>{note.kind === "bookmark" ? "书签" : note.kind === "note" ? "笔记" : "摘录"} · PDF 第 {note.pdf_page} 页</small>
          <h3><Link href={noteHref(note.category, note.id)}>{note.work.title}</Link></h3>
          <p className={styles.noteExcerpt}>{(note.kind === "bookmark" ? note.label : note.body || note.saved_quote).slice(0, 240) || "尚未填写文字"}</p>
          {note.notice ? <p className={styles.hint}>{note.notice}</p> : null}<Link href={noteHref(note.category, note.id)}>查看与编辑 →</Link>
        </article>)}</div> : null}
        {entries.length ? <div className={section === "topics" ? styles.topicLinks : styles.scholarLinks}>{(compact ? entries.slice(0, 3) : entries).map(entry => <RelatedLink key={entry.id} entry={entry} scholar={section === "scholars"} compact={compact} busy={busy} onRemove={onRemoveTopic} />)}</div> : null}
        {!compact && data.total_pages > 1 ? <nav className={styles.paging} aria-label={`${titles[section]}分页`}><button disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>{data.page} / {data.total_pages}</span><button disabled={page >= data.total_pages} onClick={() => setPage(value => value + 1)}>下一页</button></nav> : null}
        {!compact && section === "notes" ? <Link className={styles.linkedMore} href={`/account/notes?booklist=${row.id}`}>在笔记工作台管理这些记录 →</Link> : null}
        {!compact && section === "plans" ? <Link className={styles.linkedMore} href="/account/plans">我的全部阅读计划 →</Link> : null}
      </>}
  </section>;
}

function RelatedLink({ entry, scholar, compact, busy, onRemove }: { entry: BooklistPublicLink; scholar: boolean; compact: boolean; busy?: boolean; onRemove?: (id: string) => void }) {
  const body = <>{scholar ? entry.portrait_url ? <MediaPlacement uses={entry.portrait_media?.display_uses} fallback={<UserRound aria-hidden size={32} />}><Image src={entry.portrait_url} alt="" width={48} height={56} unoptimized /></MediaPlacement> : <UserRound aria-hidden size={32} /> : null}
    <span><strong>{entry.title}</strong>{!compact && entry.description ? <span>{entry.description.slice(0, 240)}</span> : null}<small>{entry.selected ? "本人关联" : ""}{entry.selected && entry.source_count ? " · " : ""}{entry.source_count ? `${entry.source_count} 部书单作品` : ""}</small></span></>;
  return <div className={styles.publicLink}>{entry.href ? <Link className={styles.linkBody} href={entry.href}>{body}</Link> : <span className={styles.linkBody}>{body}</span>}
    {entry.selected && onRemove ? <button disabled={busy} aria-label={`移除${entry.title}的本人关联`} onClick={() => onRemove(entry.id)}>移除</button> : null}</div>;
}
