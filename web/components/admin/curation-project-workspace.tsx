"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Archive, ArrowDown, ArrowUp, BookOpen, Copy, FileText, FolderPlus, LockKeyhole, Plus, Search, Users, X, ChevronRight, ChevronLeft, SlidersHorizontal, MoreHorizontal, GripVertical, Pencil, Clock3 } from "lucide-react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { adminListHref, safeAdminHref } from "@/lib/admin-route-context";
import type { components } from "@/lib/api/generated/schema";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useCatalogCommand } from "./workflow/use-intake-command";
import { PrivateMediaImage } from "./media/media-crop";
import { ReaderViewport } from "./curation/issue-publication-review";
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
type Materials=components["schemas"]["ProjectMaterials"];
type Sources=components["schemas"]["ProjectSources"];
type Preview=components["schemas"]["ProjectPreview"];
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
  const [filterOpen,setFilterOpen]=useState(false),[dragArticle,setDragArticle]=useState(""),[checked,setChecked]=useState<string[]>([]);
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
  function moveArticle(target:string){if(!project||!dragArticle||dragArticle===target||locked)return;const ids=project.article_ids.filter(id=>id!==dragArticle),index=ids.indexOf(target);if(index<0)return;ids.splice(index,0,dragArticle);setDragArticle("");const next=action("reorder",{article_ids:ids});if(next)void command.send(next).then(accept);}
  useEffect(()=>setChecked([]),[selected,project?.version]);
  const isEmpty=Boolean(data&&!data.results.length);
  const error=command.error||detail.error||list.error;
  return <main className={styles.page+" "+(isEmpty?styles.emptyDirectory:"")} data-mobile-selection={Boolean(params.get("project"))} aria-busy={command.busy}>
    <header className={styles.header}><div><nav className={styles.eyebrow} aria-label="当前位置"><span>内容</span><ChevronRight size={12}/><Link href="/admin/recommendations">特别策划</Link><ChevronRight size={12}/><span>策划项目与文章管理</span></nav><h1>策划项目与文章管理</h1><p>围绕问题持续策划文章、专题和原文展览。</p></div><div className={styles.actions}>
      {project?<button type="button" disabled={locked||!data?.can_create} onClick={()=>ask("duplicate")}><Copy size={15}/>复制为新策划</button>:null}
      {project?<button type="button" className={styles.primary} disabled={locked||!project.can_edit} onClick={()=>open("article")}><Plus size={16}/>新建文章</button>:<button type="button" className={styles.primary} disabled={locked||!data?.can_create} onClick={()=>open("create")}><Plus size={16}/>新建策划</button>}
      <details className={styles.more}><summary aria-label="更多策划操作"><MoreHorizontal size={18}/></summary><div><button type="button" disabled={locked||!data?.can_create} onClick={()=>open("create")}><FolderPlus size={15}/>新建策划</button>{project?.can_manage?<><button type="button" disabled={locked} onClick={()=>open("attach")}>加入已有文章</button><button type="button" disabled={locked} onClick={()=>ask(project.archived_at?"restore":"archive")}><Archive size={15}/>{project.archived_at?"恢复到列表":"归档项目"}</button></>:null}<Link href="/admin/recommendations?view=legacy">未归组与全部可见文章</Link><Link href="/admin/recommendations?view=home">首页推荐编排</Link></div></details>
    </div></header>
    {error?<p role="alert" className={styles.notice}>{error}<button type="button" onClick={()=>{list.reload();detail.reload();}}>重新读取</button></p>:null}
    {message?<p role="status" className={styles.notice}>{message}</p>:null}
    {command.recovery?<aside className={styles.notice}><p>原操作的结果尚未确认。请查回原记录，避免重复建立项目或文章。</p><div className={styles.actions}><button type="button" disabled={command.busy} onClick={()=>void command.lookup().then(accept)}>查回原结果</button>{command.canRetry?<button type="button" disabled={command.busy} onClick={()=>void command.send().then(accept)}>重试原请求</button>:null}<button type="button" disabled={command.busy} onClick={()=>void command.lookup(true).then(accept)}>停止未执行请求</button></div></aside>:null}
    <div className={styles.columns}>
      <aside className={styles.directory} aria-label="策划项目目录"><nav className={styles.filters} aria-label="项目筛选">{scopes.slice(0,4).map(([key,label])=><button type="button" key={key} aria-pressed={(params.get("scope")||"all")===key} onClick={()=>navigate({scope:key,page:1,project:null,articles_page:1,tab:"articles"})}>{label}{data?` (${data.summary[key]??0})`:""}</button>)}</nav>
        <button type="button" className={styles.backList} onClick={()=>navigate({project:null})}><ChevronLeft size={16}/>返回全部策划</button><div className={styles.searchRow}><form className={styles.search} onSubmit={search}><Search size={17}/><input aria-label="搜索策划项目或文章" placeholder="搜索策划或文章…" value={query} onChange={event=>setQuery(event.target.value)}/><button type="submit" className={styles.srOnly}>搜索</button></form><button type="button" className={styles.filterToggle} aria-label="筛选策划项目" aria-expanded={filterOpen} onClick={()=>setFilterOpen(!filterOpen)}><SlidersHorizontal size={17}/></button></div>
        {filterOpen?<label className={styles.scopeSelect}>项目范围<select value={params.get("scope")||"all"} onChange={event=>navigate({scope:event.target.value,page:1,project:null,articles_page:1})}>{scopes.map(([key,label])=><option key={key} value={key}>{label}{data?" ("+(data.summary[key]??0)+")":""}</option>)}</select></label>:null}
        {list.loading?<p role="status">正在读取项目…</p>:null}
        {data?.results.map(row=><button type="button" key={row.id} className={styles.projectCard} aria-pressed={selected===row.id} onClick={()=>navigate({project:row.id,tab:"articles",articles_page:1})}><span><strong>{row.title}</strong><span className={styles.intro}>{row.introduction||row.question||"尚未填写策划简介"}</span><span className={styles.tags}><span>专题策划</span><span>{row.archived_at?"已归档":row.published_count?`${row.published_count} 篇已公开`:"草稿"}</span></span><small>{new Date(row.updated_at).toLocaleDateString("zh-CN")} 更新 · {row.article_count} 篇文章</small></span><span className={styles.cardImage}>{row.cover_url?<PrivateMediaImage owner={owner} path={row.cover_url} alt="项目封面"/>:<BookOpen size={25}/>}</span></button>)}
        {data&&!data.results.length?<div className={styles.empty}><FileText size={56} strokeWidth={1}/><h2>{params.get("q")?"没有匹配的项目":"暂无策划项目"}</h2><p>从一个问题开始，策划专题文章或原文展览。</p>{data.can_create?<button type="button" disabled={locked} className={styles.primary} onClick={()=>open("create")}><Plus size={16}/>新建策划</button>:null}</div>:null}
        {data&&data.pages>1?<Pagination page={data.page} pages={data.pages} onPage={page=>navigate({page,project:null,articles_page:1})}/>:null}

      </aside>
      <section className={styles.detail} aria-label="当前策划项目">
        {detail.loading&&!project?<p role="status">正在读取项目内容…</p>:null}
        {project?<>
          <div className={styles.toolbar}><span className={styles.tags}><span>专题策划</span><span>{project.archived_at?"已归档":project.published_count?"含公开文章":"草稿"}</span></span><span className={styles.muted}>最近更新 {date(project.updated_at)}</span><button type="button" onClick={()=>open("preview")}>预览策划页</button>{project.can_manage?<button type="submit" form="curation-project-settings" className={styles.primary} disabled={locked||!dirty||tab!=="settings"||!project.can_edit} title={tab==="settings"?"保存当前策划设置":"编辑策划设置后可保存"}>保存</button>:null}</div>
          {project.archived_at?<p className={styles.notice}>项目已归档。文章、原文和公开版本保留。{project.can_manage?<button type="button" disabled={locked} onClick={()=>ask("restore")}>恢复项目</button>:null}</p>:null}
          <div className={styles.projectIntro}><div><h2>{project.title}</h2><p>{project.introduction||"尚未填写简介"}</p><div className={styles.questionLabel}><h3>研究问题</h3>{project.can_manage&&project.can_edit?<button type="button" onClick={()=>navigate({tab:"settings"})}><Pencil size={12}/>编辑</button>:null}</div><p className={styles.question}>{project.question||"尚未填写研究问题。"}</p></div><aside className={styles.facts}><h3>策划设置</h3><dl><div><dt>负责人</dt><dd><span className={styles.avatar} aria-hidden="true">{Array.from(project.owner.name)[0]}</span>{project.owner.name}</dd></div><div><dt>协作者</dt><dd>{project.collaborators.length?<button type="button" className={styles.collaborators} onClick={()=>navigate({tab:"settings"})} title={project.collaborators.map(row=>row.name).join("、")}><span>{project.collaborators.slice(0,2).map(person=><i className={styles.avatar} key={person.id}>{Array.from(person.name)[0]}</i>)}</span>{project.collaborators.length} 人<ChevronRight size={12}/></button>:"尚未加入"}</dd></div><div><dt>预期发布</dt><dd>{project.planned_for||"尚未安排"}</dd></div><div><dt>可见范围</dt><dd>{project.visibility==="team"?<><LockKeyhole size={13}/>仅项目团队</>:<><Users size={13}/>馆内编辑</>}</dd></div></dl></aside></div>
          <div className={styles.tabLine}><nav className={styles.tabs} aria-label="项目内容">{[["articles",`文章 (${project.article_count})`],["materials","已有材料"],["missing","待补证据"],["settings","策划设置"]].map(([key,label])=><button type="button" key={key} aria-current={tab===key?"page":undefined} onClick={()=>navigate({tab:key})}>{label}</button>)}</nav><button type="button" className={styles.primary} disabled={locked||!project.can_edit} onClick={()=>open("article")}><Plus size={15}/>新建文章</button></div>
          {tab==="articles"?<>{checked.length?<div className={styles.selection}><span>已选择 {checked.length} 篇文章</span><button type="button" onClick={()=>open("preview")}>预览所选文章</button><button type="button" onClick={()=>setChecked([])}>取消选择</button></div>:null}<div className={styles.table}><table><thead><tr><th className={styles.selectionCell}><input type="checkbox" aria-label="选择当前页全部文章" checked={Boolean(project.articles.length)&&project.articles.every(row=>checked.includes(row.id))} onChange={event=>setChecked(event.target.checked?project.articles.map(row=>row.id):[])}/></th><th>标题</th><th>作者</th><th>进度状态</th><th>最近编辑</th><th>操作</th></tr></thead><tbody>{project.articles.map(article=><tr key={article.id} className={checked.includes(article.id)?styles.checkedArticle:undefined} onDragOver={event=>{if(dragArticle&&project.can_manage&&project.can_edit&&!locked)event.preventDefault();}} onDrop={event=>{event.preventDefault();moveArticle(article.id);}}><td className={styles.selectionCell}><button type="button" className={styles.dragHandle} aria-label={"拖动排序"+article.title+"，也可使用更多操作中的上移下移"} draggable={!locked&&project.can_manage&&project.can_edit} disabled={locked||!project.can_manage||!project.can_edit} onDragStart={event=>{event.dataTransfer.setData("text/plain",article.id);setDragArticle(article.id);}} onDragEnd={()=>setDragArticle("")}><GripVertical size={15}/></button><input type="checkbox" aria-label={"选择"+article.title} checked={checked.includes(article.id)} onChange={event=>setChecked(event.target.checked?[...checked,article.id]:checked.filter(id=>id!==article.id))}/></td><td><div className={styles.articleTitle}><span className={styles.articleImage}>{article.cover_url?<PrivateMediaImage owner={owner} path={article.cover_url} alt="文章封面"/>:<FileText size={22}/>}</span><div><Link href={safeAdminHref(article.edit_url)}>{article.title}</Link><p>{article.introduction}</p></div></div></td><td>{article.public_byline||"尚未署名"}</td><td><span className={styles.state} data-state={article.published?"published":"draft"}><i/>{article.published?"已公开":"草稿"}</span>{article.published&&article.has_unpublished_changes?<small className={styles.draftNote}>有新草稿</small>:null}{Boolean(article.source_problem_count)?<Link className={styles.sourceProblem} href={safeAdminHref(article.edit_url)+"?tab=body"}>存在引用问题 ({article.source_problem_count})</Link>:null}</td><td><small>{date(article.saved_at)}</small><small>{article.saved_by}</small></td><td className={styles.articleActions}><Link className={styles.editLink} href={safeAdminHref(article.edit_url)}>{project.can_edit?"编辑":"查看"}</Link><details className={styles.more}><summary aria-label={article.title+"更多操作"}><MoreHorizontal size={16}/></summary><div><Link href={safeAdminHref(article.edit_url)}>{project.can_edit&&article.has_unpublished_changes?"继续编辑草稿":"查看文章"}</Link><Link href={safeAdminHref(article.edit_url)+"/preview"}>预览已保存版本</Link>{article.public_url?<Link href={article.public_url}>预览公开版</Link>:null}{project.can_manage&&project.can_edit?<><button type="button" disabled={locked||project.article_ids[0]===article.id} onClick={()=>reorder(article.id,-1)}><ArrowUp size={14}/>上移</button><button type="button" disabled={locked||project.article_ids.at(-1)===article.id} onClick={()=>reorder(article.id,1)}><ArrowDown size={14}/>下移</button></>:null}</div></details></td></tr>)}</tbody></table></div>{!project.articles.length?<div className={styles.empty}><FileText size={30}/><h3>项目中还没有文章</h3><p>建立文章草稿，或将自己创建的未归组文章加入项目。</p></div>:null}</>:null}
          {tab==="materials"||tab==="missing"?<ProjectMaterials key={`${project.id}:${project.version}:${tab}`} owner={owner} project={project} missing={tab==="missing"}/>:null}
          {tab==="settings"?<ProjectForm key={`${project.id}:${formEpoch}`} owner={owner} initial={project} disabled={locked||!project.can_manage||!project.can_edit} onDirty={setDirty} onSave={values=>command.send({action:"save",project_id:project.id,expected_version:project.version,values}).then(accept)}><div className={styles.actions}>{project.can_manage?<button type="button" disabled={locked} onClick={()=>ask(project.archived_at?"restore":"archive")}><Archive size={14}/>{project.archived_at?"恢复项目":"归档项目"}</button>:null}</div></ProjectForm>:null}
          {tab==="articles"&&project.articles_pages>1?<Pagination page={project.articles_page} pages={project.articles_pages} onPage={articles_page=>navigate({articles_page})}/>:null}
          {tab==="articles"?<div className={styles.bottom}><section><h3>最近编辑</h3>{project.activity.length?project.activity.slice(0,5).map(row=><p key={row.id}><Clock3 size={12}/><span>{row.actor} · {activity[row.action]||"项目操作"}</span><small>{date(row.at)}</small></p>):<p>暂无项目操作记录。文章修订保存在各自的版本记录中。</p>}</section><ProjectPendingSummary key={project.version} owner={owner} project={project}/></div>:null}
        </>:!detail.loading&&!isEmpty?<div className={styles.empty}><BookOpen size={36}/><h2>选择一个策划项目</h2><p>在左侧选择项目，或从一个新的问题开始。</p></div>:null}
      </section>
    </div>
    {data?.can_create&&!isEmpty?<button type="button" className={styles.mobileCreate} aria-label="新建策划" disabled={locked} onClick={()=>open("create")}><Plus size={22}/></button>:null}
    <Dialog open={Boolean(dialog)} onRequestClose={closeDialog} className={dialog==="preview"?styles.preview:styles.dialog} aria-labelledby="project-dialog-title"><header className={styles.sectionActions}><h2 id="project-dialog-title">{dialog==="create"?"建立新的策划项目":dialog==="article"?"新建文章草稿":dialog==="attach"?"加入已有文章":"策划内容预览"}</h2><button type="button" aria-label="关闭" disabled={command.busy} onClick={closeDialog}><X size={18}/></button></header>
      {command.error?<p role="alert" className={styles.notice}>{command.error}</p>:null}{dialog==="create"?<ProjectForm owner={owner} disabled={locked} onDirty={setDirty} onSave={values=>command.send({action:"create",values}).then(accept)}/>:null}
      {dialog==="article"?<form className={styles.form} onSubmit={event=>{event.preventDefault();const next=action("create_article",{title:articleTitle.trim()});if(next)void command.send(next).then(accept);}}><label>文章标题<input required maxLength={600} value={articleTitle} onChange={event=>setArticleTitle(event.target.value)}/></label><p>加入「{project?.title}」，沿用项目可见范围，创建后进入原文章编辑器。</p><button type="submit" className={styles.primary} disabled={locked||!articleTitle.trim()}>创建并开始编辑</button></form>:null}
      {dialog==="attach"&&project?<AttachArticles owner={owner} disabled={locked} onAttach={(id,version)=>{const next=action("attach_article",{article_id:id,article_version:version});if(next)setConfirmation(next);}}/>:null}
      {dialog==="preview"&&project?<ProjectPreview key={project.id} owner={owner} project={project} selectedIds={checked}/>:null}
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
  return <div className={styles.form}><form id={initial?"curation-project-settings":"curation-project-create"} onSubmit={event=>{event.preventDefault();if(!disabled&&!changed&&dirty&&values.title.trim())void onSave({...values,title:values.title.trim()});}}/>
    {dirty?<p role="status" className={styles.notice}>项目设置尚未保存。</p>:null}
    {changed?<p role="alert" className={styles.notice}>项目已由其他操作更新。当前输入保留，请先复制需要保留的文字，再离开设置并重新打开核对。</p>:null}
    <fieldset disabled={disabled||changed}>
      <label>策划标题<input form={initial?"curation-project-settings":"curation-project-create"} value={values.title} maxLength={600} required onChange={event=>setValues({...values,title:event.target.value})}/></label>
      <label>简短介绍<textarea rows={2} maxLength={3000} value={values.introduction} onChange={event=>setValues({...values,introduction:event.target.value})}/></label>
      <label>研究问题<textarea rows={4} maxLength={4000} value={values.question} onChange={event=>setValues({...values,question:event.target.value})}/></label>
      <div className={styles.formGrid}><label>预期发布日期<input type="date" value={values.planned_for||""} onChange={event=>setValues({...values,planned_for:event.target.value||null})}/></label><label>可见范围<select value={values.visibility} onChange={event=>setValues({...values,visibility:event.target.value as Values["visibility"]})}><option value="team">仅项目团队</option><option value="staff">馆内编辑</option></select></label></div>
      <p className={styles.muted}>此日期只记录计划。文章仍须逐篇审核发布；更改项目可见范围不撤回已经公开的文章。</p>
      <PeoplePicker owner={owner} selected={people} onChange={rows=>{setPeople(rows);setValues({...values,collaborator_ids:rows.map(row=>Number(row.id))});}}/>
      <details><summary>项目封面与图片出处</summary><p className={styles.muted}>图片来自馆内共享媒体库，项目问题与文章草稿按项目范围访问。</p>{values.cover_rendition_id?<><PrivateMediaImage owner={owner} path={`/api/catalog/admin/media/renditions/${values.cover_rendition_id}/file/`} alt="所选项目封面"/><button type="button" onClick={()=>setValues({...values,cover_rendition_id:null})}>取消项目选图</button></>:null}<InlineMediaPicker selectedRenditionId={values.cover_rendition_id} onSelect={id=>setValues({...values,cover_rendition_id:id})}/></details>
      <button type="submit" form={initial?"curation-project-settings":"curation-project-create"} className={styles.primary} disabled={!values.title.trim()||!dirty}>{initial?"保存项目设置":"建立项目"}</button>
    </fieldset>{children}
  </div>;
}

function PeoplePicker({owner,selected,onChange}:{owner:string;selected:Person[];onChange:(people:Person[])=>void}){
  const [query,setQuery]=useState(""),[search,setSearch]=useState(""),[opened,setOpened]=useState(false),[page,setPage]=useState(1);
  const resource=useOwned<People>(owner,opened?`${endpoint}people/?${new URLSearchParams({q:search,page:String(page)})}`:""),data=resource.data;
  return <section className={styles.people}><h3>协作者</h3><div className={styles.actions}>{selected.map(person=><button type="button" key={person.id} onClick={()=>onChange(selected.filter(row=>row.id!==person.id))}>{person.name}<X size={12}/><span className={styles.srOnly}>移除协作者</span></button>)}<button type="button" onClick={()=>setOpened(!opened)}><Users size={14}/>{opened?"收起账户选择":"添加馆内协作者"}</button></div>{opened?<><div className={styles.search}><input aria-label="搜索编辑账户公开名称" placeholder="搜索显示名称" value={query} onChange={event=>setQuery(event.target.value)}/><button type="button" onClick={()=>{setSearch(query);setPage(1);}}>搜索</button></div>{resource.error?<p role="alert">{resource.error}</p>:null}{resource.loading?<p role="status">正在读取编辑账户…</p>:null}<div className={styles.peopleResults}>{data?.results.filter(person=>person.id!==owner).map(person=><button type="button" key={person.id} disabled={selected.some(row=>row.id===person.id)||selected.length>=30} onClick={()=>onChange([...selected,person])}>{person.name}{selected.some(row=>row.id===person.id)?" · 已加入":" ＋"}</button>)}</div>{data&&data.pages>1?<Pagination page={data.page} pages={data.pages} onPage={setPage}/>:null}<p className={styles.muted}>最多30位协作者。这里只显示馆内名称，不展示邮箱与账户凭据。</p></>:null}</section>;
}

function AttachArticles({owner,disabled,onAttach}:{owner:string;disabled:boolean;onAttach:(id:string,version:string)=>void}){
  const [page,setPage]=useState(1),resource=useOwned<Articles>(owner,`/catalog/admin/recommendation-issues/?unassigned=1&mine=1&page=${page}`),data=resource.data;
  return <section><p>选择自己创建、尚未归组的文章。加入后保留原身份、版本与公开状态。</p>{resource.error?<p role="alert">{resource.error}</p>:null}{resource.loading?<p role="status">正在读取文章…</p>:null}{data?.results.map(row=><article key={row.id} className={styles.attachRow}><div><h3>{row.title}</h3><p>{row.introduction}</p></div><button type="button" disabled={disabled||!row.id||!row.edit_version} onClick={()=>onAttach(row.id!,row.edit_version!)}>加入项目</button></article>)}{data&&!data.results.length?<p className={styles.empty}>没有可加入的未归组文章。</p>:null}{data?<Pagination page={data.page} pages={Math.max(1,Math.ceil(data.count/data.page_size))} onPage={setPage}/>:null}</section>;
}


function ProjectMaterials({owner,project,missing}:{owner:string;project:Project;missing:boolean}){
  const [kind,setKind]=useState("appendix");
  return <><nav className={styles.filters} aria-label="项目材料范围">{[["appendix","附录材料"],["body","正文引用"],["selection","选材候选"]].map(([value,label])=><button type="button" key={value} aria-pressed={kind===value} onClick={()=>setKind(value)}>{label}</button>)}</nav>{kind==="appendix"?<ProjectAppendix owner={owner} project={project} missing={missing}/>:<ProjectSources key={kind} owner={owner} project={project} missing={missing} origin={kind}/>}</>;
}

function ProjectAppendix({owner,project,missing}:{owner:string;project:Project;missing:boolean}){
  const [query,setQuery]=useState(""),[q,setQ]=useState(""),[page,setPage]=useState(1);
  const resource=useOwned<Materials>(owner,`${endpoint}${project.id}/materials/?${new URLSearchParams({q,scope:missing?"missing":"all",page:String(page)})}`),data=resource.data;
  const states:Record<string,string>={available:"原文可读",bibliographic:"书目已公开，原文待补",planned:"待补材料",unavailable:"当前来源不可用"};
  return <section className={styles.materials}>
    <form className={styles.search} onSubmit={event=>{event.preventDefault();setQ(query);setPage(1);}}><Search size={16}/><input aria-label="在项目全部附录材料中搜索" placeholder="搜索材料题名、作者或所属文章…" value={query} onChange={event=>setQuery(event.target.value)}/><button type="submit">搜索</button></form>
    {resource.error?<p role="alert" className={styles.notice}>{resource.error}<button type="button" onClick={resource.reload}>重新读取</button></p>:null}
    {resource.loading?<p role="status">正在汇总整个项目的已保存材料…</p>:null}
    {data?<><p className={styles.muted}>{data.article_count} 篇文章 · {data.totals.all} 项附录引用 · {data.totals.missing} 项待补原文或来源。当前匹配 {data.count} 项。</p><p className={styles.muted}>{data.scope_notice}</p>
      {data.results.map((item,index)=><article key={`${item.article_id}:${item.id||index}`}><BookOpen size={19}/><div><h3>{item.title||"题名待补"}</h3><p>{item.authors||"作者待补"} {item.version_note}</p><small>来自 {item.article_title} · {states[item.status||""]||"状态待核对"}</small>{item.note?<p>{item.note}</p>:null}<div className={styles.actions}>{item.reader_url?<Link href={item.reader_url}>打开原文</Link>:null}{item.workbench_url?<Link href={safeAdminHref(item.workbench_url)}>补充馆藏资料</Link>:null}</div></div><Link href={`/admin/recommendations/issues/${item.article_id}`}>核对文章材料</Link></article>)}
      {!data.results.length?<p className={styles.empty}>{q?"没有匹配的材料。":missing?"项目附录材料当前没有待补原文或不可用来源。请同时核对正文与选材来源。":"项目尚未保存附录材料。请进入文章加入真实来源。"}</p>:null}
      <Pagination page={data.page} pages={data.pages} onPage={setPage}/>
    </>:null}

  </section>;
}

function ProjectSources({owner,project,missing,origin}:{owner:string;project:Project;missing:boolean;origin:string}){
  const [query,setQuery]=useState(""),[q,setQ]=useState(""),[page,setPage]=useState(1);
  const resource=useOwned<Sources>(owner,`${endpoint}${project.id}/sources/?${new URLSearchParams({q,origin,scope:missing?"missing":"all",page:String(page)})}`),data=resource.data;
  const states:Record<string,string>={public:"来源可公开",private:"尚未公开",unavailable:"来源失效或修订改变"};
  return <section className={styles.materials}>
    <form className={styles.search} onSubmit={event=>{event.preventDefault();setQ(query);setPage(1);}}><Search size={16}/><input aria-label="搜索所属文章与引用上下文" placeholder="搜索所属文章、引用上下文…" value={query} onChange={event=>setQuery(event.target.value)}/><button type="submit">搜索</button></form>
    {resource.error?<p role="alert" className={styles.notice}>{resource.error}<button type="button" onClick={resource.reload}>重新读取</button></p>:null}
    {resource.loading?<p role="status">正在读取项目全部已保存来源…</p>:null}
    {data?<><p className={styles.muted}>{data.article_count} 篇文章 · {data.totals.body} 处正文引用 · {data.totals.selection} 项选材候选 · {data.totals.missing} 项待核对。当前匹配 {data.count} 项。</p><p className={styles.muted}>{data.scope_notice}</p>
      {data.results.map((item,index)=><article key={`${item.article_id}:${item.block_id||"selection"}:${index}`}><BookOpen size={19}/><div><h3>{item.title}</h3><small>{item.article_title} · {item.position!=null?`第 ${item.position+1} 个正文区块`:"选材候选"} · {states[item.status]}</small>{item.context?<p className={styles.sourceContext}>{item.context}</p>:null}<div className={styles.actions}>{item.reader_url?<Link href={item.reader_url}>定位原文</Link>:null}{item.status==="public"&&item.source_url?<Link href={item.source_url}>查看来源</Link>:null}{item.edit_url?<Link href={safeAdminHref(item.edit_url)}>核对源资料</Link>:null}</div></div><Link href={`/admin/recommendations/issues/${item.article_id}?tab=${origin==="selection"?"selection":"body"}${item.block_id?`&block=${item.block_id}`:""}`}>处理文章引用</Link></article>)}
      {!data.results.length?<p className={styles.empty}>{q?"没有匹配的来源。":missing?"当前来源范围没有待补项。完整发布检查仍须核对文章内容与权利说明。":"当前范围尚未保存来源。"}</p>:null}
      <Pagination page={data.page} pages={data.pages} onPage={setPage}/><p className={styles.muted}>来源状态读取于 {date(data.checked_at)}</p>
    </>:null}
  </section>;
}

function ProjectPreview({owner,project,selectedIds=[]}:{owner:string;project:Project;selectedIds?:string[]}){
  const resource=useOwned<Preview>(owner,`${endpoint}${project.id}/preview/`),data=resource.data;
  const [mode,setMode]=useState("saved"),[selected,setSelected]=useState(""),[device,setDevice]=useState("desktop");
  const articles=(data?.results||[]).filter(row=>(!selectedIds.length||selectedIds.includes(row.id))&&(mode==="saved"||row.public_url));
  const current=articles.find(row=>row.id===selected)||articles[0];
  const src=current?(mode==="public"?current.public_url:`/admin/recommendations/issues/${current.id}/preview?frame=1&version=${encodeURIComponent(current.edit_version)}`):"";
  return <div className={styles.previewContent}>
    <p className={styles.eyebrow}>策划项目 · {project.visibility==="team"?"仅项目团队":"馆内编辑"}</p><h2>{project.title}</h2><p>{project.introduction}</p><blockquote>{project.question||"研究问题待补"}</blockquote>
    <p className={styles.muted}>项目介绍与问题仅用于内部策划。下面按项目顺序查看各篇文章；公开版本由各文章的明确发布决定。</p>
    <nav className={styles.filters} aria-label="预览版本">{[["saved","当前已保存稿"],["public","目前公开版本"]].map(([value,label])=><button type="button" key={value} aria-pressed={mode===value} onClick={()=>setMode(value)}>{label}</button>)}</nav>
    {resource.error?<p role="alert" className={styles.notice}>{resource.error}<button type="button" onClick={resource.reload}>重新读取</button></p>:null}
    {resource.loading?<p role="status">正在读取项目文章目录…</p>:null}
    {data?<><p className={styles.muted}>项目共 {data.count} 篇，当前范围 {articles.length} 篇。目录读取于 {date(data.checked_at)}。</p>
      <label className={styles.previewSelect}>选择文章<select value={current?.id||""} onChange={event=>setSelected(event.target.value)}>{articles.map((row,index)=><option key={row.id} value={row.id}>{index+1}. {mode==="public"?row.public_title:row.title}</option>)}</select></label>
      {current?<><article><h3>{mode==="public"?current.public_title:current.title}</h3><p>{mode==="public"?current.public_introduction:current.introduction}</p><small>{mode==="public"?current.published_byline:current.public_byline} · {mode==="public"?"当前公开版本":current.has_unpublished_changes?"含未发布修改":"最近保存版本"}</small></article>
        <div className={styles.sectionActions}><div className={styles.actions}><button type="button" aria-pressed={device==="desktop"} onClick={()=>setDevice("desktop")}>桌面</button><button type="button" aria-pressed={device==="mobile"} onClick={()=>setDevice("mobile")}>移动</button></div><a href={src} target="_blank" rel="noopener">打开完整预览 ↗</a></div>
        <ReaderViewport key={`${src}:${device}:${data.checked_at}`} src={src} device={device}/>
        <div className={styles.sectionActions}><Link href={`/admin/recommendations/issues/${current.id}`}>返回这篇文章核对与发布 →</Link><button type="button" onClick={resource.reload}>读取最新保存版本</button></div>
      </>:<p className={styles.empty}>{mode==="public"?"项目目前没有公开文章。":"项目尚未建立文章。"}</p>}
    </>:null}
  </div>;
}

function ProjectPendingSummary({owner,project}:{owner:string;project:Project}){
  const materials=useOwned<Materials>(owner,`${endpoint}${project.id}/materials/?scope=missing`);
  const sources=useOwned<Sources>(owner,`${endpoint}${project.id}/sources/?scope=missing`);
  return <section><h3>待补证据</h3><p>全项目已保存材料与来源</p>
    {materials.loading||sources.loading?<p role="status">正在读取…</p>:null}
    {materials.error||sources.error?<p role="alert">{materials.error||sources.error}<button type="button" onClick={()=>{materials.reload();sources.reload();}}>重新读取</button></p>:null}
    {materials.data&&sources.data?<><p>{materials.data.totals.missing} 项附录待补 · {sources.data.totals.missing} 处正文或选材来源待核对</p>
      {materials.data.results.slice(0,2).map((row,index)=><Link key={`${row.article_id}:${index}`} href={`/admin/recommendations/issues/${row.article_id}`}>{row.title||"材料题名待补"} →</Link>)}
      {sources.data.results.slice(0,2).map((row,index)=><Link key={`${row.article_id}:${index}`} href={`/admin/recommendations/issues/${row.article_id}?tab=${row.origin==="selection"?"selection":"body"}${row.block_id?`&block=${row.block_id}`:""}`}>{row.article_title} · {row.title} →</Link>)}
      {!materials.data.totals.missing&&!sources.data.totals.missing?<p>当前未发现待补来源，文章内容与权利说明仍须在发布前核对。</p>:null}
    </>:null}<Link href={`/admin/recommendations?project=${project.id}&tab=missing`}>查看全部待补证据 →</Link>
  </section>;
}
