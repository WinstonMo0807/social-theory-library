"use client";
import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { workFilesPath } from "@/lib/api/work-files.client";
import type { WorkFilesState } from "@/lib/api/work-files.types";
import { WorkFilePreview } from "../library/work-file-preview";
import type { MaterialEvidence } from "./material-assistant";
import styles from "./material-assistant.module.css";

const uuid=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value)?value:"";
export function MaterialSourceRecord({evidence}:{evidence?:MaterialEvidence}){
  const user=useAdminSession(),locator=evidence?.locator;
  const workId=uuid(locator?.work_id),editionId=uuid(locator?.edition_id),assetId=uuid(locator?.asset_id);
  if(!workId||!user)return null;
  if(assetId&&!editionId)return <p>此来源未记录明确出版版本，不能自动选择原文文件，请从馆藏记录核对。</p>;
  return <Record key={`${user.id}:${workId}:${editionId}:${assetId}`} owner={String(user.id)} workId={workId} editionId={editionId} assetId={assetId} page={locator?.page}/>;
}
function Record({owner,workId,editionId,assetId,page}:{owner:string;workId:string;editionId:string;assetId:string;page?:number}){
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<WorkFilesState>(path,{signal,headers:{"X-Editor-Owner":owner},cache:"no-store"},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<WorkFilesState>(workFilesPath(workId,editionId)+(assetId?`&asset=${assetId}`:""),owner,undefined,load);
  const [preview,setPreview]=useState(false);
  const data=resource.data?.work.id===workId&&(!editionId||resource.data.selected_edition_id===editionId)?resource.data:null;
  const file=data?.inspected_file?.id===assetId?data.inspected_file:null;
  const edition=data?.editions.find(row=>row.id===data.selected_edition_id);
  return <section className={styles.relatedRecord}><h3>相关书目记录</h3>{resource.error?<p role="alert">{resource.error}<button type="button" onClick={resource.reload}>重新读取书目</button></p>:null}{!data?<p role="status">{resource.loading?"正在读取明确关联的馆藏记录…":"尚未取得此来源书目。"}</p>:<><div className={styles.recordIdentity}>{data.work.cover_url?<img src={normalizePublicResourceUrl(data.work.cover_url)} alt=""/>:null}<div><strong>{data.work.title}</strong><p>{data.work.authors.join("、")||"责任者尚待核对"}</p><p>{edition?.label||"出版信息尚待核对"}</p></div></div>{!editionId?<p>来源未指定出版版本，下方为当前馆内记录，请核对具体版次。</p>:null}<a href={`/admin/library/works/${workId}${editionId?`?edition=${editionId}`:""}`} target="_blank" rel="noreferrer">在馆藏中核对 ↗</a>{file?.preview_url?<button type="button" onClick={()=>setPreview(true)}>原位查看依据文件{page?` · PDF 第 ${page} 页`:""}</button>:assetId?<p>原依据文件当前没有可用的分页预览，不会改用另一份文件替代。</p>:<p>此来源未记录具体原文件，可从馆藏记录进一步核对。</p>}{preview&&file?<WorkFilePreview file={file} ownerId={owner} initialPage={page} returnLabel="返回材料助手" onClose={()=>setPreview(false)}/>:null}</>}
  </section>;
}
