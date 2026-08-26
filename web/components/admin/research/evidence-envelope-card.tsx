import { ExternalLink } from "lucide-react";
import { normalizeEvidenceEnvelope } from "./evidence-envelope";

export function EvidenceEnvelopeCard({ evidence, compact = false }: { evidence: unknown; compact?: boolean }) {
  const row = normalizeEvidenceEnvelope(evidence);
  const percentage = row.qualityScore === null
    ? ""
    : `${Math.round((row.qualityScore <= 1 ? row.qualityScore * 100 : row.qualityScore))}%`;
  const ocr = [row.ocrProvider, row.ocrModel, row.ocrVersion].filter(Boolean).join(" · ");
  const extraction = [row.extractionMethod, row.extractionVersion].filter(Boolean).join(" · ");
  return (
    <article className={`admin-evidence-envelope${compact ? " is-compact" : ""}${row.stale ? " is-stale" : ""}`}>
      <header>
        <span><strong>{row.title}</strong>{row.authors.length ? <small>{row.authors.join("、")}</small> : null}</span>
        {row.stale ? <b>证据已失效</b> : percentage ? <b>质量 {percentage}</b> : null}
      </header>
      <blockquote>{row.text}</blockquote>
      <div className="admin-evidence-locator">
        {row.page ? <span>PDF 第 {row.page} 页</span> : <span>页码待核对</span>}
        {row.printedPageLabel && row.printedPageLabel !== row.page ? <span>印刷页 {row.printedPageLabel}</span> : null}
        {row.section ? <span>{row.section}</span> : null}
        {row.locatorDetails.map((detail) => <span key={detail}>{detail}</span>)}
      </div>
      {(extraction || ocr || row.staleReason || row.qualityDetails.length) ? <details><summary>质量与来源</summary>{row.qualityDetails.length ? <p>{row.qualityDetails.join(" · ")}</p> : null}{extraction ? <p>提取 {extraction}</p> : null}{ocr ? <p>OCR {ocr}</p> : null}{row.staleReason ? <p>失效原因 {row.staleReason}</p> : null}</details> : null}
      {(row.readerUrl || row.pdfUrl || row.sourceUrl) ? <footer>
        {row.readerUrl ? <a href={row.readerUrl} target="_blank" rel="noreferrer">回到阅读器 <ExternalLink size={12} /></a> : null}
        {row.pdfUrl ? <a href={row.pdfUrl} target="_blank" rel="noreferrer">打开 PDF <ExternalLink size={12} /></a> : null}
        {row.sourceUrl ? <a href={row.sourceUrl} target="_blank" rel="noreferrer">查看外部来源 <ExternalLink size={12} /></a> : null}
      </footer> : null}
    </article>
  );
}
