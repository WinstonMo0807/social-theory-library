"use client";

import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { authorityRequest, type AuthorityDirectory, type AuthorityDetail } from "@/lib/api/person-authority.client";
import type { PlacementSource, PlacementTarget } from "@/lib/api/curation-workspace.client";
import styles from "./concept-editor.module.css";

export type PlacementChoice = { target: PlacementTarget; source: PlacementSource };
type SourcePage = { count: number; next: string | null; previous: string | null; results: PlacementChoice[] };
export function PlacementSourcePicker({ owner, kind, onChoose }: { owner: string; kind: "span" | "edition" | "node" | "scholar" | "issue"; onChoose: (choice: PlacementChoice) => void }) {
  const [query, setQuery] = useState(""), [search, setSearch] = useState(""), [page, setPage] = useState(1);
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<SourcePage>(path, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential()), [owner]);
  const resource = usePersistentWorkspace<SourcePage>(`/catalog/admin/content-placements/sources/?${new URLSearchParams({type:kind,q:search,page:String(page)})}`, owner, undefined, load);
  return <section><div className={styles.search}><label><span>{{span:"检索已定位的原文",edition:"检索馆藏版本",node:"检索理论与概念",scholar:"检索公开学者",issue:"检索公开策划"}[kind]}</span><input maxLength={200} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) { event.preventDefault(); setSearch(query.trim()); setPage(1); } }} /></label><button type="button" onClick={() => {setSearch(query.trim());setPage(1);resource.reload();}}>查找</button></div>
    {resource.error ? <p role="alert">{resource.error}<button type="button" onClick={resource.reload}>重新读取</button></p> : !resource.data ? <p role="status">正在读取真实材料…</p> : <><p>共 {resource.data.count} 项 · 第 {page} 页</p><ul className={styles.sourceList}>{resource.data.results.map(row => <li key={`${row.target.id}:${row.target.edition_id || ""}`}>
      {typeof row.source.image_url === "string" && row.source.image_url ? <img src={normalizePublicResourceUrl(row.source.image_url)} alt="" loading="lazy" /> : null}<div><strong>{row.source.title}</strong><p>{String(row.source.edition_label || "")}{row.source.page_start ? ` · PDF ${row.source.page_start}` : ""}</p>{row.source.text ? <blockquote>{row.source.text}</blockquote> : null}<small>{row.source.public_eligible ? "当前可公开，发布时仍会复核" : "尚不能公开，可先保留草稿"}</small></div><button type="button" onClick={() => onChoose(row)}>选取</button>
    </li>)}</ul>{!resource.data.results.length ? <p>没有符合条件的材料。请调整关键词或先完成原文定位。</p> : null}<nav className={styles.pagination} aria-label="材料分页"><button type="button" disabled={!resource.data.previous} onClick={() => setPage(value => value - 1)}>上一页</button><button type="button" disabled={!resource.data.next} onClick={() => setPage(value => value + 1)}>下一页</button></nav></>}
  </section>;
}

export function UsagePersonPicker({ owner, value, onChange }: { owner: string; value: string; onChange: (id: string) => void }) {
  const [query, setQuery] = useState(""), [search, setSearch] = useState(""), [open, setOpen] = useState(false), [page, setPage] = useState(1);
  const load = useCallback((path: string, signal: AbortSignal) => authorityRequest<AuthorityDirectory>(owner, path, { signal }), [owner]);
  const loadPerson = useCallback((path: string, signal: AbortSignal) => authorityRequest<AuthorityDetail>(owner, path, { signal }), [owner]);
  const selected = usePersistentWorkspace<AuthorityDetail>(value ? `${value}/workspace/` : "", owner, undefined, loadPerson);
  const choices = usePersistentWorkspace<AuthorityDirectory>(open ? `workspace/?${new URLSearchParams({q:search,status:"verified",page:String(page)})}` : "", owner, undefined, load);
  return <section className={styles.personPicker}><strong>此用法归属的人物</strong><p>{value ? selected.error ? "原人物当前不能核对" : selected.data?.values.preferred_name || "正在读取原人物…" : "尚未指定人物"}</p><button type="button" onClick={() => setOpen(value => !value)}>{open ? "收起人物选择" : "选择已核实人物"}</button>{value ? <button type="button" onClick={() => onChange("")}>清除此选择</button> : null}
    {open ? <><div className={styles.search}><input aria-label="检索人物" maxLength={200} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => {if(event.key === "Enter" && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229){event.preventDefault();setSearch(query.trim());setPage(1);}}} /><button type="button" onClick={() => {setSearch(query.trim());setPage(1);choices.reload();}}>查找</button></div>{choices.error ? <p role="alert">{choices.error}</p> : !choices.data ? <p role="status">正在读取人物…</p> : <><ul>{choices.data.results.map(row => <li key={row.id}><span>{row.preferred_name} · {row.original_name}</span><button type="button" onClick={() => {onChange(row.id);setOpen(false);}}>选定</button></li>)}</ul>{!choices.data.results.length ? <p>没有符合条件的已核实人物。</p> : null}<nav className={styles.pagination}><button type="button" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><button type="button" disabled={page >= choices.data.total_pages} onClick={() => setPage(value => value + 1)}>下一页</button></nav></>}</> : null}
  </section>;
}
