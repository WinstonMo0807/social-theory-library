"use client";

import { CandidateDecisionBar } from "../research/candidate-decision-bar";

import {
  Check,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  LoaderCircle,
  Search,
  X,
} from "lucide-react";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useContextState } from "@/lib/use-context-state";
import { Dialog } from "@/components/ui/dialog";

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
  onApply?: (value: unknown, authority?: CurationAuthoritySuggestion) => boolean | void;
  onFillSuggestion?: (id: string, value: unknown, label: string) => boolean;
  onAccepted?: () => void | Promise<void>;
  beforeAction?: () => Promise<boolean>;
  hasUnsavedChanges?: boolean;
  savedVersion?: string;
  scopeId?: string;
  affectedFields?: string[];
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
  onFillSuggestion,
  onAccepted,
  beforeAction,
  hasUnsavedChanges = false,
  savedVersion,
  scopeId,
  affectedFields,
}: Props) {
  const popoverId = useId();
  const normalizedQuery = useMemo(() => query.normalize("NFKC").trim(), [query]);
  const objectKey = JSON.stringify([targetType || authorityType, targetId || scopeId || "new", fieldName || label]);
  const contextKey = JSON.stringify([targetType, targetId, fieldName, normalizedQuery, currentValue, formContext]);
  const [open, setOpen] = useContextState(objectKey, false);
  const [loading, setLoading] = useContextState(contextKey, false);
  const [busy, setBusy] = useState("");
  const busyRef = useRef(false);
  const [results, setResults] = useContextState<AssistantCandidate[]>(contextKey, []);
  const [externalAllowed, setExternalAllowed] = useContextState<boolean | null>(objectKey, null);
  const [showMore, setShowMore] = useState(false);
  const [message, setMessage] = useContextState(contextKey, "");
  const [outcome, setOutcome] = useContextState(objectKey, "");
  const [refreshFailed, setRefreshFailed] = useContextState(objectKey, false);
  const [uncertainSave, setUncertainSave] = useContextState(objectKey, false);
  const [review, setReview] = useContextState<AssistantCandidate | null>(objectKey, null);
  const [editingClaim, setEditingClaim] = useContextState<{ key: string; proposition: string } | null>(contextKey, null);
  const requestRef = useRef<AbortController | null>(null);
  const objectRef = useRef(objectKey);
  const lookupRef = useRef<(external?: boolean) => Promise<void>>(async () => {});
  useLayoutEffect(() => { objectRef.current = objectKey; lookupRef.current = lookup; });
  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => void lookupRef.current(false), 300);
    return () => { clearTimeout(timer); requestRef.current?.abort(); };
  }, [contextKey, open]);

  async function lookup(external = false) {
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
    const timeout = setTimeout(() => request.abort(), 30_000);
    try {
      const result = await apiRequest<{ results: AssistantCandidate[]; more_results?: AssistantCandidate[]; message?: string; can_lookup_external?: boolean }>(
        "/catalog/admin/field-assistant/lookup/",
        { method: "POST", signal: request.signal, body: JSON.stringify({
          scope: "curation", object_type: objectType, object_id: targetId || null,
          field_name: fieldName || "identity", query: normalizedQuery,
          authority_type: authorityType || "", current_value: currentValue ?? null, form_context: formContext,
          refresh: external, allow_external: external,
        }) }, getServerSessionCredential(),
      );
      if (request.signal.aborted) return;
      setExternalAllowed(result.can_lookup_external ?? null);
      setResults([...(result.results || []), ...(result.more_results || [])]);
      setMessage(result.message || (!result.results.length ? "暂时没有合适建议，可以继续手工编辑。" : ""));
    } catch (reason) {
      if (requestRef.current === request) setMessage(request.signal.aborted
        ? "建议读取超时，你的填写没有改变。可以重新读取已有结果；不要连续发起外部查找。"
        : reason instanceof Error ? reason.message : "建议服务暂时不可用，可以继续手工编辑。");
    } finally {
      clearTimeout(timeout);
      if (requestRef.current === request) setLoading(false);
    }
  }

  function choose(candidate: AssistantCandidate, confirmed = false) {
    if (candidate.enrichment && onFillSuggestion && !candidate.claim) {
      if (candidate.conflicts.length && !confirmed) { setReview(candidate); return; }
      const filled = onFillSuggestion(candidate.enrichment.id, candidate.enrichment.proposed_value, candidate.label);
      setReview(null);
      setOutcome(filled ? `已填入${label}，尚未保存。请核对后点击本页保存；可在表单中修改或撤销。` : "表单没有变化。已有内容不会重复添加；取消替换时也会保留当前填写。");
      setOpen(false);
      return;
    }
    if (!candidate.enrichment && !candidate.claim && onApply) {
      if (candidate.conflicts.length && !confirmed) { setReview(candidate); return; }
      // Filling a field is local. Never save the old form or refresh it away.
      const filled = onApply(candidate.label, candidate.authority);
      setReview(null);
      setOutcome(filled === false ? "表单已有这项内容，没有重复填写或保存。" : `已填入${(affectedFields || [label]).join("、")}。这一步只修改了表单，请核对后保存本页；没有合并人物或修改公开页面。`);
      setOpen(false);
      return;
    }
    setReview(candidate);
  }

  async function adopt(candidate: AssistantCandidate, editedProposition?: string) {
    if (busyRef.current) return;
    busyRef.current = true;
    const scope = objectKey;
    setBusy(`adopt:${candidate.key}`);
    setMessage("");
    let saved = false;
    const writeController = new AbortController();
    const writeTimeout = setTimeout(() => writeController.abort(), 25000);
    try {
      if (hasUnsavedChanges) throw new Error("请先保存本页填写，再单独保存这项关联。不会替你自动保存整页。");
      if (beforeAction && !await beforeAction()) throw new Error("本页仍有未保存填写，请先显式保存，再处理这项建议。");
      if (scope !== objectRef.current) return;
      if (candidate.claim) {
        await apiRequest(candidate.claim.decision_url, {
          method: "POST",
          signal: writeController.signal,
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
            signal: writeController.signal,
            body: JSON.stringify({ action: "accept", reason: `在${label}字段采用建议`, ...(savedVersion ? { expected_edit_version: savedVersion } : {}) }),
          },
          getServerSessionCredential(),
        );
      }
      saved = true;
      setUncertainSave(false);
      if (scope !== objectRef.current) return;
      onApply?.(candidate.enrichment?.proposed_value ?? candidate.label);
      setReview(null);
      setOutcome(`已保存${label}建议。尚未正式发布，请在本页核对填写及公开预览。`);
      await onAccepted?.();
      setRefreshFailed(false);
      setResults((current) => current.filter((row) => row.key !== candidate.key));
      setEditingClaim(null);
      setOpen(false);
    } catch (reason) {
      if (scope !== objectRef.current) return;
      const detail = reason instanceof Error ? reason.message : "请稍后重试。";
      const uncertain = !saved && writeController.signal.aborted;
      setUncertainSave(uncertain);
      setRefreshFailed(saved || uncertain);
      setOutcome(saved ? `${label}已保存，但页面结果尚未读取成功。${detail} 请重新读取，不必重复保存建议。` : uncertain ? "保存响应超时，结果尚未确认。请先重新读取当前资料，不要连续重复提交。" : `没有完成保存。${detail}`);
      if (!saved) setMessage(detail);
    } finally {
      clearTimeout(writeTimeout);
      busyRef.current = false;
      setBusy("");
    }
  }

  async function reject(candidate: AssistantCandidate, reason: string) {
    if ((!candidate.enrichment && !candidate.claim) || busyRef.current) return;
    busyRef.current = true;
    setBusy(`reject:${candidate.key}`);
    setMessage("");
    try {
      await apiRequest(
        candidate.claim?.decision_url || `/catalog/admin/field-enrichment/candidates/${candidate.enrichment?.id}/decision/`,
        {
          method: "POST",
            body: JSON.stringify({ action: "reject", reason, ...(candidate.claim ? { kind: candidate.claim.kind } : {}) }),
        },
        getServerSessionCredential(),
      );
      setResults((current) => current.filter((row) => row.key !== candidate.key));
      setOutcome(`已记录不采用：${reason}。原有资料未改变。`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "未能记录本次决定，请稍后重试。");
    } finally {
      busyRef.current = false;
      setBusy("");
    }
  }

  const visible = showMore ? results : results.slice(0, 3);
  const moreCount = Math.max(0, results.length - 3);

  return <div className="field-assistant-control curation-field-assistant">
    <button type="button" className="field-assistant-trigger" aria-haspopup="dialog" aria-expanded={open} aria-controls={popoverId} disabled={Boolean(busy)} onClick={() => setOpen(true)}>
      {loading ? <LoaderCircle className="spin" size={13} /> : <Search size={13} />}{lookupLabel}
    </button>
    {outcome ? <p role="status" aria-live="polite" className="curation-assistant-outcome">{outcome}</p> : null}
    {refreshFailed ? <button type="button" disabled={Boolean(busy)} onClick={async () => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy("reload");
      try { await onAccepted?.(); setRefreshFailed(false); setOutcome(uncertainSave ? "已重新读取当前资料。请查看该建议是否已保存；没有出现时可重新打开建议处理。" : `${label}已保存，页面结果已重新读取。尚未正式发布。`); }
      catch (reason) { setOutcome(reason instanceof Error ? reason.message : "页面读取失败，请稍后重试。"); }
      finally { busyRef.current = false; setBusy(""); }
    }}>重新读取保存结果</button> : null}
    {open ? <Dialog open id={popoverId} className="field-assistant-dialog field-assistant-popover" aria-label={`${label}建议`} aria-busy={loading} onRequestClose={() => { if (!busy) { setReview(null); setOpen(false); } }}>
      <header><strong>{label}建议</strong><button type="button" disabled={Boolean(busy)} aria-label={`关闭${label}建议`} onClick={() => { setReview(null); setOpen(false); }}><X size={14} /></button></header>
      {outcome ? <p role="status">{outcome}</p> : null}
      {review ? <section className="curation-assistant-review" aria-label={`核对${label}保存范围`}>
        <h3>核对{label}</h3>
        <p>{review.label}</p>
        <p>{review.summary}</p>
        {editingClaim?.key === review.key ? <label>修改后的{label}<textarea rows={5} value={editingClaim.proposition} disabled={Boolean(busy)} onChange={(event) => setEditingClaim({ key: review.key, proposition: event.target.value })} /></label> : null}
        <p>{(!review.enrichment && !review.claim) || (review.enrichment && onFillSuggestion) ? `只填入${(affectedFields || [label]).join("、")}，不保存、不合并人物；其他填写保持不变。` : "此操作只保存当前建议及它的关联，不保存本页其他填写。已有未保存内容时，请先用本页保存按钮保存。正式发布前不会替换公开页面。"}</p>
        {review.conflicts.length ? <p className="field-assistant-conflict">请先核对冲突：{review.conflicts.join("；")}。不确定时可返回继续编辑。</p> : null}
        <button type="button" disabled={Boolean(busy) || (editingClaim?.key === review.key && !editingClaim.proposition.trim())} onClick={() => {
          if ((!review.enrichment && !review.claim) || (review.enrichment && onFillSuggestion)) choose(review, true);
          else void adopt(review, editingClaim?.key === review.key ? editingClaim.proposition.trim() : undefined);
        }}>{busy ? "正在保存…" : (!review.enrichment && !review.claim) || (review.enrichment && onFillSuggestion) ? `核对过了，填入${label}` : `确认保存${label}`}</button>
        <button type="button" disabled={Boolean(busy)} onClick={() => setReview(null)}>返回查看建议</button>
        {message ? <p role="alert">{message}</p> : null}
      </section> : <>
      <p>先查看馆内记录和已有依据，不会保存或改变你的填写。</p>
      <button type="button" className="button secondary" disabled={loading || Boolean(busy) || externalAllowed === false} onClick={() => void lookup(true)}>查找新的{label}建议</button>
      {externalAllowed === false ? <p>当前账户没有外部查找权限，仍可核对已有建议或手工填写。</p> : null}
      <small>新的查找可能使用外部来源并产生费用。修改表单只重新核对已有结果，不会自动收费检索。</small>
      {loading ? <p><LoaderCircle className="spin" size={14} />正在查找馆内记录和可核对资料</p> : null}
      {!loading && visible.map((candidate) => <article key={candidate.key}>
        <div><strong>{candidate.label}</strong><span>{candidate.statusLabel}</span></div>
        {candidate.secondary ? <small>{candidate.secondary}</small> : null}
        <p>{candidate.summary}</p>
        {candidate.conflicts.length ? <p className="field-assistant-conflict">存在冲突，请先核对。{candidate.conflicts.join("；")}</p> : null}
        <details><summary>查看依据</summary><ul>{candidate.evidence.map((evidence, index) => <li key={`${candidate.key}:${index}`}><b>{evidence.category}</b> {evidence.summary}{evidence.url ? <> <a href={evidence.url} target="_blank" rel="noreferrer">查看资料<ExternalLink size={11} /></a></> : null}</li>)}</ul></details>
        {editingClaim?.key === candidate.key ? <label><span>修改后的{label}</span><textarea rows={4} value={editingClaim.proposition} disabled={Boolean(busy)} onChange={(event) => setEditingClaim({ key: candidate.key, proposition: event.target.value })} /></label> : null}
        <footer className="curation-field-assistant-actions">
          {(candidate.enrichment || candidate.claim || onApply) ? <button type="button" disabled={Boolean(busy) || (editingClaim?.key === candidate.key && !editingClaim.proposition.trim())} onClick={() => choose(candidate)}><Check size={13} />{candidate.claim || (candidate.enrichment && !onFillSuggestion) ? `核对并保存${label}` : `填入${label}`}</button> : null}
          {candidate.claim ? <button type="button" disabled={Boolean(busy)} onClick={() => setEditingClaim(editingClaim?.key === candidate.key ? null : { key: candidate.key, proposition: candidate.label })}>{editingClaim?.key === candidate.key ? "取消修改" : "修改后采用"}</button> : null}
          {candidate.enrichment || candidate.claim ? <CandidateDecisionBar candidate={{ id: candidate.key, actions: [{ action: "reject", label: "不采用" }] }} showInspect={false} disabled={Boolean(busy)} busyAction={busy === `reject:${candidate.key}` ? "reject" : ""} onAction={(action) => reject(candidate, String(action.payload.reason))} /> : null}
        </footer>
      </article>)}
      {!loading && !visible.length ? <p>{message || "暂时没有合适建议，可以继续手工编辑。"}</p> : null}
      {!loading && moreCount ? <button type="button" className="field-assistant-more" aria-expanded={showMore} onClick={() => setShowMore((current) => !current)}>{showMore ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{showMore ? "收起更多候选" : `更多候选（${moreCount}）`}</button> : null}
      {message && visible.length ? <p role="status" aria-live="polite" className="field-assistant-message">{message}</p> : null}
      <button type="button" disabled={Boolean(busy)} onClick={() => { setOpen(false); setOutcome("本次暂不处理建议，填写和保存记录均未改变。"); }}>暂不处理，继续填写</button>
      </>}
    </Dialog> : null}
  </div>;
}
