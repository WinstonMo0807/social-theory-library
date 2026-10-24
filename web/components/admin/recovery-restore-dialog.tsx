"use client";

import { useState } from "react";
import { CircleAlert, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./recovery-workspace.module.css";

type Detail=components["schemas"]["RecoveryDetail"];
type Rename=components["schemas"]["RecoveryConfirmInputRequest"]["rename"];
type Props={preview:Detail|null;pending:boolean;message:string;onCancel:()=>void;onConfirm:(rename?:Rename,keepSeparate?:boolean)=>void};

export function RecoveryRestoreDialog(props:Props){
  const {preview,pending,message,onCancel,onConfirm}=props;
  if(preview?.names.count)return <NameConflict key={preview.version} {...props} preview={preview}/>;
  return <ConfirmDialog open={!!preview} title="确认恢复对象" description={preview?.notice||""}
    details={preview?[preview.title,`关联摘要：${preview.dependency_count} 项；其他已删除对象需单独恢复。`,...(preview.storage.state==="checked"?[`已核对 ${preview.storage.total} 份登记文件的存在与大小，不含内容完整性校验。`]:[]),...preview.blockers,...(message?[message]:[])]:[]}
    confirmLabel={pending?"正在恢复…":"确认恢复（保持未发布）"} pending={pending} onCancel={onCancel} onConfirm={()=>onConfirm()}/>;
}

function NameConflict({preview,pending,message,onCancel,onConfirm}:Props&{preview:Detail}){
  const peer=preview.names.count===1?preview.names.results[0]:undefined;
  const existingAllowed=!!peer?.rename?.allowed;
  const [mode,setMode]=useState<"restored"|"existing"|"separate">(preview.rename.allowed?"restored":existingAllowed?"existing":"separate");
  const [sourceName,setSourceName]=useState(preview.rename.suggested_name);
  const [existingName,setExistingName]=useState(peer?.rename?.suggested_name||"");
  const selected=mode==="restored"?preview.rename:peer?.rename;
  const newName=(mode==="restored"?sourceName:existingName).trim();
  const priorName=mode==="restored"?preview.title:peer?.name||"";
  const valid=mode==="separate"||!!selected?.allowed&&!!newName&&newName.length<=selected.max_length&&newName.toLocaleLowerCase()!==priorName.trim().toLocaleLowerCase()&&!/[\r\n\t]/.test(newName);
  function submit(){
    if(pending||!valid)return;
    if(mode==="separate"){onConfirm(undefined,true);return;}
    if(!selected)return;
    onConfirm({target:mode,object_id:mode==="restored"?preview.object_id:peer!.object_id,expected_version:selected.version,new_name:newName});
  }
  return <Dialog open className={styles.conflictDialog} aria-labelledby="recovery-name-title" onRequestClose={()=>{if(!pending)onCancel();}}>
    <form onSubmit={event=>{event.preventDefault();submit();}}>
      <header className={styles.relatedTools}><div><h2 id="recovery-name-title">名称冲突</h2><p>恢复对象：{preview.title}</p></div><button type="button" aria-label="关闭恢复确认" disabled={pending} onClick={onCancel}><X size={17}/></button></header>
      <div className={styles.notice}><CircleAlert size={18}/><p>原名称已被 {preview.names.count} 个管理对象使用。请确认处理方式；各对象的内容、原身份和关联都会保留。</p></div>
      <h3>冲突项</h3><ul className={styles.conflictItems}>{preview.names.results.map(row=><li key={row.object_id}><strong>{row.name}</strong><span>{row.label} · {row.detail}</span></li>)}</ul>
      {preview.names.count>preview.names.results.length?<p className={styles.hint}>这里显示前 {preview.names.results.length} 项。请先关闭确认，通过“比较同名对象”分页核对其余对象。</p>:null}
      <fieldset disabled={pending} className={styles.nameChoices}><legend>处理方式</legend>
        <div><label><input type="radio" name="recovery-name-mode" value="restored" checked={mode==="restored"} disabled={!preview.rename.allowed} onChange={()=>setMode("restored")}/><strong>使用新标题恢复</strong></label>
          {preview.rename.allowed?<label className={styles.newName}><span>恢复对象的新名称</span><input value={sourceName} maxLength={preview.rename.max_length} disabled={mode!=="restored"} onChange={event=>setSourceName(event.target.value)}/></label>:<p>{preview.rename.reason}</p>}</div>
        <div><label><input type="radio" name="recovery-name-mode" value="existing" checked={mode==="existing"} disabled={!existingAllowed} onChange={()=>setMode("existing")}/><strong>替换现有名称，保留现有内容</strong></label>
          {existingAllowed?<><p>恢复对象保留原名称，现有对象仅改为下面的名称，不覆盖、不合并。</p><label className={styles.newName}><span>现有对象的新名称</span><input value={existingName} maxLength={peer!.rename!.max_length} disabled={mode!=="existing"} onChange={event=>setExistingName(event.target.value)}/></label></>:<p>{preview.names.count!==1?"存在多个同名对象，请先比较并逐个处理，或为恢复对象使用新名称。":peer?.rename?.reason||"请从原编辑入口处理此对象的名称。"}</p>}</div>
        <div><label><input type="radio" name="recovery-name-mode" value="separate" checked={mode==="separate"} onChange={()=>setMode("separate")}/><strong>确认为不同对象，保留原名称</strong></label><p>适用于不同作品、版本或身份确实同名的情况。两个对象保持独立。</p></div>
      </fieldset>
      <aside className={styles.notice}><CircleAlert size={17}/><div><strong>操作说明</strong><p>{preview.notice}</p><p>改名与恢复一并保存，任一步失败都不会单独生效。已有编辑草稿会保留；公开内容须先在原入口处理。</p><p>关联 {preview.dependency_count} 项，其他已删除对象仍需单独恢复。</p>{preview.storage.state==="checked"?<p>已核对 {preview.storage.total} 份登记文件的存在与大小，未校验完整内容。</p>:null}</div></aside>
      {message?<p role="alert" className={styles.error}>{message}</p>:null}
      <footer className={styles.relatedTools}><button type="button" disabled={pending} onClick={onCancel}>取消恢复</button><button type="submit" className={styles.primary} disabled={pending||!valid}>{pending?"正在恢复…":"确认恢复（保持未发布）"}</button></footer>
    </form>
  </Dialog>;
}
