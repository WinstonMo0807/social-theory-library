"use client";
import { MediaPlacement } from "@/components/media-placement";

import Link from "next/link";
import Image from "next/image";
import { BookOpen, History, LockKeyhole, RefreshCw } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { Paginated } from "@/lib/api/pagination";
import { cancelResearchTurn, changeResearchSelection, readResearchRecord, retryResearchTurn, startResearchTurn, type ProjectData, type QueryScope, type ResearchRecord, type Statement } from "@/lib/api/research.client";
import { counterAttributions, counterAvailable, counterRelation, counterRelations, saveCounterDecision, type CounterAnalysis, type CounterRelation, type CounterTurnData } from "@/lib/api/counter-evidence.client";
import { usePersistentWorkspace, useResearchRecord } from "@/lib/api/use-persistent-workspace";
import { isTaskRunning } from "@/lib/api/task-polling";
import { researchEvidenceKey, researchEvidenceReference, researchReaderHref, researchScopeLabel } from "@/lib/api/research-evidence";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { CounterEvidenceEditor, CounterLocation } from "./counter-evidence-editor";
import { CounterSaveDialog, CounterSubclaims } from "./counter-evidence-actions";

const statuses: Record<string, string> = { queued: "排队中", running: "正在检索与核对", completed: "本轮已完成", partial: "部分完成", failed: "本轮未完成", canceled: "本轮已取消", cancelled: "本轮已取消" };
const filters = { all: "全部", support: "支持", different_conclusion: "不同结论", qualification: "限定条件", insufficient_evidence: "待复核", unrelated: "不相关" };
type Filter = keyof typeof filters;
const groupOf = (row: CounterAnalysis): Filter => { const value = counterRelation(row); return value === "reframe" ? "insufficient_evidence" : value; };

export function CounterEvidenceWorkspace({ id, initialTurnId }: { id: string; initialTurnId?: string }) {
  const { state, retry } = useSessionBootstrap();
  useEffect(() => { if (state.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(`/account/research/${id}/counter-evidence`)}`); }, [state.status, id]);
  if (["temporary_error", "forbidden"].includes(state.status)) return <Frame><Empty title="暂时无法读取这份研究" message={state.message || "请重新验证登录。"} retry={retry} /></Frame>;
  if (state.status !== "authenticated" || !state.user) return <Frame><p role="status">正在核对登录状态…</p></Frame>;
  return <ProjectWorkspace key={`${state.user.id}:${id}`} id={id} ownerId={String(state.user.id)} initialTurnId={initialTurnId} />;
}

function ProjectWorkspace({ id, ownerId, initialTurnId }: { id: string; ownerId: string; initialTurnId?: string }) {
  const project = useResearchRecord<ProjectData>("research-projects", id, ownerId);
  const [historyPage, setHistoryPage] = useState(1), [activeId, setActiveId] = useState(initialTurnId || "");
  const history = usePersistentWorkspace<Paginated<ResearchRecord<CounterTurnData>>>(`/reading/research-projects/${encodeURIComponent(id)}/turns/?mode=counterargument&order=newest&page=${historyPage}`, ownerId,
    data => data.results.some(item => isTaskRunning(item.status)) ? 3000 : null);
  const counterTurns = (history.data?.results || []).filter(item => item.data.mode === "counterargument");
  const turnId = activeId || counterTurns[0]?.id || "";
  const turn = useResearchRecord<CounterTurnData>("research-turns", turnId || null, ownerId);
  const [historyOpen, setHistoryOpen] = useState(false), [selected, setSelected] = useState("");
  const [filter, setFilter] = useState<Filter>("all"), [sort, setSort] = useState("relevance"), [limit, setLimit] = useState(12);
  const [notice, setNotice] = useState(""), [actionError, setActionError] = useState("");
  const [saving, setSaving] = useState<{ kind: "note" | "plan"; row?: CounterAnalysis } | null>(null);
  const [subclaims, setSubclaims] = useState(false);
  const [statementDirty, setStatementDirty] = useState(false), [decisionDirty, setDecisionDirty] = useState(false);
  const [saveDirty, setSaveDirty] = useState(false), [subclaimsDirty, setSubclaimsDirty] = useState(false);
  useUnsavedForm(statementDirty || decisionDirty || saveDirty || subclaimsDirty, false);
  const record = project.data, current = turn.data;
  const validTurn = current?.project_id === id && current.data.mode === "counterargument";
  const busy = project.pending || turn.pending;
  if (!record) return <Frame><Empty title={project.error ? "研究暂时不可用" : "正在读取私人研究…"} message={project.error || "命题与历史记录仅本人可见。"} retry={project.reload} /></Frame>;
  if (history.loading && !history.data || turnId && turn.loading) return <Frame><Empty title="正在读取反证轮次…" message="已保存命题和历史条件正在加载。" /></Frame>;
  if (current && !validTurn) return <Frame><Empty title="此轮次不属于当前反证研究" message="请选择本研究中的反证轮次，原有研究内容继续保留。" retry={() => { setActiveId(""); history.reload(); }} /><Link href={`/account/research/${id}`}>返回研究</Link></Frame>;
  const rows = validTurn ? analysisRows(current.data) : [];
  const selectedRow = rows.find(row => row.id === selected);
  const selectedKeys = new Set(record.data.selections.map(researchEvidenceKey));
  const availableSelected = record.data.selections.filter(counterAvailable);
  const shown = rows.filter(row => filter === "all" || groupOf(row) === filter);
  const ordered = sort === "title" ? shown.toSorted((a, b) => (a.reference.title || "").localeCompare(b.reference.title || "", "zh-CN")) : shown;
  const running = isTaskRunning(current?.status);
  const refresh = () => { project.reload(); history.reload(); turn.reload(); };
  async function start(statement: Statement, scope: QueryScope, child?: string) {
    if (busy || record!.archived) return false;
    if (decisionDirty && !window.confirm("证据分类更正尚未保存。确定放弃更正并开始新轮次吗？")) return false;
    setActionError(""); setNotice(""); let nextId = "";
    const body = { question: statement.proposition, statement, scope, mode: "counterargument" as const,
      ...(current ? { parent_id: current.id } : {}), subclaims: current?.data.subclaims || [], active_subclaim_id: child || null };
    try {
      const result = await project.mutate(JSON.stringify(body), async (latest, request_id) => {
        const next = await startResearchTurn(id, { ...body, expected_revision: latest.revision, request_id }); nextId = next.id;
        return readResearchRecord<ProjectData>("research-projects", id);
      });
      if (!result) return false;
      setActiveId(nextId); setSelected(""); setFilter("all"); setHistoryPage(1); history.reload(); setNotice("已保存为新轮次，原命题、原条件与前次结果保留。"); return true;
    } catch (reason) { setActionError(reason instanceof Error ? reason.message : "新轮次未能保存，输入保留。"); return false; }
  }
  async function selection(row: CounterAnalysis) {
    if (busy) return;
    const ref = row.reference, removing = selectedKeys.has(researchEvidenceKey(ref));
    setActionError("");
    try {
      const result = await project.mutate(`selection:${row.id}:${removing}`, latest => changeResearchSelection(id, { expected_revision: latest.revision, action: removing ? "remove" : "add",
        ...(removing ? { reference_id: researchEvidenceKey(ref) } : { references: [researchEvidenceReference(ref)] }) }));
      if (!result) return;
      setNotice(removing ? "已从当前研究选材移除，分类记录保留。" : "已加入当前研究；选材不表示已确认支持或反证。");
    } catch (reason) { setActionError(reason instanceof Error ? reason.message : "选材未能保存，请重试。"); }
  }
  async function task(action: "cancel" | "retry") {
    if (!current || busy) return;
    if (action === "retry" && (statementDirty || decisionDirty) && !window.confirm("当前条件或分类更正尚未保存。确定放弃输入并重试已保存的轮次吗？")) return;
    setActionError("");
    try {
      if (action === "cancel") await turn.mutate("cancel", async () => await cancelResearchTurn(current.id) as ResearchRecord<CounterTurnData>);
      else {
        let nextId = "";
        const result = await project.mutate(`retry:${current.id}`, async (latest, request_id) => { const next = await retryResearchTurn(current.id, { expected_revision: latest.revision, request_id }); nextId = next.id; return readResearchRecord<ProjectData>("research-projects", id); });
        if (result) { setActiveId(nextId); setSelected(""); history.reload(); }
      }
    } catch (reason) { setActionError(reason instanceof Error ? reason.message : "任务操作未完成。"); }
  }
  return <Frame><nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/account">读者中心</Link><span>/</span><Link href="/account/research">我的研究</Link><span>/</span><Link href={`/account/research/${id}`}>{record.data.title || "研究会话"}</Link><span>/</span><strong>学术反证</strong></nav>
    <header className="stl4-counter-heading"><div><h1>{selectedRow ? "纠正证据分类" : "学术反证：检验一个判断"}</h1><p>寻找支持、不同结论或增加条件的原文，帮助你修正判断。</p></div><aside>系统根据命题与条件检索相关内容，给出可复核的关系候选。请结合原文、上下文和观点归属自行判断。</aside></header>
    <section className="stl4-counter-conditions"><header><h2>原命题与检索条件</h2><small><LockKeyhole size={12} />历史与笔记仅本人可见</small><button type="button" onClick={() => setHistoryOpen(value => !value)}><History size={14} />查看历史记录</button></header>
      <CounterStatementForm priorStatements={counterTurns.flatMap(turn=>turn.data.analysis_statement?[turn.data.analysis_statement]:turn.data.statement?[turn.data.statement]:[])} key={current?.id || "new"} statement={current?.data.analysis_statement || current?.data.statement || { proposition: record.data.question.slice(0, 1200) }} onDirty={setStatementDirty} scope={current?.data.scope || record.data.scope} selectedCount={availableSelected.length} busy={busy || Boolean(record.archived)} onSubmit={(statement, choice) => start(statement, choice === "selected" ? { kind: "passages", references: availableSelected.map(researchEvidenceReference), allow_neighbors: false } : choice === "library" ? { kind: "library", filters: {} } : current?.data.scope || record.data.scope)} />
      <div className="stl4-counter-condition-footer"><span>范围：{researchScopeLabel(current?.data.scope || record.data.scope)}</span><button type="button" disabled={busy || !current || running} onClick={() => setSubclaims(true)}>拆分与检验子命题{current?.data.subclaims?.length ? `（${current.data.subclaims.length}）` : ""}</button>{record.archived ? <p role="alert">这份研究已归档；可查看历史，恢复研究后再开始新轮次。</p> : null}</div>
    </section>
    {historyOpen ? <section className="stl4-counter-history" aria-label="反证历史记录"><h2>历史轮次与条件</h2>{history.error ? <p role="alert">{history.error}</p> : history.loading ? <p role="status">正在读取历史…</p> : counterTurns.length ? counterTurns.map(item => <button type="button" key={item.id} aria-pressed={item.id === turnId} disabled={busy} onClick={() => { if ((statementDirty || decisionDirty) && !window.confirm("当前输入尚未保存，确定放弃并查看另一轮次吗？")) return; setActiveId(item.id); setSelected(""); setFilter("all"); setHistoryOpen(false); }}><strong>{item.data.analysis_statement?.proposition || item.data.question}</strong><span>{statuses[item.status || ""] || "已保存"} · {new Date(item.created_at).toLocaleString("zh-CN")}</span></button>) : <p>本页没有反证轮次。普通研究轮次仍在研究工作区中保留。</p>}<nav aria-label="研究历史分页"><button type="button" disabled={historyPage <= 1 || busy} onClick={() => { setActiveId(turnId); setHistoryPage(page => page - 1); }}>前一页历史</button><span>第 {historyPage} 页</span><button type="button" disabled={!history.data?.next || busy} onClick={() => { setActiveId(turnId); setHistoryPage(page => page + 1); }}>后一页历史</button></nav></section> : null}
    <div className="stl4-counter-status" role="status"><span>{current ? statuses[current.status || ""] || "已保存" : "尚未开始检索"}{current ? ` · 修订 ${current.revision}` : ""}</span><div>{running ? <button type="button" disabled={busy} onClick={() => void task("cancel")}>取消本轮</button> : current && ["failed", "partial", "canceled", "cancelled"].includes(current.status || "") ? <button type="button" disabled={busy} onClick={() => void task("retry")}>重试本轮</button> : null}<button type="button" disabled={busy} onClick={refresh}><RefreshCw size={13} />{turn.pollPaused ? "继续读取进度" : "重新读取"}</button></div></div>
    {notice ? <p className="stl4-counter-message" role="status">{notice}</p> : null}{actionError || turn.error || project.error ? <p className="stl4-counter-message" role="alert">{actionError || turn.error || project.error} 当前输入保留。</p> : null}
    <div className="stl4-counter-grid" data-editing={Boolean(selectedRow)}><section className="stl4-counter-results" aria-label="相关证据"><header><div><h2>相关证据</h2><span>{rows.length ? `本轮 ${rows.length} 项原文候选` : "尚无原文候选"}</span></div><label>结果排序<select value={sort} onChange={event => setSort(event.target.value)}><option value="relevance">检索顺序</option><option value="title">题名顺序</option></select></label></header>
      <nav className="stl4-counter-filters" aria-label="证据分类">{Object.entries(filters).map(([key, label]) => <button type="button" key={key} aria-pressed={filter === key} onClick={() => { setFilter(key as Filter); setLimit(12); }}>{label}<span>{key === "all" ? rows.length : rows.filter(row => groupOf(row) === key).length}</span></button>)}</nav>
      {ordered.length ? <div className="stl4-counter-list">{ordered.slice(0, limit).map((row, index) => <EvidenceRow key={row.id} row={row} index={index} compact={Boolean(selectedRow)} selected={selected === row.id} inProject={selectedKeys.has(researchEvidenceKey(row.reference))} disabled={busy || Boolean(record.archived)} onChoose={() => { if (row.id !== selected && decisionDirty && !window.confirm("分类更正尚未保存，确定放弃并查看另一条证据吗？")) return; setSelected(row.id); setActionError(""); }} onSelection={() => void selection(row)} onNote={() => setSaving({ kind: "note", row })} />)}</div> : <Empty title={running ? "正在查找相关原文" : filter === "different_conclusion" && rows.some(row => groupOf(row) === "support") ? "当前条件下尚未找到不同结论" : rows.length ? "当前分类没有结果" : "尚未取得相关证据"} message={running ? "已经保存的材料保留；可稍后回来查看。" : "未检索到反例不能证明原命题成立。可以修改对象与条件，或扩大检索范围后继续核对。"} />}
      {ordered.length > limit ? <button type="button" className="stl4-counter-more" onClick={() => setLimit(value => value + 12)}>继续显示证据</button> : null}
    </section>{selectedRow && current ? <CounterEvidenceEditor key={`${current.id}:${selectedRow.id}`} row={selectedRow} revision={current.revision} onDirty={setDecisionDirty} busy={busy} running={running} error={actionError} onClose={() => setSelected("")} onSave={async body => {
      setActionError(""); try { const result = await turn.mutate(JSON.stringify(body), (_latest, request_id) => saveCounterDecision(current.id, { ...body, request_id })); if (!result) return false; setNotice(body.action === "clear" ? "已撤回本人判断，前次记录保留。" : body.save_as_note ? "本人分类与待确认笔记已保存；未授予其他研究使用。" : "本人分类已保存，系统候选与历史记录保留。"); history.reload(); return true; } catch (reason) { setActionError(reason instanceof Error ? reason.message : "分类未保存，输入保留。"); return false; }
    }} /> : null}</div>
    <footer className="stl4-counter-footer"><p>{current?.data.analysis_notice || "相关性与候选分类都不等于已经确认的支持或反证。"}</p><div><button type="button" disabled={busy} onClick={() => setSaving({ kind: "note" })}>保存我的判断到笔记</button><button type="button" disabled={busy || !availableSelected.length} onClick={() => setSaving({ kind: "plan" })}>将当前选材加入阅读计划（{availableSelected.length}）</button><Link href={`/account/research/${id}/compare`}>比较当前研究选材</Link></div>{current?.data.analysis_model?.message ? <p>{current.data.analysis_model.message}</p> : null}{current?.data.warnings?.map((warning, index) => <p key={index}>{warning.message || "本轮存在待核对的处理提示。"}</p>)}</footer>
    {saving ? <CounterSaveDialog key={`${saving.kind}:${saving.row?.id || "overall"}`} ownerId={ownerId} projectId={id} turnId={current?.id} kind={saving.kind} statement={current?.data.analysis_statement?.proposition || current?.data.question || record.data.question} references={saving.row ? rows.filter(row => row.id === saving.row!.id && counterAvailable(row.reference)).map(row => row.reference) : availableSelected} onDirty={setSaveDirty} onClose={() => setSaving(null)} /> : null}
    {subclaims && current ? <CounterSubclaims key={current.id} record={current} busy={busy || running} error={turn.error} onDirty={setSubclaimsDirty} onClose={() => setSubclaims(false)} onSave={async (values, revision) => { const { updateResearchSubclaims } = await import("@/lib/api/research.client"); try { return Boolean(await turn.mutate(JSON.stringify({ values, revision }), async () => await updateResearchSubclaims(current.id, { expected_revision: revision, subclaims: values }) as ResearchRecord<CounterTurnData>)); } catch { return false; } }} onStart={async claim => { if (statementDirty && !window.confirm("原命题或检索条件尚未保存。确定放弃这些输入并检验子命题吗？")) return; if (await start(claim, current.data.scope, claim.id)) setSubclaims(false); }} /> : null}
  </Frame>;
}

function CounterStatementForm({ statement, priorStatements, scope, selectedCount, busy, onSubmit, onDirty }: { statement: Statement; priorStatements: Statement[]; scope: QueryScope; selectedCount: number; busy: boolean; onDirty: (dirty: boolean) => void; onSubmit: (statement: Statement, scope: string) => Promise<boolean> }) {
  const [proposition, setProposition] = useState(statement.proposition), [subject, setSubject] = useState(statement.subject || "");
  const [region, setRegion] = useState(scopeText(statement.geographic_scope));
  const [period, setPeriod] = useState(scopeText(statement.temporal_scope));
  const [conditions, setConditions] = useState(statement.qualifiers?.join("；") || ""), [scopeChoice, setScopeChoice] = useState("saved");
  const [initial] = useState({ proposition, subject, region, period, conditions, scopeChoice });
  const dirty = JSON.stringify({ proposition, subject, region, period, conditions, scopeChoice }) !== JSON.stringify(initial);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  async function submit(event: FormEvent) { event.preventDefault(); if (!busy && proposition.trim().length >= 2) await onSubmit({ ...statement, proposition: proposition.trim(), subject: subject.trim(), geographic_scope: region === initial.region ? statement.geographic_scope : region.trim(), temporal_scope: period === initial.period ? statement.temporal_scope : period.trim(), qualifiers: conditions === initial.conditions ? statement.qualifiers : conditions.trim() ? [conditions.trim()] : [] }, scopeChoice); }
  return <form className="stl4-counter-statement" onSubmit={event => void submit(event)}><label className="stl4-counter-proposition">需要检验的原命题<textarea value={proposition} required minLength={2} maxLength={1200} rows={2} disabled={busy} onChange={event => setProposition(event.target.value)} placeholder="输入一个可以结合原文检验的判断" /></label><div><StatementScopeChoice label="研究对象" empty="全部对象" value={subject} options={priorStatements.map(row=>row.subject||"")} disabled={busy} onChange={setSubject}/><StatementScopeChoice label="地区" empty="全球范围" value={region} options={priorStatements.map(row=>scopeText(row.geographic_scope))} disabled={busy} onChange={setRegion}/><StatementScopeChoice label="时间" empty="不限时间" value={period} options={priorStatements.map(row=>scopeText(row.temporal_scope))} disabled={busy} onChange={setPeriod}/><label>条件（可选）<input maxLength={1000} value={conditions} disabled={busy} onChange={event => setConditions(event.target.value)} /></label><button type="submit" className="is-primary" disabled={busy || proposition.trim().length < 2 || scopeChoice === "selected" && !selectedCount}>重新检索</button></div><details><summary>检索范围</summary><label>使用材料<select value={scopeChoice} disabled={busy} onChange={event => setScopeChoice(event.target.value)}><option value="saved">沿用研究范围（{researchScopeLabel(scope)}）</option><option value="selected" disabled={!selectedCount}>仅当前可用选材（{selectedCount}）</option><option value="library">扩展至全部可访问馆藏</option></select></label><p>对象、地区、时间与条件用于限定所讨论的命题，不代表馆藏出版年份。</p></details></form>;
}

function StatementScopeChoice({label,empty,value,options,disabled,onChange}:{label:string;empty:string;value:string;options:string[];disabled:boolean;onChange:(value:string)=>void}) {
  const [custom,setCustom]=useState(false);
  const choices=Array.from(new Set([value,...options].filter(Boolean)));
  return <label>{label}<select value={custom?"__custom":value} disabled={disabled} onChange={event=>{if(event.target.value==="__custom")setCustom(true);else{setCustom(false);onChange(event.target.value);}}}><option value="">{empty}</option>{choices.map(choice=><option key={choice} value={choice}>{choice}</option>)}<option value="__custom">自定义{label}…</option></select>{custom?<input aria-label={`自定义${label}`} value={value} disabled={disabled} maxLength={300} autoFocus onChange={event=>onChange(event.target.value)}/>:null}</label>;
}

function EvidenceRow({ row, index, compact, selected, inProject, disabled, onChoose, onSelection, onNote }: { row: CounterAnalysis; index: number; compact: boolean; selected: boolean; inProject: boolean; disabled: boolean; onChoose: () => void; onSelection: () => void; onNote: () => void }) {
  const ref = row.reference, available = counterAvailable(ref), relation = counterRelation(row), href = researchReaderHref(ref);
  const cover = available && ref.cover_url ? normalizePublicResourceUrl(ref.cover_url) : "";
  const ownerAttribution = available && row.status === "user_confirmed" ? row.decision?.attribution : undefined;
  const attribution = ownerAttribution || row.candidate_statement?.attribution;
  return <article className="stl4-counter-evidence" data-selected={selected || undefined} data-compact={compact}><div className="stl4-counter-number">{String(index + 1).padStart(2, "0")}<span className="stl4-counter-tag" data-relation={relation}>{counterRelations[relation]}</span></div><div className="stl4-counter-cover">{cover ? <MediaPlacement uses={ref.cover_media?.display_uses} fallback={<BookOpen aria-hidden="true" size={24} />}><Image src={cover} alt="" width={64} height={88} unoptimized /></MediaPlacement> : <BookOpen aria-hidden="true" size={24} />}</div><div className="stl4-counter-evidence-copy"><button type="button" onClick={onChoose}><h3>{available ? ref.title || "原文材料" : "来源当前不可用"}</h3></button>{available ? <><p className="stl4-counter-bibliography">{ref.citation || [ref.authors?.join("、"), ref.publication_year].filter(Boolean).join(" · ") || "书目信息待核对"}</p><blockquote>{ref.quote || ref.text || "当前未返回原文片段，请打开原文核对。"}</blockquote></> : <p>原文已变化、撤回或不可访问。旧片段不再显示，材料身份和前次人工判断保留。</p>}<CounterLocation row={row} /></div><div className="stl4-counter-reason"><strong>{available && row.decision && row.status === "user_confirmed" ? "本人分类" : "候选分类"}：{counterRelations[relation]}{row.status !== "user_confirmed" || !available ? "（待复核）" : ""}</strong><p>{available ? row.decision?.note || row.model_suggestion?.reason || row.reason || "尚无可确认的关系，需要本人核对。" : "来源依据已变化，前次判断需要重新核对。"}</p>{available && attribution ? <small>{ownerAttribution ? "本人归属判断" : "系统归属线索"}：{counterAttributions[attribution]}{attribution !== "author_claim" ? "。不能直接当作作者本人的结论。" : ""}</small> : null}{href ? <Link href={href} target="_blank" rel="noreferrer">查看上下文</Link> : null}</div><div className="stl4-counter-evidence-actions"><button type="button" className="is-primary" disabled={disabled || !available && !inProject} onClick={onSelection}>{inProject ? "已加入研究 · 移除" : "加入当前研究"}</button><button type="button" disabled={disabled || !available} onClick={onNote}>保存到我的笔记</button><button type="button" onClick={onChoose}>{available ? "纠正分类" : "查看前次判断"}</button></div></article>;
}

function scopeText(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(scopeText).filter(Boolean).join("、");
  if (!value || typeof value !== "object") return "";
  const scope = value as Record<string, unknown>;
  if (typeof scope.label === "string") return scope.label;
  if (scope.start !== undefined || scope.end !== undefined) return [scope.start, scope.end].map(scopeText).filter(Boolean).join("–");
  return JSON.stringify(value);
}
function analysisRows(data: CounterTurnData): CounterAnalysis[] {
  const rows = data.analysis || [], known = new Set(rows.map(row => researchEvidenceKey(row.reference)));
  return [...rows, ...(Array.isArray(data.result_refs) ? data.result_refs : []).filter(ref => !known.has(researchEvidenceKey(ref))).map(ref => ({ id: researchEvidenceKey(ref), reference: ref, relation: "insufficient_evidence" as CounterRelation, status: "awaiting_analysis", reason: "已取得原文，关系分析尚未完成。" }))];
}
function Frame({ children }: { children: ReactNode }) { return <div className="stl4-research-page stl4-counter-page"><div className="stl4-research-detail-shell">{children}</div></div>; }
function Empty({ title, message, retry }: { title: string; message: string; retry?: () => void }) { return <div className="stl4-research-empty"><BookOpen size={26} /><h2>{title}</h2><p>{message}</p>{retry ? <button type="button" onClick={retry}>重新读取</button> : null}</div>; }
