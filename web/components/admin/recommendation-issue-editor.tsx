"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential, ApiRequestError } from "@/lib/api";
import { DraftConflict } from "@/components/admin/curation/draft-conflict";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useActionGuard } from "@/lib/use-action-guard";
import type { RecommendationIssue, IssueItem, IssueBlock } from "@/lib/api/recommendation-issues.types";
import { RecommendationIssueView } from "@/components/public/recommendation-issue-view";
import { FixedPageEditor } from "@/components/admin/curation/fixed-page-editor";
import { InlineMediaPicker } from "@/components/admin/curation/inline-media-picker";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";

const sections = [
  { id: "identity", label: "标题与署名", description: "期名、标题与导语出现在读者文章的顶部。公开署名不改变真实操作账号。" },
  { id: "cover", label: "本期主图" }, { id: "body", label: "导语与正文", description: "只编辑内容；文章版式固定。引文须填写出处。" },
  { id: "items", label: "推荐书目", description: "可混合已有馆藏和计划上架。计划项保存为无 PDF 书目草稿。" },
  { id: "schedule", label: "展示与发布", description: "先保存，再明确发布。未来展示时间只安排已确认发布的内容。" },
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
  const dirty = useUnsavedForm(draft, saved);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    queueMicrotask(()=>{if(alive){setDraft(null);setSaved(null);setSelected(0);setConflict(false);setInitialError("");}});
    apiRequest<Draft>(`/catalog/admin/recommendation-issues/${issueId}/${fullPreview ? "preview/" : ""}`, { signal: controller.signal }, getServerSessionCredential())
      .then(value => { if (alive) { setDraft(value); setSaved(value); } })
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
  if (fullPreview) return <div className="page-shell"><p className="private-preview-label">已保存草稿预览 · 仅后台可见</p><RecommendationIssueView issue={draft} preview /></div>;
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
  return <div className="v307-admin-editor"><header className="v307-editor-heading"><div><Link href="/admin/recommendations">‹ 返回推荐与随机</Link><h1>{draft.title || "新一期书库推荐"}</h1></div><div><button className="button secondary" disabled={busy || !dirty} onClick={() => persist()}>保存草稿</button>{canPublish ? <button className="button" disabled={busy || dirty || !draft.items.length} onClick={() => persist(true)}>确认发布</button> : null}</div></header>{message ? <p role="status" className="v307-save-status">{message}</p> : null}{conflict ? <DraftConflict endpoint={`/catalog/admin/recommendation-issues/${issueId}/`} local={draft} onUseRemote={remote => { setDraft(remote); setSaved(remote); setConflict(false); }} onKeepLocal={remote => { setSaved(remote); setDraft({ ...draft, edit_version: remote.edit_version }); setConflict(false); }} /> : null}
    <FixedPageEditor sections={sections} activeSection={active} onSectionChange={setActive} dirty={dirty} previewHref={`/admin/recommendations/issues/${issueId}/preview`} preview={<RecommendationIssueView issue={draft} preview />} fields={<fieldset disabled={busy}>
      {active === "identity" ? <>{field("issue_label", "期名或期号")}{field("title", "本期标题")}{field("slug", "稳定地址名称（创建后保留）")}{field("public_byline", "公开署名")}<label>简短导语<textarea rows={5} value={draft.introduction} onChange={event => update({ introduction: event.target.value })} /></label></> : null}
      {active === "cover" ? <><InlineMediaPicker onSelect={(id, url) => update({ cover_rendition_id: id, cover_url: url })} />{draft.cover_url ? <button className="button secondary" onClick={() => update({ cover_url: "", cover_rendition_id: null })}>恢复默认装饰图</button> : null}</> : null}
      {active === "body" ? <>{draft.body_blocks.map((block, index) => <div className="issue-block-editor" key={index}><label>内容类型<select value={block.type} onChange={event => update({ body_blocks: draft.body_blocks.map((row, i) => i === index ? { ...row, type: event.target.value as IssueBlock["type"] } : row) })}><option value="paragraph">段落</option><option value="heading">小标题</option><option value="quote">有出处的引文</option><option value="link">链接</option></select></label><textarea aria-label={`正文第${index + 1}项`} rows={4} value={block.text} onChange={event => update({ body_blocks: draft.body_blocks.map((row, i) => i === index ? { ...row, text: event.target.value } : row) })} />{block.type === "quote" || block.type === "link" ? <label>{block.type === "quote" ? "真实出处" : "链接地址"}<input value={(block.type === "quote" ? block.source : block.url) || ""} onChange={event => update({ body_blocks: draft.body_blocks.map((row, i) => i === index ? { ...row, [block.type === "quote" ? "source" : "url"]: event.target.value } : row) })} /></label> : null}<button type="button" onClick={() => update({ body_blocks: draft.body_blocks.filter((_, i) => i !== index) })}>移除段落</button></div>)}<button className="button secondary" onClick={() => update({ body_blocks: [...draft.body_blocks, { type: "paragraph", text: "" }] })}>添加正文段落</button></> : null}
      {active === "items" ? <><nav className="issue-item-selector" aria-label="选择推荐项">{draft.items.map((item, index) => <div key={item.id || index}><button type="button" aria-current={selected === index ? "true" : undefined} onClick={() => setSelected(index)}>{index + 1}. {item.title || "未填写题名"}</button><button aria-label="向前移动推荐项" disabled={index === 0} onClick={() => moveItem(index, -1)}>↑</button><button aria-label="向后移动推荐项" disabled={index === draft.items.length - 1} onClick={() => moveItem(index, 1)}>↓</button></div>)}</nav><button className="button secondary" onClick={() => { setSelected(draft.items.length); update({ items: [...draft.items, { id: "", kind: "planned", title: "", authors: "", version_note: "", isbn: "", doi: "", note: "", position: draft.items.length }] }); }}>添加推荐项</button>{draft.items[selected] ? <ItemFields onLink={linkItem} canLink={!dirty && !busy} key={draft.items[selected].id || `new-${selected}`} item={draft.items[selected]} change={item => update({ items: draft.items.map((row, i) => i === selected ? item : row) })} remove={() => { update({ items: draft.items.filter((_, i) => i !== selected).map((item, position) => ({ ...item, position })) }); setSelected(Math.max(0, selected - 1)); }} /> : null}</> : null}
      {active === "schedule" ? <><label>开始展示的日期时间<input type="datetime-local" value={draft.display_from ? localDate(draft.display_from) : ""} onChange={event => update({ display_from: event.target.value ? new Date(event.target.value).toISOString() : null })} /></label><p>留空表示确认发布后开始展示。未发布草稿不会因到期自动公开；没有新一期时保留最近的已发布一期。</p><p>{draft.has_unpublished_changes ? "存在待发布修改" : draft.published_at ? "已有正式版本" : "尚未发布"}</p></> : null}
    </fieldset>} />
  </div>;
}
function localDate(value: string) { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); }
