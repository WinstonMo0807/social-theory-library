"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { useCallback, useEffect, useRef, useState } from "react";
import { PdfCanvas } from "@/components/pdf-canvas";
import { subscribeToSessionChanges } from "@/lib/api";
import { downloadAuditOriginal, downloadPrivateCitationSource, privateCitationSourcePath, type AuditData, type AuditLocation, type AuditTextPage, type AuditTextUnit, type PrivateCitationSourceData, type ResearchRecord } from "@/lib/api/research.client";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { isTaskRunning } from "@/lib/api/task-polling";
import type { CitationPreviewKind } from "@/lib/api/citation-preview.client";
import { CitationDocxPreview } from "./citation-docx-preview";
import { auditLocation } from "./citation-audit-shared";

export type CitationPreviewFocus = { key: string; location?: AuditLocation; text?: string; occurrenceId?: string; entryId?: string; unitId?: string };

/** The original and parsed text remain owner-scoped; corrections never replace either. */
export function CitationManuscriptPreview({ record, ownerId, focus }: { record: ResearchRecord<AuditData>; ownerId: string; focus?: CitationPreviewFocus }) {
  const read = useCallback(() => downloadAuditOriginal(record.id), [record.id]);
  return <CitationDocumentPreview key={ownerId + ":" + record.id} ownerId={ownerId} identity={record.id + ":" + (record.data.manuscript_revision || 1)} filetype={record.data.filetype}
    previewId={record.id} previewKind="citation-audits" sourceGeneration={record.generation || 1} revision={record.revision} readOriginal={read} textPath={"/reading/citation-audits/" + encodeURIComponent(record.id) + "/manuscript/"} focus={focus} />;
}

export function CitationPrivateSourceDocument({ record, ownerId, focus }: { record: ResearchRecord<PrivateCitationSourceData>; ownerId: string; focus?: CitationPreviewFocus }) {
  const read = useCallback(() => downloadPrivateCitationSource(record.id), [record.id]);
  return <CitationDocumentPreview key={ownerId + ":" + record.id + ":" + (record.generation || 0)} ownerId={ownerId} identity={record.id + ":" + (record.generation || 0)} filetype={record.data.filetype}
    previewId={record.id} previewKind="citation-sources" sourceGeneration={record.generation || 1} revision={record.revision} expectedTextGeneration={record.data.source_generation ?? record.generation ?? 0} readOriginal={read} textPath={privateCitationSourcePath(record.id) + "segments/"} focus={focus} />;
}

function CitationDocumentPreview({ ownerId, identity, filetype, revision, expectedTextGeneration, readOriginal, textPath, focus, previewId, previewKind, sourceGeneration }: {
  ownerId: string; identity: string; filetype: "pdf" | "docx"; revision: number; expectedTextGeneration?: number;
  previewId: string; previewKind: CitationPreviewKind; sourceGeneration: number;
  readOriginal: () => Promise<{ blob: Blob }>; textPath: string; focus?: CitationPreviewFocus;
}) {
  const [file, setFile] = useState<{ identity: string; url: string } | null>(null);
  const [error, setError] = useState("");
  const [navigation, setNavigation] = useState({ key: "", page: 1 });
  const [textNavigation, setTextNavigation] = useState({ key: "", page: 1 });
  const [pages, setPages] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [attempt, setAttempt] = useState(0);
  const [modeChoice, setModeChoice] = useState<{ key: string; mode: "page" | "text" }>({ key: "", mode: "page" });
  const focusKey = focus?.key || "document";
  const mode = filetype === "pdf" || modeChoice.key === focusKey ? modeChoice.mode : focus ? "text" : "page";
  const setMode = (mode: "page" | "text") => setModeChoice({ key: focusKey, mode });
  const page = navigation.key === focusKey ? navigation.page : focus?.location?.pdf_page || 1;
  const url = file?.identity === identity ? file.url : "";
  const params = new URLSearchParams({ page: String(textNavigation.key === focusKey ? textNavigation.page : 1), page_size: "20", revision: String(revision) });
  if (textNavigation.key !== focusKey) {
    if (focus?.occurrenceId) params.set("occurrence_id", focus.occurrenceId);
    else if (focus?.entryId) params.set("entry_id", focus.entryId);
    else if (focus?.unitId) params.set("unit_id", focus.unitId);
  }
  const text = usePersistentWorkspace<AuditTextPage>(mode === "text" || filetype === "docx" ? textPath + "?" + params : "", ownerId);
  const staleSourceText = expectedTextGeneration !== undefined && text.data && (text.data.generation !== expectedTextGeneration || isTaskRunning(text.data.status));
  const selected = useRef<HTMLElement>(null);
  const selectedUnit = text.data?.units.find(unit => focus?.unitId ? unit.id === focus.unitId : Boolean(focus?.location && sameLocation(unit.location, focus.location)
    && (focus.location.start ?? 0) >= (unit.location.start ?? 0) && (focus.location.start ?? 0) < Math.max((unit.location.start ?? 0) + 1, unit.location.end ?? Infinity)));
  useEffect(() => { selected.current?.scrollIntoView({ block: "nearest", behavior: "instant" }); }, [focusKey, selectedUnit?.id]);
  useEffect(() => {
    if (filetype !== "pdf") return;
    let active = true, objectUrl = "";
    const clear = () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); setFile(null); };
    const off = subscribeToSessionChanges(clear);
    void withPrivateOwner(ownerId, readOriginal).then(result => {
      if (!active) return;
      objectUrl = URL.createObjectURL(result.blob); setFile({ identity, url: objectUrl }); setError("");
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "原稿读取失败。"); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); off(); };
  }, [identity, filetype, ownerId, attempt, readOriginal]);
  const parsedText = <>
    {text.error ? <p role="alert">{text.error}<button type="button" onClick={text.reload}>重新读取解析文字</button></p> : text.loading ? <LoadingState role="status">正在读取本人稿件的解析文字…</LoadingState> : staleSourceText ? <p role="alert">来源正在重新解析或解析版本已变化，旧批次文字暂不显示。请关闭来源并刷新列表后重新打开。</p> : text.data ? <>
      <div className="stl4-audit-toolbar"><span>已解析 {text.data.count} 个文本位置</span><div><button type="button" disabled={text.data.page <= 1} onClick={() => setTextNavigation({ key: focusKey, page: text.data!.page - 1 })}>前一组段落</button><span>第 {text.data.page} 组</span><button type="button" disabled={!text.data.next_page} onClick={() => setTextNavigation({ key: focusKey, page: text.data!.next_page! })}>后一组段落</button></div></div>
      <div className="stl4-audit-parsed-paper">{text.data.units.map(unit => <article key={unit.id} ref={unit.id === selectedUnit?.id ? selected : undefined} data-selected={unit.id === selectedUnit?.id || undefined}><h3>{auditLocation(unit.location)}</h3>{unit.coverage_status === "unread_content" ? <small>此位置包含尚未核对的扫描或图像内容，不能把未解析部分视为空白。</small> : null}<p>{unit.id === selectedUnit?.id ? markSelection(unit, focus) : unit.text || "此位置未解析到可用文字。"}</p></article>)}{!text.data.units.length ? <p>当前尚无可读取的解析文字。原稿仍保留；处理结束后可重试或回到原稿核对。</p> : null}</div>
      {text.data.notice ? <p className="stl4-audit-caption">{text.data.notice}</p> : null}
    </> : null}
  </>;
  return <section className="stl4-audit-manuscript-preview" aria-label="稿件解析预览">
    <nav className="stl4-audit-preview-mode" aria-label="稿件预览方式"><button type="button" aria-pressed={mode === "page"} onClick={() => setMode("page")}>{filetype === "pdf" ? "原稿页面" : "分页预览"}</button><button type="button" aria-pressed={mode === "text"} onClick={() => setMode("text")}>解析文字</button></nav>
    {filetype === "docx" ? <p className="stl4-audit-caption">段落、脚注和尾注以原稿实际解析位置为准；分页预览单独生成，不改变原稿。定位引文时显示对应解析文字。</p> : null}
    {mode === "text" ? parsedText : filetype === "docx" ? <CitationDocxPreview key={`${previewId}:${sourceGeneration}`} id={previewId} kind={previewKind} ownerId={ownerId} sourceGeneration={sourceGeneration} fallback={parsedText} /> : error ? <p role="alert">{error}<button type="button" onClick={() => setAttempt(value => value + 1)}>重试读取原稿</button></p> : !url ? <LoadingState role="status">正在安全读取本人的 PDF 原稿…</LoadingState> : <>
      <div className="stl4-audit-toolbar"><button type="button" disabled={page <= 1} onClick={() => setNavigation({ key: focusKey, page: page - 1 })}>上一页</button><label>稿件 PDF 页码 <input type="number" min={1} max={pages || undefined} value={page} onChange={event => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && (!pages || value <= pages)) setNavigation({ key: focusKey, page: value }); }} /></label><span>/ {pages || "—"}</span><button type="button" disabled={!pages || page >= pages} onClick={() => setNavigation({ key: focusKey, page: page + 1 })}>下一页</button><label>缩放 <select value={zoom} onChange={event => setZoom(Number(event.target.value))}><option value={75}>75%</option><option value={100}>100%</option><option value={125}>125%</option><option value={150}>150%</option></select></label></div>
      {pages > 0 && page > pages ? <p role="alert">当前记录的页码超出实际原稿范围，请核对解析位置。</p> : <div className="stl4-audit-manuscript-canvas"><PdfCanvas key={url} url={url} page={page} zoom={zoom} sourceWidth={0} sourceHeight={0} canonicalBlocks={[]} highlights={[]} onDocumentLoad={setPages} /></div>}
      {focus?.text ? <div className="stl4-audit-preview-selection"><strong>{auditLocation(focus.location)}</strong><p>{focus.text}</p><small>仅跳转到记录的物理页；未取得页面坐标时不绘制推测高亮。</small></div> : null}
    </>}
  </section>;
}

function sameLocation(left: AuditLocation, right: AuditLocation) {
  return left.part === right.part && (left.pdf_page ?? null) === (right.pdf_page ?? null) && (left.paragraph ?? null) === (right.paragraph ?? null) && (left.note_id ?? null) === (right.note_id ?? null);
}
function markSelection(unit: AuditTextUnit, focus?: CitationPreviewFocus) {
  const start = focus?.location?.start, end = focus?.location?.end, base = unit.location.start ?? 0;
  // Parser offsets count Unicode code points, including characters beyond BMP.
  const characters = Array.from(unit.text);
  if (focus?.unitId || typeof start !== "number" || typeof end !== "number" || start < base || end <= start || start - base >= characters.length) return unit.text;
  const localStart = start - base, localEnd = Math.min(end - base, characters.length);
  return <>{characters.slice(0, localStart).join("")}<mark>{characters.slice(localStart, localEnd).join("")}</mark>{characters.slice(localEnd).join("")}</>;
}
