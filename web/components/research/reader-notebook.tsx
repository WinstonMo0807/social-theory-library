"use client";
import { SourceText } from "@/components/source-text";

import { confirmAction } from "@/lib/ui-dialog";

import { LoadingState } from "@/components/ui/loading-state";
import { MediaPlacement } from "@/components/media-placement";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { BookOpen, Copy, Download, Quote, LockKeyhole, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { downloadNotebook, notebookPath, notebookRecordPath, notebookRequest, type NotebookChoice, type NotebookExportInput, type NotebookPage, type NotebookRecord } from "@/lib/api/notebook.client";
import { previewSharedCitation, type SharedCitationInput } from "@/lib/api/shared-citation.client";
import { SharedCitationOverlay } from "@/components/shared-citation-overlay";
import { preparePrivacyOperation, type PrivacyTarget } from "@/lib/api/privacy.client";
import { Dialog } from "@/components/ui/dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { CitationSourcePreview } from "./citation-source-preview";
import { OperationDialog } from "./privacy-workspace";
import styles from "./reader-notebook.module.css";

const labels = { note: "本人笔记", highlight: "原文摘录", underline: "原文摘录", bookmark: "书签" };
const date = (value: string) => new Date(value).toLocaleDateString("zh-CN");
const target = (row: NotebookRecord): PrivacyTarget => ({ category: row.category, id: row.id, revision: row.revision });

export function ReaderNotebook({ assetId, initialKind = "all" }: { assetId?: string; initialKind?: string }) {
  const { state, retry } = useSessionBootstrap();
  const search = useSearchParams();
  const context = new URLSearchParams();
  for (const key of ["booklist", "work", "project", "record"]) {
    const value = search?.get(key); if (value && /^[\da-f-]{36}$/i.test(value)) context.set(key, value);
  }
  if (["annotations", "bookmarks"].includes(search?.get("category") || "")) context.set("category", search!.get("category")!);
  const next = `/account/notes${assetId ? `/${assetId}` : ""}${context.size ? `?${context}` : ""}`;
  useEffect(() => { if (state.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(next)}`); }, [state.status, next]);
  if (state.status === "forbidden" || state.status === "temporary_error") return <main className={styles.page}><h1>阅读记录暂时无法读取</h1><p role="alert">{state.message}</p><button onClick={retry}>重新核对登录</button></main>;
  if (state.status !== "authenticated" || !state.user) return <main className={styles.page}><LoadingState variant="screen" role="status">正在核对登录状态…</LoadingState></main>;
  return <Notebook key={`${state.user.id}:${assetId || "all"}:${context.get("booklist") || ""}:${context.get("work") || ""}:${context.get("project") || ""}`} owner={String(state.user.id)} assetId={assetId} initialKind={initialKind} />;
}

function Notebook({ owner, assetId, initialKind }: { owner: string; assetId?: string; initialKind: string }) {
  const search = useSearchParams();
  const [filters, setFilters] = useState({ q: "", kind: ["all", "note", "excerpt", "bookmark"].includes(search?.get("kind") || "") ? search!.get("kind")! : initialKind, order: "newest", booklist: /^[\da-f-]{36}$/i.test(search?.get("booklist") || "") ? search!.get("booklist")! : "", work: /^[\da-f-]{36}$/i.test(search?.get("work") || "") ? search!.get("work")! : "", project: /^[\da-f-]{36}$/i.test(search?.get("project") || "") ? search!.get("project")! : "", start: "", end: "" });
  const [page, setPage] = useState(1), [selected, setSelected] = useState<string[]>([]);
  const [focus, setFocus] = useState<{ category: "annotations" | "bookmarks"; id: string } | null>(() => {
    const id = search?.get("record"), category = search?.get("category");
    return id && /^[\da-f-]{36}$/i.test(id) && (category === "annotations" || category === "bookmarks") ? { id, category } : null;
  });
  const [editing, setEditing] = useState<NotebookRecord | null>(null), [adding, setAdding] = useState(false), [preview, setPreview] = useState(false);
  const linkedId = search?.get("record"), linkedCategory = search?.get("category");
  useEffect(() => {
    let active = true;
    const locate = () => {
      const legacy = /^#note-([\da-f-]{36})$/i.exec(window.location.hash);
      const id = linkedId || legacy?.[1], category = linkedId ? linkedCategory : "annotations";
      if (id && /^[\da-f-]{36}$/i.test(id) && (category === "annotations" || category === "bookmarks")) {
        queueMicrotask(() => { if (active) { setFocus({ id, category }); setPreview(false); } });
      }
    };
    locate(); window.addEventListener("hashchange", locate);
    return () => { active = false; window.removeEventListener("hashchange", locate); };
  }, [linkedId, linkedCategory]);
  const query = new URLSearchParams({ page: String(page), ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)), ...(assetId ? { asset: assetId } : {}) });
  const load = useCallback((path: string, signal: AbortSignal) => notebookRequest<NotebookPage>(owner, path, { signal }), [owner]);
  const list = usePersistentWorkspace<NotebookPage>(`${notebookPath}?${query}`, owner, undefined, load);
  const detailLoad = useCallback((path: string, signal: AbortSignal) => notebookRequest<NotebookRecord>(owner, path, { signal }), [owner]);
  const detail = usePersistentWorkspace<NotebookRecord>(focus ? notebookRecordPath(focus) : "", owner, undefined, detailLoad);
  const data = list.error ? null : list.data, row = detail.error ? null : detail.data;
  const rows = data?.results || [], chosen = rows.filter(value => selected.includes(value.key));
  function change(key: keyof typeof filters, value: string) { setFilters(current => ({ ...current, [key]: value })); setPage(1); setSelected([]); }
  function reload() { list.reload(); detail.reload(); setSelected([]); }
  function open(value: NotebookRecord) { setFocus({ category: value.category, id: value.id }); setPreview(false); }
  function paginate(value: number) { setPage(value); setSelected([]); }
  return <main className={styles.page}>
    <nav className={styles.crumb} aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><Link href="/account">读者中心</Link><span>›</span><span>笔记、摘录与书签</span></nav>
    <header className={styles.heading}><div><h1>笔记、摘录与书签</h1></div><small><LockKeyhole size={20} /><span>仅本人可见</span></small></header>

    {filters.booklist ? <div className={styles.notice}><p>当前范围：这份书单现有作品下的本人记录。移除作品不删除笔记。</p><Link href={`/account/collections/${filters.booklist}?tab=notes`}>返回书单 →</Link><button onClick={() => change("booklist", "")}>查看全部笔记</button></div> : null}
    <div className={styles.workspace}>
      <aside className={styles.filters} aria-label="筛选阅读记录"><div className={styles.sectionTitle}><strong>筛选条件</strong><button onClick={() => { setFilters({ q: "", kind: "all", order: "newest", booklist: "", work: "", project: "", start: "", end: "" }); setPage(1); setSelected([]); }}>清空</button></div>
        <form onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); change("q", String(new FormData(event.currentTarget).get("q") || "")); }} className={styles.search}><input key={filters.q} name="q" defaultValue={filters.q} maxLength={180} placeholder="书名、作者、笔记内容…" aria-label="搜索自己的阅读记录" /><button aria-label="搜索"><Search size={16} /></button></form>
        {assetId ? <p>当前限定此文件。<Link href="/account/notes">全部记录</Link></p> : null}
        <ChoicePicker list owner={owner} kind="works" label="按作品" value={filters.work} onChange={value => change("work", value)} />
        <ChoicePicker list owner={owner} kind="projects" label="按问题" value={filters.project} onChange={value => change("project", value)} />
        <FilterGroup label="日期"><fieldset><label>开始日期<input type="date" value={filters.start} onChange={event => change("start", event.target.value)} /></label><label>结束日期<input type="date" value={filters.end} onChange={event => change("end", event.target.value)} /></label></fieldset></FilterGroup>
        <FilterGroup label="类型"><fieldset>{[["all", "全部记录"], ["excerpt", "原文摘录"], ["note", "本人笔记"], ["bookmark", "书签"]].map(([value, label]) => <label key={value}><input type="radio" name="record-kind" checked={filters.kind === value} onChange={() => change("kind", value)} />{label}</label>)}</fieldset></FilterGroup>
      </aside>
      <section className={styles.records} aria-label="阅读记录列表">
        <div className={styles.toolbar}><span>共 {data?.count ?? "—"} 条记录</span><label>排序<select data-stl-select value={filters.order} onChange={event => change("order", event.target.value)}><option value="newest">日期（新 → 旧）</option><option value="oldest">日期（旧 → 新）</option></select></label></div>
        <div className={styles.selectAll}><label><input type="checkbox" checked={rows.length > 0 && chosen.length === rows.length} disabled={!rows.length} onChange={event => setSelected(event.target.checked ? rows.map(value => value.key) : [])} />选择本页</label><span>已选择 {chosen.length} 条</span></div>
        <NotebookActions owner={owner} chosen={chosen} onChanged={reload} />
        {list.error ? <Failure message={list.error} retry={list.reload} /> : !data ? <LoadingState role="status">正在读取本人记录…</LoadingState> : !rows.length ? <div className={styles.empty}><BookOpen size={30} /><h2>这里还没有阅读记录</h2><p>在原文中保存笔记、摘录或书签后，可在这里继续整理。</p><Link href="/explore">查找阅读材料</Link></div> : <ol className={styles.list}>{rows.map(value => <li key={value.key} data-selected={selected.includes(value.key)} data-focused={focus?.id === value.id && focus.category === value.category}>
          <input type="checkbox" aria-label={`选择${value.work.title}的${labels[value.kind]}`} checked={selected.includes(value.key)} onChange={event => setSelected(current => event.target.checked ? [...current, value.key] : current.filter(key => key !== value.key))} />
          <button className={styles.record} disabled={Boolean(editing)} onClick={() => open(value)}><span className={styles.recordTop}><em data-kind={value.kind}>{labels[value.kind]}</em><time dateTime={value.updated_at}>{date(value.updated_at)}</time></span><strong>{value.work.title}</strong><p>{value.kind === "bookmark" ? value.label || "页面书签" : value.kind === "note" ? value.body || "尚未填写笔记" : value.saved_quote || "未保存摘录文字"}</p><small>{value.work.authors.join("、")}{value.work.year ? ` · ${value.work.year}` : ""} · PDF 第 {value.pdf_page} 页</small></button>
        </li>)}</ol>}
        <Pager page={page} total={data?.total_pages || 1} disabled={!data} onChange={paginate} />
      </section>
      <aside className={styles.detail} aria-label="记录与来源详情">
        {focus ? <button className={styles.closeDetail} disabled={Boolean(editing)} onClick={() => setFocus(null)}><X size={15} />关闭详情</button> : null}
        {detail.error ? <Failure message={detail.error} retry={detail.reload} /> : row ? <>
          <div className={styles.sectionTitle}><h2>{labels[row.kind]}</h2>{row.source.source_status === "available" && row.source.reader_url ? <Link href={row.source.reader_url}>回到原文 →</Link> : null}</div>
          {row.saved_quote ? <blockquote><SourceText text={row.saved_quote} /><footer>保存时的原文摘录 · PDF 第 {row.pdf_page} 页</footer></blockquote> : <p className={styles.muted}>{row.label || "此处尚未保存摘录文字。"}</p>}
          {row.notice ? <p className={styles.notice}>{row.notice} 自己写下的内容仍可查看和编辑。</p> : null}
          <div className={styles.sourceCard}>{row.work.cover_url ? <MediaPlacement uses={row.work.cover_media?.display_uses} fallback={<BookOpen size={25} />}><Image src={row.work.cover_url} alt={`${row.work.title}封面`} width={58} height={82} unoptimized /></MediaPlacement> : <BookOpen size={25} />}<div><h3>{row.work.title}</h3><p>{row.work.authors.join("、") || "作者待核对"}{row.work.year ? ` · ${row.work.year}` : ""}</p><small>PDF 第 {row.pdf_page} 页{row.source.printed_label ? ` · 书内页码 ${row.source.printed_label}` : ""}</small>{row.work.href ? <Link href={row.work.href}>查看作品信息 →</Link> : null}</div></div>
          <div className={styles.sectionTitle}><h2>{row.kind === "bookmark" ? "书签名称" : "我的笔记"}</h2>{!editing ? <button onClick={() => { setAdding(false); setEditing(row); }}>编辑</button> : null}</div>
          {editing ? <NoteEditor key={`${editing.key}:${adding}`} owner={owner} original={editing} addNote={adding} onSaved={saved => { setEditing(null); setFocus({ category: saved.category, id: saved.id }); reload(); }} onCancel={() => setEditing(null)} /> : <><p className={styles.body}>{row.kind === "bookmark" ? row.label || "尚未命名" : row.body || "尚未写下自己的笔记。"}</p><div className={styles.tags}>{row.tags.map(tag => <span key={tag}>#{tag}</span>)}</div><small className={styles.muted}>最后编辑 · {date(row.updated_at)}</small>
          {row.kind === "bookmark" ? <button onClick={() => { setAdding(true); setEditing(row); }}>在此位置添加笔记</button> : null}</>}
          <DetailActions owner={owner} row={row} onPreview={() => setPreview(value => !value)} />
          {preview ? <CitationSourcePreview reference={row.source} /> : null}
          <p className={styles.privateNote}>独立笔记不会自动进入学术记忆或模型参考内容。加入研究仅关联所选来源及你明确填写的备注。</p>
        </> : <div className={styles.empty}><BookOpen size={28} /><p>{focus ? "正在核对这条记录…" : "选择一条记录，查看摘录、笔记与来源。"}</p></div>}
      </aside>
    </div>

  </main>;
}

function Failure({ message, retry }: { message: string; retry: () => void }) { return <div className={styles.error} role="alert"><p>{message}</p><button type="button" onClick={retry}>重新读取</button></div>; }
function Pager({ page, total, disabled, onChange }: { page: number; total: number; disabled?: boolean; onChange: (value: number) => void }) { return <nav className={styles.pager} aria-label="分页"><button type="button" disabled={disabled || page <= 1} onClick={() => onChange(page - 1)}>上一页</button><span>{page} / {total}</span><button type="button" disabled={disabled || page >= total} onClick={() => onChange(page + 1)}>下一页</button></nav>; }

function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  const [expanded, setExpanded] = useState(true);
  useEffect(() => { const media = window.matchMedia("(max-width:760px)"); const adapt = () => setExpanded(!media.matches); adapt(); media.addEventListener("change", adapt); return () => media.removeEventListener("change", adapt); }, []);
  return <details data-disclosure="collection" className={styles.choice} open={expanded} onToggle={event=>setExpanded(event.currentTarget.open)}><summary>{label}</summary>{children}</details>;
}

function ChoicePicker({ owner, kind, label, value, onChange, list = false }: { list?: boolean; owner: string; kind: "works" | "projects"; label: string; value: string; onChange: (id: string, row?: NotebookChoice) => void }) {
  const [page, setPage] = useState(1), [q, setQ] = useState("");
  const load = useCallback((path: string, signal: AbortSignal) => notebookRequest<NotebookPage<NotebookChoice>>(owner, path, { signal }), [owner]);
  const resource = usePersistentWorkspace<NotebookPage<NotebookChoice>>(`${notebookPath}choices/${kind}/?${new URLSearchParams({ page: String(page), q })}`, owner, undefined, load);
  const data = resource.error ? null : resource.data;
  if (list) return <FilterGroup label={label}><form className={styles.search} onSubmit={event => { event.preventDefault(); setQ(String(new FormData(event.currentTarget).get("q") || "")); setPage(1); }}><input name="q" maxLength={180} placeholder={kind === "works" ? "搜索作品名称…" : "搜索研究问题…"} aria-label={kind === "works" ? "搜索作品名称" : "搜索研究问题"}/><button aria-label="筛选"><Search size={14}/></button></form><div className={styles.choiceRows}><label><input type="checkbox" checked={!value} onChange={() => onChange("")} />全部</label>{data?.results.map(row => <label key={row.id}><input type="checkbox" checked={row.id===value} onChange={() => onChange(row.id===value?"":row.id,row)}/><span>{row.title}</span>{row.count!==undefined?<small>{row.count}</small>:null}</label>)}{value&&!data?.results.some(row=>row.id===value)?<button type="button" onClick={()=>onChange("")}>清除其他页的已选条件</button>:null}</div>{resource.error?<Failure message={resource.error} retry={resource.reload}/>:null}{data&&data.total_pages>1?<Pager page={page} total={data.total_pages} onChange={setPage}/>:null}</FilterGroup>;
  return <fieldset className={styles.choice}><legend>{label}</legend><select data-stl-select aria-label={label} value={data?.results.some(row => row.id === value) ? value : value ? "__selected" : ""} onChange={event => { if (event.target.value !== "__selected") onChange(event.target.value, data?.results.find(row => row.id === event.target.value)); }}><option value="">全部</option>{value && !data?.results.some(row => row.id === value) ? <option value="__selected">已选择另一页的项目</option> : null}{data?.results.map(row => <option value={row.id} key={row.id}>{row.title}{row.count !== undefined ? ` (${row.count})` : ""}</option>)}</select>{resource.error ? <Failure message={resource.error} retry={resource.reload} /> : null}<Pager page={page} total={data?.total_pages || 1} disabled={!data} onChange={setPage} />{kind === "projects" ? <small>按已明确加入研究的来源筛选。</small> : null}</fieldset>;
}

function useOwnerController() {
  const controller = useRef<AbortController | null>(null);
  useEffect(() => { const request = new AbortController(); controller.current = request; const off = subscribeToSessionChanges(() => request.abort()); return () => { request.abort(); off(); }; }, []);
  return controller;
}

function NoteEditor({ owner, original, addNote = false, onSaved, onCancel }: { owner: string; original: NotebookRecord; addNote?: boolean; onSaved: (saved: NotebookRecord) => void; onCancel: () => void }) {
  const [body, setBody] = useState(addNote ? "" : original.kind === "bookmark" ? original.label : original.body), [tags, setTags] = useState(original.tags.join("，"));
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [canRetry, setCanRetry] = useState(false);
  const [ready, setReady] = useState(!addNote), [recovery, setRecovery] = useState<string | null>(null), [broken, setBroken] = useState(false);
  const controller = useOwnerController(), sending = useRef(false), pending = useRef<Record<string, unknown> | null>(null);
  const storageKey = `stl-notebook-new-note:${owner}:${original.id}`;
  const labelOnly = original.kind === "bookmark" && !addNote, limit = labelOnly ? 240 : Math.max(500, original.body.length);
  useEffect(() => {
    if (!addNote) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const id = sessionStorage.getItem(storageKey);
        if (id) { if (!/^[\da-f-]{36}$/i.test(id)) throw Error("原请求标识无法读取，请先在我的笔记核对。"); setRecovery(id); setMessage("上次新增笔记的结果尚未确认，请先查询原结果。"); }
      } catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "原请求无法读取。"); }
      setReady(true);
    });
    return () => { active = false; };
  }, [addNote, storageKey]);
  function clear() { sessionStorage.removeItem(storageKey); setRecovery(null); setBroken(false); setCanRetry(false); pending.current = null; }
  async function lookup() {
    const request = controller.current;
    if (!recovery || !request || request.signal.aborted || sending.current) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      const result = await withPrivateOwner(owner, () => notebookRequest<{ owner_id: string; id: string; exists: boolean; retired: boolean; record: NotebookRecord | null }>(owner, `${notebookRecordPath(original)}note/?${new URLSearchParams({ request_id: recovery })}`, { signal: request.signal }), request.signal);
      if (result.id !== recovery) throw Error("操作结果与原请求不符，请保留请求并重新核对。");
      if (!request.signal.aborted) { clear(); if (result.exists && result.record) onSaved(result.record); else setMessage("原笔记已经删除，旧请求不会重新创建。可以关闭，或明确填写另一条新笔记。"); }
    } catch (reason) { if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "原笔记暂时无法核对。"); }
    finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); const request = controller.current;
    if (!request || request.signal.aborted || sending.current || !ready || broken || recovery && !pending.current) return;
    sending.current = true; setBusy(true); setMessage("");
    const data = pending.current || { expected_version: original.revision, ...(addNote ? { request_id: createRequestKey() } : {}), ...(labelOnly ? { label: body } : { body, tags: [...new Set(tags.split(/[，,]/).map(value => value.trim()).filter(Boolean))] }) };
    try {
      if (addNote) { sessionStorage.setItem(storageKey, String(data.request_id)); pending.current = data; setCanRetry(true); setRecovery(String(data.request_id)); }
      const saved = await withPrivateOwner(owner, () => notebookRequest<NotebookRecord>(owner, addNote ? `${notebookRecordPath(original)}note/` : notebookRecordPath(original), { method: addNote ? "POST" : "PATCH", signal: request.signal, body: JSON.stringify(data) }), request.signal);
      if (!request.signal.aborted) { if (addNote) clear(); onSaved(saved); }
    } catch (reason) {
      if (request.signal.aborted) return;
      if (addNote && reason instanceof ApiRequestError && [400, 403, 404, 409].includes(reason.status)) clear();
      setMessage(reason instanceof Error ? reason.message : "保存未确认，请保留输入并查询原结果。");
    } finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  const dirty = useUnsavedForm({ body, tags }, { body: addNote ? "" : labelOnly ? original.label : original.body, tags: original.tags.join("，") });
  const locked = busy || !ready || Boolean(recovery) || broken;
  return <form className={styles.editor} onSubmit={event => void save(event)}><fieldset disabled={locked}><label>{labelOnly ? "名称" : "我的笔记"}<textarea value={body} maxLength={limit} rows={7} onChange={event => setBody(event.target.value)} /></label><small>{body.length} / {limit}</small>{!labelOnly ? <label>标签（逗号分隔，最多12个）<input value={tags} onChange={event => setTags(event.target.value)} /></label> : null}</fieldset>{message ? <p role="alert">{message}</p> : null}
    {recovery ? <button type="button" disabled={busy} onClick={() => void lookup()}>查询原笔记</button> : null}{recovery || broken ? <button type="button" disabled={busy} onClick={async () => { if ((await confirmAction("请先在我的笔记核对原操作。确认结束本次恢复？已保存内容不会删除。"))) clear(); }}>已核对，结束恢复</button> : null}
    <footer><button type="button" disabled={busy} onClick={async () => { if (!dirty || (await confirmAction("当前笔记尚未保存，确定放弃修改吗？"))) onCancel(); }}>取消</button><button className={styles.primary} disabled={busy || !ready || broken || Boolean(recovery && !canRetry)}>{busy ? "正在保存…" : recovery ? "重试原请求" : "保存"}</button></footer></form>;
}

function DetailActions({ owner, row, onPreview }: { owner: string; row: NotebookRecord; onPreview: () => void }) {
  const [message, setMessage] = useState(""); const controller = useOwnerController();
  const [citation, setCitation] = useState<SharedCitationInput | null>(null);
  async function cite(copy: boolean) {
    const request = controller.current; if (!request || request.signal.aborted) return;
    try {
      const result = await withPrivateOwner(owner, async () => {
        const fresh = await notebookRequest<NotebookRecord>(owner, notebookRecordPath(row), { signal: request.signal });
        if (fresh.source.source_status !== "available" || copy && !fresh.saved_quote) throw Error("当前无法核对摘录与引文，请先查看原文。");
        const input: SharedCitationInput = { reference: fresh.source, ...(fresh.saved_quote ? { selectedText: fresh.saved_quote } : {}) };
        return { input, verified: await previewSharedCitation(input, request.signal) };
      }, request.signal);
      if (request.signal.aborted) return;
      if (!copy) { setCitation(result.input); return; }
      await navigator.clipboard.writeText(`${result.verified.reference?.quote || ""}\n\n${result.verified.citations["gbt7714-2025"] || result.verified.source.title} · PDF 第 ${result.verified.source.pdf_page} 页`);
      if (!request.signal.aborted) setMessage("已复制当前可核对的摘录与来源。");
    } catch (reason) { if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "引用暂时无法核对。"); }
  }
  return <><div className={styles.detailActions}><button disabled={!row.saved_quote || row.source.source_status !== "available"} onClick={() => void cite(true)}><Copy size={14} />复制摘录（含出处）</button><button disabled={row.source.source_status !== "available"} onClick={() => void cite(false)}><Quote size={14} />查看引用</button><button disabled={row.source.source_status !== "available"} onClick={onPreview}><BookOpen size={14} />核对原文</button>{message ? <p role="status">{message}</p> : null}</div>{citation ? <SharedCitationOverlay {...citation} open onClose={() => setCitation(null)} /> : null}</>;
}

type BulkIntent = { requestId: string; kind: "export" | "erase"; targets: PrivacyTarget[] };
function NotebookActions({ owner, chosen, onChanged }: { owner: string; chosen: NotebookRecord[]; onChanged: () => void }) {
  const [intent, setIntent] = useState<BulkIntent | null>(null), [operation, setOperation] = useState<string | null>(null), [projectRows, setProjectRows] = useState<NotebookRecord[] | null>(null);
  const [exportRows, setExportRows] = useState<NotebookRecord[] | null>(null);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(""), [broken, setBroken] = useState(false);
  const controller = useOwnerController(), sending = useRef(false); const storageKey = `stl-notebook-operation:${owner}`;
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try { const raw = sessionStorage.getItem(storageKey); if (!raw) return; const value = JSON.parse(raw) as BulkIntent;
        if (!value || !/^[\da-f-]{36}$/i.test(value.requestId) || !["export", "erase"].includes(value.kind) || !Array.isArray(value.targets) || !value.targets.length || value.targets.length > 20 || value.targets.some(row => !row || !["annotations", "bookmarks"].includes(row.category) || !/^[\da-f-]{36}$/i.test(row.id) || typeof row.revision !== "string")) throw Error("原请求记录无法读取，请先到隐私与资料核对任务。");
        setIntent(value); setMessage("上次请求尚未取得明确结果，可核对原请求。");
      } catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "无法读取原请求。"); }
    }); return () => { active = false; };
  }, [storageKey]);
  async function submit(kind?: BulkIntent["kind"], selectedRows = chosen) {
    const request = controller.current, action = intent || (kind && selectedRows.length ? { requestId: createRequestKey(), kind, targets: selectedRows.map(target) } : null);
    if (!action || !request || request.signal.aborted || sending.current || broken) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(action)); setIntent(action);
      const result = await withPrivateOwner(owner, () => preparePrivacyOperation(owner, action.requestId, { kind: action.kind, targets: action.targets }, request.signal), request.signal);
      if (!request.signal.aborted) { sessionStorage.removeItem(storageKey); setIntent(null); setOperation(result.id); onChanged(); }
    } catch (reason) {
      if (request.signal.aborted) return;
      if (reason instanceof ApiRequestError && [400, 403, 404, 409].includes(reason.status)) { sessionStorage.removeItem(storageKey); setIntent(null); onChanged(); }
      setMessage(reason instanceof Error ? reason.message : "请求结果未确认，请核对原请求。");
    } finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  const disabled = busy || !!intent || broken || !chosen.length;
  return <><div className={styles.actions} data-selected={chosen.length>0}><span className={styles.mobileCount}>已选择 {chosen.length} 条</span><button className={styles.primary} disabled={disabled} onClick={() => setProjectRows([...chosen])}>加入研究</button><button disabled={disabled} onClick={() => setExportRows([...chosen])}><Download size={14} />导出</button><button disabled={disabled} onClick={() => void submit("erase")}><Trash2 size={14} />删除</button></div>
    {message ? <p className={styles.notice} role="status">{message}</p> : null}{intent ? <button disabled={busy} onClick={() => void submit()}>核对原请求</button> : null}{broken ? <Link href="/account/privacy">打开隐私与资料核对</Link> : null}
    {operation ? <OperationDialog id={operation} ownerId={owner} onClose={() => { setOperation(null); onChanged(); }} onChanged={onChanged} onInvalid={reason => setMessage(reason instanceof Error ? reason.message : "账户状态需重新核对。")} /> : null}
    {projectRows ? <Modal title="加入我的研究" onClose={() => setProjectRows(null)}><ProjectForm owner={owner} rows={projectRows} onDone={() => { setProjectRows(null); onChanged(); }} /></Modal> : null}
    {exportRows ? <Modal title="导出选中的阅读记录" onClose={() => setExportRows(null)}><NotebookExport owner={owner} rows={exportRows} onJson={() => { const selected = exportRows; setExportRows(null); void submit("export", selected); }} /></Modal> : null}</>;
}

function NotebookExport({ owner, rows, onJson }: { owner: string; rows: NotebookRecord[]; onJson: () => void }) {
  const [format, setFormat] = useState<NotebookExportInput["format"]>("pdf"), [notes, setNotes] = useState(false), [quotes, setQuotes] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const controller = useOwnerController(), sending = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); const request = controller.current;
    if (!request || request.signal.aborted || sending.current) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      await downloadNotebook(owner, { targets: rows.map(target), format, include_notes: notes, include_quotes: quotes }, AbortSignal.any([request.signal, AbortSignal.timeout(30000)]));
      if (!request.signal.aborted) setMessage("所选文件已准备并交给浏览器下载。");
    } catch (reason) { if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "导出未完成，请保留选择后重试。"); }
    finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  return <form className={styles.editor} onSubmit={event => void submit(event)}><p>本次选择 {rows.length} 条。只导出这些记录；关闭后不会保留未确认的下载内容。</p><ul className={styles.exportList}>{rows.map(row => <li key={row.key}><strong>{row.work.title}</strong><span>{labels[row.kind]} · PDF 第 {row.pdf_page} 页</span>{row.source.source_status !== "available" ? <small>当前来源不可核对；PDF/Markdown 可保留本人记录</small> : null}</li>)}</ul>
    <fieldset disabled={busy}><legend>文件格式</legend><div className={styles.exportChoices}>{([["pdf", "PDF"], ["markdown", "Markdown"], ["bibtex", "BibTeX"], ["ris", "RIS"]] as const).map(([value, label]) => <label key={value}><input type="radio" name="notebook-export-format" checked={format === value} onChange={() => setFormat(value)} />{label}</label>)}</div>
      <label className={styles.exportCheck}><input type="checkbox" checked={quotes} onChange={event => setQuotes(event.target.checked)} />包含保存时的摘录</label><label className={styles.exportCheck}><input type="checkbox" checked={notes} onChange={event => setNotes(event.target.checked)} />包含本人笔记和标签</label></fieldset>
    <p className={styles.muted}>默认仅导出记录和来源信息。旧摘录始终标为个人保存记录，引用功能会另行核对当前原文；不下载 PDF 原件、不授予学术记忆或公开分享权限。</p>{message ? <p role="status">{message}</p> : null}<footer><button type="button" disabled={busy} onClick={onJson}>原始 JSON 备份</button><button className={styles.primary} disabled={busy}>{busy ? "正在准备…" : "确认下载所选范围"}</button></footer><p className={styles.muted}>JSON 备份会沿隐私与资料流程生成所选记录的完整备份，含保存的摘录和本人笔记。</p></form>;
}

function ProjectForm({ owner, rows, onDone }: { owner: string; rows: NotebookRecord[]; onDone: () => void }) {
  const [project, setProject] = useState<NotebookChoice | null>(null), [note, setNote] = useState(""), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const controller = useOwnerController(), sending = useRef(false), pending = useRef<{ request_id: string; project_id: string; expected_revision: number; targets: PrivacyTarget[]; note: string } | null>(null);
  const [uncertain, setUncertain] = useState(false), [recovery, setRecovery] = useState<{ project_id: string; request_id: string } | null>(null), [broken, setBroken] = useState(false);
  const storageKey = `stl-notebook-project:${owner}`;
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try { const raw = sessionStorage.getItem(storageKey); if (!raw) return; const value = JSON.parse(raw) as { project_id: string; request_id: string };
        if (!/^[\da-f-]{36}$/i.test(value?.project_id) || !/^[\da-f-]{36}$/i.test(value?.request_id)) throw Error("暂时无法读取处理记录，请到我的研究核对。");
        setRecovery(value); setUncertain(true); setMessage("上次操作结果未确认，请先核对原操作结果。");
      } catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "原请求无法读取。"); }
    }); return () => { active = false; };
  }, [storageKey]);
  function clear() { sessionStorage.removeItem(storageKey); setRecovery(null); setUncertain(false); pending.current = null; }
  async function lookup() {
    const request = controller.current; if (!recovery || !request || request.signal.aborted || sending.current) return;
    sending.current = true; setBusy(true);
    try {
      const result = await withPrivateOwner(owner, () => notebookRequest<{ owner_id: string; project_id: string; exists: boolean }>(owner, `${notebookPath}add-to-project/?${new URLSearchParams(recovery)}`, { signal: request.signal }), request.signal);
      if (result.project_id !== recovery.project_id) throw Error("操作结果与原研究不符。");
      if (!request.signal.aborted) { clear(); setMessage(result.exists ? "原操作已保存，可在我的研究查看。" : "原操作已完成，该研究随后已删除，不会重新创建。"); }
    } catch (reason) { if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "原操作结果暂时无法核对。"); }
    finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); const request = controller.current;
    if (!request || request.signal.aborted || sending.current || broken || (recovery && !pending.current) || !project?.revision) return;
    sending.current = true; setBusy(true); setMessage("");
    const data = pending.current || { request_id: createRequestKey(), project_id: project.id, expected_revision: project.revision, targets: rows.map(target), note };
    pending.current = data; setUncertain(true);
    try {
      const identity = { request_id: data.request_id, project_id: data.project_id };
      sessionStorage.setItem(storageKey, JSON.stringify(identity)); setRecovery(identity);
      await withPrivateOwner(owner, () => notebookRequest<{ owner_id: string; project_id: string; revision: number }>(owner, `${notebookPath}add-to-project/`, { method: "POST", signal: request.signal, body: JSON.stringify(data) }), request.signal);
      if (!request.signal.aborted) { clear(); onDone(); }
    } catch (reason) {
      if (request.signal.aborted) return;
      if (reason instanceof ApiRequestError && [400, 403, 404, 409].includes(reason.status)) { clear(); }
      setMessage(reason instanceof Error ? reason.message : "结果未确认，请使用原请求重试。");
    } finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  return <form className={styles.editor} onSubmit={event => void submit(event)}><p>将明确选择的 {rows.length} 条记录对应的原文加入研究，并关联这些记录。私人笔记正文不会自动复制或授权给模型。</p><fieldset disabled={busy || uncertain || broken}><ChoicePicker owner={owner} kind="projects" label="选择我的研究" value={project?.id || ""} onChange={(_, row) => setProject(row || null)} /><label>新增选材备注（已有材料备注保留）<textarea maxLength={200} value={note} onChange={event => setNote(event.target.value)} /></label></fieldset>{message ? <p role="alert">{message}</p> : null}<button className={styles.primary} disabled={busy || broken || !project?.revision}>{busy ? "正在保存…" : uncertain ? "重试原请求" : "加入研究"}</button>{recovery ? <button type="button" disabled={busy} onClick={() => void lookup()}>核对原操作结果</button> : null}{recovery || broken ? <button type="button" disabled={busy} onClick={async () => { if ((await confirmAction("请先在我的研究核对原操作。确认结束此请求的恢复？已保存内容不会删除。"))) { clear(); setBroken(false); } }}>已核对，结束恢复</button> : null}<Link href="/account/research">管理我的研究</Link></form>;
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) { return <Dialog open onRequestClose={onClose} className={styles.modal} aria-label={title}><header><h2>{title}</h2><button type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button></header>{children}</Dialog>; }
