"use client";
import { codePointRange, type KnowledgeSegment } from "./use-knowledge-anchor";
import type { PagePayload } from "./types";

export function KnowledgeAnchorText({ segments, pages, visit }: {
  segments: KnowledgeSegment[]; pages: Record<number, PagePayload>; visit: (page: number) => void;
}) {
  if (!segments.length) return null;
  return <section className="reader-source-selection" aria-label="固定修订原文引用">
    <h2>原文引用</h2>
    {segments.map(segment => {
      const page = pages[segment.page_number];
      let range: { start: number; end: number; exact: string } | null = null;
      let error = "";
      if (page) {
        try {
          range = codePointRange(page.text, segment.start, segment.end);
          if (range.exact !== segment.exact) { range = null; error = "当前页与引用文字不一致，请重新打开来源。"; }
        } catch { error = "引用范围不能在此页定位。"; }
      }
      return <article key={segment.order}>
        <button className="reader-panel-link" type="button" onClick={() => visit(segment.page_number)}>
          PDF 第 {segment.page_number} 页{segment.printed_label ? ` · 书页 ${segment.printed_label}` : ""}
        </button>
        {error ? <p role="alert">{error}</p> : <blockquote style={{ whiteSpace: "pre-wrap" }}>
          {range && page ? <>{page.text.slice(Math.max(0, range.start - 50), range.start)}<mark>{range.exact}</mark>{page.text.slice(range.end, range.end + 50)}</> : segment.exact}
        </blockquote>}
        <p>{segment.precision === "geometry" ? "已核对原文与版面位置" : "已核对原始文字范围；PDF 定位到页面"}</p>
      </article>;
    })}
  </section>;
}
