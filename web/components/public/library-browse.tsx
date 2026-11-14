"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition, type FormEvent } from "react";
import { ArrowRight, BookOpen, Grid2X2, List, LoaderCircle, Search, X } from "lucide-react";
import { BookCover } from "@/components/ui";
import { CollectionLink } from "@/components/collection-link";
import type { Work } from "@/lib/data";
import { libraryHref, libraryKinds, libraryParams } from "@/lib/library-browse";
import { editorialImageSources } from "@/lib/performance-assets";
import "./library-browse.css";

export function LibraryBrowse({ queryString, works, count, hasNext, error }: { queryString: string; works: Work[]; count: number | null; hasNext: boolean; error: string }) {
  const params = libraryParams(queryString), router = useRouter();
  const [pending, startTransition] = useTransition();
  const view = params.get("view") === "list" ? "list" : "shelves", page = Number(params.get("page") || 1);
  function change(values: Record<string, string | null>) { startTransition(() => router.push(libraryHref(params, values), { scroll: false })); }
  function search(event: FormEvent<HTMLFormElement>) { event.preventDefault(); change({ q: String(new FormData(event.currentTarget).get("q") || ""), page: null }); }
  return <div className="library-longread">
    <header className="library-intro"><div><h1>书库</h1><p>从经典与当代文献中，找到下一本书。</p></div><div className="library-scene"><img src="/editorial/generated-20261030/home.webp" {...editorialImageSources("/editorial/generated-20261030/home.webp", "240px")} alt="" width={240} height={100}/><span>社会学 · 人类学 · 民族学</span></div></header>
    <section className="library-browser" aria-label="全部馆藏" aria-busy={pending}>
      <div className="library-controls"><form action="/library" onSubmit={search} role="search" aria-label="查找馆藏"><Search size={20} aria-hidden="true"/><input key={params.get("q") || ""} name="q" defaultValue={params.get("q") || ""} maxLength={180} aria-label="书名或作者" placeholder="书名或作者"/>{params.get("q") ? <button type="button" aria-label="清除关键词" onClick={() => change({ q: null, page: null })}><X size={17}/></button> : null}<button type="submit" disabled={pending}>{pending ? <LoaderCircle className="spin" size={17} aria-label="正在查找"/> : "查找"}</button></form><label><span className="sr-only">书目排序</span><select value={params.get("sort") || "newest"} onChange={e => change({ sort: e.target.value, page: null })}><option value="newest">最近入库</option><option value="title">书名顺序</option></select></label><div className="library-view" aria-label="呈现方式"><button type="button" aria-label="书架视图" aria-pressed={view === "shelves"} onClick={() => change({ view: null })}><Grid2X2 size={18}/></button><button type="button" aria-label="列表视图" aria-pressed={view === "list"} onClick={() => change({ view: "list" })}><List size={19}/></button></div></div>
      <div className="library-filter-row"><nav aria-label="文献类型">{libraryKinds.map(([value, label]) => <button type="button" key={value} aria-pressed={(params.get("kind") || "") === value} onClick={() => change({ kind: value, page: null })}>{label}</button>)}</nav><Link href="/explore/original" prefetch={false}>原文与高级检索 <ArrowRight size={15}/></Link></div>
      <p className="library-count" role="status">{pending ? "正在更新书目…" : count !== null ? `${count.toLocaleString("zh-CN")} 部文献${params.get("q") ? ` · ${params.get("q")}` : ""}` : "馆藏目录"}</p>
      {error ? <div className="library-empty" role="alert"><BookOpen size={32}/><h2>暂时无法展示书目</h2><p>{error}</p><button onClick={() => startTransition(() => router.refresh())}>重新读取</button><Link href={libraryHref(params, { page: null })}>返回第一页</Link></div> : works.length ? <div className={`library-books is-${view}`} data-pending={pending || undefined}>{works.map(work => <article className="library-book" key={work.id}><CollectionLink className="library-book-cover" href={`/works/${work.slug}`} aria-label={`查看《${work.title}》`}><BookCover work={work}/></CollectionLink><div className="library-book-copy"><h2><CollectionLink href={`/works/${work.slug}`}>{work.title}</CollectionLink></h2><p>{work.author}</p><small>{[work.year, work.kind].filter(Boolean).join(" · ")}</small>{view === "list" && work.summary ? <p className="library-book-summary">{work.summary}</p> : null}<CollectionLink className="library-book-open" href={`/works/${work.slug}`}><span>查看作品</span><ArrowRight size={17}/></CollectionLink></div></article>)}</div> : <div className="library-empty"><BookOpen size={32}/><h2>{params.has("q") || params.has("kind") ? "没有符合条件的文献" : "书库正在准备中"}</h2><p>{params.has("q") || params.has("kind") ? "试试缩短关键词，或换一种文献类型。" : "公开的文献会在这里呈现。"}</p>{params.has("q") || params.has("kind") ? <Link href="/library">查看全部馆藏</Link> : null}</div>}
      {page > 1 || hasNext ? <nav className="library-pagination" aria-label="书库分页">{page > 1 ? <Link href={libraryHref(params, { page: String(page - 1) })} prefetch={false}>上一页</Link> : <span/>}<span>第 {page} 页{count !== null ? ` / ${Math.max(1, Math.ceil(count / 24))} 页` : ""}</span>{hasNext ? <Link href={libraryHref(params, { page: String(page + 1) })} prefetch={false}>下一页 <ArrowRight size={16}/></Link> : <span/>}</nav> : null}
    </section>
  </div>;
}
