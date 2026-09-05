"use client";

import Link from "next/link";
import { ExternalLink, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { EntityPicker } from "../forms/workflow-fields";
import { CurationFieldAssistant } from "./curation-field-assistant";
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

function PreviewPanel({ previewUrl }: { value?: unknown; previewUrl?: string }) {
  return previewUrl ? <section className="workflow-preview-state"><Link href={previewUrl} target="_blank">打开完整前台预览 <ExternalLink size={12} /></Link></section> : null;
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
  editionId,
  contextKey,
  value,
  canManage,
  canManageRecommendations,
  onConfirm,
  onSkip,
  onRefresh,
  onMessage,
  beforeAction,
}: {
  editionId?: string;
  beforeAction?: () => Promise<boolean>;
  contextKey?: string;
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
    if (beforeAction && !(await beforeAction())) return;
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
      onMessage("当前作品的阅读路径安排已保存。正式发布后对读者生效。");
      await onRefresh();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "阅读路径安排未保存成功。");
    } finally {
      finishAction(actionKey);
    }
  }

  async function removePlacement(placement: Placement) {
    const token = getServerSessionCredential();
    if (!token || !workId) return;
    const actionKey = `remove-${placement.id}`;
    if (beforeAction && !(await beforeAction())) return;
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
      onMessage(error instanceof Error ? error.message : "移除阅读路径安排失败。");
    } finally {
      finishAction(actionKey);
    }
  }

  async function updateRecommendation(placement: string, enabled: boolean) {
    const token = getServerSessionCredential();
    if (!token || !workId || !placement) return;
    const actionKey = `recommendation-${placement}`;
    if (beforeAction && !(await beforeAction())) return;
    if (!beginAction(actionKey)) return;
    try {
      await apiRequest(
        `/catalog/admin/works/${workId}/recommendation-overrides/${encodeURIComponent(placement)}/`,
        enabled
          ? { method: "PUT", body: JSON.stringify({ action: "pin", position: 0, note: "管理员在单项策展工作流中指定" }) }
          : { method: "DELETE" },
        token,
      );
      onMessage(enabled ? "推荐位置已保存，正式发布后生效。" : "已取消人工指定，正式发布后按馆藏内容推荐。");
      await onRefresh();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "推荐位置未保存成功。");
    } finally {
      finishAction(actionKey);
    }
  }

  async function refreshCuration() {
    const actionKey = "refresh";
    if (beforeAction && !(await beforeAction())) return;
    if (!beginAction(actionKey)) return;
    try {
      await onRefresh();
    } finally {
      finishAction(actionKey);
    }
  }

  async function confirmCuration() {
    const actionKey = "confirm";
    if (beforeAction && !(await beforeAction())) return;
    if (!beginAction(actionKey)) return;
    try {
      await onConfirm();
    } finally {
      finishAction(actionKey);
    }
  }

  async function skipCuration() {
    const actionKey = "skip";
    if (beforeAction && !(await beforeAction())) return;
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
      <header><div><h3>更多策展内容</h3><p>为作品补充观点、相关人物和阅读安排。这里的可选内容可以稍后处理。</p></div><button type="button" disabled={!canManage || Boolean(busy)} onClick={() => void refreshCuration()}><RefreshCw size={14} />{busy === "refresh" ? "刷新中" : "刷新"}</button></header>
      <section className="workflow-claim-curation" aria-labelledby="workflow-claim-curation-title">
        <header><div><h3 id="workflow-claim-curation-title">核心观点、批评与回应</h3><p>核对作品中的观点、批评和回应，并保留原文依据。</p></div></header>
        {curatedClaims.length ? <div className="workflow-curated-claim-list">{curatedClaims.map((claim, index) => <article key={asString(claim.id, `curated-${index}`)}><small>{({ core_viewpoint: "核心观点", major_criticism: "主要批评", major_response: "主要回应" } as Record<string, string>)[asString(claim.kind)] ?? asString(claim.kind)}</small><p>{asString(claim.proposition)}</p><span>{({ published: "已发布", approved: "已确认", draft: "草稿", pending: "需要确认", rejected: "不采用" } as Record<string, string>)[asString(claim.status)] || "草稿"} · {String(claim.evidence_count ?? 0)} 条依据</span></article>)}</div> : <p>尚未确认作品观点，可稍后补充。</p>}
        {canManage ? <div className="workflow-curation-knowledge-grid">{([["core_viewpoint", "核心观点"], ["major_criticism", "主要批评"], ["major_response", "主要回应"]] as const).map(([field, label]) => <section className="workflow-field-assistant-row" key={field}><strong>{label}</strong><CurationFieldAssistant label={label} targetType="work" targetId={workId} fieldName={field} currentValue={curatedClaims.filter((claim) => claim.kind === field).map((claim) => claim.proposition)} formContext={{ edition_id: editionId, editorial_context: contextKey }} lookupLabel="获取观点建议" beforeAction={beforeAction} onAccepted={async () => { await onRefresh(); onMessage("观点决定已保存。正式发布前只在当前草稿中使用。"); }} /></section>)}</div> : null}
      </section>
      <section className="workflow-curation-knowledge-section"><header><div><h3>学者与知识关系</h3><p>作者与译者在相应字段确认。理论、主题和相关争论在知识对象中继续策展。</p></div></header><Link href={`/admin/knowledge?object_type=work&object_id=${encodeURIComponent(workId)}`}>打开当前作品的知识策展 <ExternalLink size={12} /></Link></section>
      <section className="workflow-current-placements">
        <header><div><h3>阅读路径</h3><p>选择现有路径和阶段，并说明先后逻辑。</p></div></header>
        {placements.map((placement) => <article key={placement.id}><div><strong>{placement.path_title}</strong><span>{placement.stage_name}</span></div><p>{placement.recommendation_reason || "尚未填写推荐理由"}</p><small>{placement.is_required ? "必读" : "选读"}{placement.editorial_note ? ` · ${placement.editorial_note}` : ""}</small>{canManage ? <button type="button" disabled={Boolean(busy)} onClick={() => void removePlacement(placement)}><Trash2 size={13} />{busy === `remove-${placement.id}` ? "移除中" : "移除"}</button> : null}</article>)}
        {!placements.length ? <p>当前作品尚未加入阅读路径。这是一项策展提示，不会阻止发布。</p> : null}
      </section>
      {canManage ? <section className="workflow-placement-form"><fieldset disabled={Boolean(busy)}><EntityPicker label="搜索馆内阅读路径" endpoint="/catalog/admin/theory-system/reading-paths/" queryParam="q" nameField="title" values={selectedPath ? [{ id: selectedPath, name: selectedPathName || "已选择阅读路径" }] : []} onChange={(next) => { const path = next.at(-1); setSelectedPath(path?.id ?? ""); setSelectedPathName(path?.name ?? ""); setSelectedPathOption(null); setSelectedStage(""); setPathLoading(Boolean(path?.id)); }} /></fieldset><label><span>与当前作品有关的阶段</span><select value={selectedStage} onChange={(event) => setSelectedStage(event.target.value)} disabled={Boolean(busy) || !selectedPath || pathLoading}><option value="">{pathLoading ? "正在读取现有阶段" : "选择现有阶段"}</option>{selectedPathOption?.stages?.map((stage) => <option value={stage.id} key={stage.id}>{stage.name}</option>)}</select>{selectedPathOption ? <small>{selectedPathOption.title} · {selectedPathOption.status === "published" ? "已发布" : "草稿"}</small> : null}</label><label><span>推荐理由</span><textarea disabled={Boolean(busy)} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label><label><span>编辑备注</span><textarea disabled={Boolean(busy)} rows={2} value={editorialNote} onChange={(event) => setEditorialNote(event.target.value)} /></label><label className="workflow-checkbox"><input type="checkbox" disabled={Boolean(busy)} checked={required} onChange={(event) => setRequired(event.target.checked)} /><span>设为必读</span></label><button className="button" type="button" disabled={Boolean(busy) || !selectedPath || !selectedStage || pathLoading} onClick={() => void placeWork()}><Plus size={14} />{busy === "placement" ? "正在加入" : "加入阅读路径"}</button></section> : null}
      {recommendationRows.length ? <section className="workflow-recommendation-placements"><h3>与当前作品有关的推荐位置</h3>{recommendationRows.map((row) => { const placement = asString(row.placement); const enabled = row.override_enabled === true; return <article key={placement}><span><strong>{asString(row.title, placement)}</strong><small>{enabled ? "人工指定" : "按策略计算"}</small></span>{canManageRecommendations ? <button type="button" disabled={Boolean(busy)} onClick={() => void updateRecommendation(placement, !enabled)}>{busy === `recommendation-${placement}` ? "保存中" : enabled ? "恢复策略" : "指定当前位置"}</button> : null}</article>; })}<Link href="/admin/recommendations">打开完整推荐管理 <ExternalLink size={12} /></Link></section> : null}
      <PreviewPanel value={value} previewUrl={asString(value.preview_url ?? value.previewUrl)} />
      <footer>{canManage ? <button className="button" type="button" disabled={Boolean(busy)} onClick={() => void confirmCuration()}>{busy === "confirm" ? "正在确认" : "确认更多策展内容"}</button> : null}<button className="button secondary" type="button" disabled={!canManage || Boolean(busy)} onClick={() => void skipCuration()}>{busy === "skip" ? "正在跳过" : "这些内容暂不适用"}</button><Link className="button secondary" href="/admin/reading-paths">打开完整策展工作台 <ExternalLink size={13} /></Link></footer>
    </div>
  );
}
