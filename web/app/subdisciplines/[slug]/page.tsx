import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, CalendarDays, CircleDot, Layers3, MessagesSquare, Wrench } from "lucide-react";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { SiteFooter } from "@/components/site-footer";
import { ArchitecturalImage, BookCover, SectionHeading } from "@/components/ui";
import { loadSubdiscipline } from "@/lib/server-api";

export const metadata: Metadata = { title: "子学科详情" };

export default async function SubdisciplinePage({ params }: { params: Promise<{ slug: string }> }) {
  const item = await loadSubdiscipline((await params).slug);
  if (!item) notFound();
  return (
    <>
      <main className="page-shell subdiscipline-page">
        <p className="breadcrumb">理论流派　/　{item.discipline.name}　/　子学科　/　{item.name}</p>
        <section className="subdiscipline-hero">
          <div><p className="eyebrow">{item.discipline.name}</p><h1>{item.name}</h1><p>{item.description || item.research_object}</p></div>
          <div className={item.hero_image ? "knowledge-hero-image has-image" : "knowledge-hero-image"} style={item.hero_image ? { backgroundImage: `url("${item.hero_image}")` } : undefined}>{!item.hero_image ? <ArchitecturalImage compact /> : null}</div>
        </section>
        <section className="subdiscipline-facts">
          <article><CircleDot /><span><small>研究对象</small><strong>{item.research_object || "待管理员补充"}</strong></span></article>
          <article><CalendarDays /><span><small>形成时期</small><strong>{item.formation_period || "待考"}</strong></span></article>
          <article><Layers3 /><span><small>相关理论</small><strong>{item.theories.map((theory) => theory.name).slice(0, 3).join("、") || "尚未确认"}</strong></span></article>
          <article><BookOpen /><span><small>馆藏文献</small><strong>{item.works.length}</strong></span></article>
        </section>
        <div className="subdiscipline-detail-grid">
          <KnowledgeList icon={<CircleDot />} title="研究对象与核心问题" items={item.core_questions} />
          <KnowledgeList icon={<CalendarDays />} title="形成与发展" items={item.formation_period ? [item.formation_period] : []} />
          <KnowledgeList icon={<Layers3 />} title="主要研究方向" items={item.research_directions} />
          <KnowledgeList icon={<Wrench />} title="常用方法" items={item.methods} />
          <KnowledgeList icon={<MessagesSquare />} title="代表性议题" items={item.representative_issues} />
          <section className="panel knowledge-list-card"><SectionHeading title="相关理论传统" /><div className="tag-list">{item.theories.map((theory) => <Link href={`/theory-schools/${theory.slug}`} key={theory.id}>{theory.name}</Link>)}</div></section>
        </div>
        <section className="panel subdiscipline-reading">
          <SectionHeading title="精选文献导读" href={`/explore?subdiscipline=${item.slug}`} action="查看全部" />
          <div>{item.works.slice(0, 8).map((work) => <Link href={`/works/${work.slug}`} key={work.id}><BookCover work={work} size="small" /><span><strong>{work.title}</strong><small>{work.author}</small><time>{work.year}</time></span><ArrowRight /></Link>)}</div>
          {!item.works.length ? <p className="empty-state">审核 PDF 的知识归位后，相关馆藏会自动汇入这里。</p> : null}
        </section>
      </main>
      <SiteFooter />
    </>
  );
}

function KnowledgeList({ icon, title, items }: { icon: ReactNode; title: string; items: string[] }) {
  return <section className="panel knowledge-list-card"><header>{icon}<h2>{title}</h2></header>{items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="empty-state">待管理员编辑确认。</p>}</section>;
}
