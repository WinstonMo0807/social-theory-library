"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { components } from "@/lib/api/generated/schema";
import styles from "./ocr-runtime-editor.module.css";

type Snapshot = components["schemas"]["OcrRuntimeSnapshot"];
type Input = components["schemas"]["OcrRuntimeInputRequest"];
type Probe = components["schemas"]["OcrProbeResult"];
const path = "/catalog/admin/ocr-runtime/";
const keyFor = (owner: string) => `stl-ocr-save:${owner}`;
const inputFor = (data: Snapshot): Input => ({expected_version:data.configuration_version, mode:data.mode, remote_url:data.remote_url, remote_model:data.remote_model, acknowledge_remote:false});

export function OcrRuntimeEditor({onSaved,onBusyChange}:{onSaved?:()=>void;onBusyChange?:(value:boolean)=>void}) {
  const user=useAdminSession(), [epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  if(!user||!["admin","superadmin"].includes(user.access_level||"")) return <p>当前账户只能查看服务状态，不能更改解析配置。</p>;
  return <Editor key={`${user.id}:${epoch}`} owner={String(user.id)} onSaved={onSaved} onBusyChange={onBusyChange}/>;
}

function Editor({owner,onSaved,onBusyChange}:{owner:string;onSaved?:()=>void;onBusyChange?:(value:boolean)=>void}) {
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Snapshot>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Snapshot>(path,owner,undefined,load);
  const [draft,setDraft]=useState<Input|null>(null),[message,setMessage]=useState(""),[pendingVersion,setPendingVersion]=useState("");
  const [ready,setReady]=useState(false),[recordError,setRecordError]=useState(""),[operation,setOperation]=useState("");
  const [confirm,setConfirm]=useState<"reload"|"fence"|"probe"|null>(null);
  const lifetime=useRef<AbortController|null>(null),busy=useRef(false);
  useEffect(()=>{const controller=new AbortController();lifetime.current=controller;
    const frame=window.requestAnimationFrame(()=>{
    try{const value=sessionStorage.getItem(keyFor(owner))||"";if(value&&!/^[a-f0-9]{64}$/.test(value))throw Error("未确认保存的记录格式异常，请先确认服务器当前配置。");setPendingVersion(value);setReady(true);}
    catch(error){setRecordError(error instanceof Error?error.message:"无法读取保存记录。");}
    });return()=>{window.cancelAnimationFrame(frame);controller.abort();};},[owner]);
  const data=resource.data, input=draft||(data?inputFor(data):null);
  const locked=!ready||!!recordError||!!operation||resource.pending||!!pendingVersion;
  useUnsavedForm(!!draft||!!pendingVersion||!!operation,false);
  const hasWork=!!draft||!!pendingVersion||!!operation;
  useEffect(()=>{onBusyChange?.(hasWork);return()=>onBusyChange?.(false);},[hasWork,onBusyChange]);
  function change(update:Partial<Input>){if(input&&!locked)setDraft({...input,...update,acknowledge_remote:false});}
  function clearPending(){sessionStorage.removeItem(keyFor(owner));setPendingVersion("");}
  async function save(event:FormEvent){
    event.preventDefault();if(!input||!data||locked||busy.current)return;
    const controller=lifetime.current;if(!controller||controller.signal.aborted)return;
    busy.current=true;setOperation("save");setMessage("");
    try{
      sessionStorage.setItem(keyFor(owner),input.expected_version);setPendingVersion(input.expected_version);
      const result=await resource.mutate(JSON.stringify(input),()=>apiRequest<Snapshot>(path,{method:"PUT",signal:controller.signal,headers:{"X-Editor-Owner":owner},body:JSON.stringify(input)},getServerSessionCredential()));
      if(!result||controller.signal.aborted)return;
      clearPending();setDraft(null);setMessage("解析设置已保存。新的任务沿原处理服务读取配置；已绑定的任务继续使用其原服务。");onSaved?.();
    }catch(error){if(!controller.signal.aborted)setMessage(`${error instanceof Error?error.message:"未收到保存结果。"} 输入保留。请先确认服务器配置，防止迟到的保存继续执行。`);}
    finally{busy.current=false;if(!controller.signal.aborted)setOperation("");}
  }
  async function fence(){
    const expected=pendingVersion||data?.configuration_version;
    const controller=lifetime.current;if(!expected||busy.current||!controller||controller.signal.aborted)return;
    busy.current=true;setOperation("fence");setMessage("");
    try{
      const result=await resource.mutate(`fence:${expected}`,()=>apiRequest<Snapshot>(path,{method:"PATCH",signal:controller.signal,headers:{"X-Editor-Owner":owner},body:JSON.stringify({expected_version:expected})},getServerSessionCredential()));
      if(!result||controller.signal.aborted)return;
      clearPending();setReady(true);setRecordError("");setDraft(null);setMessage("已读取服务器当前配置，并阻止原版本的迟到保存。已完成的修改未撤销，请核对当前值后继续。");setConfirm(null);onSaved?.();
    }catch(error){if(!controller.signal.aborted)setMessage(error instanceof Error?error.message:"暂不能确认配置，请保留此页面。");}
    finally{busy.current=false;if(!controller.signal.aborted)setOperation("");}
  }
  async function probe(action:"test_nas"|"test_remote"="test_nas"){
    const controller=lifetime.current;if(!data||locked||busy.current||!controller||controller.signal.aborted)return;
    busy.current=true;setOperation("probe");setConfirm(null);
    try{const result=await withPrivateOwner(owner,()=>apiRequest<Probe>(path,{method:"POST",signal:controller.signal,headers:{"X-Editor-Owner":owner},body:JSON.stringify({action,expected_version:data.configuration_version})},getServerSessionCredential()),controller.signal);
      if(!controller.signal.aborted)setMessage(`${result.target==="remote"?(result.reachable?"远程网关可连接，解析效果待验收":"远程网关不可连接"):result.functional===true?"当前 NAS 运行已就绪":result.reachable?"服务有响应，当前尚未就绪":"服务不可连接"}。${result.detail}`);
    }catch(error){if(!controller.signal.aborted)setMessage(`${error instanceof Error?error.message:"未收到检查结果。"} 检查可能仍在服务端继续，请先查看服务状态。`);}
    finally{busy.current=false;if(!controller.signal.aborted)setOperation("");}
  }
  function reload(){setDraft(null);setMessage("");setConfirm(null);resource.reload();}
  return <div className={styles.editor}>
    {(resource.error||recordError)?<p role="alert" className={styles.error}>{resource.error||recordError}</p>:null}
    {message?<p role="status" className={styles.notice}>{message}</p>:null}
    {pendingVersion||recordError?<div className={styles.notice}><p>保存记录尚未确认。刷新不会重新提交；确认当前配置后才能继续编辑。</p><button type="button" disabled={!data||!!operation||resource.pending} onClick={()=>setConfirm("fence")}>确认当前配置</button></div>:null}
    {!data||!input?<p>{resource.loading?"正在读取原解析配置…":"尚未读取可编辑的服务器配置。"}<button type="button" onClick={resource.reload}>重新读取</button></p>:<form onSubmit={save} aria-label="OCR 解析配置">
      <p>这些设置与处理中心共用。密钥和 NAS 地址由服务器原配置维护。</p>
      {data.remote_url_redacted?<p role="alert" className={styles.error}>现有远程地址包含不应展示的凭据或参数。请填写无凭据的新地址，或先在服务器修正；密钥原文不会显示。</p>:null}
      {draft&&draft.expected_version!==data.configuration_version?<p role="alert" className={styles.error}>服务器配置已变化，当前输入仍保留。请先重新读取；旧输入不会覆盖新配置。</p>:null}
      <fieldset disabled={locked}>
        <label><span>运行方式</span><select data-stl-select value={input.mode} onChange={event=>change({mode:event.target.value as Input["mode"]})}><option value="nas_only">只使用 NAS RapidOCR · PP-OCRv6 tiny</option><option value="nas_preferred">NAS 优先，失败后使用已配置的远程服务</option><option value="remote_only">只使用远程解析网关</option></select></label>
        <label><span>远程网关地址</span><input type="url" maxLength={2048} value={input.remote_url} onChange={event=>change({remote_url:event.target.value})} autoComplete="off" spellCheck={false}/></label>
        <label><span>远程模型标识</span><input readOnly value="PP-OCRv6-tiny"/></label>
        <small>远端也须运行相同的 RapidOCR tiny 网关。地址留空时沿用服务器默认值；选择“只使用 NAS”可停用远程回退。</small>
        {input.mode!=="nas_only"?<label className={styles.consent}><input type="checkbox" checked={input.acknowledge_remote||false} onChange={event=>setDraft({...input,acknowledge_remote:event.target.checked})}/><span>我确认此解析方式在需要时会把待识别文档发送到配置的远程服务。</span></label>:null}
      </fieldset>
      <dl><div><dt>NAS 服务</dt><dd>{data.nas_configured?data.nas_url:"未配置"}</dd></div><div><dt>远程密钥</dt><dd>{data.remote_key_configured?"服务器已配置":"未配置"}</dd></div><div><dt>远程配置</dt><dd>{data.remote_configured?"地址、模型和密钥齐全":"尚不完整"}</dd></div><div><dt>最近处理成功</dt><dd>{data.last_success_at?new Date(data.last_success_at).toLocaleString("zh-CN"):"尚无记录"}</dd></div></dl>
      <div className={styles.actions}><button type="submit" disabled={locked||!draft||draft.expected_version!==data.configuration_version} className={styles.primary}>{operation==="save"?"正在保存…":"保存解析配置"}</button><button type="button" disabled={locked} onClick={()=>draft?setConfirm("reload"):reload()}>重新读取</button><button type="button" disabled={locked||!!draft||!data.nas_configured} onClick={()=>setConfirm("probe")}>{operation==="probe"?"正在验证…":"验证 NAS 模型"}</button><button type="button" disabled={locked||!!draft||!data.remote_configured||data.remote_url_redacted} onClick={()=>void probe("test_remote")}>检查远程连接</button><Link href="/admin/settings?service=ocr">服务状态与检查</Link></div>
    </form>}
    <ConfirmDialog open={confirm==="reload"} title="重新读取解析配置" description="当前未保存的输入将被服务器配置替换。" confirmLabel="重新读取" onCancel={()=>setConfirm(null)} onConfirm={reload}/>
    <ConfirmDialog open={confirm==="fence"} title="确认当前服务器配置" description="将阻止原版本尚未执行的保存，并读取当前配置替换此页输入。已经完成的修改会保留，不会被撤销。" confirmLabel="确认并读取" pending={operation==="fence"} onCancel={()=>setConfirm(null)} onConfirm={fence}/>
    <ConfirmDialog open={confirm==="probe"} title="验证 NAS 模型" description="此操作会在现有 OCR 服务加载并检查模型，可能占用设备资源。不会发送馆藏文档，也不会改变解析配置。" confirmLabel="开始验证" onCancel={()=>setConfirm(null)} onConfirm={()=>probe()}/>
  </div>;
}
