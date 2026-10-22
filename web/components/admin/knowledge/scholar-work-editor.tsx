"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { ArrowDown, ArrowUp, BookOpen, Plus, X } from "lucide-react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { ScholarWork } from "@/lib/api/scholars.types";
import { Dialog } from "@/components/ui/dialog";
import styles from "./scholar-editor.module.css";

type Page = { count: number; page: number; page_size: number; results: ScholarWork[] };
type Props = { profileId: string | null; kind: "essential" | "recommended"; selected: string[]; reasons: Record<string, string>;
  onChange: (ids: string[], reasons: Record<string, string>) => void };

export function ScholarWorkEditor({ profileId, kind, selected, reasons, onChange }: Props) {
  const owner = String(useAdminSession()?.id || ""), [open, setOpen] = useState(false), [query, setQuery] = useState(""), [search, setSearch] = useState(""), [page, setPage] = useState(1), [active, setActive] = useState("");
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<Page>(path, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential()), [owner]);
  const root = profileId ? `/catalog/admin/scholars/${profileId}/work-selection/?kind=${kind}` : "";
  const chosen = usePersistentWorkspace<Page>(root && selected.length ? `${root}&ids=${selected.join(",")}` : "", owner, undefined, load);
  const candidates = usePersistentWorkspace<Page>(root && open ? `${root}&q=${encodeURIComponent(search)}&page=${page}` : "", owner, undefined, load);
  const rows = chosen.error ? [] : chosen.data?.results || [], selectedId = selected.includes(active) ? active : selected[0], current = rows.find(row => row.id === selectedId);
  const title = kind === "essential" ? "代表作品" : "推荐阅读", limit = kind === "essential" ? 100 : 24;
  function move(index: number, offset: number) { const next = [...selected]; [next[index], next[index + offset]] = [next[index + offset], next[index]]; onChange(next, reasons); }
  return <section className={styles.workEditor} aria-label={title}>
    <header><h2>{title}<small>{selected.length} 部</small></h2><button type="button" disabled={!profileId || selected.length >= limit} onClick={() => setOpen(true)}><Plus size={15} />从馆藏选书</button></header>
    {!profileId ? <p>先保存学者草稿，再从真实馆藏选入作品。</p> : null}
    {chosen.error ? <p role="alert">{chosen.error}<button type="button" onClick={chosen.reload}>重新核对已选作品</button></p> : null}
    <ol className={styles.workList}>{selected.map((id, index) => { const work = rows.find(row => row.id === id); return <li key={id} data-active={selectedId === id}>
      <span className={styles.ordinal}>{index + 1}</span><button className={styles.workChoice} type="button" onClick={() => setActive(id)} aria-pressed={selectedId === id}>
        {work?.cover_url ? <img src={normalizePublicResourceUrl(work.cover_url)} alt="" loading="lazy" /> : <span className={styles.noCover}><BookOpen size={20} /></span>}
        <span><strong>{work?.title || (chosen.loading ? "正在核对作品…" : "原选择当前不可公开")}</strong><small>{work ? [work.publication_year, work.role_labels.join("、"), work.version_label].filter(Boolean).join(" · ") || "正式馆藏版本" : "保留原作品编号，核对后可移除"}</small></span>
      </button><span className={styles.orderTools}><button type="button" disabled={index === 0} aria-label={`上移第 ${index + 1} 部作品`} onClick={() => move(index, -1)}><ArrowUp size={13} /></button><button type="button" disabled={index === selected.length - 1} aria-label={`下移第 ${index + 1} 部作品`} onClick={() => move(index, 1)}><ArrowDown size={13} /></button><button type="button" aria-label={`移除第 ${index + 1} 部作品`} onClick={() => onChange(selected.filter(value => value !== id), reasons)}><X size={13} /></button></span>
    </li>; })}</ol>
    {!selected.length ? <p className={styles.empty}>尚未选入作品。{kind === "essential" ? "代表作品需有正式馆藏版本中的明确人物贡献。" : "推荐阅读注明本页编者的选择，不改变作者或贡献身份。"}</p> : null}
    {selectedId ? <section className={styles.selectedWork}><h3>选中作品 · 本页推荐理由</h3>{current ? <><strong>{current.title}</strong><p>{current.contributions.map(row => `${row.name}（${row.role_label}）`).join("、")}</p><Link href={current.href} target="_blank" rel="noopener">查看馆藏条目 ↗</Link></> : <p>当前无法核对这部作品的正式版本，理由保留，不自动替换作品。</p>}<label><span>推荐理由</span><textarea rows={4} maxLength={2000} value={reasons[selectedId] || ""} onChange={event => onChange(selected, { ...reasons, [selectedId]: event.target.value })} /></label><small>{(reasons[selectedId] || "").length} / 2000</small></section> : null}
    <Dialog className={styles.picker} open={open} onRequestClose={() => setOpen(false)} aria-labelledby={`scholar-work-picker-${kind}`}><header><h2 id={`scholar-work-picker-${kind}`}>从馆藏选择{title}</h2><button type="button" onClick={() => setOpen(false)} aria-label="关闭选书"><X size={20} /></button></header>
      <div className={styles.search}><label><span>检索正式馆藏题名</span><input value={query} maxLength={200} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); setSearch(query.trim()); setPage(1); } }} /></label><button type="button" onClick={() => { setSearch(query.trim()); setPage(1); }}>查找</button></div>
      {candidates.error ? <p role="alert">{candidates.error}<button type="button" onClick={candidates.reload}>重新读取</button></p> : candidates.loading ? <p role="status">正在读取馆藏…</p> : <><p>共 {candidates.data?.count || 0} 部 · 已选 {selected.length} / {limit}</p><ul className={styles.candidates}>{candidates.data?.results.map(work => <li key={work.id}>{work.cover_url ? <img src={normalizePublicResourceUrl(work.cover_url)} alt="" loading="lazy" /> : <BookOpen size={24} />}<div><strong>{work.title}</strong><small>{work.publication_year || "年代未详"} · {work.role_labels.join("、") || "编者推荐材料"}</small></div><button type="button" disabled={selected.includes(work.id) || selected.length >= limit} onClick={() => { onChange([...selected, work.id], reasons); setActive(work.id); }}>{selected.includes(work.id) ? "已选入" : "选入"}</button></li>)}</ul>{!candidates.data?.count ? <p className={styles.empty}>没有符合条件的真实馆藏。</p> : null}<nav className={styles.pagination} aria-label="选书分页"><button type="button" disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!candidates.data || page * candidates.data.page_size >= candidates.data.count} onClick={() => setPage(value => value + 1)}>下一页</button></nav></>}
    </Dialog>
  </section>;
}
