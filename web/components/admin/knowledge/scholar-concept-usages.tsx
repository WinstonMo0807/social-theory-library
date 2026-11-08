"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import styles from "./concept-editor.module.css";

type Page = components["schemas"]["ScholarUsagePage"];
const states: Record<string,string> = {candidate:"待确认",confirmed:"已确认归属",conflict:"存在歧义"};

export function ScholarConceptUsages({scholarId,owner}:{scholarId:string;owner:string}) {
  const [page,setPage]=useState(1), [selected,setSelected]=useState<{id:string;name:string}[]>([]);
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Page>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<Page>(`/catalog/admin/scholars/${scholarId}/concept-usages/?page=${page}`,owner,undefined,load);
  return <section className={styles.workspace} aria-label="学者的概念用法">
    <header className={styles.heading}><div><h2>概念用法</h2><p>按已填写的作者归属汇集用法。编辑后在所属概念中确认；用法记录与公开版本分别核对。</p></div><button type="button" onClick={resource.reload}>重新读取</button></header>
    {resource.error?<p role="alert">{resource.error}<button type="button" onClick={()=>{setPage(1);resource.reload();}}>返回第一页重读</button></p>:!resource.data?<LoadingState role="status">正在读取用法与准确材料…</LoadingState>:<>
      <p>共 {resource.data.count} 个知识条目含有当前归属记录 · 第 {page} 页</p>
      {resource.data.results.map(group=><section className={styles.panel} key={group.node_id}>
        <header><h3>{group.node_name}</h3><p>{group.revision_status==="draft"?"当前已保存草稿，尚未公开":group.revision_status==="published"?"已发布编排，来源仍须核对":"历史编排"}</p><Link href={group.edit_url}>编辑用法与来源 →</Link></header>
        <ol>{group.items.map(item=><li key={item.id}>
          <strong>{String(item.concept_usage?.term||"术语待补")}</strong><small> · {states[String(item.concept_usage?.review_status)]||"待核对"}</small>
          {item.concept_usage?.interpretation?<p>{String(item.concept_usage.interpretation)}</p>:null}
          {item.source?<><p>{item.source.title}{item.source.page_start?` · PDF 第 ${item.source.page_start} 页`:""}</p>{item.source.text?<blockquote className={styles.quote}>{item.source.text}</blockquote>:null}{item.source.reader_url?<Link href={item.source.reader_url} target="_blank" rel="noopener">核对准确原文 ↗</Link>:<p>准确来源尚不能公开，需继续核对。</p>}</>:<p>原材料暂不可用，引用记录仍保留。</p>}
        </li>)}</ol>
      </section>)}
      {!resource.data.count?<p>还没有明确归属到此学者的概念用法。选择知识条目，在原文中核对作者和归属依据后保存。</p>:null}
      <nav className={styles.pagination} aria-label="概念用法分组分页"><button type="button" disabled={!resource.data.previous} onClick={()=>setPage(value=>value-1)}>上一页</button><button type="button" disabled={!resource.data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>
    </>}
    <details data-disclosure="collection" className={styles.panel}><summary>选择概念并从材料提取用法</summary><EntityPicker owner={owner} label="选择知识条目" endpoint="/catalog/admin/theory-system/nodes/" nameField="canonical_name_zh" values={selected} onChange={values=>{const value=values.at(-1);setSelected(value?.id?[{id:value.id,name:value.name}]:[]);}}/>{selected[0]?<Link href={`/admin/theories/${selected[0].id}?section=usages`}>进入{selected[0].name}的概念用法 →</Link>:null}</details>
  </section>;
}
