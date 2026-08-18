import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CircleDot,
  Clock3,
  FileText,
  Layers3,
  Network,
  Search,
  UsersRound,
} from "lucide-react";
import type {
  KnowledgeNodeListItem,
  NormalizedReadingPath,
  TheoryDisciplineCompact,
  TheoryWorkCompact,
} from "@/lib/server-api";
import { ArchitecturalImage } from "./ui";

export const nodeTypeLabels: Record<string, string> = {
  theory_tradition: "理论传统",
  subdiscipline: "子学科",
  concept: "核心概念",
  debate: "理论争论",
  research_problem: "研究问题",
};

export const workRoleLabels: Record<string, string> = {
  foundational_work: "奠基性原著",
  systematic_exposition: "理论阐释与发展",
  theoretical_development: "理论阐释与发展",
  empirical_application: "经验应用",
  comparative_study: "经验应用",
  critique: "批评与反思",
  general_mention: "一般提及",
};

export function TheoryBanner({ image }: { image?: string }) {
  return image ? (
    <div className="theory-system-banner has-image" style={{ backgroundImage: `url("${image}")` }} />
  ) : (
    <div className="theory-system-banner"><ArchitecturalImage compact /></div>
  );
}

export function TheorySearchForm({ defaultValue = "", action = "/theories" }: { defaultValue?: string; action?: string }) {
  return (
    <form action={action} className="theory-system-search">
      <Search size={20} strokeWidth={1.6} />
      <input type="hidden" name="context" value="theories" />
      <input name="q" defaultValue={defaultValue} placeholder="搜索理论名称、别名或外文名" aria-label="搜索理论知识系统" />
      <button type="submit">搜索</button>
    </form>
  );
}

export function TheoryStat({ value, label, kind = "network" }: { value?: number; label: string; kind?: "network" | "layers" | "works" | "people" }) {
  if (!value) return null;
  const Icon = kind === "layers" ? Layers3 : kind === "works" ? BookOpen : kind === "people" ? UsersRound : Network;
  return <span className="theory-stat"><Icon size={21} /><b>{value.toLocaleString("zh-CN")}</b><small>{label}</small></span>;
}

export function DisciplineCard({
  discipline,
  counts,
}: {
  discipline: TheoryDisciplineCompact;
  counts: Partial<Record<"theory_traditions" | "subdisciplines" | "works", number>>;
}) {
  return (
    <Link className="theory-discipline-card" href={`/theories/disciplines/${discipline.slug}`}>
      <div className="theory-discipline-copy">
        <h2>{discipline.name}</h2>
        {discipline.description ? <p>{discipline.description}</p> : null}
      </div>
      <TheoryBanner image={discipline.hero_image} />
      <footer>
        <TheoryStat value={counts.theory_traditions} label="理论传统" />
        <TheoryStat value={counts.subdisciplines} label="子学科" kind="layers" />
        <TheoryStat value={counts.works} label="馆藏文献" kind="works" />
        <ArrowRight size={21} />
      </footer>
    </Link>
  );
}

export function KnowledgeNodeCard({ node }: { node: KnowledgeNodeListItem }) {
  const question = node.core_questions?.[0] || node.summary;
  const scholars = node.representative_scholars?.map((item) => item.name).join("、");
  const neighbors = node.related_disciplines?.map((item) => item.name).join("、");
  return (
    <Link className="theory-node-card" href={`/theories/nodes/${node.slug}`}>
      <header>
        <span className="theory-node-symbol"><CircleDot size={21} /></span>
        <div>
          <h3>{node.canonical_name_zh}</h3>
          {node.canonical_name_en ? <small>{node.canonical_name_en}</small> : null}
        </div>
        {node.period_label ? <time>{node.period_label}</time> : null}
      </header>
      {question ? <p>{question}</p> : null}
      <dl>
        {scholars ? <><dt>代表学者</dt><dd>{scholars}</dd></> : null}
        {node.work_count ? <><dt>关联馆藏</dt><dd>{node.work_count.toLocaleString("zh-CN")}</dd></> : null}
        {neighbors ? <><dt>关联学科</dt><dd>{neighbors}</dd></> : null}
      </dl>
      <ArrowRight className="card-arrow" size={19} />
    </Link>
  );
}

export function ReadingPathCard({ path }: { path: NormalizedReadingPath }) {
  return (
    <Link className="theory-reading-path-card" href={`/theories/reading-paths/${path.slug}`}>
      <span className="path-icon"><BookOpen size={23} /></span>
      <span>
        <strong>{path.title}</strong>
        {path.introduction ? <small>{path.introduction}</small> : null}
        <em>{[path.audience, path.estimated_reading].filter(Boolean).join(" · ")}</em>
      </span>
      <ArrowRight size={20} />
    </Link>
  );
}

export function WorkCompactCard({ work, role }: { work: TheoryWorkCompact; role?: string }) {
  const href = work.detail_href || work.reader_href || "/explore";
  return (
    <Link className="theory-work-compact" href={href}>
      <span className={work.cover_url ? "work-cover has-image" : "work-cover"} style={work.cover_url ? { backgroundImage: `url("${work.cover_url}")` } : undefined}>
        {!work.cover_url ? <FileText size={24} /> : null}
      </span>
      <span>
        {role ? <small>{role}</small> : null}
        <strong>{work.title}</strong>
        <em>{[work.author, work.year].filter(Boolean).join(" · ")}</em>
      </span>
      <ArrowRight size={17} />
    </Link>
  );
}

export function TheoryEmpty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="theory-empty" role="status">
      <Clock3 size={24} />
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

export function TheorySectionHeading({ title, href, action = "查看全部" }: { title: string; href?: string; action?: string }) {
  return (
    <header className="theory-section-heading">
      <h2>{title}</h2>
      {href ? <Link href={href}>{action}<ArrowRight size={16} /></Link> : null}
    </header>
  );
}
