import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import type { ReactNode } from "react";
import { TheoryBanner, WorkCompactCard } from "@/components/theory-system-ui";
import type { loadNormalizedReadingPath } from "@/lib/api/knowledge.server";

type ReadingPathPayload = NonNullable<Awaited<ReturnType<typeof loadNormalizedReadingPath>>>;

export function ReadingPathPublicView({ path, footer, previewStage }: { path: ReadingPathPayload; footer: ReactNode; previewStage?: number }) {
  const stages = Array.from(new Map(path.items.map(item => [item.stage || item.stage_name, {id:item.stage || item.stage_name,name:item.stage_name}])).values());
  const stageItems = (id: string) => path.items.filter(item => (item.stage || item.stage_name) === id);

  return (
    <>
      <main className="page-shell theory-system-page theory-reading-path-page v307-knowledge">
        <section className="reading-path-reference-hero" data-edit-section="identity"><TheoryBanner image={path.cover_url} media={path.cover_media}/><div><h1>{path.title}</h1>{path.learning_goal ? <p>{path.learning_goal}</p> : null}</div></section>
        {path.introduction ? <p className="reading-path-reference-introduction" data-edit-section="identity">{path.introduction}</p> : null}
        <section className="reading-path-reference-stages" data-edit-section="paths" style={stages.length && stages.length <= 3 ? {gridTemplateColumns:stages.map(stage => `minmax(0,${1 + Math.min(2,Math.max(0,stageItems(stage.id).length - 1)) * .5}fr)`).join(" ")} : undefined}>
          {stages.length ? stages.map((stage,index)=>{const items=stageItems(stage.id);return <article key={stage.id} data-preview-selected={previewStage === index || undefined}><h2>{["一","二","三","四","五","六","七","八","九","十"][index] || index+1}、{stage.name}</h2>{items[0]?.stage_description ? <p>{items[0].stage_description}</p> : null}<div className="reading-path-reference-books">{items.map(item=><div key={item.id} data-edit-row={path.items.indexOf(item)}>{item.work_data ? <><WorkCompactCard work={{...item.work_data,title:item.work_data.title.startsWith("《") ? item.work_data.title : `《${item.work_data.title}》`,author:item.work_data.author ? `${item.work_data.author} 著` : "",year:null}}/><small className="reading-path-book-publication">{[item.work_data.publisher,item.work_data.year ? `${item.work_data.year} 年版` : ""].filter(Boolean).join(" · ")}</small></> : item.node_data ? item.node_data.slug ? <Link href={`/theories/nodes/${item.node_data.slug}`}><BookOpen size={22}/><strong>{item.node_data.canonical_name_zh}</strong><ArrowRight size={15}/></Link> : <strong>{item.node_data.canonical_name_zh}</strong> : null}</div>)}</div></article>;}) : <p className="empty-state">该阅读路径尚未配置公开阅读项目。</p>}
        </section>
        <section className="reading-path-reference-topics"><h2>相关主题</h2><div aria-hidden="true"/></section>
      </main>
      {footer}
    </>
  );
}
