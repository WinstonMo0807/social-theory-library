"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ArrowRight, ChevronDown, ChevronRight, CircleAlert, Grid2X2, List, LoaderCircle, RefreshCw, Search, SlidersHorizontal, Undo2, X } from "lucide-react";
import { ApiRequestError } from "@/lib/api";
import { catalogFilters, catalogHref, catalogParams, clearCatalogFilters, defaultCatalogMatches, readCatalogSearch, type CatalogSearchPayload } from "@/lib/api/catalog-search.client";
import type { SearchFacetOption } from "@/lib/api/search.types";
import { Dialog } from "./ui/dialog";
import { CatalogResultCard } from "./catalog-result-card";
import { SavedWorkStatusProvider } from "./save-work-button";
import { UsageTracker, SearchClickTracker } from "./usage-tracker";

const matches = [
  { value: "title", label: "题名" }, { value: "author", label: "作者" },
  { value: "keyword", label: "关键词" }, { value: "abstract", label: "摘要" }, { value: "fulltext", label: "全文" },
];
const filterNames: Record<string, string> = { match: "检索字段", document_type: "材料类型", author: "作者", language: "语言", year: "出版时间", year_min: "起始年份", year_max: "截止年份", theory: "理论流派", topic: "主题", concept: "文献标签", access: "可获取性" };
const facetKeys = { document_type: "document_types", author: "authors", language: "languages", year: "years", theory: "theories", topic: "topics", concept: "concepts", access: "access" } as const;
const emptyFacets: CatalogSearchPayload["facets"] = { document_types: [], authors: [], languages: [], years: [], theories: [], topics: [], concepts: [], access: [], year_histogram: [] };

export function CatalogSearchWorkspace({ queryString }: { queryString: string }) {
  const router = useRouter();
  const params = catalogParams(queryString);
  const key = params.toString();
  const query = params.get("q") ?? "";
  const view = params.get("view") === "grid" ? "grid" : "list";
  const [snapshot, setSnapshot] = useState<{ key: string; data?: CatalogSearchPayload; error?: string; status?: number } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [mobileFilters, setMobileFilters] = useState(false);
  const [validation, setValidation] = useState("");
  const mobileClose = useRef<HTMLButtonElement>(null);
  const current = snapshot?.key === key ? snapshot : null;
  const data = current?.data;
  const facets = data?.facets ?? emptyFacets;
  const loading = current === null;
  const activeFilters = [...params].filter(([name]) => catalogFilters.includes(name as typeof catalogFilters[number]));

  useEffect(() => {
    const controller = new AbortController();
    readCatalogSearch(key, controller.signal).then(data => {
      if (!controller.signal.aborted) setSnapshot({ key, data });
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setSnapshot({ key, error: reason instanceof Error ? reason.message : "暂时无法读取馆藏检索结果。", status: reason instanceof ApiRequestError ? reason.status : 0 });
    });
    return () => controller.abort();
  }, [key, attempt]);

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const min = Number(values.get("year_min"));
    const max = Number(values.get("year_max"));
    if (min && max && min > max) { setValidation("起始年份不能晚于截止年份。"); return; }
    const next = new URLSearchParams();
    values.forEach((value, name) => { if (typeof value === "string" && value.trim()) next.append(name, value); });
    if (!next.has("match")) { setValidation("至少选择一个匹配范围。"); return; }
    setValidation(""); setMobileFilters(false);
    router.push(catalogHref(next));
  }
  function submitQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    router.push(catalogHref(key, { q: String(new FormData(event.currentTarget).get("q") ?? "").trim(), page: null }));
  }
  function retry() { setSnapshot(null); setAttempt(value => value + 1); }
  const clear = clearCatalogFilters(key);

  return <>
    {data ? <><UsageTracker eventType="search_submit" query={query} resultCount={data.pagination.total} source="exact_search" scope="catalog" /><SearchClickTracker query={query} source="exact_search" /></> : null}
    <main className="stl4-catalog-page">
      <section className="stl4-catalog-hero" aria-labelledby="catalog-title">
        <div className="stl4-catalog-hero-copy">
          <nav aria-label="面包屑"><Link href="/home">首页</Link><ChevronRight size={12} /><Link href="/explore">探索</Link><ChevronRight size={12} /><span>馆藏检索</span></nav>
          <h1 id="catalog-title">馆藏检索与文献列表</h1>
          <p>按题名、作者、材料类型或年份寻找具体文献，<br />也能转向正文研究。</p>
          <div className="stl4-catalog-query-row"><form className="stl4-catalog-query" onSubmit={submitQuery} action="/explore/original" key={`q:${query}`}>
            <Search size={17} aria-hidden="true" /><label className="sr-only" htmlFor="catalog-query">检索馆藏</label>
            <input id="catalog-query" name="q" type="search" maxLength={500} defaultValue={query} placeholder="题名、作者、关键词……" />
            <button type="submit">搜索</button>
          </form>
          <Link className="stl4-catalog-opinions" href={`/explore/opinions${query ? `?q=${encodeURIComponent(query)}` : ""}`}>进入观点检索 <ArrowRight size={14} /></Link></div>
        </div>
        <div className="stl4-catalog-hero-media" aria-hidden="true" />
      </section>

      <div className="stl4-catalog-layout">
        <aside className="stl4-catalog-sidebar" aria-label="馆藏筛选">
          <div className="stl4-catalog-filter-title"><h2>筛选条件</h2><Link href={clear}><Undo2 size={14} />清除筛选</Link></div>
          {activeFilters.length || query ? <div className="stl4-catalog-selected"><header>当前筛选<Link href={clear}>清除全部</Link></header><CatalogFilterChips params={params} facets={facets} /></div> : null}
          <form onSubmit={submitFilters} action="/explore/original" key={`desktop:${key}`}>
            <CatalogFilterFields params={params} facets={facets} />
            {validation ? <p role="alert">{validation}</p> : null}
            <button className="stl4-catalog-apply" type="submit">应用筛选</button>
          </form>
        </aside>
        <section className={`stl4-catalog-results is-${view}`} aria-label="检索结果" aria-busy={loading}>
          <div className="stl4-catalog-toolbar">
            <button className="stl4-catalog-mobile-trigger" type="button" onClick={() => setMobileFilters(true)}><SlidersHorizontal size={15} />筛选{activeFilters.length ? ` (${activeFilters.length})` : ""}</button>
            <h2>{data ? <>找到 <em>{data.pagination.total.toLocaleString("zh-CN")}</em> 条结果</> : loading ? "正在读取检索结果" : "检索结果暂不可用"}</h2>
            <div className="stl4-catalog-sort"><label className="sr-only" htmlFor="catalog-sort">排序</label><select id="catalog-sort" value={params.get("sort") ?? "relevance"} onChange={event => router.push(catalogHref(key, { sort: event.target.value, page: null }))}>
              <option value="relevance">相关性优先</option><option value="year">出版时间</option><option value="newest">最新入库</option>
            </select></div>
            <div className="stl4-catalog-view"><Link href={catalogHref(key, { view: "list" })} aria-current={view === "list" ? "true" : undefined} aria-label="列表视图"><List size={16} /></Link><Link href={catalogHref(key, { view: "grid" })} aria-current={view === "grid" ? "true" : undefined} aria-label="网格视图"><Grid2X2 size={16} /></Link></div>
          </div>
          {activeFilters.length ? <div className="stl4-catalog-mobile-chips"><CatalogFilterChips params={params} facets={facets} /></div> : null}
          {loading ? <div className="stl4-catalog-state" role="status"><LoaderCircle className="is-spinning" size={26} /><h3>正在检索文献…</h3><p>筛选条件已保留，请稍候。</p></div> : current?.error ? <div className="stl4-catalog-state" role="alert"><CircleAlert size={28} /><h3>{current.status === 400 ? "请调整检索条件" : current.status === 429 ? "检索请求较多，请稍后重试" : "连接服务时遇到问题"}</h3><p>{current.status === 400 ? current.error : "暂时无法完成检索。你的关键词和筛选条件已保留。"}</p><div><button type="button" onClick={retry}><RefreshCw size={14} />重试</button><Link href="/explore">返回探索</Link></div></div> : data && !data.works.length ? <div className="stl4-catalog-state" role="status"><Search size={32} /><h3>{query ? `未找到与“${query}”相关的文献` : activeFilters.length ? "未找到符合筛选条件的文献" : "当前暂无已公开的馆藏"}</h3><p>{query || activeFilters.length ? "可以缩短关键词、调整匹配范围，或减少筛选条件。" : "文献完成发布后会显示在这里。"}</p>{activeFilters.length ? <Link className="stl4-catalog-reset" href={clear}>清除全部筛选</Link> : <Link href="/explore">浏览探索入口</Link>}</div> : <SavedWorkStatusProvider workIds={data?.works.map(work => work.id) ?? []}><div className="stl4-catalog-cards">{data?.works.map(work => <CatalogResultCard key={work.id} row={work} />)}</div></SavedWorkStatusProvider>}
          {data && data.pagination.total_pages > 1 ? <nav className="stl4-catalog-pagination" aria-label="检索结果分页">
            {data.pagination.page > 1 ? <Link href={catalogHref(key, { page: String(data.pagination.page - 1) })}>上一页</Link> : <span>上一页</span>}
            <span>第 {data.pagination.page} / {data.pagination.total_pages} 页</span>
            {data.pagination.page < data.pagination.total_pages ? <Link href={catalogHref(key, { page: String(data.pagination.page + 1) })}>下一页</Link> : <span>下一页</span>}
          </nav> : null}
          <p className="stl4-catalog-crosslink"><Link href={`/explore?context=global&q=${encodeURIComponent(query)}`}>同时查找学者、主题与原文片段 <ArrowRight size={13} /></Link></p>
        </section>
      </div>
    </main>
    <Dialog open={mobileFilters} onRequestClose={() => setMobileFilters(false)} initialFocusRef={mobileClose} className="stl4-catalog-filter-dialog" aria-labelledby="catalog-filters-title">
      <header><button ref={mobileClose} type="button" onClick={() => setMobileFilters(false)}>取消</button><h2 id="catalog-filters-title">筛选条件</h2><Link href={clear} onClick={() => setMobileFilters(false)}>清除全部</Link></header>
      <form onSubmit={submitFilters} action="/explore/original" key={`mobile:${key}:${mobileFilters}`}>
        <div className="stl4-catalog-filter-scroll"><CatalogFilterFields params={params} facets={facets} mobile />{validation ? <p role="alert">{validation}</p> : null}</div>
        <footer><button type="reset" onClick={() => setValidation("")}>恢复已选</button><button className="stl4-catalog-apply" type="submit">应用筛选</button></footer>
      </form>
    </Dialog>
  </>;
}

function CatalogFilterFields({ params, facets, mobile = false }: { params: URLSearchParams; facets: CatalogSearchPayload["facets"]; mobile?: boolean }) {
  const id = useId();
  const selectedMatches = params.has("match") ? params.getAll("match") : defaultCatalogMatches;
  const largestYearCount = Math.max(1, ...facets.year_histogram.map(row => row.count));
  return <>
    {["q", "sort", "view"].map(name => params.get(name) ? <input key={name} type="hidden" name={name} value={params.get(name) ?? ""} /> : null)}
    {mobile ? <CatalogFacet name="document_type" options={facets.document_types} params={params} /> : <details className="stl4-catalog-filter-group stl4-catalog-scope" open><summary>匹配范围<ChevronDown size={14} /></summary><div>
      <Link className={!params.has("document_type") ? "is-selected" : ""} href={catalogHref(params, { document_type: null, page: null })} aria-current={!params.has("document_type") ? "true" : undefined}><span aria-hidden="true" />全部馆藏{typeof facets.total === "number" ? `（${facets.total}）` : ""}</Link>
      {facets.document_types.map(option => <Link key={option.value} className={params.getAll("document_type").includes(option.value) ? "is-selected" : ""} href={catalogHref(params, { document_type: option.value, page: null })} aria-current={params.getAll("document_type").includes(option.value) ? "true" : undefined}><span aria-hidden="true" />{option.label}（{option.count}）</Link>)}
    </div></details>}
    <details className="stl4-catalog-filter-group" open={params.has("year") || params.has("year_min") || params.has("year_max")}><summary>年份<ChevronDown size={14} /></summary><div className="stl4-catalog-year-inputs"><label htmlFor={`${id}-from`} className="sr-only">起始年份</label><input id={`${id}-from`} aria-label="起始年份" type="number" name="year_min" min="1" max="9999" placeholder="起始年" defaultValue={params.get("year_min") ?? ""} /><span>至</span><label htmlFor={`${id}-to`} className="sr-only">截止年份</label><input id={`${id}-to`} aria-label="截止年份" type="number" name="year_max" min="1" max="9999" placeholder="截止年" defaultValue={params.get("year_max") ?? ""} /></div>
      {facets.year_histogram.length ? <div className="stl4-catalog-year-bars" aria-label="关键词匹配文献的出版年份分布">{facets.year_histogram.map(row => <Link key={row.year} title={`${row.year}年 · ${row.count}部作品`} aria-label={`筛选${row.year}年，${row.count}部作品`} href={catalogHref(params, { year: null, year_min: String(row.year), year_max: String(row.year), page: null })} style={{ height: `${Math.max(5, row.count / largestYearCount * 100)}%` }} />)}</div> : null}
      {params.getAll("year").map(value => <input key={value} type="hidden" name="year" value={value} />)}
    </details>
    <CatalogFacet name="language" options={facets.languages} params={params} collapsed />
    <CatalogFacet name="topic" options={facets.topics} params={params} collapsed />
    <CatalogFacet name="theory" options={facets.theories} params={params} collapsed />
    <CatalogFacet name="access" options={facets.access} params={params} collapsed />
    <details className="stl4-catalog-advanced"><summary>高级筛选<ChevronDown size={14} /></summary>
      <fieldset className="stl4-catalog-filter-group"><legend>检索字段</legend>{matches.map(option => <label key={option.value}><input type="checkbox" name="match" value={option.value} defaultChecked={selectedMatches.includes(option.value)} /><span>{option.label}</span></label>)}</fieldset>
      {!mobile ? <CatalogFacet name="document_type" options={facets.document_types} params={params} /> : null}
      <CatalogFacet name="author" options={facets.authors} params={params} collapsed />
      <CatalogFacet name="concept" options={facets.concepts} params={params} collapsed />
    </details>
  </>;
}

function CatalogFilterChips({ params, facets }: { params: URLSearchParams; facets: CatalogSearchPayload["facets"] }) {
  return <div className="stl4-catalog-chips" aria-label="已应用筛选">{params.get("q") ? <Link href={catalogHref(params, { q: null, page: null })} aria-label="移除关键词">关键词：{params.get("q")}<X size={12} /></Link> : null}{[...params].filter(([name]) => catalogFilters.includes(name as typeof catalogFilters[number])).map(([name, value]) => {
    const options = name in facetKeys ? facets[facetKeys[name as keyof typeof facetKeys]] : matches;
    const label = options.find(option => option.value === value)?.label ?? value;
    const next = catalogParams(params); next.delete(name, value); next.delete("page");
    return <Link key={`${name}:${value}`} href={catalogHref(next)} aria-label={`移除${filterNames[name]}：${label}`}>{filterNames[name]}：{label}<X size={12} /></Link>;
  })}</div>;
}

function CatalogFacet({ name, options, params, collapsed = false }: { name: keyof typeof facetKeys; options: SearchFacetOption[]; params: URLSearchParams; collapsed?: boolean }) {
  const selected = params.getAll(name);
  const rows = [...options, ...selected.filter(value => !options.some(option => option.value === value)).map(value => ({ value, label: value, count: null }))];
  const contents = rows.length ? rows.map(option => <label key={option.value}><input type="checkbox" name={name} value={option.value} defaultChecked={selected.includes(option.value)} /><span>{option.label}</span><small>{option.count}</small></label>) : <p>暂无可用选项</p>;
  return collapsed ? <details className="stl4-catalog-filter-group" open={selected.length > 0}><summary>{filterNames[name]}<ChevronDown size={14} /></summary><div>{contents}</div></details> : <fieldset className="stl4-catalog-filter-group"><legend>{filterNames[name]}</legend>{contents}</fieldset>;
}
