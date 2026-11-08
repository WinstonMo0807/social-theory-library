"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useAdminSession } from "@/lib/admin-session";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import styles from "./journal-contents-candidates.module.css";

type Candidate = { node_id: string; title: string; printed_label: string; pdf_page: number | null; contents_page: number | null; source: string; calibration_status: string; candidate_source: string };
type Directory = { owner_id: string; edition_id: string; edit_version: string; asset_id: string | null; outline_revision_id: string | null; files: { id: string; name: string; page_count: number }[]; count: number; page: number; page_size: number; results: Candidate[]; message: string };
type Props = { editionId: string; editVersion: string; disabled: boolean; rows: Record<string, unknown>[]; onAppend: (rows: Record<string, unknown>[]) => void };

export function JournalContentsCandidates(props: Props) {
  const user = useAdminSession(), owner = user ? String(user.id) : null;
  const [opened, setOpened] = useState(false), [fileId, setFileId] = useState(""), [page, setPage] = useState(1);
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<Directory>(path, {
    cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]), headers: { "X-Editor-Owner": owner || "" },
  }, getServerSessionCredential()), [owner]);
  const params = new URLSearchParams({ page: String(page) });
  if (fileId) params.set("asset_id", fileId);
  const source = usePersistentWorkspace<Directory>(opened && !props.disabled && props.editionId ? `/catalog/admin/editions/${props.editionId}/journal-contents-candidates/?${params}` : "", owner, undefined, load);
  const data = source.data;
  const matches = Boolean(data && data.owner_id === owner && data.edition_id === props.editionId && data.edit_version === props.editVersion);
  return <details data-disclosure="collection" className={styles.panel} open={opened} onToggle={event => setOpened(event.currentTarget.open)}>
    <summary>从文件目录选取论文题名</summary>
    {opened ? <div className={styles.body}>
      <p>先核对目录中的文章，再追加到下方草稿。已有条目保留；作者、终止页及馆内关联由你填写。</p>
      {props.disabled ? <p>当前书目不可编辑。</p> : null}
      {source.loading ? <LoadingState role="status">正在读取本期目录…</LoadingState> : null}
      {source.error ? <p role="alert">{source.error}</p> : null}
      {data?.files.length ? <label>阅读文件<select data-stl-select value={fileId || data.asset_id || ""} onChange={event => { setFileId(event.target.value); setPage(1); }}>
        <option value="">请选择文件</option>{data.files.map(file => <option value={file.id} key={file.id}>{file.name} · {file.page_count} 页</option>)}
      </select></label> : null}
      {data && !matches ? <p role="alert">书目已更新，当前填写仍保留。请先用书目页的重新读取核对差异，再选择目录条目。</p> : null}
      {data ? <><p>{data.message}</p>{data.asset_id ? <Link href={`/admin/library/assets/${data.asset_id}/outline`} target="_blank" rel="noopener noreferrer">在新标签页核对原文与目录</Link> : null}</> : null}
      {data && matches && !source.error ? <CandidateSelection key={`${data.asset_id}:${data.outline_revision_id}:${page}:${data.edit_version}`} {...props} data={data} /> : null}
      {data && data.count > data.page_size ? <nav aria-label="目录候选分页" className={styles.actions}>
        <button type="button" className="button secondary" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button>
        <span>第 {page} / {Math.ceil(data.count / data.page_size)} 页 · 换页后重新选择</span>
        <button type="button" className="button secondary" disabled={page * data.page_size >= data.count} onClick={() => setPage(value => value + 1)}>下一页</button>
      </nav> : null}
      {!props.disabled && !source.loading ? <button type="button" className="button secondary" onClick={source.reload}>重新读取目录</button> : null}
    </div> : null}
  </details>;
}

function CandidateSelection({ data, rows, disabled, onAppend }: Props & { data: Directory }) {
  const [selected, setSelected] = useState<string[]>([]), [reviewed, setReviewed] = useState(false), [message, setMessage] = useState("");
  // Exact matches only prevent accidental repetition; they never merge article identities.
  const present = (candidate: Candidate) => rows.some(row => row.candidate_source === candidate.candidate_source || String(row.title || "").trim() === candidate.title.trim() && String(row.page_range || "").trim() === candidate.printed_label.trim());
  const chosen = data.results.filter(row => selected.includes(row.node_id) && !present(row));
  const full = rows.length + chosen.length > 500;
  if (!data.results.length) return null;
  return <div>
    <ul className={styles.list}>{data.results.map(candidate => {
      const exists = present(candidate);
      return <li key={candidate.node_id}><label className={styles.row}>
        <input type="checkbox" disabled={disabled || exists} checked={selected.includes(candidate.node_id) && !exists} onChange={event => { setReviewed(false); setMessage(""); setSelected(values => event.target.checked ? [...values, candidate.node_id] : values.filter(id => id !== candidate.node_id)); }} />
        <span><strong>{candidate.title}</strong><small>{candidate.printed_label ? `印刷起始页 ${candidate.printed_label}` : "印刷页待核对"} · {candidate.pdf_page ? `PDF 第 ${candidate.pdf_page} 页` : "落点待核对"}{candidate.contents_page ? ` · 目录在第 ${candidate.contents_page} 页` : ""} · {candidate.source === "pdf_bookmark" ? "原文件书签" : candidate.source === "printed_contents" ? "正文目录" : candidate.source === "manual" ? "人工编辑目录" : "正文标题候选"}{exists ? " · 下方已有同题名及起始页，请核对现有条目" : ""}</small></span>
      </label></li>;
    })}</ul>
    <label className={styles.row}><input type="checkbox" checked={reviewed} disabled={disabled || !chosen.length} onChange={event => setReviewed(event.target.checked)} /><span>已对照原文，所选条目是本期文章。栏目、广告等不作为论文追加。</span></label>
    {full ? <p role="alert">本期目录最多 500 条，请减少所选条目，现有内容不会被删除。</p> : null}
    <button type="button" className="button secondary" disabled={disabled || !chosen.length || !reviewed || full} onClick={() => {
      onAppend(chosen.map(candidate => ({ id: null, article_work_id: null, title: candidate.title, author_display: "", page_range: candidate.printed_label, candidate_source: candidate.candidate_source })));
      setSelected([]); setReviewed(false); setMessage("已追加到下方草稿，请补齐作者和终止页，再保存本页填写。");
    }}>追加所选 {chosen.length || ""} 篇至草稿</button>
    {message ? <p role="status">{message}</p> : null}
  </div>;
}
