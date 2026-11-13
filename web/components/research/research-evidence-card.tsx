"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, FileText } from "lucide-react";
import { useState } from "react";
import { MediaPlacement } from "@/components/media-placement";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { ResolvedEvidence } from "@/lib/api/research.client";

export const researchDocumentTypes: Record<string, string> = { book: "图书", journal_article: "期刊论文", journal_issue: "期刊", chapter: "章节", thesis: "学位论文", report: "报告", other: "其他文献" };
export function researchEvidenceLocation(reference: ResolvedEvidence) {
  const anchors = reference.anchors?.length ? reference.anchors : [reference];
  const pages = Array.from(new Set(anchors.flatMap(ref => ref.pdf_page ? [ref.pdf_page] : [])));
  const labels = Array.from(new Set(anchors.flatMap(ref => ref.printed_labels || (ref.printed_label ? [ref.printed_label] : []))));
  const spread = anchors.some(ref => ref.printed_label_precision === "spread");
  return [pages.length ? `PDF 第 ${pages.join("、")} 页` : "原文定位待核对", labels.length ? `${spread ? "同一扫描页书内页码" : "书内页码"} ${labels.join("、")}` : ""].filter(Boolean).join(" · ");
}
export function ResearchEvidenceCover({ reference, small = false }: { reference: ResolvedEvidence; small?: boolean }) {
  const url = reference.source_status === "available" && reference.cover_url ? normalizePublicResourceUrl(reference.cover_url) : "";
  const [failed, setFailed] = useState("");
  const className = `stl4-research-source-cover${small ? " is-small" : ""}`;
  const fallback = <span className={`${className} is-placeholder`} aria-label="暂无可展示封面" role="img">{reference.document_type === "book" ? <BookOpen size={small ? 18 : 27} strokeWidth={1.2}/> : <FileText size={small ? 18 : 27} strokeWidth={1.2}/>}</span>;
  return url && failed !== url ? <MediaPlacement uses={reference.cover_media?.display_uses} fallback={fallback}><img src={url} alt="" className={className} loading="lazy" onError={() => setFailed(url)}/></MediaPlacement> : fallback;
}
export function ResearchEvidenceCard({ reference, index, href, selected, status, disabled, onToggle }: {
  reference: ResolvedEvidence; index: number; href: string; selected: boolean; status: string; disabled: boolean; onToggle: () => void;
}) {
  const available = reference.source_status === "available";
  const title = available ? reference.title || `原文证据 ${index + 1}` : "来源待重新核对";
  const metadata = available ? [reference.authors?.join("、") || "作者待核对", reference.publication_year, reference.language].filter(Boolean).join(" · ") : "原引用记录保留";
  return <article className="stl4-research-evidence has-bibliography" data-selected={selected || undefined}>
    <label className="stl4-evidence-number"><input type="checkbox" checked={selected} disabled={disabled} onChange={onToggle} aria-label={`${selected ? "移除" : "选入"}${title}`}/><span>{index + 1}</span></label>
    <ResearchEvidenceCover reference={reference}/>
    <div className="stl4-evidence-copy"><div className="stl4-evidence-title"><h3>{title}</h3>{available && researchDocumentTypes[reference.document_type || ""] ? <span>{researchDocumentTypes[reference.document_type!]}</span> : null}</div><p className="stl4-evidence-bibliography">{metadata}</p><small>{researchEvidenceLocation(reference)}</small><blockquote>{available ? reference.quote || reference.text || "暂无可提取原文，请打开原件核对。" : "来源已变化或暂不可用。旧引用不会自动替换成另一版本的同页内容。"}</blockquote></div>
    <div className="stl4-evidence-actions"><button type="button" aria-pressed={selected} className={selected ? "is-selected" : undefined} disabled={disabled} onClick={onToggle}>{status ? `${status} · 撤回` : selected ? "已选 · 移除" : "加入选材"}</button>{href ? <Link href={href}>查看原文 <ArrowRight size={14}/></Link> : <small>原文定位待核对</small>}</div>
  </article>;
}
