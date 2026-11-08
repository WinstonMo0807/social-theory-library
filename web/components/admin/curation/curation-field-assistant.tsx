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
import { MaterialAssistantDialog, MaterialCandidate, useMaterialField, materialSourceHref } from "../workflow/material-assistant";
import { useAdminSession } from "@/lib/admin-session";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useCatalogCommand } from "../workflow/use-intake-command";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { MaterialEvidence } from "../workflow/material-assistant";

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
  locator?: MaterialEvidence["locator"];
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
  decision_version?: string;
};

type DecisionCommand={expected_version:string;field_name:string;source_type:"claim"|"enrichment";source_id:string;action:"accept"|"accept_with_edit"|"reject";proposition?:string;reason?:string};
type DecisionReceipt={owner_id:string;request_id:string;target_type:string;target_id:string;state:"applied"|"cancelled";action:string;field_name:string;source_id:string;next_url:string;result:Record<string,unknown>};

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
  onFillSuggestion?: (id: string, value: unknown, label: string) => boolean | Promise<boolean>;
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
  scopeId,
  affectedFields,
}: Props) {
  const user=useAdminSession(),owner=user?String(user.id):"";
  const popoverId = useId();
  const normalizedQuery = useMemo(() => query.normalize("NFKC").trim(), [query]);
  const objectKey = JSON.stringify([owner,targetType || authorityType, targetId || scopeId || "new", fieldName || label]);
  const objectType=targetType||(authorityType==="concept"||authorityType==="theory_tradition"?"knowledge_node":authorityType);
  const field=fieldName||"identity";
  const expected=useRef<{action:string;sourceId:string}|null>(null);
  const command=useCatalogCommand<DecisionCommand,DecisionReceipt>(owner,`/catalog/admin/curation/${objectType}/${targetId}/field-decisions/`,`stl-curation-decision:${objectKey}`,value=>value.target_type===objectType&&value.target_id===targetId&&(value.state==="cancelled"||value.field_name===field&&(!expected.current||value.action===expected.current.action&&value.source_id===expected.current.sourceId)));
  const contextKey = JSON.stringify([owner,targetType, targetId, fieldName, normalizedQuery, currentValue, formContext]);
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
  const [stopping,setStopping]=useContextState(objectKey,false);
  const [review, setReview] = useContextState<AssistantCandidate | null>(objectKey, null);
  const [editingClaim, setEditingClaim] = useContextState<{ key: string; proposition: string } | null>(contextKey, null);
  const requestRef = useRef<AbortController | null>(null);
  const objectRef = useRef(objectKey);
  const contextRef=useRef(contextKey);
  const reviewField=useMaterialField(label,()=>setOpen(true));
  const lookupRef = useRef<(external?: boolean) => Promise<void>>(async () => {});
  useLayoutEffect(() => { objectRef.current = objectKey; contextRef.current=contextKey; lookupRef.current = lookup; });
  useEffect(()=>{expected.current=null;},[objectKey]);
  useUnsavedForm(Boolean(command.recovery),false);
  const blocked=Boolean(busy)||command.busy||Boolean(command.recovery)||!command.ready;
  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => void lookupRef.current(false), 300);
    return () => { clearTimeout(timer); requestRef.current?.abort(); };
  }, [contextKey, open]);

  async function ownerRequest<T>(path:string,options:RequestInit={},credential:string|null=getServerSessionCredential()){const headers=new Headers(options.headers);headers.set("X-Editor-Owner",owner);return withPrivateOwner(owner,()=>apiRequest<T>(path,{...options,headers,cache:"no-store"},credential,false),options.signal||undefined);}
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
      const result = await ownerRequest<{ results: AssistantCandidate[]; more_results?: AssistantCandidate[]; message?: string; can_lookup_external?: boolean; decision_version?:string }>(
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
      setResults([...(result.results || []), ...(result.more_results || [])].map(row=>({...row,decision_version:result.decision_version})));
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

  async function choose(candidate: AssistantCandidate, confirmed = false) {
    if(blocked)return;
    if (candidate.enrichment && onFillSuggestion && !candidate.claim) {
      if (candidate.conflicts.length && !confirmed) { setReview(candidate); return; }
      const filled = await onFillSuggestion(candidate.enrichment.id, candidate.enrichment.proposed_value, candidate.label);
      setReview(null);
      setOutcome(filled ? `已填入${label}，尚未保存。请核对后点击本页保存；可在表单中修改或撤销。` : "表单没有变化。已有内容不会重复添加；取消替换时也会保留当前填写。");
      reviewField.mark("已填入，待保存");
      return;
    }
    if (!candidate.enrichment && !candidate.claim && onApply) {
      if (candidate.conflicts.length && !confirmed) { setReview(candidate); return; }
      // Filling a field is local. Never save the old form or refresh it away.
      const filled = onApply(candidate.label, candidate.authority);
      setReview(null);
      setOutcome(filled === false ? "表单已有这项内容，没有重复填写或保存。" : `已填入${(affectedFields || [label]).join("、")}。这一步只修改了表单，请核对后保存本页；没有合并人物或修改公开页面。`);
      reviewField.mark("已填入，待保存");
      return;
    }
    setReview(candidate);
  }

  async function decide(candidate:AssistantCandidate,action:DecisionCommand["action"],reason="",proposition=""){
    if(blocked||busyRef.current)return;
    busyRef.current=true;
    const scope=objectKey,context=contextKey;
    setBusy(`${action}:${candidate.key}`);setMessage("");
    let saved=false;
    try{
      if(action!=="reject"){
        if(hasUnsavedChanges||reviewField.dirty)throw Error("请先保存本页填写，再单独保存这项关联。不会替你自动保存整页。");
        if(beforeAction&&!await beforeAction())throw Error("本页仍有未保存填写，请先显式保存。");
      }
      if(scope!==objectRef.current||context!==contextRef.current)return;
      const source=candidate.claim||candidate.enrichment;
      if(!targetId||!source||!candidate.decision_version)throw Error("尚未取得这项建议的保存版本，请重新读取候选。");
      expected.current={action,sourceId:source.id};
      const result=await command.send({action,field_name:field,source_type:candidate.claim?"claim":"enrichment",source_id:source.id,expected_version:candidate.decision_version,reason,proposition});
      if(!result)return;
      saved=result.state==="applied";
      if(scope!==objectRef.current)return;
      if(!saved){setOutcome("尚未执行的操作已取消，请刷新建议。");return;}
      reviewField.mark(action==="reject"?"已记录忽略":"已保存采用决定");
      setReview(null);setEditingClaim(null);
      setOutcome(action==="reject"?`已记录不采用：${reason}。原有资料未改变。`:`已保存${label}建议。尚未正式发布，请在本页核对草稿与公开预览。`);
      setResults(current=>current.filter(row=>row.key!==candidate.key));
      if(action!=="reject"){
        if(context!==contextRef.current){setRefreshFailed(true);setOutcome("决定已保存。等待期间填写已经变化，请先保留当前输入再读取结果，不会用旧响应替换新填写。");return;}
        onApply?.(candidate.enrichment?.proposed_value??candidate.label);
        await onAccepted?.();
        setRefreshFailed(false);setOpen(false);
      }
    }catch(error){
      if(scope===objectRef.current){const detail=error instanceof Error?error.message:"请稍后重试。";setMessage(detail);setRefreshFailed(saved);setOutcome(saved?`决定已经保存，页面尚未刷新。${detail} 请重新读取，不要重复保存。`:`没有完成保存。${detail}`);}
    }finally{busyRef.current=false;if(scope===objectRef.current)setBusy("");}
  }
  function adopt(candidate:AssistantCandidate,editedProposition?:string){return decide(candidate,editedProposition===undefined?"accept":"accept_with_edit",`在${label}字段采用建议`,editedProposition||"");}
  function reject(candidate:AssistantCandidate,reason:string){return decide(candidate,"reject",reason);}
  async function recover(cancel=false,retry=false){
    const scope=objectKey;
    const result=retry?await command.send():await command.lookup(cancel);
    if(!result||scope!==objectRef.current)return;
    expected.current=null;setStopping(false);setReview(null);setResults([]);
    setOutcome(result.state==="cancelled"?"已取消尚未执行的操作。已保存内容保留。":"已查看处理结果，没有重复保存。请核对当前资料，候选不会自动填入后来修改的表单。");
    if(result.state==="applied"&&result.action!=="reject")setRefreshFailed(true);
    await lookup(false);
  }
  const recoveryNotice=<>{command.error?<p role="alert">{command.error}</p>:null}{command.recovery?<section className="field-assistant-message"><p>{label}有一项尚待核对的决定。请查询原请求，或停止尚未执行的请求后继续。</p><button type="button" disabled={command.busy} onClick={()=>void recover()}>查看处理结果</button>{command.canRetry?<button type="button" disabled={command.busy} onClick={()=>void recover(false,true)}>重试该操作</button>:null}<button type="button" disabled={command.busy} onClick={()=>setStopping(true)}>停止尚未执行的请求</button></section>:null}</>;

  const visible = showMore ? results : results.slice(0, 3);
  const moreCount = Math.max(0, results.length - 3);

  return <div className="field-assistant-control curation-field-assistant">
    <button type="button" className="field-assistant-trigger" aria-haspopup="dialog" aria-expanded={open} aria-controls={popoverId} disabled={blocked} onClick={() => setOpen(true)}>
      {loading ? <LoaderCircle className="spin" size={13} /> : <Search size={13} />}{lookupLabel}
    </button>
    {!open?recoveryNotice:null}
    {outcome ? <p role="status" aria-live="polite" className="curation-assistant-outcome">{outcome}</p> : null}
    {refreshFailed ? <button type="button" disabled={blocked} onClick={async () => {
      if (busyRef.current||blocked) return;
      busyRef.current = true;
      setBusy("reload");
      try { if(hasUnsavedChanges||reviewField.dirty||beforeAction&&!await beforeAction())throw Error("请先保留本页未保存的填写，再读取已保存结果。"); await onAccepted?.(); setRefreshFailed(false); setOutcome(`${label}已保存，页面结果已重新读取。尚未正式发布。`); }
      catch (reason) { setOutcome(reason instanceof Error ? reason.message : "页面读取失败，请稍后重试。"); }
      finally { busyRef.current = false; setBusy(""); }
    }}>重新读取保存结果</button> : null}
    {open ? <MaterialAssistantDialog currentValue={typeof currentValue==="string"||typeof currentValue==="number"?String(currentValue):Array.isArray(currentValue)?currentValue.filter(row=>typeof row==="string").join("、")||"已填写关联条目":query||""} refresh={()=>void lookup(false)} fieldId={reviewField.id} fieldLabel={label} sources={visible.map(row=>({id:row.key,label:row.label,evidence:row.evidence}))} open id={popoverId} className="field-assistant-dialog field-assistant-popover" aria-label={`${label}建议`} aria-busy={loading||Boolean(busy)||command.busy} onRequestClose={() => { if (!busy&&!command.busy) { setReview(null); setOpen(false); } }}>
      <header><strong>{label}建议</strong><button type="button" disabled={blocked} aria-label={`关闭${label}建议`} onClick={() => { setReview(null); setOpen(false); }}><X size={14} /></button></header>
      {recoveryNotice}
      {outcome ? <p role="status">{outcome}</p> : null}
      {review ? <section className="curation-assistant-review" aria-label={`核对${label}保存范围`}>
        <h3>核对{label}</h3>
        <p>{review.label}</p>
        <p>{review.summary}</p>
        {editingClaim?.key === review.key ? <label>修改后的{label}<textarea rows={5} value={editingClaim.proposition} disabled={blocked} onChange={(event) => setEditingClaim({ key: review.key, proposition: event.target.value })} /></label> : null}
        <p>{(!review.enrichment && !review.claim) || (review.enrichment && onFillSuggestion) ? `只填入${(affectedFields || [label]).join("、")}，不保存、不合并人物；其他填写保持不变。` : "此操作只保存当前建议及它的关联，不保存本页其他填写。已有未保存内容时，请先用本页保存按钮保存。正式发布前不会替换公开页面。"}</p>
        {review.conflicts.length ? <p className="field-assistant-conflict">请先核对冲突：{review.conflicts.join("；")}。不确定时可返回继续编辑。</p> : null}
        <button type="button" disabled={blocked || (editingClaim?.key === review.key && !editingClaim.proposition.trim())} onClick={() => {
          if ((!review.enrichment && !review.claim) || (review.enrichment && onFillSuggestion)) choose(review, true);
          else void adopt(review, editingClaim?.key === review.key ? editingClaim.proposition.trim() : undefined);
        }}>{busy ? "正在保存…" : (!review.enrichment && !review.claim) || (review.enrichment && onFillSuggestion) ? `核对过了，填入${label}` : `确认保存${label}`}</button>
        <button type="button" disabled={blocked} onClick={() => setReview(null)}>返回查看建议</button>
        {message ? <p role="alert">{message}</p> : null}
      </section> : <>
      <p>先查看馆内记录和已有依据，不会保存或改变你的填写。</p>
      {externalAllowed === false ? <p>当前账户没有外部查找权限，仍可核对已有建议或手工填写。</p> : null}
      <small>这里核对馆内记录及已有来源。未启用的来源会说明原因，不会生成示例建议。</small>
      {loading ? <p><LoaderCircle className="spin" size={14} />正在查找馆内记录和可核对资料</p> : null}
      {!loading && visible.map((candidate) => <MaterialCandidate key={candidate.key} id={candidate.key} label={candidate.label}>
        <div><strong>{candidate.label}</strong><span>{candidate.statusLabel}</span></div>
        {candidate.secondary ? <small>{candidate.secondary}</small> : null}
        <p>{candidate.summary}</p>
        {candidate.conflicts.length ? <p className="field-assistant-conflict">存在冲突，请先核对。{candidate.conflicts.join("；")}</p> : null}
        <details data-disclosure="collection"><summary>查看依据</summary><ul>{candidate.evidence.map((evidence, index) => <li key={`${candidate.key}:${index}`}><b>{evidence.category}</b> {evidence.summary}{materialSourceHref(evidence.url||evidence.locator?.url) ? <> <a href={materialSourceHref(evidence.url||evidence.locator?.url)} target="_blank" rel="noreferrer">查看资料<ExternalLink size={11} /></a></> : null}</li>)}</ul></details>
        {editingClaim?.key === candidate.key ? <label><span>修改后的{label}</span><textarea rows={4} value={editingClaim.proposition} disabled={blocked} onChange={(event) => setEditingClaim({ key: candidate.key, proposition: event.target.value })} /></label> : null}
        <footer className="curation-field-assistant-actions material-candidate-actions">
          {(candidate.enrichment || candidate.claim || onApply) ? <button type="button" disabled={blocked || (editingClaim?.key === candidate.key && !editingClaim.proposition.trim())} onClick={() => choose(candidate)}><Check size={13} />{candidate.claim || (candidate.enrichment && !onFillSuggestion) ? `核对并保存${label}` : `填入${label}`}</button> : null}
          {candidate.claim ? <button type="button" disabled={blocked} onClick={() => setEditingClaim(editingClaim?.key === candidate.key ? null : { key: candidate.key, proposition: candidate.label })}>{editingClaim?.key === candidate.key ? "取消修改" : "修改后采用"}</button> : null}
          {candidate.enrichment || candidate.claim ? <CandidateDecisionBar candidate={{ id: candidate.key, actions: [{ action: "reject", label: "不采用" }] }} showInspect={false} disabled={blocked} busyAction={busy === `reject:${candidate.key}` ? "reject" : ""} onAction={(action) => reject(candidate, String(action.payload.reason))} /> : null}
        </footer>
      </MaterialCandidate>)}
      {!loading && !visible.length ? <p>{message || "暂时没有合适建议，可以继续手工编辑。"}</p> : null}
      {!loading && moreCount ? <button type="button" className="field-assistant-more" aria-expanded={showMore} onClick={() => setShowMore((current) => !current)}>{showMore ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{showMore ? "收起更多候选" : `更多候选（${moreCount}）`}</button> : null}
      {message && visible.length ? <p role="status" aria-live="polite" className="field-assistant-message">{message}</p> : null}
      <button type="button" disabled={blocked} onClick={() => { setOpen(false); setOutcome("本次暂不处理建议，填写和保存记录均未改变。"); }}>暂不处理，继续填写</button>
      </>}
    </MaterialAssistantDialog> : null}
    <ConfirmDialog open={stopping} title="取消尚未执行的操作？" description="已执行的请求会返回原结果；尚未执行的请求将被停止。不会撤销已经保存的内容，也不会重新采用候选。" confirmLabel="核对并停止" pending={command.busy} onCancel={()=>setStopping(false)} onConfirm={()=>recover(true)}/>
  </div>;
}
