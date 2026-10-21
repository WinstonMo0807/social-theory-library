"use client";

import { useEffect, useId, useMemo, useRef, useState, type PointerEvent } from "react";
import { LocateFixed, Maximize, Minus, Plus } from "lucide-react";
import type { GraphEdge, GraphNode, PublicTheoryGraph } from "@/lib/api/graph.types";
import styles from "./theory-graph.module.css";

type Point = { x: number; y: number };
export function GraphCanvas({ graph, selectedNode, selectedEdge, onNode, onEdge, zoom, offset, onTransform }: {
  graph: PublicTheoryGraph; selectedNode: string; selectedEdge: string; onNode: (node: GraphNode) => void; onEdge: (edge: GraphEdge) => void;
  zoom: number; offset: Point; onTransform: (zoom: number, offset: Point) => void;
}) {
  const panel = useRef<HTMLDivElement>(null), svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ pointer: number; x: number; y: number; original: Point } | null>(null);
  const [notice, setNotice] = useState("");
  const key = useId().replace(/:/g, "");
  const positions = useMemo(() => {
    const result = new Map<string, Point & { radius: number }>();
    for (const level of [0, 1, 2, 3]) {
      const rows = graph.nodes.filter(node => (node.is_center ? 0 : Math.max(1, Math.min(3, node.depth))) === level);
      const ring = level === 0 ? 0 : level === 1 ? 215 : level === 2 ? 330 : 445;
      rows.forEach((node, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, rows.length);
        result.set(node.id, { x: 500 + Math.cos(angle) * ring, y: 350 + Math.sin(angle) * ring * .72,
          radius: level === 0 ? 49 : Math.max(7, Math.min(node.kind === "scholar" ? 34 : 26, Math.PI * ring / Math.max(1, rows.length) * .6)) });
      });
    }
    return result;
  }, [graph.nodes]);
  const transform = useRef({ zoom, offset, onTransform });
  useEffect(() => { transform.current = { zoom, offset, onTransform }; }, [zoom, offset, onTransform]);
  useEffect(() => {
    const element = svg.current;
    function wheel(event: WheelEvent) {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const current = transform.current;
      current.onTransform(Math.max(.15, Math.min(4, current.zoom + (event.deltaY < 0 ? .1 : -.1))), current.offset);
    }
    element?.addEventListener("wheel", wheel, { passive: false });
    return () => element?.removeEventListener("wheel", wheel);
  }, []);
  function down(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0 || (event.target as Element).closest('[role="button"]')) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, original: offset };
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    const current = drag.current;
    if (!current || current.pointer !== event.pointerId) return;
    const scale = 1000 / Math.max(1, event.currentTarget.getBoundingClientRect().width);
    onTransform(zoom, { x: current.original.x + (event.clientX - current.x) * scale, y: current.original.y + (event.clientY - current.y) * scale });
  }
  async function fullscreen() {
    try {
      if (document.fullscreenElement === panel.current) await document.exitFullscreen();
      else if (panel.current?.requestFullscreen) await panel.current.requestFullscreen();
      else throw new Error("unsupported");
      setNotice("");
    } catch { setNotice("浏览器未允许全屏，可继续缩放或使用关系列表。"); }
  }
  return <div className={styles.canvas} ref={panel}>
    <div className={styles.canvasLegend}><strong>图例</strong><span><i data-kind="center" />中心节点</span><span><i data-kind="scholar" />学者 / 人物</span><span><i data-kind="topic" />概念 / 主题</span><span>→ 有方向关系</span><span>— 无方向关系</span>{graph.candidate_count !== null ? <span>┄ 待审核候选关系</span> : null}</div>
    <svg ref={svg} viewBox="0 0 1000 740" role="group" aria-label="知识关系图，可选择节点或关系" onPointerDown={down} onPointerMove={move} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <defs><marker id={`${key}-arrow`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto-start-reverse" markerUnits="strokeWidth"><path d="M 0 0 L 7 3.5 L 0 7 Z" fill="context-stroke" /></marker>
        {graph.nodes.filter(node => node.image_url && node.kind === "scholar").map(node => { const point = positions.get(node.id)!; return <clipPath id={`${key}-${node.entity_id}`} key={node.id}><circle cx={point.x} cy={point.y} r={point.radius - 2} /></clipPath>; })}
      </defs>
      <g transform={`translate(${offset.x} ${offset.y}) translate(500 350) scale(${zoom}) translate(-500 -350)`}>
        {[...graph.edges, ...graph.candidate_edges].map(edge => {
          const from = positions.get(edge.source), to = positions.get(edge.target);
          if (!from || !to) return null;
          const length = Math.hypot(to.x - from.x, to.y - from.y) || 1, dx = (to.x - from.x) / length, dy = (to.y - from.y) / length;
          const x1 = from.x + dx * (from.radius + 4), y1 = from.y + dy * (from.radius + 4), x2 = to.x - dx * (to.radius + 5), y2 = to.y - dy * (to.radius + 5);
          const active = selectedEdge === edge.id;
          return <g key={edge.id} role="button" tabIndex={0} aria-label={`${edge.status !== "published" ? "待审核候选：" : ""}${graph.nodes.find(node => node.id === edge.source)?.name} ${edge.relation_label} ${graph.nodes.find(node => node.id === edge.target)?.name}`} aria-pressed={active} className={`${styles.graphEdge} ${active ? styles.activeEdge : ""} ${edge.status !== "published" ? styles.candidateEdge : ""}`} onClick={() => onEdge(edge)} onKeyDown={event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); onEdge(edge); } }}>
            <line className={styles.edgeHitArea} x1={x1} y1={y1} x2={x2} y2={y2} />
            <line x1={x1} y1={y1} x2={x2} y2={y2} markerEnd={edge.direction === "undirected" ? undefined : `url(#${key}-arrow)`} markerStart={edge.direction === "bidirectional" ? `url(#${key}-arrow)` : undefined} />
            {graph.edges.length <= 18 || active ? <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 7} textAnchor="middle">{edge.relation_label}</text> : null}<title>{edge.relation_label}</title>
          </g>;
        })}
        {graph.nodes.map(node => {
          const point = positions.get(node.id)!, active = node.id === selectedNode;
          const displayName = graph.nodes.length <= 24 || active || node.is_center;
          return <g key={node.id} className={`${styles.graphNode} ${node.is_center ? styles.centerNode : ""} ${active ? styles.activeNode : ""}`} data-kind={node.kind} role="button" tabIndex={0} aria-label={`查看${node.name}，${node.depth}层关系`} aria-pressed={active} onClick={() => onNode(node)} onKeyDown={event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); onNode(node); } }}>
            <circle cx={point.x} cy={point.y} r={point.radius} />
            {node.image_url && node.kind === "scholar" ? <image href={node.image_url} x={point.x - point.radius} y={point.y - point.radius} width={point.radius * 2} height={point.radius * 2} preserveAspectRatio="xMidYMid slice" clipPath={`url(#${key}-${node.entity_id})`} /> : null}
            {displayName ? <text className={node.is_center && node.kind !== "scholar" ? styles.centerLabel : ""} x={point.x} y={node.is_center && node.kind !== "scholar" ? point.y + 5 : point.y + point.radius + 21} textAnchor="middle">{node.name.length > 10 ? `${node.name.slice(0, 9)}…` : node.name}</text> : null}
            <title>{node.name}{node.summary ? `：${node.summary}` : ""}</title>
          </g>;
        })}
      </g>
    </svg>
    <div className={styles.canvasControls}><button type="button" aria-label="缩小图谱" disabled={zoom <= .15} onClick={() => onTransform(Math.max(.15, zoom - .1), offset)}><Minus size={17} /></button><output aria-label="图谱缩放比例">{Math.round(zoom * 100)}%</output><button type="button" aria-label="放大图谱" disabled={zoom >= 4} onClick={() => onTransform(Math.min(4, zoom + .1), offset)}><Plus size={17} /></button><button type="button" aria-label="重置图谱位置" onClick={() => onTransform(1, { x: 0, y: 0 })}><LocateFixed size={17} /></button><button type="button" aria-label="切换图谱全屏" onClick={() => void fullscreen()}><Maximize size={16} /></button></div>
    {notice ? <p className={styles.canvasNotice} role="status">{notice}</p> : null}
  </div>;
}
