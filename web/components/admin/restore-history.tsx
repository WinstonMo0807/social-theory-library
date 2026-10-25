"use client";
import { useCallback, useState } from "react";
import { History } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { components } from "@/lib/api/generated/schema";
import styles from "./storage-workspace.module.css";

type Page=components["schemas"]["RestoreHistoryPage"];
export function RestoreHistory({owner,backupId,onExport}:{owner:string;backupId?:string;onExport:(value:unknown,name:string)=>void}) {
  const [cursors,setCursors]=useState([""]);
  const params=new URLSearchParams();
  if(backupId)params.set("backup_id",backupId);
  if(cursors.at(-1))params.set("cursor",cursors.at(-1)!);
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Page>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Page>(`/distribution/storage/rehearsals/?${params}`,owner,undefined,load),data=resource.data;
  function latest(){setCursors([""]);resource.reload();}
  return <section className={styles.panel} aria-label={backupId?"此归档的恢复演练历史":"恢复演练历史"}>
    <header><h2>恢复演练记录</h2><div className={styles.actions}><button type="button" onClick={latest}>读取最新目录</button>{data?<button type="button" onClick={()=>onExport({scope:`第 ${cursors.length} 页签名文件窗口`,backup_id:backupId||null,...data},"stl-restore-history-page.json")}>导出本页</button>:null}</div></header>
    {resource.error?<p role="alert">{resource.error}<button type="button" onClick={resource.reload}>重新读取此页</button><button type="button" onClick={latest}>返回最新记录</button></p>:null}
    {resource.loading?<p role="status">正在核对本页签名记录…</p>:null}
    {data?<>
      <p className={styles.hint}>{data.notice}</p>
      {data.source_status==="unavailable"?<p role="alert" className={styles.alert}>记录目录不可读。请核对备份卷挂载和权限后重试；未将此状态视为空历史。</p>:null}
      {data.results.length?<div className={styles.tableScroll}><table><thead><tr><th>演练时间</th><th>归档身份</th><th>已完成范围</th></tr></thead><tbody>{data.results.map(row=><tr key={row.id}><td><time dateTime={row.checked_at}>{new Date(row.checked_at).toLocaleString("zh-CN")}</time></td><td className={styles.checksum}>{row.archive_sha256}</td><td>{row.detail}</td></tr>)}</tbody></table></div>:data.source_status!=="unavailable"?<div className={styles.empty}><History size={27}/><strong>{data.candidate_count?"本页尚无匹配的有效报告":"尚无签名报告文件"}</strong><p>{data.next_cursor?"可继续翻页查看更早记录。":backupId?"此窗口未找到与当前归档身份匹配的有效报告。":"只有原隔离恢复命令成功保存的签名报告会显示在这里。"}</p></div>:null}
      {data.source_status==="available"?<p className={styles.hint}>读取截止 {new Date(data.as_of).toLocaleString("zh-CN")} · 目录内 {data.candidate_count} 份候选文件，本页核对 {data.inspected_count} 份，显示 {data.results.length} 份有效报告。{backupId?`另有 ${data.filtered_count} 份属于其他归档。`:""}文件目录可能变化，以上数量不代表整站恢复已通过。</p>:null}
      {data.unverified_count||data.directory_errors?<p role="alert" className={styles.hint}>本页有 {data.unverified_count} 份文件未通过签名、身份或完整读取；目录另有 {data.directory_errors} 项读取失败。未核实文件未计入成功记录。</p>:null}
    </>:null}
    <div className={styles.pagination}><button type="button" disabled={cursors.length<=1||resource.loading} onClick={()=>setCursors(value=>value.slice(0,-1))}>上一页</button><span>第 {cursors.length} 页 · 每页最多核对 20 份文件</span><button type="button" disabled={!data?.next_cursor||resource.loading||data.source_status!=="available"} onClick={()=>{if(data?.next_cursor)setCursors(value=>[...value,data.next_cursor]);}}>更早记录</button></div>
  </section>;
}
