"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { DraftConflict } from "@/components/admin/curation/draft-conflict";
import type { RecommendationIssue, IssueItem } from "@/lib/api/recommendation-issues.types";
import { IssuePublicationReview, type IssuePublicationCheck } from "./curation/issue-publication-review";
import { IssueBlockView } from "@/components/public/issue-block-view";
import { IssueHistory } from "./curation/issue-history";
import { IssueCollaboration } from "./curation/issue-collaboration";
import { IssueSuggestions } from "./curation/issue-suggestions";
import { IssueSelectionWorkbench } from "./curation/issue-selection-workbench";
import { useIssueDraft, type IssueDraft } from "./curation/use-issue-draft";
import styles from "./curation/issue-editor.module.css";
import { InlineMediaPicker } from "@/components/admin/curation/inline-media-picker";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { ArticleMetadataFields, emptyArticleMetadata } from "./curation/article-metadata-fields";
import { ArticleCommentReview } from "./curation/article-comment-review";
import { ArticleBodyFields, blockNames, blockTitle } from "./curation/article-body-fields";

type EditionOption = { id: string; label?: string; publication?: { public_state?: string; catalog_revision_active?: boolean; publicly_visible?: boolean; editorial_state?: string } };

function EditionSelect({ workId, value, onChange, mode, disabled = false }: { workId: string; value: string; onChange: (value: string) => void; mode: "published" | "draft"; disabled?: boolean }) {
  const [rows, setRows] = useState<EditionOption[]>([]), [error, setError] = useState(""), [loading, setLoading] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(()=>{if(!controller.signal.aborted){setRows([]);setError("");setLoading(Boolean(workId));}});
    if (!workId) return () => controller.abort();
    void (async () => {
      const editions: EditionOption[] = [];
      let page = 1, pages = 1;
      do {
        const result = await apiRequest<{ results: EditionOption[]; total_pages: number }>(`/catalog/admin/library/works/?view=editions&work_id=${encodeURIComponent(workId)}&page=${page}`, { signal: controller.signal }, getServerSessionCredential());
        editions.push(...result.results); pages = result.total_pages; page += 1;
      } while (page <= pages && !controller.signal.aborted);
      if (!controller.signal.aborted) setRows(editions.filter(row => mode === "published" ? row.publication?.public_state === "published" && row.publication.catalog_revision_active === true : row.publication?.catalog_revision_active !== true && ["draft", "ready"].includes(row.publication?.editorial_state || "")));
    })().catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "版本读取失败。"); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [workId, mode]);
  return <label>{mode === "published" ? "准确的已公开出版版本" : "已有非公开草稿版本"}<select value={value} disabled={disabled || loading || !workId} onChange={event => onChange(event.target.value)}><option value="">{loading ? "正在读取出版版本…" : "请选择具体出版版本"}</option>{rows.map(row => <option key={row.id} value={row.id}>{row.label || "出版信息待补"}</option>)}</select>{error ? <span role="alert">{error}</span> : !loading && workId && !rows.length ? <span>当前作品没有符合条件的出版版本。</span> : null}</label>;
}

function ItemFields({ item, change, remove, onLink, canLink }: { item: IssueItem; change: (item: IssueItem) => void; remove: () => void; onLink: (workId: string, editionId: string) => void; canLink: boolean }) {
  const [linkWork, setLinkWork] = useState<{id:string;name:string}|null>(null), [linkEdition, setLinkEdition] = useState(""), [confirmed, setConfirmed] = useState(false);
  const savedPlan = Boolean(item.cataloging_session_id);
  const text = (key: "title" | "authors" | "version_note" | "isbn" | "doi", label: string) => <label>{label}<input value={item[key] || ""} onChange={event => change({ ...item, [key]: event.target.value })} /></label>;
  return <div className="issue-item-fields"><label>推荐类型<select value={item.kind} disabled={savedPlan} onChange={event => change({ ...item, kind: event.target.value as IssueItem["kind"], work_id: null, edition_id: null })}><option value="catalog">已有馆藏</option><option value="planned">计划上架</option></select></label>
    {!savedPlan ? <><EntityPicker label={item.kind === "planned" ? "复用已有非公开计划书目（可选）" : "选择已公开馆藏"} endpoint={`/catalog/admin/library/works/?view=${item.kind === "planned" ? "draft" : "published"}`} queryParam="q" nameField="title" values={item.work_id ? [{ id: item.work_id, name: item.title }] : []} onChange={values => { const value = values.at(-1); change({ ...item, work_id: value?.id || null, edition_id: null, title: value?.name || item.title }); }} />
    {item.work_id ? <EditionSelect workId={item.work_id} value={item.edition_id || ""} mode={item.kind === "planned" ? "draft" : "published"} onChange={editionId => change({ ...item, edition_id: editionId || null })} /> : null}</> : <p>这条计划已建立独立书目。后续关联已有馆藏时保留计划身份和原推介文字。</p>}
    {text("title", "题名")}{text("authors", "作者署名")}{text("version_note", "版本说明")}{text("isbn", "ISBN（有依据时填写）")}{text("doi", "DOI（有依据时填写）")}
    <label>逐项推介语<textarea rows={5} value={item.note} onChange={event => change({ ...item, note: event.target.value })} /></label>
    {item.cataloging_session_id ? <Link target="_blank" rel="noopener" href={`/admin/cataloging/${item.cataloging_session_id}`}>完善这条计划书目 ↗</Link> : item.work_id ? <Link target="_blank" rel="noopener" href={`/admin/library/works/${item.work_id}${item.edition_id ? `?edition=${item.edition_id}` : ""}`}>打开馆藏工作页 ↗</Link> : <p>{item.kind === "planned" ? "保存本期草稿时会建立可跟进的最小计划书目，不创建空白 PDF。" : "请先选择已公开馆藏和准确的出版版本。"}</p>}
    {item.match_candidates?.length ? <section className="issue-plan-matches"><h3>发现相同标识符的已上架版本</h3><p>请比较下列版次与本期所荐版本。确认后只建立馆藏关联，保留本期原文和推介语。</p>{item.match_candidates.map(match => <article key={match.edition_id}><strong>{match.title}</strong><p>{match.version_label || "版次未详"} · {match.publication_year || "年份未详"}</p><button type="button" className="button secondary" disabled={!canLink || item.linked_edition_id === match.edition_id} onClick={() => onLink(match.work_id, match.edition_id)}>{item.linked_edition_id === match.edition_id ? "已关联此版本" : "版本已核对，关联此馆藏"}</button></article>)}</section> : null}
    {savedPlan ? <section className="issue-plan-manual-link"><h3>手动关联已上架馆藏</h3><p>找不到 ISBN 或 DOI 候选时，可以选择作品并核对具体出版版本。这项操作保留本期题名、署名与推介原文。</p><EntityPicker label="查找已公开作品" endpoint="/catalog/admin/library/works/?view=published" queryParam="q" nameField="title" values={linkWork ? [linkWork] : []} onChange={values => { const selected=values.at(-1); setLinkWork(selected?.id ? {id:selected.id,name:selected.name} : null); setLinkEdition(""); setConfirmed(false); }} />{linkWork ? <EditionSelect workId={linkWork.id} value={linkEdition} mode="published" onChange={value => { setLinkEdition(value); setConfirmed(false); }} /> : null}<label className="switch-row"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={!linkEdition} />我已核对本期所荐作品和这个出版版本</label><button type="button" className="button secondary" disabled={!canLink || !linkWork || !linkEdition || !confirmed || item.linked_edition_id === linkEdition} onClick={() => { if (linkWork && confirmed) onLink(linkWork.id, linkEdition); }}>确认关联这个出版版本</button>{!canLink ? <p>请先保存本期当前修改，再确认关联。</p> : null}{item.linked_edition_id ? <p>已经关联公开版本；本期原计划文字保持不变。</p> : null}</section> : null}
    <button type="button" className="button secondary" onClick={remove}>从本期移除（保留馆藏）</button>
  </div>;
}
export function RecommendationIssueEditor({ issueId, fullPreview = false }: { issueId: string; fullPreview?: boolean }) {
  const user = useAdminSession();
  return <IssueEditorSession key={`${user?.id || "anonymous"}:${issueId}:${fullPreview}`} issueId={issueId} fullPreview={fullPreview}/>;
}
function IssueEditorSession({ issueId, fullPreview }: { issueId: string; fullPreview: boolean }) {
  const user = useAdminSession();
  const editor=useIssueDraft(issueId,user ? String(user.id) : "",false);
  const {draft,dirty,busy,initialError,message,conflict,update}=editor;
  const [active,setActive]=useState("body"),[selected,setSelected]=useState(0),[selectedBlock,setSelectedBlock]=useState("");
  const [pane,setPane]=useState("preview"),[mobile,setMobile]=useState("edit"),[history,setHistory]=useState(false),[suggestions,setSuggestions]=useState(false);
  const [publicationReview,setPublicationReview]=useState(fullPreview);
  const [materials,setMaterials]=useState(false),[assistantPending,setAssistantPending]=useState(false),[assistantReviewDirty,setAssistantReviewDirty]=useState(false);
  const canEdit=hasAdminCapability(user,"can_edit_metadata");
  if (!draft) return <section className="admin-panel" aria-busy={!initialError}><p role={initialError ? "alert" : "status"}>{initialError || "正在读取本期草稿…"}</p>{initialError ? <button type="button" className="button secondary" onClick={editor.retryLoad}>重试读取</button> : null}<p><Link href="/admin/recommendations">返回推荐与随机</Link></p></section>;
  const previewDraft: RecommendationIssue = { ...draft, curator: { name: draft.public_byline, role: draft.public_byline ? draft.article_metadata?.curator_role || "" : "", affiliation: draft.public_byline ? draft.article_metadata?.curator_affiliation || "" : "", portrait_url: draft.public_byline ? draft.curator?.portrait_url || "" : "" } };

  const field = (key: "title" | "slug" | "issue_label" | "public_byline", label: string) => <label>{label}<input readOnly={key === "slug"} value={draft[key]} onChange={event => update({ [key]: event.target.value })} /></label>;
  const canPublish = hasAdminCapability(user, "can_publish_authority");
  function linkItem(workId:string,editionId:string) {
    if(!draft || !draft.items[selected]?.id)return;
    void editor.command(`items/${draft.items[selected].id}/link/`,{edit_version:draft.edit_version,work_id:workId,edition_id:editionId,confirm_version:true},"已关联所确认的馆藏版本，本期推介文字保持不变。");
  }
  function moveItem(index: number, direction: number) { const items = [...draft!.items]; const destination = index + direction; if (destination < 0 || destination >= items.length) return; [items[index], items[destination]] = [items[destination], items[index]]; update({ items: items.map((item, position) => ({ ...item, position })) }); setSelected(destination); }
  function leaveMaterials(){if(assistantPending)return false;if(assistantReviewDirty&&!window.confirm("尚有未采用的审阅修改，返回文章会放弃这些修改。是否继续？"))return false;setMaterials(false);return true;}
  function focusBlock(id:string) {if(materials&&!leaveMaterials())return;setSelectedBlock(id);setActive("body");setMobile("edit");requestAnimationFrame(()=>document.getElementById(`editor-block-${id}`)?.scrollIntoView({block:"nearest",behavior:"auto"}));}
  function locatePublication(row:IssuePublicationCheck) {
    setPublicationReview(false);setActive(row.section);setMobile("edit");
    if(row.block_id)focusBlock(row.block_id);
    if(row.item_id){const index=draft!.items.findIndex(item=>item.id===row.item_id);if(index>=0)setSelected(index);}
  }
  if(publicationReview)return <><IssuePublicationReview editor={editor} onLocate={locatePublication} onBack={()=>setPublicationReview(false)} onHistory={()=>setHistory(true)}/>{history?<IssueHistory issueId={issueId} request={editor.request} onClose={()=>setHistory(false)} canRestore={canEdit&&!editor.disabled&&!dirty&&!conflict} onRestore={value=>{editor.restoreHistory(value);setPublicationReview(false);}}/>:null}</>;
  const previewMode=mobile==="structure" ? "structure" : pane;
  return <div className={styles.editor}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/admin/about">页面编排</Link><span>›</span><Link href="/admin/recommendations">专题编辑器</Link><span>›</span><span>{draft.title}</span></nav>
    <header className={styles.heading}><div><h1>{materials?"策划选材与智能助手":"专题编辑器与结构化内容"}</h1><p>{materials?"基于馆藏资料，为当前稿件寻找证据、提供结构建议与修改思路。":"将策划叙事与真实原文、人物、概念与路径组织成文章。"}</p></div><div className={styles.actions}><span role="status">{busy ? "正在处理…" : editor.pending ? "保存结果待核对" : dirty ? "有尚未保存的修改" : "草稿已保存"}{editor.saved?.saved_at?<small><time dateTime={editor.saved.saved_at}>{new Date(editor.saved.saved_at).toLocaleString("zh-CN",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"})}</time></small>:null}</span><button type="button" disabled={assistantPending} onClick={()=>{if(leaveMaterials()){setPane("preview");setMobile("preview");}}}>预览</button>{canEdit?<button type="button" disabled={assistantPending || editor.disabled || editor.composing || conflict || !dirty} onClick={()=>void editor.save()}>保存</button>:null}{canPublish?<button type="button" className={styles.publish} disabled={assistantPending || editor.disabled || editor.composing || conflict || dirty || !draft.has_unpublished_changes || (!draft.items.length&&!draft.body_blocks.length)} onClick={()=>{if(leaveMaterials())setPublicationReview(true);}}>发布</button>:null}<button type="button" disabled={assistantPending||editor.disabled} onClick={()=>{if(leaveMaterials())setPublicationReview(true);}}>发布检查</button><details className={styles.more}><summary aria-label="更多编辑操作">···</summary><div><button type="button" onClick={()=>setHistory(true)}>版本历史</button>{canEdit?<button type="button" onClick={()=>setSuggestions(value=>!value)}>智能材料建议</button>:null}<button type="button" disabled={assistantPending || editor.disabled || editor.composing} onClick={()=>void editor.recheck()}>重新核对来源</button><a href={`/admin/recommendations/issues/${issueId}/preview`} target="_blank" rel="noopener">打开已保存草稿预览 ↗</a>{canEdit?<label><input type="checkbox" checked={editor.autosave} onChange={event=>editor.setAutosave(event.target.checked)}/>停止输入 10 秒后保存草稿</label>:null}<small>本标签页暂存未保存输入，退出登录时清除。</small></div></details></div></header>
    {message?<p className={styles.notice} role="status">{message}</p>:null}
    {editor.storageError?<p className={styles.warning} role="alert">浏览器未能保留断线草稿，请勿刷新或关闭本页，恢复连接后手动保存。</p>:null}
    {editor.recovery?<section className={styles.warning}><h2>本标签页有尚未确认的输入</h2><p>记录于 {new Date(editor.recovery.at).toLocaleString("zh-CN")}。恢复后先核对来源与保存结果。</p><button type="button" onClick={editor.recoverLocal}>恢复本标签页输入</button><button type="button" onClick={editor.discardRecovery}>舍弃暂存，使用已保存版本</button></section>:null}
    {editor.pending&&!busy?<section className={styles.warning}><p>这次保存结果尚未确认。请先查回；重试会沿用原保存编号与原内容。</p><button type="button" onClick={()=>void editor.lookup()}>查回保存结果</button><button type="button" onClick={()=>void editor.save(false,true)}>重试原保存</button></section>:null}
    {conflict?<DraftConflict endpoint={`/catalog/admin/recommendation-issues/${issueId}/`} local={draft} loadRemote={()=>editor.request<IssueDraft>(`/catalog/admin/recommendation-issues/${issueId}/`)} onUseRemote={editor.useRemote} onKeepLocal={editor.keepLocal}/>:null}
    {draft.body_source_problems?.length?<section className={styles.warning} aria-label="待处理来源"><strong>{draft.body_source_problems.length} 个来源尚不满足公开条件</strong>{draft.body_source_problems.map((problem,index)=><p key={problem.block_id || index}>{problem.detail}<button type="button" onClick={()=>focusBlock(problem.block_id || "")}>定位区块</button></p>)}</section>:null}
    {materials&&canEdit?<IssueSelectionWorkbench draft={draft} owner={String(user!.id)} dirty={dirty} disabled={editor.disabled||conflict} pending={assistantPending} request={editor.request} auxiliary={editor.auxiliary} onChange={update} onClose={()=>{leaveMaterials();}} onPending={setAssistantPending} onReviewDirty={setAssistantReviewDirty}/>:<><nav className={styles.mobileTabs} aria-label="编辑器视图">{[["edit","编辑"],["preview","预览"],["structure","结构"]].map(([id,label])=><button type="button" key={id} aria-pressed={mobile===id} onClick={()=>{setMobile(id);if(id!=="edit")setPane(id);}}>{label}</button>)}</nav>
    <div className={styles.workspace} data-mobile={mobile}><section className={styles.editPane} aria-label="编辑文章"><nav className={styles.editorTabs} aria-label="文章设置">{[["body","文章正文"],["identity","文章信息"],["cover","主图"],["items","相关材料"],["schedule","展示与发布"]].map(([id,label])=><button type="button" key={id} aria-pressed={active===id} onClick={()=>setActive(id)}>{label}</button>)}</nav>
    <fieldset disabled={editor.disabled || !canEdit}>
      {active==="body"?<><section className={styles.articleInfo}><h2>文章信息</h2>{field("title","标题")}<label>导语<textarea rows={4} maxLength={3000} value={draft.introduction} onChange={event=>update({introduction:event.target.value})}/></label></section><ArticleBodyFields disabled={editor.disabled || !canEdit} onComposition={editor.setComposing} issueId={issueId} blocks={draft.body_blocks} selected={selectedBlock} onSelect={setSelectedBlock} protectedHeadings={draft.items.map(item=>item.section_id || "").filter(Boolean)} onChange={body_blocks=>update({body_blocks})}/></>:null}
      {active === "identity" ? <>{field("issue_label", "期名或期号")}{field("title", "本期标题")}{field("slug", "稳定地址名称（创建后保留）")}{field("public_byline", "公开署名")}<label>简短导语<textarea rows={5} value={draft.introduction} onChange={event => update({ introduction: event.target.value })} /></label></> : null}
      {active === "identity" ? <ArticleMetadataFields value={draft.article_metadata} onChange={article_metadata => update({ article_metadata })} onPortrait={(id, url) => update({article_metadata: {...emptyArticleMetadata, ...draft.article_metadata, curator_portrait_id:id}, curator:{...previewDraft.curator!,portrait_url:url}})} /> : null}
      {active === "cover" ? <><InlineMediaPicker selectedRenditionId={draft.cover_rendition_id} onSelect={(id, url) => update({ cover_rendition_id: id, cover_url: url })} />{draft.cover_url ? <button className="button secondary" onClick={() => update({ cover_url: "", cover_rendition_id: null })}>移除本期主图</button> : null}</> : null}
      {active === "items" ? <><nav className="issue-item-selector" aria-label="选择推荐项">{draft.items.map((item, index) => <div key={item.id || index}><button type="button" aria-current={selected === index ? "true" : undefined} onClick={() => setSelected(index)}>{index + 1}. {item.title || "未填写题名"}</button><button aria-label="向前移动推荐项" disabled={index === 0} onClick={() => moveItem(index, -1)}>↑</button><button aria-label="向后移动推荐项" disabled={index === draft.items.length - 1} onClick={() => moveItem(index, 1)}>↓</button></div>)}</nav><button className="button secondary" onClick={() => { setSelected(draft.items.length); update({ items: [...draft.items, { id: crypto.randomUUID(), kind: "planned", title: "", authors: "", version_note: "", isbn: "", doi: "", note: "", position: draft.items.length }] }); }}>添加推荐项</button>{draft.items[selected] ? <label>展项所属分组<select value={draft.items[selected].section_id || ""} onChange={event => update({items:draft.items.map((row,index) => index === selected ? {...row,section_id:event.target.value} : row)})}><option value="">独立推荐 / 未分组展项</option>{draft.body_blocks.filter(row => row.id && (row.type === "heading" || row.type === "analysis" && row.style === "heading")).map(row => <option key={row.id} value={row.id}>{row.text || "未命名分组"}</option>)}</select></label> : null}{draft.items[selected] ? <ItemFields onLink={linkItem} canLink={!dirty && !busy} key={draft.items[selected].id || `new-${selected}`} item={draft.items[selected]} change={item => update({ items: draft.items.map((row, i) => i === selected ? item : row) })} remove={() => { update({ items: draft.items.filter((_, i) => i !== selected).map((item, position) => ({ ...item, position })) }); setSelected(Math.max(0, selected - 1)); }} /> : null}</> : null}
      {active === "schedule" ? <><label>开始展示的日期时间<input type="datetime-local" value={draft.display_from ? localDate(draft.display_from) : ""} onChange={event => update({ display_from: event.target.value ? new Date(event.target.value).toISOString() : null })} /></label><p>留空表示确认发布后开始展示。未发布草稿不会因到期自动公开；没有新一期时保留最近的已发布一期。</p><p>{draft.has_unpublished_changes ? "存在待发布修改" : draft.published_at ? "已有正式版本" : "尚未发布"}</p></> : null}
    </fieldset></section><aside className={styles.previewPane} aria-label="文章预览与结构"><nav className={styles.previewTabs} aria-label="预览方式"><button type="button" aria-pressed={previewMode==="preview"} onClick={()=>{setPane("preview");if(mobile!=="edit")setMobile("preview");}}>文章预览</button><button type="button" aria-pressed={previewMode==="structure"} onClick={()=>{setPane("structure");if(mobile!=="edit")setMobile("structure");}}>结构视图</button></nav>
    {previewMode==="structure"?<nav className={styles.structure} aria-label="正文结构定位"><h2>正文结构</h2>{draft.body_blocks.length?<ol>{draft.body_blocks.map((block,index)=><li key={block.id || index}><button type="button" aria-current={selectedBlock===block.id?"true":undefined} onClick={()=>focusBlock(block.id || String(index))}><span>{index+1}. {blockNames[block.type]}</span><strong>{blockTitle(block)}</strong></button></li>)}</ol>:<p>插入内容块后在这里查看顺序。</p>}</nav>:<article className={styles.articlePreview}><h2>{draft.title || "文章标题待填写"}</h2>{draft.introduction?<p>{draft.introduction}</p>:null}{draft.cover_url?<img src={draft.cover_url} alt="文章主图"/>:null}{draft.body_blocks.map((block,index)=><section key={block.id || index} className={styles.previewBlock} data-selected={selectedBlock===block.id || undefined}><button type="button" className={styles.editBlock} onClick={()=>focusBlock(block.id || String(index))}>编辑第 {index+1} 块</button><IssueBlockView block={block}/></section>)}{draft.items.length?<section><h3>相关材料</h3>{draft.items.map((item,index)=><div key={item.id || index}><h4>{index+1}. {item.title || "题名待填写"}</h4><p>{item.authors}</p><p>{item.note}</p></div>)}</section>:null}{!draft.body_blocks.length&&!draft.items.length?<p className={styles.empty}>文章内容将在这里同步预览。</p>:null}</article>}</aside></div></>}
    {canEdit?<div className={styles.supportActions}><button type="button" disabled={assistantPending||editor.disabled||conflict} onClick={()=>setMaterials(true)}>策划选材与智能助手</button><button type="button" disabled={assistantPending} aria-expanded={suggestions} onClick={()=>setSuggestions(value=>!value)}>智能材料建议</button></div>:null}
    {suggestions&&canEdit?<IssueSuggestions issueId={issueId} version={draft.edit_version} blocks={draft.body_blocks} disabled={assistantPending||editor.disabled||conflict} request={editor.request} onClose={()=>setSuggestions(false)} onInsert={block=>{update({body_blocks:[...draft.body_blocks,block]});if(!materials)focusBlock(block.id!);}}/>:null}
    <IssueCollaboration issueId={issueId} version={draft.edit_version} editing={canEdit&&dirty} request={editor.request} onHistory={()=>setHistory(true)}/>
    {history?<IssueHistory issueId={issueId} request={editor.request} onClose={()=>setHistory(false)} canRestore={canEdit&&!assistantPending&&!editor.disabled&&!dirty&&!conflict} onRestore={editor.restoreHistory}/>:null}
    {canPublish && user ? <ArticleCommentReview key={String(user.id)} issueId={issueId} owner={String(user.id)} /> : null}
  </div>;
}
function localDate(value: string) { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); }
