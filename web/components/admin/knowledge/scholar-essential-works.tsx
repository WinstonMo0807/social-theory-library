"use client";

import { GripVertical } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import type { ApiWork } from "@/lib/api/public-catalog";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import styles from "./scholar-essential-works.module.css";

type Option = { id: string; title?: string; name?: string };

export function selectScholarWork(ids: string[], index: number, id: string) {
  if (index < 0 || index >= Math.max(3, ids.length) || id && ids.includes(id) && ids[index] !== id) return ids;
  const next = [...ids];
  if (id) { if (index < next.length) next[index] = id; else if (next.length < 3) next.push(id); }
  else next.splice(index, 1);
  return next;
}

export function loadScholarWorkOptions(query: string, page: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ q: query.trim(), page: String(page) });
  // Default work rows carry Work IDs; edition view IDs cannot be saved here.
  return apiRequest<CollectionPage<WorkLibraryRow>>(`/catalog/admin/library/works/?${params}`, { signal }, getServerSessionCredential());
}

export function ScholarWorkPicker({ index, current, selected, suggestions, onSelect, onClose }: {
  index: number; current: string; selected: string[]; suggestions: Option[];
  onSelect: (option: Option) => void; onClose: () => void;
}) {
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState({ query: "", page: 1 });
  const [result, setResult] = useState<{ key: string; data: CollectionPage<WorkLibraryRow> } | null>(null);
  const [error, setError] = useState<{ key: string; message: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const key = JSON.stringify(search);
  const data = result?.key === key ? result.data : null;
  const message = error?.key === key ? error.message : "";
  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void loadScholarWorkOptions(search.query, search.page, controller.signal).then(data => {
        if (controller.signal.aborted) return;
        setResult({ key, data }); setError(null);
      }).catch(reason => {
        if (!controller.signal.aborted) setError({ key, message: reason instanceof Error ? reason.message : "馆藏搜索失败，请重试。" });
      });
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [key, search.query, search.page, retry]);
  const available = (option: Option) => option.id === current || !selected.includes(option.id);
  const suggested = suggestions.filter(available);
  const rows = (data?.results ?? []).filter(available);
  return <div className="workflow-entity-picker" role="group" aria-label={`选择第 ${index + 1} 本重要文献`} onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); onClose(); } }}>
    <label htmlFor={inputId}>搜索馆藏</label><input ref={input} id={inputId} type="search" value={search.query} placeholder="书名、作者或 ISBN" onKeyDown={event => { if (event.key === "Enter") event.preventDefault(); }} onChange={event => setSearch({ query: event.target.value, page: 1 })}/>
    <select aria-label={`第 ${index + 1} 本重要文献搜索结果`} value="" onChange={event => {
      const option = [...suggested, ...rows].find(row => row.id === event.target.value);
      if (option) onSelect(option);
    }}><option value="">选择馆藏文献</option>{suggested.length ? <optgroup label="建议馆藏">{suggested.map(row => <option key={row.id} value={row.id}>{row.title || row.name}</option>)}</optgroup> : null}
      {rows.length ? <optgroup label="馆藏搜索结果">{rows.map(row => <option key={row.id} value={row.id}>{[row.title, row.contributors?.join("、"), row.publisher, row.publication_year].filter(Boolean).join(" · ")}</option>)}</optgroup> : null}
    </select>
    <p role="status">{data ? `第 ${data.page} / ${Math.max(1, data.total_pages)} 页，共 ${data.count} 项馆藏` : message ? "" : "正在搜索馆藏……"}</p>
    {message ? <p role="alert">{message}<button type="button" onClick={() => { setError(null); setRetry(value => value + 1); }}>重试</button></p> : null}
    <div className={styles.selection}><button type="button" disabled={!data?.previous} onClick={() => setSearch({ ...search, page: search.page - 1 })}>上一页</button><button type="button" disabled={!data?.next} onClick={() => setSearch({ ...search, page: search.page + 1 })}>下一页</button><button type="button" onClick={onClose}>取消</button></div>
  </div>;
}

export function moveScholarWork(ids: string[], id: string, target: number) {
  const from = ids.indexOf(id);
  if (from < 0 || target < 0 || target >= ids.length || from === target) return ids;
  const next = [...ids];
  next.splice(from, 1);
  next.splice(target, 0, id);
  return next;
}

export function ScholarEssentialWorks({ selected, options, works, onChange, onResolve }: {
  selected: string[]; options: Option[]; works: ApiWork[];
  onChange: (ids: string[]) => void; onResolve: (works: ApiWork[]) => void;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [knownOptions, setKnownOptions] = useState<Option[]>([]);
  const dragging = useRef("");
  const cache = useRef(new Map<string, ApiWork | null>());
  const membership = [...selected].sort().join(",");
  useEffect(() => {
    const ids = membership ? membership.split(",") : [];
    const controller = new AbortController();
    const resolvedOptions: Option[] = [];
    void Promise.allSettled(ids.map(async id => {
      if (cache.current.has(id)) return cache.current.get(id)!;
      const credential = getServerSessionCredential();
      const library = await apiRequest<CollectionPage<WorkLibraryRow>>(`/catalog/admin/library/works/?work_id=${encodeURIComponent(id)}`, { signal: controller.signal }, credential);
      const row = library.results.find(item => item.id === id);
      if (!row) throw new Error("当前文献不可用。");
      resolvedOptions.push({ id, title: row.title });
      const editionId = row?.primary_edition?.id || row?.edition_id;
      if (!editionId) { cache.current.set(id, null); return null; }
      const payload = await apiRequest<{ work: ApiWork }>(`/catalog/admin/page-preview/editions/${encodeURIComponent(editionId)}/`, { signal: controller.signal }, credential);
      if (payload.work.id !== id) throw new Error("重要文献读取结果不完整。");
      cache.current.set(id, payload.work);
      return payload.work;
    })).then(results => {
      if (controller.signal.aborted) return;
      setKnownOptions(previous => [...new Map([...previous, ...resolvedOptions].map(option => [option.id, option])).values()]);
      onResolve(results.flatMap(result => result.status === "fulfilled" && result.value ? [result.value] : []));
      setError(results.some(result => result.status === "rejected") ? "部分书目读取失败，原有选择与顺序仍保留。" : "");
    });
    return () => controller.abort();
  }, [membership, onResolve, retry]);

  const slots = Array.from({ length: Math.max(3, selected.length) }, (_, index) => selected[index] || "");
  function choose(index: number, id: string, option?: Option) {
    const next = selectScholarWork(selected, index, id);
    if (next === selected) return;
    if (option) setKnownOptions(previous => [...previous.filter(row => row.id !== option.id), option]);
    onChange(next); setEditing(null);
  }
  return <section className={styles.editor} data-editor-section="works">
    <h3>重要文献</h3>
    <p>选择并排序该学者最重要的 3 本著作，按此顺序在学者页面展示。</p>
    {error ? <p role="alert">{error}<button type="button" onClick={() => setRetry(value => value + 1)}>重试</button></p> : null}
    <div className={styles.cards}>{slots.map((id, index) => {
      const work = works.find(row => row.id === id);
      const option = knownOptions.find(row => row.id === id) || options.find(row => row.id === id);
      const title = work?.title || option?.title || option?.name || "";
      const cover = work?.cover || work?.recommendation_image;
      const authors = work?.edition?.contributors.filter(row => row.role === "author").map(row => row.person.preferred_name).join("、") || "";
      const publication = [work?.edition?.publisher, work?.edition?.publication_year ? `${work.edition.publication_year} 年版` : ""].filter(Boolean).join(" · ");
      return <article className={styles.card} key={id || `empty-${index}`} data-work-id={id} onDragOver={event => { if (dragging.current) event.preventDefault(); }} onDrop={event => {
        event.preventDefault();
        if (!id || event.currentTarget.closest("fieldset")?.matches(":disabled")) return;
        onChange(moveScholarWork(selected, dragging.current, index)); dragging.current = "";
      }}>
        <span className={styles.number}>{index + 1}</span>
        <div className={styles.content}>
          <div className={styles.book}>
            <span className={styles.cover}>{cover ? <img src={normalizePublicResourceUrl(cover)} alt={title ? `${title}封面` : "文献封面"}/> : null}</span>
            <div className={styles.metadata}><button type="button" className={styles.title} aria-label={`选择第 ${index + 1} 本重要文献`} onClick={() => setEditing(editing === index ? null : index)}>{title || (id ? "正在读取书目…" : "选择馆藏文献")}</button>{work?.original_title ? <small>{work.original_title}</small> : null}<p>{authors ? `${authors} 著` : ""}</p><p>{publication}</p></div>
            {id ? <button type="button" className={styles.handle} draggable title="拖动调整顺序，或按上、下方向键移动" aria-label={`调整${title || `第 ${index + 1} 本文献`}顺序，当前位置 ${index + 1}`} onDragStart={event => {
              if (event.currentTarget.matches(":disabled")) { event.preventDefault(); return; }
              dragging.current = id; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", id);
            }} onDragEnd={() => { dragging.current = ""; }} onKeyDown={event => { if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return; event.preventDefault(); onChange(moveScholarWork(selected, id, index + (event.key === "ArrowUp" ? -1 : 1))); }}><GripVertical size={18}/></button> : null}
          </div>
          {editing === index ? <><ScholarWorkPicker key={index} index={index} current={id} selected={selected} suggestions={options} onSelect={option => choose(index, option.id, option)} onClose={() => setEditing(null)}/>{id ? <button type="button" onClick={() => choose(index, "")}>移除选择</button> : null}</> : null}
          <label className={styles.reason}><span>推荐说明</span><textarea aria-label={`第 ${index + 1} 本文献的推荐说明`} disabled value="" readOnly rows={3} title="此项尚无可保存并公开的对应字段"/></label>
        </div>
      </article>;
    })}</div>
  </section>;
}
