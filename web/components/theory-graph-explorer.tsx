"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, LocateFixed, Minus, Network, Plus, RotateCcw, Search, Share2, UserRound } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { LocalTheoryGraph } from "@/lib/server-api";
import { nodeTypeLabels } from "./theory-system-ui";

type Point = { x: number; y: number };

export function TheoryGraphExplorer({ graph }: { graph: LocalTheoryGraph }) {
  const [selectedId, setSelectedId] = useState(graph.center || graph.nodes[0]?.id || "");
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState<Point>({ x: 0, y: 0 });
  const [query, setQuery] = useState("");
  const dragRef = useRef<{ x: number; y: number; originX: number; originY: number } | null>(null);
  const positions = useMemo(() => graphLayout(graph), [graph]);
  const selected = graph.nodes.find((item) => item.id === selectedId) || graph.nodes[0];
  const visibleMatches = query.trim() ? graph.nodes.filter((item) => item.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())) : [];

  function resetView() {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button,a,input")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { x: event.clientX, y: event.clientY, originX: offset.x, originY: offset.y };
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragRef.current) return;
    setOffset({
      x: dragRef.current.originX + event.clientX - dragRef.current.x,
      y: dragRef.current.originY + event.clientY - dragRef.current.y,
    });
  }

  function handleWheel(event: React.WheelEvent<HTMLDivElement>) {
    if (!event.ctrlKey && Math.abs(event.deltaY) < 2) return;
    event.preventDefault();
    setZoom((value) => Math.min(1.65, Math.max(.65, value + (event.deltaY < 0 ? .08 : -.08))));
  }

  async function shareView() {
    const url = new URL(window.location.href);
    if (selected?.slug) url.searchParams.set("center", selected.slug);
    url.searchParams.set("depth", String(graph.depth));
    await navigator.clipboard?.writeText(url.toString());
  }

  if (!graph.nodes.length) {
    return <div className="theory-graph-empty"><Network size={30} /><strong>尚无公开图谱数据</strong><p>只有经过审核并发布的理论关系才会进入公共图谱。</p></div>;
  }

  return (
    <div className="theory-graph-explorer">
      <div className="theory-graph-canvas" onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={() => { dragRef.current = null; }} onPointerCancel={() => { dragRef.current = null; }} onWheel={handleWheel}>
        <div className="graph-toolbar">
          <button type="button" onClick={() => setZoom((value) => Math.min(1.65, value + .1))} aria-label="放大"><Plus size={18} /></button>
          <button type="button" onClick={() => setZoom((value) => Math.max(.65, value - .1))} aria-label="缩小"><Minus size={18} /></button>
          <button type="button" onClick={resetView} aria-label="回到中心"><LocateFixed size={18} /></button>
          <button type="button" onClick={shareView} aria-label="分享当前视图"><Share2 size={18} /></button>
        </div>
        <div className="graph-node-search">
          <Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索当前节点" />
          {visibleMatches.length ? <div>{visibleMatches.slice(0, 8).map((item) => <button type="button" key={item.id} onClick={() => { setSelectedId(item.id); setQuery(""); }}>{item.name}</button>)}</div> : null}
        </div>
        <div className="graph-transform" style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }}>
          <svg viewBox="0 0 1000 650" aria-hidden="true">
            {graph.edges.map((edge) => {
              const source = positions.get(edge.source);
              const target = positions.get(edge.target);
              if (!source || !target) return null;
              return <g key={edge.id}><line className={`relation-${edge.relation_type}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} /><text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 7}>{edge.relation_label}</text></g>;
            })}
          </svg>
          {graph.nodes.map((node) => {
            const position = positions.get(node.id)!;
            return <button
              type="button"
              className={`graph-node kind-${node.kind} type-${node.node_type || "other"} ${node.is_center ? "center" : ""} ${selectedId === node.id ? "selected" : ""}`}
              style={{ left: `${position.x / 10}%`, top: `${position.y / 6.5}%` }}
              key={node.id}
              onClick={() => setSelectedId(node.id)}
            >
              {node.kind === "work" ? <BookOpen size={16} /> : node.kind === "scholar" ? <UserRound size={16} /> : null}
              <strong>{node.name}</strong>
              {node.period_label ? <small>{node.period_label}</small> : null}
            </button>;
          })}
        </div>
        <div className="graph-minimap" aria-label="图谱小地图"><Network size={24} /><span>{graph.nodes.length} 个节点</span></div>
        <div className="theory-graph-mobile-list" aria-label="理论节点与关系列表">
          {graph.nodes.map((node) => {
            const relations = graph.edges.filter((edge) => edge.source === node.id || edge.target === node.id);
            return <button className={selectedId === node.id ? "selected" : ""} type="button" key={node.id} onClick={() => setSelectedId(node.id)}><span>{node.kind === "knowledge_node" ? nodeTypeLabels[node.node_type || ""] : node.kind === "scholar" ? "学者" : "馆藏"}</span><strong>{node.name}</strong><small>{relations.length} 条直接关系</small><ArrowRight size={15} /></button>;
          })}
        </div>
      </div>

      <aside className="theory-graph-detail">
        {selected ? <>
          <header><span>{selected.kind === "knowledge_node" ? nodeTypeLabels[selected.node_type || ""] : selected.kind === "scholar" ? "学者" : "馆藏文献"}</span><h2>{selected.name}</h2>{selected.foreign_name ? <p>{selected.foreign_name}</p> : null}</header>
          {selected.period_label ? <dl><dt>形成时期</dt><dd>{selected.period_label}</dd></dl> : null}
          {selected.summary ? <section><h3>条目摘要</h3><p>{selected.summary}</p></section> : null}
          <section><h3>直接关系</h3>{graph.edges.filter((edge) => edge.source === selected.id || edge.target === selected.id).slice(0, 8).map((edge) => { const otherId = edge.source === selected.id ? edge.target : edge.source; const other = graph.nodes.find((node) => node.id === otherId); return <button type="button" key={edge.id} onClick={() => other && setSelectedId(other.id)}><span>{edge.relation_label}</span><strong>{other?.name}</strong><ArrowRight size={15} /></button>; })}</section>
          {selected.kind === "knowledge_node" && selected.slug ? <>
            <Link className="graph-primary-link" href={`/theories/nodes/${selected.slug}`}>查看完整条目<ArrowRight size={17} /></Link>
            <Link className="graph-secondary-link" href={`/theories/graph?center=${encodeURIComponent(selected.slug)}&depth=${graph.depth === 1 ? 2 : 1}`}>{graph.depth === 1 ? "展开两层关系" : "收回一层关系"}<RotateCcw size={16} /></Link>
          </> : selected.kind === "scholar" && selected.slug ? <Link className="graph-primary-link" href={`/scholars/${selected.slug}`}>查看学者页面<ArrowRight size={17} /></Link> : selected.work?.detail_href || selected.work?.reader_href ? <Link className="graph-primary-link" href={selected.work.detail_href || selected.work.reader_href || "/explore"}>查看馆藏<ArrowRight size={17} /></Link> : null}
        </> : null}
      </aside>
    </div>
  );
}

function graphLayout(graph: LocalTheoryGraph) {
  const result = new Map<string, Point>();
  const center = graph.nodes.find((item) => item.id === graph.center) || graph.nodes[0];
  if (!center) return result;
  result.set(center.id, { x: 500, y: 325 });
  const others = graph.nodes.filter((item) => item.id !== center.id);
  others.forEach((node, index) => {
    const ring = index < 10 ? 0 : 1;
    const ringItems = ring === 0 ? Math.min(10, others.length) : Math.max(1, others.length - 10);
    const localIndex = ring === 0 ? index : index - 10;
    const angle = (Math.PI * 2 * localIndex / ringItems) - Math.PI / 2;
    const radiusX = ring === 0 ? 260 : 410;
    const radiusY = ring === 0 ? 190 : 270;
    result.set(node.id, { x: 500 + Math.cos(angle) * radiusX, y: 325 + Math.sin(angle) * radiusY });
  });
  return result;
}
