"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { ConfirmDialog } from "../confirm-dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./ocr-runtime-editor.module.css";

type Snapshot=components["schemas"]["AIRuntimeSnapshot"];
type Profile=components["schemas"]["AIRuntimeProfileOutput"];
type Input=components["schemas"]["AIRuntimeProfileDocumentRequest"];
type Draft={document:Snapshot;profile:Profile;activeKey:string;credential:"keep"|"set"|"delete";secret:string;endpoint:string;confirmDelete:boolean};
type Props={profileKey?:string;onSaved?:()=>void;onBusyChange?:(value:boolean)=>void};
const path="/reading/admin/ai-runtime-profiles/";
const keyFor=(owner:string)=>`stl-ai-profile-save:${owner}`;
const labels:Record<string,string>={private_research:"私人研究 API",metadata_extraction:"元数据提取",library_qa:"STL 智能助手",field_enrichment_optional:"联网补全判断",entity_reasoning:"实体推理",claim_extraction:"观点提取",claim_attribution:"观点归属",claim_stance:"观点立场",rerank:"结果重排",theory_reasoning:"理论推理",knowledge_relation_reasoning:"知识关系推理",debate_discovery:"争鸣发现",reading_path_generation:"阅读路径生成",curation_reasoning:"内容编排建议"};
const draftFor=(data:Snapshot,profile:Profile):Draft=>({document:data,profile,activeKey:data.active[profile.capability],credential:"keep",secret:"",endpoint:"",confirmDelete:false});
function profileInput(row:Profile,owner:boolean):Input["profiles"][number]{
  return {key:row.key,capability:row.capability,provider:row.provider,model:row.model,enabled:row.enabled,temperature:row.temperature,max_output_tokens:row.max_output_tokens,
    timeout_seconds:row.timeout_seconds,max_input_chars:row.max_input_chars,retrieval_profile:row.retrieval_profile,answer_behavior:row.answer_behavior,
    fallback_profile_key:row.fallback_profile_key||"",reasoning:row.reasoning||{},...(owner?{endpoint_alias:row.endpoint_alias,credential_alias:row.credential_alias}:{})};
}

export function AIRuntimeEditor(props:Props){
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  if(!user)return <LoadingState>正在读取当前管理账户…</LoadingState>;
  if(!hasAdminCapability(user,"can_manage_ai"))return <p>当前账户不能管理模型配置。</p>;
  return <RuntimeEditor key={`${user.id}:${epoch}:${props.profileKey||"all"}`} owner={String(user.id)} {...props}/>;
}

function RuntimeEditor({owner,profileKey,onSaved,onBusyChange}:Props&{owner:string}){
  const aliasListId=useId();
  const [secure,setSecure]=useState(false);
  useEffect(()=>setSecure(window.location.protocol==="https:"),[]);
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Snapshot>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Snapshot>(path,owner,undefined,load);
  const [selected,setSelected]=useState(""),[draft,setDraft]=useState<Draft|null>(null),[message,setMessage]=useState("");
  const [pendingVersion,setPendingVersion]=useState(""),[ready,setReady]=useState(false),[recordError,setRecordError]=useState("");
  const [operation,setOperation]=useState(""),[confirm,setConfirm]=useState<"reload"|"fence"|null>(null);
  const lifetime=useRef<AbortController|null>(null),busy=useRef(false);
  useEffect(()=>{const controller=new AbortController();lifetime.current=controller;
    const frame=window.requestAnimationFrame(()=>{try{const value=sessionStorage.getItem(keyFor(owner))||"";if(value&&!/^[a-f0-9]{64}$/.test(value))throw Error("保存记录格式异常，请先确认服务器当前配置。");setPendingVersion(value);setReady(true);}catch(error){setRecordError(error instanceof Error?error.message:"无法读取保存记录。");}});
    return()=>{window.cancelAnimationFrame(frame);controller.abort();};},[owner]);
  const data=resource.data,source=data?.profiles.find(row=>row.key===(selected||profileKey||data.profiles[0]?.key));
  const input=draft||(source&&data?draftFor(data,source):null),profile=input?.profile;
  const reasoning=profile?.reasoning&&typeof profile.reasoning==="object"?profile.reasoning as Record<string,unknown>:{};
  const hasWork=!!draft||!!pendingVersion||!!operation;
  const locked=!ready||!!recordError||!!pendingVersion||!!operation||resource.pending||!data?.permissions.can_edit_profiles;
  useUnsavedForm(hasWork,false);
  useEffect(()=>{onBusyChange?.(hasWork);return()=>onBusyChange?.(false);},[hasWork,onBusyChange]);
  function change(values:Partial<Profile>){if(input&&!locked)setDraft({...input,profile:{...input.profile,...values},confirmDelete:false});}
  function changeDraft(values:Partial<Draft>){if(input&&!locked)setDraft({...input,...values});}
  function clearPending(){sessionStorage.removeItem(keyFor(owner));setPendingVersion("");}
  function reload(){setDraft(null);setConfirm(null);setMessage("");resource.reload();}
  async function save(event:FormEvent){
    event.preventDefault();const controller=lifetime.current;
    if(!data||!source||!input||!profile||locked||busy.current||!controller||controller.signal.aborted)return;
    const base=input.document,version=base.configuration_version;
    const body:Input={expected_version:version,active:{...base.active,[profile.capability]:input.activeKey},
      profiles:base.profiles.map(row=>profileInput(row.key===profile.key?profile:row,data.permissions.can_edit_sensitive_aliases))};
    if(input.endpoint.trim())body.endpoint={profile_key:profile.key,base_url:input.endpoint.trim()};
    if(input.credential!=="keep")body.credential={action:input.credential,profile_key:profile.key,alias:profile.credential_alias,confirm_delete:input.confirmDelete,...(input.credential==="set"?{secret:input.secret}:{})};
    busy.current=true;setOperation("save");setMessage("");setDraft({...input,secret:"",endpoint:""});
    try{sessionStorage.setItem(keyFor(owner),version);setPendingVersion(version);
      const result=await resource.mutate(`${version}:${profile.key}:save`,()=>apiRequest<Snapshot>(path,{method:"PUT",signal:controller.signal,headers:{"X-Editor-Owner":owner},body:JSON.stringify(body)},getServerSessionCredential()));
      if(!result||controller.signal.aborted)return;
      clearPending();setDraft(null);setMessage("配置已保存，下次任务生效。正在运行的任务不受影响。");onSaved?.();
    }catch(error){if(!controller.signal.aborted){if(error instanceof ApiRequestError&&[400,403,409].includes(error.status))clearPending();setMessage(`${error instanceof Error?error.message:"未收到保存结果。"} 密钥输入已清除，其余输入保留。结果未知时请先确认服务器配置。`);}}
    finally{busy.current=false;if(!controller.signal.aborted)setOperation("");}
  }
  async function fence(){
    const expected=pendingVersion||data?.configuration_version,controller=lifetime.current;
    if(!expected||busy.current||!controller||controller.signal.aborted)return;
    busy.current=true;setOperation("fence");
    try{const result=await resource.mutate(`fence:${expected}`,()=>apiRequest<Snapshot>(path,{method:"PATCH",signal:controller.signal,headers:{"X-Editor-Owner":owner},body:JSON.stringify({expected_version:expected})},getServerSessionCredential()));
      if(!result||controller.signal.aborted)return;
      clearPending();setReady(true);setRecordError("");setDraft(null);setConfirm(null);setMessage("已读取当前配置并阻止原版本迟到保存；已经完成的修改保留，密钥原文不会返回。");onSaved?.();
    }catch(error){if(!controller.signal.aborted)setMessage(error instanceof Error?error.message:"暂不能确认服务器配置。");}
    finally{busy.current=false;if(!controller.signal.aborted)setOperation("");}
  }
  return <div className={styles.editor}>
    <p>管理员设置书库使用的模型。私人研究与 STL 智能助手分别配置，读者看不到这里的接口地址和密钥。</p>
    {resource.error?<p role="alert" className={styles.error}>{resource.error}</p>:null}
    {recordError?<p role="alert" className={styles.error}>{recordError}</p>:null}
    {message?<p role="status" className={styles.notice}>{message}</p>:null}
    {pendingVersion||recordError?<div className={styles.notice}><p>上次保存尚未确认，不能直接再次发送。先读取当前配置并隔离迟到请求。</p><button type="button" disabled={!data||!!operation} onClick={()=>setConfirm("fence")}>确认服务器当前配置</button></div>:null}
    {!data?<p>{resource.loading?"正在读取模型配置…":"配置尚不可读，未开放保存。"}<button type="button" disabled={!!operation} onClick={resource.reload}>重新读取</button></p>:<>
      <label><span>选择用途</span><select value={source?.key||""} disabled={hasWork} onChange={event=>{setSelected(event.target.value);setMessage("");}}>{!source?<option value="">原配置档已变化，请选择当前配置</option>:null}{data.profiles.map(row=><option key={row.key} value={row.key}>{labels[row.capability]||row.capability} · {row.key}{data.active[row.capability]===row.key?" · 当前选用":""}</option>)}</select></label>
      {input&&profile?<form onSubmit={save}>
        {input.document.configuration_version!==data.configuration_version?<p role="alert" className={styles.notice}>服务器配置已变化，输入仍保留。请重新读取后核对，旧版本不能覆盖新值。</p>:null}
        <fieldset disabled={locked}>
          <legend>{labels[profile.capability]||profile.capability}</legend>
          <label className={styles.consent}><input type="checkbox" checked={profile.enabled} disabled={input.credential==="delete"} onChange={event=>change({enabled:event.target.checked})}/><span>启用此配置</span></label>
          <label><span>服务类型</span><select value={profile.provider} onChange={event=>change({provider:event.target.value as Profile["provider"]})}><option value="none">未配置</option><option value="ollama">Ollama</option><option value="vllm">vLLM</option><option value="openai_compatible">DeepSeek / OpenAI 兼容 API</option></select></label>
          <label><span>模型名称</span><input maxLength={300} required={profile.enabled} value={profile.model} onChange={event=>change({model:event.target.value})} autoComplete="off" spellCheck={false}/></label>
          {profile.capability==="private_research"?<p>用于追问、原文比较、引文关系和阅读计划。仅发送当前读者在该研究中授权的材料；结果保存在本人账号。</p>:null}
          {profile.provider==="openai_compatible"?<label><span>结构化输出</span><select value={String(reasoning.json_mode||"json_schema")} onChange={event=>change({reasoning:{...reasoning,json_mode:event.target.value}})}><option value="json_object">JSON 对象（DeepSeek）</option><option value="json_schema">JSON Schema</option></select></label>:null}
          <label><span>该能力当前选用</span><select value={input.activeKey} onChange={event=>changeDraft({activeKey:event.target.value})}>{input.document.profiles.filter(row=>row.capability===profile.capability).map(row=><option key={row.key} value={row.key}>{row.key}</option>)}</select></label>
          <label><span>同用途备用配置</span><select value={profile.fallback_profile_key||""} onChange={event=>change({fallback_profile_key:event.target.value})}><option value="">不使用备用配置</option>{input.document.profiles.filter(row=>row.capability===profile.capability&&row.key!==profile.key).map(row=><option key={row.key} value={row.key}>{row.key}</option>)}</select><small>只允许同一用途的一层备用配置。当前书库问答与观点提取在符合各自失败条件时使用备用配置，其他处理器不会自动切换；不会以模型输出替代缺失的原文证据。</small></label>
          <label><span>最大输入字符</span><input type="number" min={1000} max={100000} step={1} required value={profile.max_input_chars} onChange={event=>change({max_input_chars:Number(event.target.value)})}/></label>
          <label><span>最大输出 Token</span><input type="number" min={128} max={8192} step={1} required value={profile.max_output_tokens} onChange={event=>change({max_output_tokens:Number(event.target.value)})}/></label>
          <label><span>超时秒数</span><input type="number" min={3} max={600} step={1} required value={profile.timeout_seconds} onChange={event=>change({timeout_seconds:Number(event.target.value)})}/></label>
          <label><span>生成温度</span><input type="number" min={0} max={2} step="any" required value={profile.temperature} onChange={event=>change({temperature:Number(event.target.value)})}/></label>
          {data.permissions.can_edit_sensitive_aliases?<>
            {profile.provider==="openai_compatible"?<label><span>API Base URL</span><input type="url" maxLength={2000} value={input.endpoint} onChange={event=>changeDraft({endpoint:event.target.value})} placeholder={source?.environment.endpoint_configured?"已配置；留空保留原地址":"https://你的中转站/v1"} autoComplete="off" spellCheck={false}/><small>支持以 /v1 结尾的地址。保存后不回显地址，不自动调用模型。</small></label>:null}
            <label><span>服务器地址别名</span><input required maxLength={64} pattern="[a-z][a-z0-9_-]{0,63}" value={profile.endpoint_alias} onChange={event=>change({endpoint_alias:event.target.value})} autoComplete="off" spellCheck={false}/><small>填写 Base URL 后自动绑定；留空时沿用此别名，地址不回显。</small></label>
            <label><span>凭据操作</span><select value={input.credential} onChange={event=>changeDraft({credential:event.target.value as Draft["credential"],secret:"",confirmDelete:false,profile:{...profile,enabled:event.target.value==="delete"?false:profile.enabled,credential_alias:event.target.value==="delete"?source!.credential_alias:event.target.value==="set"&&profile.credential_alias==="default"?`ai-${profile.key}`.slice(0,64):profile.credential_alias}})}><option value="keep">保留已保存凭据</option><option value="set" disabled={!secure}>加密保存或更新密钥</option><option value="delete" disabled={!source?.credential_managed_here}>删除此凭据并停用配置</option></select></label>
            {input.credential!=="delete"?<label><span>凭据别名</span><input list={aliasListId} required maxLength={64} pattern="[a-z][a-z0-9_-]{0,63}" value={profile.credential_alias} onChange={event=>change({credential_alias:event.target.value})} autoComplete="off" spellCheck={false}/><datalist id={aliasListId}>{data.credential_alias_options.map(alias=><option key={alias} value={alias}/>)}</datalist><small>可选择既有加密凭据。环境管理的别名优先使用部署值，需另取新别名才能在此保存；共享凭据不能从单个配置覆盖或删除。</small>{data.more_credential_aliases?<small>建议显示前50个已保存别名，其余可输入完整别名。</small>:null}</label>:null}
            {!secure?<p>当前为 HTTP 预览。请在 HTTPS 管理页录入密钥，或通过 SSH 配置服务器环境。</p>:null}
            {input.credential==="set"&&secure?<label><span>API Key</span><input type="password" required maxLength={16384} autoComplete="new-password" value={input.secret} onChange={event=>changeDraft({secret:event.target.value})}/><small>凭据和配置在同一次保存中生效。提交后清除输入，不在浏览器恢复记录中存储密钥。</small></label>:null}
            {input.credential==="delete"?<label className={styles.consent}><input type="checkbox" required checked={input.confirmDelete} onChange={event=>changeDraft({confirmDelete:event.target.checked})}/><span>确认删除该配置使用的加密凭据并停用此配置。环境凭据保留；若有其他配置仍在引用，将拒绝删除。</span></label>:null}
          </>:<p>服务地址和凭据由馆长维护，当前账户可调整模型与运行参数。</p>}
        </fieldset>
        <dl><div><dt>服务地址</dt><dd>{source?.environment.endpoint_configured?"已配置":"未配置"}</dd></div><div><dt>凭据来源</dt><dd>{{environment:"部署环境",saved:"已加密保存",absent:"未配置或服务不需要"}[source?.credential_storage||"absent"]}</dd></div><div><dt>状态范围</dt><dd>显示的是已保存配置；连通、模型加载和结果质量须分别核对。</dd></div></dl>
        <div className={styles.actions}><button className={styles.primary} type="submit" disabled={locked||!draft||input.document.configuration_version!==data.configuration_version}>{operation==="save"?"正在保存…":"保存配置"}</button><button type="button" disabled={!!operation||!!pendingVersion} onClick={()=>draft?setConfirm("reload"):reload()}>重新读取</button>{!hasWork?<Link href={`/admin/settings?service=profile-${encodeURIComponent(profile.key)}`}>查看服务状态与检查记录</Link>:null}</div>
      </form>:null}
    </>}
    <ConfirmDialog open={!!confirm} title={confirm==="fence"?"确认服务器当前配置":"放弃本地未保存输入"} description={confirm==="fence"?"读取当前配置并阻止原版本迟到保存，不会撤销已经完成的修改。草稿会被清除；密钥不会返回。":"仅清除本页未保存输入，重新读取服务器配置。已保存的凭据和任务不受影响。"} confirmLabel={confirm==="fence"?"读取并隔离旧请求":"重新读取"} pending={!!operation} onCancel={()=>setConfirm(null)} onConfirm={()=>confirm==="fence"?void fence():reload()}/>
  </div>;
}
