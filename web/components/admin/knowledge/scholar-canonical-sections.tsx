"use client";

import { ScholarLinks } from "./scholar-links";
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
      <ScholarLinks kind="node" scholarId={scholarId} blocked={blocked} onChanged={reload} derived={data?.concepts.results.filter(row=>row.relation_source==="published_work_relation")}/>
      <ScholarPersonRelations scholarId={scholarId} blocked={blocked} onChanged={reload}/>
      <ScholarLinks kind="topic" scholarId={scholarId} blocked={blocked} onChanged={reload}/>
    </> : <ScholarTimeline scholarId={scholarId} blocked={blocked} onChanged={reload}/>}
    <p className={styles.empty}>这里包含正式关系、待核对记录和已撤回内容。关系确认与学者正文发布分别保存；馆藏推导关联须沿原文来源核对。</p><button type="button" onClick={reload}>重新读取关联与来源</button>
  </section>;
}
