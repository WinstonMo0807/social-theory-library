"use client";

import { useId, useState } from "react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { PublicReadingPath } from "@/lib/api/reading-paths.types";
import type { DependencyMaterial } from "./reading-path-dependencies";
import styles from "../knowledge/path-editor.module.css";

/** Bounded pages keep dense 600-item paths usable; off-page relations remain navigable. */
export function PathDependencyGraph({ materials, data, conflicts, onEdit }: {
  materials: DependencyMaterial[]; data?: PublicReadingPath | null; conflicts: string[]; onEdit: (id: string) => void;
}) {
  const [focus, setFocus] = useState("");
  const [page, setPage] = useState(0);
  const marker = useId().replaceAll(":", "");
  const rows = materials.filter(row => row.id), total = Math.max(1, Math.ceil(rows.length / 18));
  const currentPage = Math.min(page, total - 1), visible = rows.slice(currentPage * 18, (currentPage + 1) * 18);
  const selected = rows.find(row => row.id === focus) || visible[0];
  const label = (id: string) => { const item = rows.find(row => row.id === id); return item?.work_name || item?.node_name || data?.items.find(row => row.id === id)?.title || "已移除的材料"; };
  function select(id: string) { const index = rows.findIndex(row => row.id === id); if (index >= 0) { setFocus(id); setPage(Math.floor(index / 18)); } }
  const edges = rows.flatMap(row => (row.dependencies || []).map(relation => ({ from: relation.item_id, to: row.id!, kind: relation.kind, reason: relation.reason })));
  const relevant = edges.filter(edge => edge.from === selected?.id || edge.to === selected?.id);
  const point = (id: string) => { const index = visible.findIndex(row => row.id === id); return index < 0 ? null : { x: 20 + index % 3 * 300, y: 25 + Math.floor(index / 3) * 130 }; };
  return <section className={styles.graph} aria-label="先修依赖图"><header><h3>先修依赖图</h3><p><span className={styles.learningLegend}>→ 学习顺序</span>　<span>— 理论相关</span></p></header>
    <p>选择材料查看相连关系。箭头由先修材料指向后读材料；理论相关不决定先后。边框提示来自最近一次对当前编排的验证。</p>
    {rows.length ? <><div className={styles.graphScroll}><svg role="group" aria-label={`先修关系图，第 ${currentPage + 1} 页，共 ${total} 页`} viewBox={`0 0 900 ${Math.max(160, Math.ceil(visible.length / 3) * 130)}`}>
      <defs><marker id={marker} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="var(--annotation)"/></marker></defs>
      {relevant.map((edge, index) => { const a = point(edge.from), b = point(edge.to); if (!a || !b) return null; const forward = a.y !== b.y ? a.y < b.y : a.x < b.x;
        const x1 = a.x + 125, y1 = a.y + (forward ? 78 : 0), x2 = b.x + 125, y2 = b.y + (forward ? 0 : 78);
        return <path key={`${edge.from}:${edge.to}:${edge.kind}:${index}`} d={`M${x1},${y1} C${x1 + 35},${y1 + (forward ? 45 : -45)} ${x2 - 35},${y2 + (forward ? -45 : 45)} ${x2},${y2}`} fill="none" stroke={edge.kind === "learning_order" ? "var(--annotation)" : "var(--muted)"} strokeWidth="1.5" strokeDasharray={edge.kind === "theory_related" ? "4 3" : undefined} markerEnd={edge.kind === "learning_order" ? `url(#${marker})` : undefined}><title>{label(edge.from)} → {label(edge.to)} · {edge.kind === "learning_order" ? "学习顺序" : "理论相关"}</title></path>;
      })}
      {visible.map(row => { const p = point(row.id!)!, source = data?.items.find(item => item.id === row.id); return <g key={row.id} transform={`translate(${p.x},${p.y})`} role="button" tabIndex={0} aria-pressed={selected?.id === row.id} aria-label={`${label(row.id!)}${conflicts.includes(row.id!) ? "，存在先修冲突" : ""}`} onClick={() => select(row.id!)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(row.id!); } }}>
        <rect width="250" height="78" rx="3" fill={selected?.id === row.id ? "var(--paper)" : "var(--surface)"} stroke={conflicts.includes(row.id!) ? "var(--danger, #a73535)" : selected?.id === row.id ? "var(--annotation)" : "var(--line)"}/>
        {source?.cover_url ? <image href={normalizePublicResourceUrl(source.cover_url)} x="8" y="9" width="38" height="58" preserveAspectRatio="xMidYMid meet"/> : null}
        <text x="54" y="30" fill="var(--ink)" fontSize="13">{label(row.id!).slice(0, 13)}{label(row.id!).length > 13 ? "…" : ""}</text><text x="54" y="55" fill="var(--muted)" fontSize="11">{row.status === "withdrawn" ? "已撤回" : conflicts.includes(row.id!) ? "需要核对先修关系" : `${(row.dependencies || []).length} 项关联`}</text><title>{label(row.id!)}</title>
      </g>; })}
    </svg></div><nav aria-label="先修图分页"><button type="button" disabled={!currentPage} onClick={() => { setPage(currentPage - 1); setFocus(""); }}>上一页</button><span>第 {currentPage + 1} / {total} 页 · 共 {rows.length} 项</span><button type="button" disabled={currentPage + 1 >= total} onClick={() => { setPage(currentPage + 1); setFocus(""); }}>下一页</button></nav>
      {selected ? <div className={styles.graphRelations}><strong>{label(selected.id!)}</strong><button type="button" data-path-navigation="true" data-preview-item-id={selected.id} onClick={() => onEdit(selected.id!)}>编辑这份材料</button>{relevant.length ? <ul>{relevant.map((edge, index) => <li key={`${edge.from}:${edge.to}:${edge.kind}:${index}`}><button type="button" onClick={() => select(edge.from)} disabled={!rows.some(row => row.id === edge.from)}>{label(edge.from)}</button><span>{edge.kind === "learning_order" ? " → 先读后读 → " : " — 理论相关 — "}</span><button type="button" onClick={() => select(edge.to)}>{label(edge.to)}</button>{edge.reason ? <p>{edge.reason}</p> : null}</li>)}</ul> : <p>尚无已记录的关联。</p>}</div> : null}
    </> : <p>从馆藏选择材料后，可在此查看先修关系。</p>}
  </section>;
}
