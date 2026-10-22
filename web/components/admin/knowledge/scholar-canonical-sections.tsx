"use client";

import Link from "next/link";
import type { PublicScholarDetail } from "@/lib/api/scholars.types";
import { timelineDate } from "@/lib/api/timeline.types";
import styles from "./scholar-editor.module.css";

/** Confirmed records stay separate from the retained legacy free-text notes. */
export function ScholarCanonicalSections({ section, scholarId, data, error, reload }: { section: string; scholarId: string;
  data: PublicScholarDetail | null; error: string; reload: () => void }) {
  if (!["theory", "timeline"].includes(section)) return null;
  if (error) return <p role="alert">{error}<button type="button" onClick={reload}>重新核对正式资料</button></p>;
  if (!data) return <p role="status">正在读取已确认的关系与事件…</p>;
  const returnTo = `/admin/scholars/${scholarId}?section=${section}`;
  return <section className={styles.canonical}>
    {section === "theory" ? <>
      <header><h2>核心概念 <small>{data.concepts.count}</small></h2><Link href="/admin/theories/relations">管理规范关系 ↗</Link></header>
      <ul>{data.concepts.results.map(row => <li key={row.id}><div><strong>{row.name}</strong><small>{row.relation_label} · {row.source_count} 项来源</small></div><Link href={row.href} target="_blank" rel="noopener">查看来源 ↗</Link></li>)}</ul>{!data.concepts.count ? <p>还没有已确认的概念关联。</p> : null}
      <header><h2>相关人物 <small>{data.relations.count}</small></h2><Link href={`/admin/scholars/${scholarId}/relations`}>核对候选与编辑关系 ↗</Link></header>
      <ul>{data.relations.results.map(row => <li key={row.id}><div><strong>{row.source_scholar === scholarId ? row.target_name : row.source_name}</strong><small>已确认 · {row.relation_label}</small><p>{row.summary}</p>{row.source ? <details><summary>关系依据</summary><p>{row.source}</p></details> : null}</div><Link href={`/admin/scholars/${scholarId}/relations?relation=${row.id}`}>查看与编辑</Link></li>)}</ul>{!data.relations.count ? <p>尚无已发布的人物关系。候选保留在原关系审核中。</p> : null}
      <header><h2>相关主题 <small>{data.topics.count}</small></h2><Link href="/admin/knowledge">管理人物与主题关联 ↗</Link></header>
      <ul>{data.topics.results.map(row => <li key={row.id}><strong>{row.name}</strong><Link href={row.href} target="_blank" rel="noopener">查看已确认主题 ↗</Link></li>)}</ul>{!data.topics.count ? <p>尚未确认相关主题。</p> : null}
    </> : <><header><h2>生平时间线 <small>{data.timeline.count}</small></h2><Link href={`/admin/theories/timeline?${new URLSearchParams({returnTo})}`}>添加或管理事件 ↗</Link></header><ol className={styles.eventList}>{data.timeline.results.map(row => <li key={row.id}><time>{timelineDate(row)}</time><div><strong>{row.title}</strong><p>{row.description}</p>{row.evidence_source?.reader_href ? <Link href={row.evidence_source.reader_href} target="_blank" rel="noopener">查看原文来源 ↗</Link> : <small>{row.source_status === "citation_only" ? "有来源说明，全文位置待核对" : "原文资料仍需核对"}</small>}</div><Link href={`/admin/theories/timeline?${new URLSearchParams({event:row.id,returnTo})}`}>编辑</Link></li>)}</ol>{!data.timeline.count ? <p>尚无已发布的真实生平事件。下方历史笔记不会自动转为正式事件。</p> : null}</>}
    <p className={styles.empty}>此处展示当前公开条件下的正式资料；完整编辑、候选审核和其余分页在原管理入口继续处理。</p><button type="button" onClick={reload}>重新读取关联与来源</button>
  </section>;
}
