"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { PageHeader } from "@/components/admin-ui";
import { FixedPageEditor } from "../curation/fixed-page-editor";
import { EntityPicker } from "../forms/workflow-fields";
import { SiteHeader } from "@/components/site-header";
import { WorkDetailView } from "@/components/work-detail-view";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { Work } from "@/lib/data";
import { ApiRequestError, getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { createManualCatalog, type CatalogingSession, type ManualCatalogInput } from "@/lib/api/cataloging";
import { useApiResource } from "@/lib/api/use-api-resource";
import { WorkflowEditor } from "./workflow-editor";
import { safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";

export function ManualCatalogForm() {
  const router = useRouter(), params = useSearchParams();
  const returnHref = safeAdminHref(params.get("return_to"));
  const requestKey = useRef("");
  const pendingInput = useRef<ManualCatalogInput | null>(null);
  const submitting = useRef(false);
  const initial = {title:"",subtitle:"",abstract:"",publisher:"",publication_year:"",version_label:"",document_type:"book",language:"zh-CN"};
  const [draft,setDraft]=useState(initial);
  const [authors,setAuthors]=useState<Array<{id:string;name:string}>>([]), [topics,setTopics]=useState<Array<{id:string;name:string}>>([]);
  const [step,setStep]=useState("identity"), [busy,setBusy]=useState(false), [error,setError]=useState(""), [uncertain,setUncertain]=useState(false);
  const dirty=useUnsavedForm({draft,authors,topics},{draft:initial,authors:[],topics:[]});
  const steps=[{id:"identity",label:"填写书目"},{id:"relations",label:"关联作者与主题"},{id:"preview",label:"检查书目"}];
  const index=steps.findIndex(row=>row.id===step);
  async function save() {
    if(submitting.current)return;
    submitting.current=true;requestKey.current ||= createRequestKey();setBusy(true);setError("");
    pendingInput.current ||= {...draft,document_type:draft.document_type as ManualCatalogInput["document_type"],publication_year:draft.publication_year ? Number(draft.publication_year) : null,author_ids:authors.map(row=>row.id),topic_ids:topics.map(row=>row.id),request_key:requestKey.current};
    try {
      const session=await createManualCatalog(pendingInput.current);
      const destination=`/admin/cataloging/${encodeURIComponent(session.id)}`;
      router.push(params.has("return_to") ? withAdminReturn(destination,returnHref,index===2 ? "publication" : "work") : `${destination}#${index===2 ? "publication" : "work"}`);
    } catch(reason) {
      const rejected=reason instanceof ApiRequestError && reason.status>=400 && reason.status<500;
      if(rejected){pendingInput.current=null;requestKey.current="";}
      setUncertain(!rejected);setError(reason instanceof Error ? reason.message : "保存结果尚未确认，输入已保留，请重试核对。");setBusy(false);submitting.current=false;
    }
  }
  const work:Work={id:"",workId:"",editionId:"",slug:"",title:draft.title || "未填写题名",subtitle:draft.subtitle,publisher:draft.publisher,versionLabel:draft.version_label,author:authors.map(row=>row.name).join("、"),authors:authors.map(row=>({name:row.name})),year:draft.publication_year,kind:({book:"图书",journal_article:"期刊论文",journal_issue:"整期期刊",thesis:"学位论文",report:"研究报告"} as Record<string,Work["kind"]>)[draft.document_type],school:"",summary:draft.abstract,cover:"paper",pages:0,language:draft.language,topics:topics.map(row=>({name:row.name,slug:""}))};
  return <div className="admin-page manual-catalog-reference"><PageHeader title="新建书目" description="先建立书目信息，稍后补充PDF。保存后不会发布，也不会与其他馆藏合并。" actions={<Link href={returnHref}>返回原页面</Link>}/>
    <nav className="knowledge-reference-steps" aria-label="新建书目步骤">{steps.map((row,i)=><button type="button" key={row.id} aria-current={step===row.id ? "step" : undefined} disabled={busy} onClick={()=>setStep(row.id)}><span>{i+1}</span><strong>{row.label}</strong></button>)}</nav>
    {error ? <p role="alert">{error}</p> : null}{uncertain ? <p role="status">保存结果未确认。请重试核对同一次保存，当前输入保持不变。</p> : null}
    <FixedPageEditor sections={steps} navigationSections={[]} activeSection={step} onSectionChange={setStep} dirty={dirty} preview={<><SiteHeader preview previewPath="/explore"/><WorkDetailView work={work} preview={{publicationState:"draft",pdfPreviewUrl:"",returnHref}} footer={null}/></>}
      fields={<form onSubmit={event=>{event.preventDefault();void save();}} className="fixed-editor-fields"><fieldset disabled={busy || uncertain}><div hidden={step!=="identity"}><h2>书目信息</h2>{([["title","书名",600],["subtitle","副标题",600],["publisher","出版社",300],["version_label","出版版本",120]] as const).map(([key,label,max])=><label key={key}>{label}<input value={draft[key]} maxLength={max} onChange={event=>setDraft({...draft,[key]:event.target.value})}/></label>)}<label>出版年份<input type="number" min={1} max={9999} value={draft.publication_year} onChange={event=>setDraft({...draft,publication_year:event.target.value})}/></label><label>简介<textarea rows={5} maxLength={20000} value={draft.abstract} onChange={event=>setDraft({...draft,abstract:event.target.value})}/></label><details><summary>类型与语言</summary><label>文献类型<select value={draft.document_type} onChange={event=>setDraft({...draft,document_type:event.target.value})}><option value="book">图书</option><option value="journal_article">期刊论文</option><option value="journal_issue">整期期刊</option><option value="thesis">学位论文</option><option value="report">研究报告</option></select></label><label>正文语言<select value={draft.language} onChange={event=>setDraft({...draft,language:event.target.value})}><option value="zh-CN">简体中文</option><option value="zh-TW">繁体中文</option><option value="en">英文</option><option value="mixed">多语种</option></select></label></details><aside className="manual-catalog-file"><strong>暂不上传PDF</strong><p>可在后续补充，仅有书目信息也可以保存。</p></aside></div>
      <div hidden={step!=="relations"}><h2>关联作者与主题</h2><EntityPicker label="选择馆内作者" endpoint="/catalog/admin/people/" nameField="preferred_name" values={authors} onChange={rows=>setAuthors(rows.filter(row=>row.id).map(row=>({id:row.id!,name:row.name})))}/><EntityPicker label="选择馆内主题" endpoint="/catalog/admin/topics/" values={topics} onChange={rows=>setTopics(rows.filter(row=>row.id).map(row=>({id:row.id!,name:row.name})))}/><p>未找到的人物可在保存书目后，通过作者编辑器明确新建。不会依据姓名自动合并。</p></div>
      <div hidden={step!=="preview"}><h2>检查书目</h2><h3>{draft.title || "题名尚未填写"}</h3><p>{authors.map(row=>row.name).join("、") || "作者尚未关联"}</p><p>{[draft.publisher,draft.publication_year,draft.version_label].filter(Boolean).join(" · ")}</p><p>{draft.abstract}</p><p>保存后进入馆藏工作页，发布需要另行确认。</p></div></fieldset></form>}
      toolbar={<footer className="knowledge-reference-step-actions"><button type="button" className="button secondary" disabled={busy || index===0} onClick={()=>setStep(steps[index-1].id)}>上一步</button><button type="button" className="button secondary" disabled={busy} onClick={()=>void save()}>{busy ? "正在保存…" : uncertain ? "重试核对保存" : "保存草稿"}</button>{index<2 ? <button type="button" className="button" disabled={busy || uncertain} onClick={()=>setStep(steps[index+1].id)}>下一步：{steps[index+1].label} →</button> : <button type="button" className="button" disabled={busy} onClick={()=>void save()}>保存并继续整理 →</button>}</footer>}/>
  </div>;
}

export function CatalogingWorkbench({ sessionId }: { sessionId: string }) {
  const params = useSearchParams();
  const returnHref = safeAdminHref(params.get("return_to"));
  const { data, error, loading, retry } = useApiResource<{ session: CatalogingSession }>(
    `/catalog/admin/cataloging-sessions/${encodeURIComponent(sessionId)}/?workspace=0`, getServerSessionCredential(),
  );
  if (error) return <section className="admin-panel" role="alert"><p>{error}</p><button type="button" onClick={retry}>重新读取</button><Link href={returnHref}>返回原页面</Link></section>;
  if (loading || !data) return <p className="admin-list-state" role="status">正在读取编目会话…</p>;
  const session = data.session;
  if (["published", "abandoned"].includes(session.status)) return <section className="admin-panel"><p>本次编目已结束，草稿、馆藏和原始文件均保留。</p>{session.work_id && session.edition_id ? <Link href={withAdminReturn(`/admin/library/works/${session.work_id}?edition=${session.edition_id}`, returnHref, "publication")}>核对当前出版版本及公开结果</Link> : null}<Link href={returnHref}>返回原页面</Link></section>;
  if (!session.work_id || !session.edition_id) return <section className="admin-panel"><p role="status">上传尚未建立作品版本，文件处理完成后可继续编目。</p><button type="button" onClick={retry}>刷新处理结果</button><Link href={withAdminReturn(session.upload_item_id ? `/admin/uploads?item=${encodeURIComponent(session.upload_item_id)}` : "/admin/uploads", returnHref)}>查看原上传来源</Link></section>;
  return <WorkflowEditor key={session.id} mode="maintenance" workId={session.work_id} editionId={session.edition_id} />;
}
