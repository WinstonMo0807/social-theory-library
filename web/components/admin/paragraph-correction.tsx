"use client";

import { useState } from "react";
import { createRequestKey } from "@/lib/request-key";
import { knowledgeCall, type SourceLocator, type SourceSegment } from "./knowledge-workbench";
import s from "./knowledge-workbench.module.css";

type Paragraph = { id: string; human_corrected: boolean; segments: SourceSegment[] };
type Ranges = { base_hash: string; paragraphs: Paragraph[]; last_correction?: { reason: string; operation: string } };

export function ParagraphCorrection({ revision, pages, onPage, onSaved }: {
  revision: string; pages: number; onPage: (page: number) => void; onSaved: (locator: SourceLocator | null) => void;
}) {
  const [start, setStart] = useState(1), [end, setEnd] = useState(Math.min(2, pages));
  const [ranges, setRanges] = useState<Ranges | null>(null), [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState(""), [request, setRequest] = useState(createRequestKey);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const chosen = ranges?.paragraphs.filter(p => selected.includes(p.id)) || [];
  const endpoint = `/knowledge/revisions/${revision}/structure/paragraphs/`;
  async function load() {
    setBusy(true); setError(""); setNotice("");
    try { setRanges(await knowledgeCall<Ranges>(`${endpoint}?page=${start}&end=${end}`)); setSelected([]); setRequest(createRequestKey()); }
    catch (e) { setError(e instanceof Error ? e.message : "段落读取失败，请重试。"); }
    finally { setBusy(false); }
  }
  async function save(operation: "join" | "undo") {
    if (!ranges) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await knowledgeCall<{ locator: SourceLocator | null }>(endpoint, {
        operation, node_ids: operation === "join" ? selected : [], base_hash: ranges.base_hash, reason, request_id: request,
      });
      setRanges(await knowledgeCall<Ranges>(`${endpoint}?page=${start}&end=${end}`)); setSelected([]); setRequest(createRequestKey()); setReason("");
      setNotice(operation === "join" ? "连续段落已保存，历史结构与引用保留。检索更新已进入任务队列。" : "已恢复校正前的段落结构，历史引用保留。检索更新已进入任务队列。");
      onSaved(result.locator);
    } catch (e) { setError(e instanceof Error ? e.message : "段落校正未保存，请重试。"); }
    finally { setBusy(false); }
  }
  return <details className={s.paragraphCorrection}>
    <summary>校正跨页段落</summary>
    <p className={s.muted}>对照 PDF 选择属于同一段的完整正文。脚注独立保留，原文文字不变。</p>
    <form onSubmit={e => { e.preventDefault(); void load(); }} className={s.toolbar}>
      <label>PDF 起页<input type="number" min={1} max={pages} value={start} onChange={e => { setStart(Number(e.target.value)); setRanges(null); }} required /></label>
      <label>PDF 止页<input type="number" min={start} max={Math.min(pages, start + 4)} value={end} onChange={e => { setEnd(Number(e.target.value)); setRanges(null); }} required /></label>
      <button disabled={busy}>读取段落</button>
    </form>
    {error && <p className={s.error} role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {ranges && <>
      <div className={s.paragraphChoices}>{ranges.paragraphs.map((paragraph, index) => <article key={paragraph.id} data-selected={selected.includes(paragraph.id)}>
        <label className={s.paragraphChoice}><input type="checkbox" disabled={busy} checked={selected.includes(paragraph.id)} onChange={e => {
          setSelected(old => e.target.checked ? [...old, paragraph.id] : old.filter(id => id !== paragraph.id)); setRequest(createRequestKey());
        }} /><span>段落 {index + 1}{paragraph.human_corrected ? " · 人工校正" : ""}</span></label>
        {paragraph.segments.map((segment, i) => <div key={i}><button className={s.pageLink} onClick={() => onPage(segment.page_number)}>PDF {segment.page_number}{segment.printed_label ? ` · 书页 ${segment.printed_label}` : ""} ↗</button><p className={s.paragraph}>{segment.exact}</p></div>)}
      </article>)}</div>
      {!ranges.paragraphs.length && <p>所选页面尚无可校正的段落。请先准备正文结构。</p>}
      {chosen.length > 0 && <section className={s.paragraphPreview} aria-label="校正后段落预览"><h3>校正后的一段正文</h3>
        <p className={s.muted}>{chosen.length} 个段落 · {chosen.reduce((total, item) => total + item.segments.length, 0)} 个页面片段</p>
        <p className={s.paragraph}>{chosen.flatMap(p => p.segments).map((segment, i) => <span key={i}><small>〔PDF {segment.page_number}〕</small>{segment.exact}</span>)}</p>
      </section>}
      {(chosen.length > 0 || ranges.last_correction) && <>
        <label>校正依据<textarea rows={2} maxLength={1000} value={reason} disabled={busy} placeholder="说明从 PDF 排版与上下文确认连续或撤销校正的依据" onChange={e => { setReason(e.target.value); setRequest(createRequestKey()); }} /></label>
        <div className={s.toolbar}><button className={s.primary} disabled={busy || chosen.length < 2 || reason.trim().length < 2} onClick={() => void save("join")}>确认为连续段落</button>
          {ranges.last_correction && <button disabled={busy || reason.trim().length < 2} onClick={() => void save("undo")}>撤销最近一次校正</button>}</div>
        {ranges.last_correction && <p className={s.muted}>最近校正依据：{ranges.last_correction.reason}</p>}
      </>}
    </>}
  </details>;
}
