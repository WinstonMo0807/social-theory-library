"use client";

import Link from "next/link";
import { Dialog } from "@/components/ui/dialog";
import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { topicCuration, type TopicCurationFields } from "./topic-fields";
import styles from "./topic-editor.module.css";

type Row = { id: string; name: string; parent_id: string | null; editorial_status: string; children_count: number };
type Page = { count: number; page: number; total_pages: number; results: Row[] };
type Impact = { topic_id: string; parent_id: string | null; parent_changed: boolean; descendant_count: number; public_descendant_count: number; content_counts: Record<string, number>; can_publish: boolean; problems: { field: string; detail: string }[] };

export function TopicTreeBranch({ parent = "", owner, selected, ancestors = [], query = "", onChoose }: { parent?: string; owner: string; selected?: string; ancestors?: string[]; query?: string; onChoose?: (row: { id: string; name: string }) => void }) {
  const [page, setPage] = useState(1), [expanded, setExpanded] = useState<string[]>([]);
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<Page>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource = usePersistentWorkspace<Page>(`/catalog/admin/topics/organization/?${new URLSearchParams({parent,page:String(page),q:query})}`,owner,undefined,load);
  if (resource.error) return <p role="alert">{resource.error}<button type="button" onClick={resource.reload}>重新读取</button></p>;
  if (!resource.data) return <p role="status">正在读取主题…</p>;
  return <><ul className={styles.tree}>{resource.data.results.map(row => <li key={row.id}><div data-selected={selected === row.id}>
    <button type="button" disabled={!row.children_count || Boolean(query)} aria-expanded={expanded.includes(row.id)} aria-label={`展开${row.name}的子主题`} onClick={() => setExpanded(values => values.includes(row.id) ? values.filter(id => id !== row.id) : [...values,row.id])}>{row.children_count && !query ? expanded.includes(row.id) ? "⌄" : "›" : "·"}</button>
    <>{onChoose ? <button type="button" className={styles.chooseParent} aria-pressed={selected === row.id} onClick={() => onChoose(row)}>{row.name}</button> : <Link href={`/admin/topics/${row.id}`} aria-current={selected === row.id ? "page" : undefined}>{row.name}</Link>}</><small title="直接子主题数量">{row.children_count || ""}</small>
    </div>{expanded.includes(row.id) && !query ? ancestors.includes(row.id) || ancestors.length >= 20 ? <p>层级需在原资料中核对。</p> : <TopicTreeBranch parent={row.id} owner={owner} selected={selected} ancestors={[...ancestors,row.id]} onChoose={onChoose}/> : null}</li>)}</ul>{!resource.data.results.length ? <p className={styles.muted}>此处尚无主题。</p> : null}{resource.data.total_pages > 1 ? <nav className={styles.pages} aria-label="主题结构分页"><button type="button" disabled={page<=1} onClick={()=>setPage(value=>value-1)}>上一页</button><span>{resource.data.page}/{resource.data.total_pages}</span><button type="button" disabled={page>=resource.data.total_pages} onClick={()=>setPage(value=>value+1)}>下一页</button></nav> : null}</>;
}

export function TopicOrganizationTree({ selected }: { selected?: string | null }) {
  const owner = String(useAdminSession()?.id || ""), [input,setInput]=useState(""), [query,setQuery]=useState(""),[expanded,setExpanded]=useState(false);
  return <aside className={styles.structure} data-expanded={expanded}><header><h2>主题结构</h2><button type="button" className={styles.treeToggle} aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>展开 / 收起</button><Link href="/admin/topics/new">＋新建主题</Link></header><div className={styles.structureBody}><div className={styles.treeSearch}><input aria-label="查找主题结构" maxLength={240} value={input} placeholder="查找名称或别名" onChange={event=>setInput(event.target.value)} onKeyDown={event=>{if(event.key === "Enter" && !event.nativeEvent.isComposing && event.keyCode !== 229){event.preventDefault();setQuery(input.trim());}}}/><button type="button" onClick={()=>setQuery(input.trim())}>查找</button></div><TopicTreeBranch key={`${owner}:${query}`} owner={owner} selected={selected || undefined} query={query}/><p className={styles.muted}>显示当前主题层级；已公开主题的层级草稿在发布后生效。</p></div></aside>;
}

export function TopicOrganizationChecks({ topicId, name, value }: { topicId: string | null; name: string; value: TopicCurationFields }) {
  const owner = String(useAdminSession()?.id || ""), [query,setQuery]=useState(""), [impact,setImpact]=useState<{key:string;data:Impact}|null>(null), [error,setError]=useState(""), [busy,setBusy]=useState(false);
  const [similarPage, setSimilarPage] = useState(1);
  const body = JSON.stringify({parent:value.parentId||null,curation:topicCuration(value)}), identity=`${owner}:${topicId}:${body}`, result=impact?.key===identity?impact.data:null;
  const load = useCallback((path:string,signal:AbortSignal)=>apiRequest<Page>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const similar=usePersistentWorkspace<Page>(query?`/catalog/admin/topics/organization/?${new URLSearchParams({q:query,exclude:topicId||"",page:String(similarPage)})}`:"",owner,undefined,load);
  async function inspect() {
    if (!topicId || busy) return; setBusy(true);setError("");
    const signal=AbortSignal.timeout(30000);
    try { const data=await withPrivateOwner(owner,()=>apiRequest<Impact>(`/catalog/admin/topics/${topicId}/organization-preview/`,{method:"POST",body,signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal);if(data.topic_id!==topicId)throw Error("预览对象不一致，请重新读取。");setImpact({key:identity,data}); }
    catch(reason){setImpact(null);setError(reason instanceof Error?reason.message:"调整预览暂不可用");}finally{setBusy(false);}
  }
  return <section className={styles.checks}><div><button type="button" disabled={!name.trim()} onClick={()=>{setQuery(name.trim());setSimilarPage(1);similar.reload();}}>查看已有相似名称</button>{topicId?<button type="button" disabled={busy} onClick={()=>void inspect()}>{busy?"正在核对…":"核对层级与关联内容"}</button>:null}</div>
    <Dialog open={Boolean(query)} data-editor-transient className={styles.hierarchyDialog} onRequestClose={()=>setQuery("")} aria-label="已有主题名称提示">
      <header><h2>已有主题名称提示</h2><button type="button" onClick={()=>setQuery("")}>关闭</button></header>
      <p>按名称和别名查找“{query}”。查看已有主题后，再决定是否继续编辑当前档案。</p>
      {similar.error?<p role="alert">{similar.error}<button type="button" onClick={similar.reload}>重新查找</button></p>:!similar.data?<p role="status">正在查找…</p>:<>
        <ul className={styles.similarTopics}>{similar.data.results.map(row=><li key={row.id}><div><strong>{row.name}</strong><small>{row.children_count} 个直接子主题</small></div><Link href={`/admin/topics/${row.id}`} target="_blank" rel="noopener noreferrer">查看<span className={styles.liveNotice}>，在新页面打开{row.name}</span></Link></li>)}</ul>
        <p>{similar.data.count?`共 ${similar.data.count} 个名称或别名匹配，本页 ${similar.data.results.length} 项。` : "目前没有匹配名称。"}</p>
        {similar.data.total_pages>1?<nav className={styles.pages} aria-label="已有主题匹配分页"><button type="button" disabled={similar.data.page<=1} onClick={()=>setSimilarPage(similar.data!.page-1)}>上一页</button><span>{similar.data.page} / {similar.data.total_pages}</span><button type="button" disabled={similar.data.page>=similar.data.total_pages} onClick={()=>setSimilarPage(similar.data!.page+1)}>下一页</button></nav>:null}
      </>}
      <footer><p>查看其他主题会保留当前表单。此处不创建或合并主题。</p><div><button type="button" onClick={()=>setQuery("")}>继续编辑当前主题</button></div></footer>
    </Dialog>
    {error?<p role="alert">{error}</p>:null}{result?<section aria-live="polite"><h3>本次调整的影响</h3>{result.parent_changed?<p>上级变化涉及 {result.descendant_count} 个后代主题，其中 {result.public_descendant_count} 个已公开；原身份和关联材料保留。</p>:<p>上级主题未变化。</p>}<p>当前可公开关联：{result.content_counts.works} 部作品 · {result.content_counts.scholars} 位学者 · {result.content_counts.knowledge} 个知识条目 · {result.content_counts.articles} 篇策划。</p>{result.problems.map((problem,index)=><p role="alert" key={index}>{problem.detail}</p>)}{!result.can_publish?<p>层级或关联内容仍需补充，发布时会再次核对。</p>:<p>此预览不保存内容。保存与发布仍需分别确认。</p>}</section>:null}
  </section>;
}
