import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, Search } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { loadSearch } from "@/lib/api/search.server";

export const metadata: Metadata = { title: "原文证据" };

type RawSearchParams = Record<string, string | string[] | undefined>;

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function EvidencePage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const params = await searchParams;
  const query = firstParam(params.q).trim();
  const page = Math.max(1, Number(firstParam(params.page)) || 1);
  let results: Awaited<ReturnType<typeof loadSearch>> | null = null;
  let unavailable = false;
  if (query) {
    try {
      results = await loadSearch(query, { scope: "fulltext", page, pageSize: 10, sort: "relevance" });
    } catch {
      unavailable = true;
    }
  }
  const passages = results?.passages ?? [];
  const selected = passages[0] ?? null;
  const queryHref = (nextPage?: number) => {
    const search = new URLSearchParams({ context: "global" });
    if (query) search.set("q", query);
    if (nextPage && nextPage > 1) search.set("page", String(nextPage));
    return `/explore/evidence?${search.toString()}`;
  };

  return (
    <>
      <div className="stl4-evidence-page">
        <header className="stl4-evidence-head">
          <div>
            <p className="stl4-evidence-breadcrumb"><Link href="/explore">探索</Link><span>/</span>原文证据</p>
            <h1>原文证据结果</h1>
            <p>按页码保留馆藏原文的位置、版本和可回读入口，方便跨作品核对。</p>
          </div>
          <form className="stl4-evidence-search" action="/explore/evidence" method="get">
            <Search size={16} aria-hidden="true" />
            <label className="sr-only" htmlFor="evidence-query">搜索原文证据</label>
            <input type="hidden" name="context" value="global" />
            <input id="evidence-query" name="q" type="search" defaultValue={query} placeholder="输入关键词或概念……" />
            <button type="submit">检索</button>
          </form>
        </header>

        <div className="stl4-evidence-layout">
          <aside className="stl4-evidence-filters" aria-label="证据筛选">
            <section>
              <h2>文献类型</h2>
              {results?.facets.document_types.length ? results.facets.document_types.map((facet) => (
                <p key={facet.value}><span>{facet.label}</span><small>{facet.count}</small></p>
              )) : <p className="stl4-evidence-muted">提交检索后显示可用筛选。</p>}
            </section>
            <section>
              <h2>检索范围</h2>
              <p><span>馆藏公开全文</span><small>{results?.counts.passages ?? "—"}</small></p>
              <p><span>当前页</span><small>{results?.pagination.page ?? "—"}</small></p>
            </section>
          </aside>

          <section className="stl4-evidence-results" aria-live="polite">
            <div className="stl4-evidence-results-head">
              <div><strong>{query ? "原文候选" : "从一个问题开始"}</strong><span>{results ? `${results.pagination.total.toLocaleString("zh-CN")} 条结果` : "等待检索"}</span></div>
              {results?.source === "demo" ? <small>当前运行环境未提供馆藏 API，未显示替代文献。</small> : null}
            </div>
            {!query ? (
              <div className="stl4-evidence-empty"><BookOpen size={26} /><h2>输入关键词开始查找</h2><p>结果会保留原文片段、作品版本和 PDF 页码，不把没有来源的回答当作证据。</p></div>
            ) : unavailable ? (
              <div className="stl4-evidence-empty"><h2>原文检索暂时不可用</h2><p>接口没有返回可核对的结果，请稍后重试；当前没有生成替代内容。</p></div>
            ) : passages.length ? passages.map((passage) => (
              <article className="stl4-evidence-card" key={passage.id}>
                <div className="stl4-evidence-card-index">{passage.page_index + 1}</div>
                <div className="stl4-evidence-card-content">
                  <h2>{passage.title}</h2>
                  <p className="stl4-evidence-meta">{passage.edition_slug || "公开版本"} · PDF 第 {passage.page_index + 1} 页 · 印刷页码 {passage.printed_label || "未标注"}</p>
                  <p className="stl4-evidence-snippet">{passage.snippet}</p>
                  <footer><Link href={`/reader/${encodeURIComponent(passage.asset_id)}?page=${passage.page_index + 1}&passage=${encodeURIComponent(passage.id)}&return_to=${encodeURIComponent("/explore/evidence")}`}>回到 Reader <ArrowRight size={14} /></Link><span>原文定位已保留</span></footer>
                </div>
              </article>
            )) : (
              <div className="stl4-evidence-empty"><h2>没有找到可展示的原文</h2><p>请调整关键词或转到原文检索扩大范围。</p><Link href="/explore/original">转到原文检索 <ArrowRight size={14} /></Link></div>
            )}
            {results && results.pagination.total_pages > 1 ? <nav className="stl4-evidence-pagination" aria-label="证据结果分页">{page > 1 ? <Link href={queryHref(page - 1)}>上一页</Link> : <span>上一页</span>}<strong>{page} / {results.pagination.total_pages}</strong>{page < results.pagination.total_pages ? <Link href={queryHref(page + 1)}>下一页</Link> : <span>下一页</span>}</nav> : null}
          </section>

          <aside className="stl4-evidence-detail" aria-label="证据摘要">
            <h2>证据摘要</h2>
            {selected ? <>
              <p className="stl4-evidence-detail-title">{selected.title}</p>
              <p>{selected.edition_slug || "公开版本"} · PDF 第 {selected.page_index + 1} 页</p>
              <blockquote>{selected.snippet}</blockquote>
              <Link className="stl4-evidence-detail-action" href={`/reader/${encodeURIComponent(selected.asset_id)}?page=${selected.page_index + 1}&passage=${encodeURIComponent(selected.id)}&return_to=${encodeURIComponent("/explore/evidence")}`}>阅读原文 <BookOpen size={15} /></Link>
            </> : <p className="stl4-evidence-muted">选择一个结果后，这里会显示版本、页码和回读入口。</p>}
          </aside>
        </div>
      </div>
      <SiteFooter />
    </>
  );
}
