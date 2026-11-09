"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { SectionHeading } from "../ui";
import { IssueBlockView } from "./issue-block-view";
import type { IssueBlock } from "@/lib/api/recommendation-issues.types";

export type KnowledgeBlock = Omit<Partial<IssueBlock>, "references" | "target"> & { id: string; text?: string; references?: { type: string; id: string; edition_id?: string }[] };
export type KnowledgeAssertion = {
  id: string; text: string;
  sources: { work__title: string; attribution__label: string | null; expression: string }[];
  evidence: { anchor_id: string; stance: string; locator?: {
    reader_url: string; segments: { exact: string; page_number: number; printed_label?: string }[];
  } }[];
};
export type KnowledgePageData = {
  id: string; title?: string; blocks: KnowledgeBlock[]; assertions: KnowledgeAssertion[];
  revision_id?: string | null; status?: string;
  anchors?: { anchor_id: string; locator?: { reader_url: string; segments: { exact: string; page_number: number; printed_label?: string }[] } }[];
};

// The editor supplies the same content to this renderer, without fetching or publishing it.
export function KnowledgePageContent({ page, renderBlock }: {
  page: Pick<KnowledgePageData, "blocks" | "assertions" | "anchors">;
  renderBlock?: (block: KnowledgeBlock, content: ReactNode) => ReactNode;
}) {
  return <section className="detail-section work-curated-claims"><SectionHeading title="知识导读" />
    {page.blocks.map(block => {
      const anchors = (page.anchors || []).filter(a => block.references?.some(r => r.type === "anchor" && r.id === a.anchor_id));
      const content = <div key={block.id}><IssueBlockView block={{ ...block, type: block.type || "analysis", text: block.text || "", references: undefined }} />
        {!!anchors.length && <details className="work-curated-evidence"><summary>原文依据 · {anchors.length} 处</summary>{anchors.map(a => a.locator ? <blockquote key={a.anchor_id}><p style={{ whiteSpace: "pre-wrap" }}>{a.locator.segments.map(v => v.exact).join("\n")}</p><footer><span>{a.locator.segments.map(v => v.printed_label ? `${v.printed_label} · PDF ${v.page_number}` : `PDF ${v.page_number}`).join("、")}</span> <Link href={a.locator.reader_url}>查看原文 <ArrowRight size={14} /></Link></footer></blockquote> : <p key={a.anchor_id}><Link href={`/login?next=${encodeURIComponent(typeof window === "undefined" ? "/home" : window.location.pathname)}`}>登录后查看原文依据</Link></p>)}</details>}
      </div>;
      return renderBlock ? renderBlock(block, content) : content;
    })}
    <div className="work-curated-claim-list">{page.assertions.map(assertion => <KnowledgeAssertionContent key={assertion.id} assertion={assertion} />)}</div>
  </section>;
}

export function KnowledgeAssertionContent({ assertion }: { assertion: KnowledgeAssertion }) {
  return <article>
    <p className="work-curated-proposition">{assertion.text}</p>
    <p className="work-curated-note">{assertion.sources.map(s => [s.attribution__label, s.work__title].filter(Boolean).join(" · ")).join("；")}</p>
    <section data-content-section className="work-curated-evidence"><header data-section-heading>查看依据 <span>{assertion.evidence.length} 条馆藏原文</span></header><div>
      {assertion.evidence.map(e => e.locator ? <blockquote key={e.anchor_id}>
        <p>{e.locator.segments.map(s => s.exact).join("\n")}</p><footer><span>{e.locator.segments.map(s => s.printed_label ? `${s.printed_label} · PDF 第 ${s.page_number} 页` : `PDF 第 ${s.page_number} 页`).join("、")}</span><Link href={e.locator.reader_url}>查看原文 <ArrowRight size={14} /></Link></footer>
      </blockquote> : <p key={e.anchor_id}><Link href={`/login?next=${encodeURIComponent(typeof window === "undefined" ? "/home" : window.location.pathname)}`}>登录后查看原文依据</Link></p>)}
    </div></section>
  </article>;
}
