"use client";

import { ExternalLink, FlaskConical, LoaderCircle, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";
import type { WorkflowCandidate } from "../workflow/workflow-types";
import { groupResearchSuggestions } from "./research-suggestion-state";

export type ResearchSuggestionPayload = {
  groups?: Array<{ key: string; label: string; count: number }>;
  suggestions?: WorkflowCandidate[];
  stats?: Record<string, unknown>;
  errors?: Array<{ code?: string; detail?: string; message?: string }>;
  run?: Record<string, unknown>;
};

const tierLabels: Record<string, string> = {
  in_library: "本馆正式条目",
  query_lexicon: "QueryLexicon 匹配",
  pdf_evidence: "当前 PDF / OCR",
  structured_source: "结构化来源",
  web_evidence: "联网学术来源",
  research_lead: "联网研究线索",
};

function endpointFor(mode: "intake" | "maintenance", itemId?: string, workId?: string) {
  return mode === "intake"
    ? `/catalog/admin/intake/${encodeURIComponent(itemId ?? "")}/suggestions/`
    : `/catalog/admin/library/works/${encodeURIComponent(workId ?? "")}/suggestions/`;
}

export function ResearchSuggestionPanel({
  mode,
  itemId,
  workId,
  step,
  field,
  token,
  canRun = true,
  onInspect,
  onUpdated,
  onMessage,
}: {
  mode: "intake" | "maintenance";
  itemId?: string;
  workId?: string;
  step: string;
  field?: string;
  token: string | null;
  canRun?: boolean;
  onInspect?: (items: WorkflowCandidate[], title: string) => void;
  onUpdated?: () => void;
  onMessage?: (message: string) => void;
}) {
  const [payload, setPayload] = useState<ResearchSuggestionPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const endpoint = endpointFor(mode, itemId, workId);
  const grouped = useMemo(() => groupResearchSuggestions(payload?.suggestions ?? [], field), [field, payload?.suggestions]);
  const publishSuggestions = useCallback((suggestions: WorkflowCandidate[]) => {
    window.dispatchEvent(new CustomEvent("workflow-research-suggestions", { detail: { step, suggestions } }));
  }, [step]);

  useEffect(() => {
    if (!token || (!itemId && !workId)) return;
    let active = true;
    const timer = window.setTimeout(() => {
      if (!active) return;
      setLoading(true);
      const query = new URLSearchParams({ step });
      if (field) query.set("field", field);
      void apiRequest<ResearchSuggestionPayload>(`${endpoint}?${query.toString()}`, {}, token)
        .then((result) => { if (active) { setPayload(result); publishSuggestions(result.suggestions ?? []); } })
        .catch(() => { if (active) setPayload({ suggestions: [], groups: [], errors: [{ detail: "研究候选暂时不可用，已有表单数据不受影响。" }] }); })
        .finally(() => { if (active) setLoading(false); });
    }, 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [endpoint, field, itemId, publishSuggestions, step, token, workId]);

  const runResearch = async () => {
    if (!token || running) return;
    setRunning(true);
    try {
      const result = await apiRequest<ResearchSuggestionPayload>(endpoint, { method: "POST", body: JSON.stringify({ step, fields: field ? [field] : undefined, mode: "full" }) }, token);
      setPayload(result);
      publishSuggestions(result.suggestions ?? []);
      onMessage?.("本节研究已完成，联网线索与已有候选已刷新。正式字段仍需人工确认。");
      onUpdated?.();
    } catch (reason) {
      onMessage?.(reason instanceof Error ? reason.message : "本节研究暂时失败，已有馆藏数据未受影响。");
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="workflow-research-suggestions" aria-label={`${step} 社科研究候选`}>
      <header>
        <div><small>研究候选层</small><h3>本节建议与证据</h3><p>本馆、QueryLexicon、当前 PDF 和联网线索分组显示。建议不会自动写入正式字段。</p></div>
        <button type="button" className="button secondary" disabled={!canRun || running || !token} onClick={() => void runResearch()}>
          {running ? <LoaderCircle className="spin" size={14} /> : <FlaskConical size={14} />}联网补充本节
        </button>
      </header>
      {loading ? <p className="workflow-research-loading"><LoaderCircle className="spin" size={14} />正在读取快速建议……</p> : null}
      {payload?.errors?.map((error, index) => <p className="workflow-research-error" role="status" key={`${error.code ?? "error"}-${index}`}>{error.detail ?? error.message ?? "候选来源暂时不可用。"}</p>)}
      {payload?.groups?.length ? <div className="workflow-research-group-counts">{payload.groups.map((group) => <span key={group.key}>{group.label} {group.count}</span>)}</div> : null}
      {Array.isArray(payload?.run?.layers) ? <div className="workflow-research-run-status">{(payload.run.layers as Array<Record<string, unknown>>).map((layer) => <span key={String(layer.key)} data-status={String(layer.status)}>{String(layer.label)} · {String(layer.status) === "complete" ? "完成" : String(layer.status) === "skipped" ? "跳过" : "需注意"}</span>)}</div> : null}
      {grouped.length ? <div className="workflow-research-groups">{grouped.map(([tier, rows]) => <section key={tier}><h4>{tierLabels[tier] ?? tier}</h4>{rows.slice(0, 5).map((candidate) => <button type="button" className="workflow-research-card" key={String(candidate.id)} onClick={() => onInspect?.([candidate], `${candidate.label ?? "候选"} · 来源检查`)}><span><strong>{String(candidate.label ?? candidate.field_name ?? "候选")}</strong><small>{String(candidate.source_class ?? candidate.source ?? "")} · {Math.round(Number(candidate.confidence ?? 0) * 100)}% · {Number(candidate.evidence_count ?? 0)} 条证据</small></span><span>{tier === "research_lead" ? <ExternalLink size={13} /> : <Search size={13} />}</span></button>)}</section>)}</div> : !loading ? <p className="workflow-research-empty">当前步骤尚无快速候选。可以继续编辑，或点击“联网补充本节”。</p> : null}
    </section>
  );
}
