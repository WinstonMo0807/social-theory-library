"use client";

import Link from "next/link";
import { MediaPlacement } from "@/components/media-placement";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Bookmark, ChevronDown, ListOrdered, Search, Tag, Users } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { pathDifficultyLabels, readingPathHref, readingPathsHref, type ReadingPathFilters, type ReadingPathPage } from "@/lib/api/reading-paths.types";
import styles from "./reading-path.module.css";

export function ReadingPathList({ result, filters, error }: { result: ReadingPathPage | null; filters: ReadingPathFilters; error: string }) {
  const page = Math.max(1, Number(filters.page) || 1);
  return <main className={styles.page}>
    <header className={`${styles.hero} ${styles.listHero}`}><div><nav aria-label="面包屑"><Link href="/">首页</Link><span>›</span><Link href="/theories">探索</Link><span>›</span><span>阅读路径</span></nav><h1>选择一条阅读路径</h1><p className={styles.heroLead}>从问题和基础出发，按阶段阅读原典。</p><p>这些路径由社会理论的核心议题出发，<br />按照清晰的阶段，带你读关键作品，建立基本理解。</p></div><img src="/visual/stl4/reading-paths/list-hero.webp" alt="" width={546} height={143} /></header>
    <form className={styles.listFilters} action="/theories/reading-paths" method="get" aria-label="筛选阅读路径">
      <label className={styles.search}><Search size={19} /><input name="q" defaultValue={filters.q || ""} placeholder="搜索阅读路径（如：国家、民主、现代性…）" aria-label="搜索阅读路径" maxLength={300} /><button type="submit" aria-label="搜索路径"><ArrowRight size={17} /></button></label>
      <PathTopicPicker value={filters.topic || ""} known={result?.results.flatMap(row => row.topics) || []} />
      <label className={styles.difficulty}><Users size={22} /><span>阅读基础<select name="difficulty" defaultValue={filters.difficulty || ""}><option value="">全部基础</option>{Object.entries(pathDifficultyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></span></label>
      {filters.node ? <input type="hidden" name="node" value={filters.node} /> : null}{filters.discipline ? <input type="hidden" name="discipline" value={filters.discipline} /> : null}
      <button className={styles.primaryButton} type="submit">应用筛选</button>
    </form>
    {(filters.topic || filters.difficulty || filters.node || filters.discipline || filters.q) ? <p className={styles.filterNotice}>已应用选择的阅读范围<Link href="/theories/reading-paths">清空筛选</Link></p> : null}
    {error ? <section className={styles.error} role="alert"><h2>阅读路径暂时无法读取</h2><p>{error}</p><button type="button" onClick={() => window.location.reload()}>重试读取</button></section> : result ? <>
      <div className={styles.listSummary}><strong>共 {result.count} 条阅读路径</strong><span>公共路径，任何人可浏览。</span></div>
      {result.results.length ? <div className={styles.pathList}>{result.results.map(path => <article className={styles.pathRow} key={path.id}>
        <Link href={readingPathHref(path)} className={styles.pathImage} aria-label={`查看${path.title}`}>{path.cover_url ? <MediaPlacement uses={path.cover_media?.display_uses}><img src={path.cover_url} alt="" /></MediaPlacement> : <img src="/visual/stl4/reading-paths/detail-hero.webp" alt="" />}</Link>
        <div className={styles.pathCopy}><h2><Link href={readingPathHref(path)}>{path.title}</Link></h2>{path.introduction ? <p>{path.introduction}</p> : null}<div className={styles.tags}>{path.topics.map(topic => <Link href={readingPathsHref({}, { topic: topic.slug })} key={topic.id}>{topic.title}</Link>)}</div></div>
        <dl className={styles.pathMeta}><div><ListOrdered size={20} /><dt>{path.counts.stages} 个阶段</dt><dd>{path.estimated_reading || (path.estimated_weeks ? `约 ${path.estimated_weeks} 周` : "阅读时间尚未填写")}</dd></div><div><Users size={20} /><dt>{path.audience || pathDifficultyLabels[path.difficulty] || "读者基础尚未填写"}</dt><dd>{path.prerequisite || "先修要求尚未填写"}</dd></div></dl>
        <div className={styles.pathActions}><Link className={styles.primaryButton} href={readingPathHref(path)}>查看路径<ArrowRight size={15} /></Link><Link className={styles.outlineButton} href={`${readingPathHref(path)}?action=copy-plan`}><Bookmark size={15} />保存为我的计划</Link><small>登录后可保存</small></div>
      </article>)}</div> : <section className={styles.empty}><ListOrdered size={28} /><h2>没有符合条件的公开阅读路径</h2><p>试试其他主题、阅读基础或关键词。</p><Link href="/theories/reading-paths">查看全部路径</Link></section>}
      {(result.previous || result.next) ? <nav className={styles.pagination} aria-label="阅读路径分页">{result.previous ? <Link href={readingPathsHref(filters, { page: page - 1 })}>上一页</Link> : <span>上一页</span>}<span>第 {page} 页</span>{result.next ? <Link href={readingPathsHref(filters, { page: page + 1 })}>下一页</Link> : <span>下一页</span>}</nav> : null}
    </> : null}
  </main>;
}

function PathTopicPicker({ value, known }: { value: string; known: { id: string; slug: string; title: string }[] }) {
  const [selected, setSelected] = useState(value), [selectedName, setSelectedName] = useState(known.find(row => row.slug === value || row.id === value)?.title || "");
  const [query, setQuery] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [result, setResult] = useState<{ results: { id: string; slug: string; name: string }[]; count: number; next: string | null; previous: string | null; page: number; query: string } | null>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function load(page = 1, text = query) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller; setBusy(true); setError("");
    try { const data = await apiRequest<Omit<NonNullable<typeof result>, "page" | "query">>(`/catalog/topics/?${new URLSearchParams({ q: text, page: String(page) })}`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]) }, null, false); if (!controller.signal.aborted) setResult({ ...data, page, query: text }); }
    catch { if (!controller.signal.aborted) setError("主题暂时无法读取，请重试。"); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <div className={styles.topicPicker}><input type="hidden" name="topic" value={selected} /><details onToggle={event => { if (event.currentTarget.open && !busy && !result && !error) void load(); }}><summary><Tag size={22} /><span>主题<strong>{selected ? selectedName || "已选择主题" : "全部主题"}</strong></span><ChevronDown size={15} /></summary><div className={styles.topicPanel}><label className={styles.search}><input value={query} onChange={event => setQuery(event.target.value)} aria-label="搜索阅读路径主题" onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); void load(); } }} /><button type="button" disabled={busy} onClick={() => void load()} aria-label="查找阅读主题"><Search size={15} /></button></label><button type="button" onClick={() => { setSelected(""); setSelectedName(""); }}>全部主题</button>{busy ? <p role="status">正在读取主题…</p> : error ? <p role="alert">{error}<button type="button" onClick={() => void load()}>重试主题</button></p> : result ? <><ul>{result.results.map(row => <li key={row.id}><label><input type="radio" name="topic-choice" checked={selected === row.id || selected === row.slug} onChange={() => { setSelected(row.slug); setSelectedName(row.name); }} />{row.name}</label></li>)}</ul><p>共 {result.count} 个公开主题</p><div className={styles.pagination}><button type="button" disabled={!result.previous} onClick={() => void load(result.page - 1, result.query)}>上一页主题</button><span>{result.page}</span><button type="button" disabled={!result.next} onClick={() => void load(result.page + 1, result.query)}>下一页主题</button></div></> : null}</div></details></div>;
}
