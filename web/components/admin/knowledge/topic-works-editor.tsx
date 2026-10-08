"use client";

import { GripVertical, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { ApiWork } from "@/lib/api/public-catalog";
import { loadLibraryWorkPreview, moveScholarWork, ScholarWorkPicker } from "./scholar-essential-works";

type Option = { id: string; title?: string; name?: string };

export function TopicWorksEditor({ selected, suggestions, works, onChange, onResolve }: {
  selected: string[]; suggestions: Option[]; works: ApiWork[];
  onChange: (ids: string[]) => void; onResolve: (works: ApiWork[]) => void;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [knownOptions, setKnownOptions] = useState<Option[]>([]);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const cache = useRef(new Map<string, ApiWork | null>());
  const dragging = useRef("");
  const membership = [...new Set(selected)].sort().join(",");
  useEffect(() => {
    const controller = new AbortController();
    const ids = membership ? membership.split(",") : [];
    const options: Option[] = [];
    void Promise.allSettled(ids.map(async id => {
      if (cache.current.has(id)) return cache.current.get(id)!;
      const resolved = await loadLibraryWorkPreview(id, controller.signal);
      if (!controller.signal.aborted) { options.push(resolved.option); cache.current.set(id, resolved.work); }
      return resolved.work;
    })).then(results => {
      if (controller.signal.aborted) return;
      setKnownOptions(previous => [...new Map([...previous, ...options].map(option => [option.id, option])).values()]);
      onResolve(results.flatMap(result => result.status === "fulfilled" && result.value ? [result.value] : []));
      setError(results.some(result => result.status === "rejected") ? "部分文献读取失败，原有选择与顺序仍保留。" : "");
    });
    return () => controller.abort();
  }, [membership, onResolve, retry]);

  function choose(option: Option) {
    if (editing === null || selected.includes(option.id) && selected[editing] !== option.id) return;
    const next = [...selected];
    if (editing < next.length) next[editing] = option.id; else next.push(option.id);
    setKnownOptions(previous => [...previous.filter(row => row.id !== option.id), option]);
    onChange(next); setEditing(null);
  }
  const picker = editing === null ? null : <ScholarWorkPicker key={editing} index={editing} current={selected[editing] || ""} selected={selected} suggestions={suggestions} itemLabel="入门文献" onSelect={choose} onClose={() => setEditing(null)}/>;
  return <section className="topic-reference-works" data-editor-section="works">
    <h2>入门阅读</h2>
    <p>从馆藏中选择文献，按此顺序展示在主题首页。</p>
    {error ? <p role="alert">{error}<button type="button" onClick={() => setRetry(value => value + 1)}>重试</button></p> : null}
    <ol>{selected.map((id, index) => {
      const work = works.find(row => row.id === id);
      const option = knownOptions.find(row => row.id === id) || suggestions.find(row => row.id === id);
      const title = work?.title || option?.title || option?.name || "";
      const cover = work?.cover || work?.recommendation_image;
      const authors = work?.edition?.contributors.filter(row => row.role === "author").map(row => row.person.preferred_name).join("、") || "";
      const publication = [work?.edition?.publisher, work?.edition?.publication_year].filter(Boolean).join(" · ");
      return <li key={id} data-work-id={id} onDragOver={event => { if (dragging.current) event.preventDefault(); }} onDrop={event => {
        event.preventDefault();
        if (event.currentTarget.closest("fieldset")?.matches(":disabled")) return;
        onChange(moveScholarWork(selected, dragging.current, index)); dragging.current = "";
      }}>
        <header><strong>文献 {index + 1}</strong><button type="button" draggable aria-label={`调整第 ${index + 1} 本入门文献顺序`} title="拖动调整顺序，或按上、下方向键移动" onDragStart={event => {
          if (event.currentTarget.matches(":disabled")) { event.preventDefault(); return; }
          dragging.current = id; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", id);
        }} onDragEnd={() => { dragging.current = ""; }} onKeyDown={event => {
          if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
          event.preventDefault(); onChange(moveScholarWork(selected, id, index + (event.key === "ArrowUp" ? -1 : 1)));
        }}><GripVertical size={16}/></button><button type="button" onClick={() => { onChange(selected.filter(row => row !== id)); setEditing(null); }}>移除</button></header>
        <div className="topic-reference-work-book"><span>{cover ? <img src={normalizePublicResourceUrl(cover)} alt={title ? `${title}封面` : "文献封面"}/> : null}</span><div><button type="button" aria-label={`选择第 ${index + 1} 本入门文献`} onClick={() => setEditing(editing === index ? null : index)}>{title || "选择馆藏文献"}</button><p>{authors}</p><p>{publication}</p></div></div>
        {editing === index ? picker : null}
      </li>;
    })}</ol>
    {editing === selected.length ? picker : null}
    <button type="button" className="topic-work-add" onClick={() => setEditing(selected.length)}><Plus size={14}/>添加入门文献</button>
  </section>;
}
