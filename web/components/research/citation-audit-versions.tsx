"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileUp, History } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Dialog } from "@/components/ui/dialog";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { createCitationAuditVersion, type AuditCapabilities, type AuditData, type AuditVersionComparison, type AuditVersions, type ResearchRecord } from "@/lib/api/research.client";
import { isTaskRunning } from "@/lib/api/task-polling";
import { auditStatuses } from "./citation-audit-shared";

const MAX_UPLOAD_BYTES = 12 * 1024 * 1024;
const fileSize = (bytes: number) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / 1024 / 1024).toFixed(2)} MiB`;

type VersionUpload = { file: File; requestId: string; expectedRevision: number; onlyChanged: boolean };

const comparisonCounts: Array<{ field: keyof AuditVersionComparison; label: string }> = [
  { field: "total_occurrences", label: "本版引文" }, { field: "changed_occurrences", label: "发生变化" },
  { field: "added_occurrences", label: "新增引文" }, { field: "removed_occurrences", label: "前版已移除" },
  { field: "reused_occurrences", label: "沿用结果" }, { field: "ambiguous_occurrences", label: "对应关系待核对" },
  { field: "changed_bibliography_entries", label: "书目变化" }, { field: "rechecked_occurrences", label: "本轮重查范围" },
];

export function CitationAuditVersions({ record, ownerId, disabled = false, onRefresh, retrySession }: {
  record: ResearchRecord<AuditData>; ownerId: string; disabled?: boolean; onRefresh: () => void; retrySession: () => void;
}) {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const versions = usePersistentWorkspace<AuditVersions>(`/reading/citation-audits/${encodeURIComponent(record.id)}/versions/`, ownerId,
    result => result.versions?.some(row => isTaskRunning(row.status)) ? 3000 : null);
  const available = versions.data?.current_id === record.id ? versions.data.versions : [];
  const current = available.find(row => row.id === record.id);
  const comparison = record.data.version_comparison;
  const baseId = comparison?.base_audit_id || record.data.version_lineage?.parent_audit_id;
  const base = available.find(row => row.id === baseId);
  const needsParsedReport = record.data.parsed !== true;
  const uploadingDisabled = disabled || isTaskRunning(record.status) || needsParsedReport;
  const refresh = () => { versions.reload(); onRefresh(); };
  return <section className="stl4-audit-versions" aria-label="稿件版本与变化">
    <div className="stl4-audit-version-bar"><label><History size={14} />稿件版本
      {current ? <select aria-label="选择稿件版本" disabled={disabled || uploading} value={record.id} onChange={event => router.push(`/account/citation-audits/${event.target.value}`)}>
        {available.map(version => <option key={version.id} value={version.id}>v{version.manuscript_revision} · {version.filename} · {new Date(version.created_at).toLocaleString("zh-CN")}{version.id === record.id ? "（当前查看）" : ""}</option>)}
      </select> : <span>v{record.data.manuscript_revision || 1} · {record.data.filename}</span>}
    </label><div><button type="button" onClick={() => setUploading(true)} disabled={uploadingDisabled || uploading}><FileUp size={14} />上传新版本</button><button type="button" disabled={disabled || uploading || versions.loading} onClick={refresh}>读取版本记录</button></div></div>
    {versions.loading ? <p className="stl4-audit-version-note" role="status">正在读取本人保存的稿件版本…</p> : versions.error ? <p className="stl4-audit-version-note" role="alert">{versions.error}</p> : versions.data && !current ? <p className="stl4-audit-version-note" role="alert">当前稿件不在返回的版本列表中，请重新读取记录。</p> : null}
    <p className="stl4-audit-version-note">{versions.data?.notice || "每个稿件版本保留独立原稿、报告和人工记录。切换版本将打开所选版本的报告。"}{needsParsedReport ? " 取得已解析的报告后可上传新版本。" : isTaskRunning(record.status) ? " 当前核验完成或取消后可上传下一版稿件。" : ""}{versions.data?.truncated ? <> <Link href="/account/citation-audits">从体检任务列表查看其他记录</Link></> : null}</p>
    {comparison || baseId ? <div className="stl4-audit-version-changes"><h3>与前版的实际变化{base ? <> · <Link href={`/account/citation-audits/${base.id}`}>回看基准 v{base.manuscript_revision}</Link></> : null}</h3>
      {comparison?.status === "completed" ? <dl className="stl4-audit-version-counts">{comparisonCounts.flatMap(({ field, label }) => {
        const value = comparison[field];
        return typeof value === "number" && Number.isFinite(value) && value >= 0 ? [<div key={field}><dt>{label}</dt><dd>{value}</dd></div>] : [];
      })}</dl> : <p role="status">新稿尚未完成解析比较，变化数量待确定。</p>}
      {comparison?.notice ? <p>{comparison.notice}</p> : null}
      {record.data.version_lineage ? <p>{record.data.version_lineage.check_changed_only ? "本版按变化内容重新核验；可继承的记录由实际比较结果确定。" : "本版重新核验全部引文。"}</p> : null}
      {baseId && !base && !versions.loading && !versions.error ? <p>基准稿件当前未能从版本列表读取，不能据此认定旧报告已删除。</p> : null}
    </div> : null}
    {available.length > 1 ? <details className="stl4-audit-version-changes"><summary>回看保存的稿件版本（{available.length}）</summary><ul className="stl4-audit-version-history">{available.map(version => <li key={version.id}><span>v{version.manuscript_revision} · {version.filename}<br /><time dateTime={version.created_at}>{new Date(version.created_at).toLocaleString("zh-CN")}</time> · {auditStatuses[version.status] || "已保存"}</span>{version.id === record.id ? <span>当前查看</span> : <Link href={`/account/citation-audits/${version.id}`}>打开报告</Link>}</li>)}</ul></details> : null}
    {uploading ? <VersionUploadForm record={record} ownerId={ownerId} disabled={uploadingDisabled} onClose={() => setUploading(false)} onRefresh={refresh} retrySession={retrySession}
      onUpload={({ file, requestId, expectedRevision, onlyChanged }) => createCitationAuditVersion(record.id, file, { request_id: requestId, expected_revision: expectedRevision, check_changed_only: onlyChanged })} /> : null}
  </section>;
}

function VersionUploadForm({ record, ownerId, disabled, onUpload, onClose, onRefresh, retrySession }: {
  record: ResearchRecord<AuditData>; ownerId: string; disabled: boolean;
  onUpload: (value: VersionUpload) => Promise<ResearchRecord<AuditData>>;
  onClose: () => void; onRefresh: () => void; retrySession: () => void;
}) {
  const router = useRouter();
  const capabilities = usePersistentWorkspace<AuditCapabilities>("/reading/citation-audits/capabilities/", ownerId);
  const [file, setFile] = useState<File | null>(null);
  const [onlyChanged, setOnlyChanged] = useState(true);
  const [expectedRevision, setExpectedRevision] = useState(record.revision);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [identityError, setIdentityError] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const alive = useRef(false);
  const pending = useRef(false);
  const operation = useRef<{ file: File; fingerprint: string; id: string } | null>(null);
  useEffect(() => {
    alive.current = true;
    const clear = () => {
      alive.current = false; operation.current = null; setFile(null); setIdentityError(true);
      if (input.current) input.current.value = "";
    };
    const off = subscribeToSessionChanges(clear);
    return () => { alive.current = false; operation.current = null; off(); };
  }, []);
  const limit = Math.min(MAX_UPLOAD_BYTES, capabilities.data?.max_upload_bytes || MAX_UPLOAD_BYTES);
  const stale = conflict || expectedRevision !== record.revision;
  function chooseFile(candidate?: File) {
    if (!candidate || pending.current || !alive.current) return;
    if (!/\.(docx|pdf)$/i.test(candidate.name) || candidate.size <= 0 || candidate.size > limit) {
      setError(`请选择大小大于 0 且不超过 ${fileSize(limit)} 的 PDF 或 DOCX 稿件。原先选择的文件仍保留。`); return;
    }
    setFile(candidate); setError(""); operation.current = null;
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || pending.current || disabled || stale || identityError || !alive.current) return;
    pending.current = true; setBusy(true); setError("");
    const fingerprint = JSON.stringify({ expectedRevision, onlyChanged });
    if (operation.current?.file !== file || operation.current.fingerprint !== fingerprint) operation.current = { file, fingerprint, id: crypto.randomUUID() };
    try {
      const created = await withPrivateOwner(ownerId, () => {
        if (!alive.current) throw new DOMException("Session changed", "AbortError");
        return onUpload({ file, requestId: operation.current!.id, expectedRevision, onlyChanged });
      });
      if (!alive.current) return;
      onClose(); router.push(`/account/citation-audits/${created.id}`);
    } catch (reason) {
      if (!alive.current) return;
      setError(reason instanceof Error ? reason.message : "新稿件未能提交，所选文件和检查选项已保留。");
      if (reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403].includes(reason.status)) {
        setIdentityError(true); setFile(null); operation.current = null;
        if (input.current) input.current.value = "";
      } else if (reason instanceof ApiRequestError && reason.status === 409) { setConflict(true); onRefresh(); }
    } finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  return <Dialog open className="stl4-audit-dialog" onRequestClose={() => { if (!busy) onClose(); }} aria-labelledby="audit-version-title"><form className="stl4-audit-version-form" onSubmit={submit} aria-busy={busy}>
    <h2 id="audit-version-title">上传新的稿件版本</h2>
    <p className="stl4-audit-version-baseline">比较基准：{record.data.filename} · 稿件版本 {record.data.manuscript_revision || 1}</p>
    <p>上传后生成独立版本。现有原稿、报告和人工记录继续保留，可从版本列表回看。</p>
    <label className="stl4-audit-version-file"><strong>{file?.name || "选择修改后的稿件"}</strong>
      <input ref={input} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" aria-label="选择新版本稿件"
        disabled={busy || disabled || identityError} onChange={event => chooseFile(event.target.files?.[0])} />
      <small>{file ? `已选 ${fileSize(file.size)} · ` : ""}PDF / DOCX，最大 {fileSize(limit)}</small>
    </label>
    <label className="stl4-audit-version-check"><input type="checkbox" checked={onlyChanged} disabled={busy || disabled || identityError} onChange={event => setOnlyChanged(event.target.checked)} />
      <span>仅重新核验变化内容<small>解析新稿后确定实际变化范围；符合继承条件的结果与人工记录保留，无法确认的项目仍需核验。</small></span>
    </label>
    <p>新稿沿用当前稿件的检查项与来源范围。变化数量在实际解析完成后显示。</p>
    {capabilities.error ? <p role="alert">{capabilities.error}<button type="button" disabled={busy} onClick={capabilities.reload}>重新读取上传限制</button></p> : null}
    {stale ? <p role="alert">报告或任务条件已有变化，所选文件和选项已保留。<button type="button" disabled={busy || disabled || identityError} onClick={() => { setExpectedRevision(record.revision); setConflict(false); operation.current = null; }}>已核对当前报告，继续使用所选稿件</button></p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {identityError ? <button type="button" onClick={retrySession}>重新验证登录</button> : null}
    <footer><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="is-primary" type="submit" disabled={!file || busy || disabled || stale || identityError || !capabilities.data || Boolean(capabilities.error)}>{busy ? "正在提交新版本…" : "保存新版本并开始核验"}</button></footer>
  </form></Dialog>;
}
