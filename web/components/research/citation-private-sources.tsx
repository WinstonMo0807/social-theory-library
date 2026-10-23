"use client";

import { createRequestKey } from "../../lib/request-key";
import { useEffect, useRef, useState } from "react";
import { FilePlus2, LockKeyhole } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import type { Paginated } from "@/lib/api/pagination";
import { commandPrivateCitationSource, createPrivateCitationSource, deletePrivateCitationSource, downloadPrivateCitationSource, privateCitationSourcePath, type AuditCapabilities, type AuditData, type AuditEntry, type PrivateCitationCandidate, type PrivateCitationReference, type PrivateCitationSourceData, type ResearchRecord } from "@/lib/api/research.client";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { isTaskRunning } from "@/lib/api/task-polling";
import { auditLocation, auditStatuses } from "./citation-audit-shared";
import type { useAuditWorkspace } from "./citation-audit-report";
import { CitationPrivateSourceDocument } from "./citation-manuscript-preview";

type SourceRecord = ResearchRecord<PrivateCitationSourceData>;
type AuditWorkspace = ReturnType<typeof useAuditWorkspace>;

/** Every inclusion is an explicit owner selection; a new upload is not selected automatically. */
export function CitationPrivateSourcePicker({ ownerId, selectedIds, onChange, disabled = false }: { ownerId: string; selectedIds: string[]; onChange: (ids: string[]) => void; disabled?: boolean }) {
  const [page, setPage] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [citation, setCitation] = useState("");
  const [scan, setScan] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [remove, setRemove] = useState<SourceRecord | null>(null);
  const [preview, setPreview] = useState<SourceRecord | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const alive = useRef(false), pending = useRef(false);
  const change = useRef(onChange);
  const operation = useRef<{ file: File; fingerprint: string; id: string } | null>(null);
  const sources = usePersistentWorkspace<Paginated<SourceRecord>>(`${privateCitationSourcePath()}?page=${page}`, ownerId,
    data => data.results.some(item => isTaskRunning(item.status)) ? 3000 : null);
  const capabilities = usePersistentWorkspace<AuditCapabilities>("/reading/citation-audits/capabilities/", ownerId);
  useEffect(() => { change.current = onChange; }, [onChange]);
  useEffect(() => {
    alive.current = true;
    const off = subscribeToSessionChanges(() => { alive.current = false; operation.current = null; setFile(null); setTitle(""); setCitation(""); setPreview(null); setRemove(null); change.current([]); if (input.current) input.current.value = ""; });
    return () => { alive.current = false; off(); };
  }, [ownerId]);
  const limit = Math.min(12 * 1024 * 1024, capabilities.data?.max_upload_bytes || Infinity);
  const blocked = disabled || busy;
  function failure(reason: unknown) {
    if (reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403].includes(reason.status)) {
      setFile(null); setTitle(""); setCitation(""); setPreview(null); setRemove(null); onChange([]); operation.current = null;
      if (input.current) input.current.value = "";
      sources.reload();
    }
    setError(reason instanceof Error ? reason.message : "私人来源操作未完成，已保存的文件继续保留。");
  }
  async function upload() {
    if (!file || pending.current || blocked || !alive.current) return;
    pending.current = true; setBusy(true); setError(""); setNotice("");
    const fingerprint = JSON.stringify({ title: title.trim(), citation: citation.trim(), scan_ocr: scan });
    if (operation.current?.file !== file || operation.current.fingerprint !== fingerprint) operation.current = { file, fingerprint, id: createRequestKey() };
    try {
      await withPrivateOwner(ownerId, () => createPrivateCitationSource(file, { request_id: operation.current!.id, title: title.trim(), citation: citation.trim(), scan_ocr: scan }));
      if (!alive.current) return;
      operation.current = null; setFile(null); setTitle(""); setCitation(""); if (input.current) input.current.value = "";
      setPage(1); sources.reload(); setNotice("来源文件已保存。解析完成后，请勾选需要用于本次核对的文件。");
    } catch (reason) { if (alive.current) failure(reason); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  async function command(row: SourceRecord, action: "cancel" | "retry" | "delete" | "download") {
    if (pending.current || blocked || !alive.current) return;
    pending.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const result = await withPrivateOwner<SourceRecord | Awaited<ReturnType<typeof downloadPrivateCitationSource>> | void>(ownerId, () => action === "delete" ? deletePrivateCitationSource(row.id, row.revision) : action === "download" ? downloadPrivateCitationSource(row.id) : commandPrivateCitationSource(row.id, { expected_revision: row.revision, action }));
      if (!alive.current) return;
      if (action === "delete") { onChange(selectedIds.filter(id => id !== row.id)); setRemove(null); setPreview(null); }
      if (action === "download" && result && "blob" in result) { const url = URL.createObjectURL(result.blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = row.data.filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
      sources.reload();
    } catch (reason) { if (alive.current) { failure(reason); if (reason instanceof ApiRequestError && reason.status === 409) { sources.reload(); setRemove(null); } } }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  return <section className="stl4-audit-private-sources" aria-label="本人来源文件"><div className="stl4-audit-private-source-heading"><strong><LockKeyhole size={12} />本人来源文件</strong><span>已选择 {selectedIds.length} / 4</span><button type="button" disabled={blocked || sources.loading} onClick={sources.reload}>刷新</button></div>
    <p className="stl4-audit-caption">只使用你明确勾选的文件。上传和匹配均不会进入公共馆藏。</p>
    {sources.error ? <p role="alert">{sources.error}</p> : sources.loading ? <p role="status">正在读取本人的来源文件…</p> : sources.data?.results.length ? <div className="stl4-audit-private-source-list">{sources.data.results.map(row => {
      const parsed = row.data.parsed === true && ["completed", "partial"].includes(row.status || "");
      const ready = parsed && (row.data.matchable_segment_count ?? 0) > 0;
      return <article key={row.id}><label><input type="checkbox" checked={selectedIds.includes(row.id)} disabled={blocked || (!selectedIds.includes(row.id) && (!ready || selectedIds.length >= 4))} onChange={event => onChange(event.target.checked ? [...selectedIds, row.id] : selectedIds.filter(id => id !== row.id))} /><span><strong>{row.data.title || row.data.filename}</strong><small>{row.data.filename}</small><small>{auditStatuses[row.status || ""] || "已保存"}{typeof row.data.segment_count === "number" ? ` · ${row.data.segment_count} 个文本位置` : ""}</small></span></label>{row.data.citation ? <p>{row.data.citation}</p> : null}<div><button type="button" disabled={blocked || !parsed} onClick={() => setPreview(row)}>查看来源</button><button type="button" disabled={blocked} onClick={() => void command(row, "download")}>下载原件</button>{isTaskRunning(row.status) ? <button type="button" disabled={blocked} onClick={() => void command(row, "cancel")}>取消解析</button> : ["failed", "canceled", "cancelled", "partial"].includes(row.status || "") ? <button type="button" disabled={blocked} onClick={() => void command(row, "retry")}>重试解析</button> : null}<button type="button" disabled={blocked || isTaskRunning(row.status)} onClick={() => setRemove(row)}>删除来源</button></div>{parsed && !ready ? <p>尚无可连续核对的文字。可查看已解析内容或下载原件，待补全识别后再选入。</p> : null}{row.error_code ? <p>来源解析尚未完成，原件仍保留，可重试。</p> : null}</article>;
    })}</div> : <p>尚未上传私人来源。可以补充用于核对的 PDF 或 DOCX。</p>}
    {sources.data && (page > 1 || sources.data.next) ? <nav className="stl4-audit-private-source-pages" aria-label="私人来源分页"><button type="button" disabled={blocked || page <= 1} onClick={() => setPage(value => value - 1)}>上一页来源</button><span>第 {page} 页</span><button type="button" disabled={blocked || !sources.data.next} onClick={() => setPage(value => value + 1)}>下一页来源</button></nav> : null}
    {selectedIds.length ? <button type="button" disabled={blocked} onClick={() => onChange([])}>清空本次来源选择</button> : null}
    <details className="stl4-audit-private-source-upload"><summary><FilePlus2 size={13} />上传用于核对的来源</summary><div><label>来源文件<input ref={input} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={blocked} onChange={event => { const next = event.target.files?.[0]; if (!next) return; if (!/\.(pdf|docx)$/i.test(next.name) || next.size <= 0 || next.size > limit) { setError("请选择有效的 PDF 或 DOCX，大小须大于 0 且不超过 12 MiB。此前所选文件保留。"); return; } setFile(next); setError(""); operation.current = null; }} /></label>{file ? <p>{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MiB</p> : null}<label>来源题名（可选）<input maxLength={240} disabled={blocked} value={title} onChange={event => setTitle(event.target.value)} /></label><label>书目信息（可选）<textarea maxLength={2000} disabled={blocked} value={citation} rows={3} onChange={event => setCitation(event.target.value)} /></label><label><input type="checkbox" checked={scan} disabled={blocked || !capabilities.data?.ocr?.available} onChange={event => setScan(event.target.checked)} />允许扫描文字识别</label><small>{capabilities.data?.ocr?.reason || "扫描文字识别按当前能力开放，默认关闭。"}</small><button type="button" className="is-primary" disabled={blocked || !file || !capabilities.data} onClick={() => void upload()}>{busy ? "正在处理…" : "保存并解析来源"}</button></div></details>
    {error ? <p role="alert">{error}</p> : null}{notice ? <p role="status">{notice}</p> : null}
    <Dialog className="stl4-audit-dialog" open={Boolean(remove)} aria-labelledby="citation-source-delete" onRequestClose={() => { if (!busy) setRemove(null); }}>{remove ? <><h2 id="citation-source-delete">删除本人来源文件</h2><p>{remove.data.filename}</p><p>这会删除该私人来源的原件与解析文字。曾引用它的报告会显示来源不可用，人工核对记录保留。下载原件后再确认删除。</p><footer><button type="button" disabled={busy} onClick={() => setRemove(null)}>保留来源</button><button type="button" disabled={busy} onClick={() => void command(remove, "delete")}>确认删除私人来源</button></footer></> : null}</Dialog>
    <Dialog className="stl4-audit-dialog" open={Boolean(preview)} aria-labelledby="citation-source-preview" onRequestClose={() => setPreview(null)}>{preview ? <><h2 id="citation-source-preview">{preview.data.title || preview.data.filename}</h2><CitationPrivateSourceDocument record={preview} ownerId={ownerId} /><footer><button type="button" onClick={() => setPreview(null)}>关闭来源</button></footer></> : null}</Dialog>
  </section>;
}

export function CitationAuditSources({ record, ownerId, workspace }: { record: ResearchRecord<AuditData>; ownerId: string; workspace: AuditWorkspace }) {
  const [editing, setEditing] = useState<{ ids: string[]; revision: number } | null>(null);
  const busy = workspace.busy || isTaskRunning(record.status);
  return <><button type="button" disabled={busy} onClick={() => setEditing({ ids: [...(record.data.private_source_ids || [])], revision: record.revision })}>{record.data.private_source_ids?.length ? `管理本次私人来源（${record.data.private_source_ids.length}）` : "补充本人来源"}</button>
    <Dialog className="stl4-audit-dialog" open={Boolean(editing)} aria-labelledby="audit-private-sources-title" onRequestClose={() => { if (!workspace.busy) setEditing(null); }}>{editing ? <><h2 id="audit-private-sources-title">选择本次用于核对的来源</h2><CitationPrivateSourcePicker ownerId={ownerId} selectedIds={editing.ids} disabled={busy} onChange={ids => setEditing({ ...editing, ids })} /><p>保存后使用全部勾选文件与馆藏资料重新核对。取消全部选择后恢复为仅馆藏范围；原稿与人工记录保留。</p>{editing.revision !== record.revision ? <p role="alert">报告已更新，来源选择保留。<button type="button" disabled={busy} onClick={() => setEditing({ ...editing, revision: record.revision })}>核对最新报告后继续</button></p> : null}{workspace.actionError ? <p role="alert">{workspace.actionError}</p> : null}<footer><button type="button" disabled={workspace.busy} onClick={() => setEditing(null)}>取消</button><button type="button" className="is-primary" disabled={busy || editing.revision !== record.revision} onClick={async () => { if (await workspace.command({ action: "sources", private_source_ids: editing.ids }, editing.revision)) setEditing(null); }}>保存来源范围并重查</button></footer></> : null}</Dialog>
  </>;
}

export function CitationPrivateMatches({ entry, record, ownerId, workspace }: { entry: AuditEntry; record: ResearchRecord<AuditData>; ownerId: string; workspace: AuditWorkspace }) {
  const [choice, setChoice] = useState<{ candidate: PrivateCitationCandidate; revision: number } | null>(null);
  const busy = workspace.busy || isTaskRunning(record.status);
  return <section className="stl4-audit-private-matches"><h4>本人来源候选</h4>{entry.private_candidates?.length ? entry.private_candidates.map(candidate => <article key={candidate.source_id}><strong>{candidate.title || candidate.filename || "本人来源文件"}</strong><p>{candidate.citation}</p>{candidate.source_status !== "available" ? <small>来源当前不可用，请重新读取或补充来源。</small> : <button type="button" disabled={busy} onClick={() => setChoice({ candidate, revision: record.revision })}>{entry.selected_private_source_id === candidate.source_id ? "已选本人来源 · 重新核对" : "确认对应此私人来源"}</button>}</article>) : <p>尚无可确认的本人来源候选。上传并明确选入来源后可重新匹配。</p>}<CitationAuditSources record={record} ownerId={ownerId} workspace={workspace} />
    <Dialog open={Boolean(choice)} className="stl4-audit-dialog" aria-labelledby="audit-private-match-title" onRequestClose={() => { if (!workspace.busy) setChoice(null); }}>{choice ? <><h2 id="audit-private-match-title">确认书目对应的私人来源</h2><p>{entry.raw}</p><blockquote>{choice.candidate.citation || choice.candidate.title || choice.candidate.filename}</blockquote><p>请核对作者、版本与出版信息。确认将重新检查引用此书目的位置，不会把私人来源加入公共馆藏。</p>{choice.revision !== record.revision ? <p role="alert">报告已更新，请关闭并重新核对候选。</p> : null}{workspace.actionError ? <p role="alert">{workspace.actionError}</p> : null}<footer><button type="button" disabled={workspace.busy} onClick={() => setChoice(null)}>取消</button><button type="button" disabled={busy || choice.revision !== record.revision} onClick={async () => { if (await workspace.command({ action: "match_private", entry_id: entry.id, source_id: choice.candidate.source_id }, choice.revision)) setChoice(null); }}>确认私人来源并重查</button></footer></> : null}</Dialog>
  </section>;
}

export function CitationPrivateReferencePreview({ reference, ownerId }: { reference: PrivateCitationReference; ownerId: string }) {
  const [open, setOpen] = useState(false);
  const source = usePersistentWorkspace<SourceRecord>(reference.source_status === "available" ? privateCitationSourcePath(reference.source_id) : "", ownerId,
    record => isTaskRunning(record.status) ? 3000 : null);
  const current = source.data;
  const valid = reference.source_status === "available" && current?.data.parsed === true && !isTaskRunning(current.status)
    && (current.data.source_generation ?? current.generation) === reference.source_generation;
  return <section className="stl4-audit-private-reference"><h3><LockKeyhole size={12} />本人来源原文</h3>{!valid ? <p role={source.loading ? "status" : "alert"}>{source.loading ? "正在核对私人来源权限与版本…" : source.error || "私人来源已删除、重新解析或暂不可用，旧片段不再显示。"}</p> : <><strong>{reference.title || reference.filename}</strong><p>{reference.citation}</p><small>{auditLocation(reference.location)}</small><blockquote>{reference.quote}</blockquote><button type="button" onClick={() => setOpen(value => !value)}>{open ? "收起私人原稿" : "查看本人来源原稿"}</button>{open ? <CitationPrivateSourceDocument record={current!} ownerId={ownerId} focus={{ key: `${reference.source_id}:${reference.source_generation}:${reference.unit_id}`, unitId: reference.unit_id, location: reference.location, text: reference.quote }} /> : null}</>}</section>;
}
