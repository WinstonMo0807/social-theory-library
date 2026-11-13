"use client";
import { SourceText } from "@/components/source-text";


import { DefaultCover } from "@/components/default-cover";
import { confirmAction } from "@/lib/ui-dialog";


import { LoadingState } from "@/components/ui/loading-state";
import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import Image from "next/image";
import { BookOpen, GitBranch, LockKeyhole, Plus, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { researchEvidenceKey, researchScopeLabel } from "@/lib/api/research-evidence";
import type { ResolvedEvidence } from "@/lib/api/research.client";
import { replayPath, replayRequest, type ReplayDetail, type ReplayFork, type ReplayReceipt, type ReplayTimeline } from "@/lib/api/research-replay.client";
import { Dialog } from "@/components/ui/dialog";
import { MediaPlacement } from "@/components/media-placement";
import { CitationSourcePreview } from "./citation-source-preview";
import { ProjectBranches, TurnBranches } from "./replay-paths";
import { ReplayTextHistory } from "./replay-text-history";
import { ReaderMobileNav } from "./reader-mobile-nav";
import styles from "./research-replay.module.css";

const date = (value: string) => new Date(value).toLocaleDateString("zh-CN");
type Tab = "materials" | "notes" | "compare" | "snapshots" | "evidence";

export function ResearchReplay({ id, initialTurn = "" }: { id: string; initialTurn?: string }) {
  const { state, retry } = useSessionBootstrap();
  useEffect(() => { if (state.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(`/account/research/${id}/history${initialTurn ? `?turn=${initialTurn}` : ""}`)}`); }, [id, initialTurn, state.status]);
  if (state.status === "temporary_error" || state.status === "forbidden") return <main className={styles.page}><h1>研究回放暂时无法读取</h1><p>{state.message}</p><button onClick={retry}>重新核对登录</button></main>;
  if (state.status !== "authenticated" || !state.user) return <main className={styles.page}><LoadingState variant="screen" role="status">正在核对登录状态…</LoadingState></main>;
  return <Replay key={`${state.user.id}:${id}:${initialTurn}`} id={id} owner={String(state.user.id)} initialTurn={initialTurn} />;
}

function Replay({ id, owner, initialTurn }: { id: string; owner: string; initialTurn: string }) {
  const [page, setPage] = useState(1), [turnId, setTurnId] = useState(initialTurn), [compareId, setCompareId] = useState("");
  const [pathView, setPathView] = useState<"time" | "tree">("time"), [treeEpoch, setTreeEpoch] = useState(0), [branchRoot, setBranchRoot] = useState(""), [showProjects, setShowProjects] = useState(false);
  const [tab, setTab] = useState<Tab>("materials"), [selected, setSelected] = useState<string[]>([]), [sort, setSort] = useState("saved");
  const [editor, setEditor] = useState<ReplayDetail | null>(null), [fork, setFork] = useState<ReplayDetail | null>(null), [source, setSource] = useState<ResolvedEvidence | null>(null);
  const loadTimeline = useCallback((path: string, signal: AbortSignal) => replayRequest<ReplayTimeline>(owner, path, { signal }), [owner]);
  const history = usePersistentWorkspace<ReplayTimeline>(`${replayPath(id)}?page=${page}`, owner, undefined, loadTimeline);
  const timeline = history.error ? null : history.data;
  const active = turnId || timeline?.current_turn_id || timeline?.results[0]?.id || "";
  const loadDetail = useCallback((path: string, signal: AbortSignal) => replayRequest<ReplayDetail>(owner, path, { signal }), [owner]);
  const detail = usePersistentWorkspace<ReplayDetail>(active ? `${replayPath(id)}?${new URLSearchParams({ turn_id: active, ...(compareId ? { compare_id: compareId } : {}) })}` : "", owner, undefined, loadDetail);
  const data = detail.error ? null : detail.data;
  const visibleMaterials = data ? tab === "evidence" ? data.evidence : data.materials : [];
  const material = data ? [...visibleMaterials].sort(sort === "title" ? (a, b) => (a.title || "").localeCompare(b.title || "", "zh-CN") : () => 0) : [];
  function refresh() { history.reload(); detail.reload(); setTreeEpoch(value => value + 1); }
  function choose(value: string) { setTurnId(value); setSelected([]); setCompareId(""); }
  return <main className={styles.page}>
    <nav className={styles.crumb} aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><Link href="/account/research">我的研究</Link><span>›</span><span>研究过程回放</span></nav>
    <header className={styles.heading}><div><h1>研究过程回放</h1></div><div><button className={styles.primary} disabled={!data || !(data.materials.length + data.evidence.length)} onClick={() => setFork(data)}><GitBranch size={16} />从此分支另开研究</button><Link href={`/account/sharing/new?kind=research&source=${id}`}>分享所选内容</Link><small><LockKeyhole size={12} />仅本人可见 · 明确选择材料</small></div></header>
    {history.error ? <Failure message={history.error} onRetry={history.reload} /> : !timeline ? <LoadingState role="status">正在读取研究路径…</LoadingState> : <>
      <div className={styles.topnav}><button aria-pressed={tab === "materials"} onClick={() => setTab("materials")}>研究路径</button><button aria-pressed={tab === "notes"} onClick={() => setTab("notes")}>材料与笔记</button><button aria-pressed={tab === "compare"} onClick={() => setTab("compare")}>对比视图</button><button aria-pressed={tab === "snapshots"} onClick={() => setTab("snapshots")}>历史记录</button></div>
      <div className={styles.layout}>
        <aside className={styles.timeline}><h2>研究轮次 <small>{timeline.count} 轮</small></h2><div className={styles.pathTools}><button aria-pressed={pathView === "time"} onClick={() => setPathView("time")}>按时间</button><button aria-pressed={pathView === "tree"} onClick={() => setPathView("tree")}>按分支</button></div>
          {pathView === "time" ? <><ol>{timeline.results.map(turn => <li key={turn.id} data-current={turn.id === active}><button onClick={() => choose(turn.id)} aria-pressed={turn.id === active}><span>{turn.id === timeline.current_turn_id ? "当前" : turn.parent_id ? "分支 / 继续" : "初始"}</span><strong>{turn.title}</strong><small>{date(turn.created_at)} · {turn.material_count} 条起始选材</small></button></li>)}</ol>{!timeline.results.length ? <p>尚未创建研究轮次。</p> : null}<div className={styles.pager}><button disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>{page} / {timeline.total_pages}</span><button disabled={page >= timeline.total_pages} onClick={() => setPage(value => value + 1)}>下一页</button></div></> : <><div className={styles.pathTools}><button onClick={() => setTreeEpoch(value => value + 1)}>全部折叠</button><button disabled={!active} onClick={() => { setBranchRoot(active); setTreeEpoch(value => value + 1); }}>从所选轮次展开</button>{branchRoot ? <button onClick={() => { setBranchRoot(""); setTreeEpoch(value => value + 1); }}>全部起始轮次</button> : null}</div>{branchRoot ? <p className={styles.branchHint}>当前展示所选轮次之后的路径。</p> : null}<TurnBranches key={`${id}:${treeEpoch}:${branchRoot}`} id={id} owner={owner} active={active} parent={branchRoot} onSelect={choose} /></>}
          <details data-disclosure="collection" className={styles.projectTree} onToggle={event => setShowProjects(event.currentTarget.open)}><summary>研究来源与分支</summary>{showProjects ? <ProjectBranches key={treeEpoch} id={id} owner={owner} /> : null}</details><Link className={styles.newTurn} href={`/account/research/${id}`}><Plus size={16} />新增研究轮次</Link></aside>
        <section className={styles.main}>
          {detail.error ? <Failure message={detail.error} onRetry={detail.reload} /> : !data ? <div className={styles.empty}><BookOpen size={28} /><p>{active ? "正在核对这一轮的保存记录…" : "提交研究问题后，可在这里查看研究过程和材料。"}</p></div> : <>
            <header className={styles.turnHeader}><div><span>{data.turn.id===timeline.current_turn_id?"当前轮次":"所选轮次"}</span><h2>{data.turn.title}<button onClick={() => setEditor(data)}>编辑</button></h2><small>{date(data.turn.created_at)} · 保存材料 {data.materials.length} 条{data.compared ? ` · 对比 ${data.compared.title}` : ""}</small></div><Link href={`/account/research/${id}`}>查看完整研究 →</Link></header>
            <div className={styles.questionScope}><div><strong>研究问题</strong><p>{data.turn.question}</p></div><div><strong>范围与选材</strong><p>{researchScopeLabel(data.scope)}</p></div></div>
            <p className={styles.notice}>{data.notice}</p>
            <div className={styles.tabs}>{([["materials", "核心材料", data.materials.length], ["notes", "本人笔记", data.notes ? 1 : 0], ["compare", "比较与变化", data.added_ids.length + data.removed.length], ["evidence", "新增证据", data.evidence.length]] as const).map(([key, label, count]) => <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}<span>{count}</span></button>)}</div>
            {tab === "materials" || tab === "evidence" ? <>{tab === "evidence" ? <p className={styles.notice}>只展示本轮已保存结果中，不在起始选材且未出现在所选对比轮次结果中的原文；不会重新检索。{["queued", "running"].includes(data.turn.status) ? "正在处理，完成后请刷新。" : ""}<button onClick={refresh}>刷新保存结果</button></p> : null}<div className={styles.materialTools}><label><input type="checkbox" checked={!!visibleMaterials.length && visibleMaterials.every(ref => selected.includes(researchEvidenceKey(ref)))} onChange={event => setSelected(values => event.target.checked ? [...new Set([...values, ...visibleMaterials.map(researchEvidenceKey)])] : values.filter(key => !visibleMaterials.some(ref => researchEvidenceKey(ref) === key)))} />选择当前列表材料</label><label>排序<select data-stl-select value={sort} onChange={event => setSort(event.target.value)}><option value="saved">按保存顺序</option><option value="title">按题名</option></select></label></div>{visibleMaterials.some(ref => ref.source_status !== "available") ? <p className={styles.warning}>有 {visibleMaterials.filter(ref => ref.source_status !== "available").length} 条材料的当前来源无法核对。已保存问题与笔记保留，分支时请明确调整选择。</p> : null}<div className={styles.materials}>{material.map((ref, index) => <article key={researchEvidenceKey(ref)}><input type="checkbox" aria-label={`选择${ref.title || `材料${index + 1}`}`} checked={selected.includes(researchEvidenceKey(ref))} onChange={event => setSelected(current => event.target.checked ? [...current, researchEvidenceKey(ref)] : current.filter(key => key !== researchEvidenceKey(ref)))} /><div className={styles.cover}>{ref.cover_url ? <MediaPlacement uses={ref.cover_media?.display_uses} fallback={<DefaultCover title={ref.title || "未题名资料"} />}><Image src={ref.cover_url} alt={`${ref.title || "材料"}封面`} width={58} height={82} unoptimized /></MediaPlacement> : <DefaultCover title={ref.title || "未题名资料"} />}</div><div><h3>{ref.title || "来源当前不可用"}</h3><p>{ref.authors?.join("、") || "作者待核对"}{ref.publication_year ? ` · ${ref.publication_year}` : ""}</p><small>PDF 第 {ref.pdf_page || "—"} 页{ref.printed_label ? ` · 书内页码 ${ref.printed_label}` : ""}</small></div><blockquote><SourceText text={(ref.source_status === "available" ? ref.quote || ref.text || "暂无可提取原文" : "此来源需要重新核对。") || ""} /></blockquote><button disabled={ref.source_status !== "available"} onClick={() => setSource(ref)}>查看原文</button></article>)}</div>{!material.length ? <p className={styles.empty}>{tab === "evidence" ? "本轮没有保存符合当前对比范围的新增证据。" : "本轮开始时没有保存选材。后来加入的材料在当前研究中查看。"}</p> : null}</> : null}
            {tab === "notes" ? <section className={styles.notes}><div><h3>本轮回放笔记</h3><button onClick={() => setEditor(data)}>编辑</button></div><p>{data.notes || "尚未写下本轮回放笔记。"}</p><small>仅本人可见，不自动授权模型。</small><h3>本轮开始时的项目笔记</h3><p>{data.snapshot_notes === null ? "此轮未保存项目笔记。" : data.snapshot_notes || "开始时尚未填写项目笔记。"}</p><Link href={`/account/notes?project=${id}`}>查看阅读记录 →</Link></section> : null}
            {tab === "compare" ? <section className={styles.compare}><h3>对比两轮范围与选材</h3><label>选择对比轮次<select data-stl-select value={compareId || ""} onChange={event => { setCompareId(event.target.value); setSelected([]); }}><option value="">原父轮次</option>{compareId && !timeline.results.some(row => row.id === compareId) ? <option value={compareId}>另一页的所选轮次</option> : null}{timeline.results.filter(row => row.id !== active).map(row => <option value={row.id} key={row.id}>{row.title}</option>)}</select></label><p>可在左侧翻页选择其他轮次。切换对比会清空材料勾选。本对比仅使用实际保存的输入，不重新计算或覆盖历史。</p><div className={styles.scopeDiff}><div><h4>本轮范围</h4><p>{researchScopeLabel(data.scope)}</p></div><div><h4>对比范围</h4><p>{data.previous_scope ? researchScopeLabel(data.previous_scope) : "没有父轮次或未选择对比轮次"}</p></div></div><p>{data.compared ? data.scope_changed ? "两轮保存的范围不同。" : "两轮保存的范围相同。" : "请选择对比轮次。"}</p><div className={styles.diffGrid}><div><h4>本轮新增材料 · {data.added_ids.length}</h4>{data.materials.filter(ref => data.added_ids.includes(researchEvidenceKey(ref))).map(ref => <SourceLine key={researchEvidenceKey(ref)} value={ref} onOpen={setSource} />)}</div><div><h4>本轮未再选择 · {data.removed.length}</h4>{data.removed.map(ref => <SourceLine key={researchEvidenceKey(ref)} value={ref} onOpen={setSource} />)}</div></div><p>两轮共同保存 {data.unchanged_ids.length} 条材料。</p></section> : null}
            {tab === "snapshots" ? <section className={styles.notes}><h3>{date(data.turn.created_at)} 的起始输入</h3><dl><dt>研究问题</dt><dd>{data.turn.question}</dd><dt>材料范围</dt><dd>{researchScopeLabel(data.scope)}</dd><dt>已保存选材</dt><dd>{data.materials.length} 条</dd><dt>当时项目题名</dt><dd>{data.snapshot_title === null ? "旧轮次未保存此项" : data.snapshot_title || "未命名"}</dd><dt>项目笔记</dt><dd>{data.snapshot_notes === null ? "旧轮次未保存此项" : data.snapshot_notes || "当时为空"}</dd></dl><p>原检索任务或临时会话过期不删除这份轮次输入。原文仍须满足当前公开与阅读条件。</p><ReplayTextHistory key={data.turn.id} owner={owner} id={id} turnId={data.turn.id} active={["queued", "running"].includes(data.turn.status)} onChanged={refresh} /></section> : null}
          </>}
        </section>
        <aside className={styles.side}><h2>本轮次的笔记</h2><p>{data?.notes || "选择轮次后，可写下自己的想法与下一步。"}</p><button disabled={!data} onClick={() => setEditor(data)}>编辑</button><h2>本轮主题标签</h2>{data?.tags.length ? <ul className={styles.replayTags}>{data.tags.map(tag => <li key={tag}>{tag}</li>)}</ul> : <p>尚未设置本人主题标签。</p>}<small>仅用于本人整理，不改变公开主题关系。</small><button disabled={!data} onClick={() => setEditor(data)}>编辑主题标签</button><h2>下一步</h2><button disabled={!data} onClick={() => setTab("compare")}>对比两轮范围／选材</button><button className={styles.primary} disabled={!data || !(data.materials.length + data.evidence.length)} onClick={() => setFork(data)}><GitBranch size={14} />从此分支另开研究</button><Link href={`/account/research/${id}`}>返回研究工作区 →</Link></aside>
      </div>
    </>}
    {editor ? <ReplayEditor owner={owner} id={id} data={editor} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); refresh(); }} /> : null}
    {fork ? <ForkForm owner={owner} id={id} data={fork} selected={selected} onClose={() => setFork(null)} /> : null}
    {source ? <Modal title="核对原文" onClose={() => setSource(null)} wide><CitationSourcePreview reference={source} /></Modal> : null}
    <ReaderMobileNav />
  </main>;
}

function SourceLine({ value, onOpen }: { value: ResolvedEvidence; onOpen: (ref: ResolvedEvidence) => void }) { return <div className={styles.sourceLine}>{value.cover_url?<MediaPlacement uses={value.cover_media?.display_uses} fallback={<BookOpen size={24}/>}><Image src={value.cover_url} alt="" width={40} height={58} unoptimized/></MediaPlacement>:<BookOpen size={24}/>}<div><strong>{value.title || "来源当前不可用"}</strong><small>{value.authors?.join("、")}{value.publication_year?` · ${value.publication_year}`:""} · PDF 第 {value.pdf_page || "—"} 页</small><button disabled={value.source_status !== "available"} onClick={() => onOpen(value)}>查看原文</button></div></div>; }
function Failure({ message, onRetry }: { message: string; onRetry: () => void }) { return <div className={styles.warning} role="alert"><p>{message}</p><button type="button" onClick={onRetry}>重新读取</button></div>; }
function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) { return <Dialog open onRequestClose={onClose} className={`${styles.modal} ${wide ? styles.wide : ""}`} aria-label={title}><header><h2>{title}</h2><button type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button></header>{children}</Dialog>; }
function useController() { const controller = useRef<AbortController | null>(null); useEffect(() => { const next = new AbortController(); controller.current = next; const off = subscribeToSessionChanges(() => next.abort()); return () => { next.abort(); off(); }; }, []); return controller; }

function ReplayEditor({ owner, id, data, onSaved, onClose }: { owner: string; id: string; data: ReplayDetail; onSaved: () => void; onClose: () => void }) {
  const [title, setTitle] = useState(data.turn.title), [notes, setNotes] = useState(data.notes), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [tagsText, setTagsText] = useState(data.tags.join("\n"));
  const dirty = useUnsavedForm([title, notes, tagsText], [data.turn.title, data.notes, data.tags.join("\n")]);
  const requests = useController(), sending = useRef(false);
  async function save(event: FormEvent) {
    event.preventDefault(); const request = requests.current; if (!request || request.signal.aborted || sending.current) return;
    sending.current = true; setBusy(true);
    try { await withPrivateOwner(owner, () => replayRequest<ReplayDetail>(owner, replayPath(id), { method: "PATCH", signal: request.signal, body: JSON.stringify({ turn_id: data.turn.id, expected_revision: data.turn.revision, title, notes, tags: tagsText.split("\n").map(value => value.trim()).filter(Boolean) }) }), request.signal); if (!request.signal.aborted) onSaved(); }
    catch (reason) { if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "保存未确认，输入仍保留。"); }
    finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  return <Modal title="编辑本轮回放记录" onClose={async () => { if (!busy && (!dirty || (await confirmAction("回放文字尚未保存，确定关闭并放弃本次输入吗？")))) onClose(); }}><form className={styles.form} onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }} onSubmit={event => void save(event)}><label>轮次显示名称<input value={title} onChange={event => setTitle(event.target.value)} maxLength={240} required /></label><label>本轮回放笔记<textarea value={notes} onChange={event => setNotes(event.target.value)} maxLength={20000} rows={7} /></label><label>本轮主题标签<textarea value={tagsText} onChange={event => setTagsText(event.target.value)} maxLength={600} rows={3} placeholder="每行一个，最多12项，每项40字" /></label><p>名称、笔记和标签只供本人整理，编辑会保留加密文字历史。原问题、检索条件与起始材料仍保留。处理中轮次需完成或取消后再编辑；删除本轮或整份研究会同时删除这些历史。</p>{message ? <p role="alert">{message}</p> : null}<button className={styles.primary} disabled={busy}>{busy ? "正在保存…" : "保存"}</button></form></Modal>;
}

function ForkForm({ owner, id, data, selected, onClose }: { owner: string; id: string; data: ReplayDetail; selected: string[]; onClose: () => void }) {
  const router = useRouter(), requests = useController(), sending = useRef(false), pending = useRef<ReplayFork | null>(null);
  const [title, setTitle] = useState(`${data.turn.title.slice(0, 40)} · 分支`), [question, setQuestion] = useState(""), [scope, setScope] = useState(selected.length ? "selected" : "all"), [includeNotes, setIncludeNotes] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(""), [recovery, setRecovery] = useState<string | null>(null), [broken, setBroken] = useState(false), [canRetry, setCanRetry] = useState(false);
  const dirty = useUnsavedForm([title, question, scope, includeNotes, Boolean(recovery)], [`${data.turn.title.slice(0, 40)} · 分支`, "", selected.length ? "selected" : "all", false, false]);
  const storageKey = `stl-replay-fork:${owner}`;
  const references = [...data.materials, ...data.evidence];
  const all = [...new Set(references.map(researchEvidenceKey))], ids = scope === "selected" ? selected : scope === "added" ? data.added_ids : all;
  const staleSelection = ids.some(key => !all.includes(key));
  const unavailable = references.some(ref => ids.includes(researchEvidenceKey(ref)) && ref.source_status !== "available");
  useEffect(() => { let active = true; queueMicrotask(() => { if (!active) return; try { const value = sessionStorage.getItem(storageKey); if (!value) return; if (!/^[\da-f-]{36}$/i.test(value)) throw Error("暂时无法读取处理记录，请到我的研究核对。"); setRecovery(value); setMessage("上次创建结果未确认，请先核对原请求。"); } catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "原请求无法读取。"); } }); return () => { active = false; }; }, [storageKey]);
  function clear() { sessionStorage.removeItem(storageKey); setRecovery(null); pending.current = null; setCanRetry(false); }
  async function execute(mode: "lookup" | "stop" | "create" = "create") {
    const lookup = mode !== "create";
    const request = requests.current; if (!request || request.signal.aborted || sending.current || broken) return;
    const command = pending.current || (!lookup && !recovery ? { turn_id: data.turn.id, expected_revision: data.turn.revision, expected_project_revision: data.project_revision, request_id: createRequestKey(), title, question, reference_ids: ids, include_notes: includeNotes } : null);
    const requestId = lookup ? recovery : command?.request_id; if (!requestId) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      sessionStorage.setItem(storageKey, requestId); setRecovery(requestId); if (command && !lookup) { pending.current = command; setCanRetry(true); }
      const result = await withPrivateOwner(owner, () => replayRequest<ReplayReceipt>(owner, lookup ? `/reading/research-projects/replay-fork-receipt/?request_id=${requestId}` : `/reading/research-projects/${id}/fork-from-replay/`, { signal: request.signal, ...(mode === "stop" ? { method: "POST", body: JSON.stringify({ action: "cancel_pending", request_id: requestId }) } : lookup ? {} : { method: "POST", body: JSON.stringify(command) }) }), request.signal);
      if (result.request_id !== requestId || !["applied", "cancelled"].includes(result.state) || result.state === "cancelled" && (result.project_id || result.deleted)) throw Error("操作结果与原创建请求不符。");
      if (!request.signal.aborted) { clear(); if (result.state === "cancelled") setMessage("原请求已经停止，迟到提交不会再建立分支；填写内容仍保留。"); else if (result.deleted || !result.project_id) setMessage("原分支已删除，旧请求不会重新创建它。"); else router.push(`/account/research/${result.project_id}`); }
    } catch (reason) { if (request.signal.aborted) return; if (!lookup && reason instanceof ApiRequestError && [400, 422].includes(reason.status)) clear(); setMessage(reason instanceof Error ? reason.message : "创建结果未确认，请核对原请求。"); }
    finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  return <Modal title="从此分支另开研究" onClose={async () => { if (!busy && (!dirty || (await confirmAction("当前有填写内容或待核对请求。关闭会放弃未提交的输入，原请求编号仍保留，确定关闭吗？")))) onClose(); }}><form className={styles.form} onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }} onSubmit={event => { event.preventDefault(); void execute(); }}><fieldset disabled={busy || !!recovery || broken}><label>新研究主题<input value={title} onChange={event => setTitle(event.target.value)} maxLength={50} required /></label><legend>基于此轮保存的材料</legend>{[["all", `全部 ${all.length} 条`], ["added", `起始选材相对对比轮次新增 ${data.added_ids.length} 条`], ["selected", `仅列表中明确选择的 ${selected.length} 条`]].map(([value, label]) => <label className={styles.option} key={value}><input type="radio" name="fork-scope" checked={scope === value} onChange={() => setScope(value)} />{label}</label>)}<label>研究问题（可选）<textarea value={question} onChange={event => setQuestion(event.target.value)} maxLength={200} rows={4} /></label><label className={styles.option}><input type="checkbox" checked={includeNotes} onChange={event => setIncludeNotes(event.target.checked)} />复制本轮回放笔记到新研究</label><p>最多明确选择400项材料。当前选择 {ids.length} 项。新研究只限定到所选原文，不自动扩大至全馆，不继承个人学术记忆的模型使用授权，也不立即启动检索。</p>{staleSelection ? <p>所选材料已不在当前回放范围，请返回列表重新选择。</p> : null}{unavailable ? <p>当前选择含无法核对的来源，请返回列表明确调整选择。</p> : null}</fieldset>{message ? <p role="status">{message}</p> : null}<footer>{recovery ? <><button type="button" disabled={busy} onClick={() => void execute("lookup")}>核对原请求</button>{canRetry ? <button disabled={busy}>重试原创建</button> : null}</> : <button className={styles.primary} disabled={busy || broken || !ids.length || ids.length > 400 || staleSelection || unavailable || !title.trim()}>创建并进入新研究</button>}{recovery && !broken ? <button type="button" disabled={busy} onClick={() => void execute("stop")}>停止尚未执行的原请求</button> : null}{broken ? <p>原请求编号暂不能安全恢复，记录已保留。请从我的研究核对已创建内容。</p> : null}</footer></form></Modal>;
}
