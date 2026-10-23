"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Archive, ArrowDown, ArrowUp, BookOpen, Copy, FileText, FolderPlus, LockKeyhole, Plus, Search, Users, X } from "lucide-react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { adminListHref, safeAdminHref } from "@/lib/admin-route-context";
import type { components } from "@/lib/api/generated/schema";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useCatalogCommand } from "./workflow/use-intake-command";
import { PrivateMediaImage } from "./media/media-crop";
import { InlineMediaPicker } from "./curation/inline-media-picker";
import { Dialog } from "@/components/ui/dialog";
import styles from "./curation-project-workspace.module.css";

type Directory=components["schemas"]["ProjectDirectory"];
type Project=components["schemas"]["ProjectDetail"];
type Person=components["schemas"]["ProjectPerson"];
type Values=components["schemas"]["ProjectValuesRequest"];
type Command=Omit<components["schemas"]["ProjectCommandRequest"],"request_id">;
type Receipt=components["schemas"]["ProjectReceipt"];
type People=components["schemas"]["ProjectPeople"];
type Articles=components["schemas"]["AdminRecommendationIssueCollection"];
const endpoint="/catalog/admin/curation-projects/";
const scopes=[["all","全部项目"],["mine","我负责的"],["draft","草稿"],["published","已公开"],["archived","已归档"]];
const activity:Record<string,string>={create:"建立项目",save:"更新策划设置",duplicate:"复制为新策划",archive:"归档项目",restore:"恢复项目",create_article:"建立文章草稿",attach_article:"加入已有文章",reorder:"调整文章顺序","recommendation_issue.save_draft":"保存文章草稿","recommendation_issue.publish":"发布文章修订"};
const date=(value:string|null|undefined)=>value?new Date(value).toLocaleString("zh-CN",{hour12:false}):"尚未记录";
const emptyValues:Values={title:"",question:"",introduction:"",visibility:"team",collaborator_ids:[],cover_rendition_id:null,planned_for:null};
const valuesOf=(p:Project):Values=>({title:p.title,question:p.question,introduction:p.introduction,visibility:p.visibility,collaborator_ids:p.collaborators.map(row=>Number(row.id)),cover_rendition_id:p.cover_rendition_id,planned_for:p.planned_for});
function useOwned<T>(owner:string,path:string){const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<T>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);return usePersistentWorkspace<T>(path,owner,undefined,load);}

export function CurationProjectWorkspace(){const user=useAdminSession(),[epoch,setEpoch]=useState(0);useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);return user?<Workspace key={`${user.id}:${epoch}`} owner={String(user.id)}/>:<p role="status">正在核对策划账户…</p>;}

function Workspace({owner}:{owner:string}){
  const params=useSearchParams(),router=useRouter(),pathname=usePathname();
  const [query,setQuery]=useState(params.get("q")||""),[message,setMessage]=useState(""),[dialog,setDialog]=useState<"create"|"article"|"attach"|"preview"|null>(null),[confirmation,setConfirmation]=useState<Command|null>(null),[dirty,setDirty]=useState(false),[formEpoch,setFormEpoch]=useState(0),[articleTitle,setArticleTitle]=useState("");
  const filters=new URLSearchParams();for(const key of ["q","scope","page"])if(params.get(key))filters.set(key,params.get(key)!);
  const list=useOwned<Directory>(owner,`${endpoint}?${filters}`),data=list.data;
  const selected=params.get("project")||data?.results[0]?.id||"";
  const detail=useOwned<Project>(owner,selected?`${endpoint}${selected}/?articles_page=${params.get("articles_page")||1}`:""),project=detail.data;
  const tab=["articles","materials","missing","settings"].includes(params.get("tab")||"")?params.get("tab")!:"articles";
  const command=useCatalogCommand<Command,Receipt>(owner,endpoint,`stl-curation-project:${owner}`);
  const locked=!command.ready||command.busy||Boolean(command.recovery);
  const articleDirty=useUnsavedForm(dialog==="article"?articleTitle:"","");
  function canLeave(){return !(dirty||articleDirty)||window.confirm("当前项目设置尚未保存，放弃这些输入并继续吗？");}
  function navigate(values:Record<string,string|number|null>){if(!canLeave())return;setDirty(false);router.push(adminListHref(pathname,params.toString(),values));}
  function open(value:typeof dialog){if(!canLeave())return;setDirty(false);if(tab==="settings")router.push(adminListHref(pathname,params.toString(),{tab:"articles"}));setDialog(value);setArticleTitle("");}
  function closeDialog(){if(command.busy||!canLeave())return;setDirty(false);setDialog(null);}
  async function accept(result:Receipt|null){
    if(!result)return false;
    setMessage(result.state==="cancelled"?"尚未执行的原请求已停止。":result.message);setConfirmation(null);
    if(result.state==="applied"){
      setDirty(false);setDialog(null);setFormEpoch(value=>value+1);
      if(result.next_url)router.push(safeAdminHref(result.next_url));
    }
    list.reload();detail.reload();return result.state==="applied";
  }
  function action(action:Command["action"],extra:Partial<Command>={}){return project?{action,project_id:project.id,expected_version:project.version,...extra}:null;}
  function ask(actionName:Command["action"]){const next=action(actionName);if(next&&canLeave()){setDirty(false);setConfirmation(next);}}
  function reorder(id:string,offset:number){if(!project)return;const ids=[...project.article_ids],index=ids.indexOf(id),target=index+offset;if(index<0||target<0||target>=ids.length)return;[ids[index],ids[target]]=[ids[target],ids[index]];const next=action("reorder",{article_ids:ids});if(next)void command.send(next).then(accept);}
  function search(event:FormEvent){event.preventDefault();navigate({q:query||null,page:1,project:null,articles_page:1,tab:"articles"});}
  const missing=project?.materials.filter(row=>row.status!=="available")||[];
  const error=command.error||detail.error||list.error;
  return <main className={styles.page} aria-busy={command.busy}>
    <header className={styles.header}><div><p className={styles.eyebrow}>内容 / 特别策划</p><h1>策划项目与文章管理</h1><p>围绕问题持续策划文章、专题和原文展览。</p></div><div className={styles.actions}>
      {project?<button type="button" disabled={locked||!data?.can_create} onClick={()=>ask("duplicate")}><Copy size={15}/>复制为新策划</button>:null}
      <button type="button" className={styles.primary} disabled={locked||!project?.can_edit} onClick={()=>open("article")}><Plus size={16}/>新建文章</button>
      <button type="button" disabled={locked||!data?.can_create} onClick={()=>open("create")}><FolderPlus size={16}/>新建项目</button>
    </div></header>
    {error?<p role="alert" className={styles.notice}>{error}<button type="button" onClick={()=>{list.reload();detail.reload();}}>重新读取</button></p>:null}
    {message?<p role="status" className={styles.notice}>{message}</p>:null}
    {command.recovery?<aside className={styles.notice}><p>原操作的结果尚未确认。请查回原记录，避免重复建立项目或文章。</p><div className={styles.actions}><button type="button" disabled={command.busy} onClick={()=>void command.lookup().then(accept)}>查回原结果</button>{command.canRetry?<button type="button" disabled={command.busy} onClick={()=>void command.send().then(accept)}>重试原请求</button>:null}<button type="button" disabled={command.busy} onClick={()=>void command.lookup(true).then(accept)}>停止未执行请求</button></div></aside>:null}
    <div className={styles.columns}>
      <aside className={styles.directory} aria-label="策划项目目录"><nav className={styles.filters} aria-label="项目筛选">{scopes.map(([key,label])=><button type="button" key={key} aria-pressed={(params.get("scope")||"all")===key} onClick={()=>navigate({scope:key,page:1,project:null,articles_page:1,tab:"articles"})}>{label}{data?` (${data.summary[key]??0})`:""}</button>)}</nav>
        <form className={styles.search} onSubmit={search}><Search size={17}/><input aria-label="搜索策划项目或文章" placeholder="搜索策划或文章…" value={query} onChange={event=>setQuery(event.target.value)}/><button type="submit">搜索</button></form>
        {list.loading?<p role="status">正在读取项目…</p>:null}
        {data?.results.map(row=><button type="button" key={row.id} className={styles.projectCard} aria-pressed={selected===row.id} onClick={()=>navigate({project:row.id,tab:"articles",articles_page:1})}><span><strong>{row.title}</strong><span className={styles.intro}>{row.introduction||row.question||"尚未填写策划简介"}</span><span className={styles.tags}><span>专题策划</span><span>{row.archived_at?"已归档":row.published_count?`${row.published_count} 篇已公开`:"草稿"}</span></span><small>{new Date(row.updated_at).toLocaleDateString("zh-CN")} 更新 · {row.article_count} 篇文章</small></span><span className={styles.cardImage}>{row.cover_url?<PrivateMediaImage owner={owner} path={row.cover_url} alt="项目封面"/>:<BookOpen size={25}/>}</span></button>)}
        {data&&!data.results.length?<div className={styles.empty}><BookOpen size={32}/><h2>{params.get("q")?"没有匹配的项目":"还没有策划项目"}</h2><p>从一个研究问题开始，逐步组织文章与材料。</p>{data.can_create?<button type="button" disabled={locked} onClick={()=>open("create")}>建立第一个项目</button>:null}</div>:null}
        {data?<Pagination page={data.page} pages={data.pages} onPage={page=>navigate({page,project:null,articles_page:1})}/>:null}
        <footer className={styles.directoryFooter}><Link href="/admin/recommendations?view=legacy">未归组与全部可见文章{data?` (${data.unassigned_count} 篇未归组)`:""}</Link><Link href="/admin/recommendations?view=home">首页推荐编排</Link></footer>
      </aside>
      <section className={styles.detail} aria-label="当前策划项目">
        {detail.loading&&!project?<p role="status">正在读取项目内容…</p>:null}
        {project?<>
          <div className={styles.toolbar}><span className={styles.tags}><span>专题策划</span><span>{project.archived_at?"已归档":project.published_count?"含公开文章":"草稿"}</span></span><span className={styles.muted}>最近更新 {date(project.updated_at)}</span><button type="button" onClick={()=>open("preview")}>预览策划内容</button>{project.can_manage?<button type="button" className={styles.primary} disabled={locked} onClick={()=>navigate({tab:"settings"})}>策划设置</button>:null}</div>
          {project.archived_at?<p className={styles.notice}>项目已归档。文章、原文和公开版本保留。{project.can_manage?<button type="button" disabled={locked} onClick={()=>ask("restore")}>恢复项目</button>:null}</p>:null}
          <div className={styles.projectIntro}><div><h2>{project.title}</h2><p>{project.introduction||"尚未填写简介"}</p><div className={styles.questionLabel}><h3>研究问题</h3>{project.can_manage&&project.can_edit?<button type="button" onClick={()=>navigate({tab:"settings"})}>编辑</button>:null}</div><p className={styles.question}>{project.question||"尚未填写研究问题。"}</p></div><aside className={styles.facts}><h3>策划设置</h3><dl><div><dt>负责人</dt><dd>{project.owner.name}</dd></div><div><dt>协作者</dt><dd>{project.collaborators.map(row=>row.name).join("、")||"尚未加入"}</dd></div><div><dt>预期发布</dt><dd>{project.planned_for||"尚未安排"}</dd></div><div><dt>可见范围</dt><dd>{project.visibility==="team"?<><LockKeyhole size={13}/>仅项目团队</>:<><Users size={13}/>馆内编辑</>}</dd></div></dl></aside></div>
          <nav className={styles.tabs} aria-label="项目内容">{[["articles",`文章 (${project.article_count})`],["materials",`已有材料 (${project.materials.length})`],["missing",`待补证据 (${missing.length+project.problems.length})`],["settings","策划设置"]].map(([key,label])=><button type="button" key={key} aria-current={tab===key?"page":undefined} onClick={()=>navigate({tab:key})}>{label}</button>)}</nav>
          {tab==="articles"?<><div className={styles.sectionActions}><p className={styles.muted}>公开版本与新草稿分别保留。</p><div className={styles.actions}>{project.can_manage&&project.can_edit?<button type="button" disabled={locked} onClick={()=>open("attach")}>加入已有文章</button>:null}<button type="button" className={styles.primary} disabled={locked||!project.can_edit} onClick={()=>open("article")}><Plus size={14}/>新建文章</button></div></div><div className={styles.table}><table><thead><tr><th>标题</th><th>作者</th><th>进度状态</th><th>最近编辑</th><th>操作</th></tr></thead><tbody>{project.articles.map(article=><tr key={article.id}><td><div className={styles.articleTitle}><span className={styles.articleImage}>{article.cover_url?<PrivateMediaImage owner={owner} path={article.cover_url} alt="文章封面"/>:<FileText size={22}/>}</span><div><Link href={safeAdminHref(article.edit_url)}>{article.title}</Link><p>{article.introduction}</p></div></div></td><td>{article.public_byline||"尚未署名"}</td><td><span className={styles.state}>{article.published?"已公开":"草稿"}</span>{article.published&&article.has_unpublished_changes?<small>有未发布修改</small>:null}</td><td><small>{date(article.saved_at)}</small><small>{article.saved_by}</small></td><td><Link href={safeAdminHref(article.edit_url)}>{project.can_edit?"编辑":"查看"}</Link>{project.can_manage&&project.can_edit?<div className={styles.order}><button type="button" aria-label={`上移${article.title}`} disabled={locked||project.article_ids[0]===article.id} onClick={()=>reorder(article.id,-1)}><ArrowUp size={14}/></button><button type="button" aria-label={`下移${article.title}`} disabled={locked||project.article_ids.at(-1)===article.id} onClick={()=>reorder(article.id,1)}><ArrowDown size={14}/></button></div>:null}</td></tr>)}</tbody></table></div>{!project.articles.length?<div className={styles.empty}><FileText size={30}/><h3>项目中还没有文章</h3><p>建立文章草稿，或将自己创建的未归组文章加入项目。</p></div>:null}</>:null}
          {tab==="materials"||tab==="missing"?<section className={styles.materials}><p className={styles.muted}>{project.material_scope}</p>{(tab==="materials"?project.materials:missing).map((item,index)=><article key={`${item.article_id}:${item.id||index}`}><BookOpen size={19}/><div><h3>{item.title||"题名待补"}</h3><p>{item.authors||"作者待补"} {item.version_note}</p><small>来自 {item.article_title} · {item.kind==="planned"?"待补材料":item.status==="available"?"已有来源":"来源待核对"}</small>{item.note?<p>{item.note}</p>:null}</div><Link href={`/admin/recommendations/issues/${item.article_id}`}>核对材料</Link></article>)}{tab==="missing"?project.problems.map((problem,index)=><article key={`${problem.article_id}:${problem.block_id||index}`}><FileText size={19}/><div><h3>{problem.article_title}</h3><p>{problem.detail}</p><small>{problem.position!=null?`第 ${problem.position+1} 个正文区块`:"正文来源"}</small></div><Link href={`/admin/recommendations/issues/${problem.article_id}`}>处理来源</Link></article>):null}{!(tab==="materials"?project.materials.length:missing.length+project.problems.length)?<p className={styles.empty}>{tab==="materials"?"当前文章分页还没有已保存材料。":"当前文章分页未发现待补材料或正文来源问题。发布前仍须在文章中完成完整检查。"}</p>:null}</section>:null}
          {tab==="settings"?<ProjectForm key={`${project.id}:${formEpoch}`} owner={owner} initial={project} disabled={locked||!project.can_manage||!project.can_edit} onDirty={setDirty} onSave={values=>command.send({action:"save",project_id:project.id,expected_version:project.version,values}).then(accept)}><div className={styles.actions}>{project.can_manage?<button type="button" disabled={locked} onClick={()=>ask(project.archived_at?"restore":"archive")}><Archive size={14}/>{project.archived_at?"恢复项目":"归档项目"}</button>:null}</div></ProjectForm>:null}
          {tab!=="settings"?<Pagination page={project.articles_page} pages={project.articles_pages} onPage={articles_page=>navigate({articles_page})}/>:null}
          {tab==="articles"?<div className={styles.bottom}><section><h3>最近编辑</h3>{project.activity.length?project.activity.slice(0,5).map(row=><p key={row.id}><span>{row.actor} · {activity[row.action]||"项目操作"}</span><small>{date(row.at)}</small></p>):<p>暂无项目操作记录。文章修订保存在各自的版本记录中。</p>}</section><section><h3>待补证据</h3><p>{project.material_scope}</p>{missing.slice(0,3).map((row,index)=><Link key={index} href={`/admin/recommendations/issues/${row.article_id}`}>{row.title||"材料题名待补"} →</Link>)}{project.problems.length?<button type="button" onClick={()=>navigate({tab:"missing"})}>查看 {project.problems.length} 处正文来源问题 →</button>:null}{!missing.length&&!project.problems.length?<p>当前分页没有待补项。</p>:null}</section></div>:null}
        </>:!detail.loading?<div className={styles.empty}><BookOpen size={36}/><h2>选择一个策划项目</h2><p>在左侧选择项目，或从一个新的问题开始。</p></div>:null}
      </section>
    </div>
    <Dialog open={Boolean(dialog)} onRequestClose={closeDialog} className={dialog==="preview"?styles.preview:styles.dialog} aria-labelledby="project-dialog-title"><header className={styles.sectionActions}><h2 id="project-dialog-title">{dialog==="create"?"建立新的策划项目":dialog==="article"?"新建文章草稿":dialog==="attach"?"加入已有文章":"策划内容预览"}</h2><button type="button" aria-label="关闭" disabled={command.busy} onClick={closeDialog}><X size={18}/></button></header>
      {command.error?<p role="alert" className={styles.notice}>{command.error}</p>:null}{dialog==="create"?<ProjectForm owner={owner} disabled={locked} onDirty={setDirty} onSave={values=>command.send({action:"create",values}).then(accept)}/>:null}
      {dialog==="article"?<form className={styles.form} onSubmit={event=>{event.preventDefault();const next=action("create_article",{title:articleTitle.trim()});if(next)void command.send(next).then(accept);}}><label>文章标题<input required maxLength={600} value={articleTitle} onChange={event=>setArticleTitle(event.target.value)}/></label><p>加入「{project?.title}」，沿用项目可见范围，创建后进入原文章编辑器。</p><button type="submit" className={styles.primary} disabled={locked||!articleTitle.trim()}>创建并开始编辑</button></form>:null}
      {dialog==="attach"&&project?<AttachArticles owner={owner} disabled={locked} onAttach={(id,version)=>{const next=action("attach_article",{article_id:id,article_version:version});if(next)setConfirmation(next);}}/>:null}
      {dialog==="preview"&&project?<div className={styles.previewContent}><p className={styles.eyebrow}>策划草稿 · {project.visibility==="team"?"仅项目团队":"馆内编辑"}</p><h2>{project.title}</h2><p>{project.introduction}</p><blockquote>{project.question||"研究问题待补"}</blockquote><p className={styles.muted}>当前第 {project.articles_page} / {project.articles_pages} 页文章；进入文章预览查看完整正文。项目预览不改变公开内容。</p>{project.articles.map(article=><article key={article.id}><h3>{article.title}</h3><p>{article.introduction}</p><Link href={`/admin/recommendations/issues/${article.id}/preview`}>打开文章预览 →</Link></article>)}</div>:null}
    </Dialog>
    <Dialog open={Boolean(confirmation)} onRequestClose={()=>{if(!command.busy)setConfirmation(null);}} className={styles.dialog} aria-labelledby="project-confirm-title"><h2 id="project-confirm-title">{confirmation?.action==="duplicate"?"复制为新的策划项目":confirmation?.action==="archive"?"归档当前项目":confirmation?.action==="restore"?"恢复当前项目":"将原文章加入项目"}</h2><p>{confirmation?.action==="duplicate"?"复制项目问题、简介、图片与最多50篇文章的当前草稿。副本仅自己可见，可另加协作者；文章不会自动发布。":confirmation?.action==="archive"?"归档后项目停止编辑，保留文章、来源和历史。已经公开的文章继续展示，可在原发布流程单独处理。":confirmation?.action==="restore"?"恢复项目编辑，文章身份和版本保留，不自动发布或重启处理。":`原文章及历史将遵循本项目的${project?.visibility==="team"?"团队私密":"馆内编辑"}范围；已公开版本保持公开。原身份、来源与修订保留。`}</p><div className={styles.actions}><button type="button" disabled={command.busy} onClick={()=>setConfirmation(null)}>取消</button><button type="button" className={styles.primary} disabled={locked||!confirmation} onClick={()=>{if(confirmation)void command.send(confirmation).then(accept);}}>{command.busy?"正在保存…":"确认"}</button></div>{command.error?<p role="alert" className={styles.notice}>{command.error}</p>:null}</Dialog>
  </main>;
}

function Pagination({page,pages,onPage}:{page:number;pages:number;onPage:(page:number)=>void}){return <nav className={styles.pagination} aria-label="分页"><button type="button" disabled={page<=1} onClick={()=>onPage(page-1)}>上一页</button><span>{page} / {pages}</span><button type="button" disabled={page>=pages} onClick={()=>onPage(page+1)}>下一页</button></nav>;}

function ProjectForm({owner,initial,disabled,onDirty,onSave,children}:{owner:string;initial?:Project;disabled:boolean;onDirty:(value:boolean)=>void;onSave:(values:Values)=>Promise<boolean>;children?:React.ReactNode}){
  const [baseline]=useState(initial?valuesOf(initial):emptyValues),[values,setValues]=useState<Values>(baseline),[version]=useState(initial?.version),[people,setPeople]=useState<Person[]>(initial?.collaborators||[]);
  const dirty=useUnsavedForm(values,baseline);
  useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
  const changed=Boolean(initial&&initial.version!==version);
  return <div className={styles.form}>
    {dirty?<p role="status" className={styles.notice}>项目设置尚未保存。</p>:null}
    {changed?<p role="alert" className={styles.notice}>项目已由其他操作更新。当前输入保留，请先复制需要保留的文字，再离开设置并重新打开核对。</p>:null}
    <fieldset disabled={disabled||changed}>
      <label>策划标题<input value={values.title} maxLength={600} required onChange={event=>setValues({...values,title:event.target.value})}/></label>
      <label>简短介绍<textarea rows={2} maxLength={3000} value={values.introduction} onChange={event=>setValues({...values,introduction:event.target.value})}/></label>
      <label>研究问题<textarea rows={4} maxLength={4000} value={values.question} onChange={event=>setValues({...values,question:event.target.value})}/></label>
      <div className={styles.formGrid}><label>预期发布日期<input type="date" value={values.planned_for||""} onChange={event=>setValues({...values,planned_for:event.target.value||null})}/></label><label>可见范围<select value={values.visibility} onChange={event=>setValues({...values,visibility:event.target.value as Values["visibility"]})}><option value="team">仅项目团队</option><option value="staff">馆内编辑</option></select></label></div>
      <p className={styles.muted}>此日期只记录计划。文章仍须逐篇审核发布；更改项目可见范围不撤回已经公开的文章。</p>
      <PeoplePicker owner={owner} selected={people} onChange={rows=>{setPeople(rows);setValues({...values,collaborator_ids:rows.map(row=>Number(row.id))});}}/>
      <details><summary>项目封面与图片出处</summary><p className={styles.muted}>图片来自馆内共享媒体库，项目问题与文章草稿按项目范围访问。</p>{values.cover_rendition_id?<><PrivateMediaImage owner={owner} path={`/api/catalog/admin/media/renditions/${values.cover_rendition_id}/file/`} alt="所选项目封面"/><button type="button" onClick={()=>setValues({...values,cover_rendition_id:null})}>取消项目选图</button></>:null}<InlineMediaPicker selectedRenditionId={values.cover_rendition_id} onSelect={id=>setValues({...values,cover_rendition_id:id})}/></details>
      <button type="button" className={styles.primary} disabled={!values.title.trim()||!dirty} onClick={()=>void onSave({...values,title:values.title.trim()})}>{initial?"保存项目设置":"建立项目"}</button>
    </fieldset>{children}
  </div>;
}

function PeoplePicker({owner,selected,onChange}:{owner:string;selected:Person[];onChange:(people:Person[])=>void}){
  const [query,setQuery]=useState(""),[search,setSearch]=useState(""),[opened,setOpened]=useState(false),[page,setPage]=useState(1);
  const resource=useOwned<People>(owner,opened?`${endpoint}people/?${new URLSearchParams({q:search,page:String(page)})}`:""),data=resource.data;
  return <section className={styles.people}><h3>协作者</h3><div className={styles.actions}>{selected.map(person=><button type="button" key={person.id} onClick={()=>onChange(selected.filter(row=>row.id!==person.id))}>{person.name}<X size={12}/><span className={styles.srOnly}>移除协作者</span></button>)}<button type="button" onClick={()=>setOpened(!opened)}><Users size={14}/>{opened?"收起账户选择":"添加馆内协作者"}</button></div>{opened?<><div className={styles.search}><input aria-label="搜索编辑账户公开名称" placeholder="搜索显示名称" value={query} onChange={event=>setQuery(event.target.value)}/><button type="button" onClick={()=>{setSearch(query);setPage(1);}}>搜索</button></div>{resource.error?<p role="alert">{resource.error}</p>:null}{resource.loading?<p role="status">正在读取编辑账户…</p>:null}<div className={styles.peopleResults}>{data?.results.filter(person=>person.id!==owner).map(person=><button type="button" key={person.id} disabled={selected.some(row=>row.id===person.id)||selected.length>=30} onClick={()=>onChange([...selected,person])}>{person.name}{selected.some(row=>row.id===person.id)?" · 已加入":" ＋"}</button>)}</div>{data?<Pagination page={data.page} pages={data.pages} onPage={setPage}/>:null}<p className={styles.muted}>最多30位协作者。这里只显示馆内名称，不展示邮箱与账户凭据。</p></>:null}</section>;
}

function AttachArticles({owner,disabled,onAttach}:{owner:string;disabled:boolean;onAttach:(id:string,version:string)=>void}){
  const [page,setPage]=useState(1),resource=useOwned<Articles>(owner,`/catalog/admin/recommendation-issues/?unassigned=1&mine=1&page=${page}`),data=resource.data;
  return <section><p>选择自己创建、尚未归组的文章。加入后保留原身份、版本与公开状态。</p>{resource.error?<p role="alert">{resource.error}</p>:null}{resource.loading?<p role="status">正在读取文章…</p>:null}{data?.results.map(row=><article key={row.id} className={styles.attachRow}><div><h3>{row.title}</h3><p>{row.introduction}</p></div><button type="button" disabled={disabled||!row.id||!row.edit_version} onClick={()=>onAttach(row.id!,row.edit_version!)}>加入项目</button></article>)}{data&&!data.results.length?<p className={styles.empty}>没有可加入的未归组文章。</p>:null}{data?<Pagination page={data.page} pages={Math.max(1,Math.ceil(data.count/data.page_size))} onPage={setPage}/>:null}</section>;
}
