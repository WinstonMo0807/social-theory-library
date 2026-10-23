"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, LockKeyhole, Plus } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { subscribeToSessionChanges } from "@/lib/api";
import type { Paginated } from "@/lib/api/pagination";
import { createReadingPlan, type PlanData, type ResearchRecord, type ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceReference } from "@/lib/api/research-evidence";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ResearchCenterNav } from "./research-center-nav";
import { PageButtons, PlanMaterialPicker, PlanSettingsForm, type PlanSettings } from "./reading-plan-form";

export const planStatuses: Record<string, string> = { queued: "正在收集材料", running: "正在整理", completed: "计划已就绪", failed: "生成未完成", canceled: "已取消", queue_unavailable: "任务队列暂不可用", pending: "待读", reading: "进行中", skipped: "已跳过", disabled: "建议暂不可用", authorization_changed: "笔记授权已变更", skipped_after_edit: "已手动调整" };

export function PlanFrame({ children }: { children: ReactNode }) {
  return <div className="stl4-research-page stl4-plan-page"><div className="stl4-research-detail-shell">{children}</div></div>;
}

export function PlanSessionGate({ children, next }: { children: (ownerId: string, retrySession: () => void) => ReactNode; next: string }) {
  const { state, retry } = useSessionBootstrap();
  useEffect(() => { if (state.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(next)}`); }, [state.status, next]);
  if (state.status === "forbidden" || state.status === "temporary_error") return <PlanFrame><div className="stl4-research-state" role="alert"><h2>暂时无法读取阅读计划</h2><p>{state.message}</p><button onClick={retry}>重新验证登录</button></div></PlanFrame>;
  if (state.status !== "authenticated" || !state.user) return <PlanFrame><div className="stl4-research-state" role="status">正在核对登录状态…</div></PlanFrame>;
  return <div key={state.user.id}>{children(String(state.user.id), retry)}</div>;
}

export function ReadingPlans() {
  return <PlanSessionGate next="/account/plans">{ownerId => <PlanList ownerId={ownerId} />}</PlanSessionGate>;
}

function PlanList({ ownerId }: { ownerId: string }) {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<ResolvedEvidence[]>([]);
  const alive = useRef(false);
  const request = useRef({ fingerprint: "", id: "" });
  const plans = usePersistentWorkspace<Paginated<ResearchRecord<PlanData>>>(`/reading/reading-plans/?page=${page}`, ownerId,
    data => data.results.some(row => ["queued", "running"].includes(row.status || "")) ? 3000 : null);
  useEffect(() => { alive.current = true; const off = subscribeToSessionChanges(() => { alive.current = false; }); return () => { alive.current = false; off(); }; }, []);
  async function create(settings: PlanSettings) {
    if (busy) return;
    setBusy(true); setError("");
    const data = { ...settings, ...(selected.length ? { references: selected.map(researchEvidenceReference) } : {}) };
    const fingerprint = JSON.stringify(data);
    if (request.current.fingerprint !== fingerprint) request.current = { fingerprint, id: createRequestKey() };
    try {
      if (!alive.current) return;
      const record = await withPrivateOwner(ownerId, () => createReadingPlan({ ...data, request_id: request.current.id }));
      if (!alive.current) return;
      request.current = { fingerprint: "", id: "" };
      router.push(`/account/plans/${record.id}`);
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "计划未能创建，请重试。输入仍保留。"); }
    finally { if (alive.current) setBusy(false); }
  }
  return <PlanFrame><nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/account">读者中心</Link><span>/</span><span>阅读计划</span></nav><header className="stl4-plan-heading"><div><h1>{creating ? "设置阅读目标与时间" : "我的阅读计划"}</h1><p>{creating ? "填写问题、基础和时间，生成可随时调整的阅读安排。" : "根据目标、时间与已选材料安排，随时继续阅读。"}</p></div><span><LockKeyhole size={13} />仅本人可见</span></header>
    {creating ? <PlanSettingsForm ownerId={ownerId} busy={busy} error={error} onSave={create} onCancel={() => { setCreating(false); setSelected([]); setError(""); }}><PlanMaterialPicker ownerId={ownerId} selected={selected} onChange={setSelected} /></PlanSettingsForm> : <section className="stl4-research-panel"><ResearchCenterNav active="plans" counts={plans.data ? { plans: plans.data.count } : undefined} /><div className="stl4-research-panel-head"><h2>阅读计划</h2><button onClick={() => setCreating(true)}><Plus size={14} />创建计划</button></div>{plans.error ? <p role="alert">{plans.error}<button onClick={plans.reload}>重新读取</button></p> : null}{plans.loading ? <div className="stl4-research-state" role="status">正在读取计划…</div> : plans.data?.results.length ? <div className="stl4-research-list">{plans.data.results.map(row => <article key={row.id} className="stl4-research-card"><div className="stl4-research-card-copy"><h3>{row.data.goal}</h3><p>{row.data.items.length} 项材料 · {row.data.items.filter(item => item.status === "completed").length} 项已完成</p><time dateTime={row.updated_at}>{new Date(row.updated_at).toLocaleDateString("zh-CN")}</time></div><span className="stl4-research-status">{planStatuses[row.status || row.data.generation_status || "completed"] || "已保存"}</span><Link className="stl4-research-open" href={`/account/plans/${row.id}`}>查看计划 <ArrowRight size={14} /></Link></article>)}</div> : !plans.error ? <div className="stl4-research-empty"><h2>还没有阅读计划</h2><p>从一个真实问题开始，也可以选择研究会话中保存的材料。</p></div> : null}<PageButtons page={page} next={Boolean(plans.data?.next)} onChange={setPage} /></section>}
  </PlanFrame>;
}
