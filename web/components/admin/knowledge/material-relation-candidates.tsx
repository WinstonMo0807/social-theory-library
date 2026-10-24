"use client";

import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { components } from "@/lib/api/generated/schema";
import styles from "./node-relations.module.css";
import shared from "./scholar-editor.module.css";

type Page = components["schemas"]["PaginatedTheoryReviewTaskList"];
const labels: Record<string,string> = {pending:"待核对",needs_changes:"待修改",deferred:"延后处理",insufficient_evidence:"证据不足"};

export function MaterialRelationCandidates({owner,centerKind,centerId}:{owner:string;centerKind:"node"|"scholar";centerId:string}) {
  const [page,setPage]=useState(1);
  const query=new URLSearchParams({[centerKind==="scholar"?"scholar":"candidate_node"]:centerId,review_only:"true",page_size:"6",page:String(page)});
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Page>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<Page>(`/catalog/admin/theory-system/review-tasks/?${query}`,owner,undefined,load);
  return <section aria-label="原材料审核候选">
    <header><h4>材料中的待核对线索 <small>{resource.data?.count??"…"}</small></h4><p>{centerKind==="scholar"?"来自该学者已确认参与的具体版本。作者、译者或其他参与身份不等于本人持有材料中的观点。":"来自该条目在原材料识别与审核流程中的候选。"} 这些线索尚未建立人物或概念之间的关系。</p></header>
    {resource.error?<p role="alert">{resource.error}<button type="button" onClick={()=>{setPage(1);resource.reload();}}>从第一页重新读取</button></p>:!resource.data?<p role="status">正在读取原材料审核任务…</p>:<>
      <ul className={styles.candidateRows}>{resource.data.results.map(row=><li key={row.id}>
        <div><strong>{row.work_title||"原文献当前不可读"} → {row.node_name||row.suggested_node_name||"待核对条目"}</strong><p>{labels[row.status||""]||row.status||"状态待核对"}</p>
          {row.evidence_text?<details><summary>识别时保留的摘录</summary><p>{row.evidence_text}</p><small>此摘录不是已确认的原文锚点，须核对原文件及当前准确版本。它不代表关系已成立。</small></details>:<small>原任务没有保留摘录，请先补齐材料证据。</small>}
          <small>{row.submitted_at?`最近提交 ${new Date(row.submitted_at).toLocaleString("zh-CN")}`:"原任务未记录提交时间"}</small></div>
        <a target="_blank" rel="noopener" href={`/admin/theories/relations?review_task=${encodeURIComponent(row.id)}&review_status=all${row.work?`&review_work=${encodeURIComponent(row.work)}`:""}${row.file?`&review_file=${encodeURIComponent(row.file)}`:""}`}>在新页核对原任务 ↗</a>
      </li>)}</ul>
      {!resource.data.count?<p>当前范围没有待核对材料任务。已经确认或不采用的任务保留在原审核历史中。</p>:null}
      {resource.data.count>6?<nav className={shared.pagination} aria-label="材料候选分页"><button type="button" disabled={!resource.data.previous} onClick={()=>setPage(value=>value-1)}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!resource.data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>:null}
      <button type="button" onClick={resource.reload}>刷新审核结果</button>
    </>}
  </section>;
}
