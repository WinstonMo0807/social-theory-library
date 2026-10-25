"use client";

import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { ConfirmDialog } from "./confirm-dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./admin/ocr-runtime-editor.module.css";

type Snapshot=components["schemas"]["ResearchSourceSnapshot"];
type Source=components["schemas"]["ResearchSourceOutput"];
type Input=components["schemas"]["SourceRegistryInputRequest"];
type Probe=components["schemas"]["ResearchSourceProbeResult"];
type Draft={version:string;key:string;enabled:boolean;endpoint:string;alias:string;credential:"keep"|"set"|"delete";secret:string;confirmDelete:boolean};
type Props={revision?:number;sourceKey?:string;onSaved?:()=>void;onBusyChange?:(value:boolean)=>void};
const path="/catalog/admin/research-sources/";
const keyFor=(owner:string)=>`stl-source-save:${owner}`;
const inputFor=(source:Source,data:Snapshot):Draft=>({version:data.configuration_version,key:source.key,enabled:source.enabled,endpoint:source.endpoint_alias,alias:source.credential_alias,credential:"keep",secret:"",confirmDelete:false});
const date=(value:string|null)=>value?new Date(value).toLocaleString("zh-CN"):"尚无记录";

export function ResearchSourceRegistryPanel(props:Props){
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  if(!user)return <p>正在读取当前管理账户…</p>;
  if(!hasAdminCapability(user,"can_view_system_status"))return <p>当前账户不能查看来源配置。</p>;
  return <RegistryEditor key={`${user.id}:${epoch}:${props.sourceKey||"all"}`} owner={String(user.id)} {...props}/>;
}

function RegistryEditor({owner,sourceKey,revision=0,onSaved,onBusyChange}:Props&{owner:string}){
  const aliasListId=useId();
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Snapshot>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Snapshot>(path,owner,undefined,load);
  const [selected,setSelected]=useState(""),[draft,setDraft]=useState<Draft|null>(null),[message,setMessage]=useState("");
  const [pendingVersion,setPendingVersion]=useState(""),[ready,setReady]=useState(false),[recordError,setRecordError]=useState("");
  const [operation,setOperation]=useState(""),[confirm,setConfirm]=useState<"reload"|"fence"|null>(null);
  const lifetime=useRef<AbortController|null>(null),busy=useRef(false);
  useEffect(()=>{const controller=new AbortController();lifetime.current=controller;
    const frame=window.requestAnimationFrame(()=>{try{const value=sessionStorage.getItem(keyFor(owner))||"";if(value&&!/^[a-f0-9]{64}$/.test(value))throw Error("保存记录格式异常，请先确认服务器当前配置。");setPendingVersion(value);setReady(true);}catch(error){setRecordError(error instanceof Error?error.message:"无法读取保存记录。");}});
    return()=>{window.cancelAnimationFrame(frame);controller.abort();};},[owner]);
  const reloadResource=resource.reload;
  useEffect(()=>{if(revision)reloadResource();},[revision,reloadResource]);
  const data=resource.data,source=data?.adapters.find(row=>row.key===(sourceKey||selected||data.adapters[0]?.key));
  const input=draft||(source&&data?inputFor(source,data):null);
  const hasWork=!!draft||!!pendingVersion||!!operation;
  const locked=!ready||!!recordError||!!pendingVersion||!!operation||resource.pending||!data?.permissions.can_edit;
  useUnsavedForm(hasWork,false);
  useEffect(()=>{onBusyChange?.(hasWork);return()=>onBusyChange?.(false);},[hasWork,onBusyChange]);
  function change(values:Partial<Draft>){if(input&&!locked)setDraft({...input,...values,confirmDelete:values.confirmDelete??false});}
  function clearPending(){sessionStorage.removeItem(keyFor(owner));setPendingVersion("");}
  function reload(){setDraft(null);setConfirm(null);setMessage("");resource.reload();}
  async function save(event:FormEvent){
    event.preventDefault();const controller=lifetime.current;
    if(!data||!source||!input||locked||busy.current||!controller||controller.signal.aborted)return;
    const adapter:Input["adapters"][number]={key:source.key as Input["adapters"][number]["key"],enabled:input.enabled};
    if(data.permissions.can_edit_sensitive_aliases){if(source.endpoint_alias_supported)adapter.endpoint_alias=input.endpoint;if(source.credential_alias_supported)adapter.credential_alias=input.alias;}
    const body:Input={expected_version:input.version,adapters:[adapter]};
    if(input.credential!=="keep")body.credential={action:input.credential,source_key:adapter.key,confirm_delete:input.confirmDelete,alias:input.credential==="delete"?source.credential_alias:input.alias,
      ...(input.credential==="set"?{secret:input.secret}:{confirm_delete:input.confirmDelete})};
    busy.current=true;setOperation("save");setMessage("");setDraft({...input,secret:""});
    try{sessionStorage.setItem(keyFor(owner),input.version);setPendingVersion(input.version);
      const result=await resource.mutate(`${input.version}:${source.key}:save`,()=>apiRequest<Snapshot>(path,{method:"PUT",signal:controller.signal,headers:{"X-Editor-Owner":owner},body:JSON.stringify(body)},getServerSessionCredential()));
      if(!result||controller.signal.aborted)return;
      clearPending();setDraft(null);setMessage("来源配置和本次凭据操作已一并保存。已有资料与人工确认内容保留；服务是否可用仍需单独检查。");onSaved?.();
    }catch(error){if(!controller.signal.aborted){if(error instanceof ApiRequestError&&[400,403,409].includes(error.status))clearPending();setMessage(`${error instanceof Error?error.message:"未收到保存结果。"} 凭据输入已清除，其余输入保留。响应未知时请先确认服务器配置。`);}}
    finally{busy.current=false;if(!controller.signal.aborted)setOperation("");}
  }
  async function fence(){
    const expected=pendingVersion||data?.configuration_version,controller=lifetime.current;
    if(!expected||busy.current||!controller||controller.signal.aborted)return;
    busy.current=true;setOperation("fence");
    try{const result=await resource.mutate(`fence:${expected}`,()=>apiRequest<Snapshot>(path,{method:"PATCH",signal:controller.signal,headers:{"X-Editor-Owner":owner},body:JSON.stringify({expected_version:expected})},getServerSessionCredential()));
      if(!result||controller.signal.aborted)return;
      clearPending();setReady(true);setRecordError("");setDraft(null);setConfirm(null);setMessage("已读取当前配置并阻止原版本迟到保存。已经完成的修改保留，密钥原文不会返回。");onSaved?.();
    }catch(error){if(!controller.signal.aborted)setMessage(error instanceof Error?error.message:"暂不能确认服务器配置。");}
    finally{busy.current=false;if(!controller.signal.aborted)setOperation("");}
  }
  async function probe(){
    const controller=lifetime.current;if(!data||!source||locked||draft||busy.current||!controller||controller.signal.aborted)return;
    busy.current=true;setOperation("probe");
    try{const result=await withPrivateOwner(owner,()=>apiRequest<Probe>(path,{method:"POST",signal:controller.signal,headers:{"X-Editor-Owner":owner},body:JSON.stringify({action:"test",source_key:source.key,expected_version:data.configuration_version})},getServerSessionCredential()),controller.signal);
      if(!controller.signal.aborted){setMessage(`${result.functional?"公开样例检查已返回":"当前来源尚不可用"}。${result.detail} 这不代表生产任务或内容质量已通过。`);resource.reload();onSaved?.();}
    }catch(error){if(!controller.signal.aborted)setMessage(`${error instanceof Error?error.message:"未收到检查结果。"} 检查可能仍在服务器继续，请先核对服务记录。`);}
    finally{busy.current=false;if(!controller.signal.aborted)setOperation("");}
  }
  return <section className={styles.editor} aria-label="外部书目来源配置">
    {(resource.error||recordError)?<p role="alert" className={styles.error}>{resource.error||recordError}</p>:null}
    {message?<p role="status" className={styles.notice}>{message}</p>:null}
    {pendingVersion||recordError?<div className={styles.notice}><p>保存结果尚未确认。刷新不会重发，浏览器仅保存原版本指纹，不保存密钥或配置输入。</p><button type="button" disabled={!data||!!operation||resource.pending} onClick={()=>setConfirm("fence")}>确认服务器当前配置</button></div>:null}
    {!data?<p>{resource.loading?"正在读取原来源注册表…":"尚未取得服务器配置。"}<button type="button" onClick={resource.reload}>重新读取</button></p>:<>
      {!sourceKey?<><h2>外部书目来源</h2><p>已启用 {data.summary.enabled} / {data.summary.total} 项，已配置 {data.summary.configured} 项。配置齐全不表示当前服务已检查。</p><label><span>选择来源</span><select disabled={hasWork||!!recordError} value={source?.key||""} onChange={event=>{setSelected(event.target.value);setMessage("");}}>{data.adapters.map(row=><option key={row.key} value={row.key}>{row.label} · {row.category}</option>)}</select></label></>:null}
      {!source||!input?<p role="alert">原来源已不在当前注册表中。请返回服务列表重新选择，未自动编辑其他来源。</p>:<form onSubmit={save} aria-label={`${source.label} 配置`}>
        <h3>{source.label}</h3><p>{source.purpose}</p><p className={styles.hint}>{source.usage_policy}</p>
        {draft&&draft.version!==data.configuration_version?<p role="alert" className={styles.error}>服务器配置或凭据已变化。当前输入保留，请重新读取后再保存，旧输入不会覆盖新配置。</p>:null}
        <fieldset disabled={locked}>
          <label className={styles.consent}><input type="checkbox" checked={input.credential==="delete"?false:input.enabled} disabled={input.credential==="delete"} onChange={event=>change({enabled:event.target.checked})}/><span>启用此来源。保存不触发检索，也不会发送馆藏或私人材料。</span></label>
          {data.permissions.can_edit_sensitive_aliases?<>
            {source.endpoint_alias_supported?<label><span>服务器地址别名</span><input maxLength={64} pattern="[a-z][a-z0-9_-]{0,63}" value={input.endpoint} onChange={event=>change({endpoint:event.target.value})} autoComplete="off" spellCheck={false}/><small>只填写服务器已配置的别名。留空会解除别名绑定，沿用服务器默认地址；实际地址不会显示。</small></label>:null}
            {source.credential_alias_supported?<>
              <label><span>凭据操作</span><select value={input.credential} onChange={event=>change({credential:event.target.value as Draft["credential"],secret:"",alias:event.target.value==="delete"?source.credential_alias:input.alias||`source-${source.key.replaceAll("_","-")}`})}><option value="keep">保留已保存凭据</option><option value="set">加密保存或更新凭据</option><option value="delete" disabled={!source.credential_managed_here}>删除此来源凭据并停用</option></select></label>
              {input.credential!=="delete"?<label><span>凭据别名</span><input list={aliasListId} required={input.credential==="set"} maxLength={64} pattern="[a-z][a-z0-9_-]{0,63}" value={input.alias} onChange={event=>change({alias:event.target.value})} autoComplete="off" spellCheck={false}/><datalist id={aliasListId}>{source.credential_alias_options.map(alias=><option key={alias} value={alias}/>)}</datalist>{source.more_credential_aliases?<small>建议只展示前50个已保存别名，其余可输入完整别名。</small>:null}<small>可选择此来源已加密保存的别名，包括旧入口保存后尚未绑定的凭据。别名不含密钥。留空解除当前绑定，仍可能沿用服务器环境凭据；停用来源可阻止继续使用。</small></label>:null}
              {input.credential==="set"?<label><span>新凭据</span><input type="password" required maxLength={16384} autoComplete="new-password" value={input.secret} onChange={event=>change({secret:event.target.value})}/><small>与来源绑定在同一事务保存；提交后清除输入，不回显原值，不保存到浏览器恢复记录。</small></label>:null}
              {input.credential==="delete"?<label className={styles.consent}><input type="checkbox" required checked={input.confirmDelete} onChange={event=>change({confirmDelete:event.target.checked})}/><span>确认删除此来源已加密保存的凭据并停用来源。其他来源仍引用的凭据不会删除，服务器环境凭据保持原样。</span></label>:null}
            </>:null}
          </>:<p>当前账户可调整非敏感启用状态，地址别名和凭据由馆长维护。</p>}
        </fieldset>
        <dl><div><dt>影响功能</dt><dd>{source.affected_features.join("、")}</dd></div><div><dt>配置要求</dt><dd>{source.configuration_requirements.join("、")||"无需额外配置"}</dd></div><div><dt>服务地址</dt><dd>{source.endpoint_configured?"已配置":"尚未配置或不需要独立地址"}</dd></div><div><dt>服务凭据</dt><dd>{source.credential_configured?"已在服务器配置":source.credential_alias_supported?"尚未配置":"无需凭据"}</dd></div><div><dt>凭据更新时间</dt><dd>{date(source.credential_updated_at)}</dd></div><div><dt>凭据检查时间</dt><dd>{date(source.credential_last_tested_at)}</dd></div><div><dt>最近来源成功</dt><dd>{date(source.last_success_at)}</dd></div><div><dt>最近来源失败</dt><dd>{date(source.last_failure_at)}</dd></div><div><dt>元数据格式</dt><dd>{source.metadata_formats.join("、")||"不适用"}</dd></div></dl>
        <div className={styles.actions}><button type="submit" className={styles.primary} disabled={locked||!draft||draft.version!==data.configuration_version}>{operation==="save"?"正在保存…":"保存来源配置"}</button><button type="button" disabled={locked} onClick={()=>draft?setConfirm("reload"):reload()}>重新读取</button>{data.permissions.can_test?<button type="button" disabled={locked||!!draft} onClick={()=>void probe()}>{operation==="probe"?"正在检查…":"检查公开样例"}</button>:null}</div>
      </form>}
    </>}
    <ConfirmDialog open={confirm==="reload"} title="重新读取来源配置" description="未保存的配置输入将被服务器当前值替换。密钥原文不会返回。" confirmLabel="重新读取" onCancel={()=>setConfirm(null)} onConfirm={reload}/>
    <ConfirmDialog open={confirm==="fence"} title="确认当前来源配置" description="阻止原版本尚未执行的保存，再读取服务器当前配置。已完成的凭据或来源修改不会撤销。" confirmLabel="确认并读取" pending={operation==="fence"} onCancel={()=>setConfirm(null)} onConfirm={fence}/>
  </section>;
}
