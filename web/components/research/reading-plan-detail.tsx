"use client";
import { MediaPlacement } from "@/components/media-placement";

import Link from "next/link";
import { AlertTriangle, ArrowDown, ArrowUp, BookOpen, Check, ChevronRight, Clock3, Lightbulb, LockKeyhole, MoreHorizontal, Pencil, Save, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { Dialog } from "@/components/ui/dialog";
import { normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { commandReadingPlan, exportResearchRecord, updateReadingPlan, type PlanData, type PlanItem, type ResearchRecord, type ResolvedEvidence } from "@/lib/api/research.client";
import { readerContextHref } from "@/lib/api/research-navigation";
import { researchEvidenceReference, researchReaderHref } from "@/lib/api/research-evidence";
import { isTaskRunning } from "@/lib/api/task-polling";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useResearchRecord } from "@/lib/api/use-persistent-workspace";
import { PlanMaterialPicker, PlanSettingsForm, planDurations, planLevels } from "./reading-plan-form";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { usePathPlanCommand, type PendingPathPlanCommand } from "@/lib/api/use-path-plan-command";
import { PlanFrame, PlanSessionGate, planStatuses } from "./reading-plans";

type PlanPatch = Omit<Parameters<typeof updateReadingPlan>[1], "expected_revision" | "request_id">;
const reasons: Record<string, string> = { within_budget: "在本轮预算内", completed_preserved: "已完成记录保留", owner_skipped: "本人选择跳过", source_unavailable: "来源目前不可用", prerequisite_outside_budget: "先修材料尚未安排", duration_unknown: "缺少时长估计", over_budget: "超出本轮时间预算" };
const statusNames = { pending: "待读", reading: "进行中", completed: "已完成", skipped: "已跳过" };
const safeHref = (url?: string | null) => url?.startsWith("/") && !url.startsWith("//") && !url.includes("\\") ? url : "";
const itemHref = (item: PlanItem, planId?: string) => {
  if (!item.available) return "";
  const href = item.reference ? researchReaderHref(item.reference) : safeHref(item.reader_url) || safeHref(typeof item.href === "string" ? item.href : null);
  return href.startsWith("/reader/") && planId ? readerContextHref(href, { returnTo: `/account/plans/${planId}` }) : href;
};
const messageOf = (reason: unknown) => reason instanceof Error ? reason.message : "操作未完成，请重试。";

export function ReadingPlanDetail({ id }: { id: string }) {
  const pendingPathCommand = useRef<PendingPathPlanCommand | null>(null);
  const [pending, setPending] = useState(false);
  useUnsavedForm(pending, false);
  return <PlanSessionGate next={`/account/plans/${id}`}>{(ownerId, retrySession) => <PlanWorkspace key={`${ownerId}:${id}`} pendingPathCommand={pendingPathCommand} onPending={setPending} id={id} ownerId={ownerId} retrySession={retrySession} />}</PlanSessionGate>;
}

function PlanWorkspace({ id, ownerId, retrySession, pendingPathCommand, onPending }: { id: string; ownerId: string; retrySession: () => void; pendingPathCommand: RefObject<PendingPathPlanCommand | null>; onPending: (value: boolean) => void }) {
  const workspace = useResearchRecord<PlanData>("reading-plans", id, ownerId);
  const copyCommand = usePathPlanCommand(ownerId, id, pendingPathCommand, workspace.reload, onPending);
  const [expandedStages,setExpandedStages]=useState<Record<string,boolean>>({});
  const [tab, setTab] = useState<"overview" | "materials" | "questions" | "settings">("overview");
  const [settings, setSettings] = useState<ResearchRecord<PlanData> | null>(null);
  const [editor, setEditor] = useState<{ item: PlanItem; revision: number } | null>(null);
  const [order, setOrder] = useState<{ ids: string[]; revision: number } | null>(null);
  const [preview, setPreview] = useState<ResearchRecord<PlanData> | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [printRecord, setPrintRecord] = useState<ResearchRecord<PlanData> | null>(null);
  const alive = useRef(false);
  useEffect(() => { alive.current = true; const off = subscribeToSessionChanges(() => { alive.current = false; setSettings(null); setEditor(null); setOrder(null); setPreview(null); setPrintRecord(null); }); return () => { alive.current = false; off(); }; }, []);
  useEffect(() => {
    if (!printRecord) return;
    const cleanup = () => { document.body.classList.remove("stl4-print-plan"); setPrintRecord(null); };
    document.body.classList.add("stl4-print-plan");
    const frame = requestAnimationFrame(() => window.print());
    window.addEventListener("afterprint", cleanup);
    return () => { cancelAnimationFrame(frame); document.body.classList.remove("stl4-print-plan"); window.removeEventListener("afterprint", cleanup); };
  }, [printRecord]);
  useEffect(() => {
    if (!order) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [order]);
  const record = workspace.data;
  const publicCopy = record?.data.origin?.type === "public_path_copy";
  const busy = workspace.pending || actionBusy || copyCommand.pending || copyCommand.running;
  const recovery = copyCommand.pending || copyCommand.error ? <div className="stl4-plan-alert" role="alert"><p>{copyCommand.error || "上次保存结果待核对。已保留原请求，核对前暂停新的修改。"}</p>{copyCommand.pending ? <button disabled={copyCommand.running} onClick={() => void copyCommand.submit()}>核对上次保存结果</button> : null}</div> : null;
  async function patch(data: PlanPatch, expectedRevision = record?.revision) {
    if (!expectedRevision || busy) return false;
    setActionError(""); setNotice("");
    try {
      const saved = publicCopy ? await copyCommand.submit({ ...data, expected_revision: expectedRevision }) : await workspace.mutate(JSON.stringify(data), (_current, requestId) => updateReadingPlan(id, { ...data, request_id: requestId, expected_revision: expectedRevision }, ownerId));
      if (!saved) return false;
      setNotice(publicCopy ? "已保存本人修改，公共路径版本保持不变。" : "已保存，计划安排已按当前规则更新。"); return true;
    } catch (reason) { setActionError(messageOf(reason)); return false; }
  }
  async function command(action: "cancel" | "retry" | "enhance") {
    if (!record || busy) return;
    setActionError("");
    try { const saved = await workspace.mutate(action, current => commandReadingPlan(id, { action, expected_revision: current.revision })); if (saved) setNotice(action === "cancel" ? "任务已取消，已保存材料和进度保留。" : "任务已提交，进度将自动更新。"); }
    catch (reason) { setActionError(messageOf(reason)); }
  }
  async function externalRead(kind: "preview" | "print") {
    if (!record || busy) return;
    setActionBusy(true); setActionError("");
    try {
      const result = await withPrivateOwner(ownerId, () => kind === "preview" ? updateReadingPlan(id, { expected_revision: record.revision, optimize_order: true, preview: true }, ownerId) : exportResearchRecord<PlanData>("reading-plans", id, ownerId));
      if (!alive.current) return;
      if (kind === "preview") setPreview(result); else setPrintRecord(result);
    } catch (reason) { if (alive.current) setActionError(messageOf(reason)); }
    finally { if (alive.current) setActionBusy(false); }
  }
  if (!record) return <PlanFrame>{recovery}<div className="stl4-research-state" role={workspace.error ? "alert" : "status"}><h2>{workspace.error ? "阅读计划暂时不可用" : "正在读取阅读计划…"}</h2>{workspace.error ? <><p>{workspace.error}</p><button onClick={retrySession}>重新验证登录并读取</button><Link href="/account/plans">返回计划列表</Link></> : null}</div></PlanFrame>;
  const data = record.data;
  const policy = data.planning_policy;
  const status = record.status || data.generation_status || "completed";
  const enhancing = isTaskRunning(record.enhancement_status || data.enhancement_status);
  const generating = isTaskRunning(status);
  const completed = data.items.filter(item => item.status === "completed").length;
  const byId = new Map(data.items.map(item => [item.id, item]));
  const orderedItems = order ? order.ids.flatMap(key => byId.has(key) ? [byId.get(key)!] : []) : data.items;
  // Preserve the server's exact order, including repeated stage labels separated by another stage.
  const stages: Array<{ name: string; items: PlanItem[] }> = [];
  for (const item of orderedItems) {
    const name = item.stage || "围绕问题阅读";
    if (stages.at(-1)?.name === name && (!publicCopy || stages.at(-1)?.items[0]?.source_stage_id === item.source_stage_id)) stages[stages.length - 1].items.push(item);
    else stages.push({ name, items: [item] });
  }
  function unmetPrerequisites(item:PlanItem) {
    if(publicCopy || item.status==="completed" || item.status==="skipped") return [];
    return (data.prerequisites||[]).filter(edge=>edge.work_id===item.work_id).flatMap(edge=>{
      const required=orderedItems.find(row=>row.work_id===edge.requires_work_id);
      return required && required.status!=="completed" && (required.prior_reading?.progress_ratio||0)<0.98 ? [required] : [];
    });
  }
  function revealPrerequisite(item:PlanItem) {
    const target=document.getElementById(`plan-item-${item.id}`),stage=target?.closest("details");
    if(stage instanceof HTMLDetailsElement) stage.open=true;
    target?.scrollIntoView({block:"center"});
  }
  const nextItem = data.items.find(item => item.status !== "completed" && item.status !== "skipped" && item.budget_assignment?.included !== false && itemHref(item, id));
  const deferred = data.items.filter(item => item.budget_assignment?.included === false && item.status !== "skipped");
  const reorderStale = Boolean(order && order.revision !== record.revision);
  const memoryEnabled = data.use_confirmed_memories === true || data.planning_inputs?.use_confirmed_memories === true;
  function move(item: PlanItem, direction: number) {
    if (!record) return;
    const ids = order?.ids || data.items.map(row => row.id);
    const index = ids.indexOf(item.id);
    const next = index + direction;
    if (next < 0 || next >= ids.length || publicCopy && byId.get(ids[next])?.source_stage_id !== item.source_stage_id || item.status === "completed" || byId.get(ids[next])?.status === "completed") return;
    const changed = [...ids]; [changed[index], changed[next]] = [changed[next], changed[index]];
    setOrder({ ids: changed, revision: order?.revision || record.revision });
  }
  return <PlanFrame><div className="stl4-plan-screen" data-settings-open={Boolean(settings)||undefined}><nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/account">读者中心</Link><span>/</span><Link href="/account/plans">阅读计划</Link></nav>
    <header className="stl4-plan-heading"><div><h1>{order?"调整阅读顺序":"我的阅读计划"} <span><LockKeyhole size={14} />仅本人可见</span></h1></div><button className="stl4-plan-rule-hint" onClick={() => setRulesOpen(true)}><Lightbulb size={25} /><span>{publicCopy ? "保留公开路径的阶段与材料安排。" : "按先修顺序与未读材料建议下一项。"}</span><span>查看依据 →</span></button></header>
    <div className="stl4-plan-toolbar"><nav aria-label="计划内容">{([['overview', '计划总览'], ['materials', '阶段与材料'], ['questions', '相关问题'], ['settings', '计划设置']] as const).map(([value, label]) => <button key={value} aria-current={tab === value ? "page" : undefined} onClick={() => { setTab(value); if (value === "settings") setSettings(record); }}>{label}</button>)}</nav><div><span className="stl4-plan-saved"><Check size={12} />{copyCommand.pending ? "保存结果待核对" : order ? "顺序尚未保存" : "已保存"} <time dateTime={record.updated_at}>{new Date(record.updated_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time></span><button className="is-primary" disabled={!order || busy || reorderStale} onClick={async () => { if (order && await patch({ order: order.ids }, order.revision)) setOrder(null); }}><Save size={14} />保存计划</button><button disabled={generating || busy} onClick={() => { setTab("materials"); setOrder({ ids: data.items.map(item => item.id), revision: record.revision }); }}><SlidersHorizontal size={14} />调整计划</button></div></div>
    {recovery}
    {publicCopy ? <p className="stl4-plan-notice">来自公共阅读路径的私人副本。阶段与材料原样保留，升级公开版本请从来源路径比较后确认。{typeof data.path_snapshot === "object" && data.path_snapshot && "slug" in data.path_snapshot && typeof data.path_snapshot.slug === "string" ? <Link href={`/theories/reading-paths/${encodeURIComponent(data.path_snapshot.slug)}?copy=${encodeURIComponent(id)}`}>返回来源路径并核对版本</Link> : null}</p> : null}
    {workspace.error || actionError ? <div className="stl4-plan-alert" role="alert"><p>{actionError || workspace.error}{workspace.conflict ? " 草稿仍保留，请核对最新计划后重新编辑。" : ""}</p><button onClick={workspace.reload}>重新读取</button></div> : null}{notice ? <p className="stl4-plan-notice" role="status">{notice}</p> : null}
    {generating || enhancing || status === "failed" || status === "canceled" || workspace.pollPaused ? <div className="stl4-plan-alert" role="status"><p>{generating ? "正在收集可读材料，任务状态会自动更新。" : enhancing ? "计划已可阅读，正在补充可选择采纳的导读建议。" : planStatuses[status] || "计划进度已保留"}{workspace.pollPaused ? " 自动刷新已暂停，可重新读取进度。" : ""}</p>{generating || enhancing ? <button disabled={busy} onClick={() => void command("cancel")}>取消任务</button> : !data.items.length ? <button disabled={busy} onClick={() => void command("retry")}>重试生成</button> : null}<button onClick={workspace.reload}>读取进度</button></div> : null}
    {reorderStale ? <div className="stl4-plan-alert" role="alert"><p>计划在其他位置发生了变化，当前顺序草稿未覆盖服务器。请以最新材料重新调整。</p><button onClick={() => setOrder(null)}>使用最新顺序</button></div> : null}
    {tab === "questions" ? <section className="stl4-plan-questions"><h2>研究问题与阅读笔记</h2><p>{data.goal}</p>{record.project_id ? <Link href={`/account/research/${record.project_id}`}>继续相关研究 <ChevronRight size={14} /></Link> : null}{data.items.some(item => item.note) ? data.items.filter(item => item.note).map(item => <article key={item.id}><h3>{item.title}</h3><p>{item.note}</p><button disabled={busy} onClick={() => setEditor({ item, revision: record.revision })}>编辑笔记</button></article>) : <p>尚未记录相关问题。可在材料的更多操作中写下问题与笔记。</p>}</section> : <div className={`stl4-plan-grid ${tab === "materials" ? "is-materials" : ""}`}>
      {tab === "materials" ? <aside className="stl4-plan-stage-nav"><h3>阶段列表</h3><p>共 {stages.length} 个阶段 · {data.items.length} 项材料</p><ol>{stages.map((stage, index) => <li key={stage.items[0].id}><a href={`#plan-stage-${index}`} onClick={() => { const element = document.getElementById(`plan-stage-${index}`); if (element instanceof HTMLDetailsElement) element.open = true; }}><span>{index + 1}</span><div><strong>{stage.name}</strong><small>{stage.items.filter(item => item.status === "completed").length} / {stage.items.length} 已完成</small></div></a></li>)}</ol><button onClick={() => setTab("overview")}>查看完整计划</button></aside> : <aside className="stl4-plan-summary"><SummaryBlock title="1. 我的研究目标" onEdit={() => setSettings(record)} disabled={generating || busy}><p>{data.goal}</p></SummaryBlock><SummaryBlock title="2. 我的基础" onEdit={() => setSettings(record)} disabled={generating || busy}><p>{policy?.reading_level ? planLevels[policy.reading_level] : "尚未设置"}</p><p>{data.planning_inputs?.read_book_count!=null?`已读相关书籍 ${data.planning_inputs.read_book_count} 本`:"已读数量尚未填写"}</p><p>{data.background || "尚未填写已读材料与关注方向。"}</p></SummaryBlock><SummaryBlock title="3. 时间与偏好" onEdit={() => setSettings(record)} disabled={generating || busy}><p>本轮 {policy?.budget_minutes ? planDurations(policy.budget_minutes) : "不限总时长"}</p><p>每次 {policy?.session_minutes || 30} 分钟 · {data.planning_inputs?.language_preference || "语言不限"}</p></SummaryBlock><section><h3>4. 研究问题 / 公共路线</h3>{record.project_id ? <Link href={`/account/research/${record.project_id}`}>返回来源研究 →</Link> : <p>材料按本计划目标组织。</p>}{!publicCopy ? <div className="stl4-plan-memory"><strong>已确认笔记（可选）</strong><p>{memoryEnabled ? `已授权 ${(data.confirmed_memory_ids || data.planning_inputs?.confirmed_memory_ids || []).length} 条选定笔记` : "已关闭，仅使用公开材料生成建议。"}</p><button disabled={generating || busy} onClick={() => setSettings(record)}>选择笔记 →</button></div> : null}</section></aside>}
      <section className="stl4-plan-materials"><header><h2>5. 阶段与材料</h2><span>共 {stages.length} 个阶段 · {data.items.length} 项材料</span><button type="button" onClick={()=>{const allOpen=stages.every((stage,index)=>expandedStages[stage.items[0].id]??(index===0||Boolean(order)));setExpandedStages(Object.fromEntries(stages.map(stage=>[stage.items[0].id,!allOpen])));}}>{stages.every((stage,index)=>expandedStages[stage.items[0].id]??(index===0||Boolean(order)))?"全部收起":"全部展开"}</button></header>{!data.items.length ? <div className="stl4-research-empty"><BookOpen size={26} /><h2>{generating ? "正在为问题寻找材料" : "当前计划没有可读材料"}</h2><p>{generating ? "请稍后读取进度，也可以取消此次任务。" : "可以调整问题或从研究会话选材后创建计划。"}</p><Link href="/account/plans">返回阅读计划</Link></div> : stages.map(({ name: stage, items }, index) => <details id={`plan-stage-${index}`} className="stl4-plan-stage" key={items[0].id} open={expandedStages[items[0].id]??(index === 0 || Boolean(order))} onToggle={event=>{const open=event.currentTarget.open;setExpandedStages(previous=>previous[items[0].id]===open?previous:{...previous,[items[0].id]:open});}}><summary><span className="stl4-plan-stage-number">阶段 {index + 1}</span><strong>{stage}</strong><small>{items.length} 项材料</small><span>{items.filter(item => item.status === "completed").length} / {items.length} 已完成</span><progress aria-label={`${stage}完成进度`} max={items.length} value={items.filter(item => item.status === "completed").length} /></summary><ol>{items.map((item, itemIndex) => <li id={`plan-item-${item.id}`} key={item.id} data-prerequisite={unmetPrerequisites(item).length?true:undefined} className={item.status === "completed" ? "is-completed" : item.budget_assignment?.included === false ? "is-deferred" : ""}><span className="stl4-plan-item-number">{index + 1}.{itemIndex + 1}</span><PlanCover item={item} /><div className="stl4-plan-item-copy"><h3>{item.title || "未命名材料"}</h3><small>{[item.authors?.join("、"), item.publication_year].filter(Boolean).join(" · ")}</small><p>{item.learning_goal || item.reason || "围绕当前研究问题阅读。"}</p><small>{planDurations(item.estimated_minutes)} · {item.kind === "node" ? "知识条目" : item.kind === "chapter" ? "指定章节" : item.reading_scope === "selected_passage" ? "选定原文" : "整份文献"}{item.difficulty?.level ? ` · ${planLevels[item.difficulty.level]}` : ""}</small>{item.budget_assignment?.included === false ? <p className="stl4-plan-deferred">{reasons[item.budget_assignment.reason] || "暂未安排"}</p> : null}</div><div className="stl4-plan-item-actions"><label><span className="sr-only">{item.title}阅读状态</span><select value={item.status} disabled={busy || generating || Boolean(order) || item.status === "completed"} onChange={event => { const status = event.target.value as PlanItem["status"]; if (status !== "completed" || window.confirm("将此项记为已完成后，计划会保留它的材料、位置和时长，不再参与替换或重新排序。确认已完成阅读？")) void patch({ item_id: item.id, status }); }}>{Object.entries(statusNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>{itemHref(item, id) ? <Link href={itemHref(item, id)}>{item.status === "reading" ? "继续阅读" : "开始阅读"}</Link> : <span>材料不可用</span>}<button title="笔记、替换和时长设置" aria-label={`${item.title || "材料"}更多操作`} disabled={busy || generating || Boolean(order)} onClick={() => setEditor({ item, revision: record.revision })}><MoreHorizontal size={16} /></button>{order ? <div className="stl4-plan-move"><button aria-label={`${item.title}上移`} disabled={busy || reorderStale || item.status === "completed" || orderedItems.indexOf(item) === 0 || orderedItems[orderedItems.indexOf(item) - 1]?.status === "completed" || publicCopy && orderedItems[orderedItems.indexOf(item) - 1]?.source_stage_id !== item.source_stage_id} onClick={() => move(item, -1)}><ArrowUp size={13} /></button><button aria-label={`${item.title}下移`} disabled={busy || reorderStale || item.status === "completed" || orderedItems.indexOf(item) === orderedItems.length - 1 || orderedItems[orderedItems.indexOf(item) + 1]?.status === "completed" || publicCopy && orderedItems[orderedItems.indexOf(item) + 1]?.source_stage_id !== item.source_stage_id} onClick={() => move(item, 1)}><ArrowDown size={13} /></button></div> : null}</div>{unmetPrerequisites(item).length?<section className="stl4-plan-prerequisite"><AlertTriangle size={20}/><div><strong>{unmetPrerequisites(item).some(required=>orderedItems.indexOf(required)>orderedItems.indexOf(item))?"存在先修顺序冲突":"先修材料尚未完成"}</strong>{unmetPrerequisites(item).map(required=><p key={required.id}>《{item.title}》需要先阅读《{required.title}》。<button type="button" onClick={()=>revealPrerequisite(required)}>查看先修材料 →</button></p>)}</div></section>:null}</li>)}</ol></details>)}
        {deferred.length ? <div className="stl4-plan-alert"><Clock3 size={17} /><p>{deferred.length} 项材料因时间、来源或先修条件暂未安排，仍保留在计划中。</p><button disabled={busy || generating} onClick={() => setSettings(record)}>调整时间</button></div> : null}{!publicCopy ? <div className="stl4-plan-reschedule"><div><strong>重新安排未完成部分</strong><p>按时间、阅读进度和先修顺序调整。已完成部分保留。</p></div><button disabled={busy || generating || !data.items.length || Boolean(order)} onClick={() => void externalRead("preview")}>预览调整 →</button></div> : <p>可调整同一阶段内未完成材料的顺序；阶段顺序与已完成材料保留。</p>}{order ? <div className="stl4-plan-buttons"><button onClick={() => setOrder(null)} disabled={busy}>取消顺序调整</button><button className="is-primary" disabled={busy || reorderStale} onClick={async () => { if (await patch({ order: order.ids }, order.revision)) setOrder(null); }}>确认并保存</button></div> : null}
      </section><aside className="stl4-plan-operations"><h3>计划操作</h3>{nextItem ? <Link className="is-primary" href={itemHref(nextItem, id)}>继续阅读 <ChevronRight size={14} /></Link> : null}<button disabled={busy} onClick={() => void externalRead("print")}>打印 / 保存 PDF</button>{!publicCopy ? <button disabled={busy || generating || enhancing || !data.items.length || Boolean(order)} onClick={() => void command("enhance")}>重新整理导读建议</button> : null}<dl><dt>已完成</dt><dd>{completed}</dd><dt>进行中</dt><dd>{data.items.filter(item => item.status === "reading").length}</dd><dt>待读</dt><dd>{data.items.filter(item => item.status === "pending").length}</dd><dt>已跳过</dt><dd>{data.items.filter(item => item.status === "skipped").length}</dd></dl><p>{planDurations(data.schedule?.planned_minutes)}已安排；分为 {data.schedule?.sessions.length || 0} 次阅读。</p>{data.schedule?.unknown_duration_count ? <p>{data.schedule.unknown_duration_count} 项时长待本人估计。</p> : null}{data.schedule?.unscheduled_minutes ? <p>另有 {planDurations(data.schedule.unscheduled_minutes)}超过分次明细上限。</p> : null}<p>{data.notice || "阅读进度由你记录。"}</p></aside>
    </div>}
    {settings ? <section className="stl4-plan-setting-page" aria-labelledby="plan-settings-title"><div className="stl4-plan-dialog-head"><h2 id="plan-settings-title">设置阅读目标与时间</h2><button aria-label="关闭计划设置" disabled={busy} onClick={() => { setSettings(null); setTab("overview"); }}><X size={18} /></button></div>{settings.revision !== record.revision ? <p role="alert">计划已有新版本。输入仍保留；保存前请核对最新内容。<button onClick={() => setSettings(record)}>丢弃本地设置并载入最新版</button></p> : null}<PlanSettingsForm navigation key={`${settings.id}:${settings.revision}`} ownerId={ownerId} initial={settings.data} busy={busy || generating} error={actionError} onCancel={() => { setSettings(null); setTab("overview"); }} onSave={async values => { if (await patch(values, settings.revision)) { setSettings(null); setTab("overview"); } }} /></section> : null}
    <Dialog className="stl4-plan-dialog" open={Boolean(editor)} onRequestClose={() => { if (!busy) setEditor(null); }} aria-labelledby="plan-item-title">{editor ? <PlanItemEditor publicCopy={publicCopy} key={`${editor.item.id}:${editor.revision}`} ownerId={ownerId} item={editor.item} prerequisitesCount={(data.prerequisites || []).filter(edge => edge.work_id === editor.item.work_id || edge.requires_work_id === editor.item.work_id).length} busy={busy} error={actionError} onClose={() => setEditor(null)} onSave={async values => { if (await patch({ ...values, item_id: editor.item.id }, editor.revision)) setEditor(null); }} /> : null}</Dialog>
    <Dialog className="stl4-plan-dialog" open={Boolean(preview)} onRequestClose={() => { if (!busy) setPreview(null); }} aria-labelledby="plan-preview-title">{preview ? <><h2 id="plan-preview-title">预览未完成部分的调整</h2><p>仅预览，尚未保存。先修、阅读基础和时间预算共同确定顺序。</p><ol className="stl4-plan-preview">{preview.data.items.map((item, index) => <li key={item.id}><strong>{index + 1}. {item.title}</strong><span>{statusNames[item.status]} · {item.budget_assignment ? reasons[item.budget_assignment.reason] : ""}</span></li>)}</ol>{preview.revision !== record.revision ? <p role="alert">计划已有新版本，请关闭后重新预览。</p> : null}<div className="stl4-plan-buttons"><button disabled={busy} onClick={() => setPreview(null)}>保留当前计划</button><button className="is-primary" disabled={busy || preview.revision !== record.revision} onClick={async () => { if (await patch({ optimize_order: true }, preview.revision)) setPreview(null); }}>应用调整并保存</button></div></> : null}</Dialog>
    <Dialog className="stl4-plan-dialog" open={rulesOpen} onRequestClose={() => setRulesOpen(false)} aria-labelledby="plan-rules-title"><h2 id="plan-rules-title">本计划的依据</h2><p>{policy?.notice || "按材料、先修关系、本人阅读基础和时间预算安排。"}</p><p>{data.schedule?.notice}</p><h3>先修关系</h3>{data.prerequisites?.length ? <ul>{data.prerequisites.map(edge => <li key={`${edge.work_id}:${edge.requires_work_id}`}>{data.items.find(item => item.work_id === edge.requires_work_id)?.title || "先修材料"} → {data.items.find(item => item.work_id === edge.work_id)?.title || "后续材料"}{researchReaderHref(edge.reference) ? <Link href={researchReaderHref(edge.reference)}>查看依据</Link> : <span> 来源当前不可用</span>}</li>)}</ul> : <p>暂无已确认的先修要求。</p>}<h3>时间与难度</h3><p>{publicCopy ? "路径副本不将策划的周数猜算为材料时长；请在材料更多操作中明确填写本人估计。" : "选段按原文字词估算；整本按最多12页采样外推，缺少文字时使用每页时长假设。可在材料更多操作中填写本人的估计。"}</p><p>文字复杂度与已读记录不能证明理解水平。已完成记录不参与替换或重新排序。</p><button onClick={() => setRulesOpen(false)}>关闭</button></Dialog>
  </div>{printRecord ? <PlanPrint record={printRecord} /> : null}</PlanFrame>;
}

function SummaryBlock({ title, onEdit, disabled, children }: { title: string; onEdit: () => void; disabled: boolean; children: React.ReactNode }) {
  return <section><header><h3>{title}</h3><button onClick={onEdit} disabled={disabled}><Pencil size={11} />编辑</button></header>{children}</section>;
}
function PlanCover({ item }: { item: PlanItem }) {
  const [failed, setFailed] = useState("");
  // The API supplies the published edition's real cover; missing covers stay empty.
  return item.cover_url && failed !== item.cover_url ? <MediaPlacement uses={item.cover_media?.display_uses} fallback={<span className="stl4-plan-cover is-empty" aria-label="暂无封面"><BookOpen size={18} /></span>}><img className="stl4-plan-cover" src={normalizePublicResourceUrl(item.cover_url)} alt="" loading="lazy" onError={() => setFailed(item.cover_url || "")} /></MediaPlacement> : <span className="stl4-plan-cover is-empty" aria-label="暂无封面"><BookOpen size={18} /></span>;
}
function PlanItemEditor({ publicCopy = false, ownerId, item, prerequisitesCount, busy, error, onSave, onClose }: { publicCopy?: boolean; ownerId: string; item: PlanItem; prerequisitesCount: number; busy: boolean; error: string; onSave: (data: PlanPatch) => void; onClose: () => void }) {
  const [note, setNote] = useState(item.note || "");
  const [minutes, setMinutes] = useState(String(item.estimated_minutes || ""));
  const [difficulty, setDifficulty] = useState(item.difficulty?.level || "");
  const [replacement, setReplacement] = useState<ResolvedEvidence[]>([]);
  const [replacing, setReplacing] = useState(false);
  const [removeRelations, setRemoveRelations] = useState(false);
  const [adopt, setAdopt] = useState(false);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || replacing && (!replacement.length || prerequisitesCount > 0 && !removeRelations)) return;
    const estimates = item.status !== "completed" && !replacing && (minutes !== String(item.estimated_minutes || "") || difficulty !== (item.difficulty?.level || ""));
    onSave({ note, ...(publicCopy && !replacing && minutes !== String(item.estimated_minutes || "") && item.status !== "completed" ? { item_minutes: minutes ? Number(minutes) : null } : {}), ...(!publicCopy && estimates ? { item_estimates: [{ work_id: item.work_id, ...(minutes ? { minutes: Number(minutes) } : {}), ...(difficulty ? { difficulty: difficulty as "beginner" | "intermediate" | "advanced" } : {}) }] } : {}), ...(replacing && replacement[0] ? { reference: researchEvidenceReference(replacement[0]), ...(!publicCopy ? { remove_related_prerequisites: removeRelations } : {}) } : {}), ...(adopt ? { adopt_suggestion: true } : {}) });
  }
  return <form onSubmit={submit} className="stl4-plan-item-editor"><div className="stl4-plan-dialog-head"><h2 id="plan-item-title">{item.title || "材料设置"}</h2><button type="button" aria-label="关闭材料设置" disabled={busy} onClick={onClose}><X size={18} /></button></div><label>相关问题与阅读笔记<textarea rows={4} maxLength={4000} value={note} onChange={event => setNote(event.target.value)} /></label>{item.status !== "completed" ? <><div className="stl4-plan-field-row"><label>本人估计时长（分钟）<input type="number" min={1} max={100000} value={minutes} onChange={event => setMinutes(event.target.value)} disabled={replacing} /></label>{!publicCopy ? <label>本人判断难度<select value={difficulty} onChange={event => setDifficulty(event.target.value)} disabled={replacing}><option value="">暂不判断</option>{Object.entries(planLevels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label> : null}</div><p>{item.planning_estimate?.limits || item.difficulty?.notice}</p><label className="stl4-plan-check"><input type="checkbox" checked={replacing} onChange={event => { setReplacing(event.target.checked); setReplacement([]); setAdopt(false); }} />替换当前材料</label>{publicCopy ? <p>替换仅作用于本人未完成的材料；原材料与笔记历史保留，公共路径不受影响。</p> : null}{replacing ? <><PlanMaterialPicker ownerId={ownerId} selected={replacement} onChange={setReplacement} single />{prerequisitesCount > 0 ? <label className="stl4-plan-check"><input type="checkbox" checked={removeRelations} onChange={event => setRemoveRelations(event.target.checked)} />确认移除此材料相关的 {prerequisitesCount} 条先修关系，旧依据不会套用到新材料。</label> : null}</> : null}{item.model_suggestion && !replacing ? <section><h3>待本人确认的导读建议</h3><p>{item.model_suggestion.stage} · {item.model_suggestion.reason}</p><p>{item.model_suggestion.learning_goal}</p><label className="stl4-plan-check"><input type="checkbox" checked={adopt} onChange={event => setAdopt(event.target.checked)} />采用这条建议</label></section> : null}</> : <p>此项已完成，保留原材料、顺序与时长记录；可继续补充笔记。</p>}{error ? <p role="alert">{error}</p> : null}<div className="stl4-plan-buttons"><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="is-primary" type="submit" disabled={busy || replacing && (!replacement.length || prerequisitesCount > 0 && !removeRelations)}>保存材料设置</button></div></form>;
}
function PlanPrint({ record }: { record: ResearchRecord<PlanData> }) {
  return <article className="stl4-plan-print"><h1>我的阅读计划</h1><p>仅本人可见 · {new Date(record.updated_at).toLocaleString("zh-CN")}</p><h2>{record.data.goal}</h2><p>{record.data.background}</p><p>本轮预算：{planDurations(record.data.planning_policy?.budget_minutes)}。{record.data.notice}</p>{record.data.items.map((item, index) => <section key={item.id}><h3>{index + 1}. {item.title}</h3><p>{item.stage} · {statusNames[item.status]} · {planDurations(item.estimated_minutes)}</p><p>{item.reason}</p>{item.note ? <p>我的笔记：{item.note}</p> : null}{item.reference?.source_status === "available" ? <blockquote>{item.reference.quote}</blockquote> : null}{!item.available ? <p>来源目前不可用。</p> : null}</section>)}</article>;
}
