"use client";

import {
  Check,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  LoaderCircle,
  Search,
  X,
} from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type AuthorityEntityType =
  | "person"
  | "concept"
  | "discipline"
  | "subdiscipline"
  | "theory_tradition"
  | "topic";

type EnrichmentTargetType =
  | "person"
  | "work"
  | "edition"
  | "discipline"
  | "subdiscipline"
  | "knowledge_node"
  | "topic"
  | "reading_path";

type Evidence = {
  category: string;
  summary: string;
  url?: string;
};

export type CurationAuthoritySuggestion = {
  label: string;
  originalName: string;
  aliases: string[];
  description: string;
  birthYear: number | null;
  deathYear: number | null;
};

type EnrichmentRow = {
  id: string;
  proposed_value: unknown;
};

type AssistantCandidate = {
  key: string;
  label: string;
  secondary: string;
  summary: string;
  statusLabel: "建议采用" | "需要确认" | "存在冲突";
  conflicts: string[];
  evidence: Evidence[];
  authority?: CurationAuthoritySuggestion;
  enrichment?: EnrichmentRow;
  claim?: { id: string; kind: string; decision_url: string };
};

type Props = {
  label: string;
  query?: string;
  authorityType?: AuthorityEntityType;
  targetType?: EnrichmentTargetType;
  targetId?: string | null;
  fieldName?: string;
  currentValue?: unknown;
  formContext?: Record<string, unknown>;
  lookupLabel?: string;
  onApply?: (value: unknown, authority?: CurationAuthoritySuggestion) => void;
  onAccepted?: () => void | Promise<void>;
  beforeAction?: () => Promise<boolean>;
};

export function CurationFieldAssistant({
  label,
  query = "",
  authorityType,
  targetType,
  targetId,
  fieldName,
  currentValue,
  formContext = {},
  lookupLabel = "查找建议",
  onApply,
  onAccepted,
  beforeAction,
}: Props) {
  const popoverId = useId();
  const normalizedQuery = useMemo(() => query.normalize("NFKC").trim(), [query]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [results, setResults] = useState<AssistantCandidate[]>([]);
  const [showMore, setShowMore] = useState(false);
  const [message, setMessage] = useState("");
  const [editingClaim, setEditingClaim] = useState<{ key: string; proposition: string } | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const contextKey = JSON.stringify([targetType, targetId, fieldName, normalizedQuery, currentValue, formContext]);
  useEffect(() => {
    requestRef.current?.abort();
    setResults([]);
    setEditingClaim(null);
    setOpen(false);
    setLoading(false);
    return () => requestRef.current?.abort();
  }, [contextKey]);

  async function lookup() {
    setOpen(true);
    setLoading(true);
    setShowMore(false);
    setMessage("");
    requestRef.current?.abort();
    const request = new AbortController();
    requestRef.current = request;
    const objectType = targetType || (authorityType === "concept" || authorityType === "theory_tradition" ? "knowledge_node" : authorityType);
    if (!objectType) {
      setLoading(false);
      setMessage("请先保存当前对象，再查找建议。");
      return;
    }
    try {
      const result = await apiRequest<{ results: AssistantCandidate[]; more_results?: AssistantCandidate[]; message?: string }>(
        "/catalog/admin/field-assistant/lookup/",
        { method: "POST", signal: request.signal, body: JSON.stringify({
          scope: "curation", object_type: objectType, object_id: targetId || null,
          field_name: fieldName || "identity", query: normalizedQuery,
          authority_type: authorityType || "", current_value: currentValue ?? null, form_context: formContext,
        }) }, getServerSessionCredential(),
      );
      if (request.signal.aborted) return;
      setResults([...(result.results || []), ...(result.more_results || [])]);
      setMessage(result.message || (!result.results.length ? "暂时没有合适建议，可以继续手工编辑。" : ""));
    } catch (reason) {
      if (!request.signal.aborted) setMessage(reason instanceof Error ? reason.message : "建议服务暂时不可用，可以继续手工编辑。");
    } finally {
      if (requestRef.current === request) setLoading(false);
    }
  }

  async function adopt(candidate: AssistantCandidate, editedProposition?: string) {
    setBusy(`adopt:${candidate.key}`);
    setMessage("");
    try {
      if (beforeAction && !(await beforeAction())) throw new Error("当前草稿未保存成功，请先处理保存提示。");
      if (candidate.claim) {
        await apiRequest(candidate.claim.decision_url, {
          method: "POST",
          body: JSON.stringify({
            action: editedProposition === undefined ? "accept" : "accept_with_edit",
            kind: candidate.claim.kind,
            proposition: editedProposition ?? "",
          }),
        }, getServerSessionCredential());
      } else if (candidate.enrichment) {
        await apiRequest(
          `/catalog/admin/field-enrichment/candidates/${candidate.enrichment.id}/decision/`,
          {
            method: "POST",
            body: JSON.stringify({ action: "accept", reason: `在${label}字段采用建议` }),
          },
          getServerSessionCredential(),
        );
      }
      onApply?.(candidate.enrichment?.proposed_value ?? candidate.label, candidate.authority);
      await onAccepted?.();
      setResults((current) => current.filter((row) => row.key !== candidate.key));
      setEditingClaim(null);
      setMessage(candidate.enrichment || candidate.claim
        ? "已采用并保存到当前编辑内容。正式发布前不会出现在公开页面。"
        : "已采用到当前草稿，请保存本页。正式发布前不会出现在公开页面。");
    } catch (reason) {
      setOpen(true);
      setMessage(reason instanceof Error ? reason.message : "未保存成功，请重试。");
    } finally {
      setBusy("");
    }
  }

  async function reject(candidate: AssistantCandidate) {
    if (!candidate.enrichment && !candidate.claim) return;
    setBusy(`reject:${candidate.key}`);
    setMessage("");
    try {
      await apiRequest(
        candidate.claim?.decision_url || `/catalog/admin/field-enrichment/candidates/${candidate.enrichment?.id}/decision/`,
        {
          method: "POST",
            body: JSON.stringify({ action: "reject", reason: `在${label}字段确认不采用`, ...(candidate.claim ? { kind: candidate.claim.kind } : {}) }),
        },
        getServerSessionCredential(),
      );
      setResults((current) => current.filter((row) => row.key !== candidate.key));
      setMessage("已记录不采用。该结果不会进入正式馆藏知识。");
    } catch (reason) {
      setMessage("未能记录本次决定，请稍后重试。");
    } finally {
      setBusy("");
    }
  }

  const visible = showMore ? results : results.slice(0, 3);
  const moreCount = Math.max(0, results.length - 3);

  return <div className="field-assistant-control curation-field-assistant">
    <button type="button" className="field-assistant-trigger" aria-expanded={open} aria-controls={popoverId} disabled={loading || Boolean(busy)} onClick={() => void lookup()}>
      {loading ? <LoaderCircle className="spin" size={13} /> : <Search size={13} />}{lookupLabel}
    </button>
    {open ? <section id={popoverId} className="field-assistant-popover" aria-label={`${label}建议`} aria-busy={loading}>
      <header><strong>{label}建议</strong><button type="button" aria-label={`关闭${label}建议`} onClick={() => setOpen(false)}><X size={14} /></button></header>
      {loading ? <p><LoaderCircle className="spin" size={14} />正在查找馆内记录和可核对资料</p> : null}
      {!loading && visible.map((candidate) => <article key={candidate.key}>
        <div><strong>{candidate.label}</strong><span>{candidate.statusLabel}</span></div>
        {candidate.secondary ? <small>{candidate.secondary}</small> : null}
        <p>{candidate.summary}</p>
        {candidate.conflicts.length ? <p className="field-assistant-conflict">存在冲突，请先核对。{candidate.conflicts.join("；")}</p> : null}
        <details><summary>查看依据</summary><ul>{candidate.evidence.map((evidence, index) => <li key={`${candidate.key}:${index}`}><b>{evidence.category}</b> {evidence.summary}{evidence.url ? <> <a href={evidence.url} target="_blank" rel="noreferrer">查看资料<ExternalLink size={11} /></a></> : null}</li>)}</ul></details>
        {editingClaim?.key === candidate.key ? <label><span>修改后的{label}</span><textarea rows={4} value={editingClaim.proposition} disabled={Boolean(busy)} onChange={(event) => setEditingClaim({ key: candidate.key, proposition: event.target.value })} /></label> : null}
        <footer className="curation-field-assistant-actions">
          {(candidate.enrichment || candidate.claim || onApply) ? <button type="button" disabled={Boolean(busy) || (editingClaim?.key === candidate.key && !editingClaim.proposition.trim())} onClick={() => void adopt(candidate, editingClaim?.key === candidate.key ? editingClaim.proposition.trim() : undefined)}>{busy === `adopt:${candidate.key}` ? <LoaderCircle className="spin" size={13} /> : <Check size={13} />}{editingClaim?.key === candidate.key ? "采用修改内容" : `采用${label}`}</button> : null}
          {candidate.claim ? <button type="button" disabled={Boolean(busy)} onClick={() => setEditingClaim(editingClaim?.key === candidate.key ? null : { key: candidate.key, proposition: candidate.label })}>{editingClaim?.key === candidate.key ? "取消修改" : "修改后采用"}</button> : null}
          {candidate.enrichment || candidate.claim ? <button type="button" disabled={Boolean(busy)} onClick={() => void reject(candidate)}>{busy === `reject:${candidate.key}` ? <LoaderCircle className="spin" size={13} /> : <X size={13} />}不是此项</button> : null}
        </footer>
      </article>)}
      {!loading && !visible.length ? <p>{message || "暂时没有合适建议，可以继续手工编辑。"}</p> : null}
      {!loading && moreCount ? <button type="button" className="field-assistant-more" aria-expanded={showMore} onClick={() => setShowMore((current) => !current)}>{showMore ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{showMore ? "收起更多候选" : `更多候选（${moreCount}）`}</button> : null}
      {message && visible.length ? <p role="status" aria-live="polite" className="field-assistant-message">{message}</p> : null}
    </section> : null}
  </div>;
}
