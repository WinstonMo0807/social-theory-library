"use client";
import { MediaPlacement } from "@/components/media-placement";

import Link from "next/link";
import { ArrowRight, BookOpen, X } from "lucide-react";
import { useState } from "react";
import { CollectionLink } from "@/components/collection-link";
import { graphKindLabels, graphNodeLabels, type GraphEdge, type GraphNode, type PublicTheoryGraph } from "@/lib/api/graph.types";
import styles from "./theory-graph.module.css";

export function GraphInspector({ graph, node, edge, onNode, onEdge, onCenter, onClose, disabled }: {
  graph: PublicTheoryGraph; node?: GraphNode; edge?: GraphEdge; onNode: (node: GraphNode) => void;
  onEdge: (edge: GraphEdge) => void; onCenter: (node: GraphNode) => void; onClose: () => void; disabled: boolean;
}) {
  const [tab, setTab] = useState<"overview" | "related">("overview");
  const source = graph.nodes.find(row => row.id === edge?.source), target = graph.nodes.find(row => row.id === edge?.target);
  const related = node ? graph.edges.filter(row => row.source === node.id || row.target === node.id) : [];
  return <section className={styles.inspector} aria-label={edge ? "选中关系详情" : "选中节点详情"}>
    <header><h2>{edge ? "选中关系" : "节点详情"}</h2><button type="button" aria-label="关闭图谱详情" onClick={onClose}><X size={18} /></button></header>
    {edge ? <>
      <div className={styles.edgeTitle}><strong>{source?.name}</strong><span>{edge.direction === "undirected" ? "—" : edge.direction === "bidirectional" ? "↔" : "→"}</span><strong>{target?.name}</strong></div>
      <dl className={styles.facts}><dt>关系类型</dt><dd>{edge.relation_label}</dd><dt>方向</dt><dd>{edge.direction === "undirected" ? "无方向关系" : edge.direction === "bidirectional" ? "双向关系" : `${source?.name} → ${target?.name}`}</dd><dt>确认状态</dt><dd>{edge.status === "published" ? "已发布" : "待审核的候选关系"}</dd></dl>
      {edge.status !== "published" ? <p className={styles.candidateNotice}>此关系尚未公开，不能作为已确认的学术关系使用。{graph.candidate_access.review_href ? <Link href={graph.candidate_access.review_href}>进入后台核对依据</Link> : null}</p> : null}
      <h3>概要说明</h3><p>{edge.description || "这条关系尚未提供公开说明。"}</p>
      <h3>证据与来源</h3>
      {edge.evidence_source ? <p>{edge.evidence_source}</p> : null}
      {edge.evidence.length ? <ul className={styles.evidenceList}>{edge.evidence.map(item => <li key={item.id}><strong>{item.title}</strong>{item.edition_label ? <small>{item.edition_label}</small> : null}<blockquote>{item.quote}</blockquote><small>{item.printed_page_label ? `印刷页 ${item.printed_page_label} · ` : ""}PDF 第 {item.pdf_page} 页</small><CollectionLink href={item.reader_href}>查看原文<ArrowRight size={13} /></CollectionLink></li>)}</ul> : <p className={styles.muted}>{edge.source_status === "citation_only" ? "仅有来源说明，尚无可定位的原文依据。" : "尚无可公开核对的关系原文。"}</p>}
      {edge.evidence_truncated ? <p className={styles.muted}>当前展示前 {edge.evidence.length} 条原文依据。</p> : null}
      <div className={styles.detailActions}>{source ? <button type="button" onClick={() => onNode(source)}>查看{source.name}</button> : null}{target ? <button type="button" onClick={() => onNode(target)}>查看{target.name}</button> : null}</div>
    </> : node ? <>
      <nav className={styles.detailTabs} aria-label="节点详情内容"><button type="button" aria-pressed={tab === "overview"} onClick={() => setTab("overview")}>概览</button><button type="button" aria-pressed={tab === "related"} onClick={() => setTab("related")}>相关内容</button></nav>
      <div className={styles.nodeTitle}><h3>{node.name}</h3><span>{graphNodeLabels[node.node_type] || graphKindLabels[node.kind]}</span></div>
      {tab === "overview" ? <>
        {node.image_url ? <MediaPlacement uses={node.image_media?.display_uses}><img className={`${styles.detailImage} ${node.kind === "scholar" ? styles.portrait : ""}`} src={node.image_url} alt="" /></MediaPlacement> : null}
        {node.foreign_name ? <p className={styles.foreign}>{node.foreign_name}</p> : null}
        <p>{node.summary || "尚无已发布的条目简介。"}</p>{node.period_label ? <p className={styles.muted}>{node.period_label}</p> : null}
        <h3>直接关系 <small>{related.length}</small></h3>
        <ul className={styles.neighbors}>{related.map(row => { const other = graph.nodes.find(item => item.id === (row.source === node.id ? row.target : row.source)); return <li key={row.id}><button type="button" onClick={() => onEdge(row)}><strong>{other?.name}</strong><small>{row.relation_label}</small><ArrowRight size={13} /></button></li>; })}</ul>
        {!related.length ? <p className={styles.muted}>当前范围内没有已公开的直接关系。</p> : null}
      </> : <><h3>相邻节点</h3><ul className={styles.neighbors}>{graph.nodes.filter(row => related.some(relation => relation.source === row.id || relation.target === row.id) && row.id !== node.id).map(row => <li key={row.id}><button type="button" onClick={() => onNode(row)}>{row.image_url && row.kind === "scholar" ? <MediaPlacement uses={row.image_media?.display_uses} fallback={<BookOpen size={18}/>}><img src={row.image_url} alt="" /></MediaPlacement> : <BookOpen size={18} />}<span><strong>{row.name}</strong><small>{graphNodeLabels[row.node_type] || graphKindLabels[row.kind]}</small></span><ArrowRight size={13} /></button></li>)}</ul>{!related.length ? <p className={styles.muted}>当前范围内没有相邻节点。</p> : null}</>}
      <div className={styles.detailActions}><Link className={styles.outlineButton} href={node.href}>查看完整条目<ArrowRight size={14} /></Link><button className={styles.primaryButton} type="button" disabled={disabled || node.is_center} onClick={() => onCenter(node)}>以此为中心展开</button></div>
    </> : <p className={styles.empty}>请选择一个节点或关系，查看公开资料与依据。</p>}
  </section>;
}
