"use client";

import styles from "./concept-editor.module.css";

/** The side panel reflects the same draft; it does not keep another editable copy. */
export function KnowledgeNodeSummary({draft,objectType,onEdit}:{draft:object;objectType:string;onEdit:()=>void}){
  const value=draft as {canonical_name_zh?:string;definition?:string;summary?:string;aliases?:{alias:string}[];editorial_details?:{internal_note?:string}};
  return <section className={styles.nodeSummary}><header><h3>{{theory:"理论信息",concept:"概念信息",debate:"争论信息",research_problem:"问题信息"}[objectType]||"条目信息"}</h3><button type="button" onClick={onEdit}>编辑基本信息</button></header><dl><dt>节点类型</dt><dd>{{theory:"理论",concept:"概念",debate:"争论",research_problem:"研究问题"}[objectType]||"知识条目"}</dd><dt>名称</dt><dd>{value.canonical_name_zh||"待填写"}</dd><dt>异名</dt><dd>{value.aliases?.map(row=>row.alias).filter(Boolean).join("、")||"尚未填写"}</dd><dt>解释对象</dt><dd>{value.definition||value.summary||"尚未填写"}</dd><dt>编辑说明</dt><dd>{value.editorial_details?.internal_note||"尚未填写"}</dd></dl></section>;
}
