"use client";

import Link from "next/link";
import { ExternalLink, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { CandidateDecisionBar } from "../research/candidate-decision-bar";
import type { CandidateActionDescriptor } from "../research/candidate-action-contract";
import { EvidenceEnvelopeCard } from "../research/evidence-envelope-card";
import { ResearchEntityPicker } from "../research/research-entity-picker";
import { useResearchWorkspace } from "../research/research-workspace-context";
import { asArray, asRecord, asString, type WorkflowCandidate } from "../workflow/workflow-types";

type PathOption = { id: string; title: string; status?: string; stages?: Array<{ id?: string; name: string }> };
type Placement = {
  id: string;
  path_id: string;
  path_title: string;
  path_updated_at?: string;
  stage_id?: string | null;
  stage_name: string;
  recommendation_reason: string;
  is_required: boolean;
  editorial_note: string;
};

function candidateField(candidate: WorkflowCandidate): string {
  return asString(candidate.field_name ?? candidate.field).toLocaleLowerCase();
}

function candidateEntityType(candidate: WorkflowCandidate): string {
  return asString(candidate.entity_type ?? candidate.target_type ?? candidate.candidate_entity_type).toLocaleLowerCase();
}

function matchesCandidate(candidate: WorkflowCandidate, names: string[]): boolean {
  const field = candidateField(candidate);
  const entityType = candidateEntityType(candidate);
  return names.some((name) => field.includes(name) || entityType.includes(name));
}

function candidateEvidence(candidate: WorkflowCandidate): unknown[] {
  const records = asArray(candidate.evidence_records);
  if (records.length) return records;
  const envelope = asRecord(candidate.evidence);
  const nested = asArray(envelope.records ?? envelope.items ?? envelope.evidence);
  if (nested.length) return nested;
  return Object.keys(envelope).length ? [envelope] : asArray(candidate.evidence);
}

type FrontendImpact = {
  publicVisibility: boolean | null;
  modules: string[];
  projections: string[];
  states: Record<string, unknown>[];
  targets: Record<string, unknown>[];
};

function normalizeFrontendImpact(value: unknown): FrontendImpact | null {
  const row = asRecord(value);
  if (!Object.keys(row).length) return null;
  const modules = asArray(row.modules).map((item) => asString(item)).filter(Boolean);
  const projections = asArray(row.projections).map((item) => asString(item)).filter(Boolean);
  const states = asArray(row.projection_states ?? row.projectionStates).map(asRecord).filter((item) => Object.keys(item).length);
  const targets = asArray(row.targets).map(asRecord).filter((item) => Object.keys(item).length);
  const hasPayload = modules.length || projections.length || states.length || targets.length || typeof row.public_visibility === "boolean";
  if (!hasPayload) return null;
  return {
    publicVisibility: typeof row.public_visibility === "boolean" ? row.public_visibility : null,
    modules,
    projections,
    states,
    targets,
  };
}

function sectionImpact(root: unknown, sectionKey: string, candidates: WorkflowCandidate[] = []): unknown {
  const source = asRecord(root);
  const sections = asRecord(source.sections);
  const section = asRecord(sections[sectionKey] ?? source[sectionKey]);
  const direct = section.frontend_impact ?? section.frontendImpact;
  if (normalizeFrontendImpact(direct)) return direct;
  for (const candidate of candidates) {
    const impact = candidate.frontend_impact ?? candidate.frontendImpact;
    if (normalizeFrontendImpact(impact)) return impact;
  }
  return normalizeFrontendImpact(source.frontend_impact ?? source.frontendImpact)
    ? source.frontend_impact ?? source.frontendImpact
    : null;
}

function FrontendImpactPanel({ value }: { value: unknown }) {
  const impact = normalizeFrontendImpact(value);
  if (!impact) {
    return <div className="workflow-frontend-impact is-unavailable"><strong>前台影响未接通</strong><span>后端尚未返回 dependency/projection 元数据，本页不会推测影响范围。</span></div>;
  }
  return (
    <div className="workflow-frontend-impact">
      <strong>前台影响</strong>
      {impact.publicVisibility !== null ? <span>{impact.publicVisibility ? "当前对象公开可见" : "当前对象尚未公开"}</span> : null}
      {impact.modules.map((item) => <span key={`module-${item}`}>{item}</span>)}
      {impact.projections.map((item) => <span key={`projection-${item}`}>{item}</span>)}
      {impact.targets.map((target, index) => {
        const label = asString(target.label, `前台目标 ${index + 1}`);
        const url = asString(target.url);
        return url ? <Link href={url} target="_blank" key={`${label}-${url}`}>{label} <ExternalLink size={11} /></Link> : <span key={`${label}-${index}`}>{label}</span>;
      })}
      {impact.states.length ? <div className="workflow-impact-state-list">{impact.states.map((state, index) => {
        const name = asString(state.label ?? state.name ?? state.type, `Projection ${index + 1}`);
        const status = asString(state.status, "unknown");
        const sourceRevision = Number(state.source_revision ?? 0);
        const projectedRevision = Number(state.projected_revision ?? 0);
        return <small key={`${name}-${index}`}><b>{name}</b><span>{status}</span><span>source {sourceRevision} / projected {projectedRevision}</span>{state.last_error_code ? <em>{asString(state.last_error_code)}</em> : null}</small>;
      })}</div> : null}
    </div>
  );
}

function PreviewPanel({ value, previewUrl }: { value: unknown; previewUrl?: string }) {
  const root = asRecord(value);
  const preview = asRecord(root.preview ?? root.materialized_preview ?? root.materializedPreview);
  const materialized = asRecord(preview.materialized ?? preview.data ?? preview);
  const rows = Object.entries(materialized).slice(0, 6);
  if (!rows.length && !previewUrl) {
    return <section className="workflow-preview-state is-unavailable"><strong>Preview 未接通</strong><p>后端尚未返回 materialized preview 或预览地址，本页不会生成模拟预览。</p></section>;
  }
  return <section className="workflow-preview-state"><header><strong>Preview</strong>{previewUrl ? <Link href={previewUrl} target="_blank">打开真实预览 <ExternalLink size={12} /></Link> : null}</header>{rows.length ? <dl>{rows.map(([field, entry]) => <div key={field}><dt>{field}</dt><dd>{typeof entry === "string" || typeof entry === "number" ? String(entry) : "已包含结构化预览数据"}</dd></div>)}</dl> : <p>预览地址可用，后端未返回当前页面的 materialized 字段摘要。</p>}</section>;
}

function CurationCandidateList({ candidates, canManage, busy, onInspect, onDecide }: {
  candidates: WorkflowCandidate[];
  canManage: boolean;
  busy: string;
  onInspect?: (candidate: WorkflowCandidate) => void;
  onDecide: (candidate: WorkflowCandidate, descriptor: CandidateActionDescriptor, editedValue?: unknown) => Promise<void>;
}) {
  return <div className="workflow-curation-candidate-list">{candidates.map((candidate) => {
    const evidence = candidateEvidence(candidate).slice(0, 2);
    const actionPrefix = `candidate-${candidate.id}-`;
    const busyAction = busy.startsWith(actionPrefix) ? busy.slice(actionPrefix.length) : "";
    return <article key={candidate.id}><button type="button" className="workflow-curation-candidate-summary" onClick={() => onInspect?.(candidate)}><span><strong>{asString(candidate.label, "未命名候选")}</strong><small>{asString(candidate.source_tier_label ?? candidate.source_tier ?? candidate.source, "来源待核对")} · {String(candidate.evidence_count ?? evidence.length)} 条依据</small></span><b>{Math.round(Number(candidate.confidence ?? 0) * 100)}%</b></button>{evidence.length ? <div className="workflow-curation-evidence-list">{evidence.map((entry, index) => <EvidenceEnvelopeCard evidence={entry} compact key={`${candidate.id}-evidence-${index}`} />)}</div> : <p className="workflow-candidate-evidence-missing">当前候选未返回可展示的 EvidenceEnvelope，请先查看依据或核实来源。</p>}<CandidateDecisionBar candidate={candidate} busyAction={busyAction} disabled={!canManage || Boolean(busy)} onInspect={() => onInspect?.(candidate)} onAction={(descriptor, editedValue) => onDecide(candidate, descriptor, editedValue)} /></article>;
  })}</div>;
}

function CurationCandidateSection({
  title,
  description,
  candidates,
  impact,
  canManage,
  busy,
  onInspect,
  onDecide,
}: {
  title: string;
  description: string;
  candidates: WorkflowCandidate[];
  impact: unknown;
  canManage: boolean;
  busy: string;
  onInspect?: (candidate: WorkflowCandidate) => void;
  onDecide: (candidate: WorkflowCandidate, descriptor: CandidateActionDescriptor, editedValue?: unknown) => Promise<void>;
}) {
  return <section className="workflow-curation-knowledge-section"><header><div><h3>{title}</h3><p>{description}</p></div><span>{candidates.length} 个候选</span></header><FrontendImpactPanel value={impact} />{candidates.length ? <CurationCandidateList candidates={candidates} canManage={canManage} busy={busy} onInspect={onInspect} onDecide={onDecide} /> : <p className="workflow-no-reliable-candidate">没有可靠候选。当前馆藏原文、馆内实体或已核实来源没有达到本区证据要求，可以稍后重跑研究。</p>}</section>;
}

function placementsFrom(value: Record<string, unknown>): Placement[] {
  return asArray(value.reading_path_placements ?? value.placements).flatMap((entry, index) => {
    const row = asRecord(entry);
    const path = asRecord(row.path ?? row.reading_path);
    const stage = asRecord(row.stage);
    const id = asString(row.id, `placement-${index}`);
    const pathId = asString(row.path_id ?? path.id);
    if (!pathId) return [];
    return [{
      id,
      path_id: pathId,
      path_title: asString(row.path_title ?? path.title, "未命名阅读路径"),
      path_updated_at: asString(row.path_updated_at),
      stage_id: asString(row.stage_id ?? stage.id) || null,
      stage_name: asString(row.stage_name ?? stage.name, "未指定阶段"),
      recommendation_reason: asString(row.recommendation_reason),
      is_required: row.is_required === true,
      editorial_note: asString(row.editorial_note),
    }];
  });
}

export function WorkCurationEditor({
  workId,
  value,
  canManage,
  canManageRecommendations,
  onConfirm,
  onSkip,
  onRefresh,
  onMessage,
  suggestions = [],
  onInspect,
}: {
  workId: string;
  value: Record<string, unknown>;
  canManage: boolean;
  canManageRecommendations: boolean;
  onConfirm: () => Promise<void>;
  onSkip: () => Promise<void>;
  onRefresh: () => Promise<boolean>;
  onMessage: (message: string) => void;
  suggestions?: WorkflowCandidate[];
  onInspect?: (candidate: WorkflowCandidate) => void;
}) {
  const workspace = useResearchWorkspace();
  const [selectedPath, setSelectedPath] = useState("");
  const [selectedPathName, setSelectedPathName] = useState("");
  const [selectedPathOption, setSelectedPathOption] = useState<PathOption | null>(null);
  const [selectedStage, setSelectedStage] = useState("");
  const [pathLoading, setPathLoading] = useState(false);
  const [reason, setReason] = useState("");
  const [editorialNote, setEditorialNote] = useState("");
  const [required, setRequired] = useState(false);
  const [busy, setBusy] = useState("");
  const busyRef = useRef("");
  const placements = placementsFrom(value);
  const claimSuggestions = suggestions.filter((candidate) => candidate.kind === "derived_claim_curation" || matchesCandidate(candidate, ["core_viewpoint", "major_criticism", "major_response"])).slice(0, 5);
  const theoryConceptSuggestions = suggestions.filter((candidate) => matchesCandidate(candidate, ["theory", "concept"]));
  const scholarRelationSuggestions = suggestions.filter((candidate) => matchesCandidate(candidate, ["scholar", "person", "contributor"]));
  const topicSuggestions = suggestions.filter((candidate) => matchesCandidate(candidate, ["topic"]));
  const debateSuggestions = suggestions.filter((candidate) => matchesCandidate(candidate, ["debate"]));
  const readingPathSuggestions = suggestions.filter((candidate) => matchesCandidate(candidate, ["reading_path", "placement"]));
  const recommendationSuggestions = suggestions.filter((candidate) => matchesCandidate(candidate, ["recommendation"]));
  const curatedClaims = asArray(value.curated_claims).map(asRecord);

  const beginAction = (key: string) => {
    if (!canManage || busyRef.current) return false;
    busyRef.current = key;
    setBusy(key);
    return true;
  };

  const finishAction = (key: string) => {
    if (busyRef.current !== key) return;
    busyRef.current = "";
    setBusy("");
  };

  useEffect(() => {
    if (!selectedPath) return;
    const token = getServerSessionCredential();
    if (!token) return;
    let active = true;
    void apiRequest<Record<string, unknown>>(`/catalog/admin/theory-system/reading-paths/${encodeURIComponent(selectedPath)}/`, {}, token)
      .then((row) => {
        if (!active) return;
        const stages = asArray(row.stages ?? row.items).map((entry) => {
          const stage = asRecord(entry);
          return { id: asString(stage.id), name: asString(stage.name ?? stage.stage_name) };
        }).filter((stage) => stage.id && stage.name);
        const option = {
          id: asString(row.id, selectedPath),
          title: asString(row.title, "未命名阅读路径"),
          status: asString(row.status),
          stages,
        };
        setSelectedPathOption(option);
        setSelectedPathName(option.title);
        setSelectedStage((current) => stages.some((stage) => stage.id === current) ? current : stages[0]?.id ?? "");
      })
      .catch((error) => {
        if (!active) return;
        setSelectedPathOption(null);
        setSelectedStage("");
        onMessage(error instanceof Error ? error.message : "读取路径阶段失败。");
      })
      .finally(() => { if (active) setPathLoading(false); });
    return () => { active = false; };
  }, [onMessage, selectedPath]);

  async function placeWork() {
    const token = getServerSessionCredential();
    if (!token || !workId || !selectedPath || !selectedStage) return;
    const actionKey = "placement";
    if (!beginAction(actionKey)) return;
    try {
      await apiRequest<Record<string, unknown>>(
        `/catalog/admin/works/${workId}/reading-path-placements/`,
        {
          method: "POST",
          body: JSON.stringify({
            reading_path_id: selectedPath,
            stage_id: selectedStage,
            recommendation_reason: reason.trim(),
            is_required: required,
            editorial_note: editorialNote.trim(),
          }),
        },
        token,
      );
      setSelectedPath("");
      setSelectedPathName("");
      setSelectedPathOption(null);
      setSelectedStage("");
      setReason("");
      setEditorialNote("");
      setRequired(false);
      onMessage("当前作品已加入阅读路径。完整路径结构没有被覆盖。");
      await onRefresh();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "阅读路径 placement 保存失败。");
    } finally {
      finishAction(actionKey);
    }
  }

  async function removePlacement(placement: Placement) {
    const token = getServerSessionCredential();
    if (!token || !workId) return;
    const actionKey = `remove-${placement.id}`;
    if (!beginAction(actionKey)) return;
    try {
      await apiRequest<Record<string, unknown>>(
        `/catalog/admin/works/${workId}/reading-path-placements/${placement.id}/`,
        {
          method: "DELETE",
          body: JSON.stringify({ expected_path_updated_at: placement.path_updated_at || null }),
        },
        token,
      );
      onMessage("已从该阅读路径移除当前作品，路径中的其他项目保持不变。");
      await onRefresh();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "移除 placement 失败。");
    } finally {
      finishAction(actionKey);
    }
  }

  async function updateRecommendation(placement: string, enabled: boolean) {
    const token = getServerSessionCredential();
    if (!token || !workId || !placement) return;
    const actionKey = `recommendation-${placement}`;
    if (!beginAction(actionKey)) return;
    try {
      await apiRequest(
        `/catalog/admin/works/${workId}/recommendation-overrides/${encodeURIComponent(placement)}/`,
        enabled
          ? { method: "PUT", body: JSON.stringify({ action: "pin", position: 0, note: "管理员在单项策展工作流中指定" }) }
          : { method: "DELETE" },
        token,
      );
      onMessage(enabled ? "已通过现有 RecommendationOverride 保存当前 placement，将在下一次推荐刷新时生效。" : "人工 placement 已移除，下一次刷新将恢复策略计算。");
      await onRefresh();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "推荐 placement 保存失败。");
    } finally {
      finishAction(actionKey);
    }
  }

  async function refreshCuration() {
    const actionKey = "refresh";
    if (!beginAction(actionKey)) return;
    try {
      await onRefresh();
    } finally {
      finishAction(actionKey);
    }
  }

  async function decideCandidate(candidate: WorkflowCandidate, descriptor: CandidateActionDescriptor, editedValue?: unknown) {
    const action = descriptor.action;
    const actionKey = `candidate-${candidate.id}-${action}`;
    if (!beginAction(actionKey)) return;
    try {
      const decisionCandidate = {
        ...candidate,
        decision_descriptor: descriptor,
        ...(editedValue !== undefined ? { edited_value: editedValue } : {}),
      };
      const succeeded = await workspace?.onCandidateDecision?.(decisionCandidate, action);
      if (succeeded === false) throw new Error("候选决定没有完成。");
      onMessage(action === "reject" ? "已记录不采用，正式内容没有被写入。" : "候选已采用，变更将进入编辑草稿并显示在前台影响中。");
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "候选决定失败。");
    } finally {
      finishAction(actionKey);
    }
  }

  async function confirmCuration() {
    const actionKey = "confirm";
    if (!beginAction(actionKey)) return;
    try {
      await onConfirm();
    } finally {
      finishAction(actionKey);
    }
  }

  async function skipCuration() {
    const actionKey = "skip";
    if (!beginAction(actionKey)) return;
    try {
      await onSkip();
    } finally {
      finishAction(actionKey);
    }
  }

  const recommendationRows = asArray(value.recommendation_placements ?? value.recommendations).map(asRecord);
  return (
    <div className="workflow-curation-editor">
      <header><div><h3>知识策展与前台联动</h3><p>在同一页面判断作品如何进入 Knowledge Core。每项采用都会显示真实前台影响，未完成的可选策展不会阻止发布。</p></div><button type="button" disabled={!canManage || Boolean(busy)} onClick={() => void refreshCuration()}><RefreshCw size={14} />{busy === "refresh" ? "刷新中" : "刷新"}</button></header>
      <section className="workflow-claim-curation" aria-labelledby="workflow-claim-curation-title">
        <header><div><h3 id="workflow-claim-curation-title">核心观点、批评与回应</h3><p>机器命题已去重、聚类和排序。这里只主动呈现最多五个当前最值得人工判断的候选。</p></div><span>{claimSuggestions.length} 个待决定</span></header>
        <FrontendImpactPanel value={sectionImpact(value, "claims", claimSuggestions)} />
        {curatedClaims.length ? <div className="workflow-curated-claim-list">{curatedClaims.map((claim, index) => <article key={asString(claim.id, `curated-${index}`)}><small>{({ core_viewpoint: "核心观点", major_criticism: "主要批评", major_response: "主要回应" } as Record<string, string>)[asString(claim.kind)] ?? asString(claim.kind)}</small><p>{asString(claim.proposition)}</p><span>{asString(claim.status, "draft")} · {String(claim.evidence_count ?? 0)} 条依据</span></article>)}</div> : <p>尚未采用正式策展命题。此项可稍后处理，不阻止作品发布。</p>}
        {claimSuggestions.length ? <CurationCandidateList candidates={claimSuggestions} canManage={canManage} busy={busy} onInspect={onInspect} onDecide={decideCandidate} /> : <p className="workflow-no-reliable-candidate">没有可靠候选。原因是当前 PDF EvidenceSpan 尚未形成达到阈值的原子命题，或候选仍在后台等待可用 AI capability。</p>}
      </section>
      <div className="workflow-curation-knowledge-grid">
        <CurationCandidateSection title="理论与概念" description="确认作品与正式 Theory、Concept 的关系。" candidates={theoryConceptSuggestions} impact={sectionImpact(value, "theory_concept", theoryConceptSuggestions)} canManage={canManage} busy={busy} onInspect={onInspect} onDecide={decideCandidate} />
        <CurationCandidateSection title="学者与知识关系" description="连接作者、批评者及其他学者与作品中的知识位置。" candidates={scholarRelationSuggestions} impact={sectionImpact(value, "scholar_relations", scholarRelationSuggestions)} canManage={canManage} busy={busy} onInspect={onInspect} onDecide={decideCandidate} />
        <CurationCandidateSection title="主题" description="选择馆内正式 Topic，避免用自由文本制造重复主题。" candidates={topicSuggestions} impact={sectionImpact(value, "topics", topicSuggestions)} canManage={canManage} busy={busy} onInspect={onInspect} onDecide={decideCandidate} />
        <CurationCandidateSection title="Debate / 争论" description="采用后进入 Debate 草稿及其证据位置，不会自动公开。" candidates={debateSuggestions} impact={sectionImpact(value, "debates", debateSuggestions)} canManage={canManage} busy={busy} onInspect={onInspect} onDecide={decideCandidate} />
      </div>
      <section className="workflow-current-placements">
        <header><div><h3>Reading Path</h3><p>选择现有路径和阶段，并说明先后逻辑。</p></div><div className="workflow-frontend-impact"><strong>采用后影响</strong><span>Work 页面</span><span>Reading Path 页面</span></div></header>
        {placements.map((placement) => <article key={placement.id}><div><strong>{placement.path_title}</strong><span>{placement.stage_name}</span></div><p>{placement.recommendation_reason || "尚未填写推荐理由"}</p><small>{placement.is_required ? "必读" : "选读"}{placement.editorial_note ? ` · ${placement.editorial_note}` : ""}</small>{canManage ? <button type="button" disabled={Boolean(busy)} onClick={() => void removePlacement(placement)}><Trash2 size={13} />{busy === `remove-${placement.id}` ? "移除中" : "移除"}</button> : null}</article>)}
        {!placements.length ? <p>当前作品尚未加入阅读路径。这是一项策展提示，不会阻止发布。</p> : null}
      </section>
      {canManage ? <section className="workflow-placement-form"><ResearchEntityPicker label="搜索现有阅读路径" endpoint="/catalog/admin/theory-system/reading-paths/" entityType="reading_path" step="curation" field="reading_path_placements" queryHint={selectedPathName} values={selectedPath ? [{ id: selectedPath, name: selectedPathName || "已选择阅读路径" }] : []} suggestions={readingPathSuggestions} onInspect={onInspect} disabled={Boolean(busy)} onChange={(next) => { const path = next.at(-1); setSelectedPath(path?.id ?? ""); setSelectedPathName(path?.name ?? ""); setSelectedPathOption(null); setSelectedStage(""); setPathLoading(Boolean(path?.id)); }} /><label><span>与当前作品有关的阶段</span><select value={selectedStage} onChange={(event) => setSelectedStage(event.target.value)} disabled={Boolean(busy) || !selectedPath || pathLoading}><option value="">{pathLoading ? "正在读取现有阶段" : "选择现有阶段"}</option>{selectedPathOption?.stages?.map((stage) => <option value={stage.id} key={stage.id}>{stage.name}</option>)}</select>{selectedPathOption ? <small>{selectedPathOption.title} · {selectedPathOption.status || "draft"}</small> : null}</label><label><span>推荐理由</span><textarea disabled={Boolean(busy)} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label><label><span>编辑备注</span><textarea disabled={Boolean(busy)} rows={2} value={editorialNote} onChange={(event) => setEditorialNote(event.target.value)} /></label><label className="workflow-checkbox"><input type="checkbox" disabled={Boolean(busy)} checked={required} onChange={(event) => setRequired(event.target.checked)} /><span>设为必读</span></label><button className="button" type="button" disabled={Boolean(busy) || !selectedPath || !selectedStage || pathLoading} onClick={() => void placeWork()}><Plus size={14} />{busy === "placement" ? "正在加入" : "加入阅读路径"}</button></section> : null}
      <CurationCandidateSection title="相关推荐" description="说明作品在相关推荐中的位置和推荐理由。" candidates={recommendationSuggestions} impact={sectionImpact(value, "recommendations", recommendationSuggestions)} canManage={canManageRecommendations} busy={busy} onInspect={onInspect} onDecide={decideCandidate} />
      {recommendationRows.length ? <section className="workflow-recommendation-placements"><h3>与当前作品有关的推荐位置</h3>{recommendationRows.map((row) => { const placement = asString(row.placement); const enabled = row.override_enabled === true; return <article key={placement}><span><strong>{asString(row.title, placement)}</strong><small>{enabled ? "人工指定" : "按策略计算"}</small></span>{canManageRecommendations ? <button type="button" disabled={Boolean(busy)} onClick={() => void updateRecommendation(placement, !enabled)}>{busy === `recommendation-${placement}` ? "保存中" : enabled ? "恢复策略" : "指定当前位置"}</button> : null}</article>; })}<Link href="/admin/recommendations">打开完整推荐管理 <ExternalLink size={12} /></Link></section> : null}
      <PreviewPanel value={value} previewUrl={asString(value.preview_url ?? value.previewUrl)} />
      <footer>{canManage ? <button className="button" type="button" disabled={Boolean(busy)} onClick={() => void confirmCuration()}>{busy === "confirm" ? "正在确认" : "确认策展并继续"}</button> : null}<button className="button secondary" type="button" disabled={!canManage || Boolean(busy)} onClick={() => void skipCuration()}>{busy === "skip" ? "正在跳过" : "暂不策展并继续"}</button><Link className="button secondary" href="/admin/reading-paths">打开完整策展工作台 <ExternalLink size={13} /></Link></footer>
    </div>
  );
}
