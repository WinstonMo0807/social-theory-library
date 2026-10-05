"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { apiRequest, getServerSessionCredential, ApiRequestError } from "@/lib/api";
import { DraftConflict } from "@/components/admin/curation/draft-conflict";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useActionGuard } from "@/lib/use-action-guard";
import type { RecommendationIssue, IssueItem, IssueBlock, IssuePage } from "@/lib/api/recommendation-issues.types";
import { RecommendationIssueView, DailyReadingContent } from "@/components/public/recommendation-issue-view";
import { SiteHeader } from "@/components/site-header";
import { useApiResource } from "@/lib/api/use-api-resource";
import { FixedPageEditor } from "@/components/admin/curation/fixed-page-editor";
import { InlineMediaPicker } from "@/components/admin/curation/inline-media-picker";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";

const sections = [
  { id: "identity", label: "标题与署名", description: "期名、标题与导语出现在读者文章的顶部。公开署名不改变真实操作账号。" },
  { id: "cover", label: "本期主图" }, { id: "body", label: "导语与正文", description: "只编辑内容；文章版式固定。引文须填写出处。" },
  { id: "items", label: "推荐书目", description: "可混合已有馆藏和计划上架。计划项保存为无 PDF 书目草稿。" },
  { id: "schedule", label: "展示与发布", description: "先保存，再明确发布。未来展示时间只安排已确认发布的内容。" },
  { id: "preview", label: "预览发布", description: "核对文章和书目，保存草稿后再确认发布。" },
];
const issueSteps = [
  { id: "identity", label: "标题与配图" },
  { id: "body", label: "正文与书目" },
  { id: "schedule", label: "发布日期" },
  { id: "preview", label: "预览发布" },
];
type Draft = RecommendationIssue & { cover_rendition_id?: string | null };
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
  const [draft, setDraft] = useState<Draft | null>(null), [saved, setSaved] = useState<Draft | null>(null);
  const [active, setActive] = useState("identity"), [selected, setSelected] = useState(0), [message, setMessage] = useState("");
  const {pendingAction, startAction, finishAction} = useActionGuard();
  const busy = Boolean(pendingAction);
  const [conflict, setConflict] = useState(false);
  const [initialError, setInitialError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [previewLocation, setPreviewLocation] = useState<"article" | "home">("article");
  const [calendarMonth, setCalendarMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const scheduled = useApiResource<IssuePage>(`/catalog/admin/recommendation-issues/?day=${draft?.display_from ? localDate(draft.display_from).slice(0,10) : `${calendarMonth}-01`}&bucket=upcoming`, getServerSessionCredential());
  const dirty = useUnsavedForm(draft, saved);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    queueMicrotask(()=>{if(alive){setDraft(null);setSaved(null);setSelected(0);setConflict(false);setInitialError("");}});
    apiRequest<Draft>(`/catalog/admin/recommendation-issues/${issueId}/${fullPreview ? "preview/" : ""}`, { signal: controller.signal }, getServerSessionCredential())
      .then(value => { if (alive) { setDraft(value); setSaved(value); if(value.display_from) setCalendarMonth(localDate(value.display_from).slice(0,7)); } })
      .catch(error => { if (alive) setInitialError(controller.signal.aborted ? "读取本期草稿超时，请重试。" : error instanceof Error ? error.message : "本期草稿读取失败。"); })
      .finally(() => window.clearTimeout(timeout));
    return () => { alive = false; window.clearTimeout(timeout); controller.abort(); };
  }, [issueId, fullPreview, loadAttempt]);
  async function persist(publish = false) {
    if (!draft || busy || (publish && dirty)) return;
    if (!publish && draft.items.some(item => item.kind === "catalog" ? !item.work_id || !item.edition_id : !item.title.trim() || Boolean(item.work_id && !item.edition_id))) { setMessage("请为已有馆藏选择准确作品和出版版本；计划项至少填写题名，复用草稿时也需选择版本。"); return; }
    const action = publish ? "publish" : "save";
    if (!startAction(action)) return;
    setMessage("");
    try {
      const next = await apiRequest<Draft>(`/catalog/admin/recommendation-issues/${issueId}/${publish ? "publish/" : ""}`, { method: publish ? "POST" : "PUT", body: JSON.stringify(publish ? { edit_version: draft.edit_version, confirm: true } : draft) }, getServerSessionCredential());
      setDraft(next); setSaved(next); setConflict(false); setMessage(publish ? "已确认发布；按本期展示日期出现在公开页面。" : "草稿已保存，公开页面保持原内容。");
    } catch (error) { setConflict(error instanceof ApiRequestError && error.status === 409); setMessage(`${error instanceof Error ? error.message : "保存失败"} 当前输入已保留。`); }
    finally { finishAction(action); }
  }
  if (!draft) return <section className="admin-panel" aria-busy={!initialError}><p role={initialError ? "alert" : "status"}>{initialError || "正在读取本期草稿…"}</p>{initialError ? <button type="button" className="button secondary" onClick={() => { if (!draft) { setInitialError(""); setLoadAttempt(value => value + 1); } }}>重试读取</button> : null}<p><Link href="/admin/recommendations">返回推荐与随机</Link></p></section>;
  if (fullPreview) return <><SiteHeader preview previewPath="/recommendations"/><div className="page-shell"><p className="private-preview-label">已保存草稿预览 · 仅后台可见</p><RecommendationIssueView issue={draft} preview /></div></>;
  const update = (patch: Partial<Draft>) => setDraft(current => current ? { ...current, ...patch } : current);
  const field = (key: "title" | "slug" | "issue_label" | "public_byline", label: string) => <label>{label}<input readOnly={key === "slug"} value={draft[key]} onChange={event => update({ [key]: event.target.value })} /></label>;
  const canPublish = hasAdminCapability(user, "can_publish_authority");
  async function linkItem(workId: string, editionId: string) {
    if (!draft || dirty || busy || !draft.items[selected]?.id) return;
    if (!startAction("link")) return;
    setMessage("");
    try { const next = await apiRequest<Draft>(`/catalog/admin/recommendation-issues/${issueId}/items/${draft.items[selected].id}/link/`, { method: "POST", body: JSON.stringify({ edit_version: draft.edit_version, work_id: workId, edition_id: editionId, confirm_version: true }) }, getServerSessionCredential()); setDraft(next); setSaved(next); setConflict(false); setMessage("已关联所确认的馆藏版本，本期推介文字保持不变。"); }
    catch (error) { setConflict(error instanceof ApiRequestError && error.status === 409); setMessage(error instanceof Error ? error.message : "关联失败"); }
    finally { finishAction("link"); }
  }
  function moveItem(index: number, direction: number) { const items = [...draft!.items]; const destination = index + direction; if (destination < 0 || destination >= items.length) return; [items[index], items[destination]] = [items[destination], items[index]]; update({ items: items.map((item, position) => ({ ...item, position })) }); setSelected(destination); }
  const activeStep = active === "preview" ? 3 : active === "schedule" ? 2 : ["body", "items"].includes(active) ? 1 : 0;
  const navigationSections = sections.filter(section => activeStep === 0 ? ["identity","cover"].includes(section.id) : activeStep === 1 ? ["body","items"].includes(section.id) : section.id === active);
  const changeSection = (id: string) => { setActive(id); setPreviewLocation(id === "schedule" ? "home" : "article"); };
  const selectDate = (value: string) => update({display_from: value ? new Date(`${value}T${draft.display_from ? localDate(draft.display_from).slice(11,16) : "08:00"}`).toISOString() : null});
  const monthStart = new Date(`${calendarMonth}-01T12:00:00`);
  const monthDays = new Date(monthStart.getFullYear(), monthStart.getMonth()+1, 0).getDate();
  const monthOffset = (monthStart.getDay()+6)%7;
  const articlePreview = <><SiteHeader preview previewPath="/recommendations"/><RecommendationIssueView issue={draft} preview /></>;
  const homePreview = <><SiteHeader preview previewPath="/"/><DailyReadingContent lead={draft} cards={(scheduled.data?.results || []).filter(issue=>issue.id !== draft.id).slice(0,3)} preview/></>;
  return <div className="v307-admin-editor recommendation-issue-editor-v2"><header className="v307-editor-heading"><div><Link href="/admin/recommendations">‹ 返回编辑日历</Link><h1>编辑每日荐读 · {issueSteps[activeStep].label}</h1><p>{draft.title || "新一期书库推荐"}</p></div><div className="recommendation-issue-progress"><p>当前：第 {activeStep+1} / 4 步</p><nav className="recommendation-issue-stepper" aria-label="每日荐读编辑步骤">{issueSteps.map((step,index)=><button type="button" key={step.id} className={index===activeStep ? "active" : index<activeStep ? "done" : "future"} aria-current={index===activeStep ? "step" : undefined} onClick={()=>changeSection(step.id)}><b>{index<activeStep ? "✓" : index+1}</b><span>{step.label}</span></button>)}</nav></div></header>{message ? <p role="status" className="v307-save-status">{message}</p> : null}{conflict ? <DraftConflict endpoint={`/catalog/admin/recommendation-issues/${issueId}/`} local={draft} onUseRemote={remote => { setDraft(remote); setSaved(remote); setConflict(false); }} onKeepLocal={remote => { setSaved(remote); setDraft({ ...draft, edit_version: remote.edit_version }); setConflict(false); }} /> : null}
    <FixedPageEditor sections={sections} navigationSections={navigationSections} activeSection={active} onSectionChange={changeSection} dirty={dirty} previewHref={`/admin/recommendations/issues/${issueId}/preview`} publishedHref={draft.public_url || undefined} preview={previewLocation === "home" ? homePreview : articlePreview} previewToolbar={<label className="recommendation-preview-location">页面位置<select value={previewLocation} onChange={event=>setPreviewLocation(event.target.value as "article"|"home")}><option value="article">每日荐读 · 文章详情</option><option value="home">首页入口</option></select></label>} toolbar={<footer className="recommendation-issue-actions"><button type="button" className="button secondary" disabled={busy || activeStep===0} onClick={()=>changeSection(issueSteps[activeStep-1].id)}>上一步</button><button type="button" className="button secondary" disabled={busy || !dirty} onClick={()=>persist()}>保存草稿</button>{activeStep<3 ? <button type="button" className="button" disabled={busy} onClick={()=>changeSection(issueSteps[activeStep+1].id)}>下一步：{issueSteps[activeStep+1].label} →</button> : canPublish ? <button type="button" className="button" disabled={busy || dirty || !draft.items.length} onClick={()=>persist(true)}>确认发布 →</button> : null}</footer>} fields={<fieldset disabled={busy}>
      {active === "identity" ? <>{field("title", "文章题名")}<label>导语<textarea rows={5} value={draft.introduction} onChange={event => update({ introduction: event.target.value })} /></label><label>栏目分类<select disabled><option>—</option></select></label>{field("public_byline", "署名")}<label>发表日期<input type="date" value={draft.display_from ? localDate(draft.display_from).slice(0,10) : ""} onChange={event=>selectDate(event.target.value)}/></label><h3>封面主图</h3>{draft.cover_url ? <img className="recommendation-current-cover" src={draft.cover_url} alt="当前文章封面"/> : null}<InlineMediaPicker onSelect={(id, url) => update({ cover_rendition_id: id, cover_url: url })} /><details><summary>更多设置</summary>{field("issue_label", "期名或期号")}{field("slug", "稳定地址名称（创建后保留）")}</details></> : null}
      {active === "cover" ? <><InlineMediaPicker onSelect={(id, url) => update({ cover_rendition_id: id, cover_url: url })} />{draft.cover_url ? <button type="button" className="button secondary" onClick={() => update({ cover_url: "", cover_rendition_id: null })}>移除图片</button> : null}</> : null}
      {active === "body" ? <>{draft.body_blocks.map((block, index) => <div className="issue-block-editor" key={index}><label>内容类型<select value={block.type} onChange={event => update({ body_blocks: draft.body_blocks.map((row, i) => i === index ? { ...row, type: event.target.value as IssueBlock["type"] } : row) })}><option value="paragraph">段落</option><option value="heading">小标题</option><option value="quote">有出处的引文</option><option value="link">链接</option></select></label><textarea aria-label={`正文第${index + 1}项`} rows={4} value={block.text} onChange={event => update({ body_blocks: draft.body_blocks.map((row, i) => i === index ? { ...row, text: event.target.value } : row) })} />{block.type === "quote" || block.type === "link" ? <label>{block.type === "quote" ? "真实出处" : "链接地址"}<input value={(block.type === "quote" ? block.source : block.url) || ""} onChange={event => update({ body_blocks: draft.body_blocks.map((row, i) => i === index ? { ...row, [block.type === "quote" ? "source" : "url"]: event.target.value } : row) })} /></label> : null}<button type="button" onClick={() => update({ body_blocks: draft.body_blocks.filter((_, i) => i !== index) })}>移除段落</button></div>)}<button className="button secondary" onClick={() => update({ body_blocks: [...draft.body_blocks, { type: "paragraph", text: "" }] })}>添加正文段落</button></> : null}
      {active === "items" ? <><nav className="issue-item-selector" aria-label="选择推荐项">{draft.items.map((item, index) => <div key={item.id || index}><button type="button" aria-current={selected === index ? "true" : undefined} onClick={() => setSelected(index)}>{index + 1}. {item.title || "未填写题名"}</button><button aria-label="向前移动推荐项" disabled={index === 0} onClick={() => moveItem(index, -1)}>↑</button><button aria-label="向后移动推荐项" disabled={index === draft.items.length - 1} onClick={() => moveItem(index, 1)}>↓</button></div>)}</nav><button className="button secondary" onClick={() => { setSelected(draft.items.length); update({ items: [...draft.items, { id: "", kind: "planned", title: "", authors: "", version_note: "", isbn: "", doi: "", note: "", position: draft.items.length }] }); }}>添加推荐项</button>{draft.items[selected] ? <ItemFields onLink={linkItem} canLink={!dirty && !busy} key={draft.items[selected].id || `new-${selected}`} item={draft.items[selected]} change={item => update({ items: draft.items.map((row, i) => i === selected ? item : row) })} remove={() => { update({ items: draft.items.filter((_, i) => i !== selected).map((item, position) => ({ ...item, position })) }); setSelected(Math.max(0, selected - 1)); }} /> : null}</> : null}
      {active === "schedule" ? <section className="recommendation-issue-schedule-v2"><p>选择文章在网站上公开的时间。保存日期不会自动发布，你仍需在下一步确认发布。</p><div className="recommendation-date-fields"><label>发布日期<input type="date" value={draft.display_from ? localDate(draft.display_from).slice(0,10) : ""} onChange={event=>selectDate(event.target.value)}/></label><label>发布时间<input type="time" value={draft.display_from ? localDate(draft.display_from).slice(11,16) : "08:00"} onChange={event=>update({display_from:new Date(`${draft.display_from ? localDate(draft.display_from).slice(0,10) : `${calendarMonth}-01`}T${event.target.value || "08:00"}`).toISOString()})}/></label></div><div className="recommendation-date-grid"><div className="recommendation-month"><header><strong>{monthStart.getFullYear()}年{monthStart.getMonth()+1}月</strong><button type="button" aria-label="上个月" onClick={()=>setCalendarMonth(localDate(new Date(monthStart.getFullYear(),monthStart.getMonth()-1,1,12).toISOString()).slice(0,7))}><ChevronLeft size={18}/></button><button type="button" aria-label="下个月" onClick={()=>setCalendarMonth(localDate(new Date(monthStart.getFullYear(),monthStart.getMonth()+1,1,12).toISOString()).slice(0,7))}><ChevronRight size={18}/></button></header><div className="recommendation-month-days">{["一","二","三","四","五","六","日"].map(label=><span key={label}>{label}</span>)}{Array.from({length:monthOffset},(_,index)=><span key={`empty-${index}`}/>)}{Array.from({length:monthDays},(_,index)=>{const date=`${calendarMonth}-${String(index+1).padStart(2,"0")}`;return <button type="button" key={date} aria-pressed={draft.display_from ? localDate(draft.display_from).slice(0,10)===date : false} onClick={()=>selectDate(date)}>{index+1}</button>;})}</div></div><div className="recommendation-upcoming"><h3>接下来三篇文章</h3>{scheduled.error ? <p role="alert">{scheduled.error}<button type="button" onClick={scheduled.retry}>重试</button></p> : scheduled.loading ? <p role="status">正在读取排期…</p> : (scheduled.data?.results || []).filter(issue=>issue.id!==draft.id).slice(0,3).map(issue=><Link key={issue.id} href={`/admin/recommendations/issues/${issue.id}`}><time>{issue.display_from ? new Date(issue.display_from).toLocaleString("zh-CN",{timeZone:"Asia/Hong_Kong"}) : "—"}</time><strong>{issue.title}</strong><small>{issue.public_byline}</small></Link>)}{!scheduled.loading && !scheduled.error && !scheduled.data?.results.length ? <p>暂无安排</p> : null}</div></div><div className="recommendation-issue-schedule-status"><strong>当前状态</strong><p>{draft.has_unpublished_changes ? "存在待发布修改。保存或更改发布日期不会自动发布。" : draft.public_url ? "当前已有公开版本。修改后需重新确认发布。" : "当前尚未公开。请在下一步预览并确认后手动发布。"}</p></div></section> : null}
      {active === "preview" ? <section className="recommendation-publish-review"><h3>确认本期内容</h3><p>{draft.title}</p><p>{draft.items.length}项阅读物 · {draft.display_from ? new Date(draft.display_from).toLocaleString("zh-CN",{timeZone:"Asia/Hong_Kong"}) : "确认后立即展示"}</p>{dirty ? <p>当前输入尚未保存，请先保存草稿。</p> : <p>草稿已保存。确认发布后，读者会按设置的日期看到这一版内容。</p>}{!canPublish ? <p>当前账号没有发布权限。</p> : null}</section> : null}
    </fieldset>} />
  </div>;
}
function localDate(value: string) { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); }
