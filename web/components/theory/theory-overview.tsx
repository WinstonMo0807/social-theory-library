import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { loadTheorySystemNodesPage, loadTheorySystemOverview } from "@/lib/api/knowledge.server";
import { searchPage } from "@/lib/search-context";
import styles from "./theory-overview.module.css";

export type TheoryOverviewSearchParams = {
  q?: string | string[]; discipline?: string | string[]; page?: string | string[];
};
const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value)?.trim() || "";
const photos = "/editorial/generated-20261030";
const disciplinePhotos = ["bookshelf", "globe", "branches"];
const theoryPhotos = ["open-book", "book-spines", "stone-wall"];
const nodeLabels: Record<string, string> = { theory_tradition: "理论传统", subdiscipline: "子学科", concept: "核心概念", debate: "关键争论", research_problem: "研究问题" };
const further = [
  { title: "理论传统", description: "重要的理论谱系与发展脉络。", href: "/theories/directory?type=theory_tradition", photo: "reading" },
  { title: "子学科", description: "相关的学科分支与交叉领域。", href: "/subdisciplines", photo: "library" },
  { title: "关键争论", description: "持续的学术讨论与理论分歧。", href: "/theories/directory?type=debate", photo: "book-stack" },
];

function PhotoCard({ href, title, description, photo, compact = false, label }: {
  href: string; title: string; description: string; photo: string; compact?: boolean; label?: string;
}) {
  return <Link className={`${styles.card}${compact ? ` ${styles.compact}` : ""}`} href={href}>
    <span className={styles.cardPhoto} aria-hidden="true" style={{ backgroundImage: `url("${photos}/${photo}.webp")` }} />
    <span className={styles.cardCopy}>{label ? <small className={styles.nodeLabel}>{label}</small> : null}<strong>{title}</strong>{description ? <span>{description}</span> : <span className={styles.missingSummary}>简介尚未发布</span>}</span>
    <ArrowRight size={17} strokeWidth={1.6} className={styles.arrow} aria-hidden="true" />
  </Link>;
}

export async function TheoryOverviewPage({ searchParams, actionPath = "/theory-schools" }: {
  searchParams: Promise<TheoryOverviewSearchParams>; actionPath?: "/theory-schools" | "/theories";
}) {
  const params = await searchParams, query = first(params.q), discipline = first(params.discipline), page = searchPage(params.page);
  const [overviewResult, nodesResult] = await Promise.allSettled([
    loadTheorySystemOverview(),
    loadTheorySystemNodesPage({ ...(query ? {} : { type: "theory_tradition", has_works: "true" }), q: query, discipline, sort: "name" }, page),
  ]);
  const overview = overviewResult.status === "fulfilled" ? overviewResult.value : null;
  const nodePage = nodesResult.status === "fulfilled" ? nodesResult.value : null;
  const retry = new URLSearchParams({ ...(query ? { q: query } : {}), ...(discipline ? { discipline } : {}), ...(page > 1 ? { page: String(page) } : {}) });
  const retryHref = `${actionPath}${retry.size ? `?${retry}` : ""}`;
  const selectedDiscipline = overview?.disciplines.find(item => item.slug === discipline);

  return <>
    <div className={styles.page}>
      <section className={styles.hero} aria-labelledby="theory-overview-title">
        <picture className={styles.heroPhoto}>
          <Image src="/editorial/generated-20261030/theories.webp" alt="" width={1536} height={1024} priority unoptimized sizes="(max-width: 700px) 100vw, 55vw" />
        </picture>
        <div className={styles.heroCopy}>
          <h1 id="theory-overview-title">理论流派</h1>
          <p>梳理社会理论发展的主要流派与传统，<br className={styles.desktopBreak} />理解不同理论取向的核心观点、历史脉络<br className={styles.desktopBreak} />及其在当代的影响与对话。</p>
          <form className={styles.search} action={actionPath} role="search" aria-label="搜索理论流派与概念">
            <Search size={20} strokeWidth={1.7} aria-hidden="true" />
            <input type="search" name="q" defaultValue={query} placeholder="搜索流派名称、核心概念、代表学者…" aria-label="流派名称、核心概念或代表学者" />
            {discipline ? <input type="hidden" name="discipline" value={discipline} /> : null}
            <button type="submit">搜索</button>
          </form>
        </div>
      </section>

      <div className={styles.content}>
        <section className={styles.section} aria-labelledby="theory-disciplines-title">
          <h2 id="theory-disciplines-title">主要学科领域</h2>
          {overview ? overview.disciplines.length ? <div className={styles.grid}>
            {overview.disciplines.map((item, index) => <PhotoCard key={item.id}
              href={`/theories/disciplines/${encodeURIComponent(item.slug)}`} title={item.name}
              description={item.description} photo={disciplinePhotos[index % disciplinePhotos.length]} />)}
          </div> : <p className={styles.state} role="status">学科资料尚未发布。公开条目建立后，将在这里形成学科入口。</p>
            : <div className={styles.state} role="alert"><p>学科资料暂时无法读取。下方仍可浏览已经读取的馆藏理论。</p><a href={retryHref}>重新载入学科资料</a></div>}
        </section>

        <section className={styles.section} aria-labelledby="theory-collection-title">
          <header className={styles.sectionHeading}><h2 id="theory-collection-title">{query ? "搜索结果" : "馆藏理论流派"}</h2>
            {query || discipline ? <Link href={actionPath}>清除筛选<ArrowRight size={14} aria-hidden="true" /></Link> : null}
          </header>
          {query || discipline ? <p className={styles.query}>{
            [query ? `搜索：${query}` : "", discipline ? `学科：${selectedDiscipline?.name || discipline}` : ""].filter(Boolean).join(" · ")
          }{nodePage ? ` · 共 ${nodePage.count} 个公开条目` : ""}</p> : null}
          {nodePage ? nodePage.results.length ? <div className={styles.grid}>
            {nodePage.results.map((node, index) => <PhotoCard key={node.id}
              href={`/theories/nodes/${encodeURIComponent(node.slug)}`} title={node.canonical_name_zh || node.canonical_name_en}
              description={node.summary} photo={theoryPhotos[index % theoryPhotos.length]} label={query ? nodeLabels[node.node_type] : undefined} />)}
          </div> : <div className={styles.state} role="status"><p>{query
            ? "没有找到符合条件的公开理论条目。可调整名称、概念或学者关键词后再次搜索。"
            : discipline ? "当前学科暂无关联公开馆藏的理论流派。可清除学科筛选后继续浏览。"
            : "暂无关联公开馆藏的理论流派。已审核条目与馆藏建立公开关联后，会显示在这里。"}</p>
            <Link href="/theories/directory?type=theory_tradition">浏览全部公开理论传统<ArrowRight size={14} aria-hidden="true" /></Link>
          </div> : <div className={styles.state} role="alert"><p>馆藏理论暂时无法读取。请稍后重试，当前状态不能判断馆藏是否为空。</p><a href={retryHref}>重新载入馆藏理论</a></div>}
          {nodePage ? <div className={styles.pagination}><ScopedSearchPagination path={actionPath} context="theories" page={page}
            totalPages={nodePage.totalPages} params={{ q: query, discipline }} /></div> : null}
        </section>

        <nav className={styles.section} aria-labelledby="theory-further-title">
          <h2 id="theory-further-title">进一步浏览</h2>
          <div className={styles.grid}>{further.map(item => <PhotoCard key={item.href} {...item} compact />)}</div>
        </nav>
      </div>
    </div>
  </>;
}
