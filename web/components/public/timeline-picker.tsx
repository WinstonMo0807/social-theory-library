"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { isImeComposing } from "@/lib/search-submit-key";
import type { Paginated } from "@/lib/api/pagination";
import type { ApiTopic } from "@/lib/api/topics.types";
import type { ApiScholar } from "@/lib/api/people.types";
import type { TimelineTopic } from "@/lib/api/timeline.types";
import styles from "./theory-timeline.module.css";

type Choice = Pick<TimelineTopic, "id" | "name" | "slug">;
export function TimelinePicker({ kind, values, selected }: {
  kind: "topic" | "author"; values: string[]; selected: Choice[];
}) {
  const label = kind === "topic" ? "主题" : "作者";
  const [chosen, setChosen] = useState(values);
  const [known, setKnown] = useState(selected);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<{ items: Choice[]; count: number; next: boolean; page: number; query: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; request.current?.abort(); }, []);
  async function load(page: number, search = query) {
    request.current?.abort();
    const controller = new AbortController(), version = ++generation.current;
    request.current = controller;
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ q: search, page: String(page) });
      const response = await apiRequest<Paginated<ApiTopic | ApiScholar>>(
        `/catalog/${kind === "topic" ? "topics" : "scholars"}/?${params}`,
        { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]) }, null, false,
      );
      if (version !== generation.current || controller.signal.aborted) return;
      const items = response.results.flatMap(row => {
        if (!row.id || !row.slug) return [];
        return [{ id: row.id, slug: row.slug, name: "person" in row ? row.person.preferred_name : row.name }];
      });
      setResult({ items, count: response.count, next: Boolean(response.next), page, query: search });
      setKnown(previous => [...new Map([...previous, ...items].map(row => [row.id, row])).values()]);
    } catch {
      if (version === generation.current && !controller.signal.aborted) setError(`${label}候选暂时无法读取，请重试。`);
    } finally {
      if (version === generation.current) setLoading(false);
    }
  }
  const selectedNames = chosen.map(value => known.find(row => row.slug === value || row.id === value)?.name);
  return <div className={styles.picker}>
    {chosen.map(value => <input type="hidden" name={kind} value={value} key={value} />)}
    <span className={styles.filterLabel}>{label}</span>
    <details data-disclosure="collection" onToggle={event => { if (event.currentTarget.open && !result && !loading && !error) void load(1); }}>
      <summary aria-label={`选择${label}`}><span>{chosen.length ? `${selectedNames.filter(Boolean).slice(0, 2).join("、") || `所选${label}当前不可用`}${chosen.length > 2 ? ` 等 ${chosen.length} 项` : ""}${selectedNames.some(value => !value) && selectedNames.some(Boolean) ? " · 含不可用项" : ""}` : `全部${label}`}</span><ChevronDown size={13} aria-hidden="true" /></summary>
      <div className={styles.pickerPanel}>
        <div className={styles.pickerSearch}><input aria-label={`搜索${label}`} value={query} placeholder={`搜索${label}名称`} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !isImeComposing(event)) { event.preventDefault(); void load(1); } }} /><button type="button" aria-label={`搜索${label}候选`} onClick={() => void load(1)}><Search size={15} aria-hidden="true" /></button></div>
        {chosen.length ? <div className={styles.chosen}>{chosen.map((value, index) => <button type="button" key={value} onClick={() => setChosen(previous => previous.filter(item => item !== value))} aria-label={`移除${label} ${selectedNames[index] || "当前不可用的选择"}`}>{selectedNames[index] || `所选${label}当前不可用`} ×</button>)}</div> : null}
        {loading ? <p role="status">正在读取{label}…</p> : error ? <p role="alert">{error}<button type="button" onClick={() => void load(result?.page || 1)}>重试{label}候选</button></p> : result ? <>
          <div className={styles.pickerChoices}>{result.items.map(row => <label key={row.id}><input type="checkbox" checked={chosen.includes(row.id) || chosen.includes(row.slug)} disabled={chosen.length >= 30 && !chosen.includes(row.id) && !chosen.includes(row.slug)} onChange={event => setChosen(previous => event.target.checked ? [...new Set([...previous, row.slug])] : previous.filter(value => value !== row.id && value !== row.slug))} /><span>{row.name}</span></label>)}</div>
          <p role="status">{result.count ? `共 ${result.count} 个公开${label} · 第 ${result.page} 页` : `没有找到公开${label}。`}</p>
          <div className={styles.pickerPages}><button type="button" disabled={result.page <= 1} onClick={() => void load(result.page - 1, result.query)}>上一页{label}</button><button type="button" disabled={!result.next} onClick={() => void load(result.page + 1, result.query)}>下一页{label}</button></div>
        </> : null}
      </div>
    </details>
  </div>;
}
