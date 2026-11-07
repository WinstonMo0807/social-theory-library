"use client";


import { LoadingState } from "@/components/ui/loading-state";
import styles from "./concept-editor.module.css";
import { useCallback } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { components } from "@/lib/api/generated/schema";

/** The side panel reflects the same draft; it does not keep another editable copy. */
export function KnowledgeNodeSummary({draft,objectType,onEdit}:{draft:object;objectType:string;onEdit:()=>void}){
  const value=draft as {canonical_name_zh?:string;definition?:string;summary?:string;aliases?:{alias:string}[];editorial_details?:{internal_note?:string}};
  return <section className={styles.nodeSummary}><header><h3>{{theory:"理论信息",concept:"概念信息",debate:"争论信息",research_problem:"问题信息"}[objectType]||"条目信息"}</h3><button type="button" onClick={onEdit}>编辑基本信息</button></header><dl><dt>节点类型</dt><dd>{{theory:"理论",concept:"概念",debate:"争论",research_problem:"研究问题"}[objectType]||"知识条目"}</dd><dt>名称</dt><dd>{value.canonical_name_zh||"待填写"}</dd><dt>异名</dt><dd>{value.aliases?.map(row=>row.alias).filter(Boolean).join("、")||"尚未填写"}</dd><dt>解释对象</dt><dd>{value.definition||value.summary||"尚未填写"}</dd><dt>编辑说明</dt><dd>{value.editorial_details?.internal_note||"尚未填写"}</dd></dl></section>;
}

export function KnowledgeRelationSummary({owner,nodeId,onEdit}:{owner:string;nodeId:string;onEdit:()=>void}) {
  type Page=components["schemas"]["NodeRelationPage"];
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Page>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<Page>(`/catalog/admin/theory-system/nodes/${nodeId}/relations/?kind=node`,owner,undefined,load);
  return <section className={styles.nodeSummary}><header><h3>关联关系</h3><button type="button" onClick={onEdit}>＋ 新建关系</button></header>{resource.error?<p role="alert">{resource.error}<button type="button" onClick={resource.reload}>重新读取</button></p>:!resource.data?<LoadingState>正在读取关系…</LoadingState>:<><ul className={styles.relationSummary}>{resource.data.results.slice(0,4).map(row=><li key={row.id}><button type="button" onClick={onEdit}><span>{row.relation_label}</span><strong>{row.source_name} {row.direction==="undirected"?"—":"→"} {row.target_name}</strong><small>{({published:"已确认公开",pending:"待确认",draft:"草稿",rejected:"不采用",archived:"已下线"} as Record<string,string>)[row.status]||row.status}</small></button></li>)}</ul>{resource.data.count?<button type="button" className={styles.summaryLink} onClick={onEdit}>查看全部 {resource.data.count} 项 →</button>:<p>尚未建立关联关系</p>}</>}</section>;
}
