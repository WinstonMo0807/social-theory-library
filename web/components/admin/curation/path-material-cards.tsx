"use client";

import { useRef, type DragEvent } from "react";
import { GripVertical, ChevronDown, ChevronRight } from "lucide-react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { PublicReadingPath } from "@/lib/api/reading-paths.types";
import styles from "../knowledge/path-editor.module.css";

type Material = { key: string; id?: string; work_name: string; node_name: string; is_required: boolean; learning_goal: string; status: string };
type Stage = { key: string; id?: string; name: string; estimated_reading: string; description: string; items: Material[] };
export type PathDrag = { kind: "stage" | "item"; key: string } | null;

export function PathStageIndex({ stages, active, onSelect, onMoveStage, onMoveItem, dragRef }: {
  stages: Stage[]; active: number; onSelect: (index: number) => void; onMoveStage: (key: string, before?: string) => void;
  onMoveItem: (key: string, stage: string, before?: string) => void; dragRef: React.RefObject<PathDrag>;
}) {
  return <nav className={styles.stageIndex} aria-label="阅读阶段">{stages.map((stage, index) => <button key={stage.key} style={{order:index*2}} type="button" aria-current={index === active ? "true" : undefined}
    draggable onDragStart={event => { dragRef.current = { kind: "stage", key: stage.key }; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", stage.key); }} onDragEnd={() => { dragRef.current = null; }}
    onDragOver={event => { if (dragRef.current) event.preventDefault(); }} onDrop={event => { event.preventDefault(); const current = dragRef.current; dragRef.current = null; if (current?.kind === "stage") onMoveStage(current.key, stage.key); else if (current) onMoveItem(current.key, stage.key); }} onClick={() => onSelect(index)}>
    <GripVertical size={13} aria-hidden="true"/><span className={styles.stageNumber}>{index + 1}</span><span><strong>{stage.name || "未命名阶段"}</strong><small>{stage.estimated_reading || "用时未设置"} · {stage.items.length} 项</small><small>{stage.description}</small></span>{index===active?<ChevronDown size={13}/>:<ChevronRight size={13}/>}
  </button>)}</nav>;
}

export function PathMaterialCards({ stage, selected, data, onSelect, onMove, dragRef }: {
  stage: Stage; selected: number; data: PublicReadingPath | null; onSelect: (index: number) => void;
  onMove: (key: string, stage: string, before?: string) => void; dragRef: React.RefObject<PathDrag>;
}) {
  const hover = useRef<HTMLElement | null>(null);
  function end() { dragRef.current = null; hover.current?.removeAttribute("data-drop"); hover.current = null; }
  function over(event: DragEvent<HTMLElement>) { if (dragRef.current?.kind === "item") { event.preventDefault(); hover.current?.removeAttribute("data-drop"); event.currentTarget.dataset.drop = "true"; hover.current = event.currentTarget; } }
  function drop(event: DragEvent<HTMLElement>, before?: string) { event.preventDefault(); const current = dragRef.current; end(); if (current?.kind === "item") onMove(current.key, stage.key, before); }
  return <nav className={styles.materialCards} aria-label="本阶段阅读项目">{stage.items.map((item, index) => {
    const source = data?.items.find(row => row.id === item.id);
    return <button key={item.key} type="button" data-preview-item-id={item.id || item.key} aria-current={index === selected ? "true" : undefined}
      draggable onDragStart={event => { dragRef.current = { kind: "item", key: item.key }; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", item.key); }} onDragEnd={end} onDragOver={over} onDragLeave={() => hover.current?.removeAttribute("data-drop")} onDrop={event => drop(event, item.key)} onClick={() => onSelect(index)}>
      <GripVertical size={13} aria-hidden="true"/>{source?.cover_url ? <img src={normalizePublicResourceUrl(source.cover_url)} alt=""/> : <span className={styles.cardPlaceholder}>暂无封面</span>}
      <span><strong>{item.work_name || item.node_name || source?.title || "尚未选择材料"}</strong><em>{item.status === "withdrawn" ? "已撤回" : item.is_required ? "必读" : "选读"}</em>
        {source ? <small>{[source.authors.join("、"), source.publication_year, source.version_label].filter(Boolean).join(" · ") || source.source_notice}</small> : <small>材料详情待核对</small>}
        <small>阅读目标：{item.learning_goal || "尚未填写"}</small></span>
    </button>;
  })}<span className={styles.dropEnd} onDragOver={over} onDragLeave={() => hover.current?.removeAttribute("data-drop")} onDrop={event => drop(event)}>拖动到此处排在本阶段末尾。也可使用下方位置控件。</span></nav>;
}
