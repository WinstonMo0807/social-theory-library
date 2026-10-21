"use client";

import { useState } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { outlinePath, type OutlineState } from "@/lib/api/curation-workspace.client";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import { asRecord } from "./workflow-types";

type Chapter = { title: string; asset_id: string; document_revision_id: string; outline_revision_id: string; outline_node_id: string; page_start: number; page_end: number };
export function ContributionScopeEditor({ editionId, value, disabled, onChange }: { editionId: string; value: unknown; disabled: boolean; onChange: (value: object) => void }) {
  const scope = asRecord(value), chapters = Array.isArray(scope.chapters) ? scope.chapters as Chapter[] : [];
  const [fileId, setFileId] = useState(""), [nodeId, setNodeId] = useState(""), [lastPage, setLastPage] = useState("");
  const token = getServerSessionCredential(), chapterMode = scope.kind === "chapter";
  const editions = useApiResource<CollectionPage<WorkLibraryRow>>(chapterMode && editionId ? `/catalog/admin/library/works/?view=editions&edition_id=${encodeURIComponent(editionId)}` : "", token);
  const files = editions.data?.results.find(row => row.id === editionId)?.assets?.filter(row => row.kind === "normalized" && row.status === "ready" && row.validation_status === "valid") || [];
  const source = useApiResource<OutlineState>(chapterMode && fileId ? outlinePath(fileId) : "", token);
  const outline = source.data?.active, documentId = source.data?.asset?.document_revision_id;
  const node = outline?.nodes?.find(row => row.id === nodeId), start = node?.pdf_page;
  const end = lastPage ? Number(lastPage) : start;
  const canAdd = Boolean(node?.id && start && end && end >= start && end <= (source.data?.asset?.page_count || 0) && outline?.id && documentId
    && outline.document_revision_id === documentId && source.data?.asset?.source_current !== false && !chapters.some(row => row.outline_revision_id === outline.id && row.outline_node_id === node.id));
  return <fieldset disabled={disabled} aria-label="此人的版本责任范围"><label><span>责任范围</span><select value={chapterMode ? "chapter" : "edition"} onChange={event => onChange(event.target.value === "chapter" ? { kind: "chapter", chapters: [] } : { kind: "edition" })}><option value="edition">整部出版版本</option><option value="chapter">明确章节（不作为整部著作作者）</option></select></label>
    {chapterMode ? <><p>从本版真实目录选择该人承担的章节，并核对结束页；同一人可选择多个章节。更换原文后须重新确认。</p>
      <ul>{chapters.map((row, index) => <li key={`${row.outline_revision_id}:${row.outline_node_id}`}><strong>{row.title}</strong> · PDF 第 {row.page_start}–{row.page_end} 页 <button type="button" onClick={() => onChange({ kind: "chapter", chapters: chapters.filter((_, i) => i !== index) })}>移除此章节</button></li>)}</ul>
      {editions.error || source.error ? <p role="alert">{editions.error || source.error}<button type="button" onClick={() => { editions.retry(); source.retry(); }}>重新读取章节来源</button></p> : null}
      <label><span>本版原文文件</span><select value={fileId} onChange={event => { setFileId(event.target.value); setNodeId(""); setLastPage(""); }}><option value="">选择原文文件</option>{files.map(row => <option key={row.id} value={row.id}>{row.original_filename || "阅读文件"} · {row.page_count} 页</option>)}</select></label>
      <label><span>当前目录章节</span><select value={nodeId} disabled={!outline || source.loading} onChange={event => { setNodeId(event.target.value); setLastPage(""); }}><option value="">选择有准确起页的章节</option>{outline?.nodes?.filter(row => row.pdf_page && row.id).map(row => <option key={row.id} value={row.id}>{row.title || row.chapter_title} · 第 {row.pdf_page} 页</option>)}</select></label>
      <label><span>该章节结束 PDF 页序</span><input type="number" min={start || 1} max={source.data?.asset?.page_count} value={lastPage} placeholder={start ? String(start) : ""} onChange={event => setLastPage(event.target.value)} /></label>
      <button type="button" disabled={!canAdd || chapters.length >= 100} onClick={() => { if (canAdd && node?.id && start && end && outline && documentId) { onChange({ kind: "chapter", chapters: [...chapters, { title: node.title || node.chapter_title, asset_id: fileId, document_revision_id: documentId, outline_revision_id: outline.id, outline_node_id: node.id, page_start: start, page_end: end }] }); setNodeId(""); setLastPage(""); } }}>确认加入所选章节</button>
      {fileId && !source.loading && (!outline || !documentId) ? <p>当前文件尚无完整正文和目录修订，请先在文件处理中完成目录核对。</p> : null}
    </> : null}
  </fieldset>;
}
