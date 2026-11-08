"use client";

import { confirmAction } from "@/lib/ui-dialog";

import { LoadingState } from "@/components/ui/loading-state";
import { MediaPlacement } from "@/components/media-placement";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, ChevronRight, Download, FileText, LockKeyhole, MoreVertical, Plus, RefreshCw, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { privateRequest, researchRecordPath, type ResolvedEvidence } from "@/lib/api/research.client";
import { changeMemoryUsage, proposeMemory, saveMemory, type AnnotationChoice, type ConfirmedMemory, type MemoryKind, type MemoryPage, type MemoryScope, type MemoryState, type MemoryUsage } from "@/lib/api/memory.client";
import type { Paginated } from "@/lib/api/pagination";
import { researchEvidenceKey, researchEvidenceReference, researchReaderHref } from "@/lib/api/research-evidence";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { PlanMaterialPicker } from "./reading-plan-form";
import styles from "./confirmed-notes.module.css";
import { ReaderMobileNav } from "./reader-mobile-nav";

const kindNames: Record<MemoryKind, string> = { understanding: "理论判断", question: "问题意识", contradiction: "矛盾与修正", concept: "概念理解", method: "研究方法", observation: "经验观察" };
const stateNames: Record<MemoryState, string> = { confirmed: "已确认", proposed: "待确认", ignored: "暂不采纳" };
const dateLabel = (value: string) => Number.isNaN(Date.parse(value)) ? "时间未记录" : new Date(value).toLocaleDateString("zh-CN");
const titleOf = (record: ConfirmedMemory) => record.data.body.split("\n")[0].slice(0, 100);
function safeCount(counts: MemoryPage["counts"], key: string) {
  const count = counts?.[key];
  return typeof count === "number" ? count : undefined;
}

export function ConfirmedNotesWorkspace() {
  const { state: session, retry } = useSessionBootstrap();
  const [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  useEffect(() => { if (session.status === "unauthenticated") window.location.replace("/login?next=%2Faccount%2Fconfirmed-notes"); }, [session.status]);
  if (session.status !== "authenticated" || session.user?.id === undefined) return <div className={styles.page}><div className={styles.empty} role="status"><h1>我的已确认笔记</h1><p>{session.message || "正在验证登录状态…"}</p>{["temporary_error", "forbidden"].includes(session.status) ? <button onClick={retry}>重新验证</button> : null}</div></div>;
  return <MemoryCollection key={`${session.user.id}:${epoch}`} ownerId={String(session.user.id)} />;
}

function MemoryCollection({ ownerId }: { ownerId: string }) {
  const locationParams = useSearchParams();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [kind, setKind] = useState("");
  const [source, setSource] = useState("");
  const [order, setOrder] = useState("updated_at");
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [inspect, setInspect] = useState<string | null>(() => {
    const id = locationParams.get("memory") || "";
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) ? id : null;
  });
  const [usage, setUsage] = useState<string | null>(null);
  const [create, setCreate] = useState(false);
  const [notice, setNotice] = useState("");
  const [exporting, setExporting] = useState(false);
  const [privateInvalid, setPrivateInvalid] = useState(false);
  const params = new URLSearchParams({ page: String(page), order });
  if (search) params.set("q", search);
  if (state) params.set("state", state);
  if (kind) params.set("kind", kind);
  if (source) params.set("source_status", source);
  const workspace = usePersistentWorkspace<MemoryPage>(`/reading/research-memories/?${params}`, ownerId);
  const rows = workspace.data?.results || [];
  const counts = workspace.data?.counts;
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  function filter(change: () => void) { change(); setPage(1); setSelected([]); }
  function saved(message: string) { workspace.reload(); setNotice(message); }
  function invalidate() { setPrivateInvalid(true); setInspect(null); setUsage(null); setCreate(false); setSelected([]); workspace.reload(); }
  async function exportSelection() {
    if (!selected.length || exporting) return;
    setExporting(true); setNotice("");
    try {
      const data = await withPrivateOwner(ownerId, () => Promise.all(selected.map(id => privateRequest<ConfirmedMemory>(`${researchRecordPath("research-memories", id)}export/`))));
      if (!alive.current) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify({ schema_version: 1, memories: data }, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = "我的选定笔记.json"; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(`已导出 ${data.length} 条本人笔记及其来源状态。`);
    } catch (reason) { if (alive.current) { setNotice(reason instanceof Error ? reason.message : "导出失败，请重试。"); if (reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403].includes(reason.status)) invalidate(); } }
    finally { if (alive.current) setExporting(false); }
  }
  if (privateInvalid) return <div className={styles.page}><div className={styles.empty} role="alert"><p>登录账户暂时无法确认，私人内容已收起。</p><button onClick={() => window.location.reload()}>重新验证账户</button></div></div>;
  return <div className={styles.page}><div className={styles.shell} data-inspecting={Boolean(inspect) || undefined}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/home">首页</Link><ChevronRight size={12} /><Link href="/account">读者中心</Link><ChevronRight size={12} /><span>已确认笔记</span></nav>
    <header className={styles.heading}><div><h1>我的已确认笔记</h1><p>由你确认，在选定的研究与阅读计划中使用。</p></div><Link href="/account/notes">查看我的笔记 <ChevronRight size={14} /></Link></header>
    <div className={styles.layout}>
      <aside className={`${styles.sidebar} ${filtersOpen ? styles.showFilters : ""}`}><button className={styles.gold} onClick={() => setCreate(true)}><Plus size={17} />从笔记选择</button>
        <nav aria-label="笔记状态">{[["", "全部笔记", "total"], ["confirmed", "我确认的笔记", "confirmed"], ["proposed", "待确认的笔记", "proposed"], ["needs_revision", "需要修正的笔记", "needs_revision"], ["ignored", "暂不采纳", "ignored"]].map(([value, label, key]) => <button key={key} className={state === value ? styles.active : ""} aria-current={state === value ? "page" : undefined} onClick={() => filter(() => setState(value))}>{label}<span>{safeCount(counts, key) ?? ""}</span></button>)}</nav>
        <fieldset><legend>按类型筛选</legend>{Object.entries(kindNames).map(([value, label]) => <label key={value}><input type="radio" name="memory-kind" checked={kind === value} onChange={() => filter(() => setKind(value))} />{label}</label>)}<button className={styles.textButton} onClick={() => filter(() => setKind(""))}>全部类型</button></fieldset>
        <fieldset><legend>按来源筛选</legend><label><input type="radio" name="memory-source" checked={source === "unavailable"} onChange={() => filter(() => setSource("unavailable"))} />来源不可用</label><label><input type="radio" name="memory-source" checked={source === "updated"} onChange={() => filter(() => setSource("updated"))} />原文已更新</label><label><input type="radio" name="memory-source" checked={source === "available"} onChange={() => filter(() => setSource("available"))} />来源可核对</label><button className={styles.textButton} onClick={() => filter(() => setSource(""))}>全部来源</button></fieldset><p className={styles.quiet}><LockKeyhole size={13} />所有内容仅本人可见。</p>
      </aside>
      <section className={styles.main} aria-label="笔记列表">
        <div className={styles.toolbar}><form onSubmit={event => { event.preventDefault(); filter(() => setSearch(query.trim())); }}><Search size={16} /><input aria-label="搜索笔记" placeholder="按问题、概念或状态查找，例如：国家、权力、待确认…" maxLength={1200} value={query} onChange={event => setQuery(event.target.value)} /><button className={styles.primary} type="submit">搜索</button></form><button aria-expanded={filtersOpen} className={styles.filterButton} onClick={() => setFiltersOpen(value => !value)}><SlidersHorizontal size={15} />筛选</button><select aria-label="笔记排序" value={order} onChange={event => filter(() => setOrder(event.target.value))}><option value="updated_at">更新时间</option><option value="newest">创建时间</option></select></div>
        <p className={styles.notice}><LockKeyhole size={13} />仅使用本次选择的笔记。</p>
        {notice ? <p className={styles.feedback} role="status">{notice}</p> : null}
        {workspace.error ? <div className={styles.error} role="alert">{workspace.error}<button onClick={workspace.reload}><RefreshCw size={14} />重新读取</button></div> : null}
        {workspace.loading ? <div className={styles.empty} role="status">正在读取你的笔记…</div> : null}
        {selected.length && workspace.data ? <div className={styles.selection}><span>已选择 {selected.length} 条</span><button onClick={() => setInspect(selected[0])}>逐条核对</button><button onClick={() => void exportSelection()} disabled={exporting}><Download size={14} />{exporting ? "正在导出…" : "导出所选"}</button><button onClick={() => setSelected([])}>清空选择</button></div> : null}
        {workspace.data ? <><div className={styles.mobileTabs}>{[["", "全部笔记", "total"], ["confirmed", "我确认的笔记", "confirmed"], ["proposed", "待确认的笔记", "proposed"]].map(([value, label, key]) => <button key={value} className={state === value ? styles.active : ""} aria-current={state === value ? "page" : undefined} onClick={() => filter(() => setState(value))}>{label}<span>{safeCount(counts, key) ?? ""}</span></button>)}</div>
          {rows.length ? <div>{rows.map(record => <MemoryRow key={record.id} record={record} checked={selected.includes(record.id)} disabled={selected.length >= 40 && !selected.includes(record.id)} onCheck={checked => setSelected(previous => checked ? [...previous, record.id] : previous.filter(id => id !== record.id))} onInspect={() => setInspect(record.id)} onUsage={() => setUsage(record.id)} />)}</div> : <div className={styles.empty}><img className={styles.emptyIllustration} src="/brand/stl-confirmed-notes-empty-final-r2.png" alt="" width={53} height={63}/><h2>{search || state || kind || source ? "当前条件下没有笔记" : "还没有已确认笔记"}</h2><p>选择阅读笔记，核对后保存。用于研究或计划时需另行选择。</p><button className={styles.primary} onClick={() => setCreate(true)}>从笔记选择</button></div>}
          <footer className={styles.pagination}><span>共 {workspace.data.count} 条</span><button disabled={page === 1} onClick={() => { setPage(value => value - 1); setSelected([]); }}>上一页</button><span>第 {page} 页</span><button disabled={!workspace.data.next} onClick={() => { setPage(value => value + 1); setSelected([]); }}>下一页</button></footer></> : null}
      </section>
    </div>
    {workspace.data && inspect ? <MemoryInspector id={inspect} ownerId={ownerId} rows={rows} onSelect={setInspect} onClose={() => setInspect(null)} onUsage={() => { setUsage(inspect); setInspect(null); }} onSaved={saved} onDeleted={() => { setSelected(previous => previous.filter(id => id !== inspect)); setInspect(null); saved("已删除这条确认笔记及其派生资料，原始阅读笔记保留。"); }} /> : null}
    {workspace.data && usage ? <MemoryUsageDialog key={usage} id={usage} ownerId={ownerId} onClose={() => setUsage(null)} onSaved={saved} /> : null}
    {workspace.data && create ? <MemoryProposal ownerId={ownerId} onClose={() => setCreate(false)} onInvalid={invalidate} onSaved={record => { setCreate(false); setInspect(record.id); saved("已保存待确认笔记，请核对后作出决定。"); }} /> : null}
  </div><ReaderMobileNav variant={inspect?"memory-review":"memory"}/></div>;
}

function MemoryRow({ record, checked, disabled, onCheck, onInspect, onUsage }: { record: ConfirmedMemory; checked: boolean; disabled: boolean; onCheck: (value: boolean) => void; onInspect: () => void; onUsage: () => void }) {
  const first = record.data.sources?.[0];
  const summary = record.data.source_summaries?.[0];
  const needsRevision = ["updated","unavailable"].includes(record.data.source_status || "") || record.state === "proposed" && Boolean(record.data.history?.length);
  const label = needsRevision ? "需要修正" : stateNames[record.state as MemoryState] || "待核对";
  const scopes = record.data.usage_scopes || [];
  const sourceHref = first ? researchReaderHref(first) : undefined;
  return <article className={styles.row}>
    <input type="checkbox" aria-label={`选择笔记：${titleOf(record)}`} checked={checked} disabled={disabled} onChange={event => onCheck(event.target.checked)} />
    <div className={styles.cover}>{summary?.cover_url ? <MediaPlacement uses={summary.cover_media?.display_uses} fallback={<FileText size={26} aria-hidden="true" />}><img src={summary.cover_url} alt="" loading="lazy" /></MediaPlacement> : <FileText size={26} aria-hidden="true" />}</div>
    <div className={styles.copy}><span className={styles.badge}>{label}</span><button className={styles.titleButton} onClick={onInspect}>{titleOf(record)}</button><p>{record.data.body}</p><span className={styles.tag}>{kindNames[record.data.kind] || "个人笔记"}</span>{record.data.source_status === "unavailable" || record.data.source_status === "updated" ? <span className={styles.unavailable}>{record.data.source_status === "updated" ? "原文已更新" : "来源不可用"}</span> : null}</div>
    <div className={styles.source}><small>来源</small>{sourceHref ? <Link href={sourceHref}>{summary?.title || first?.title || "查看原文"}</Link> : <span>{summary?.title || first?.title || "本人笔记"}</span>}{summary || first?.source_status === "available" ? <p>{(summary?.authors || first?.authors)?.join("、")}{summary?.printed_label || first?.printed_label ? ` · 第 ${summary?.printed_label || first?.printed_label} 页` : first?.pdf_page ? ` · PDF 第 ${first.pdf_page} 页` : ""}</p> : null}<button className={styles.textButton} onClick={onInspect}><FileText size={12} />我的笔记</button><time dateTime={record.updated_at}>{dateLabel(record.updated_at)}</time></div>
    <div className={styles.rowActions}><span className={styles.confirmed}><Check size={12} />{record.state === "confirmed" ? "本人已确认" : record.state === "ignored" ? "暂不采纳" : "确认后可用"}</span><button className={styles.usage} role="switch" aria-checked={scopes.length > 0} onClick={onUsage} aria-label={`选择笔记使用范围：${titleOf(record)}`}><span aria-hidden="true" className={scopes.length ? styles.switchOn : styles.switchOff} /><span>{scopes.length ? `已用于 ${scopes.length} 个范围` : "用于当前研究与计划"}</span></button><small><LockKeyhole size={11} />仅本人可见</small></div>
    <details data-action-menu className={styles.menu}><summary aria-label={`笔记操作：${titleOf(record)}`}><MoreVertical size={17} /></summary><div data-menu-panel><button onClick={onInspect}>查看原笔记</button><button onClick={onInspect}>编辑与确认</button><button onClick={onUsage}>使用范围 / 停止使用</button></div></details>
  </article>;
}

function MemoryInspector({ id, ownerId, rows, onSelect, onClose, onUsage, onSaved, onDeleted }: { id: string; ownerId: string; rows: ConfirmedMemory[]; onSelect: (id: string) => void; onClose: () => void; onUsage: () => void; onSaved: (message: string) => void; onDeleted: () => void }) {
  const workspace = usePersistentWorkspace<ConfirmedMemory>(researchRecordPath("research-memories", id), ownerId);
  const [dirty, setDirty] = useState(false);
  const [queueState,setQueueState]=useState(rows.find(row=>row.id===id)?.state||"all");
  const [queueQuery,setQueueQuery]=useState(""),[queueSearch,setQueueSearch]=useState("");
  const [queueSource,setQueueSource]=useState("all"),[queueOrder,setQueueOrder]=useState("updated_at"),[queuePage,setQueuePage]=useState(1);
  const [queueFilters,setQueueFilters]=useState(false);
  const queueParams=new URLSearchParams({state:queueState,q:queueSearch,source_status:queueSource,order:queueOrder,page:String(queuePage)});
  const queue=usePersistentWorkspace<MemoryPage>(`/reading/research-memories/?${queueParams}`,ownerId);
  function queueFilter(change:()=>void){change();setQueuePage(1);}
  async function close() { if (!workspace.pending && (!workspace.data || !dirty || (await confirmAction("当前修改尚未保存，确定放弃修改吗？")))) onClose(); }
  async function selectRecord(next: string) { if (next !== id && !workspace.pending && (!dirty || (await confirmAction("当前修改尚未保存，确定放弃修改并查看另一条笔记吗？")))) onSelect(next); }
  return <section className={styles.confirmation} aria-labelledby="memory-inspector-title"><header className={styles.confirmationHeader}><div><h1 id="memory-inspector-title">确认笔记</h1></div><aside><LockKeyhole size={20}/><div><strong>私人笔记</strong></div></aside></header>
    <nav className={styles.queueTabs} aria-label="确认笔记状态">{[["proposed","待确认"],["confirmed","已确认"],["revised","修改记录"]].map(([value,label])=><button key={value} aria-current={queueState===value?"page":undefined} onClick={()=>queueFilter(()=>setQueueState(value))}>{label}{safeCount(queue.data?.counts,value)!==undefined?`（${safeCount(queue.data?.counts,value)}）`:""}</button>)}</nav>
    <div className={styles.queueTools} data-filters-open={queueFilters||undefined}><form onSubmit={event=>{event.preventDefault();queueFilter(()=>setQueueSearch(queueQuery.trim()));}}><Search size={17}/><input aria-label="搜索确认队列" placeholder="搜索我的笔记、概念或问题…" value={queueQuery} maxLength={1200} onChange={event=>setQueueQuery(event.target.value)}/><button type="submit">搜索</button></form><button className={styles.queueFilterToggle} aria-label="筛选确认队列" aria-expanded={queueFilters} onClick={()=>setQueueFilters(value=>!value)}><SlidersHorizontal size={17}/></button><select aria-label="确认队列来源状态" value={queueSource} onChange={event=>queueFilter(()=>setQueueSource(event.target.value))}><option value="all">全部来源</option><option value="available">来源可核对</option><option value="updated">原文已更新</option><option value="unavailable">来源不可用</option><option value="no_source">未关联原文</option></select><select aria-label="确认队列笔记状态" value={queueState} onChange={event=>queueFilter(()=>setQueueState(event.target.value))}><option value="all">全部状态</option><option value="proposed">待确认</option><option value="confirmed">已确认</option><option value="needs_revision">需要修正</option><option value="ignored">暂不采纳</option><option value="revised">有修改记录</option></select><select aria-label="确认队列排序" value={queueOrder} onChange={event=>queueFilter(()=>setQueueOrder(event.target.value))}><option value="updated_at">最近更新</option><option value="newest">创建时间</option></select></div>
    {queue.error?<p className={styles.error} role="alert">{queue.error}<button onClick={queue.reload}>重新读取</button></p>:null}
    <div className={styles.confirmationQueue} aria-label="确认笔记队列"><button className={styles.returnToList} disabled={workspace.pending} onClick={close}>返回笔记列表</button>{(queue.data?.results||[]).map(row => { const source = row.data.source_summaries?.[0]; return <button className={styles.queueRow} aria-pressed={row.id === id} disabled={workspace.pending} key={row.id} onClick={() => selectRecord(row.id)}><span className={styles.queueCheck}>{row.id===id?<Check size={15}/>:null}</span><span className={styles.cover}>{source?.cover_url?<MediaPlacement uses={source.cover_media?.display_uses} fallback={<FileText size={24}/>}><img src={source.cover_url} alt=""/></MediaPlacement>:<FileText size={24}/>}</span><span className={styles.queueSource}><strong>{source?.title||row.data.sources[0]?.title||"本人笔记"}</strong><span>{source?.authors?.join("、")}</span></span><span className={styles.queueCopy}><span className={styles.badge}>{stateNames[row.state as MemoryState]||"待核对"}</span><strong>{titleOf(row)}</strong><span>{row.data.body}</span><small>我的原始笔记 · 来源：{source?.printed_label?`第 ${source.printed_label} 页`:row.data.sources[0]?.pdf_page?`PDF 第 ${row.data.sources[0].pdf_page} 页`:"待核对"}</small></span><time dateTime={row.updated_at}>{dateLabel(row.updated_at)}</time></button>; })}</div>
    {queue.loading?<LoadingState role="status">正在读取确认队列…</LoadingState>:queue.data&&!queue.data.results.length?<p className={styles.queueEmpty}>当前条件下没有笔记，已打开的详情仍保留。</p>:null}
    {queue.data?<footer className={styles.pagination}><span>共 {queue.data.count} 条</span><button disabled={queuePage===1} onClick={()=>setQueuePage(value=>value-1)}>上一页</button><span>第 {queuePage} 页</span><button disabled={!queue.data.next} onClick={()=>setQueuePage(value=>value+1)}>下一页</button></footer>:null}
    <section className={`${styles.dialog} ${styles.inspector}`} aria-label="查看详情并确认笔记">{!workspace.data ? <div className={styles.empty}><p role="status">{workspace.error || "正在读取笔记…"}</p><button onClick={workspace.reload}>重新读取</button></div> : <MemoryEditor key={workspace.data.id} record={workspace.data} workspace={workspace} ownerId={ownerId} onDirty={setDirty} onClose={onClose} onUsage={onUsage} onSaved={message=>{queue.reload();onSaved(message);}} onDeleted={onDeleted} />}</section>
  </section>;

}

function MemoryEditor({ record, workspace, ownerId, onDirty, onClose, onUsage, onSaved, onDeleted }: { record: ConfirmedMemory; workspace: ReturnType<typeof usePersistentWorkspace<ConfirmedMemory>>; ownerId: string; onDirty: (dirty: boolean) => void; onClose: () => void; onUsage: () => void; onSaved: (message: string) => void; onDeleted: () => void }) {
  const [body, setBody] = useState(record.data.body);
  const [kind, setKind] = useState(record.data.kind);
  const [base, setBase] = useState({ body: record.data.body, kind: record.data.kind, revision: record.revision });
  const [tab, setTab] = useState<"note" | "original" | "sources" | "history">("note");
  const [decision, setDecision] = useState<MemoryState>(record.state === "ignored" ? "ignored" : "confirmed");
  const [remove, setRemove] = useState<number | null>(null);
  const [sourceEdit, setSourceEdit] = useState<{ revision: number; sources: ResolvedEvidence[] } | null>(null);
  const [actionError, setActionError] = useState("");
  const dirty = useUnsavedForm({ body, kind, sourcesOpen: sourceEdit !== null }, { body: base.body, kind: base.kind, sourcesOpen: false });
  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  const note = record.data.origin_note;
  async function close() { if (!dirty || (await confirmAction("当前修改尚未保存，确定放弃修改吗？"))) onClose(); }
  function acceptSourceChange(result: ConfirmedMemory) {
    if (body === base.body && kind === base.kind) { setBody(result.data.body); setKind(result.data.kind); }
    setBase({ body: result.data.body, kind: result.data.kind, revision: result.revision });
    setDecision("proposed");
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setActionError("");
    try {
      const result = await workspace.mutate(JSON.stringify({ body, kind, decision, revision: base.revision }), () => saveMemory(record.id, { expected_revision: base.revision, body, kind, state: decision }));
      if (result) { setBase({ body: result.data.body, kind: result.data.kind, revision: result.revision }); setBody(result.data.body); setKind(result.data.kind); onSaved(decision === "confirmed" ? "笔记已由本人确认；使用范围需另行选择。" : "笔记状态与修改已保存。"); }
    } catch { /* The shared workspace keeps inputs and reports conflicts. */ }
  }
  async function destroy() {
    setActionError("");
    try {
      const result = await workspace.mutate(`delete:${remove}`, async latest => {
        await privateRequest(researchRecordPath("research-memories", latest.id), { method: "DELETE", body: JSON.stringify({ expected_revision: remove }) });
        return latest;
      });
      if (result) onDeleted();
    } catch (reason) { setRemove(null); setActionError(reason instanceof Error ? reason.message : "删除失败，请重试。"); }
  }
  async function refreshOrigin() {
    try {
      const result = await workspace.mutate(`origin:${record.revision}`, () => saveMemory(record.id, { expected_revision: record.revision, refresh_origin: true }));
      if (result) { acceptSourceChange(result); onSaved("已更新关联来源；原笔记和修改记录继续保留，请重新核对。"); }
    } catch { /* The shared workspace preserves the draft. */ }
  }
  async function saveSources(event: FormEvent) {
    event.preventDefault(); if (!sourceEdit) return;
    try {
      const result = await workspace.mutate(JSON.stringify(sourceEdit), () => saveMemory(record.id, { expected_revision: sourceEdit.revision, sources: sourceEdit.sources.map(researchEvidenceReference) }));
      if (result) { acceptSourceChange(result); setSourceEdit(null); onSaved("来源关联已保存，原笔记保留；请重新确认修改后的认识。此前使用范围已撤销。"); }
    } catch { /* Keep the chosen sources and explicit base on conflict. */ }
  }
  return <>{["unavailable","updated"].includes(record.data.source_status||"")?<section className={styles.sourceAlert} data-source-status={record.data.source_status}><strong>{record.data.source_status==="updated"?"原文已更新":"来源不可用"}</strong><p>{record.data.source_status==="updated"?"该条笔记的来源文献已发生变化，请查看当前原文，再决定是否更新关联。":"该条笔记的来源暂时无法访问，请检查并更新来源关联。"}原始笔记与此前确认内容均保留。</p><button type="button" onClick={()=>setTab("sources")}>{record.data.source_status==="updated"?"查看变化":"检查来源"}</button><button type="button" onClick={close}>稍后处理</button></section>:null}<div className={styles.detailTabs}>{[["note", "待核实建议 / 我的判断"], ["original", "我的原始笔记"], ["sources", "来源信息"], ["history", "修改记录"]].map(([value, label]) => <button key={value} aria-pressed={tab === value} onClick={() => setTab(value as typeof tab)}>{label}</button>)}</div>
    {workspace.error || actionError ? <p className={styles.error} role="alert">{workspace.error || actionError}</p> : null}
    {workspace.conflict ? <section className={styles.conflict}><h3>另一处已更新，当前输入仍保留</h3><p>最新保存的正文：{record.data.body}</p><button disabled={workspace.pending} onClick={() => { setBase(previous => ({ ...previous, revision: record.revision })); setActionError("已选择当前最新版本作为保存基准，请再次核对输入并保存。"); }}>保留输入，以最新版本为保存基准</button></section> : null}
    <form onSubmit={save}>
      {tab === "note" ? <div className={styles.editorGrid}><section><label>我确认的认识、问题或修正<textarea aria-label="笔记正文" rows={8} value={body} onChange={event => setBody(event.target.value)} required maxLength={20000} /></label><label>笔记类型<select value={kind} onChange={event => setKind(event.target.value as MemoryKind)}>{Object.entries(kindNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><p className={styles.quiet}>原始阅读笔记保留。</p></section><fieldset><legend>我的判断</legend>{[["confirmed", "确认这条笔记"], ["proposed", "修改后再确认"], ["ignored", "暂不采纳"]].map(([value, label]) => <label key={value}><input type="radio" name="memory-decision" checked={decision === value} onChange={() => setDecision(value as MemoryState)} />{label}</label>)}<p>已确认内容也只在你选定的研究或计划中使用。</p><button type="button" disabled={workspace.pending || record.state !== "confirmed"} onClick={async () => { if (!dirty || (await confirmAction("当前修改尚未保存，确定先查看使用范围吗？"))) onUsage(); }}>选择使用范围</button></fieldset></div> : null}
      {tab === "original" ? <section className={styles.reading}><h3>我的原始笔记</h3>{note ? <><p>{note.body_text || note.body || "原笔记未填写正文。"}</p>{note.quote ? <blockquote>{note.quote}</blockquote> : null}{note.source_status === "unavailable" ? <p>原文当前不可用，自己的笔记仍保留。</p> : null}{note.reader_url?.startsWith("/reader/") || note.reader_url?.startsWith("/account/notes/") ? <Link href={note.reader_url} target="_blank" rel="noopener">打开原始笔记 ↗</Link> : null}</> : <p>没有可读取的原始阅读笔记；这条已保存的认识仍然保留。</p>}</section> : null}
      {tab === "sources" ? <section className={styles.reading}><h3>来源信息</h3>{record.data.sources.length ? record.data.sources.map((reference, index) => { const href = researchReaderHref(reference); return <article key={reference.reference_id || index}><h4>{reference.title || `来源 ${index + 1}`}</h4>{reference.source_status === "available" ? <><p>{reference.citation}</p><blockquote>{reference.quote || reference.text}</blockquote>{href ? <Link href={href} target="_blank" rel="noopener">查看原文 ↗</Link> : null}</> : <p>来源已变化、撤回或不可访问。本人保存的笔记不受影响；请重新核对来源。</p>}</article>; }) : <p>此笔记未关联公开原文。</p>}</section> : null}
      {tab === "history" ? <section className={styles.reading}><h3>修改记录</h3>{record.data.history?.length ? [...record.data.history].reverse().map(entry => <article key={`${entry.revision}:${entry.at}`}><time dateTime={entry.at}>{dateLabel(entry.at)} · 修订 {entry.revision}</time><p>{entry.data.body}</p></article>) : <p>尚无修改记录。</p>}</section> : null}
      {tab === "sources" ? <div className={styles.dialogActions}><Link href="/explore/original" target="_blank" rel="noopener">检索来源 ↗</Link><button type="button" disabled={workspace.pending} onClick={() => setSourceEdit({ revision: record.revision, sources: [...record.data.sources] })}>编辑来源</button></div> : null}
      {tab === "sources" && record.data.source_status === "updated" ? <section className={styles.conflict}><h3>原文已有更新</h3><p>原来源保留在历史记录中。请先查看当前原文，再更新关联。</p>{record.data.source_summaries?.map((summary, index) => summary.current_reader_url?.startsWith("/reader/") ? <Link key={index} href={summary.current_reader_url} target="_blank" rel="noopener">查看当前原文 ↗</Link> : null)}<button type="button" disabled={workspace.pending} onClick={() => void refreshOrigin()}>已核对，更新来源关联</button></section> : null}
      <footer className={styles.dialogActions}><button type="button" onClick={() => setRemove(record.revision)} disabled={workspace.pending}>删除这条笔记</button><span /><button type="button" onClick={close} disabled={workspace.pending}>关闭</button><button className={styles.primary} type="submit" disabled={workspace.pending || !body.trim()}>{workspace.pending ? "正在保存…" : decision === "confirmed" ? "确认并保存笔记" : "保存我的决定"}</button></footer>
    </form>
    <Dialog open={remove !== null} onRequestClose={() => { if (!workspace.pending) setRemove(null); }} className={styles.smallDialog} aria-labelledby="memory-delete-title"><h2 id="memory-delete-title">删除这条已保存笔记？</h2><p>删除确认笔记、修改记录和派生资料，并停止在研究与计划中使用。原始阅读笔记保留。</p><div className={styles.dialogActions}><button disabled={workspace.pending} onClick={() => setRemove(null)}>保留笔记</button><button className={styles.primary} disabled={workspace.pending} onClick={() => void destroy()}>确认删除</button></div></Dialog>
    <Dialog open={sourceEdit !== null} onRequestClose={async () => { if (!workspace.pending && (await confirmAction("确定放弃当前未保存的来源选择吗？"))) setSourceEdit(null); }} className={styles.dialog} aria-labelledby="memory-sources-title">{sourceEdit ? <form onSubmit={saveSources}><h2 id="memory-sources-title">编辑笔记来源</h2><p>从已保存的研究选材中选择原文。更改来源后需重新确认笔记与使用范围。</p><div className={styles.usageList}>{sourceEdit.sources.map(reference => <p key={researchEvidenceKey(reference)}><span>{reference.title || "原关联来源"}{reference.source_status !== "available" ? "（当前不可用）" : ""}</span><button type="button" onClick={() => setSourceEdit({ ...sourceEdit, sources: sourceEdit.sources.filter(row => researchEvidenceKey(row) !== researchEvidenceKey(reference)) })}>移除此来源</button></p>)}</div><PlanMaterialPicker ownerId={ownerId} selected={sourceEdit.sources} onChange={sources => setSourceEdit({ ...sourceEdit, sources })} />{workspace.error ? <p className={styles.error} role="alert">{workspace.error}</p> : null}{sourceEdit.revision !== record.revision ? <section className={styles.conflict}><p>笔记已经更新，当前选择仍保留。请核对最新关联后再保存。</p><p>最新来源：{record.data.sources.map(reference => reference.title || "来源待核对").join("、") || "未关联来源"}</p><button type="button" onClick={() => setSourceEdit({ ...sourceEdit, revision: record.revision })}>核对后以最新版本保存此选择</button></section> : null}<footer className={styles.dialogActions}><button type="button" disabled={workspace.pending} onClick={() => setSourceEdit(null)}>取消</button><button className={styles.primary} type="submit" disabled={workspace.pending || sourceEdit.revision !== record.revision || sourceEdit.sources.some(reference => reference.source_status !== "available")}>保存来源关联</button></footer></form> : null}</Dialog>
  </>;
}

function MemoryProposal({ ownerId, onClose, onInvalid, onSaved }: { ownerId: string; onClose: () => void; onInvalid: () => void; onSaved: (record: ConfirmedMemory) => void }) {
  const [page, setPage] = useState(1);
  const notes = usePersistentWorkspace<Paginated<AnnotationChoice>>(`/reading/annotations/?p=${page}`, ownerId);
  const [note, setNote] = useState<AnnotationChoice | null>(null);
  const [body, setBody] = useState("");
  const [kind, setKind] = useState<MemoryKind>("understanding");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const request = useRef({ fingerprint: "", id: "" });
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const dirty = useUnsavedForm(Boolean(note || body), false);
  async function close() { if (!busy && (!dirty || (await confirmAction("尚未保存待确认笔记，确定放弃当前输入吗？")))) onClose(); }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!note || !body.trim() || pending.current) return;
    pending.current = true; setBusy(true); setError("");
    const data = { annotation_id: note.id, body, kind };
    const fingerprint = JSON.stringify(data);
    if (request.current.fingerprint !== fingerprint) request.current = { fingerprint, id: createRequestKey() };
    try { const result = await withPrivateOwner(ownerId, () => proposeMemory({ ...data, request_id: request.current.id })); if (alive.current) onSaved(result); }
    catch (reason) { if (alive.current) { setError(reason instanceof Error ? reason.message : "保存失败，输入仍保留。"); if (reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403].includes(reason.status)) onInvalid(); if (reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500) request.current = { fingerprint: "", id: "" }; } }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  return <Dialog open onRequestClose={close} className={styles.dialog} aria-labelledby="memory-proposal-title"><header><div><h2 id="memory-proposal-title">从笔记选择</h2><p>选择自己的阅读笔记，形成待确认的认识。</p></div><button aria-label="关闭选择" onClick={close} disabled={busy}><X size={18} /></button></header><form onSubmit={submit}><div className={styles.proposalGrid}><section><h3>选择原始笔记</h3>{notes.error ? <p className={styles.error} role="alert">{notes.error}<button type="button" onClick={notes.reload}>重试</button></p> : null}{notes.loading ? <LoadingState>正在读取笔记…</LoadingState> : null}{notes.data?.results.map(row => <label className={styles.noteChoice} key={row.id}><input type="radio" name="original-note" checked={note?.id === row.id} onChange={async () => { if (!note || body === (note.body_text || "") || (await confirmAction("切换原笔记会替换当前未保存的输入，继续吗？"))) { setNote(row); setBody(row.body_text || ""); } }} /><span><strong>{row.work?.title || "未命名文献"}</strong><p>{row.body_text || "未填写正文"}</p><small>{dateLabel(row.updated_at)}{row.orphaned ? " · 原文待核对" : ""}</small></span></label>)}{notes.data && !notes.data.results.length ? <p>当前还没有阅读笔记。<Link href="/explore/original">前往阅读并保存笔记</Link></p> : null}<div className={styles.pagination}><button type="button" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!notes.data?.next} onClick={() => setPage(value => value + 1)}>下一页</button></div></section><section><h3>整理我的认识</h3><label>待确认的笔记<textarea rows={9} required maxLength={20000} value={body} onChange={event => setBody(event.target.value)} placeholder="写下你自己的认识、问题或修正" /></label><label>类型<select value={kind} onChange={event => setKind(event.target.value as MemoryKind)}>{Object.entries(kindNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><p className={styles.quiet}>引文与自己的判断分别保存。下一步由你主动确认，默认不用于任何研究或计划。</p></section></div>{error ? <p className={styles.error} role="alert">{error}</p> : null}<footer className={styles.dialogActions}><button type="button" onClick={close} disabled={busy}>取消</button><button type="submit" className={styles.primary} disabled={busy || !note || !body.trim()}>{busy ? "正在保存…" : "保存并继续核对"}</button></footer></form></Dialog>;
}

function MemoryUsageDialog({ id, ownerId, onClose, onSaved }: { id: string; ownerId: string; onClose: () => void; onSaved: (message: string) => void }) {
  const memory = usePersistentWorkspace<ConfirmedMemory>(researchRecordPath("research-memories", id), ownerId);
  const usage = usePersistentWorkspace<MemoryUsage>(`${researchRecordPath("research-memories", id)}usage/`, ownerId);
  const [choice, setChoice] = useState("");
  const [message, setMessage] = useState("");
  async function change(action: "grant" | "revoke" | "revoke_all", target?: MemoryScope) {
    setMessage("");
    try {
      const result = await memory.mutate(JSON.stringify({ action, target }), latest => changeMemoryUsage(id, { expected_revision: latest.revision, action, ...(target ? { targets: [{ kind: target.kind, id: target.id, expected_revision: target.revision }] } : {}) }));
      if (result) { usage.reload(); onSaved(action === "grant" ? "已授权给选定范围，其他研究与计划不受影响。" : "已停止在选定范围中使用；本人笔记仍保留。"); setMessage(action === "grant" ? "已保存使用范围。" : "已撤销授权。"); }
    } catch { usage.reload(); }
  }
  const target = usage.data?.targets.find(row => `${row.kind}:${row.id}` === choice);
  return <Dialog open onRequestClose={() => { if (!memory.pending) onClose(); }} className={styles.smallDialog} aria-labelledby="memory-usage-title"><header><h2 id="memory-usage-title">选择笔记使用范围</h2><button aria-label="关闭使用范围" disabled={memory.pending} onClick={onClose}><X size={17} /></button></header><p>仅用于你选择的研究或阅读计划。相关片段可能发送给书库配置的 API 服务分析。</p>{memory.error || usage.error ? <p className={styles.error} role="alert">{memory.error || usage.error}<button onClick={() => { memory.reload(); usage.reload(); }}>重新读取</button></p> : null}{message ? <p role="status">{message}</p> : null}
    {memory.data && usage.data ? <><h3>{titleOf(memory.data)}</h3>{memory.data.state !== "confirmed" ? <p className={styles.notice}>先由本人确认这条笔记，再选择使用范围。现有授权仍可撤销。</p> : null}<label>研究或计划<select value={choice} onChange={event => setChoice(event.target.value)}><option value="">选择一个明确范围</option>{usage.data.targets.map(row => <option key={`${row.kind}:${row.id}`} value={`${row.kind}:${row.id}`}>{row.kind === "project" ? "研究" : "计划"} · {row.title || "未命名"}{row.selected ? "（已选）" : ""}</option>)}</select></label>{target ? <p>{target.selected ? target.enabled ? "这条笔记已用于此范围。" : "笔记已选定，此范围当前暂停使用个人笔记。" : "此范围尚未选用这条笔记。"}</p> : null}<div className={styles.dialogActions}><button disabled={memory.pending || !target?.selected} onClick={() => target && void change("revoke", target)}>停止在此范围使用</button><button className={styles.primary} disabled={memory.pending || !target || memory.data.state !== "confirmed" || Boolean(target.selected && target.enabled)} onClick={() => target && void change("grant", target)}>授权给此范围</button></div><section className={styles.usageList}><h3>当前已选范围</h3>{usage.data.targets.filter(row => row.selected).map(row => <p key={`${row.kind}:${row.id}`}><span>{row.title || "未命名"}{!row.enabled ? "（已暂停）" : ""}</span><button disabled={memory.pending} onClick={() => void change("revoke", row)}>撤销</button></p>)}{!usage.data.targets.some(row => row.selected) ? <p>尚未用于任何研究或计划。</p> : <button disabled={memory.pending} onClick={() => void change("revoke_all")}>停止在全部范围使用</button>}</section><p className={styles.quiet}>{usage.data.notice}</p></> : <LoadingState role="status">正在核对使用范围…</LoadingState>}
  </Dialog>;
}
