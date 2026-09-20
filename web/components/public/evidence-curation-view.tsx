import { CollectionLink } from "@/components/collection-link";
import type { EvidenceCurationItem } from "@/lib/api/evidence-curation.types";

/** Shared by private draft preview and the published scholar/topic/theory sections. */
export function EvidenceCurationView({ items, preview = false }: { items: EvidenceCurationItem[]; preview?: boolean }) {
  if (!items.length) return <p className="evidence-curation-empty">尚未策展原文。</p>;
  return <div className="evidence-curation-public" data-edit-section="passages">{items.map((item, index) => {
    const source = item.source;
    const groupChanged = item.group_title && (index === 0 || item.group_title !== items[index - 1].group_title);
    return <section id={`curated-${item.id || item.source_id}`} key={item.id || `${item.source_type}:${item.source_id}`} data-edit-row={index}>
      {groupChanged ? <h2>{item.group_title}</h2> : null}
      <article className="evidence-curation-quote">
        <blockquote>{source.text}</blockquote>
        <p className="evidence-curation-citation">{source.work_title} · {source.edition_label || "出版信息待补"}{source.page_start ? ` · PDF 第 ${source.page_start}${source.page_end && source.page_end !== source.page_start ? `–${source.page_end}` : ""} 页` : " · 页码待核对"}{source.printed_label ? ` · 印刷页 ${source.printed_label}` : ""}</p>
        {item.reason ? <div className="evidence-curation-reason"><strong>关联说明</strong><p>{item.reason}</p></div> : null}
        {preview && !source.public_eligible ? <p className="form-message">此来源尚未满足公开条件，仅管理员可见。</p> : null}
        {source.reader_url ? <CollectionLink href={source.reader_url}>打开原文位置 ↗</CollectionLink> : null}
      </article>
    </section>;
  })}</div>;
}
