"use client";

import { confirmAction } from "@/lib/ui-dialog";

import Link from "next/link";
import {useCallback, useEffect, useRef, useState, type FormEvent} from "react";
import {apiRequest, getServerSessionCredential} from "@/lib/api";
import {withPrivateOwner} from "@/lib/api/private-owner";
import {usePersistentWorkspace} from "@/lib/api/use-persistent-workspace";
import {useUnsavedForm} from "@/lib/use-unsaved-form";
import type {components} from "@/lib/api/generated/schema";
import {Dialog} from "@/components/ui/dialog";
import {useCatalogCommand} from "../workflow/use-intake-command";
import styles from "./person-authority.module.css";
import { SourceEditorFrame, type SourceEditorOptions } from "./source-editor-frame";

type Source=components["schemas"]["KnowledgeTermsSource"];
type Alias=components["schemas"]["KnowledgeTermInputRequest"];
type Receipt=components["schemas"]["KnowledgeTermsReceipt"];
type Command=Omit<components["schemas"]["KnowledgeTermsCommandRequest"],"request_id">;
const endpoint="/catalog/admin/index-maintenance/knowledge-terms/";
const types:Record<string,string>={alias:"别名",translation:"译名",abbreviation:"简称",historical:"历史名称",transliteration:"音译"};
const sources:Record<string,string>={editorial:"编辑确认",authority_import:"权威库导入",legacy_review:"历史名称复核",pdf_evidence:"馆藏原文",web_evidence:"外部公开来源",other:"其他已记录来源"};

function readSource(owner:string,url:string,signal:AbortSignal){return withPrivateOwner(owner,async()=>{
  const result=await apiRequest<Source>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false);
  if(result.owner_id!==owner)throw Error("账户已变化，请重新读取知识来源。");return result;
},signal);}

export function KnowledgeAliasesDialog({owner,nodeId,onClose,onSaved,...options}:{owner:string;nodeId:string;onClose:()=>void;onSaved:()=>void}&SourceEditorOptions){
  const load=useCallback((url:string,signal:AbortSignal)=>readSource(owner,url,signal),[owner]);
  const resource=usePersistentWorkspace<Source>(`${endpoint}${nodeId}/`,owner,undefined,load);
  if(!resource.data)return <SourceEditorFrame embedded={options.embedded} onClose={onClose} label="知识术语来源"><h2>知识术语来源</h2><p role={resource.error?"alert":"status"}>{resource.error||"正在读取原知识记录与编辑草稿…"}</p><button type="button" onClick={resource.reload}>重新读取</button><button type="button" onClick={onClose}>关闭</button></SourceEditorFrame>;
  return <AliasForm {...options} key={`${owner}:${nodeId}`} owner={owner} source={resource.data} readError={resource.error} reload={resource.reload} onClose={onClose} onSaved={onSaved}/>;
}

function AliasForm({owner,source,readError,reload,onClose,onSaved,embedded,formId,onState}:{owner:string;source:Source;readError:string;reload:()=>void;onClose:()=>void;onSaved:()=>void}&SourceEditorOptions){
  const [original,setOriginal]=useState(source),[aliases,setAliases]=useState<Alias[]>(source.aliases),[reason,setReason]=useState("");
  const [review,setReview]=useState(false),[notice,setNotice]=useState(""),[refreshing,setRefreshing]=useState(false);
  const command=useCatalogCommand<Command,Receipt>(owner,endpoint,`stl-knowledge-terms:${owner}`);
  const lifetime=useRef<AbortController|null>(null);
  useEffect(()=>{const request=new AbortController();lifetime.current=request;return()=>request.abort();},[]);
  const dirty=useUnsavedForm({aliases,reason},{aliases:original.aliases,reason:""});
  const blocked=!source.can_edit||refreshing||review||command.busy||!command.ready||Boolean(command.recovery);
  const changed=aliases.filter((row,index)=>JSON.stringify(row)!==JSON.stringify(original.aliases[index]));
  const saveable=!blocked&&changed.length>0&&source.version===original.version;
  useEffect(()=>{onState?.({dirty,busy:command.busy||refreshing||review||Boolean(command.recovery),saveable});},[onState,dirty,command.busy,refreshing,review,command.recovery,saveable]);
  async function close(){if(!command.busy&&!refreshing&&(!dirty||(await confirmAction("术语修改尚未保存，关闭会放弃当前输入。是否关闭？"))))onClose();}
  async function refreshSource(){const active=lifetime.current;if(!active||refreshing||active.signal.aborted||dirty&&!(await confirmAction("重新读取会放弃当前未保存输入。是否继续？")))return;setRefreshing(true);
    try{const next=await readSource(owner,`${endpoint}${original.node_id}/`,AbortSignal.any([active.signal,AbortSignal.timeout(30000)]));if(!active.signal.aborted){setOriginal(next);setAliases(next.aliases);setReason("");setNotice("");reload();}}
    catch(error){if(!active.signal.aborted){setNotice(error instanceof Error?error.message:"来源暂不可读，输入仍保留。");reload();}}
    finally{if(!active.signal.aborted)setRefreshing(false);}}
  async function save(){const result=await command.send({node_id:original.node_id,expected_version:original.version,aliases,reason,confirmed:true});if(result){if(result.state==="applied"){onSaved();onClose();}else{setReview(false);setNotice("原保存已停止，当前输入仍保留。");}}}
  async function recover(stop=false){const result=await command.lookup(stop);if(!result)return;setReview(false);setNotice(result.state==="cancelled"?"原待定保存已停止，当前输入仍保留。":result.node_id===original.node_id?"已查询本条目的保存结果。请重新读取草稿后继续。":"已查询此前另一知识条目的保存，本次输入仍保留。");reload();if(result.state==="applied")onSaved();}
  function submit(event:FormEvent){event.preventDefault();if(!blocked&&changed.length&&source.version===original.version)setReview(true);}
  const pending=Boolean(command.recovery);
  return <SourceEditorFrame embedded={embedded} label="知识术语来源" onClose={review?undefined:close}>
    <header className={styles.row}><div><h2 id="knowledge-terms-title">{original.title} · 中英术语</h2>{original.foreign_name?<p>{original.foreign_name}</p>:null}</div><button type="button" disabled={command.busy||review||refreshing} onClick={close}>关闭</button></header>
    <p>维护这条知识记录的别名、译名和检索用法。保存到原编辑草稿，核对并发布后才改变公开检索。</p>
    {source.revision_id?<p className={styles.notice}>已有编辑草稿，本次只更改术语列表，草稿中的其他修改一起保留。</p>:null}
    {source.notice?<p role="alert" className={styles.notice}>{source.notice}</p>:null}{!source.can_edit&&!source.notice?<p className={styles.notice}>当前账户只能查看来源。</p>:null}
    {readError?<p role="alert">{readError}；当前输入仍保留。</p>:null}{source.version!==original.version?<p role="alert" className={styles.notice}>来源已有新版本，当前输入仍保留。请核对最新草稿后继续。</p>:null}
    {notice?<p role="status" className={styles.notice}>{notice}</p>:null}
    {pending?<aside className={styles.notice}><strong>有一次保存需要核对</strong><p>仅保留请求编号。停止只阻止尚未执行的保存，已保存的草稿仍会返回实际操作结果。</p><div className={styles.actions}><button type="button" disabled={command.busy} onClick={()=>void recover()}>查询原保存</button><button type="button" disabled={command.busy} onClick={()=>void recover(true)}>停止未执行的保存</button>{command.canRetry?<button type="button" disabled={command.busy} onClick={()=>void command.send().then(result=>{if(result){setReview(false);setNotice(result.state==="applied"?"已确认原保存，请重新读取草稿。":"原保存已停止。");reload();if(result.state==="applied")onSaved();}})}>重试同一次保存</button>:null}</div></aside>:null}
    {command.error?<p role="alert">{command.error}</p>:null}
    <form id={formId} onSubmit={submit}><fieldset className={styles.aliasFields} disabled={blocked}>{aliases.map((row,index)=><fieldset className={styles.aliasRow} key={index}><legend>{index<original.aliases.length?"已保存术语":"新增术语"} {index+1}</legend><label>名称<input required maxLength={240} readOnly={index<original.aliases.length} value={row.alias} onChange={event=>setAliases(rows=>rows.map((value,at)=>at===index?{...value,alias:event.target.value}:value))}/></label><label>语言<input required maxLength={16} value={row.language} onChange={event=>setAliases(rows=>rows.map((value,at)=>at===index?{...value,language:event.target.value}:value))}/></label><label>类别<select data-stl-select value={row.alias_type} onChange={event=>setAliases(rows=>rows.map((value,at)=>at===index?{...value,alias_type:event.target.value as Alias["alias_type"]}:value))}>{Object.entries(types).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label><label>来源类别<select data-stl-select value={row.source_kind} onChange={event=>setAliases(rows=>rows.map((value,at)=>at===index?{...value,source_kind:event.target.value as Alias["source_kind"]}:value))}>{Object.entries(sources).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label><label className={styles.checks}><input type="checkbox" checked={row.is_verified} onChange={event=>setAliases(rows=>rows.map((value,at)=>at===index?{...value,is_verified:event.target.checked}:value))}/>已核对名称与归属</label>{index>=original.aliases.length?<button type="button" onClick={()=>setAliases(rows=>rows.filter((_,at)=>at!==index))}>移除此新增项</button>:null}</fieldset>)}
      {!aliases.length?<p>暂无别名或译名。请按出处填写。</p>:null}<button type="button" disabled={aliases.length>=200} onClick={()=>setAliases(rows=>[...rows,{alias:"",language:"und",alias_type:"alias",source_kind:"other",is_verified:false}])}>添加术语</button>
      <label className={styles.aliasReason}>本次修改的来源与依据<textarea required minLength={2} maxLength={1000} rows={3} value={reason} onChange={event=>setReason(event.target.value)}/></label>
      <p className={styles.muted}>已保存名称保留原记录。更正时取消原词的核验，再新增准确名称；发布后未核验词仅供后台追溯。词语匹配不会自动建立学术关系。</p><button className={styles.primary} type="submit" disabled={!changed.length||source.version!==original.version}>预览术语变化</button>
    </fieldset></form>
    <div className={styles.actions}><button type="button" disabled={command.busy||review||refreshing} onClick={()=>void refreshSource()}>{refreshing?"正在读取…":"重新读取来源"}</button><Link href={source.editor_url}>进入原知识编辑与发布</Link></div>
    <details data-disclosure="collection" className={styles.variantChanges}><summary>正式来源中的术语（{original.saved_aliases.length} 项）</summary>{original.saved_aliases.map(row=><article key={row.alias}><strong>{row.alias}</strong><p>{row.language} · {types[row.alias_type]} · {row.is_verified?"已核验":"未核验"}</p></article>)}</details>
    {review?<Dialog open className={styles.dialog} aria-labelledby="knowledge-terms-review" onRequestClose={command.busy?undefined:()=>setReview(false)}><h2 id="knowledge-terms-review">确认术语草稿</h2><p>以下 {changed.length} 项写入原知识条目的编辑草稿，公开版本须从原发布流程另行核对。</p><div className={styles.variantChanges}>{changed.map((row,index)=><article key={index}><strong>{row.alias}</strong><p>{row.language} · {types[row.alias_type]} · {sources[row.source_kind]} · {row.is_verified?"已核对":"待核对"}</p></article>)}</div><p>依据：{reason}</p>{command.error?<p role="alert">{command.error}</p>:null}<div className={styles.actions}><button type="button" disabled={command.busy} onClick={()=>setReview(false)}>返回修改</button><button type="button" className={styles.primary} disabled={command.busy||pending||source.version!==original.version} onClick={()=>void save()}>{command.busy?"正在保存…":"确认保存草稿"}</button></div></Dialog>:null}
  </SourceEditorFrame>;
}
