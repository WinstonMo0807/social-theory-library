import { CollectionLink } from "@/components/collection-link";
import type { EvidenceCurationItem } from "@/lib/api/evidence-curation.types";
import type { Work } from "@/lib/data";
import { BookCover } from "@/components/ui";

/** Shared by private draft preview and the published scholar/topic/theory sections. */
export function EvidenceCurationView({ items, preview = false, presentation, works = [], rowIndices, selectedKey }: { items: EvidenceCurationItem[]; preview?: boolean; presentation?: "topic"; works?: Work[]; rowIndices?: number[]; selectedKey?: string }) {
  if (!items.length) return <p className="evidence-curation-empty">尚未策展原文。</p>;
  return <div className="evidence-curation-public" data-edit-section="passages">{items.map((item, index) => {
    const source = item.source;
    if (presentation === "topic") {
      const work = works.find(row => (row.workId || row.id) === source.work_id && row.editionId === source.edition_id);
      return <section className="topic-evidence-quote" id={`curated-${item.id || item.source_id}`} key={item.id || `${item.source_type}:${item.source_id}`} data-edit-row={rowIndices?.[index] ?? index} data-selected={selectedKey === `${item.source_type}:${item.source_id}`}><div><h2>{item.group_title}</h2><p className="topic-evidence-reading-note">{item.reason}</p><p className="topic-evidence-citation">选自《{source.work_title}》{source.edition_label ? `　${source.edition_label}` : ""}<br/>{source.page_start ? `PDF 第 ${source.page_start}${source.page_end && source.page_end !== source.page_start ? `–${source.page_end}` : ""} 页` : ""}{source.printed_label ? ` / 书页 ${source.printed_label}` : ""}</p></div><aside>{work?.coverImage ? <BookCover work={work} size="small"/> : <span className="topic-evidence-cover-empty" aria-hidden="true"/>}{source.reader_url ? <CollectionLink href={source.reader_url}>打开原书{source.page_start ? `第 ${source.page_start} 页` : ""} ↗</CollectionLink> : null}</aside></section>;
    }
    const groupChanged = item.group_title && (index === 0 || item.group_title !== items[index - 1].group_title);
    return <section id={`curated-${item.id || item.source_id}`} key={item.id || `${item.source_type}:${item.source_id}`} data-edit-row={index}>
      {groupChanged ? <h2>{item.group_title}</h2> : null}
      <article className="evidence-curation-quote">
        {item.reason ? <div className="evidence-curation-reason"><p>{item.reason}</p></div> : null}
        <p className="evidence-curation-citation">{source.work_title} · {source.edition_label || "出版信息待补"}{source.page_start ? ` · PDF 第 ${source.page_start}${source.page_end && source.page_end !== source.page_start ? `–${source.page_end}` : ""} 页` : " · 页码待核对"}{source.printed_label ? ` · 印刷页 ${source.printed_label}` : ""}</p>
        <details><summary>查看原文</summary><blockquote>{source.text}</blockquote></details>
        {preview && !source.public_eligible ? <p className="form-message">此来源尚未满足公开条件，仅管理员可见。</p> : null}
        {source.reader_url ? <CollectionLink href={source.reader_url}>打开原文位置 ↗</CollectionLink> : null}
      </article>
    </section>;
  })}</div>;
}
