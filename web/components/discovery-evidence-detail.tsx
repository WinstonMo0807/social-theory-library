"use client";
import { useEvidenceLanguage } from "./evidence-language";
import { MediaPlacement } from "@/components/media-placement";

import { BookOpen, ChevronLeft, ChevronRight, Copy, Quote } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { DiscoveryContext, DiscoveryPassage } from "@/lib/api/discovery.types";
import { passageReference } from "@/lib/api/research.client";
import { citationText, previewSharedCitation } from "@/lib/api/shared-citation.client";
import Link from "next/link";
import { SaveWorkButton } from "./save-work-button";
import { SharedCitationButton } from "./shared-citation-overlay";
import { SourceText } from "./source-text";
import styles from "@/app/explore/opinions/viewpoint-search.module.css";

export function discoveryReaderHref(item: DiscoveryPassage, returnTo?: string) {
  if (!item.reader_url.startsWith("/reader/") || /[\\\u0000-\u001f\u007f]/.test(item.reader_url)) return "";
  const url = new URL(item.reader_url, "https://library.invalid");
  if (url.origin !== "https://library.invalid") return "";
  if (returnTo) url.searchParams.set("return_to", returnTo);
  return `${url.pathname}${url.search}`;
}

export function EvidenceBook({ item, compact = false, onSelect }: { item: DiscoveryPassage; compact?: boolean; onSelect?: () => void }) {
  const { t } = useEvidenceLanguage();
  const [failed, setFailed] = useState("");
  const book = item.bibliography;
  const cover = normalizePublicResourceUrl(book?.cover_url || "");
  return <div className={`${styles.evidenceBook} ${compact ? styles.compactBook : ""}`}>
    {cover && failed !== cover ? <MediaPlacement uses={book?.cover_media?.display_uses} fallback={<div className={styles.coverMissing} aria-label={t("暂无封面")}><BookOpen size={22} /></div>}><img src={cover} alt={t("{title}封面", { title: item.work.title })} onError={() => setFailed(cover)} loading="lazy" /></MediaPlacement> : <div className={styles.coverMissing} aria-label={t("暂无封面")}><BookOpen size={22} /></div>}
    <div><h3>{onSelect ? <button type="button" className={`${styles.titleSelect} editorial-link`} onClick={onSelect} aria-label={t("查看证据摘要：{title}", { title: item.work.title })}>{item.work.title}</button> : item.work.title}</h3>{book?.original_title && book.original_title !== item.work.title ? <p className={styles.originalTitle}>{book.original_title}</p> : null}
      <p>{item.authors?.join("、") || t("责任者待核对")}</p>
      <p>{[book?.publisher, book?.publication_year, book?.language, book?.page_count ? t("PDF {count} 页", { count: book.page_count }) : ""].filter(Boolean).join(" · ") || t("出版信息待补充")}</p>
      {book?.version_label ? <small>{book.version_label}</small> : null}
    </div>
  </div>;
}

export function EvidenceQuote({ item }: { item: DiscoveryPassage }) {
  const { t } = useEvidenceLanguage();
  return <blockquote className={styles.passageQuote}><Quote size={18} aria-hidden="true" /><div><strong>{t("原文节选")}{/ocr/i.test(item.source_kind) ? " · OCR" : ""}</strong><p><SourceText text={item.excerpt} /></p><small>{item.printed_page ? `${t("印刷页 {page}", { page: item.printed_page })} · ` : ""}{t("PDF 第 {page} 页", { page: item.pdf_page })}</small></div></blockquote>;
}

export function EvidenceResultCard({ item, index, selected, fresh, onSelect, onContext }: {
  item: DiscoveryPassage; index: number; selected: boolean; fresh: boolean; onSelect: () => void; onContext: () => void;
}) {
  const { t } = useEvidenceLanguage();
  return <article className={`${styles.resultCard} ${selected ? styles.selectedCard : ""}`} id={`material-${item.id}`}>
    <span className={styles.resultNumber}>{index + 1}</span><div className={styles.resultContent}>
      <div className={styles.selectEvidence}><EvidenceBook item={item} onSelect={onSelect} /></div>
      <div className={styles.evidenceTags}>{fresh ? <span>{t("本轮新增")}</span> : null}<span>{t("含原文证据")}</span>{item.attribution?.status && item.attribution.status !== "unknown" ? <span>{item.attribution.label}</span> : null}</div>
      <div className={styles.selectQuote}><EvidenceQuote item={item} /></div>
      <footer><span>{item.section_title || t("章节位置待核对")}</span><button type="button" className="editorial-link" onClick={onContext}>{t("查看上下文")}<ChevronRight size={14} /></button></footer>
    </div><div className={styles.cardSave}><SaveWorkButton workId={item.work.id} compact /></div>
  </article>;
}

export function EvidenceSummary({ item, returnTo, onContext }: { item: DiscoveryPassage; returnTo: string; onContext?: () => void }) {
  const { t } = useEvidenceLanguage();
  const [copyState, setCopyState] = useState("");
  const [manual, setManual] = useState("");
  const [copying, setCopying] = useState(false);
  const href = discoveryReaderHref(item, returnTo);
  async function copy() {
    if (copying) return;
    setCopying(true); setCopyState(""); setManual("");
    try {
      // Resolve again before copying: withdrawn text must not be exported from a stale card.
      const value = await previewSharedCitation({ reference: passageReference(item), selectedText: item.excerpt });
      const text = citationText(value, "quote");
      try { await navigator.clipboard.writeText(text); setCopyState("引文和来源已复制。"); }
      catch { setManual(text); setCopyState("自动复制未完成，可选中下面的引文复制。"); }
    } catch (reason) { setCopyState(reason instanceof Error ? reason.message : "来源核对失败，请刷新结果后重试。"); }
    finally { setCopying(false); }
  }
  return <div className={styles.evidenceSummary}>
    <EvidenceBook item={item} compact />
    <section><h3>{t("页面位置")}</h3><strong>{item.printed_page ? t("印刷页 {page}", { page: item.printed_page }) : t("PDF 第 {page} 页", { page: item.pdf_page })}</strong><p>{item.printed_page ? t("PDF 第 {page} 页", { page: item.pdf_page }) : t("印刷页码未标注")}</p>{item.section_title ? <p>{item.section_title}</p> : null}</section>
    <EvidenceQuote item={item} />
    <section><h3>{t("原文核对")}</h3><dl><div><dt>{t("定位方式")}</dt><dd>{item.locator_precision === "exact" ? t("原文定位") : t("按页定位")}</dd></div><div><dt>{t("观点归属")}</dt><dd>{item.attribution?.label || t("待人工核对")}</dd></div></dl><p>{item.attribution?.notice || t("请结合上下文核对观点的提出者。")}</p>{/ocr/i.test(item.source_kind) ? <p>{t("文字由 OCR 识别，请与原始扫描画面核对。")}</p> : null}</section>
    {([['related_concepts', t("相关概念")], ['related_theories', t("相关理论流派")]] as const).map(([key, title]) => item[key]?.length ? <section key={key}><h3>{t(title)}</h3><div className={styles.relatedTags}>{item[key]!.map(node => <Link key={node.id} href={`/theories/nodes/${encodeURIComponent(node.slug || node.id)}`}>{node.title}</Link>)}</div></section> : null)}
    {item.match_basis?.length ? <details className={styles.matchBasis}><summary>{t("匹配依据")}</summary><div className={styles.evidenceTags}>{item.match_basis.map((text, index) => <span key={`${text}-${index}`}>{text}</span>)}</div></details> : null}
    <div className={styles.summaryActions}>{href ? <Link className="button" href={href}><BookOpen size={16} />{t("阅读原文")}</Link> : <p>{t("阅读定位暂不可用，请刷新结果。")}</p>}
      <div><button type="button" onClick={() => void copy()} disabled={copying}><Copy size={14} />{copying ? t("核对来源") : t("复制引文")}</button><SharedCitationButton reference={passageReference(item)} selectedText={item.excerpt}>{t("引用")}</SharedCitationButton><SaveWorkButton workId={item.work.id} compact /></div>
      {onContext ? <button type="button" className="editorial-link" onClick={onContext}>{t("查看上下文")}<ChevronRight size={14} /></button> : null}
    </div>
    {copyState ? <p role="status">{t(copyState)}</p> : null}{manual ? <textarea aria-label={t("手动复制引文")} readOnly value={manual} rows={6} onFocus={event => event.currentTarget.select()} /> : null}
  </div>;
}

export function EvidenceContextBody({ item, context, returnTo, onOpenCandidate }: {
  item: DiscoveryPassage; context: DiscoveryContext; returnTo: string; onOpenCandidate: (item: DiscoveryPassage) => void;
}) {
  const { t } = useEvidenceLanguage();
  const [sameBook, setSameBook] = useState(false);
  const [originalLines, setOriginalLines] = useState(false);
  const source = context.source || item;
  const blocks = context.blocks?.length ? context.blocks : [{ text: context.before, role: "before", pdf_page: source.pdf_page }, { text: context.excerpt, role: "hit", pdf_page: source.pdf_page }, { text: context.after, role: "after", pdf_page: source.pdf_page }].filter(block => block.text);
  const contextRef = useRef<HTMLDivElement>(null);
  const blockIndex = useRef(Math.max(0, blocks.findIndex(block => ["hit", "match"].includes(block.role))));
  useEffect(() => {
    // Long preceding pages must not hide the passage the reader just selected.
    const node = contextRef.current?.querySelectorAll<HTMLElement>("[data-discovery-context-block]")[blockIndex.current];
    node?.scrollIntoView({ block: "start", behavior: "instant" });
  }, []);
  const scrollBlock = (direction: number) => {
    const nodes = [...(contextRef.current?.querySelectorAll<HTMLElement>("[data-discovery-context-block]") || [])];
    blockIndex.current = Math.max(0, Math.min(nodes.length - 1, blockIndex.current + direction));
    nodes[blockIndex.current]?.focus();
  };
  const reader = discoveryReaderHref(source, returnTo);
  return <div className={styles.contextColumns} ref={contextRef}><div><EvidenceBook item={source} compact />
    <div className={styles.contextNavigation}><h3>{t("上下文")}<small>{t("共 {count} 段", { count: blocks.length })}</small></h3><button type="button" aria-pressed={originalLines} onClick={() => setOriginalLines(value => !value)}>{t("原始换行")}</button><button type="button" onClick={() => scrollBlock(-1)}><ChevronLeft size={14} />{t("上一段")}</button><button type="button" onClick={() => scrollBlock(1)}>{t("下一段")}<ChevronRight size={14} /></button></div>
    {context.notice ? <p className={styles.help}>{context.notice}</p> : null}
    {blocks.map((block, index) => <section key={`${context.result_id}-${index}`} tabIndex={-1} data-discovery-context-block className={["hit", "match"].includes(block.role) ? styles.contextMatch : styles.contextBlock}><small>{["hit", "match"].includes(block.role) ? t("命中原文") : block.role === "before" ? t("前段") : block.role === "after" ? t("后段") : t("相邻原文")}  · {t("PDF 第 {page} 页", { page: block.pdf_page })}</small><p><SourceText text={block.text} original={originalLines} /></p></section>)}
    </div><aside><section><h3>{t("作者自述或转引角色")}</h3><strong>{source.attribution?.label || t("待人工核对")}</strong><p>{source.attribution?.notice || t("请核对上下文中的作者自述、转引和评论关系。")}</p></section>
    <section><h3>{t("本段信息")}</h3><dl><div><dt>{t("出处位置")}</dt><dd>{source.printed_page ? `${t("印刷页 {page}", { page: source.printed_page })} · ` : ""}{t("PDF 第 {page} 页", { page: source.pdf_page })}</dd></div>{source.section_title ? <div><dt>{t("所属章节")}</dt><dd>{source.section_title}</dd></div> : null}<div><dt>{t("版本信息")}</dt><dd>{[source.bibliography?.publication_year, source.bibliography?.publisher, source.bibliography?.version_label].filter(Boolean).join(" · ") || t("待补充")}</dd></div></dl></section>
    <div className={styles.contextActions}>{reader ? <Link href={reader} className="button"><BookOpen size={16} />{t("打开阅读器")}</Link> : null}<SharedCitationButton className="button secondary" reference={passageReference(source)} selectedText={source.excerpt}>{t("加入当前研究")}</SharedCitationButton><button type="button" className="button secondary" onClick={() => setSameBook(value => !value)} aria-expanded={sameBook}>{t("查看同书更多段落")}{typeof context.same_work_count === "number" ? `（${context.same_work_count}）` : ""}<ChevronRight size={14} /></button></div>
    {sameBook ? <section className={styles.sameBook}><h3>{t("本次检索的同书材料")}</h3>{context.same_work_results?.length ? context.same_work_results.map(row => <button type="button" key={row.id} disabled={row.id === source.id} onClick={() => onOpenCandidate(row)}><span>{t("PDF 第 {page} 页", { page: row.pdf_page })}{row.id === source.id ? t(" · 当前") : ""}</span><p><SourceText text={row.excerpt} /></p></button>) : <p>{t("本次检索没有其他可展示的同书材料。")}</p>}{(context.same_work_count || 0) > (context.same_work_results?.length || 0) ? <p>{t("这里显示前 {count} 条，可返回结果继续读取。", { count: context.same_work_results?.length || 0 })}</p> : null}</section> : null}
    </aside></div>;
}
