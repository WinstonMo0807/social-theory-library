"use client";

import { ExternalLink } from "lucide-react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import type { EvidenceCurationItem } from "@/lib/api/evidence-curation.types";
import type { ApiWork } from "@/lib/api/public-catalog";
import { SavedEditionCover } from "@/components/admin/preview/selected-work-preview";

type Props = {
  item: EvidenceCurationItem | null;
  items: EvidenceCurationItem[];
  onChoose: () => void;
  onSelect: (index: number) => void;
  onChange: (field: "group_title" | "reason", value: string) => void;
  onMove: (index: number, delta: number) => void;
  onRemove: (index: number) => void;
};

export function TopicEvidenceFields({ item, items, onChoose, onSelect, onChange, onMove, onRemove }: Props) {
  const source = item?.source;
  const book = useApiResource<CollectionPage<WorkLibraryRow>>(source ? `/catalog/admin/library/works/?view=editions&work_id=${encodeURIComponent(source.work_id)}&edition_id=${encodeURIComponent(source.edition_id)}` : "", getServerSessionCredential());
  const metadata = useApiResource<{work:ApiWork}>(source ? `/catalog/admin/page-preview/editions/${encodeURIComponent(source.edition_id)}/` : "", getServerSessionCredential());
  const edition = book.data?.results.find(row => row.id === source?.edition_id && row.work_id === source?.work_id);
  const exactWork = source && metadata.data && metadata.data.work.id === source.work_id && metadata.data.work.edition?.id === source.edition_id ? metadata.data.work : null;
  if (!item || !source) return <div className="topic-evidence-empty"><p>尚未选择原文。</p><button type="button" className="button secondary" onClick={onChoose}>选择书中原文</button></div>;
  return <div className="topic-evidence-details" data-field-section="details">
    <section className="topic-evidence-selected-book">
      <header><strong>已选书籍</strong><button type="button" onClick={onChoose}>更换书籍</button></header>
      <div><SavedEditionCover editionId={source.edition_id} coverUrl={edition?.cover_url ?? ""} title={source.work_title}/><div><h2>{source.work_title}</h2><p className="topic-evidence-original-title">{exactWork?.original_title || ""}</p><p className="topic-evidence-book-meta">{edition?.contributors.join("、")}{edition?.publisher ? `　|　${edition.publisher}` : ""}{edition?.publication_year ? `　${edition.publication_year} 年` : ""}{source.edition_label ? `　${source.edition_label}` : ""}</p></div></div>
      {book.error ? <p role="alert">{book.error} <button type="button" onClick={book.retry}>重试书目信息</button></p> : null}
      {metadata.error ? <p role="alert">{metadata.error} <button type="button" onClick={metadata.retry}>重试书名信息</button></p> : null}
    </section>
    <section className="topic-evidence-selected-source" aria-label="选中的原文，只读">
      <header><strong>选中的原文 <span>（只读）</span></strong>{source.reader_url ? <a href={source.reader_url} target="_blank" rel="noreferrer">在原书中打开{source.page_start ? `（PDF 第 ${source.page_start} 页）` : ""}<ExternalLink size={14}/></a> : null}</header>
      <div className="topic-evidence-source-copy"><p>{source.page_start ? `PDF 第 ${source.page_start}${source.page_end && source.page_end !== source.page_start ? `–${source.page_end}` : ""} 页` : ""}{source.printed_label ? ` / 书页 ${source.printed_label}` : ""}</p><blockquote>{source.text}</blockquote></div>
    </section>
    <label className="topic-evidence-annotation"><span>分组名称 <b aria-hidden="true">*</b></span><input name="evidence_group" aria-required="true" value={item.group_title} onChange={event => onChange("group_title", event.target.value)}/><span className="topic-evidence-field-help"><small>为这段原文设置一个简洁的分组名称，便于在主题页面中展示。（建议不超过 20 个字）</small><small>{item.group_title.length} / 20</small></span></label>
    <label className="topic-evidence-annotation"><span>阅读说明 <b aria-hidden="true">*</b></span><textarea name="evidence_reason" aria-required="true" value={item.reason} onChange={event => onChange("reason", event.target.value)}/><span className="topic-evidence-field-help"><small>向读者解释这段原文的背景、核心观点或现实意义。（建议 50–300 字）</small><small>{item.reason.length} / 300</small></span></label>
    <details className="topic-evidence-other-settings"><summary>其他设置（可选）</summary>
      <section aria-label="已选原文"><h3>已选原文 · {items.length}</h3>{items.map((row, index) => <article key={row.id || `${row.source_type}:${row.source_id}`}><button type="button" aria-pressed={row.source_type === item.source_type && row.source_id === item.source_id} onClick={() => onSelect(index)}>{row.group_title || row.source.work_title}{row.source.page_start ? ` · PDF 第 ${row.source.page_start} 页` : ""}</button><div><button type="button" disabled={index === 0} onClick={() => onMove(index, -1)}>上移</button><button type="button" disabled={index === items.length - 1} onClick={() => onMove(index, 1)}>下移</button><button type="button" onClick={() => onRemove(index)}>移出策展</button></div></article>)}</section>
      {source.context_before || source.context_after ? <details><summary>查看上下文（只读）</summary>{source.context_before ? <p>{source.context_before}</p> : null}<blockquote>{source.text}</blockquote>{source.context_after ? <p>{source.context_after}</p> : null}</details> : null}
      <details><summary>来源详情</summary><p>文件 {source.asset_id} · {source.source_type === "span" ? "原文证据段" : "馆内摘录"}</p><p>出版版本 {source.edition_id}</p></details>
      {!source.public_eligible ? <p className="form-message">来源尚未公开，可保存为策展草稿，发布前需完成来源上架。</p> : null}
    </details>
  </div>;
}
