"use client";

import Link from "next/link";
import { ExternalLink, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { asArray, asRecord, asString } from "../workflow/workflow-types";

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
  onChange,
  onConfirm,
  onSkip,
  onRefresh,
  onMessage,
}: {
  workId: string;
  value: Record<string, unknown>;
  canManage: boolean;
  onChange: (value: Record<string, unknown>) => void;
  onConfirm: () => void;
  onSkip: () => void;
  onRefresh: () => void;
  onMessage: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<PathOption[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [selectedStage, setSelectedStage] = useState("");
  const [reason, setReason] = useState("");
  const [editorialNote, setEditorialNote] = useState("");
  const [required, setRequired] = useState(false);
  const [busy, setBusy] = useState("");
  const placements = placementsFrom(value);

  useEffect(() => {
    const token = getServerSessionCredential();
    if (!token || !query.trim()) {
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void apiRequest<{ results?: Array<Record<string, unknown>> }>(`/catalog/admin/theory-system/reading-paths/?q=${encodeURIComponent(query.trim())}`, {}, token)
        .then((payload) => {
          if (!active) return;
          setOptions((payload.results ?? []).map((row) => ({
            id: asString(row.id),
            title: asString(row.title),
            status: asString(row.status),
            stages: asArray(row.stages ?? row.items).map((entry) => {
              const stage = asRecord(entry);
              return { id: asString(stage.id), name: asString(stage.name ?? stage.stage_name) };
            }).filter((stage) => stage.name),
          })).filter((row) => row.id && row.title));
        })
        .catch((error) => { if (active) onMessage(error instanceof Error ? error.message : "阅读路径搜索失败。"); });
    }, 220);
    return () => { active = false; window.clearTimeout(timer); };
  }, [onMessage, query]);

  async function placeWork() {
    const token = getServerSessionCredential();
    if (!token || !workId || !selectedPath || !selectedStage) return;
    setBusy("placement");
    try {
      const result = await apiRequest<Record<string, unknown>>(
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
      onChange({
        ...value,
        reading_path_placements: [...placements, result],
      });
      setSelectedPath("");
      setSelectedStage("");
      setReason("");
      setEditorialNote("");
      setRequired(false);
      onMessage("当前作品已加入阅读路径。完整路径结构没有被覆盖。");
      onRefresh();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "阅读路径 placement 保存失败。");
    } finally {
      setBusy("");
    }
  }

  async function removePlacement(placement: Placement) {
    const token = getServerSessionCredential();
    if (!token || !workId) return;
    setBusy(placement.id);
    try {
      const result = await apiRequest<Record<string, unknown>>(
        `/catalog/admin/works/${workId}/reading-path-placements/${placement.id}/`,
        {
          method: "DELETE",
          body: JSON.stringify({ expected_path_updated_at: placement.path_updated_at || null }),
        },
        token,
      );
      onChange({
        ...value,
        reading_path_placements: placements.filter((row) => row.id !== placement.id),
        last_placement_action: result,
      });
      onMessage("已从该阅读路径移除当前作品，路径中的其他项目保持不变。");
      onRefresh();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "移除 placement 失败。");
    } finally {
      setBusy("");
    }
  }

  async function updateRecommendation(placement: string, enabled: boolean) {
    const token = getServerSessionCredential();
    if (!token || !workId || !placement) return;
    setBusy(`recommendation-${placement}`);
    try {
      await apiRequest(
        `/catalog/admin/works/${workId}/recommendation-overrides/${encodeURIComponent(placement)}/`,
        enabled
          ? { method: "PUT", body: JSON.stringify({ action: "pin", position: 0, note: "管理员在单项策展工作流中指定" }) }
          : { method: "DELETE" },
        token,
      );
      onMessage(enabled ? "已通过现有 RecommendationOverride 保存当前 placement，将在下一次推荐刷新时生效。" : "人工 placement 已移除，下一次刷新将恢复策略计算。");
      onRefresh();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "推荐 placement 保存失败。");
    } finally {
      setBusy("");
    }
  }

  const recommendationRows = asArray(value.recommendation_placements ?? value.recommendations).map(asRecord);
  return (
    <div className="workflow-curation-editor">
      <header><div><h3>当前作品的策展位置</h3><p>这里只修改当前作品。新增、重排和发布整条路径仍在完整策展工作台完成。</p></div><button type="button" onClick={onRefresh}><RefreshCw size={14} />刷新</button></header>
      <section className="workflow-current-placements">
        {placements.map((placement) => <article key={placement.id}><div><strong>{placement.path_title}</strong><span>{placement.stage_name}</span></div><p>{placement.recommendation_reason || "尚未填写推荐理由"}</p><small>{placement.is_required ? "必读" : "选读"}{placement.editorial_note ? ` · ${placement.editorial_note}` : ""}</small>{canManage ? <button type="button" disabled={busy === placement.id} onClick={() => void removePlacement(placement)}><Trash2 size={13} />移除</button> : null}</article>)}
        {!placements.length ? <p>当前作品尚未加入阅读路径。这是一项策展提示，不会阻止发布。</p> : null}
      </section>
      {canManage ? <section className="workflow-placement-form"><label><span>搜索现有阅读路径</span><input value={query} onChange={(event) => { const next = event.target.value; setQuery(next); if (!next.trim()) setOptions([]); }} placeholder="输入路径名称" /></label>{options.length ? <div className="workflow-path-options">{options.map((option) => <button className={selectedPath === option.id ? "selected" : ""} type="button" key={option.id} onClick={() => { setSelectedPath(option.id); setSelectedStage(option.stages?.[0]?.id ?? ""); }}><strong>{option.title}</strong><small>{option.status || "draft"}</small></button>)}</div> : null}<label><span>与当前作品有关的阶段</span><select value={selectedStage} onChange={(event) => setSelectedStage(event.target.value)} disabled={!selectedPath}><option value="">选择现有阶段</option>{options.find((option) => option.id === selectedPath)?.stages?.map((stage) => <option value={stage.id} key={stage.id}>{stage.name}</option>)}</select></label><label><span>推荐理由</span><textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label><label><span>编辑备注</span><textarea rows={2} value={editorialNote} onChange={(event) => setEditorialNote(event.target.value)} /></label><label className="workflow-checkbox"><input type="checkbox" checked={required} onChange={(event) => setRequired(event.target.checked)} /><span>设为必读</span></label><button className="button" type="button" disabled={!selectedPath || !selectedStage || busy === "placement"} onClick={() => void placeWork()}><Plus size={14} />加入阅读路径</button></section> : null}
      {recommendationRows.length ? <section className="workflow-recommendation-placements"><h3>与当前作品有关的推荐位置</h3>{recommendationRows.map((row) => { const placement = asString(row.placement); const enabled = row.override_enabled === true; return <article key={placement}><span><strong>{asString(row.title, placement)}</strong><small>{enabled ? "人工指定" : "按策略计算"}</small></span>{canManage ? <button type="button" disabled={busy === `recommendation-${placement}`} onClick={() => void updateRecommendation(placement, !enabled)}>{enabled ? "恢复策略" : "指定当前位置"}</button> : null}</article>; })}<Link href="/admin/recommendations">打开完整推荐管理 <ExternalLink size={12} /></Link></section> : null}
      <footer>{canManage ? <button className="button" type="button" onClick={onConfirm}>确认策展并继续</button> : null}<button className="button secondary" type="button" onClick={onSkip}>暂不策展并继续</button><Link className="button secondary" href="/admin/reading-paths">打开完整策展工作台 <ExternalLink size={13} /></Link></footer>
    </div>
  );
}
