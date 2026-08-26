import Link from "next/link";
import { ArrowRight, BookOpen, Check, Circle, Clock3, GraduationCap } from "lucide-react";
import type { ReactNode } from "react";
import { TheoryBanner, WorkCompactCard } from "@/components/theory-system-ui";
import type { loadNormalizedReadingPath } from "@/lib/server-api";

type ReadingPathPayload = NonNullable<Awaited<ReturnType<typeof loadNormalizedReadingPath>>>;

export function ReadingPathPublicView({ path, footer }: { path: ReadingPathPayload; footer: ReactNode }) {
  const learningGoal = path.learning_goal || path.introduction;

  return (
    <>
      <main className="page-shell theory-system-page theory-reading-path-page">
        <div className="theory-breadcrumb"><Link href="/theories">探索理论流派</Link><span>/</span><strong>{path.title}</strong></div>
        <section className="reading-path-hero"><div><p className="eyebrow">精选阅读路径</p><h1>{path.title}</h1>{path.learning_goal && path.introduction ? <p>{path.introduction}</p> : null}<dl>{learningGoal ? <><dt><GraduationCap size={17} />学习目标</dt><dd>{learningGoal}</dd></> : null}{path.primary_discipline_data ? <><dt><GraduationCap size={17} />主要学科</dt><dd>{path.primary_discipline_data.name}</dd></> : null}{path.audience ? <><dt>适合人群</dt><dd>{path.audience}</dd></> : null}{path.difficulty ? <><dt>阅读难度</dt><dd>{difficultyLabel(path.difficulty)}</dd></> : null}{path.estimated_reading ? <><dt><Clock3 size={17} />预计阅读量</dt><dd>{path.estimated_reading}</dd></> : null}</dl></div><TheoryBanner image={path.cover_url} /></section>
        <section className="reading-path-stages">
          {path.items.length ? path.items.map((item, index) => <article key={item.id}>
            <div className="stage-index"><b>{index + 1}</b><span>{item.is_required ? <><Check size={14} />必读</> : <><Circle size={12} />选读</>}</span></div>
            <div className="stage-copy"><p className="eyebrow">{item.stage_name}</p><h2>{item.work_data?.title || item.node_data?.canonical_name_zh || `第 ${index + 1} 阶段`}</h2><p>{item.stage_description}</p>{item.recommendation_reason ? <blockquote>{item.recommendation_reason}</blockquote> : null}{item.prerequisite || item.editorial_note ? <small>{item.prerequisite ? "先修条件" : "编辑说明"}　{item.prerequisite || item.editorial_note}</small> : null}{item.prerequisite && item.editorial_note ? <small>编辑说明　{item.editorial_note}</small> : null}</div>
            <div className="stage-target">{item.work_data ? <WorkCompactCard work={item.work_data} /> : item.node_data ? <Link href={`/theories/nodes/${item.node_data.slug}`}><BookOpen size={22} /><span><strong>{item.node_data.canonical_name_zh}</strong><small>{item.node_data.summary}</small></span><ArrowRight size={18} /></Link> : null}</div>
          </article>) : <p className="empty-state">该阅读路径尚未配置公开阅读项目。</p>}
        </section>
      </main>
      {footer}
    </>
  );
}

function difficultyLabel(value: string) {
  return value === "advanced" ? "深入" : value === "intermediate" ? "进阶" : "入门";
}
