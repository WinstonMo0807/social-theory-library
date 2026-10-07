"use client";

import { GripVertical } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import type { ApiWork } from "@/lib/api/public-catalog";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import styles from "./scholar-essential-works.module.css";

type Option = { id: string; title?: string; name?: string };

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
  const dragging = useRef("");
  const cache = useRef(new Map<string, ApiWork>());
  const membership = [...selected].sort().join(",");
  useEffect(() => {
    const ids = membership ? membership.split(",") : [];
    const controller = new AbortController();
    void Promise.allSettled(ids.map(async id => {
      if (cache.current.has(id)) return cache.current.get(id)!;
      const credential = getServerSessionCredential();
      const library = await apiRequest<CollectionPage<WorkLibraryRow>>(`/catalog/admin/library/works/?work_id=${encodeURIComponent(id)}`, { signal: controller.signal }, credential);
      const row = library.results.find(item => item.id === id);
      const editionId = row?.primary_edition?.id || row?.edition_id;
      if (!editionId) throw new Error("当前文献没有可预览的出版版本。");
      const payload = await apiRequest<{ work: ApiWork }>(`/catalog/admin/page-preview/editions/${encodeURIComponent(editionId)}/`, { signal: controller.signal }, credential);
      if (payload.work.id !== id) throw new Error("重要文献读取结果不完整。");
      cache.current.set(id, payload.work);
      return payload.work;
    })).then(results => {
      if (controller.signal.aborted) return;
      onResolve(results.flatMap(result => result.status === "fulfilled" ? [result.value] : []));
      setError(results.some(result => result.status === "rejected") ? "部分书目读取失败，原有选择与顺序仍保留。" : "");
    });
    return () => controller.abort();
  }, [membership, onResolve, retry]);

  const slots = Array.from({ length: Math.max(3, selected.length) }, (_, index) => selected[index] || "");
  function choose(index: number, id: string) {
    if (id && selected.includes(id) && selected[index] !== id) return;
    const next = [...selected];
    if (id) { if (index < next.length) next[index] = id; else if (next.length < 3) next.push(id); }
    else next.splice(index, 1);
    onChange(next); setEditing(null);
  }
  return <section className={styles.editor} data-editor-section="works">
    <h3>重要文献</h3>
    <p>选择并排序该学者最重要的 3 本著作，按此顺序在学者页面展示。</p>
    {error ? <p role="alert">{error}<button type="button" onClick={() => setRetry(value => value + 1)}>重试</button></p> : null}
    <div className={styles.cards}>{slots.map((id, index) => {
      const work = works.find(row => row.id === id);
      const option = options.find(row => row.id === id);
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
          {editing === index || !id ? <div className={styles.selection}><select aria-label={`第 ${index + 1} 本重要文献`} value={id} onChange={event => choose(index, event.target.value)}><option value="">选择馆藏文献</option>{id && !options.some(row => row.id === id) ? <option value={id}>{title || "已保存文献"}</option> : null}{options.filter(row => row.id === id || !selected.includes(row.id)).map(row => <option key={row.id} value={row.id}>{row.title || row.name || "未命名馆藏"}</option>)}</select>{id ? <button type="button" onClick={() => choose(index, "")}>移除选择</button> : null}</div> : null}
          <label className={styles.reason}><span>推荐说明</span><textarea aria-label={`第 ${index + 1} 本文献的推荐说明`} disabled value="" readOnly rows={3} title="此项尚无可保存并公开的对应字段"/></label>
        </div>
      </article>;
    })}</div>
  </section>;
}
