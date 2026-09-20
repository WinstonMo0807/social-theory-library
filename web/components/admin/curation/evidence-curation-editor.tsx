"use client";

import { useEffect, useState } from "react";
import { apiRequest, ApiRequestError, getServerSessionCredential } from "@/lib/api";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useActionGuard } from "@/lib/use-action-guard";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { EvidenceEnvelopeCard } from "@/components/admin/research/evidence-envelope-card";
import { EvidenceCurationView } from "@/components/public/evidence-curation-view";
import { FixedPageEditor, type FixedEditorSection } from "./fixed-page-editor";
import { DraftConflict } from "./draft-conflict";
import { evidenceCurationSavePayload, type EvidenceCurationDraft, type EvidenceCurationSource, type EvidenceCurationType } from "@/lib/api/evidence-curation.types";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";

type SourcePage = { count: number; next: string | null; previous: string | null; results: EvidenceCurationSource[] };
type Props = { objectType: EvidenceCurationType; objectId: string; sections?: FixedEditorSection[]; onSectionChange?: (id: string) => void; onDirtyChange?: (dirty: boolean) => void; fullPreview?: boolean };

function SourceCard({ source }: { source: EvidenceCurationSource }) {
  return <div className="evidence-curation-source"><EvidenceEnvelopeCard evidence={{ text: source.text, source: { work_title: source.work_title, asset_id: source.asset_id }, locator: { page: source.page_start, printed_page_label: source.printed_label }, reader_url: source.reader_url }} />
    <p>{source.edition_label || "出版信息待补"} · 文件 {source.asset_id} · {source.source_type === "span" ? "原文证据段" : "馆内摘录"}</p>
    {source.context_before || source.context_after ? <details><summary>查看上下文（只读）</summary>{source.context_before ? <p className="evidence-curation-context">{source.context_before}</p> : null}<blockquote>{source.text}</blockquote>{source.context_after ? <p className="evidence-curation-context">{source.context_after}</p> : null}</details> : null}
    {!source.public_eligible ? <p className="form-message">来源尚未公开，可保存为策展草稿，发布前需完成来源上架。</p> : null}
  </div>;
}

export function EvidenceCurationEditor({ objectType, objectId, sections = [{ id: "passages", label: "原文策展" }], onSectionChange = () => {}, onDirtyChange, fullPreview = false }: Props) {
  const endpoint = `/catalog/admin/evidence-curation/${objectType}/${objectId}/`;
  const [draft, setDraft] = useState<EvidenceCurationDraft | null>(null), [saved, setSaved] = useState<EvidenceCurationDraft | null>(null);
  const [initialError, setInitialError] = useState(""), [loadAttempt, setLoadAttempt] = useState(0);
  const [message, setMessage] = useState(""), [conflict, setConflict] = useState(false);
  const [work, setWork] = useState<{ id: string; name: string } | null>(null), [editions, setEditions] = useState<WorkLibraryRow[]>([]);
  const [editionId, setEditionId] = useState(""), [assetId, setAssetId] = useState("");
  const [editionError, setEditionError] = useState(""), [editionLoading, setEditionLoading] = useState(false), [editionAttempt, setEditionAttempt] = useState(0);
  const [query, setQuery] = useState(""), [search, setSearch] = useState(""), [page, setPage] = useState(1), [sourceAttempt, setSourceAttempt] = useState(0);
  const [sources, setSources] = useState<SourcePage | null>(null), [sourceError, setSourceError] = useState(""), [sourceLoading, setSourceLoading] = useState(false);
  const [selected, setSelected] = useState<EvidenceCurationSource | null>(null), [groupTitle, setGroupTitle] = useState(""), [reason, setReason] = useState("");
  const dirty = useUnsavedForm(draft, saved);
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const canPublish = hasAdminCapability(useAdminSession(), "can_publish_authority");
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    apiRequest<EvidenceCurationDraft>(endpoint, { signal: controller.signal }, getServerSessionCredential()).then(value => { if (active) { setDraft(value); setSaved(value); setInitialError(""); } }).catch(error => { if (active) setInitialError(controller.signal.aborted ? "读取超时，请重试。" : error instanceof Error ? error.message : "策展草稿读取失败"); }).finally(() => window.clearTimeout(timeout));
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, [endpoint, loadAttempt]);
  useEffect(() => {
    if (!work || fullPreview) return;
    const controller = new AbortController();
    queueMicrotask(() => { if (!controller.signal.aborted) { setEditionLoading(true); setEditionError(""); setEditions([]); } });
    void (async () => {
      const rows: WorkLibraryRow[] = []; let current = 1, pages = 1;
      do { const result = await apiRequest<CollectionPage<WorkLibraryRow>>(`/catalog/admin/library/works/?view=editions&work_id=${work.id}&page=${current}`, { signal: controller.signal }, getServerSessionCredential()); rows.push(...result.results); pages = result.total_pages; current += 1; } while (current <= pages && !controller.signal.aborted);
      if (!controller.signal.aborted) setEditions(rows);
    })().catch(error => { if (!controller.signal.aborted) setEditionError(error instanceof Error ? error.message : "版本读取失败"); }).finally(() => { if (!controller.signal.aborted) setEditionLoading(false); });
    return () => controller.abort();
  }, [work, editionAttempt, fullPreview]);
  useEffect(() => {
    if (!work || !editionId || !assetId || fullPreview) return;
    const controller = new AbortController();
    queueMicrotask(() => { if (!controller.signal.aborted) { setSourceLoading(true); setSourceError(""); setSources(null); } });
    const params = new URLSearchParams({ work: work.id, edition: editionId, asset: assetId, q: search, page: String(page) });
    apiRequest<SourcePage>(`/catalog/admin/evidence-curation/sources/?${params}`, { signal: controller.signal }, getServerSessionCredential()).then(value => { if (!controller.signal.aborted) setSources(value); }).catch(error => { if (!controller.signal.aborted) setSourceError(error instanceof Error ? error.message : "原文读取失败"); }).finally(() => { if (!controller.signal.aborted) setSourceLoading(false); });
    return () => controller.abort();
  }, [work, editionId, assetId, search, page, sourceAttempt, fullPreview]);

  async function persist(publish = false) {
    if (!draft || conflict || (publish && (dirty || !canPublish)) || !startAction(publish ? "publish" : "save")) return;
    const action = publish ? "publish" : "save";
    setMessage("");
    try {
      const result = await apiRequest<EvidenceCurationDraft>(`${endpoint}${publish ? "publish/" : ""}`, { method: publish ? "POST" : "PUT", body: JSON.stringify(publish ? { edit_version: draft.edit_version } : evidenceCurationSavePayload(draft)) }, getServerSessionCredential());
      setDraft(result); setSaved(result); setMessage(publish ? "原文策展已发布。" : "原文策展草稿已保存，尚未公开。");
    } catch (error) { setConflict(error instanceof ApiRequestError && error.status === 409); setMessage(`${error instanceof Error ? error.message : "保存失败"} 当前输入仍保留。`); }
    finally { finishAction(action); }
  }
  if (!draft) return <section className="admin-panel"><p role={initialError ? "alert" : "status"}>{initialError || "正在读取原文策展…"}</p>{initialError ? <button type="button" className="button secondary" onClick={() => { setInitialError(""); setLoadAttempt(value => value + 1); }}>重试读取</button> : null}</section>;
  if (fullPreview) return <main className="container evidence-curation-full-preview"><p>管理员草稿预览 · 未发布内容仅登录管理账号可见</p><h1>{draft.title} · 原文</h1><EvidenceCurationView items={draft.items} preview /></main>;
  const busy = Boolean(pendingAction);
  const files = editions.find(row => row.id === editionId)?.assets || [];
  const preview = <main className="container evidence-curation-full-preview"><h1>{draft.title} · 原文</h1><EvidenceCurationView items={draft.items} preview /></main>;
  function move(index: number, delta: number) {
    if (!draft) return;
    const items = [...draft.items]; [items[index], items[index + delta]] = [items[index + delta], items[index]];
    setDraft({ ...draft, items: items.map((item, order) => ({ ...item, order })) });
  }
  return <div className="evidence-curation-editor">{message ? <p className="v307-save-status" role="status">{message}</p> : null}{conflict ? <DraftConflict endpoint={endpoint} local={draft} onUseRemote={remote => { setDraft(remote); setSaved(remote); setConflict(false); }} onKeepLocal={remote => { setSaved(remote); setDraft({ ...draft, edit_version: remote.edit_version }); setConflict(false); }} /> : null}
    <FixedPageEditor sections={sections} activeSection="passages" onSectionChange={onSectionChange} dirty={dirty} previewHref={`/admin/preview/evidence/${objectType}/${objectId}`} preview={preview} fields={<fieldset disabled={busy} className="evidence-curation-fields">
      <p>从已有馆藏选择准确版本、文件和原文。原文与页码保持只读；这里仅编辑关联说明、分组和顺序。</p>
      <EntityPicker label="选择馆藏作品" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" values={work ? [work] : []} onChange={values => { const value = values.at(-1); setWork(value?.id ? { id: value.id, name: value.name } : null); setEditionId(""); setAssetId(""); setSources(null); setSelected(null); setPage(1); }} />
      {work ? <><label>准确出版版本<select value={editionId} disabled={editionLoading} onChange={event => { setEditionId(event.target.value); setAssetId(""); setSources(null); setSelected(null); setPage(1); }}><option value="">{editionLoading ? "正在读取版本…" : "选择出版版本"}</option>{editions.map(row => <option key={row.id} value={row.id}>{row.label || row.title}</option>)}</select></label>{editionError ? <p role="alert">{editionError} <button type="button" onClick={() => setEditionAttempt(value => value + 1)}>重试版本</button></p> : !editionLoading && !editions.length ? <p>当前作品还没有出版版本。</p> : null}</> : null}
      {editionId ? <label>原文文件<select value={assetId} onChange={event => { setAssetId(event.target.value); setSelected(null); setSources(null); setPage(1); }}><option value="">选择实际文件</option>{files.map(file => <option key={file.id} value={file.id}>{file.original_filename || file.kind} · 文件版本 {file.version}{file.page_count ? ` · ${file.page_count} 页` : ""}{file.is_current ? " · 当前" : " · 历史"}</option>)}</select>{!files.length ? <span>这个出版版本尚无原文文件。</span> : null}</label> : null}
      {assetId ? <section className="evidence-curation-picker"><div className="evidence-curation-search"><label>查找该文件内的原文<input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); setSearch(query.trim()); setPage(1); } }} /></label><button type="button" className="button secondary" onClick={() => { setSearch(query.trim()); setPage(1); }}>查找原文</button></div>{sourceLoading ? <p role="status">正在读取原文…</p> : sourceError ? <p role="alert">{sourceError} <button type="button" onClick={() => setSourceAttempt(value => value + 1)}>重试读取原文</button></p> : sources ? <><p>共 {sources.count} 段 · 第 {page} 页</p><div className="evidence-curation-source-list">{sources.results.map(source => <button type="button" key={`${source.source_type}:${source.id}`} aria-pressed={selected?.id === source.id && selected.source_type === source.source_type} onClick={() => setSelected(source)}><strong>PDF 第 {source.page_start || "待核对"} 页 · {source.source_type === "span" ? "原文证据段" : "馆内摘录"}</strong><span>{source.text}</span></button>)}</div>{!sources.results.length ? <p>当前文件没有匹配原文，请调整关键词或选择其他文件。</p> : null}<nav aria-label="原文候选分页"><button type="button" disabled={!sources.previous} onClick={() => { setPage(value => value - 1); setSelected(null); }}>上一页</button><button type="button" disabled={!sources.next} onClick={() => { setPage(value => value + 1); setSelected(null); }}>下一页</button></nav></> : null}</section> : null}
      {selected ? <section className="evidence-curation-selected"><h3>核对原文与上下文</h3><SourceCard source={selected} /><label>分组标题<input value={groupTitle} onChange={event => setGroupTitle(event.target.value)} /></label><label>与本页的关联理由<textarea value={reason} onChange={event => setReason(event.target.value)} /></label><button type="button" className="button secondary" disabled={draft.items.some(item => item.source_id === selected.id && item.source_type === selected.source_type)} onClick={() => { setDraft({ ...draft, items: [...draft.items, { source_type: selected.source_type, source_id: selected.id, source: selected, group_title: groupTitle.trim(), reason: reason.trim(), order: draft.items.length }] }); setSelected(null); setReason(""); }}>加入策展草稿</button></section> : null}
      <section className="evidence-curation-items"><h3>已选原文 · {draft.items.length}</h3>{!draft.items.length ? <p>尚未选择原文。</p> : draft.items.map((item, index) => <article key={item.id || `${item.source_type}:${item.source_id}`}><header><strong>原文 {index + 1}</strong><div><button type="button" disabled={index === 0} onClick={() => move(index, -1)}>上移</button><button type="button" disabled={index === draft.items.length - 1} onClick={() => move(index, 1)}>下移</button><button type="button" onClick={() => setDraft({ ...draft, items: draft.items.filter((_, row) => row !== index) })}>移出策展</button></div></header><SourceCard source={item.source} /><label>分组标题<input value={item.group_title} onChange={event => setDraft({ ...draft, items: draft.items.map((row, rowIndex) => rowIndex === index ? { ...row, group_title: event.target.value } : row) })} /></label><label>关联理由<textarea value={item.reason} onChange={event => setDraft({ ...draft, items: draft.items.map((row, rowIndex) => rowIndex === index ? { ...row, reason: event.target.value } : row) })} /></label></article>)}</section>
      <footer className="evidence-curation-actions"><button type="button" className="button secondary" disabled={!dirty || conflict} onClick={() => void persist()}>保存策展草稿</button>{canPublish ? <button type="button" className="button" disabled={dirty || conflict || !draft.has_unpublished_changes || draft.items.some(item => !item.source.public_eligible)} onClick={() => void persist(true)}>发布已保存策展</button> : null}<p>{busy ? "正在提交…" : dirty ? "当前修改尚未保存。" : draft.has_unpublished_changes ? "当前为已保存草稿，尚未公开。" : "当前没有待发布修改。"}</p></footer>
    </fieldset>} />
  </div>;
}
