"use client";

import Link from "next/link";
import { ScholarPersonRelations } from "./scholar-person-relations";
import type { PublicScholarDetail } from "@/lib/api/scholars.types";
import { ScholarTimeline } from "./scholar-timeline";
import styles from "./scholar-editor.module.css";

/** Confirmed records stay separate from the retained legacy free-text notes. */
export function ScholarCanonicalSections({ section, scholarId, data, error, reload, blocked }: { section: string; scholarId: string; blocked: boolean;
  data: PublicScholarDetail | null; error: string; reload: () => void }) {
  if (!["theory", "timeline"].includes(section)) return null;

  return <section className={styles.canonical}>
    {error?<p role="alert">{error}<button type="button" onClick={reload}>重新核对正式资料</button></p>:null}
    {!data?<p role="status">正在读取已确认的关系与事件…</p>:null}
    {section === "theory" ? <>
      {data?<><header><h2>核心概念 <small>{data.concepts.count}</small></h2><Link href="/admin/theories/relations">管理规范关系 ↗</Link></header>
      <ul>{data.concepts.results.map(row => <li key={row.id}><div><strong>{row.name}</strong><small>{row.relation_label} · {row.source_count} 项来源</small></div><Link href={row.href} target="_blank" rel="noopener">查看来源 ↗</Link></li>)}</ul>{!data.concepts.count ? <p>还没有已确认的概念关联。</p> : null}
      </>:null}<ScholarPersonRelations scholarId={scholarId} blocked={blocked} onChanged={reload}/>
      {data?<><header><h2>相关主题 <small>{data.topics.count}</small></h2><Link href="/admin/knowledge">管理人物与主题关联 ↗</Link></header>
      <ul>{data.topics.results.map(row => <li key={row.id}><strong>{row.name}</strong><Link href={row.href} target="_blank" rel="noopener">查看已确认主题 ↗</Link></li>)}</ul>{!data.topics.count ? <p>尚未确认相关主题。</p> : null}
      </>:null}
    </> : <ScholarTimeline scholarId={scholarId} blocked={blocked} onChanged={reload}/>}
    <p className={styles.empty}>此处展示当前公开条件下的正式资料；人物关系和生平事件包含待核对草稿并可在此编辑；概念/主题关联继续原管理入口。</p><button type="button" onClick={reload}>重新读取关联与来源</button>
  </section>;
}
