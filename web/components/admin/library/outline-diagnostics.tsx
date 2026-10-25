"use client";

import { useMemo, useState } from "react";
import type { EditableOutlineNode } from "./outline-edit-state";
import styles from "./document-outline.module.css";

type Props = {
  items: Array<Record<string, unknown>>;
  nodes: EditableOutlineNode[];
  currentId: string;
  pageCount: number;
  onSelect: (node: EditableOutlineNode) => void;
  onPreview: (page: number) => void;
};

export function OutlineDiagnostics({ items, nodes, currentId, pageCount, onSelect, onPreview }: Props) {
  const [onlyCurrent, setOnlyCurrent] = useState(false);
  const [limit, setLimit] = useState(50);
  const byId = useMemo(() => new Map(nodes.map(node => [node.id, node])), [nodes]);
  const rows = useMemo(() => items.filter(item => !onlyCurrent || !item.node_id || item.node_id === currentId), [items, onlyCurrent, currentId]);
  if (!items.length) return null;
  return <div className={styles.diagnosticPanel}>
    <header><h3>提取时的核对提示 <small>{rows.length} 条</small></h3><label><input type="checkbox" checked={onlyCurrent} onChange={event => { setOnlyCurrent(event.target.checked); setLimit(50); }} />仅当前节点及整份目录提示</label></header>
    <p className={styles.caption}>提示保留提取当时的观察。编辑后的结果请对照原稿确认，保存候选后仍需明确采用。</p>
    <ul className={styles.diagnostics}>{rows.slice(0, limit).map((item, index) => {
      const node = typeof item.node_id === "string" ? byId.get(item.node_id) : undefined;
      const pages = Array.isArray(item.observed_pages) ? [...new Set(item.observed_pages.filter((page): page is number => typeof page === "number" && Number.isInteger(page) && page >= 1 && page <= pageCount))].slice(0, 20) : [];
      return <li key={index}>
        <p>{String(item.message || item.code || "目录需要进一步核对")}</p>
        <div className={styles.diagnosticActions}>
          {node ? <button type="button" onClick={() => onSelect(node)}>核对此节点</button> : item.node_id ? <span className={styles.caption}>此节点已不在当前草稿中，原提示仍保留。</span> : null}
          {pages.map(page => <button type="button" key={page} onClick={() => onPreview(page)} aria-label={`查看对比原稿的 PDF 第 ${page} 页`}>PDF {page}</button>)}
          {typeof item.observed_page_count === "number" && item.observed_page_count > pages.length ? <span className={styles.caption}>{item.observed_page_count_is_lower_bound ? "至少" : "共"}{item.observed_page_count} 个观察页，此处显示 {pages.length} 页。</span> : null}
        </div>
      </li>;
    })}</ul>
    {!rows.length ? <p className={styles.caption}>此节点没有提取提示；仍需核对标题、层级和落点。</p> : null}
    {rows.length > limit ? <button type="button" onClick={() => setLimit(value => value + 50)}>再显示 50 条（已显示 {Math.min(limit, rows.length)} / {rows.length}）</button> : null}
  </div>;
}
