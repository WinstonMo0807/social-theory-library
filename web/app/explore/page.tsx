import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Grid2X2,
  List,
  Quote,
  Search,
  Sparkles,
} from "lucide-react";
import {
  BookCard,
  ScholarCard,
  SearchField,
  SectionHeading,
} from "@/components/ui";
import { SiteFooter } from "@/components/site-footer";
import { ExploreAskClient, type LibraryScope } from "@/components/explore-ask-client";
import { ExploreLanding } from "@/components/explore-landing";
import { SemanticResultActions } from "@/components/semantic-result-actions";
import { SearchClickTracker, UsageTracker } from "@/components/usage-tracker";
import { semanticResponseLabel } from "@/lib/semantic-search-ui";
import {
  loadHotSearches,
  loadSearch,
  loadSemanticSearch,
  type SearchFacetOption,
  type SearchFilters,
  type SemanticSearchPayload,
  type SemanticSearchResult,
} from "@/lib/server-api";

export const metadata: Metadata = {
  title: "探索书库",
};

type RawSearchParams = Record<string, string | string[] | undefined>;

const scopeLabels: Record<string, string> = {
  all: "全部结果",
  book: "图书",
  article: "论文",
  thesis: "学位论文",
  report: "研究报告",
  scholar: "学者",
  topic: "主题",
  theory: "理论流派",
  fulltext: "全文",
};

export default async function ExplorePage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const params = await searchParams;
  if (!Object.keys(params).length) {
    return <ExploreLanding />;
  }
  const query = firstParam(params.q)?.trim() ?? "";
  const requestedMode = firstParam(params.mode);
  const mode = requestedMode === "semantic" || requestedMode === "ask" ? requestedMode : "exact";
  if (mode === "ask") {
    const requestedContext = firstParam(params.context) ?? "global";
    const allowedContexts = new Set<LibraryScope["context"]>([
      "global", "works", "scholars", "disciplines", "subdisciplines", "theories", "topics", "reading_paths",
    ]);
    const context = allowedContexts.has(requestedContext as LibraryScope["context"])
      ? requestedContext as LibraryScope["context"]
      : "global";
    return <AskLibraryPage
      query={query}
      scope={{
        context,
        ids: listParam(params.id),
        asset_id: firstParam(params.asset_id),
        visibility: "public",
      }}
    />;
  }
  if (mode === "semantic") {
    const semanticFilters: SearchFilters = {
      documentType: listParam(params.document_type),
      language: listParam(params.language),
      theory: listParam(params.theory),
      topic: listParam(params.topic),
      concept: listParam(params.concept),
      author: listParam(params.author),
      year: listParam(params.year),
      access: listParam(params.access),
      sort: firstParam(params.sort) ?? "relevance",
      rewrite: firstParam(params.rewrite) ?? "",
      rewriteDisabled: firstParam(params.rewrite_disabled) === "1",
    };
    const semantic = await loadSemanticSearch(query, semanticFilters);
    return (
      <SemanticExplorePage
        params={params}
        query={query}
        filters={semanticFilters}
        results={semantic}
      />
    );
  }
  const scope = scopeLabels[firstParam(params.type) ?? "all"]
    ? firstParam(params.type) ?? "all"
    : "all";
  const sort = firstParam(params.sort) ?? "relevance";
  const view = firstParam(params.view) === "list" ? "list" : "grid";
  const page = Math.max(1, Number(firstParam(params.page)) || 1);
  const filters: SearchFilters = {
    scope,
    documentType: listParam(params.document_type),
    theory: listParam(params.theory),
    topic: listParam(params.topic),
    concept: listParam(params.concept),
    author: listParam(params.author),
    year: listParam(params.year),
    language: listParam(params.language),
    access: listParam(params.access),
    sort,
    page,
  };
  const [results, hotSearches] = await Promise.all([
    loadSearch(query, filters),
    loadHotSearches(),
  ]);
  const bookWorks = results.works.filter((work) => work.kind === "图书");
  const articleWorks = results.works.filter((work) => work.kind === "期刊论文");
  const thesisWorks = results.works.filter((work) => work.kind === "学位论文");
  const reportWorks = results.works.filter((work) => work.kind === "研究报告");
  const activeFilterCount = [
    filters.documentType,
    filters.theory,
    filters.topic,
    filters.concept,
    filters.author,
    filters.year,
    filters.language,
    filters.access,
  ].reduce((total, values) => total + (values?.length ?? 0), 0);
  const preservedForFilter = entriesExcept(params, [
    "q",
    "type",
    "document_type",
    "theory",
    "topic",
    "concept",
    "author",
    "year",
    "language",
    "access",
    "page",
  ]);
  const preservedForSort = entriesExcept(params, ["sort", "page"]);

  return (
    <>
      <UsageTracker eventType="search_submit" query={query} resultCount={resultCount(results.counts)} source="exact_search" scope={scope} />
      <SearchClickTracker query={query} source="exact_search" />
      <div className="page-shell explore-page">
        <section className="explore-workbench-head exact-workbench-head">
          <div className="explore-workbench-title">
            <h1>原文检索</h1>
            <p>在题名、责任者、知识实体与全文中定位可核对的原文，并精确回到 PDF 页面。</p>
          </div>
          <div className="explore-query-column">
            <form className="explore-search" action="/explore/original">
              <input type="hidden" name="context" value="global" />
              <SearchField defaultValue={query} />
              <button className="button" type="submit">
                搜索
              </button>
            </form>
            <nav className="result-tabs" aria-label="搜索结果类别">
              {[
                ["all", "全部", resultCount(results.counts)],
                ["book", "图书", results.counts.books],
                ["article", "论文", results.counts.articles],
                ["scholar", "学者", results.counts.scholars],
                ["topic", "主题", results.counts.topics],
                ["theory", "理论流派", results.counts.theories],
                ["fulltext", "全文内容", results.counts.passages],
              ].map(([value, label, count]) => (
                <Link
                  className={scope === value ? "active" : ""}
                  href={buildExploreHref(params, {
                    type: value === "all" ? null : String(value),
                    document_type: null,
                    page: null,
                  })}
                  key={String(value)}
                >
                  <span>{label}</span><small>{count}</small>
                </Link>
              ))}
            </nav>
          </div>
          <SearchModeSwitch mode="exact" query={query} />
        </section>

        <ExactMobileFilters
          params={params}
          query={query}
          scope={scope}
          filters={filters}
          results={results}
          activeFilterCount={activeFilterCount}
          preserved={preservedForFilter}
        />

        <div className="search-layout">
          <form className="filter-sidebar" action="/explore/original">
            <input type="hidden" name="context" value="global" />
            {query ? <input type="hidden" name="q" value={query} /> : null}
            {scope !== "all" ? <input type="hidden" name="type" value={scope} /> : null}
            {preservedForFilter.map(([name, value]) => (
              <input type="hidden" name={name} value={value} key={`${name}-${value}`} />
            ))}
            <div className="filter-title">
              <strong>筛选结果{activeFilterCount ? ` · ${activeFilterCount}` : ""}</strong>
              <Link href={buildExploreHref(params, {
                document_type: null,
                theory: null,
                topic: null,
                concept: null,
                author: null,
                year: null,
                language: null,
                access: null,
                page: null,
              })}>清除</Link>
            </div>
            <FilterGroup
              title="内容类型"
              name="document_type"
              selected={filters.documentType ?? []}
              options={[
                { value: "book", label: "图书", count: results.counts.books },
                { value: "article", label: "期刊论文", count: results.counts.articles },
                { value: "thesis", label: "学位论文", count: results.counts.theses },
                { value: "report", label: "研究报告", count: results.counts.reports },
              ]}
            />
            <FilterGroup
              title="理论流派"
              name="theory"
              selected={filters.theory ?? []}
              options={results.facets.theories}
            />
            <FilterGroup
              title="研究专题"
              name="topic"
              selected={filters.topic ?? []}
              options={results.facets.topics}
              collapsible
            />
            <FilterGroup
              title="文献标签"
              name="concept"
              selected={filters.concept ?? []}
              options={results.facets.concepts}
              collapsible
            />
            <FilterGroup
              title="作者"
              name="author"
              selected={filters.author ?? []}
              options={results.facets.authors}
              collapsible
            />
            <FilterGroup
              title="出版时间"
              name="year"
              selected={filters.year ?? []}
              options={results.facets.years}
              collapsible
            />
            <FilterGroup
              title="语言"
              name="language"
              selected={filters.language ?? []}
              options={results.facets.languages}
              collapsible
            />
            <FilterGroup
              title="开放状态"
              name="access"
              selected={filters.access ?? []}
              options={results.facets.access}
              collapsible
            />
            <button className="button filter-submit" type="submit">
              应用筛选
            </button>
          </form>

          <section className={`search-results view-${view}`}>
            <div className="results-toolbar">
              <strong>
                {scopeLabels[scope]} · {scopeResultCount(scope, results.counts, results.pagination.total).toLocaleString("zh-CN")} 条
              </strong>
              <div>
                <Link
                  className={view === "list" ? "active" : ""}
                  href={buildExploreHref(params, { view: "list", page: null })}
                  aria-label="列表视图"
                >
                  <List size={16} />
                </Link>
                <Link
                  className={view === "grid" ? "active" : ""}
                  href={buildExploreHref(params, { view: "grid", page: null })}
                  aria-label="网格视图"
                >
                  <Grid2X2 size={16} />
                </Link>
              </div>
            </div>

            {scope === "all" || scope === "book" ? (
              <WorkResultGroup
                title="图书"
                works={scope === "all" ? bookWorks.slice(0, 4) : bookWorks}
                href={buildExploreHref(params, { type: "book", document_type: null, page: null })}
                action="查看全部图书"
                empty="没有找到题名、责任者或筛选条件匹配的公开图书。"
              />
            ) : null}

            {scope === "all" || scope === "fulltext" ? (
              <PassageResultGroup
                passages={scope === "all" ? results.passages.slice(0, 4) : results.passages}
                query={query}
                href={buildExploreHref(params, { type: "fulltext", document_type: null, page: null })}
                showAllLink={scope === "all"}
              />
            ) : null}

            {scope === "all" || scope === "article" ? (
              <WorkResultGroup
                title="期刊论文"
                works={scope === "all" ? articleWorks.slice(0, 4) : articleWorks}
                href={buildExploreHref(params, { type: "article", document_type: null, page: null })}
                action="查看全部论文"
                empty="当前查询没有匹配的期刊论文。"
              />
            ) : null}

            {scope === "thesis" ? (
              <WorkResultGroup
                title="学位论文"
                works={thesisWorks}
                href={buildExploreHref(params, { type: "thesis", document_type: null, page: null })}
                action="查看全部学位论文"
                empty="当前查询没有匹配的学位论文。"
              />
            ) : null}

            {scope === "report" ? (
              <WorkResultGroup
                title="研究报告"
                works={reportWorks}
                href={buildExploreHref(params, { type: "report", document_type: null, page: null })}
                action="查看全部研究报告"
                empty="当前查询没有匹配的研究报告。"
              />
            ) : null}

            {scope === "all" || scope === "scholar" ? (
              <div className="result-group scholar-results">
                <SectionHeading
                  title="学者"
                  href={buildExploreHref(params, { type: "scholar", document_type: null, page: null })}
                  action={scope === "all" ? "查看全部学者" : undefined}
                />
                <div>
                  {(scope === "all" ? results.scholars.slice(0, 4) : results.scholars).map((scholar) => (
                    <ScholarCard scholar={scholar} key={scholar.slug} />
                  ))}
                  {!results.scholars.length ? <p className="empty-state">没有找到匹配的学者。</p> : null}
                </div>
              </div>
            ) : null}

            {scope === "all" || scope === "topic" ? (
              <DirectoryResultGroup
                title="主题"
                items={scope === "all" ? results.topics.slice(0, 5) : results.topics}
                basePath="/topics"
                href={buildExploreHref(params, { type: "topic", document_type: null, page: null })}
                action={scope === "all" ? "查看全部主题" : undefined}
                empty="没有找到匹配的公开主题。"
              />
            ) : null}

            {scope === "all" || scope === "theory" ? (
              <DirectoryResultGroup
                title="理论流派"
                items={scope === "all" ? results.theories.slice(0, 5) : results.theories}
                basePath="/theory-schools"
                href={buildExploreHref(params, { type: "theory", document_type: null, page: null })}
                action={scope === "all" ? "查看全部理论流派" : undefined}
                empty="没有找到匹配的公开理论流派。"
              />
            ) : null}

            <SearchPagination
              current={results.pagination.page}
              total={results.pagination.total_pages}
              params={params}
            />
          </section>

          <aside className="search-aside exact-search-aside">
            <section>
              <h2>结果概览</h2>
              {[
                [results.counts.books.toLocaleString("zh-CN"), "图书"],
                [results.counts.articles.toLocaleString("zh-CN"), "论文"],
                [results.counts.scholars.toLocaleString("zh-CN"), "学者"],
                [results.counts.topics.toLocaleString("zh-CN"), "主题"],
                [results.counts.passages.toLocaleString("zh-CN"), "全文内容"],
              ].map(([count, label]) => (
                <p key={label}><strong>{count}</strong><span>{label}</span></p>
              ))}
            </section>
            <section>
              <h2>排序</h2>
              <form className="sort-form exact-aside-sort" action="/explore/original">
                <input type="hidden" name="context" value="global" />
                {preservedForSort.map(([name, value]) => (
                  <input type="hidden" name={name} value={value} key={`${name}-${value}`} />
                ))}
                <label>
                  <span className="sr-only">结果排序</span>
                  <select name="sort" defaultValue={sort}>
                    <option value="relevance">相关性降序</option>
                    <option value="newest">最新入库</option>
                    <option value="year">出版年份</option>
                  </select>
                </label>
                <button type="submit">应用</button>
              </form>
            </section>
            <section>
              <h2>推荐搜索</h2>
              {hotSearches.map((item) => (
                <Link href={`/explore/original?context=global&q=${encodeURIComponent(item)}`} key={item}><Search size={13} />{item}</Link>
              ))}
              {!hotSearches.length ? <p className="empty-state">匿名搜索数据积累后将在这里显示。</p> : null}
            </section>
          </aside>
        </div>
      </div>
      <SiteFooter />
    </>
  );
}

function SearchModeSwitch({
  mode,
  query,
}: {
  mode: "exact" | "semantic" | "ask";
  query: string;
}) {
  const encodedQuery = query ? `?q=${encodeURIComponent(query)}` : "";
  return (
    <nav className="search-mode-switch" aria-label="检索方式">
      <Link className={mode === "exact" ? "active" : ""} href={`/explore/original?context=global${query ? `&q=${encodeURIComponent(query)}` : ""}`}>
        <span><strong>原文检索</strong></span>
      </Link>
      <Link className={mode === "semantic" ? "active" : ""} href={`/explore/opinions${encodedQuery}`}>
        <span><strong>观点检索</strong></span>
      </Link>
      <Link className={mode === "ask" ? "active" : ""} href={`/explore/ask${encodedQuery}`}>
        <span><strong>向书库提问</strong></span>
      </Link>
    </nav>
  );
}

function SemanticExplorePage({
  params,
  query,
  filters,
  results,
}: {
  params: RawSearchParams;
  query: string;
  filters: SearchFilters;
  results: SemanticSearchPayload;
}) {
  const topEvidence = results.results.slice(0, 3);
  const moreEvidence = results.results.slice(3);
  const activeFilterCount = [
    filters.documentType,
    filters.language,
    filters.theory,
    filters.topic,
    filters.concept,
    filters.author,
    filters.year,
    filters.access,
  ].reduce((total, values) => total + (values?.length ?? 0), 0);
  const preservedForFilters = entriesExcept(params, [
    "q",
    "document_type",
    "language",
    "theory",
    "topic",
    "concept",
    "author",
    "year",
    "access",
  ]);
  return (
    <>
      <UsageTracker eventType="search_submit" query={query} resultCount={results.count} source="semantic_search" scope="semantic" />
      <SearchClickTracker query={query} source="semantic_search" />
      <div className="page-shell explore-page semantic-explore-page">
        <section className="explore-workbench-head semantic-workbench-head">
          <div className="explore-workbench-title">
            <h1>观点检索</h1>
            <p>从馆藏学术观点文本中寻找可能回应问题的原文片段，所有出处均回到原文核对。</p>
          </div>
          <div className="explore-query-column">
            <form className="explore-search" action="/explore/opinions">
              <SearchField defaultValue={query} placeholder="输入社会科学问题或待追查的观点……" />
              {entriesExcept(params, ["q"]).map(([name, value]) => (
                <input type="hidden" name={name} value={value} key={`${name}-${value}`} />
              ))}
              <button className="button" type="submit">
                检索
              </button>
            </form>
            <SearchModeSwitch mode="semantic" query={query} />
          </div>
        </section>

        <SemanticMobileFilters
          params={params}
          query={query}
          filters={filters}
          results={results}
          activeFilterCount={activeFilterCount}
        />

        <div className="semantic-search-layout">
          <form className="filter-sidebar semantic-filter-sidebar" action="/explore/opinions">
            {query ? <input type="hidden" name="q" value={query} /> : null}
            {preservedForFilters.map(([name, value]) => (
              <input type="hidden" name={name} value={value} key={`${name}-${value}`} />
            ))}
            <div className="filter-title">
              <strong>限定馆藏{activeFilterCount ? ` · ${activeFilterCount}` : ""}</strong>
              <Link href={buildExploreHref(params, {
                mode: "semantic",
                document_type: null,
                language: null,
                theory: null,
                topic: null,
                concept: null,
                author: null,
                year: null,
                access: null,
              })}>清除</Link>
            </div>
            <FilterGroup
              title="内容类型"
              name="document_type"
              selected={filters.documentType ?? []}
              options={results.facets.document_types}
            />
            <FilterGroup
              title="正文语言"
              name="language"
              selected={filters.language ?? []}
              options={results.facets.languages}
            />
            <FilterGroup title="作者与学者" name="author" selected={filters.author ?? []} options={results.facets.authors} collapsible />
            <FilterGroup title="出版时间" name="year" selected={filters.year ?? []} options={results.facets.years} collapsible />
            <FilterGroup title="理论流派" name="theory" selected={filters.theory ?? []} options={results.facets.theories} collapsible />
            <FilterGroup title="研究专题" name="topic" selected={filters.topic ?? []} options={results.facets.topics} collapsible />
            <FilterGroup title="文献标签" name="concept" selected={filters.concept ?? []} options={results.facets.concepts} collapsible />
            <FilterGroup title="开放状态" name="access" selected={filters.access ?? []} options={results.facets.access} collapsible />
            <button className="button filter-submit" type="submit">应用限定</button>
          </form>

          <main className="semantic-results">
            <header className="semantic-results-header">
              <div>
                <p>馆藏原文候选</p>
                <h2>{query ? `${results.work_count} 部馆藏 · ${results.count} 个候选段落` : "等待检索"}</h2>
              </div>
              <form className="sort-form" action="/explore/opinions">
                {entriesExcept(params, ["sort"]).map(([name, value]) => (
                  <input type="hidden" name={name} value={value} key={`${name}-${value}`} />
                ))}
                <label>
                  <span>馆内证据排序</span>
                  <select name="sort" defaultValue={filters.sort ?? "relevance"}>
                    <option value="relevance">优先核对</option>
                    <option value="newest">最近入库</option>
                    <option value="year">出版年份</option>
                  </select>
                </label>
                <button type="submit">应用</button>
              </form>
            </header>
            <p className={`semantic-notice ${results.fallback_used || results.service_unavailable ? "warning" : ""}`}>
              {results.service_unavailable || results.fallback_reason === "api_unavailable"
                ? results.notice
                : results.fallback_used
                  ? "服务端已确认本次查询使用关键词检索。下面的顺序不代表语义相关程度。"
                  : results.notice}
            </p>
            {query ? (
              <section className="semantic-understanding">
                <h2>问题拆解与查询理解</h2>
                <div><span>查询类型</span><strong>{results.understanding.type}</strong></div>
                {results.understanding.terms.length ? (
                  <div><span>识别线索</span><p>{results.understanding.terms.map((term) => <em key={term}>{term}</em>)}</p></div>
                ) : null}
                {results.understanding.related_concepts.length ? (
                  <div><span>相关馆内概念</span><p>{results.understanding.related_concepts.map((concept) => <em key={`${concept.kind}-${concept.slug}`}>{concept.name}</em>)}</p></div>
                ) : null}
                {results.query_rewrite_enabled && results.understanding.rewrites.length > 1 ? (
                  <details open={Boolean(filters.rewrite)}>
                    <summary>查看和调整检索表达</summary>
                    <p>原始查询始终参与检索。下面的表达只用于补充语义召回。</p>
                    {results.understanding.rewrites.map((rewrite) => <p key={rewrite}>{rewrite}</p>)}
                    <form className="semantic-rewrite-form" action="/explore/opinions">
                      {entriesExcept(params, ["rewrite", "rewrite_disabled"]).map(([name, value]) => (
                        <input type="hidden" name={name} value={value} key={`${name}-${value}`} />
                      ))}
                      <input
                        name="rewrite"
                        aria-label="检索表达"
                        defaultValue={filters.rewrite || results.active_rewrite || ""}
                        placeholder="编辑补充检索表达"
                      />
                      <button type="submit">应用表达</button>
                      <Link href={buildExploreHref(params, { rewrite: null, rewrite_disabled: "1" })}>关闭改写</Link>
                    </form>
                  </details>
                ) : null}
                {results.query_rewrite_enabled && filters.rewriteDisabled ? (
                  <Link className="semantic-rewrite-enable" href={buildExploreHref(params, { rewrite_disabled: null })}>重新启用查询改写</Link>
                ) : null}
            </section>
            ) : null}
            <div className="semantic-result-list semantic-evidence-sections">
              {topEvidence.length ? (
                <section className="semantic-top-evidence">
                  <header><span>1</span><div><h2>优先核对的原文</h2><p>排序用于缩小核对范围，不表示已经回答问题，也不是相关概率。</p></div></header>
                  {topEvidence.map((item, index) => (
                    <SemanticEvidenceCard item={item} query={query} rank={index + 1} key={item.id} />
                  ))}
                </section>
              ) : null}
              {moreEvidence.length ? (
                <details className="semantic-more-evidence" open>
                  <summary><span>2</span><strong>更多候选原文</strong><small>{moreEvidence.length} 个段落</small></summary>
                  <div>
                    {moreEvidence.map((item, index) => (
                      <SemanticEvidenceCard item={item} query={query} rank={index + 4} compact key={item.id} />
                    ))}
                  </div>
                </details>
              ) : null}
              {topEvidence.length > 1 ? (
                <section className="semantic-comparison">
                  <header><span>3</span><div><h2>并排核对</h2><p>这里只并排呈现真实证据，不推断作者支持或反对某一立场。</p></div></header>
                  <div>
                    {topEvidence.slice(0, 2).map((item) => (
                      <article key={item.id}>
                        <SemanticSourceCover item={item} compact />
                        <div>
                          <p>{item.title}</p>
                          {item.authors.length ? <small>{item.authors.join("、")}{item.publication_year ? ` · ${item.publication_year}` : ""}</small> : null}
                          <blockquote className="semantic-comparison-excerpt"><span>{item.snippet}</span></blockquote>
                          <small>PDF 第 {item.page_index} 页{item.printed_label ? ` · 书页 ${item.printed_label}` : ""}</small>
                          <Link href={item.reader_url} aria-label={`打开《${item.title}》PDF 第 ${item.page_index} 页核对原文`}>回到原文 <ArrowRight size={14} /></Link>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}
              {query && !results.results.length ? (
                <p className="empty-state">暂时没有可靠候选。可尝试增加上下文，或减少筛选条件。</p>
              ) : null}
              {!query ? (
                <div className="semantic-empty-guide">
                  <Sparkles size={28} />
                  <h2>可以直接粘贴一段待追查的观点</h2>
                  <p>检索结果会标明馆藏、PDF 页序和纸本页码，并可回到阅读器核对原文。</p>
                </div>
              ) : null}
            </div>
          </main>

          <aside className="search-aside semantic-search-aside">
            {query ? (
              <section className="semantic-aside-analysis">
                <h2>问题拆解</h2>
                <p>{results.understanding.type}</p>
                <div>
                  {results.understanding.terms.map((term) => <span className="semantic-aside-chip" key={term}>{term}</span>)}
                </div>
              </section>
            ) : null}
            <section className="semantic-aside-explainer">
              <h2>检索说明</h2>
              <div><Sparkles size={16} aria-hidden="true" /><p><strong>馆藏语义匹配</strong><span>从已完成检索准备的公开全文中寻找候选。</span></p></div>
              <div><Quote size={16} aria-hidden="true" /><p><strong>短语原文定位</strong><span>结果保留页码、书页标签和前后文。</span></p></div>
              <div><Search size={16} aria-hidden="true" /><p><strong>不直接生成答案</strong><span>候选只安排核对顺序，不代替原文判断。</span></p></div>
              <dl>
                <div><dt>检索方式</dt><dd>{results.engine === "hybrid" ? "混合检索" : results.engine === "keyword_fallback" ? "关键词检索" : "状态待确认"}</dd></div>
                {results.search_version ? <div><dt>索引版本</dt><dd>{results.search_version}</dd></div> : null}
              </dl>
            </section>
            <section className="semantic-aside-tips">
              <h2>探索小贴士</h2>
              <ul>
                <li>把宽泛主题改写为一个明确问题。</li>
                <li>可补充人物、年代或理论语境。</li>
                <li>先看上下文，再决定是否引用。</li>
              </ul>
            </section>
          </aside>
        </div>
      </div>
      <SiteFooter />
    </>
  );
}

function SemanticEvidenceCard({
  item,
  query,
  rank,
  compact = false,
}: {
  item: SemanticSearchResult;
  query: string;
  rank: number;
  compact?: boolean;
}) {
  return (
    <article className={`semantic-result-card semantic-work-result-card ${compact ? "compact" : ""}`}>
      <div className="semantic-rank">
        <span>{rank}</span>
        <strong>{semanticResponseLabel(item)}</strong>
      </div>
      <SemanticSourceCover item={item} />
      <div className="semantic-work-result-copy">
        <header>
          <p>{documentTypeLabel(item.document_type)}{item.publication_year ? ` · ${item.publication_year}` : ""}</p>
          <h3>{item.title}</h3>
          {item.authors.length ? <p className="muted-row">{item.authors.join("、")}</p> : null}
        </header>
        <SemanticPassageBlock item={item} query={query} rank={rank} />
        <Link className="semantic-work-detail-link" href={`/explore/semantic/${item.work_id}?q=${encodeURIComponent(query)}`}>
          查看本馆藏更多相关观点 <ArrowRight size={16} />
        </Link>
      </div>
    </article>
  );
}

function SemanticSourceCover({
  item,
  compact = false,
}: {
  item: SemanticSearchResult;
  compact?: boolean;
}) {
  return (
    <div className={`semantic-source-cover ${compact ? "compact" : ""}`}>
      {item.cover_url ? (
        <Image
          src={item.cover_url}
          alt={`《${item.title}》封面`}
          width={compact ? 54 : 72}
          height={compact ? 78 : 104}
          sizes={compact ? "54px" : "72px"}
          unoptimized
        />
      ) : (
        <div className="semantic-source-mark" aria-label={`《${item.title}》暂无馆藏封面`}>
          <span>{documentTypeLabel(item.document_type).slice(0, 2)}</span>
          <small>{item.title.slice(0, 8)}</small>
        </div>
      )}
    </div>
  );
}

function SemanticPassageBlock({
  item,
  query,
  rank,
}: {
  item: SemanticSearchResult;
  query: string;
  rank: number;
}) {
  return (
    <section className="semantic-passage-block">
      <p className="semantic-result-meta">
        <span>PDF 第 {item.page_index} 页</span>
        {item.printed_label && item.printed_label !== String(item.page_index)
          ? <span>书页 {item.printed_label}</span>
          : null}
        {item.chapter_title ? <span>{item.chapter_title}</span> : null}
        {item.section_title ? <span>{item.section_title}</span> : null}
      </p>
      <blockquote><Quote size={18} fill="currentColor" aria-hidden="true" /><span className="semantic-snippet">{item.snippet}</span></blockquote>
      {item.context_before || item.context_after ? (
        <details className="semantic-context">
          <summary>查看上下文</summary>
          {item.context_before ? <p>{item.context_before}</p> : null}
          <blockquote>{item.snippet}</blockquote>
          {item.context_after ? <p>{item.context_after}</p> : null}
        </details>
      ) : null}
      {item.concepts.length ? <p className="semantic-concepts">{item.concepts.map((concept) => <span key={concept}>{concept}</span>)}</p> : null}
      {item.reasons.length ? (
        <ul className="semantic-reasons">
          {item.reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      ) : null}
      <footer>
        <SemanticResultActions query={query} chunkId={item.id} rank={rank} />
        <Link className="button secondary" href={item.reader_url} aria-label={`打开《${item.title}》PDF 第 ${item.page_index} 页核对原文`}>
          回到原文 <ArrowRight size={16} />
        </Link>
      </footer>
    </section>
  );
}

function documentTypeLabel(value: string) {
  return {
    book: "图书",
    journal_article: "期刊论文",
    thesis: "学位论文",
    report: "研究报告",
  }[value] ?? value;
}

function AskLibraryPage({ query, scope }: { query: string; scope: LibraryScope }) {
  return (
    <>
      <div className="page-shell explore-page ask-library-page">
        <ExploreAskClient initialQuestion={query} initialScope={scope} />
      </div>
      <SiteFooter />
    </>
  );
}

function FilterGroup({
  title,
  name,
  options,
  selected,
  collapsible = false,
}: {
  title: string;
  name: string;
  options: SearchFacetOption[];
  selected: string[];
  collapsible?: boolean;
}) {
  const content = options.length ? options.map((option) => (
    <label key={option.value}>
      <input
        type="checkbox"
        name={name}
        value={option.value}
        defaultChecked={selected.includes(option.value)}
      />
      <span>{option.label}</span>
      <small>{option.count}</small>
    </label>
  )) : <p className="filter-empty">当前结果没有可用选项。</p>;

  if (collapsible) {
    return (
      <details className="filter-group collapsible-filter" open={selected.length > 0}>
        <summary>{title}<span>{selected.length ? selected.length : "＋"}</span></summary>
        <div>{content}</div>
      </details>
    );
  }
  return (
    <fieldset className="filter-group">
      <legend>{title}</legend>
      {content}
    </fieldset>
  );
}

function ExactMobileFilters({
  params,
  query,
  scope,
  filters,
  results,
  activeFilterCount,
  preserved,
}: {
  params: RawSearchParams;
  query: string;
  scope: string;
  filters: SearchFilters;
  results: Awaited<ReturnType<typeof loadSearch>>;
  activeFilterCount: number;
  preserved: [string, string][];
}) {
  return (
    <details className="mobile-filter-disclosure">
      <summary>筛选结果{activeFilterCount ? ` · 已选 ${activeFilterCount}` : ""}<span>展开</span></summary>
      <form action="/explore/original">
        <input type="hidden" name="context" value="global" />
        {query ? <input type="hidden" name="q" value={query} /> : null}
        {scope !== "all" ? <input type="hidden" name="type" value={scope} /> : null}
        {preserved.map(([name, value]) => <input type="hidden" name={name} value={value} key={`${name}-${value}`} />)}
        <div className="filter-title">
          <strong>限定公开馆藏</strong>
          <Link href={buildExploreHref(params, {
            document_type: null,
            theory: null,
            topic: null,
            concept: null,
            author: null,
            year: null,
            language: null,
            access: null,
            page: null,
          })}>清除</Link>
        </div>
        <FilterGroup title="内容类型" name="document_type" selected={filters.documentType ?? []} options={[
          { value: "book", label: "图书", count: results.counts.books },
          { value: "article", label: "期刊论文", count: results.counts.articles },
          { value: "thesis", label: "学位论文", count: results.counts.theses },
          { value: "report", label: "研究报告", count: results.counts.reports },
        ]} />
        <FilterGroup title="理论流派" name="theory" selected={filters.theory ?? []} options={results.facets.theories} />
        <FilterGroup title="研究专题" name="topic" selected={filters.topic ?? []} options={results.facets.topics} collapsible />
        <FilterGroup title="文献标签" name="concept" selected={filters.concept ?? []} options={results.facets.concepts} collapsible />
        <FilterGroup title="作者" name="author" selected={filters.author ?? []} options={results.facets.authors} collapsible />
        <FilterGroup title="出版时间" name="year" selected={filters.year ?? []} options={results.facets.years} collapsible />
        <FilterGroup title="语言" name="language" selected={filters.language ?? []} options={results.facets.languages} collapsible />
        <FilterGroup title="开放状态" name="access" selected={filters.access ?? []} options={results.facets.access} collapsible />
        <button className="button filter-submit" type="submit">应用筛选</button>
      </form>
    </details>
  );
}

function SemanticMobileFilters({
  params,
  query,
  filters,
  results,
  activeFilterCount,
}: {
  params: RawSearchParams;
  query: string;
  filters: SearchFilters;
  results: SemanticSearchPayload;
  activeFilterCount: number;
}) {
  return (
    <details className="mobile-filter-disclosure">
      <summary>限定馆藏{activeFilterCount ? ` · 已选 ${activeFilterCount}` : ""}<span>展开</span></summary>
      <form action="/explore/opinions">
        {query ? <input type="hidden" name="q" value={query} /> : null}
        {entriesExcept(params, ["q", "document_type", "language", "theory", "topic", "concept", "author", "year", "access"]).map(([name, value]) => (
          <input type="hidden" name={name} value={value} key={`${name}-${value}`} />
        ))}
        <div className="filter-title">
          <strong>观点检索限定</strong>
          <Link href={buildExploreHref(params, {
            document_type: null,
            language: null,
            theory: null,
            topic: null,
            concept: null,
            author: null,
            year: null,
            access: null,
          })}>清除</Link>
        </div>
        <FilterGroup title="内容类型" name="document_type" selected={filters.documentType ?? []} options={results.facets.document_types} />
        <FilterGroup title="正文语言" name="language" selected={filters.language ?? []} options={results.facets.languages} />
        <FilterGroup title="作者与学者" name="author" selected={filters.author ?? []} options={results.facets.authors} collapsible />
        <FilterGroup title="出版时间" name="year" selected={filters.year ?? []} options={results.facets.years} collapsible />
        <FilterGroup title="理论流派" name="theory" selected={filters.theory ?? []} options={results.facets.theories} collapsible />
        <FilterGroup title="研究专题" name="topic" selected={filters.topic ?? []} options={results.facets.topics} collapsible />
        <FilterGroup title="文献标签" name="concept" selected={filters.concept ?? []} options={results.facets.concepts} collapsible />
        <FilterGroup title="开放状态" name="access" selected={filters.access ?? []} options={results.facets.access} collapsible />
        <button className="button filter-submit" type="submit">应用限定</button>
      </form>
    </details>
  );
}

function WorkResultGroup({
  title,
  works,
  href,
  action,
  empty,
}: {
  title: string;
  works: Awaited<ReturnType<typeof loadSearch>>["works"];
  href: string;
  action: string;
  empty: string;
}) {
  return (
    <div className="result-group">
      <SectionHeading title={title} href={href} action={action} />
      <div className="result-books">
        {works.map((work) => <BookCard work={work} exploreActions key={work.id} />)}
        {!works.length ? <p className="empty-state">{empty}</p> : null}
      </div>
    </div>
  );
}

function PassageResultGroup({
  passages,
  query,
  href,
  showAllLink,
}: {
  passages: Awaited<ReturnType<typeof loadSearch>>["passages"];
  query: string;
  href: string;
  showAllLink: boolean;
}) {
  return (
    <div className="result-group passage-result-group">
      <SectionHeading
        title="全文匹配"
        href={showAllLink ? href : undefined}
        action={showAllLink ? "查看全部全文结果" : undefined}
      />
      <div className="passage-results-list passage-results-table" role="table" aria-label="全文命中原文">
        <div className="passage-table-head" role="row">
          <span role="columnheader">页码</span>
          <span role="columnheader">来源与命中原文</span>
          <span role="columnheader">操作</span>
        </div>
        {passages.map((passage) => (
          <article className="fulltext-result passage-table-row" role="row" key={passage.id}>
            <div className="passage-table-page" role="cell">
              <strong>第 {passage.page_index} 页</strong>
              {passage.printed_label && passage.printed_label !== String(passage.page_index)
                ? <small>书页 {passage.printed_label}</small>
                : <small>PDF 页序</small>}
            </div>
            <div className="passage-table-copy" role="cell">
              <strong>{passage.title}</strong>
              <p className="muted-row">
                PDF 第 {passage.page_index} 页
                {passage.printed_label && passage.printed_label !== String(passage.page_index)
                  ? ` · 书页 ${passage.printed_label}`
                  : ""}
              </p>
              <blockquote>
                <Quote size={16} fill="currentColor" aria-hidden="true" />
                <span>{passage.snippet}</span>
              </blockquote>
            </div>
            <div className="passage-table-actions" role="cell">
              <details>
                <summary>查看上下文</summary>
                <p>{passage.snippet}</p>
              </details>
              <Link
                href={`/reader/${passage.asset_id}?page=${passage.page_index}&q=${encodeURIComponent(query)}&passage=${encodeURIComponent(passage.id)}`}
              >
                跳到 PDF <ArrowRight size={14} />
              </Link>
            </div>
          </article>
        ))}
        {!passages.length ? <p className="empty-state">没有找到公开全文中的匹配段落。</p> : null}
      </div>
    </div>
  );
}

function DirectoryResultGroup({
  title,
  items,
  basePath,
  href,
  action,
  empty,
}: {
  title: string;
  items: Awaited<ReturnType<typeof loadSearch>>["topics"];
  basePath: string;
  href: string;
  action?: string;
  empty: string;
}) {
  return (
    <div className="result-group directory-search-results">
      <SectionHeading title={title} href={href} action={action} />
      <div className="secondary-link-list">
        {items.map((item) => (
          <Link href={`${basePath}/${item.slug}`} key={item.slug}>
            <span className="theory-symbol">{item.name.slice(0, 2)}</span>
            <p><strong>{item.name}</strong><small>{item.description || "公开资料页"}</small></p>
            <ArrowRight size={16} />
          </Link>
        ))}
        {!items.length ? <p className="empty-state">{empty}</p> : null}
      </div>
    </div>
  );
}

function SearchPagination({
  current,
  total,
  params,
}: {
  current: number;
  total: number;
  params: RawSearchParams;
}) {
  if (total <= 1) return null;
  return (
    <nav className="search-pagination" aria-label="搜索结果分页">
      {current > 1 ? (
        <Link href={buildExploreHref(params, { page: String(current - 1) })}>
          <ArrowLeft size={15} />上一页
        </Link>
      ) : <span />}
      <span>第 {current} / {total} 页</span>
      {current < total ? (
        <Link href={buildExploreHref(params, { page: String(current + 1) })}>
          下一页<ArrowRight size={15} />
        </Link>
      ) : <span />}
    </nav>
  );
}

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function listParam(value: string | string[] | undefined) {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

function resultCount(counts: Awaited<ReturnType<typeof loadSearch>>["counts"]) {
  return counts.works + counts.scholars + counts.topics + counts.theories + counts.passages;
}

function scopeResultCount(
  scope: string,
  counts: Awaited<ReturnType<typeof loadSearch>>["counts"],
  paginationTotal: number,
) {
  if (scope === "all") return resultCount(counts);
  return {
    book: counts.books,
    article: counts.articles,
    thesis: counts.theses,
    report: counts.reports,
    scholar: counts.scholars,
    topic: counts.topics,
    theory: counts.theories,
    fulltext: counts.passages,
  }[scope] ?? paginationTotal;
}

function entriesExcept(params: RawSearchParams, excluded: string[]) {
  const entries: [string, string][] = [];
  Object.entries(params).forEach(([name, rawValue]) => {
    if (excluded.includes(name) || rawValue === undefined) return;
    listParam(rawValue).forEach((value) => entries.push([name, value]));
  });
  return entries;
}

function buildExploreHref(
  params: RawSearchParams,
  changes: Record<string, string | string[] | null | undefined>,
) {
  const output = new URLSearchParams();
  Object.entries(params).forEach(([name, rawValue]) => {
    if (name === "mode") return;
    listParam(rawValue).forEach((value) => output.append(name, value));
  });
  Object.entries(changes).forEach(([name, value]) => {
    if (name === "mode") return;
    output.delete(name);
    if (value === null || value === undefined || value === "") return;
    (Array.isArray(value) ? value : [value]).forEach((item) => output.append(name, item));
  });
  const queryString = output.toString();
  const mode = firstParam(params.mode);
  const basePath = mode === "semantic"
    ? "/explore/opinions"
    : mode === "ask"
      ? "/explore/ask"
      : "/explore/original";
  return queryString ? `${basePath}?${queryString}` : basePath;
}
