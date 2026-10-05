import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import type { ReactNode } from "react";
import { TheoryBanner, WorkCompactCard } from "@/components/theory-system-ui";
import type { loadNormalizedReadingPath } from "@/lib/api/knowledge.server";

type ReadingPathPayload = NonNullable<Awaited<ReturnType<typeof loadNormalizedReadingPath>>>;

export function ReadingPathPublicView({ path, footer }: { path: ReadingPathPayload; footer: ReactNode }) {
  const stages = Array.from(new Set(path.items.map(item=>item.stage_name)));

  return (
    <>
      <main className="page-shell theory-system-page theory-reading-path-page v307-knowledge">
        <div className="theory-breadcrumb"><Link href="/theories">探索理论流派</Link><span>/</span><strong>{path.title}</strong></div>
        <section className="reading-path-reference-hero" data-edit-section="identity"><TheoryBanner image={path.cover_url} media={path.cover_media}/><div><h1>{path.title}</h1>{path.learning_goal ? <p>{path.learning_goal}</p> : null}</div></section>
        {path.introduction ? <p className="reading-path-reference-introduction" data-edit-section="identity">{path.introduction}</p> : null}
        <section className="reading-path-reference-stages" data-edit-section="paths">
          {stages.length ? stages.map((name,index)=>{const items=path.items.filter(item=>item.stage_name===name);return <article key={name}><h2>{index+1}、{name}</h2>{items[0]?.stage_description ? <p>{items[0].stage_description}</p> : null}<div className="reading-path-reference-books">{items.map(item=><div key={item.id} data-edit-row={path.items.indexOf(item)}>{item.work_data ? <WorkCompactCard work={item.work_data}/> : item.node_data ? <Link href={`/theories/nodes/${item.node_data.slug}`}><BookOpen size={22}/><strong>{item.node_data.canonical_name_zh}</strong><ArrowRight size={15}/></Link> : null}{item.recommendation_reason ? <p>{item.recommendation_reason}</p> : null}{item.prerequisite ? <small>前置阅读：{item.prerequisite}</small> : null}</div>)}</div></article>;}) : <p className="empty-state">该阅读路径尚未配置公开阅读项目。</p>}
        </section>
        {[path.audience,path.estimated_reading].some(Boolean) ? <details className="reading-path-reference-details"><summary>阅读安排</summary><p>{[path.audience,difficultyLabel(path.difficulty),path.estimated_reading].filter(Boolean).join(" · ")}</p></details> : null}
      </main>
      {footer}
    </>
  );
}

function difficultyLabel(value: string) {
  return value === "advanced" ? "深入" : value === "intermediate" ? "进阶" : "入门";
}
