"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, BookOpen, FileText, Plus, Search, Upload, X } from "lucide-react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { apiEndpoint } from "@/lib/runtime-api";
import { useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { safeAdminHref } from "@/lib/admin-route-context";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { useCatalogCommand } from "./use-intake-command";
import styles from "./manual-catalog.module.css";
import { ManualMetadataPrefill, prefillKey, prefillLabels, type ManualMetadataCandidate, type ManualPrefill } from "./manual-metadata-prefill";

type PersonRow={person_id:string|null;name:string;role:string;create_new:boolean};
type Form={work:{title:string;document_type:string;language:string;subtitle:string;abstract:string};bibliography:Record<string,string|number|null>;contributors:PersonRow[]};
type Edition={id:string;version:string;label:string;state:string;bibliography:Form["bibliography"];contributors:PersonRow[]};
type Candidate={id:string;title:string;document_type:string;language:string;subtitle:string;abstract:string;cover_url:string;editions:Edition[]};
type Saved={session_id:string;edition_id:string;work_id:string;version:string;form:Form;editable:boolean;shared_work:boolean;status:string};
type Workspace={owner_id:string;results:Candidate[];count:number;page:number;pages:number;saved:Saved|null;people_count:number;people_page:number;people_pages:number;people:{id:string;name:string;original_name:string;context:string}[]};
type Command={session_id:string|null;expected_version:string;mode:string;edition_id:string|null;candidate_version:string;acknowledge_similar:boolean;continue_files:boolean;form:Form;prefills:{token:string;fields:string[]}[]};
type Receipt={owner_id:string;request_id:string;state:"applied"|"cancelled";session_id:string|null;edition_id:string|null;work_id:string|null;version:string;next_url:string;form:Form|null;manual_form:boolean;shared_work:boolean};
const kinds:Record<string,string>={book:"图书",journal_article:"期刊论文",chapter:"论文集章节",other:"其他资料",journal_issue:"整期期刊",thesis:"学位论文",report:"研究报告"};
const roles:Record<string,string>={author:"作者",translator:"译者",editor:"编者",chief_editor:"主编",annotator:"校注",photographer:"摄影",advisor:"导师",subject:"研究对象",other:"其他责任者"};
const empty:Form={work:{title:"",document_type:"book",language:"zh-CN",subtitle:"",abstract:""},bibliography:{},contributors:[{person_id:null,name:"",role:"author",create_new:false}]};

function PersonField({owner,row,onChange,disabled}:{owner:string;row:PersonRow;onChange:(next:PersonRow)=>void;disabled:boolean}){
  const [opened,setOpened]=useState(false),[query,setQuery]=useState(""),[page,setPage]=useState(1);
  const name=row.name.trim();
  useEffect(()=>{if(!opened||!name)return;const timer=setTimeout(()=>setQuery(name),300);return()=>clearTimeout(timer);},[name,opened]);
  const load=useCallback(async(path:string,signal:AbortSignal)=>{const result=await apiRequest<Workspace>(path,{signal,headers:{"X-Editor-Owner":owner},cache:"no-store"},getServerSessionCredential(),false);if(result.owner_id!==owner)throw new PrivateOwnerVerificationError("人物候选与当前账户不匹配，请重新读取。",403);return result;},[owner]);
  const people=usePersistentWorkspace<Workspace>(opened&&name&&name===query?`/catalog/admin/manual-catalog/?${new URLSearchParams({people:query,people_page:String(page)})}`:"",owner,undefined,load);
  const searching=name!==query||people.loading;
  return <div className={styles.person}>
    <div><input aria-label="责任者姓名" maxLength={240} disabled={disabled} value={row.name} onChange={event=>{onChange({...row,name:event.target.value,person_id:null,create_new:false});setPage(1);setOpened(true);}} placeholder="输入姓名，核对馆内人物"/><select aria-label="责任角色" disabled={disabled} value={row.role} onChange={event=>onChange({...row,role:event.target.value})}>{Object.entries(roles).map(([id,label])=><option value={id} key={id}>{label}</option>)}</select></div>
    {row.person_id?<small>已选择馆内人物<button disabled={disabled} onClick={()=>{setPage(1);setOpened(true);}}>重新选择</button></small>:row.create_new?<small>保存时新建人物草稿，身份仍待核对</small>:null}
    {opened&&name?<section className={styles.personResults} aria-label="人物候选">
      {searching?<p role="status">正在查找馆内人物…</p>:null}{people.error?<p role="alert">{people.error}<button disabled={disabled} onClick={people.reload}>重新读取人物</button></p>:null}
      {people.data?.people.map(person=><button key={person.id} disabled={disabled||searching||Boolean(people.error)} onClick={()=>{onChange({...row,person_id:person.id,name:person.name,create_new:false});setOpened(false);}}><strong>{person.name}</strong><small>{person.original_name} {person.context}</small></button>)}
      {!searching&&!people.error&&people.data?.people_count===0?<p>未找到对应人物，请核对姓名和原文拼写。</p>:null}
      {people.data&&!people.error?<nav className={styles.pager} aria-label="人物候选分页"><button disabled={disabled||searching||people.data.people_page<=1} onClick={()=>setPage(people.data!.people_page-1)}>上一页</button><span>共 {people.data.people_count} 位 · {people.data.people_page} / {people.data.people_pages}</span><button disabled={disabled||searching||people.data.people_page>=people.data.people_pages} onClick={()=>setPage(people.data!.people_page+1)}>下一页</button></nav>:null}
      <button disabled={disabled||searching} onClick={()=>{onChange({...row,person_id:null,create_new:true});setOpened(false);}}>明确新建“{row.name}”的人物草稿</button><button onClick={()=>setOpened(false)}>收起</button>
    </section>:null}
  </div>;
}

export function ManualCatalogForm(){const user=useAdminSession(),params=useSearchParams(),[epoch,setEpoch]=useState(0);useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);return user?<ManualBody key={`${user.id}:${epoch}:${params.get("session")||"new"}`} owner={String(user.id)}/>:<p role="status">正在核对编目账户…</p>;}

function ManualBody({owner}:{owner:string}){
  const router=useRouter(),params=useSearchParams(),returnHref=safeAdminHref(params.get("return_to")),sessionParam=params.get("session")||"";
  const [draft,setDraft]=useState<Form|null>(null),[saved,setSaved]=useState<Saved|null>(null),[query,setQuery]=useState(""),[search,setSearch]=useState(""),[page,setPage]=useState(1),[selection,setSelection]=useState<Candidate|null>(null),[editionId,setEditionId]=useState(""),[mode,setMode]=useState("new_work"),[notice,setNotice]=useState(""),[localError,setLocalError]=useState(""),[duplicate,setDuplicate]=useState<{title:string;files:boolean;support:boolean}|null>(null);
  const [prefills,setPrefills]=useState<Record<string,ManualPrefill>>({});
  const [checking,setChecking]=useState(false),[duplicatePage,setDuplicatePage]=useState(1),checkRequest=useRef<AbortController|null>(null);
  useEffect(()=>()=>checkRequest.current?.abort(),[]);
  const command=useCatalogCommand<Command,Receipt>(owner,"/catalog/admin/manual-catalog/",`stl-manual-catalog:${owner}`);
  const load=useCallback(async(path:string,signal:AbortSignal)=>{const result=await apiRequest<Workspace>(path,{signal,headers:{"X-Editor-Owner":owner},cache:"no-store"},getServerSessionCredential(),false);if(result.owner_id!==owner)throw new PrivateOwnerVerificationError("书目资料与当前账户不匹配，请重新读取。",403);const expected=new URLSearchParams(path.split("?")[1]).get("session");if(expected&&result.saved?.session_id!==expected)throw new PrivateOwnerVerificationError("当前书目会话已变化，请保留填写并重新读取。",403);return result;},[owner]);
  const workspace=usePersistentWorkspace<Workspace>(`/catalog/admin/manual-catalog/?${new URLSearchParams({q:search,page:String(page),...(sessionParam?{session:sessionParam}:{})})}`,owner,undefined,load);
  const duplicates=usePersistentWorkspace<Workspace>(duplicate?`/catalog/admin/manual-catalog/?${new URLSearchParams({match_title:duplicate.title,page:String(duplicatePage)})}`:"",owner,undefined,load);
  const current=saved??workspace.data?.saved??null,form=draft??current?.form??empty,edition=selection?.editions.find(row=>row.id===editionId),kind=form.work.document_type;
  useUnsavedForm({form,prefills,selection:current?null:[mode,editionId],pending:Boolean(command.recovery)},
    {form:current?.form??empty,prefills:{},selection:current?null:["new_work",""],pending:false});
  const locked=checking||!command.ready||command.busy||Boolean(command.recovery)||Boolean(sessionParam&&!current)||Boolean(current&&!current.editable);
  const shared=Boolean(current?.shared_work||selection&&mode!=="new_work"&&!current),source=current?`/admin/library/works/${current.work_id}?edition=${current.edition_id}`:edition&&selection?`/admin/library/works/${selection.id}?edition=${edition.id}`:"";
  function editWork(key:keyof Form["work"],value:string){setDraft({...form,work:{...form.work,[key]:value}});setNotice("");}
  function editField(key:string,value:string){setDraft({...form,bibliography:{...form.bibliography,[key]:key==="publication_year"?(value?Number(value):null):value}});setNotice("");}
  function choose(row:Candidate){setPrefills({});setSelection(row);setEditionId(row.editions[0]?.id||"");setMode("new_version");setDraft({...form,work:{title:row.title,document_type:row.document_type,language:row.language,subtitle:row.subtitle,abstract:row.abstract}});setDuplicate(null);setNotice("已选择馆内作品；新增版本只保存当前出版信息。");}
  function refresh(){setSaved(null);workspace.reload();}
  function accept(result:Receipt){if(result.state==="cancelled"){setNotice("原请求已停止，输入仍保留。");return;}if(!result.manual_form){go(result.next_url);return;}setPrefills({});if(result.session_id&&result.edition_id&&result.work_id&&result.form){setSaved({session_id:result.session_id,edition_id:result.edition_id,work_id:result.work_id,version:result.version,form:result.form,editable:mode!=="use_edition",shared_work:result.shared_work,status:"drafting"});setDraft(result.form);setNotice("已保存草稿 · 尚未发布，可以稍后补充文件。");router.replace(`/admin/cataloging/new?session=${result.session_id}${params.has("return_to")?`&return_to=${encodeURIComponent(returnHref)}`:""}`);}}
  function go(path:string,support=false){if(/^\/admin\/library\/works\/[0-9a-f-]+(?:\/files)?\?edition=[0-9a-f-]+(?:#bibliography)?$/i.test(path))router.push(support?`${path}&tab=files&support=1`:path);}
  async function save(files=false,ack=false,support=false){if(locked||checkRequest.current)return;setLocalError("");if(!form.work.title.trim()){setLocalError("请填写题名。");document.getElementById("manual-title")?.focus();return;}if(!current&&mode!=="new_work"&&!edition){setLocalError("请先选定已有作品的具体版本。");return;}if(!current&&mode==="new_work"&&!ack){
      const controller=new AbortController();checkRequest.current=controller;setChecking(true);
      try{const result=await withPrivateOwner(owner,()=>load(`/catalog/admin/manual-catalog/?${new URLSearchParams({match_title:form.work.title.trim()})}`,AbortSignal.any([controller.signal,AbortSignal.timeout(60000)])),controller.signal);if(controller.signal.aborted)return;if(result.count){setDuplicatePage(1);setDuplicate({title:form.work.title.trim(),files,support});return;}}
      catch(reason){if(!controller.signal.aborted)setLocalError(reason instanceof Error?reason.message:"同名作品暂时无法核对，填写仍保留，请稍后保存。");return;}
      finally{if(!controller.signal.aborted){checkRequest.current=null;setChecking(false);}}
      if(controller.signal.aborted)return;
    }
    if(ack&&(!duplicate||duplicate.title!==form.work.title.trim())){setLocalError("题名已变化，请重新核对同名作品。");setDuplicate(null);return;}const result=await command.send({session_id:current?.session_id??null,expected_version:current?.version??"",mode,edition_id:edition?.id??null,candidate_version:edition?.version??"",acknowledge_similar:ack,continue_files:files,prefills:Object.values(prefills).map(({token,fields})=>({token,fields})),form:{...form,contributors:form.contributors.filter(row=>row.name.trim())}});if(result){accept(result);setDuplicate(null);if(files||mode==="use_edition")go(result.next_url,support);}}
  async function recover(cancel=false){const result=await command.lookup(cancel);if(result)accept(result);}
  const prefillCurrent:Record<string,unknown>={...form.work,...form.bibliography,authors:form.contributors.filter(row=>row.role==="author").map(row=>row.name),translators:form.contributors.filter(row=>row.role==="translator").map(row=>row.name)};
  function applyPrefill(row:ManualMetadataCandidate,fields:string[]){
    if(locked||mode==="use_edition")return;
    const next:Form={work:{...form.work},bibliography:{...form.bibliography},contributors:[...form.contributors]},pending={...prefills},seen=new Set<string>();
    let count=0;const skipped:string[]=[];
    for(const sourceField of fields){
      const key=prefillKey(sourceField);if(seen.has(key))continue;seen.add(key);
      if(shared&&key in form.work)continue;
      let value=row.fields[sourceField];if(value==null||value==="")continue;
      let previous:unknown;
      if(key==="authors"||key==="translators"){
        const role=key==="authors"?"author":"translator";
        if(!Array.isArray(value)||!value.length||value.length>50||value.some(name=>typeof name!=="string"||!name.trim()||name.length>240)){skipped.push(prefillLabels[key]);continue;}
        previous=next.contributors.filter(person=>person.role===role);
        value=value.map(name=>({person_id:null,name:String(name).trim(),role,create_new:false}));
        const others=next.contributors.filter(person=>person.role!==role&&person.name.trim());
        if(others.length+(value as PersonRow[]).length>50){skipped.push(prefillLabels[key]);continue;}
        next.contributors=[...others,...value as PersonRow[]];
      }else{
        if(typeof value!=="string"&&typeof value!=="number"){skipped.push(prefillLabels[key]);continue;}
        if(key==="publication_year"){
          const year=Number(value);if(!Number.isInteger(year)||year<1000||year>2100){skipped.push(prefillLabels[key]);continue;}value=year;
        }else value=String(value);
        if(key==="document_type"&&!(String(value) in kinds)){skipped.push(prefillLabels[key]);continue;}
        const limit=({title:600,subtitle:600,abstract:60000,language:32,document_type:40,doi:255,isbn:32,volume:40,issue:40,page_range:80,publication_place:200,version_label:120} as Record<string,number>)[key]||300;
        if(String(value).length>limit){skipped.push(prefillLabels[key]);continue;}
        previous=key in next.work?next.work[key as keyof Form["work"]]:next.bibliography[key];
        if(key in next.work)next.work={...next.work,[key]:String(value)};else next.bibliography[key]=value as string|number;
      }
      pending[key]={token:row.token,fields:[sourceField],previous:key in pending?pending[key].previous:previous,applied:value,label:row.source_label};count++;
    }
    setDraft(next);setPrefills(pending);setNotice(`${count?`已填入 ${count} 项，尚未保存。`:"没有可填入的空字段。"}${skipped.length?`${skipped.join("、")}需手工核对，未直接填入。`:""}`);
  }
  function undoPrefill(field:string){
    const row=prefills[field];if(!row||locked)return;
    const role=field==="authors"?"author":"translator",people=field==="authors"||field==="translators";
    const value=people?form.contributors.filter(person=>person.role===role):prefillCurrent[field];
    if(JSON.stringify(value)!==JSON.stringify(row.applied)){setNotice("这项填写在预填后又有修改，已保留。可手动修改，或移除本次预填来源后保存。");return;}
    if(people)setDraft({...form,contributors:[...form.contributors.filter(person=>person.role!==role),...row.previous as PersonRow[]]});
    else if(field in form.work)setDraft({...form,work:{...form.work,[field]:row.previous??""}});
    else setDraft({...form,bibliography:{...form.bibliography,[field]:row.previous as string|number|null??null}});
    const next={...prefills};delete next[field];setPrefills(next);setNotice("已撤销这项预填，其他填写保留。");
  }
  function field(id:string,label:string,max=300){return <label key={id}>{label}<input type={id==="publication_year"?"number":"text"} min={id==="publication_year"?1000:undefined} max={id==="publication_year"?2100:undefined} maxLength={max} disabled={locked||mode==="use_edition"} value={form.bibliography[id]??""} onChange={event=>editField(id,event.target.value)}/></label>;}
  const actions=<><Link href={returnHref}>取消</Link><button disabled={locked} onClick={()=>void save()}>保存草稿</button><button className={styles.primary} disabled={locked} onClick={()=>void save(true)}>保存并继续补文件 <ArrowRight size={15}/></button></>;
  const matching=workspace.data?.results??[];
  return <main className={styles.page}><nav className={styles.breadcrumb}><Link href="/admin/uploads">收件与编目</Link><span>›</span><span>新建书目：先材料后文件</span></nav><header className={styles.heading}><div><h1>新建书目：先材料后文件</h1><p>在 PDF 尚未准备好时建立准确书目，之后继续补齐。</p></div><div className={styles.actions}>{actions}<small>{current?"● 已保存未发布":"尚未保存"}</small></div></header>
    {checking?<p className={styles.notice} role="status">正在核对馆内同名作品，当前填写保留…</p>:null}{notice?<p className={styles.notice} role="status">{notice}{source?<Link href={source.replace("?edition=", "/files?edition=")}>去文件处理 →</Link>:null}</p>:null}{localError||command.error?<p className={styles.error} role="alert">{localError||command.error}<button onClick={refresh}>重新核对当前书目</button><button onClick={()=>{setSearch(form.work.title.slice(0,160));setPage(1);}}>核对同名作品</button></p>:null}{workspace.error?<p className={styles.error} role="alert">{workspace.error}。已填写内容仍保留。<button onClick={workspace.reload}>重新读取</button></p>:null}{command.recovery?<section className={styles.notice}><p>保存结果尚未确认，请查回原请求，避免重复新建书目。</p><button disabled={command.busy} onClick={()=>void recover()}>查回原请求</button><button disabled={command.busy} onClick={()=>void recover(true)}>停止未执行请求</button>{command.canRetry?<button disabled={command.busy} onClick={()=>void command.send().then(result=>{if(result)accept(result);})}>重发原内容</button>:null}</section>:null}{current&&!current.editable?<p className={styles.notice}>此书目已进入后续流程。<Link href={source}>打开馆藏工作页</Link></p>:null}
    <div className={styles.columns}><div className={styles.form}><section><h2><b>1</b>材料类型</h2><div className={styles.types}>{["book","journal_article","chapter","other"].map(id=><button disabled={locked||shared||Boolean(current)} aria-pressed={id===kind||id==="other"&&["thesis","report","journal_issue"].includes(kind)} key={id} onClick={()=>editWork("document_type",id)}>{id==="book"?<BookOpen size={17}/>:<FileText size={17}/>} {kinds[id]}</button>)}</div>{["other","thesis","report","journal_issue"].includes(kind)?<label className={styles.subtype}>具体类型<select disabled={locked||shared||Boolean(current)} value={kind} onChange={event=>editWork("document_type",event.target.value)}>{["other","thesis","report","journal_issue"].map(id=><option key={id} value={id}>{kinds[id]}</option>)}</select></label>:null}</section>
    <section><h2><b>2</b>基本信息</h2><ManualMetadataPrefill owner={owner} context={prefillCurrent} current={prefillCurrent} disabled={locked||mode==="use_edition"} shared={shared} prefills={prefills} onApply={applyPrefill} onUndo={undoPrefill} onDetach={()=>{setPrefills({});setNotice("本次预填来源已移除，填写仍保留，之后按人工填写保存。");}}/><label className={styles.title}>题名 <span aria-hidden="true">*</span><input id="manual-title" required maxLength={600} disabled={locked||shared} value={form.work.title} onChange={event=>editWork("title",event.target.value)} aria-invalid={Boolean(localError&&!form.work.title.trim())}/><small>{form.work.title.length}/600</small></label><div className={styles.people}><span>责任者</span><div>{form.contributors.map((row,index)=><div className={styles.personRow} key={index}><PersonField owner={owner} row={row} disabled={locked||mode==="use_edition"} onChange={next=>setDraft({...form,contributors:form.contributors.map((person,i)=>i===index?next:person)})}/><button aria-label={`移除第${index+1}位责任者`} disabled={locked||mode==="use_edition"} onClick={()=>setDraft({...form,contributors:form.contributors.filter((_,i)=>i!==index)})}><X size={14}/></button></div>)}<button disabled={locked||mode==="use_edition"||form.contributors.length>=50} onClick={()=>setDraft({...form,contributors:[...form.contributors,{person_id:null,name:"",role:"author",create_new:false}]})}><Plus size={14}/> 添加其他责任者（译者、编者等）</button></div></div><details><summary>更多作品信息</summary><label>正文语言<select disabled={locked||shared} value={form.work.language} onChange={event=>editWork("language",event.target.value)}>{["zh-CN","zh-TW","en","de","fr","mixed"].map(id=><option key={id} value={id}>{({"zh-CN":"简体中文","zh-TW":"繁体中文",en:"英语",de:"德语",fr:"法语",mixed:"多语种"} as Record<string,string>)[id]}</option>)}</select></label><label>副题名<input disabled={locked||shared} maxLength={600} value={form.work.subtitle} onChange={event=>editWork("subtitle",event.target.value)}/></label><label>简介<textarea disabled={locked||shared} rows={4} value={form.work.abstract} onChange={event=>editWork("abstract",event.target.value)}/></label></details></section>
    <section><h2><b>3</b>{["journal_article","journal_issue"].includes(kind)?"期刊信息":kind==="chapter"?"论文集与篇章信息":"版本信息"}</h2><div className={styles.fields}>{["journal_article","journal_issue"].includes(kind)?<>{field("journal_title","期刊名称")}{field("publication_year","出版年")}{field("volume","卷",40)}{field("issue","期",40)}{field("page_range","起止页码",80)}{field("doi","DOI",255)}</>:kind==="chapter"?<>{field("container_title","论文集名称",600)}{field("publisher","出版社")}{field("publication_year","出版年")}{field("publication_place","出版地",200)}{field("page_range","起止页码",80)}{field("doi","DOI",255)}</>:<>{field("publication_place","出版地",200)}{field("publisher","出版社")}{field("publication_year","出版年")}{field("isbn","ISBN",32)}{field("series","丛书名")}{field("series_number","丛书号",80)}{field("version_label","版次",120)}</>}{kind==="thesis"?<>{field("degree_institution","学位授予单位")}{field("degree_type","学位类型",120)}</>:null}{["report","other"].includes(kind)?field("report_institution","责任或发布机构"):null}</div></section>
    <section><h2><b>4</b>已有作品查找 <small>（避免重复）</small></h2><form className={styles.search} onSubmit={event=>{event.preventDefault();setSearch((query.trim()||form.work.title.trim()).slice(0,160));setPage(1);}}><Search size={17}/><input aria-label="查找已有作品" maxLength={160} value={query} onChange={event=>setQuery(event.target.value)} placeholder={form.work.title||"题名、责任者、ISBN 或 DOI"}/><button className={styles.primary}>搜索</button></form><div className={styles.matches}>{matching.map(row=><button key={row.id} data-selected={selection?.id===row.id} disabled={locked||Boolean(current)||!row.editions.length} onClick={()=>choose(row)}><span className={styles.radio}/>{row.cover_url?<img src={apiEndpoint(row.cover_url.slice(4))} alt="" loading="lazy"/>:<BookOpen size={25}/>}<span><strong>{row.title}</strong><small>{kinds[row.document_type]} · {row.editions[0]?.contributors.map(person=>person.name).join("、")||"责任者待核对"}</small></span><small>{row.editions.length} 个版本 ›</small></button>)}{!workspace.loading&&search&&!matching.length?<p>未找到对应馆内作品，可继续手动填写。检索结果不会自动建立关联。</p>:null}{workspace.loading?<p role="status">正在读取馆内书目…</p>:null}</div>{search?<div className={styles.pager}><button disabled={!workspace.data||workspace.data.page<=1||workspace.loading} onClick={()=>setPage(workspace.data!.page-1)}>上一页</button><span>{workspace.data?.page||page} / {workspace.data?.pages||1}</span><button disabled={!workspace.data||workspace.data.page>=workspace.data.pages||workspace.loading} onClick={()=>setPage(workspace.data!.page+1)}>下一页</button></div>:null}{selection&&!current?<button disabled={locked} onClick={()=>{setMode("new_work");setSelection(null);setEditionId("");}}>核对后仍建立独立作品</button>:null}</section></div>
    <aside className={styles.preview}><header><h2>{selection?"选择的作品与版本":"预览"}</h2>{source?<Link href={source}>查看作品详情 →</Link>:<button onClick={()=>document.getElementById("manual-title")?.focus()}>编辑预览</button>}</header><div className={styles.previewIdentity}>{selection?.cover_url?<img src={apiEndpoint(selection.cover_url.slice(4))} alt={`${selection.title}封面`}/>:<div className={styles.noCover}><BookOpen size={38}/><small>尚未添加封面</small></div>}<div><h3>{form.work.title||"题名尚未填写"}</h3><p>{form.contributors.filter(row=>row.name).map(row=>`${row.name}（${roles[row.role]}）`).join("、")||"责任者待补充"}</p><span>{kinds[kind]}</span>{form.work.abstract?<p className={styles.abstract}>{form.work.abstract}</p>:null}</div></div><section><h2>{selection?"版本信息（当前编辑）":"关键信息"}</h2>{selection&&!current?<><label>选择已有版本<select disabled={locked} value={editionId} onChange={event=>setEditionId(event.target.value)}>{selection.editions.map(row=><option key={row.id} value={row.id}>{row.label}</option>)}</select></label><div className={styles.versionActions}><button disabled={locked} aria-pressed={mode==="new_version"} onClick={()=>setMode("new_version")}><Plus size={15}/> 新增版本</button><button disabled={locked} aria-pressed={mode==="use_edition"} onClick={()=>{setMode("use_edition");setPrefills({});}}>使用已有版本</button></div><p>{mode==="use_edition"?"继续到已有版本，不将当前新建表单覆盖到已有书目。":"归入此作品，保留新版本的出版信息。"}</p></>:null}<dl>{Object.entries(mode==="use_edition"&&edition?edition.bibliography:form.bibliography).filter(([,value])=>value!==""&&value!==null).map(([key,value])=><div key={key}><dt>{({publication_place:"出版地",publisher:"出版社",publication_year:"出版年",isbn:"ISBN",doi:"DOI",series:"丛书名",series_number:"丛书号",container_title:"论文集",version_label:"版次",journal_title:"期刊",volume:"卷",issue:"期",page_range:"页码",degree_institution:"授予单位",degree_type:"学位类型",report_institution:"责任机构",extent:"篇幅"} as Record<string,string>)[key]||key}</dt><dd>{value}</dd></div>)}</dl></section><section><h2>后续文件补充</h2><div className={styles.supplements}><div className={styles.upload}><Upload size={24}/><strong>上传 PDF 文件</strong><p>在对应版本补充文件，核对后生成或采用阅读副本。</p>{current?<Link href={source.replace("?edition=", "/files?edition=")+"&tab=files"}>选择文件</Link>:<button disabled={locked} onClick={()=>void save(true)}>保存并选择文件</button>}</div><div className={styles.upload}><FileText size={24}/><strong>其他补充材料</strong><p>补充说明、相关链接及 DOCX、TIFF 原件。</p>{current?<Link href={source.replace("?edition=", "/files?edition=")+"&tab=files&support=1"}>添加附件或说明</Link>:<button disabled={locked} onClick={()=>void save(true,false,true)}>保存并添加附件</button>}</div></div><small>先保存当前出版版本再补文件；补充说明和链接仅管理可见，保存不会自动发布。</small></section></aside></div>
    <footer className={styles.mobileActions}>{actions}</footer><Dialog open={duplicate!==null} onRequestClose={()=>{if(!command.busy)setDuplicate(null);}} className={styles.dialog} aria-label="核对相似作品"><h2>发现同名的已有作品</h2><p>正在核对《{duplicate?.title}》。同名不代表同一作品，请查看现有版本后明确选择。</p>
      {duplicates.loading?<p role="status">正在读取同名作品…</p>:null}{duplicates.error?<p role="alert">{duplicates.error}<button onClick={duplicates.reload}>重新读取</button></p>:null}
      {duplicates.data?.results.map(row=><div key={row.id}><button disabled={locked||!row.editions.length} onClick={()=>choose(row)}>{row.title} · {row.editions.length} 个版本 · 选择此作品</button>{!row.editions.length?<small>此作品尚无出版版本，请先在馆藏工作页核对。</small>:null}</div>)}
      {duplicates.data&&!duplicates.error?<div className={styles.pager}><button disabled={locked||duplicates.data.page<=1} onClick={()=>setDuplicatePage(duplicates.data!.page-1)}>上一页</button><span>共 {duplicates.data.count} 部同名作品 · {duplicates.data.page} / {duplicates.data.pages}</span><button disabled={locked||duplicates.data.page>=duplicates.data.pages} onClick={()=>setDuplicatePage(duplicates.data!.page+1)}>下一页</button></div>:null}
      <div className={styles.actions}><button disabled={command.busy} onClick={()=>setDuplicate(null)}>返回核对</button><button disabled={locked||duplicates.loading||Boolean(duplicates.error)||!duplicates.data} onClick={()=>void save(duplicate?.files??false,true,duplicate?.support??false)}>确认是不同作品，仍新建</button></div></Dialog>
  </main>;
}
