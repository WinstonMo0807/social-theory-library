"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type FormEvent, type ReactNode } from "react";
import { ArrowRight, BookOpen, LoaderCircle, Search, Shuffle } from "lucide-react";
import { usePublicSession } from "@/components/public-session-provider";
import { ScholarPortrait } from "@/components/ui";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import type { Scholar, Work } from "@/lib/data";
import type { ApiWork } from "@/lib/api/public-catalog";
import type { LibraryTopic } from "@/lib/api/topics.types";
import type { HomeSection, HomeSections } from "@/lib/api/home.types";

function EmptyDiscovery({ section, children }: { section?: HomeSection; children: ReactNode }) {
  return <div className="stl4-home-state" role={section?.status === "unavailable" ? "alert" : "status"}><BookOpen size={24} strokeWidth={1} /><p>{section?.status === "unavailable" ? section.message : children}</p>{section?.status === "unavailable" ? <Link href="/">重新加载首页 <ArrowRight size={14} /></Link> : null}</div>;
}

export function HomeSearch() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = String(new FormData(event.currentTarget).get("q") ?? "").trim();
    if (!query) return;
    startTransition(() => router.push(`/explore?${new URLSearchParams({ context: "global", q: query })}`));
  }
  return <form action="/explore" className="stl4-home-search" role="search" aria-label="搜索书库" aria-busy={pending} onSubmit={submit}>
    <input type="hidden" name="context" value="global" />
    <label><Search size={19} aria-hidden="true" /><span className="sr-only">搜索书名、作者、概念或主题</span><input name="q" type="search" required autoComplete="off" placeholder="搜索书名、作者、概念、主题…" /></label>
    <button type="submit" disabled={pending}>{pending ? "搜索中…" : "搜索"}</button>
    {pending ? <span className="stl4-home-search-pending" role="status"><LoaderCircle size={16} aria-hidden="true" />正在打开检索结果，已保留输入内容。</span> : null}
  </form>;
}

export function HomeDiscoveryCards({ scholars, topics, sections }: { scholars: Scholar[]; topics: LibraryTopic[]; sections?: HomeSections }) {
  const [scholarOffset, setScholarOffset] = useState(0);
  const [topicOffset, setTopicOffset] = useState(0);
  const shownScholars = scholars.slice(scholarOffset).concat(scholars.slice(0, scholarOffset)).slice(0, 5);
  const shownTopics = topics.slice(topicOffset).concat(topics.slice(0, topicOffset)).slice(0, 5);
  const rotate = (count: number, current: number) => count < 2 ? 0 : (current + 1 + Math.floor(Math.random() * (count - 1))) % count;
  return <>
    <section className="stl4-home-section" data-edit-section="scholars" aria-labelledby="home-scholars">
      <header className="stl4-home-heading"><h2 id="home-scholars">学者聚焦 <small>Scholars</small></h2><div><button type="button" disabled={scholars.length < 2} onClick={() => setScholarOffset(current => rotate(scholars.length, current))}><Shuffle size={15} />随机推荐<span className="sr-only">学者</span></button><Link href="/scholars">查看全部 <ArrowRight size={15} /></Link></div></header>
      {shownScholars.length ? <div className="stl4-scholar-grid" aria-live="polite">{shownScholars.map(scholar => <Link href={`/scholars/${scholar.slug}`} key={scholar.slug} className="stl4-scholar-card"><ScholarPortrait scholar={scholar} /><div><h3>{scholar.name}</h3><p>{scholar.years}</p><p>{scholar.concerns.join("、") || scholar.school}</p><ArrowRight size={16} aria-hidden="true" /></div></Link>)}</div> : <EmptyDiscovery section={sections?.scholars}>尚无已发布学者档案。</EmptyDiscovery>}
    </section>
    <section className="stl4-home-section" data-edit-section="topics" aria-labelledby="home-topics">
      <header className="stl4-home-heading"><h2 id="home-topics">探索主题 <small>Topics</small></h2><div><button type="button" disabled={topics.length < 2} onClick={() => setTopicOffset(current => rotate(topics.length, current))}><Shuffle size={15} />随机推荐<span className="sr-only">主题</span></button><Link href="/topics">查看全部 <ArrowRight size={15} /></Link></div></header>
      {shownTopics.length ? <div className="stl4-topic-grid" aria-live="polite">{shownTopics.map(topic => <Link className="stl4-topic-card" href={`/topics/${topic.slug}`} key={topic.slug}>{topic.heroImage ? <img src={topic.heroImage} alt="" loading="lazy" /> : <div className="stl4-image-missing" aria-label="尚未提供主题配图"><BookOpen size={30} strokeWidth={1} /></div>}<div><h3>{topic.name}</h3><p>{topic.description}</p><ArrowRight size={16} aria-hidden="true" /></div></Link>)}</div> : <EmptyDiscovery section={sections?.topics}>尚无已发布主题。</EmptyDiscovery>}
    </section>
  </>;
}

export function HomeRandomBook({ works, section }: { works: Work[]; section?: HomeSection }) {
  const [index, setIndex] = useState<number | null>(null);
  const work = index === null ? null : works[index];
  return <section className="stl4-home-random" aria-label="随机荐读"><div><h2>{work?.title || "遇见一本好书"}</h2><p aria-live="polite">{work ? `${work.author} · ${work.year}` : section?.status === "unavailable" ? section.message : works.length ? "从已发布馆藏中，开始一次新的阅读。" : "馆藏发布后，即可随机发现一本书。"}</p></div><button type="button" disabled={!works.length} onClick={() => setIndex(current => current === null ? Math.floor(Math.random() * works.length) : works.length < 2 ? 0 : (current + 1 + Math.floor(Math.random() * (works.length - 1))) % works.length)}><Shuffle size={16} />{work ? "再换一本" : "随机推荐"}</button>{work ? <Link href={`/works/${work.slug}`}>查看馆藏 <ArrowRight size={16} /></Link> : null}</section>;
}

type ProgressRow = { id: string; asset: string; current_page: number; progress_ratio: number; updated_at?: string; work: ApiWork | null };
export function HomeContinueReading() {
  const { state: session } = usePublicSession();
  const userId = session.status === "authenticated" ? session.user?.id : undefined;
  const [result, setResult] = useState<{ owner: number; row?: ProgressRow; error?: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (userId === undefined) return;
    const controller = new AbortController();
    const unsubscribe = subscribeToSessionChanges(() => { controller.abort(); setResult(null); });
    apiRequest<{ results: ProgressRow[] }>("/reading/progress/", { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]), cache: "no-store" }, getServerSessionCredential(), false)
      .then(data => { if (!controller.signal.aborted) setResult({ owner: userId, row: data.results[0] }); })
      .catch(() => { if (!controller.signal.aborted) setResult({ owner: userId, error: "阅读进度暂时无法加载。" }); });
    return () => { controller.abort(); unsubscribe(); };
  }, [userId, attempt]);
  // Do not show the previous account's private row while a new session loads.
  if (userId === undefined || result?.owner !== userId || (!result.row && !result.error)) return null;
  if (result.error) return <aside className="stl4-continue" role="status"><p>{result.error}</p><button type="button" onClick={() => setAttempt(value => value + 1)}>重试</button></aside>;
  const row = result.row!;
  if (!row.work) return <aside className="stl4-continue"><p>上次阅读的来源当前不可用，阅读位置仍保留。</p><Link href="/account">查看读者中心</Link></aside>;
  return <aside className="stl4-continue"><span className="stl4-continue-cover">{row.work.cover ? <img src={row.work.cover} alt={`${row.work.title}封面`} width={44} height={64} /> : <BookOpen size={24} aria-label="尚未提供封面" />}</span><div><span>继续阅读 <small>仅本人可见</small></span><h2>{row.work.title}</h2><p>PDF 第 {row.current_page} 页 · 已读 {Math.round(Math.min(1, Math.max(0, row.progress_ratio)) * 100)}%{row.updated_at && Number.isFinite(Date.parse(row.updated_at)) ? <> · 上次阅读 <time dateTime={row.updated_at}>{new Date(row.updated_at).toLocaleDateString("zh-CN")}</time></> : null}</p></div><Link href={`/reader/${encodeURIComponent(row.asset)}?page=${row.current_page}`}>继续阅读 <ArrowRight size={16} /></Link></aside>;
}
