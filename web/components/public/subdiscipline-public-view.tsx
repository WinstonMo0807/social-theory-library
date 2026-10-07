import Link from "next/link";
import { CollectionLink } from "@/components/collection-link";
import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { BookCover } from "@/components/ui";
import type { loadSubdiscipline } from "@/lib/api/taxonomy.server";

type SubdisciplinePayload = NonNullable<Awaited<ReturnType<typeof loadSubdiscipline>>>;

export function SubdisciplinePublicView({ item, footer }: { item: SubdisciplinePayload; footer: ReactNode }) {
  const firstTheory = item.theories[0];
  const firstScholar = item.scholars?.[0];
  const firstWork = item.works[0];
  return <>
    <main className="page-shell subdiscipline-page subdiscipline-reference-page v307-knowledge">
      <section className="taxonomy-public-hero">
        <div><nav className="taxonomy-public-breadcrumb" aria-label="当前位置"><Link href="/">首页</Link><span>›</span><Link href="/theories">理论流派</Link><span>›</span><Link href={`/theories/disciplines/${item.discipline.slug}`}>{item.discipline.name}</Link><span>›</span><strong>{item.name}</strong></nav><h1 data-edit-section="identity">{item.name}</h1><p className="taxonomy-public-parent">隶属于：{item.discipline.name}</p><p data-edit-section="content">{item.description}</p></div>
        <div className="taxonomy-public-image" data-edit-section="media" style={{backgroundImage:item.hero_image ? `url("${item.hero_image}")` : "none"}} aria-label={item.hero_image ? `${item.name}配图` : undefined}/>
      </section>
      <section className="taxonomy-public-questions" data-edit-section="questions"><h2>研究问题</h2>{item.core_questions.length ? <p>{item.core_questions.join(" ")}</p> : null}</section>
      <section className="taxonomy-public-related" data-edit-section="relations">
        <article><h2>相关理论</h2>{firstTheory ? <><Link href={`/theory-schools/${firstTheory.slug}`}><strong>{firstTheory.name}</strong></Link><RelatedMore title="相关理论">{item.theories.map(theory=><Link key={theory.id} href={`/theory-schools/${theory.slug}`}>{theory.name}</Link>)}</RelatedMore></> : null}</article>
        <article><h2>相关学者</h2>{firstScholar ? <><Link href={`/scholars/${firstScholar.slug}`}><strong>{firstScholar.name}</strong></Link><RelatedMore title="相关学者">{item.scholars.map(scholar=><Link key={scholar.id} href={`/scholars/${scholar.slug}`}>{scholar.name}</Link>)}</RelatedMore></> : null}</article>
        <article><h2>相关馆藏</h2>{firstWork ? <><CollectionLink className="taxonomy-public-work" href={`/works/${firstWork.slug}`}>{firstWork.coverImage ? <BookCover work={firstWork} size="small"/> : <div className="taxonomy-missing-work-cover"/>}<span><strong>{firstWork.title}</strong>{firstWork.author ? <small>{firstWork.author}</small> : null}{firstWork.publisher || firstWork.year ? <small>{[firstWork.publisher,firstWork.year ? `${firstWork.year}年版` : ""].filter(Boolean).join(" ")}</small> : null}</span></CollectionLink><Link className="taxonomy-related-more" href={`/explore?subdiscipline=${encodeURIComponent(item.slug)}`}>查看更多 <ArrowRight size={16}/></Link></> : null}</article>
      </section>
    </main>
    {footer}
  </>;
}
function RelatedMore({title,children}: {title:string;children:ReactNode}) {
  return <details className="taxonomy-related-more"><summary aria-label={`查看更多${title}`}>查看更多 <ArrowRight size={16}/></summary><div>{children}</div></details>;
}
