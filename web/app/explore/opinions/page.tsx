import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  FileSearch,
  Quote,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { SearchClickTracker, UsageTracker } from "@/components/usage-tracker";
import { SearchField } from "@/components/ui";
import {
  loadViewpointSearch,
  type SearchFilters,
  type ViewpointSearchPayload,
  type ViewpointSearchResult,
  type ViewpointStance,
} from "@/lib/server-api";
import styles from "./viewpoint-search.module.css";

export const metadata: Metadata = { title: "观点检索" };

type SearchParams = Record<string, string | string[] | undefined>;

const stanceSections: Array<{
  key: ViewpointStance;
  label: string;
  description: string;
}> = [
  { key: "direct", label: "直接回应", description: "原文直接讨论输入命题或其核心关系。" },
  { key: "support", label: "支持", description: "原文的论证方向支持输入命题。" },
  { key: "oppose", label: "相斥", description: "原文明确否定或提出相反判断。" },
  { key: "qualify", label: "限定或修正", description: "原文为命题补充条件、范围或例外。" },
  { key: "critique", label: "批评", description: "原文质疑命题的前提、解释或方法。" },
  { key: "extend", label: "延展", description: "原文把命题推进到新的机制或对象。" },
  { key: "reframe", label: "重新界定", description: "原文用另一套问题框架重新理解命题。" },
];

const attributionLabels: Record<string, string> = {
  author_claim: "作者主张",
  quoted_claim: "引述主张",
  reported_claim: "转述主张",
  criticized_claim: "被批评主张",
  historical_description: "历史描述",
  uncertain: "归因待核对",
};

export default async function OpinionSearchPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const query = firstParam(params.q).trim();
  const filters: SearchFilters = {
    documentType: listParam(params.document_type),
    language: listParam(params.language),
    author: listParam(params.author),
    year: listParam(params.year),
    theory: listParam(params.theory),
    topic: listParam(params.topic),
    concept: listParam(params.concept),
    access: listParam(params.access),
    sort: firstParam(params.sort) || "relevance",
  };
  const payload = await loadViewpointSearch(query, filters);
  const populatedSections = stanceSections.filter(
    ({ key }) => payload.groups[key].length > 0,
  );

  return (
    <>
      <UsageTracker
        eventType="search_submit"
        query={query}
        resultCount={payload.count}
        source="viewpoint_search_v3"
        scope="semantic"
      />
      <SearchClickTracker query={query} source="viewpoint_search_v3" />
      <div className={`page-shell explore-page ${styles.page}`}>
        <header className={styles.hero}>
          <div className={styles.intro}>
            <p className={styles.eyebrow}>馆藏原文 · 命题关系</p>
            <h1>观点检索</h1>
            <p>输入一个完整的社会科学命题。结果会区分直接回应、支持、相斥、限定与批评，并回到 PDF 页核对。</p>
          </div>
          <div className={styles.queryArea}>
            <form className={`explore-search ${styles.search}`} action="/explore/opinions">
              <SearchField defaultValue={query} placeholder="例如：市场化会削弱地方共同体的互助关系" />
              <button className="button" type="submit">查找馆藏观点</button>
            </form>
            <SearchModeSwitch query={query} />
          </div>
        </header>

        {query ? <QueryClaim payload={payload} /> : null}

        <section className={styles.relationshipIndex} aria-label="命题关系分组">
          {stanceSections.map((section) => {
            const count = payload.stance_counts[section.key] ?? 0;
            return count ? (
              <a data-stance={section.key} href={`#stance-${section.key}`} key={section.key}>
                <span>{section.label}</span><strong>{count}</strong>
              </a>
            ) : (
              <span data-stance={section.key} aria-disabled="true" key={section.key}>
                <span>{section.label}</span><strong>0</strong>
              </span>
            );
          })}
        </section>

        <div className={styles.layout}>
          <main className={styles.results}>
            <header className={styles.resultsHeader}>
              <div>
                <p>已验证馆藏定位</p>
                <h2>{query ? `${payload.work_count} 部作品 · ${payload.count} 条原文` : "等待输入命题"}</h2>
              </div>
              {query ? <span>{payload.default_mode === "claim" ? "Claim 排序" : "Semantic V2 基准排序"}</span> : null}
            </header>
            <p className={`${styles.notice} ${payload.service_unavailable || payload.fallback_used ? styles.warning : ""}`}>
              {payload.notice}
            </p>

            {populatedSections.map((section) => (
              <section className={styles.stanceSection} id={`stance-${section.key}`} key={section.key}>
                <header>
                  <span className={styles.stanceMarker} data-stance={section.key}>{section.label}</span>
                  <div><h2>{section.label}</h2><p>{section.description}</p></div>
                  <strong>{payload.groups[section.key].length}</strong>
                </header>
                <div className={styles.cardList}>
                  {payload.groups[section.key].map((item, index) => (
                    <EvidenceCard item={item} index={index} key={item.id} />
                  ))}
                </div>
              </section>
            ))}

            {query && !payload.count ? (
              <section className={styles.empty}>
                <FileSearch size={28} aria-hidden="true" />
                <h2>暂时没有可验证的原文</h2>
                <p>可以补充行动者、时间、地点或因果机制，也可以先到原文检索查看更宽的全文结果。</p>
                <Link className="button secondary" href={`/explore/original?context=global&q=${encodeURIComponent(query)}`}>
                  转到原文检索 <ArrowRight size={15} />
                </Link>
              </section>
            ) : null}
            {!query ? (
              <section className={styles.empty}>
                <Scale size={30} aria-hidden="true" />
                <h2>从一个可判断的命题开始</h2>
                <p>“社会资本”过于宽泛。“社会资本会提高社区灾后恢复能力”更适合比较支持、反对和限定证据。</p>
              </section>
            ) : null}
          </main>

          <aside className={styles.inspector}>
            <section>
              <ShieldCheck size={18} aria-hidden="true" />
              <h2>证据边界</h2>
              <p>页面只显示能够定位到当前 DocumentRevision、EvidenceSpan 和公开 PDF 页的馆藏原文。</p>
            </section>
            <section>
              <Scale size={18} aria-hidden="true" />
              <h2>关系判断</h2>
              <p>立场会同时核对否定、条件、归因和命题结构。语义相近不自动等于支持。</p>
            </section>
            <section>
              <BookOpen size={18} aria-hidden="true" />
              <h2>排序状态</h2>
              <dl>
                <div><dt>当前默认</dt><dd>{payload.default_mode === "claim" ? "Claim" : "Semantic V2"}</dd></div>
                <div><dt>Claim Engine</dt><dd>{payload.metadata.claim_ranking_status === "promoted" ? "已通过基准门槛" : "影子评估中"}</dd></div>
                <div><dt>定位校验</dt><dd>{payload.metadata.evidence_span_validation_required ? "必须通过" : "未启用"}</dd></div>
              </dl>
            </section>
          </aside>
        </div>
      </div>
      <SiteFooter />
    </>
  );
}

function SearchModeSwitch({ query }: { query: string }) {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return (
    <nav className="search-mode-switch" aria-label="检索方式">
      <Link href={`/explore/original?context=global${query ? `&q=${encodeURIComponent(query)}` : ""}`}><strong>原文检索</strong></Link>
      <Link className="active" href={`/explore/opinions${suffix}`}><strong>观点检索</strong></Link>
      <Link href={`/explore/ask${suffix}`}><strong>向书库提问</strong></Link>
    </nav>
  );
}

function QueryClaim({ payload }: { payload: ViewpointSearchPayload }) {
  const claim = payload.query_claim;
  const hasStructure = Boolean(claim.subject || claim.predicate || claim.object);
  return (
    <section className={styles.queryClaim} aria-label="查询命题理解">
      <div><span>输入命题</span><strong>{claim.proposition}</strong></div>
      {hasStructure ? (
        <dl>
          {claim.subject ? <div><dt>主体</dt><dd>{claim.subject}</dd></div> : null}
          {claim.predicate ? <div><dt>关系</dt><dd>{claim.predicate}</dd></div> : null}
          {claim.object ? <div><dt>对象</dt><dd>{claim.object}</dd></div> : null}
          <div><dt>方向</dt><dd>{claim.polarity === "negative" ? "否定" : claim.polarity === "positive" ? "肯定" : "待判断"}</dd></div>
        </dl>
      ) : <p>系统会从完整句子中比较立场、条件和归因。</p>}
    </section>
  );
}

function EvidenceCard({ item, index }: { item: ViewpointSearchResult; index: number }) {
  const authors = item.authors.length ? item.authors : item.evidence.source.authors;
  const printed = item.printed_page_label || item.evidence.locator.printed_page_label;
  const attribution = attributionLabels[item.attribution] ?? "归因待核对";
  const revision = item.evidence.source.document_revision;
  const extraction = String(item.evidence.provenance.extraction_method || "馆藏文本");
  return (
    <article className={styles.evidenceCard} data-stance={item.stance}>
      <header>
        <span>{String(index + 1).padStart(2, "0")}</span>
        <div>
          <p>{authors.length ? authors.join("、") : "责任者待核对"}</p>
          <h3>《{item.work.title}》</h3>
        </div>
        <strong>{item.stance_label}</strong>
      </header>
      <blockquote><Quote size={18} aria-hidden="true" /><p>{item.evidence.text}</p></blockquote>
      <div className={styles.locator}>
        <span>PDF 第 {item.page} 页</span>
        {printed && printed !== String(item.page) ? <span>印刷页 {printed}</span> : null}
        {item.evidence.locator.section ? <span>{item.evidence.locator.section}</span> : null}
        <span>{attribution}</span>
      </div>
      {item.stance_reasons.length ? (
        <p className={styles.reason}><strong>关系依据</strong>{item.stance_reasons.slice(0, 2).join("；")}</p>
      ) : null}
      <footer>
        <details>
          <summary>证据与版本</summary>
          <p>文本质量 {Math.round(item.quality_score * 100)}% · DocumentRevision {revision || "待核对"} · {extraction}</p>
        </details>
        <Link className="button secondary" href={item.reader_url}>
          查看原文并跳转 PDF <ArrowRight size={15} />
        </Link>
      </footer>
    </article>
  );
}

function firstParam(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function listParam(value: string | string[] | undefined): string[] {
  if (!value) return [];
  return (Array.isArray(value) ? value : [value])
    .flatMap((item) => item.split(","))
    .map((item) => item.trim())
    .filter(Boolean);
}
