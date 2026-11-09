import { EntityKnowledge } from "../work-knowledge";
import Link from "next/link";
import { ArrowRight, BookOpen, CircleDot, Layers3, Network, Search, UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import { ReadingPathCard, TheoryBanner } from "@/components/theory-system-ui";
import type { loadTheoryDisciplinePage } from "@/lib/api/knowledge.server";
import styles from "./discipline.module.css";

type DisciplinePagePayload = NonNullable<Awaited<ReturnType<typeof loadTheoryDisciplinePage>>>;
const photos = "/editorial/generated-20261030";
const disciplinePhotos: Record<string, string> = { sociology: "bookshelf", anthropology: "globe", ethnology: "branches" };
const nodePhotos = ["open-book", "book-spines", "stone-wall"];

export function DisciplinePublicView({ payload, activeType, slug, footer }: {
  payload: DisciplinePagePayload; activeType: string; slug: string; footer: ReactNode;
}) {
  const { discipline, counts } = payload;
  return <><article className={styles.page}>
    <header className={styles.hero} data-edit-section="identity">
      <div className={styles.heroCopy}>
        <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><Link href="/theories">理论流派</Link><span>›</span><span>{discipline.name}</span></nav>
        <h1>{discipline.name}</h1>
        {discipline.foreign_name ? <p className={styles.foreignName}>{discipline.foreign_name}</p> : null}
        {discipline.description ? <p className={styles.description}>{discipline.description}</p> : null}
        <form action="/theories/directory" className={styles.search}>
          <Search size={18} aria-hidden="true" /><input type="hidden" name="context" value="theories" /><input type="hidden" name="discipline" value={slug} />
          <input name="q" placeholder="搜索理论、别名或外文名" aria-label="搜索本学科理论" /><button type="submit">搜索</button>
        </form>
      </div>
      <div className={styles.heroPhoto}><TheoryBanner image={discipline.hero_image} media={discipline.cover_media} placement="detail" fallbackImage={`${photos}/${disciplinePhotos[slug] || "theories"}.webp`} /></div>
    </header>
    <nav className={styles.navigation} aria-label="学科内容分类">
      <Link aria-current={activeType === "theory_tradition" ? "page" : undefined} href={`/theories/disciplines/${slug}?type=theory_tradition`}><Network size={17} />理论传统{counts.theory_traditions ? <b>{counts.theory_traditions}</b> : null}</Link>
      <Link aria-current={activeType === "subdiscipline" ? "page" : undefined} href={`/subdisciplines?discipline=${encodeURIComponent(slug)}`}><Layers3 size={17} />子学科{counts.subdisciplines ? <b>{counts.subdisciplines}</b> : null}</Link>
      <Link aria-current={activeType === "debate" ? "page" : undefined} href={`/theories/disciplines/${slug}?type=debate`}><CircleDot size={17} />关键争论{counts.debates ? <b>{counts.debates}</b> : null}</Link>
      <Link href={`/explore?discipline=${encodeURIComponent(slug)}`}><BookOpen size={17} />全部馆藏{counts.works ? <b>{counts.works}</b> : null}</Link>
    </nav>
    <div className={styles.content} data-edit-section="content">
      <EntityKnowledge kind="discipline" id={discipline.id} />
      {payload.nodes.length ? <section className={styles.nodes} aria-label="学科条目">{payload.nodes.map((node, index) => <Link className={styles.node} href={`/theories/nodes/${node.slug}`} key={node.id}>
        <div className={styles.nodeImage}><TheoryBanner image={node.cover_url} media={node.cover_media} fallbackImage={`${photos}/${nodePhotos[index % nodePhotos.length]}.webp`} /></div>
        <div className={styles.nodeCopy}><h2>{node.canonical_name_zh}<ArrowRight size={18} /></h2>
        {node.canonical_name_en ? <small>{node.canonical_name_en}</small> : null}
        {node.period_label ? <small>{node.period_label}</small> : null}
        {node.core_questions?.[0] || node.summary ? <p>{node.core_questions?.[0] || node.summary}</p> : null}
        {node.representative_scholars?.length ? <small>{node.representative_scholars.map(person => person.name).join("、")}</small> : null}
        {node.work_count ? <small>{node.work_count} 部关联馆藏</small> : null}</div>
      </Link>)}</section> : <p className={styles.empty}>该分类尚无已审核并公开的条目。</p>}
      {payload.lineage.length ? <section className={styles.section}><header><h2>本学科脉络</h2><Link href={`/theories/timeline?discipline=${encodeURIComponent(slug)}`}>查看完整时间线<ArrowRight size={15} /></Link></header>
        <div className={styles.events}>{payload.lineage.slice(0, 8).map(event => <Link className={styles.event} href={`/theories/events/${event.id}`} key={event.id}><time>{event.date_label || event.start_year}</time><div><h3>{event.title}</h3><p>{event.description}</p></div></Link>)}</div>
      </section> : null}
      {payload.reading_paths.length ? <section className={styles.section}><header><h2>推荐阅读路径</h2></header><div className={styles.paths}>{payload.reading_paths.map(path => <ReadingPathCard key={path.id} path={path} />)}</div></section> : null}
      <nav className={styles.shortcuts} aria-label="理论系统快捷入口">
        <Link href={`/theories/timeline?discipline=${encodeURIComponent(slug)}`}><CircleDot />历史时间线<ArrowRight /></Link>
        <Link href={`/theories/graph?discipline=${encodeURIComponent(slug)}`}><Network />局部理论图谱<ArrowRight /></Link>
        {counts.scholars ? <Link href="/scholars?view=directory"><UsersRound />浏览学者<ArrowRight /></Link> : null}
      </nav>
    </div>
  </article>{footer}</>;
}
