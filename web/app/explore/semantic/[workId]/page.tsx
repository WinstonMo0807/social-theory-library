import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Quote } from "lucide-react";
import { SemanticResultActions } from "@/components/semantic-result-actions";
import { SiteFooter } from "@/components/site-footer";
import { loadSemanticSearch } from "@/lib/server-api";
import { semanticResponseLabel } from "@/lib/semantic-search-ui";

export const metadata: Metadata = {
  title: "馆藏观点结果",
};

export default async function SemanticWorkResultsPage({
  params,
  searchParams,
}: {
  params: Promise<{ workId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { workId } = await params;
  const raw = await searchParams;
  const queryValue = raw.q;
  const query = (Array.isArray(queryValue) ? queryValue[0] : queryValue ?? "").trim();
  const payload = await loadSemanticSearch(query, {
    workId,
    maxPerWork: 12,
    pageSize: 24,
  });
  const first = payload.results[0];

  return (
    <>
      <main className="page-shell semantic-work-detail-page">
        <nav className="breadcrumbs" aria-label="面包屑">
          <Link href={`/explore?mode=semantic&q=${encodeURIComponent(query)}`}><ArrowLeft size={15} /> 返回全部观点结果</Link>
        </nav>
        <header className="semantic-work-detail-hero">
          <p>馆藏内观点结果</p>
          <h1>{first?.title ?? "查看馆藏相关段落"}</h1>
          {first?.authors.length ? <p>{first.authors.join("、")}</p> : null}
          <dl>
            <div><dt>原始查询</dt><dd>{query || "尚未输入查询"}</dd></div>
            <div><dt>相关段落</dt><dd>{payload.count}</dd></div>
          </dl>
        </header>

        {payload.notice ? <p className={`semantic-notice ${payload.fallback_used || payload.service_unavailable ? "warning" : ""}`}>{payload.notice}</p> : null}

        <section className="semantic-work-detail-results">
          {payload.results.map((item, index) => (
            <article key={item.id}>
              <div className="semantic-rank"><span>{String(index + 1).padStart(2, "0")}</span><strong>{semanticResponseLabel(item)}</strong></div>
              <div>
                <p className="semantic-result-meta">
                  <span>PDF 第 {item.page_index} 页</span>
                  {item.printed_label && item.printed_label !== String(item.page_index) ? <span>书页 {item.printed_label}</span> : null}
                  {item.chapter_title ? <span>{item.chapter_title}</span> : null}
                  {item.section_title ? <span>{item.section_title}</span> : null}
                </p>
                <blockquote><Quote size={18} fill="currentColor" />{item.snippet}</blockquote>
                {item.context_before || item.context_after ? (
                  <details className="semantic-context">
                    <summary>展开前后文</summary>
                    {item.context_before ? <p>{item.context_before}</p> : null}
                    <blockquote>{item.snippet}</blockquote>
                    {item.context_after ? <p>{item.context_after}</p> : null}
                  </details>
                ) : null}
                <footer>
                  <SemanticResultActions query={query} chunkId={item.id} rank={index + 1} />
                  <Link className="button secondary" href={item.reader_url} aria-label={`打开《${item.title}》PDF 第 ${item.page_index} 页核对原文`}>回到原页 <ArrowRight size={16} /></Link>
                </footer>
              </div>
            </article>
          ))}
          {query && !payload.results.length ? (
            <div className="empty-state">
              <h2>这部馆藏暂时没有更多可用结果</h2>
              <p>可返回全部结果，或减少筛选条件后重新检索。</p>
            </div>
          ) : null}
          {!query ? (
            <div className="empty-state">
              <h2>缺少观点查询</h2>
              <Link className="button" href="/explore?mode=semantic">前往观点检索</Link>
            </div>
          ) : null}
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
