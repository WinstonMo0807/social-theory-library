"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { PdfCanvas } from "@/components/pdf-canvas";
import { subscribeToSessionChanges } from "@/lib/api";
import { citationPreviewPath, commandCitationPreview, readCitationPreviewPdf, readCitationPreviewStatus, type CitationPreviewKind, type CitationPreviewStatus } from "@/lib/api/citation-preview.client";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";

/** A derived PDF never supplies guessed DOCX paragraph coordinates. */
export function CitationDocxPreview({ id, ownerId, kind, sourceGeneration, fallback }: {
  id: string; ownerId: string; kind: CitationPreviewKind; sourceGeneration: number; fallback: ReactNode;
}) {
  const load = useCallback((_path: string, signal: AbortSignal) => readCitationPreviewStatus(ownerId, kind, id, signal), [ownerId, kind, id]);
  const preview = usePersistentWorkspace<CitationPreviewStatus>(citationPreviewPath(kind, id), ownerId, data => data.poll_after_ms, load);
  const [file, setFile] = useState<{ key: string; url: string } | null>(null), [error, setError] = useState("");
  const [page, setPage] = useState(1), [zoom, setZoom] = useState(100), [attempt, setAttempt] = useState(0);
  const [loadedPages, setLoadedPages] = useState(0);
  const autoStarted = useRef("");
  const data = preview.data;
  const current = Boolean(data && data.audit_id === id && data.source_generation === sourceGeneration);
  const key = current && data?.status === "completed" ? `${ownerId}:${kind}:${id}:${sourceGeneration}:${data.content_hash}:${data.preview_generation}` : "";
  const url = key && file?.key === key ? file.url : "";
  const active = data?.status === "queued" || data?.status === "running";
  const previewGeneration = data?.preview_generation;
  const pageCount = loadedPages || data?.page_count || 0;
  const { mutate } = preview;
  useEffect(() => {
    if (!current || !data?.enabled || !["not_generated", "source_changed"].includes(data.status) || autoStarted.current === `${ownerId}:${kind}:${id}:${sourceGeneration}`) return;
    autoStarted.current = `${ownerId}:${kind}:${id}:${sourceGeneration}`;
    const body = { action: "generate" as const, expected_preview_revision: data.preview_revision, source_generation: sourceGeneration };
    void mutate(JSON.stringify(body), (_latest, request_id) => commandCitationPreview(ownerId, kind, id, { ...body, request_id })).catch(() => {});
  }, [current, data, sourceGeneration, id, kind, ownerId, mutate]);
  useEffect(() => {
    if (!key || !previewGeneration) return;
    let alive = true, objectUrl = "";
    const request = new AbortController();
    const clear = () => { alive = false; request.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); setFile(null); };
    const off = subscribeToSessionChanges(clear);
    void withPrivateOwner(ownerId, () => readCitationPreviewPdf(ownerId, kind, id, previewGeneration, request.signal), request.signal).then(blob => {
      if (!alive) return;
      objectUrl = URL.createObjectURL(blob); setFile({ key, url: objectUrl }); setPage(1); setLoadedPages(0); setError("");
    }).catch(reason => { if (alive) setError(reason instanceof Error ? reason.message : "分页预览读取失败，解析文字仍可查看。"); });
    return () => { alive = false; request.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); off(); };
  }, [key, previewGeneration, ownerId, id, kind, attempt]);
  async function command(action: "generate" | "cancel") {
    if (!current || !data || preview.pending) return;
    const body = { action, expected_preview_revision: data.preview_revision, source_generation: sourceGeneration };
    try { await mutate(JSON.stringify(body), (_latest, request_id) => commandCitationPreview(ownerId, kind, id, { ...body, request_id })); }
    catch { /* Workspace retains the explicit conflict and current version. */ }
  }
  return <div className="stl4-audit-docx-preview" aria-label="DOCX 分页预览">
    <p className="stl4-audit-caption">{data?.notice || "预览页码可能与 Word 不同。引文按原稿段落定位。"}</p>
    {!current && data ? <p role="alert">稿件处理版本已更新，请重新读取稿件后再查看分页预览。旧预览不再显示。</p> : null}
    {preview.error || error ? <p role="alert">{preview.error || error}</p> : null}
    {data?.message ? <p role={data.status === "failed" ? "alert" : "status"}>{data.message}</p> : null}
    <div className="stl4-audit-toolbar">
      {preview.loading ? <span role="status">正在读取私人预览状态…</span> : active ? <span role="status">{data?.status === "queued" ? "分页预览正在排队" : "正在生成分页预览"}，引文检查与原稿保留。</span> : null}
      {current && data?.enabled && !active && data.status !== "completed" ? <button type="button" disabled={preview.pending} onClick={() => void command("generate")}>生成分页预览</button> : null}
      {current && active ? <button type="button" disabled={preview.pending} onClick={() => void command("cancel")}>取消分页预览</button> : null}
      <button type="button" disabled={preview.pending} onClick={() => { preview.reload(); setAttempt(value => value + 1); }}>{preview.pollPaused ? "继续读取预览进度" : "重新读取预览"}</button>
    </div>
    {url && data ? <><div className="stl4-audit-toolbar"><button type="button" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><label>预览页码 <input type="number" min={1} max={pageCount || undefined} value={page} onChange={event => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && value <= pageCount) setPage(value); }} /></label><span>/ {pageCount}</span><button type="button" disabled={page >= pageCount} onClick={() => setPage(value => value + 1)}>下一页</button><label>缩放 <select value={zoom} onChange={event => setZoom(Number(event.target.value))}>{[75, 100, 125, 150].map(value => <option key={value} value={value}>{value}%</option>)}</select></label></div><div className="stl4-audit-manuscript-canvas"><PdfCanvas key={url} url={url} page={page} zoom={zoom} sourceWidth={0} sourceHeight={0} canonicalBlocks={[]} highlights={[]} onDocumentLoad={setLoadedPages} /></div></> : <>{current && data?.status === "completed" && !error ? <p role="status">正在加载 PDF 预览…</p> : null}<p className="stl4-audit-caption">分页预览暂未就绪，以下显示原稿中实际解析的文字。</p>{fallback}</>}
  </div>;
}
