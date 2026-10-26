"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import { ApiRequestError, apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import type { AuthorityDetail } from "@/lib/api/person-authority.client";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { asArray, asRecord, asString, type WorkflowPayload } from "../workflow/workflow-types";
import { contributorRoleOptions } from "../workflow/contributor-state";
import styles from "./person-authority.module.css";

type Edition = AuthorityDetail["impact"]["editions"][number];


export function PersonContributions({ detail, owner, active, onActive, onSaved, disabled }: {
  detail: AuthorityDetail; owner: string; active: string; onActive: (id: string) => void; onSaved?: () => void; disabled: boolean;
}) {
  return <>{detail.impact.editions.length ? <div className={styles.contributionTable}>
    <header><span>作品名称</span><span>出版信息</span><span>在本文献中的角色</span><span>关联状态</span><span>操作</span></header>
    {detail.impact.editions.map(row => <article key={row.edition_id}>
      <div className={styles.contributionRow}>
        <Link className={styles.contributionTitle} href={row.editor_url}>{row.cover_url ? <img src={normalizePublicResourceUrl(row.cover_url)} alt="" /> : <BookOpen size={26} strokeWidth={1} />}<strong>{row.title}</strong></Link>
        <span className={styles.contributionPublication}>{row.edition_label}</span>
        <button className={styles.roleSelect} type="button" disabled={disabled || Boolean(active && active !== row.edition_id)} onClick={() => onActive(row.edition_id)} aria-expanded={active === row.edition_id}>{row.roles.map(role => role.role_label).join("、") || "查看职责"}<ChevronDown size={12} /></button>
        <span className={styles.contributionState} title={row.publication.detail} data-public-state={row.publication.public_state}><i />{{published:"当前公开",publishing:"正在发布",withdrawn:"已撤回",unpublished:"尚未公开"}[row.publication.public_state||""]||row.publication.detail}</span><Link className={styles.contributionView} href={row.editor_url}><span>查看</span><ChevronRight size={13} /></Link>
      </div>
      {active === row.edition_id ? <RoleEditor row={row} owner={owner} personId={detail.id} onClose={() => onActive("")} onSaved={() => { onActive(""); onSaved?.(); }} /> : null}
    </article>)}</div> : <p className={styles.muted}>还没有关联作品。可从<Link href="/admin/library">馆藏目录</Link>进入相应版本关联贡献者。</p>}
    {!detail.impact_complete ? <p role="alert">关联版本超过500项，此处未完整显示，当前不能保存正式变化。</p> : null}
    {disabled && !active ? <p className={styles.muted}>请先保存或取消当前人物资料的修改，再编辑作品职责。</p> : null}
    {detail.scholar_id ? <Link href={`/admin/scholars/${detail.scholar_id}`}>编辑关联学者页与资料 →</Link> : <p className={styles.muted}>没有独立学者页。<Link href={`/admin/scholars/new?person=${detail.id}`}>从当前人物建立学者页草稿 →</Link></p>}
  </>;
}

function RoleEditor({ row, owner, personId, onClose, onSaved }: { row: Edition; owner: string; personId: string; onClose: () => void; onSaved: () => void }) {
  const endpoint = `/catalog/admin/library/works/${row.work_id}/`, recoveryKey = `stl-workspace-save:${owner}:maintenance:${row.work_id}:${row.edition_id}`;
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<WorkflowPayload>(path, {signal,cache:"no-store",headers:{"X-Editor-Owner":owner}}, getServerSessionCredential(), false), [owner]);
  const resource = usePersistentWorkspace<WorkflowPayload>(`${endpoint}?edition=${row.edition_id}`, owner, undefined, load);
  const [changes,setChanges]=useState<Record<number,string>>({}),[priorRequest,setPriorRequest]=useState(false),[ready,setReady]=useState(false),[uncertain,setUncertain]=useState(false);
  useEffect(() => { setPriorRequest(Boolean(sessionStorage.getItem(recoveryKey))); setReady(true); }, [recoveryKey]);
  useUnsavedForm(changes, {});
  const payload=resource.data, items=asArray(asRecord(payload?.data.contributors).items).map(asRecord);
  const mine=items.map((item,index)=>({item,index})).filter(({item})=>item.person_id===personId);
  const changed=Object.keys(changes).length>0, blocked=!ready||priorRequest||resource.pending||resource.conflict||uncertain||!payload?.permissions.can_edit;
  async function save() {
    if (!payload || !changed || priorRequest || resource.conflict || resource.pending || !payload.permissions.can_edit) return;
    const next=items.map((item,index)=>Object.hasOwn(changes,index)?{...item,role:changes[index]}:item);
    const body={edition_id:row.edition_id,edit_version:payload.editing?.edit_version,sections:{contributors:{...asRecord(payload.data.contributors),items:next}},confirm_sections:[],suggestions:[]};
    try {
      const result=await resource.mutate(JSON.stringify(body), async (_current, requestId) => {
        sessionStorage.setItem(recoveryKey,JSON.stringify({work_id:row.work_id,edition_id:row.edition_id,request_id:requestId}));
        try {
          const updated=await apiRequest<WorkflowPayload>(`${endpoint}edits/`,{method:"POST",body:JSON.stringify({...body,request_id:requestId}),signal:AbortSignal.timeout(60000),headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false);
          sessionStorage.removeItem(recoveryKey); return updated;
        } catch (error) {
          if (error instanceof ApiRequestError && !(error instanceof PrivateOwnerVerificationError) && [400,401,403,404,409].includes(error.status)) sessionStorage.removeItem(recoveryKey);
          throw error;
        }
      });
      if (result) { setChanges({});setUncertain(false);onSaved(); }
    } catch (error) { setUncertain(!(error instanceof ApiRequestError) || error instanceof PrivateOwnerVerificationError || ![400,401,403,404,409].includes(error.status)); }
  }
  return <div className={styles.roleEditor}>
    <p>修改保存到此版本的书目草稿。其他贡献者、顺序与章节责任范围保留，正式发布仍在原书目页面确认。</p>
    {priorRequest ? <p role="alert">此版本有尚待核对的保存请求。请先<Link href={row.editor_url}>打开原书目核对请求</Link>，再继续修改。</p> : resource.loading ? <p role="status">正在读取此版本的当前职责…</p> : payload ? <>
      {!payload.permissions.can_edit ? <p>当前账户没有书目编辑权限，可查看原关联。</p> : null}
      {mine.length ? mine.map(({item,index})=><label key={index}>{asString(item.display_name)}<select disabled={blocked} value={changes[index]||asString(item.role)} onChange={event=>{const role=event.target.value;setChanges(current=>{const next={...current};if(role===item.role)delete next[index];else next[index]=role;return next;});}}>{contributorRoleOptions.map(({value,label})=><option key={value} value={value} disabled={items.some((other,at)=>at!==index&&other.person_id===personId&&(changes[at]||other.role)===value)}>{label}</option>)}</select></label>) : <p>当前草稿已没有此人物关联，请从原书目核对，不能覆盖其他编辑。</p>}
    </> : null}
    {resource.error ? <p role="alert">{resource.error}{resource.conflict ? " 请关闭后重新读取并核对。" : uncertain ? " 输入已保留，可重试同一次保存或在原书目核对。" : ""}</p> : null}
    <div className={styles.actions}><button type="button" disabled={resource.pending} onClick={()=>{if(changed&&!uncertain&&!window.confirm("放弃尚未保存的职责修改吗？"))return;onClose();}}>{uncertain?"关闭并保留原请求":"取消编辑"}</button><button type="button" className={styles.primary} disabled={!changed||!payload?.permissions.can_edit||resource.pending||priorRequest||resource.conflict} onClick={()=>void save()}>{resource.pending?"正在保存…":uncertain?"重试同一次保存":"保存职责草稿"}</button></div>
  </div>;
}
