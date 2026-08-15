"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { TheoryGraph } from "@/lib/server-api";

export function TheoryGraphClient({ graph }: { graph: TheoryGraph }) {
  const [selectedId, setSelectedId] = useState(graph.nodes[0]?.id ?? "");
  const layout = useMemo(() => {
    const centerX = 420;
    const centerY = 300;
    const radius = Math.min(245, 120 + graph.nodes.length * 10);
    return new Map(graph.nodes.map((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(graph.nodes.length, 1) - Math.PI / 2;
      return [node.id, { x: centerX + Math.cos(angle) * radius, y: centerY + Math.sin(angle) * radius }];
    }));
  }, [graph.nodes]);
  const selected = graph.nodes.find((node) => node.id === selectedId) ?? null;
  const relatedEdges = graph.edges.filter((edge) => edge.source === selectedId || edge.target === selectedId);

  return (
    <div className="theory-graph-layout">
      <div className="theory-graph-canvas" role="img" aria-label="理论传统关系图">
        <svg viewBox="0 0 840 600">
          {graph.edges.map((edge) => {
            const source = layout.get(edge.source);
            const target = layout.get(edge.target);
            if (!source || !target) return null;
            return <line className={`edge ${edge.relation_type}`} key={edge.id} x1={source.x} y1={source.y} x2={target.x} y2={target.y} />;
          })}
          {graph.nodes.map((node) => {
            const point = layout.get(node.id)!;
            const selectedNode = node.id === selectedId;
            return (
              <g className={selectedNode ? "graph-node selected" : "graph-node"} key={node.id} onClick={() => setSelectedId(node.id)} role="button" tabIndex={0}>
                <circle cx={point.x} cy={point.y} r={selectedNode ? 46 : node.entity_level === "tradition" ? 38 : 28} />
                <text x={point.x} y={point.y + 4} textAnchor="middle">{node.name.slice(0, 8)}</text>
              </g>
            );
          })}
        </svg>
        {!graph.nodes.length ? <p className="empty-state">理论关系需要证据并经管理员确认后才会出现在图谱中。</p> : null}
      </div>
      <aside className="theory-graph-inspector panel">
        {selected ? (
          <>
            <p className="eyebrow">{selected.entity_level === "branch" ? "理论分支" : "理论传统"}</p>
            <h2>{selected.name}</h2>
            {selected.foreign_name ? <p>{selected.foreign_name}</p> : null}
            <dl><div><dt>已确认关系</dt><dd>{relatedEdges.length}</dd></div><div><dt>策展等级</dt><dd>{selected.curation_level}</dd></div></dl>
            <Link className="button" href={`/theory-schools/${selected.slug}`}>查看理论详情</Link>
            <div className="graph-related-list">
              {relatedEdges.map((edge) => {
                const relatedId = edge.source === selected.id ? edge.target : edge.source;
                const related = graph.nodes.find((node) => node.id === relatedId);
                return related ? <button key={edge.id} onClick={() => setSelectedId(related.id)}><span>{edge.relation_type}</span><strong>{related.name}</strong></button> : null;
              })}
            </div>
          </>
        ) : <p className="empty-state">选择一个理论节点查看详情。</p>}
      </aside>
    </div>
  );
}
