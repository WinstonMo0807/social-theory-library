"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { graphKindLabels, type GraphKind } from "@/lib/api/graph.types";
import styles from "./theory-graph.module.css";

type Result = { id: string; slug: string; name?: string; canonical_name_zh?: string; person?: { preferred_name: string } };
const endpoints: Record<GraphKind, string> = { knowledge_node: "theory-system/nodes", scholar: "scholars", topic: "topics", subdiscipline: "subdisciplines" };
export function GraphCenterSearch({ disabled, onSelect }: { disabled?: boolean; onSelect: (kind: GraphKind, id: string) => void }) {
  const [kind, setKind] = useState<GraphKind>("knowledge_node"), [query, setQuery] = useState("");
  const [result, setResult] = useState<{ results: Result[]; count: number; next: string | null; previous: string | null; kind: GraphKind; query: string; page: number } | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function search(page = 1, targetKind = kind, text = query) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setError("");
    try {
      const data = await apiRequest<{ results: Result[]; count: number; next: string | null; previous: string | null }>(`/catalog/${endpoints[targetKind]}/?${new URLSearchParams({ q: text, page: String(page) })}`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]) }, null, false);
      if (!controller.signal.aborted) setResult({ ...data, kind: targetKind, query: text, page });
    } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "公开条目暂时无法读取，请重试。"); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <details data-disclosure="collection" className={styles.centerSearch}><summary>选择或搜索中心节点<Search size={14} /></summary>
    <form onSubmit={event => { event.preventDefault(); void search(); }}>
      <label>条目类型<select data-stl-select value={kind} onChange={event => setKind(event.target.value as GraphKind)}>{Object.entries(graphKindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div><input aria-label="搜索公开图谱节点" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索节点、学者、概念…" /><button type="submit" disabled={busy} aria-label="搜索图谱中心"><Search size={16} /></button></div>
    </form>
    {busy ? <p role="status">正在读取公开条目…</p> : error ? <p role="alert">{error}<button type="button" onClick={() => void search()}>重试搜索</button></p> : result ? <>
      <p>{graphKindLabels[result.kind]} · 共 {result.count} 条</p>
      {result.results.length ? <ul>{result.results.map(row => <li key={row.id}><button type="button" disabled={disabled} onClick={() => onSelect(result.kind, row.id)}>{row.canonical_name_zh || row.person?.preferred_name || row.name || "名称未详"}</button></li>)}</ul> : <p>没有符合条件的公开条目。</p>}
      <div className={styles.pagination}><button type="button" disabled={!result.previous} onClick={() => void search(result.page - 1, result.kind, result.query)}>上一页</button><span>{result.page}</span><button type="button" disabled={!result.next} onClick={() => void search(result.page + 1, result.kind, result.query)}>下一页</button></div>
    </> : null}
  </details>;
}

export function GraphDisciplineFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<{ results: { id: string; slug: string; name: string }[]; count: number; next: string | null; previous: string | null; page: number; query: string } | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function load(page = 1, text = query) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller; setBusy(true); setError("");
    try {
      const data = await apiRequest<{ results: { id: string; slug: string; name: string }[]; count: number; next: string | null; previous: string | null }>(`/catalog/disciplines/?${new URLSearchParams({ q: text, page: String(page) })}`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]) }, null, false);
      if (!controller.signal.aborted) setResult({ ...data, page, query: text });
    } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "学科范围暂时无法读取。"); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <details data-disclosure="collection" className={styles.disciplinePicker} onToggle={event => { if (event.currentTarget.open && !result && !busy && !error) void load(); }}><summary>学科范围{value ? " · 已限定" : " · 全部学科"}<ChevronDown size={13} /></summary>
    <div className={styles.disciplineSearch}><input aria-label="搜索公开学科" value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); void load(); } }} /><button type="button" aria-label="查找学科" disabled={busy} onClick={() => void load()}><Search size={14} /></button></div>
    <label><input type="radio" name="graph-discipline" checked={!value} onChange={() => onChange("")} />全部学科</label>
    {busy ? <p role="status">正在读取学科…</p> : error ? <p role="alert">{error}<button type="button" onClick={() => void load()}>重试读取学科</button></p> : result ? <><div className={styles.disciplineChoices}>{result.results.map(row => <label key={row.id}><input type="radio" name="graph-discipline" checked={value === row.id || value === row.slug} onChange={() => onChange(row.slug)} />{row.name}</label>)}</div><p>共 {result.count} 个公开学科</p><div className={styles.pagination}><button type="button" disabled={!result.previous} onClick={() => void load(result.page - 1, result.query)}>上一页学科</button><span>{result.page}</span><button type="button" disabled={!result.next} onClick={() => void load(result.page + 1, result.query)}>下一页学科</button></div></> : null}
  </details>;
}
