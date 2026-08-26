export type NormalizedEvidenceEnvelope = {
  id: string;
  title: string;
  authors: string[];
  text: string;
  page: string;
  printedPageLabel: string;
  section: string;
  locatorDetails: string[];
  qualityScore: number | null;
  qualityDetails: string[];
  stale: boolean;
  staleReason: string;
  extractionMethod: string;
  extractionVersion: string;
  ocrProvider: string;
  ocrModel: string;
  ocrVersion: string;
  readerUrl: string;
  pdfUrl: string;
  sourceUrl: string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asString(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number") return String(value);
  return "";
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const normalized = asString(value);
    if (normalized) return normalized;
  }
  return "";
}

function stringRows(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(asString).filter(Boolean);
  const row = asString(value);
  return row ? [row] : [];
}

function qualityDetails(quality: Record<string, unknown>): string[] {
  const rows: string[] = [];
  const summary = firstString(quality.summary, quality.label);
  if (summary) rows.push(summary);
  if (quality.body_fetched === true) rows.push("已取得正文");
  if (quality.identity_term_present === true) rows.push("身份词已核对");
  const contentType = firstString(quality.content_type);
  if (contentType) rows.push(contentType);
  return [...new Set(rows)];
}

function locatorDetails(locator: Record<string, unknown>): string[] {
  const rows: string[] = [];
  const block = firstString(locator.block_id, locator.text_block_id);
  if (block) rows.push(`区块 ${block}`);
  const start = firstString(locator.start_offset, locator.start);
  const end = firstString(locator.end_offset, locator.end);
  if (start || end) rows.push(`字符 ${start || "?"}–${end || "?"}`);
  if (Array.isArray(locator.bbox) && locator.bbox.length) rows.push(`页内坐标 ${locator.bbox.map(asString).filter(Boolean).join(", ")}`);
  return rows;
}

export function normalizeEvidenceEnvelope(value: unknown, fallbackId = "evidence"): NormalizedEvidenceEnvelope {
  const row = asRecord(value);
  const source = asRecord(row.source);
  const locator = asRecord(row.locator);
  const quality = asRecord(row.quality);
  const provenance = asRecord(row.provenance);
  const nestedOcr = { ...asRecord(row.ocr_provenance), ...asRecord(provenance.ocr) };
  const page = firstString(locator.page, locator.page_number, row.page_number, row.page, row.page_index);
  const asset = firstString(source.asset_id, row.asset_id, row.asset);
  const readerUrl = firstString(row.reader_url, row.reader_href, locator.reader_url) || (asset && page ? `/reader/${encodeURIComponent(asset)}?page=${encodeURIComponent(page)}` : "");
  const qualityValue = quality.score ?? (typeof row.quality === "number" ? row.quality : undefined) ?? row.quality_score ?? row.ocr_quality;
  const parsedQuality = typeof qualityValue === "number" ? qualityValue : Number(qualityValue);
  return {
    id: firstString(row.id, fallbackId),
    title: firstString(source.work_title, source.title, row.source_title, row.work_title, row.title, "馆藏证据"),
    authors: stringRows(source.authors ?? row.authors),
    text: firstString(row.text, row.supporting_text, row.evidence_text, row.text_quote, row.quote, "未提供支撑片段"),
    page,
    printedPageLabel: firstString(locator.printed_page_label, locator.printed_label, row.printed_page_label),
    section: firstString(locator.section, row.section),
    locatorDetails: locatorDetails(locator),
    qualityScore: Number.isFinite(parsedQuality) ? parsedQuality : null,
    qualityDetails: qualityDetails(quality),
    stale: quality.stale === true || row.is_stale === true || row.is_current === false,
    staleReason: firstString(quality.stale_reason, row.stale_reason),
    extractionMethod: firstString(provenance.extraction_method, row.extraction_method),
    extractionVersion: firstString(provenance.extraction_version, row.extraction_version),
    ocrProvider: firstString(provenance.ocr_provider, nestedOcr.provider, row.ocr_provider),
    ocrModel: firstString(provenance.ocr_model, nestedOcr.model, row.ocr_model),
    ocrVersion: firstString(provenance.ocr_version, nestedOcr.version, row.ocr_version),
    readerUrl,
    pdfUrl: firstString(row.pdf_url, row.pdf_href, locator.pdf_url),
    sourceUrl: firstString(row.canonical_url, row.source_url, row.url, source.url, locator.url),
  };
}
