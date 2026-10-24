"use client";

import { useCallback, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { Dialog } from "@/components/ui/dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { components } from "@/lib/api/generated/schema";
import styles from "./topic-editor.module.css";

type Choice = components["schemas"]["TopicAssociationRow"];
type ChoicePage = components["schemas"]["TopicAssociationPage"];
const pageSize = 24;
const endpoint = "/catalog/admin/topics/association-choices/";

function useChoices(field: string, params: URLSearchParams, active = true) {
  const owner = String(useAdminSession()?.id || "");
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<ChoicePage>(path,
    { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), [owner]);
  return usePersistentWorkspace<ChoicePage>(active ? `${endpoint}?field=${field}&${params}` : "", owner, undefined, load);
}

function Cover({ row }: { row?: Choice }) {
  const [failed, setFailed] = useState("");
  return row?.cover_url && row.cover_url !== failed
    ? <img src={row.cover_url} alt="" loading="lazy" onError={() => setFailed(row.cover_url)} />
    : <span className={styles.associationCover} aria-label="暂无可用图片">STL</span>;
}

function PageButtons({ page, total, onChange }: { page: number; total: number; onChange: (page: number) => void }) {
  return total > 1 ? <nav className={styles.pages} aria-label="关联内容分页">
    <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button>
    <span>{page} / {total}</span><button type="button" disabled={page >= total} onClick={() => onChange(page + 1)}>下一页</button>
  </nav> : null;
}

function SelectionRows({ field, ids, labels, notes, sorting = false, onOrder, onNote, onRemove }: {
  field: string; ids: string[]; labels: Record<string, string>; notes: Record<string, string>;
  sorting?: boolean; onOrder: (ids: string[]) => void;
  onNote?: (id: string, text: string) => void; onRemove?: (id: string) => void;
}) {
  const [requestedPage, setPage] = useState(1), [announcement, announce] = useState("");
  const dragging = useRef<string | null>(null);
  const total = Math.max(1, Math.ceil(ids.length / pageSize)), page = Math.min(requestedPage, total);
  const visible = ids.slice((page - 1) * pageSize, page * pageSize);
  const resource = useChoices(field, new URLSearchParams({ ids: [...visible].sort().join(",") }), visible.length > 0);
  const details = new Map(resource.data?.results.map(row => [row.id, row]) || []);
  function move(id: string, target: number) {
    const from = ids.indexOf(id);
    if (from < 0 || target < 0 || target >= ids.length || from === target) return;
    const next = ids.filter(value => value !== id); next.splice(target, 0, id); onOrder(next);
    announce(`已将第 ${from + 1} 项移到第 ${target + 1} 项，当前调整尚未保存。`);
    setPage(Math.floor(target / pageSize) + 1);
  }
  return <>
    {resource.error ? <p role="alert">关联资料读取失败，已选编号和输入仍保留。<button type="button" onClick={resource.reload}>重新读取</button></p> : null}
    <span className={styles.liveNotice} role="status">{announcement}</span>
    <ol className={styles.associationRows} start={(page - 1) * pageSize + 1}>{visible.map((id, localIndex) => {
      const index = (page - 1) * pageSize + localIndex, row = details.get(id), name = row?.name || labels[id] || `原条目 ${id.slice(0, 8)}`;
      return <li key={id} onDragOver={event => { if (sorting && dragging.current) event.preventDefault(); }} onDrop={event => {
        if (!sorting || !dragging.current) return; event.preventDefault(); move(dragging.current, index); dragging.current = null;
      }}>
        <span className={styles.associationNumber}>{index + 1}</span><Cover row={row} />
        <div className={styles.associationCopy}><strong>{name}</strong>{row?.subtitle ? <small>{row.subtitle}</small> : null}
          {resource.data && !row ? <small>当前无法读取此关联，请核对后决定是否保留。</small> : null}
          {!sorting ? <details><summary>{notes[id] ? "编辑关联说明" : "补充关联说明"}</summary>
            <label><span>关联说明 · 发布后读者可见</span><textarea rows={3} maxLength={600} value={notes[id] || ""}
              onChange={event => onNote?.(id, event.target.value)} aria-label={`${name}的关联说明`} /></label><small>{(notes[id] || "").length} / 600</small>
          </details> : null}
        </div>
        <div className={styles.associationActions}>
          {sorting ? <button type="button" draggable onDragStart={event => {
            dragging.current = id; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", id);
          }} onDragEnd={() => { dragging.current = null; }} aria-label={`拖动${name}排序；也可使用上下移和位置选择`} title="拖动排序">⠿</button> : null}
          {sorting ? <><button type="button" disabled={index === 0} aria-label={`上移${name}`} onClick={() => move(id, index - 1)}>上移</button>
          <button type="button" disabled={index === ids.length - 1} aria-label={`下移${name}`} onClick={() => move(id, index + 1)}>下移</button></> : null}
          {sorting ? <select aria-label={`${name}的位置`} value={index} onChange={event => move(id, Number(event.target.value))}>
            {ids.map((_, position) => <option key={position} value={position}>第 {position + 1} 项</option>)}
          </select> : <button type="button" onClick={() => {
            if (!notes[id] || window.confirm(`移除“${name}”的关联及本主题中的说明？原条目不会删除。`)) onRemove?.(id);
          }}>移除</button>}
        </div>
      </li>;
    })}</ol>
    <PageButtons page={page} total={total} onChange={setPage} />
  </>;
}

export function TopicAssociations({ field, label, ids, labels, notes, onChange, onNote }: {
  field: string; label: string; ids: string[]; labels: Record<string, string>; notes: Record<string, string>;
  onChange: (ids: string[], labels?: Record<string, string>) => void; onNote: (id: string, text: string) => void;
}) {
  const [picker, setPicker] = useState(false), [search, setSearch] = useState(""), [query, setQuery] = useState(""), [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ base: string; ids: string[] } | null>(null);
  const options = useChoices(field, new URLSearchParams({ q: query, page: String(page) }), picker);
  const changed = Boolean(sort && sort.base !== JSON.stringify(ids)), maximum = field === "issue_ids" ? 50 : 200;
  useUnsavedForm(Boolean(sort && sort.base !== JSON.stringify(sort.ids)), false);
  function closeSort() { if (!sort || JSON.stringify(sort.ids) === sort.base || window.confirm("放弃此次尚未应用的排序？")) setSort(null); }
  return <section className={styles.associations}>
    <header><h3>{label} <small>{ids.length}</small></h3><div>
      <button type="button" onClick={() => setPicker(true)}>＋ 关联已有内容</button>
      <button type="button" disabled={ids.length < 2} onClick={() => setSort({ base: JSON.stringify(ids), ids: [...ids] })}>批量排序</button>
    </div></header>
    {!ids.length ? <p className={styles.muted}>尚未关联内容。从已有条目选择后，可补充说明并调整顺序。</p> : <SelectionRows field={field} ids={ids} labels={labels} notes={notes}
      onOrder={onChange} onNote={onNote} onRemove={id => onChange(ids.filter(value => value !== id))} />}
    <Dialog open={picker} data-editor-transient className={styles.associationDialog} onRequestClose={() => setPicker(false)} aria-label={`选择${label}`}>
      <header><h2>选择{label}</h2><button type="button" onClick={() => setPicker(false)}>完成</button></header>
      <div className={styles.treeSearch}><input value={search} maxLength={240} aria-label={`搜索${label}`} placeholder="搜索已有条目" onChange={event => setSearch(event.target.value)}
        onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); setQuery(search.trim()); setPage(1); } }} />
        <button type="button" onClick={() => { setQuery(search.trim()); setPage(1); }}>查找</button></div>
      <p role="status">已选 {ids.length} / {maximum} 项。选择仅更新当前草稿，保存和发布仍需分别操作。</p>
      {options.error ? <p role="alert">{options.error}<button type="button" onClick={options.reload}>重新读取</button></p> : !options.data ? <p role="status">正在读取…</p> : <>
        <ul className={styles.associationRows}>{options.data.results.map(row => <li key={row.id}><Cover row={row} /><div className={styles.associationCopy}><strong>{row.name}</strong><small>{row.subtitle}</small></div>
          <button type="button" disabled={ids.includes(row.id) || ids.length >= maximum} onClick={() => onChange([...ids, row.id], { [row.id]: row.name })}>{ids.includes(row.id) ? "已选" : "选入"}</button></li>)}</ul>
        {!options.data.count ? <p>当前没有匹配的已有内容。</p> : null}<PageButtons page={options.data.page} total={options.data.total_pages} onChange={setPage} />
      </>}
    </Dialog>
    <Dialog open={Boolean(sort)} data-editor-transient className={styles.associationDialog} onRequestClose={closeSort} aria-label={`${label}批量排序`}>
      <header><h2>{label}排序</h2><button type="button" onClick={closeSort}>取消</button><button type="button" disabled={changed} onClick={() => { if (sort && !changed) { onChange(sort.ids); setSort(null); } }}>完成</button></header>
      <p>拖动、上下移动或选择位置。完成后应用到当前草稿，再保存主题。</p>
      {changed ? <p role="alert">原关联已变化，请取消并重新打开排序，避免覆盖更新。</p> : sort ? <SelectionRows field={field} ids={sort.ids} labels={labels} notes={notes} sorting onOrder={next => setSort({ ...sort, ids: next })} /> : null}
    </Dialog>
  </section>;
}
