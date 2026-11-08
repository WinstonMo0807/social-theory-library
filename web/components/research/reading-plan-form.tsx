"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { BookOpen, NotebookPen, History, MessageCircle, Settings, Clock3 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import type { Paginated } from "@/lib/api/pagination";
import type { MemoryData, PlanData, PlanLevel, PlanPolicy, ProjectData, ResearchRecord, ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceKey } from "@/lib/api/research-evidence";
import { usePersistentWorkspace, useResearchRecord } from "@/lib/api/use-persistent-workspace";
import { ResearchEvidenceCover } from "./research-evidence-card";

export type PlanSettings = PlanPolicy & { goal: string; background: string };
export const planLevels: Record<PlanLevel, string> = { beginner: "没有基础", intermediate: "有一些基础", advanced: "已有基础" };
export const planDurations = (minutes?: number | null) => typeof minutes === "number" ? minutes >= 60 ? `${Math.floor(minutes / 60)} 小时${minutes % 60 ? ` ${minutes % 60} 分钟` : ""}` : `${minutes} 分钟` : "时长待估计";

export function PlanSettingsForm({ ownerId, initial, defaultGoal, navigation = false, preserveSourceOrder = false, busy, error, onSave, onCancel, children }: {
  ownerId: string; initial?: PlanData; busy: boolean; error?: string;
  defaultGoal?: string; navigation?: boolean;
  preserveSourceOrder?: boolean;
  onSave: (settings: PlanSettings) => void; onCancel: () => void; children?: React.ReactNode;
}) {
  const publicCopy = initial?.origin?.type === "public_path_copy";
  const inputs = initial?.planning_inputs || {};
  const [goal, setGoal] = useState(initial?.goal || defaultGoal || "");
  const [background, setBackground] = useState(initial?.background || "");
  const [level, setLevel] = useState<PlanLevel>(inputs.reading_level || "beginner");
  const [weekly, setWeekly] = useState(String((inputs.weekly_minutes || 240)/60));
  const [readCount,setReadCount]=useState(String(inputs.read_book_count??0));
  const [weeks, setWeeks] = useState(String(inputs.duration_weeks || 8));
  const [budgetMode, setBudgetMode] = useState<"weekly" | "total">(initial && !inputs.weekly_minutes ? "total" : "weekly");
  const [budget, setBudget] = useState(String(initial?.planning_policy?.budget_minutes ?? ""));
  const [sessionMinutes, setSessionMinutes] = useState(String(inputs.session_minutes || 30));
  const [language, setLanguage] = useState(inputs.language_preference || "不限");
  const [preferUnread, setPreferUnread] = useState(inputs.prefer_unread !== false);
  const [useMemories, setUseMemories] = useState(initial?.use_confirmed_memories === true || inputs.use_confirmed_memories === true);
  const [memoryIds, setMemoryIds] = useState<string[]>(initial?.confirmed_memory_ids || inputs.confirmed_memory_ids || []);
  const [edited, setEdited] = useState(false);
  useEffect(() => {
    if (!edited) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [edited]);
  const total = budgetMode === "weekly" ? Math.round(Number(weekly)*60) * Number(weeks) : budget ? Number(budget) : null;
  const valid = Number.isInteger(Number(readCount)) && Number(readCount)>=0 && Number(readCount)<=10000 && goal.trim().length >= 2 && (total === null || total > 0 && total <= 100000) && (publicCopy || !useMemories || memoryIds.length > 0);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !valid) return;
    onSave({ goal: goal.trim(), background: background.trim(), reading_level: level, read_book_count:Number(readCount), time_budget: "",
      ...(budgetMode === "weekly" ? { weekly_minutes: Math.round(Number(weekly)*60), duration_weeks: Number(weeks) } : { budget_minutes: total }),
      session_minutes: Number(sessionMinutes), language_preference: language, prefer_unread: preserveSourceOrder ? false : preferUnread,
      ...(!publicCopy ? { use_confirmed_memories: useMemories, confirmed_memory_ids: useMemories ? memoryIds : [] } : {}) });
  }
  return <div className={navigation ? "stl4-plan-setting-layout" : undefined}>{navigation ? <nav className="stl4-plan-setting-nav" aria-label="我的阅读计划"><h3>我的阅读计划</h3><span aria-current="page"><Clock3 size={17}/>设置阅读目标与时间</span><Link href="/account/collections"><BookOpen size={17}/>我的书架</Link><Link href="/account/notes"><NotebookPen size={17}/>阅读笔记</Link><Link href="/account?section=history"><History size={17}/>阅读历史</Link><Link href="/account/research"><MessageCircle size={17}/>我的问题</Link><Link href="/account/settings/privacy"><Settings size={17}/>账号设置</Link></nav> : null}<form className="stl4-plan-settings" onSubmit={submit} onChange={() => setEdited(true)}>
    <div className="stl4-plan-fields">
      <section><h3>1. 研究问题</h3><label>用一个简短问题或主题，说明你希望通过阅读解决什么<textarea value={goal} onChange={event => setGoal(event.target.value)} maxLength={1200} minLength={2} required rows={3} /></label><small>{goal.length} / 1200</small></section>
      <section><h3>2. 当前基础</h3><fieldset className="stl4-plan-levels"><legend className="sr-only">当前阅读基础</legend>{Object.entries(planLevels).map(([value, label]) => <label key={value}><input type="radio" name="plan-level" value={value} checked={level === value} onChange={() => setLevel(value as PlanLevel)} /><span>{label}<small>{value==="beginner"?"从头开始了解":value==="intermediate"?"读过少量相关书籍":"对该主题比较熟悉"}</small></span></label>)}</fieldset><label className="stl4-plan-read-count">已读相关书籍数量<input type="number" min={0} max={10000} step={1} value={readCount} onChange={event=>setReadCount(event.target.value)} required/><span>本</span></label><label>已读材料与关注方向<textarea value={background} onChange={event => setBackground(event.target.value)} maxLength={4000} rows={2} /></label></section>
      <section><h3>3. 时间安排</h3><label>预算方式<select data-stl-select value={budgetMode} onChange={event => setBudgetMode(event.target.value as "weekly" | "total")}><option value="weekly">每周时间 × 计划周期</option><option value="total">本轮总时间</option></select></label><div className="stl4-plan-field-row">{budgetMode === "weekly" ? <><label>每周可投入（小时）<input type="number" min={1/60} max={168} step="any" value={weekly} onChange={event => setWeekly(event.target.value)} required /></label><label>持续周期（周）<input type="number" min={1} max={52} step={1} value={weeks} onChange={event => setWeeks(event.target.value)} required /></label></> : <label>总时间（分钟，可留空）<input type="number" min={1} max={100000} step={1} value={budget} onChange={event => setBudget(event.target.value)} /></label>}<label>每次阅读（分钟）<input type="number" min={5} max={480} step={1} value={sessionMinutes} onChange={event => setSessionMinutes(event.target.value)} required /></label></div><label>材料语言偏好<select data-stl-select value={language} onChange={event => setLanguage(event.target.value)}><option>不限</option><option>中文优先</option><option>英文优先</option></select></label>{preserveSourceOrder ? <p>本次保留书单顺序。生成后可在计划中明确选择优化顺序。</p> : <label className="stl4-plan-check"><input type="checkbox" checked={preferUnread} onChange={event => setPreferUnread(event.target.checked)} />在允许使用阅读记录时优先安排未读材料</label>}</section>
      {children}
    </div>
    <aside className="stl4-plan-basis"><h3>依据预览</h3><dl><dt>主题匹配</dt><dd>{goal.trim() || "填写研究问题后，围绕问题组织材料。"}</dd><dt>已读记录</dt><dd>本人填写已读 {readCount||"0"} 本相关书籍，{planLevels[level]}。阅读完成由本人记录，不推断理解程度。</dd><dt>先修关系</dt><dd>{preserveSourceOrder ? "保留本人书单顺序；时间和基础用于估计与安排。" : publicCopy ? "保留公共路径阶段顺序；仅调整本人时间安排。" : "只按有来源的先修关系排序；材料中的文字建议供你判断。"}</dd><dt>时间预算</dt><dd>{total === null ? "尚未限制总时间" : `本轮共 ${planDurations(total)}`}，每次 {sessionMinutes || "—"} 分钟。估计可由本人修改。</dd><dt>语言偏好</dt><dd>{language}。用于导读建议，不自动排除其他语言的材料。</dd></dl>{!publicCopy ? <><h3>其他选项</h3><label className="stl4-plan-check"><input type="checkbox" checked={useMemories} onChange={event => { setUseMemories(event.target.checked); setEdited(true); }} />使用选定的已确认笔记</label><p>只将本人明确选择的笔记用于本计划的建议。</p>{useMemories ? <PlanMemoryPicker ownerId={ownerId} value={memoryIds} onChange={value => { setMemoryIds(value); setEdited(true); }} /> : <p>当前不使用个人笔记。</p>}</> : <p>公共路径副本保留编排，不使用个人笔记生成建议。</p>}
      {total !== null && total > 100000 ? <p role="alert">本轮预算不能超过 100000 分钟，请缩短周期。</p> : null}
      {error ? <p className="stl4-plan-error" role="alert">{error}</p> : null}<div className="stl4-plan-buttons"><button type="button" onClick={onCancel} disabled={busy}>取消</button><button className="is-primary" type="submit" disabled={busy || !valid}>{busy ? "正在保存…" : initial ? "保存设置" : "生成计划"}</button></div>
    </aside>
  </form></div>;
}

function PlanMemoryPicker({ ownerId, value, onChange }: { ownerId: string; value: string[]; onChange: (value: string[]) => void }) {
  const [page, setPage] = useState(1);
  const memories = usePersistentWorkspace<Paginated<ResearchRecord<MemoryData>>>(`/reading/research-memories/?state=confirmed&page=${page}`, ownerId);
  const rows = memories.data?.results.filter(row => row.state === "confirmed") || [];
  return <div className="stl4-plan-picker"><p>已选 {value.length} 条，最多 40 条</p>{memories.loading ? <LoadingState role="status">正在读取笔记…</LoadingState> : null}{memories.error ? <p role="alert">{memories.error}<button type="button" onClick={memories.reload}>重试</button></p> : rows.map(row => <label key={row.id}><input type="checkbox" checked={value.includes(row.id)} disabled={!value.includes(row.id) && value.length >= 40} onChange={event => onChange(event.target.checked ? [...value, row.id] : value.filter(id => id !== row.id))} /><span>{row.data.body}</span></label>)}{memories.data && !rows.length ? <p>本页没有已确认笔记。<Link href="/account/confirmed-notes" target="_blank" rel="noopener">查看并确认本人笔记 ↗</Link></p> : null}<button type="button" disabled={memories.loading} onClick={memories.reload}>刷新已确认笔记</button><PageButtons page={page} next={Boolean(memories.data?.next)} onChange={setPage} /><button type="button" disabled={!value.length} onClick={() => onChange([])}>清空所选笔记</button></div>;
}

/** Select the same source references that have already been saved in a private research project. */
export function PlanMaterialPicker({ ownerId, selected, onChange, single = false }: { ownerId: string; selected: ResolvedEvidence[]; onChange: (value: ResolvedEvidence[]) => void; single?: boolean }) {
  const [page, setPage] = useState(1);
  const [projectId, setProjectId] = useState("");
  const projects = usePersistentWorkspace<Paginated<ResearchRecord<ProjectData>>>(`/reading/research-projects/?page=${page}`, ownerId);
  const project = useResearchRecord<ProjectData>("research-projects", projectId || null, ownerId);
  const rows = project.data?.data.selections || [];
  return <section className="stl4-plan-material-picker"><h3>{single ? "选择替换材料" : "4. 选择材料"}</h3><p>从研究会话的选材中选择原文。{single ? "替换只作用于当前未完成项。" : "不选择时，将围绕问题从全馆可访问材料中检索。"}</p><label>研究会话<select data-stl-select value={projectId} onChange={event => setProjectId(event.target.value)}><option value="">选择研究会话</option>{projects.data?.results.map(row => <option key={row.id} value={row.id}>{row.data.title || row.data.question || "未命名研究"}</option>)}</select></label><PageButtons page={page} next={Boolean(projects.data?.next)} onChange={setPage} />
    {projects.error || project.error ? <p role="alert">{projects.error || project.error}<button type="button" onClick={() => { projects.reload(); project.reload(); }}>重试</button></p> : null}{projects.loading || project.loading ? <LoadingState role="status">正在读取材料…</LoadingState> : null}
    {rows.map((row, index) => { const key = researchEvidenceKey(row); return <label className="stl4-plan-source-choice" key={key}><input type={single ? "radio" : "checkbox"} name="plan-source" disabled={row.source_status !== "available"} checked={selected.some(ref => researchEvidenceKey(ref) === key)} onChange={event => onChange(single ? [row] : event.target.checked ? [...selected, row] : selected.filter(ref => researchEvidenceKey(ref) !== key))} /><ResearchEvidenceCover reference={row} small/><span><strong>{row.title || `材料 ${index + 1}`}</strong><small>{row.source_status === "available" ? `PDF 第 ${row.pdf_page || "—"} 页 · ${row.quote || row.text || "原文选段"}` : "来源当前不可用"}</small></span></label>; })}
    {project.data && !rows.length ? <p>此会话尚未保存选材。</p> : null}<p>已选择 {selected.length} 条原文。<button type="button" disabled={!selected.length} onClick={() => onChange([])}>清空</button></p><Link href="/explore/opinions" target="_blank" rel="noopener">去检索并保存选材 ↗</Link>
  </section>;
}

export function PageButtons({ page, next, onChange }: { page: number; next: boolean; onChange: (page: number) => void }) {
  if (page === 1 && !next) return null;
  return <nav className="stl4-plan-pagination" aria-label="资料分页"><button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!next} onClick={() => onChange(page + 1)}>下一页</button></nav>;
}
