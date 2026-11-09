"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { SectionHeading } from "../ui";
import { IssueBlockView } from "./issue-block-view";
import type { IssueBlock } from "@/lib/api/recommendation-issues.types";

export type KnowledgeBlock = Omit<Partial<IssueBlock>, "references" | "target"> & { id: string; text?: string; references?: { type: string; id: string; edition_id?: string }[] };
export type KnowledgeAssertion = {
  id: string; text: string; conditions?: Record<string, string>; source_quality?: string;
  sources: { work__title: string; attribution__label: string | null; expression: string; citation?: string }[];
  evidence: { anchor_id: string; stance: string; locator?: {
    reader_url: string; document_revision_id?: string; segments: { exact: string; page_number: number; printed_label?: string; start?: number; end?: number }[];
  } }[];
};
export type KnowledgePageData = {
  id: string; title?: string; scope?: string; blocks: KnowledgeBlock[]; assertions: KnowledgeAssertion[];
  references?: { type: string; id: string; title: string; href?: string | null; work_url?: string; edition_label?: string; unavailable?: boolean }[];
  revision_id?: string | null; status?: string;
  publication_scope?: { withdrawals?: { id: string; text: string; reason: string }[]; entities: { id: string; label: string; kind: string }[] };
  anchors?: { anchor_id: string; locator?: { reader_url: string; segments: { exact: string; page_number: number; printed_label?: string }[] } }[];
};

// The editor supplies the same content to this renderer, without fetching or publishing it.
export function KnowledgePageContent({ page, renderBlock }: {
  page: Pick<KnowledgePageData, "blocks" | "assertions" | "anchors" | "references">;
  renderBlock?: (block: KnowledgeBlock, content: ReactNode) => ReactNode;
}) {
  return <section className="detail-section work-curated-claims"><SectionHeading title="知识导读" />
    {page.blocks.map(block => {
      const anchors = (page.anchors || []).filter(a => block.references?.some(r => r.type === "anchor" && r.id === a.anchor_id));
      const assertions = page.assertions.filter(a => block.references?.some(r => r.type === "assertion" && r.id === a.id));
      const references = page.references?.filter(r => !["anchor", "assertion"].includes(r.type) && block.references?.some(v => v.type === r.type && v.id === r.id)) || [];
      const repeated = assertions.length === 1 && block.text?.trim() === assertions[0].text.trim();
      const content = <div key={block.id}>{!repeated && <IssueBlockView block={{ ...block, type: block.type || "analysis", text: block.text || "", references: undefined }} />}
        {!!assertions.length && <div className="work-curated-claim-list">{assertions.map(assertion => <KnowledgeAssertionContent key={assertion.id} assertion={assertion} />)}</div>}
        {!!references.length && <details className="work-curated-evidence"><summary>相关资料 · {references.length} 项</summary>{references.map(ref => {
          const href = ref.href || ref.work_url || "";
          return <p key={`${ref.type}:${ref.id}`}>{!ref.unavailable && /^\/(?!\/)/.test(href) ? <Link href={href}>{ref.title}</Link> : ref.title}{ref.edition_label ? ` · ${ref.edition_label}` : ""}</p>;
        })}</details>}
        {!!anchors.length && <details className="work-curated-evidence"><summary>原文依据 · {anchors.length} 处</summary>{anchors.map(a => a.locator ? <blockquote key={a.anchor_id}><p style={{ whiteSpace: "pre-wrap" }}>{a.locator.segments.map(v => v.exact).join("\n")}</p><footer><span>{a.locator.segments.map(v => v.printed_label ? `${v.printed_label} · PDF ${v.page_number}` : `PDF ${v.page_number}`).join("、")}</span> <Link href={a.locator.reader_url}>查看原文 <ArrowRight size={14} /></Link></footer></blockquote> : <p key={a.anchor_id}><Link href={`/login?next=${encodeURIComponent(typeof window === "undefined" ? "/home" : window.location.pathname)}`}>登录后查看原文依据</Link></p>)}</details>}
      </div>;
      return renderBlock ? renderBlock(block, content) : content;
    })}
  </section>;
}

export function KnowledgeAssertionContent({ assertion }: { assertion: KnowledgeAssertion }) {
  const hasCitation = assertion.sources.some(s => s.citation || s.work__title);
  return <div data-ui-scope="editorial-v2"><article>
    <p className="work-curated-proposition">{assertion.text}</p>
    <p className="work-curated-note">{assertion.sources.map(s => [s.attribution__label, s.work__title].filter(Boolean).join(" · ")).join("；")}</p>
    {assertion.conditions && Object.values(assertion.conditions).some(Boolean) && <p className="work-curated-note">{Object.entries(assertion.conditions).filter(([, value]) => value).map(([key, value]) => `${({ time: "时间", region: "地区", population: "人群", research_object: "研究对象", concept_usage: "概念用法", other: "其他限定" } as Record<string, string>)[key] || key}：${typeof value === "string" ? value : JSON.stringify(value)}`).join("；")}</p>}
    <details className="work-curated-evidence"><summary>查看依据 <span>{assertion.evidence.length ? `${assertion.evidence.length} 条馆藏原文` : hasCitation ? "文献出处 · 未核验精确原文" : "历史人工内容 · 原出处待补"}</span></summary><div>
      {!hasCitation && !assertion.evidence.length && <p>原人工确认记录已保留，尚缺可核对的文献出处。</p>}
      {assertion.sources.filter(s => s.citation || s.work__title).map((source, i) => <p key={i}>{source.citation || `《${source.work__title}》；具体版本与原文位置尚待核验。`}</p>)}
      {assertion.evidence.map(e => e.locator ? <blockquote key={`${e.anchor_id}:${e.stance}`}><small>{({ supports: "支持", opposes: "反对", qualifies: "限定", context: "语境" } as Record<string, string>)[e.stance] || e.stance}</small>
        <p>{e.locator.segments.map(s => s.exact).join("\n")}</p><footer><span>{e.locator.segments.map(s => s.printed_label ? `${s.printed_label} · PDF 第 ${s.page_number} 页` : `PDF 第 ${s.page_number} 页`).join("、")}</span><Link href={e.locator.reader_url}>查看原文 <ArrowRight size={14} /></Link></footer>
      </blockquote> : <p key={e.anchor_id}><Link href={`/login?next=${encodeURIComponent(typeof window === "undefined" ? "/home" : window.location.pathname)}`}>登录后查看原文依据</Link></p>)}
    </div></details>
  </article></div>;
}
