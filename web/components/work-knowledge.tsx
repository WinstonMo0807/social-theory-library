"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { SectionHeading } from "./ui";
import { usePublicSession } from "./public-session-provider";

type Page = { id: string; blocks: { id: string; text: string }[]; assertions: { id: string; text: string;
  sources: { work__title: string; attribution__label: string | null; expression: string }[];
  evidence: { anchor_id: string; stance: string; locator?: { reader_url: string; segments: { exact: string; page_number: number; printed_label: string }[] } }[] }[] };

export function WorkKnowledge({ workId }: { workId: string }) {
  const { state } = usePublicSession();
  const [page, setPage] = useState<Page | null>(null), [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setError(""); setPage(null);
    void apiRequest<{ page: Page | null }>(`/knowledge/works/${workId}/`, { signal: controller.signal, cache: "no-store" }, getServerSessionCredential())
      .then(data => setPage(data.page)).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [workId, state.status]);
  if (error) return <p role="alert">知识导读暂时无法读取。{error}</p>;
  if (!page?.blocks.length) return null;
  return <section className="detail-section work-curated-claims"><SectionHeading title="知识导读" />
    {page.blocks.map(block => <p className="work-curated-note" key={block.id}>{block.text}</p>)}
    <div className="work-curated-claim-list">{page.assertions.map(assertion => <article key={assertion.id}>
      <p className="work-curated-proposition">{assertion.text}</p>
      <p className="work-curated-note">{assertion.sources.map(s => [s.attribution__label, s.work__title].filter(Boolean).join(" · ")).join("；")}</p>
      <section data-content-section className="work-curated-evidence"><header data-section-heading>查看依据 <span>{assertion.evidence.length} 条馆藏原文</span></header><div>
        {assertion.evidence.map(e => e.locator ? <blockquote key={e.anchor_id}>
          <p>{e.locator.segments.map(s => s.exact).join("\n")}</p><footer><span>{e.locator.segments.map(s => s.printed_label ? `${s.printed_label} · PDF 第 ${s.page_number} 页` : `PDF 第 ${s.page_number} 页`).join("、")}</span><Link href={e.locator.reader_url}>查看原文 <ArrowRight size={14} /></Link></footer>
        </blockquote> : <p key={e.anchor_id}><Link href={`/login?next=${encodeURIComponent(locationPath())}`}>登录后查看原文依据</Link></p>)}
      </div></section>
    </article>)}</div>
  </section>;
}
function locationPath() { return typeof window === "undefined" ? "/home" : window.location.pathname; }
