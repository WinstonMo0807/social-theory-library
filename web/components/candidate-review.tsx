"use client";

import { Filter, LoaderCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import {
  buildCandidateActionBody,
  candidateEditableValue, candidateRejectionAction, candidateRejectionReasons, parseCandidateEditableValue, resolveCandidateActionDescriptors,
  type CandidateActionDescriptor,
  type CandidateActionSource,
} from "./admin/research/candidate-action-contract";
import { WorkflowInspector } from "./admin/inspector/workflow-inspector";
import { SelectedWorkPreview } from "./admin/preview/selected-work-preview";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { EvidenceEnvelopeCard } from "./admin/research/evidence-envelope-card";

type Evidence = {
  id: string;
  source_title?: string;
  canonical_url?: string;
  supporting_text?: string;
  evidence_text?: string;
  work_title?: string;
  asset?: string;
  page_number?: number | null;
  printed_page_label?: string;
  is_current?: boolean;
  locator?: Record<string, unknown>;
  quality?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  reader_url?: string;
  pdf_url?: string;
};

type Candidate = {
  id: string;
  review_kind: "field_enrichment" | "query_lexicon" | "new_authority" | "metadata" | "theory";
  field_name?: string;
  candidate_type?: string;
  target_label?: string;
  target_entity_type?: string;
  target_entity_id?: string | null;
  proposed_term?: string;
  proposed_value?: unknown;
  current_value?: unknown;
  language?: string;
  candidate_kind?: string;
  confidence: number;
  confidence_factors?: Record<string, unknown>;
  conflicts?: unknown[];
  identity_status?: string;
  linking_status?: string;
  status: string;
  evidence_count: number;
  independent_source_count: number;
  evidence_records?: Evidence[];
  review_action?: string;
  upload_item_id?: string | null;
  possible_matches?: Array<{ entity_type?: string; entity_id?: string; label?: string; canonical_label?: string }>;
  work_id?: string | null;
  edition_id?: string | null;
  workbench_url?: string;
  target_type?: string;
  target_id?: string;
  action_descriptors?: unknown;
  actions?: unknown;
  available_actions?: string[];
  decision_url?: string;
};

type ReviewEnvelope = {
  results: Candidate[];
  counts: Record<string, number>;
  returned_count?: number;
  truncated?: boolean;
};

function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") return "未填写";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value, null, 2);
}

function kindLabel(kind: Candidate["review_kind"]) {
  return ({
    query_lexicon: "PDF 词典候选",
    field_enrichment: "字段补全候选",
    new_authority: "新权威对象候选",
    metadata: "元数据候选",
    theory: "理论 / 关系审核",
  } as Record<Candidate["review_kind"], string>)[kind];
}

function statusLabel(value: string) {
  return ({ pending: "待审核", accepted: "已接受", rejected: "已拒绝", superseded: "已替代", draft_created: "已创建草稿", matched: "已匹配" } as Record<string, string>)[value] ?? value;
}

function decisionCandidate(candidate: Candidate): Candidate & CandidateActionSource {
  if (candidate.action_descriptors || (Array.isArray(candidate.actions) && candidate.actions.some((row) => row && typeof row === "object"))) {
    return candidate;
  }
  const availableActions = candidate.available_actions ?? (
    candidate.status !== "pending"
      ? []
      : candidate.review_kind === "new_authority"
        ? ["match_existing", "create_draft", "reject"]
        : ["field_enrichment", "query_lexicon"].includes(candidate.review_kind)
          ? ["accept", "reject"]
          : []
  );
  const decisionUrl = candidate.decision_url || (
    ["field_enrichment", "query_lexicon", "new_authority"].includes(candidate.review_kind)
      ? `/catalog/admin/candidate-review/${candidate.review_kind}/${candidate.id}/decision/`
      : ""
  );
  return { ...candidate, available_actions: availableActions, decision_url: decisionUrl };
}

export function CandidateReview() {
  const [status, setStatus] = useState("pending");
  const [kind, setKind] = useState("all");
  const [data, setData] = useState<ReviewEnvelope | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [selectedKey, setSelectedKey] = useState("");
  const [selectionDirty, setSelectionDirty] = useState(false);
  const loadRevision = useRef(0);
  const actionPending = useRef(false);

  const load = useCallback(async () => {
    const revision = ++loadRevision.current;
    setLoading(true);
    setData(null);
    setMessage("");
    try {
      const credential = getServerSessionCredential();
      const query = new URLSearchParams({ status, kind });
      const payload = await apiRequest<ReviewEnvelope>(
        `/catalog/admin/candidate-review/?${query.toString()}`,
        {},
        credential,
      );
      if (revision === loadRevision.current) setData(payload);
    } catch (reason) {
      if (revision === loadRevision.current) setMessage(reason instanceof Error ? reason.message : "候选读取失败。");
    } finally {
      if (revision === loadRevision.current) setLoading(false);
    }
  }, [kind, status]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => { window.clearTimeout(timer); loadRevision.current += 1; };
  }, [load]);

  async function decide(candidate: Candidate, descriptor: CandidateActionDescriptor, editedValue?: unknown) {
    if (actionPending.current || descriptor.disabled) return false;
    const action = descriptor.action;
    if (descriptor.source !== "descriptor" && !["field_enrichment", "query_lexicon", "new_authority"].includes(candidate.review_kind)) {
      setMessage("该条记录请从 Intake 或专用理论审核页面处理，统一列表只展示证据和入口。");
      return false;
    }
    actionPending.current = true;
    setBusy(`${candidate.id}:${action}`);
    setMessage("");
    try {
      const fallbackBody: Record<string, unknown> = { action, reason: `统一候选审核 ${action}` };
      if (action === "match_existing") {
        const match = candidate.possible_matches?.[0];
        if (!match?.entity_id) {
          setMessage("当前没有可安全选择的已有实体，请打开 Knowledge Workspace 后再决定。");
          return false;
        }
        fallbackBody.target_type = match.entity_type;
        fallbackBody.target_id = match.entity_id;
      }
      if (action === "create_draft") fallbackBody.confirm_new = true;
      const body = buildCandidateActionBody(descriptor, editedValue, fallbackBody);
      const decisionUrl = descriptor.url || candidate.decision_url || `/catalog/admin/candidate-review/${candidate.review_kind}/${candidate.id}/decision/`;
      const updated = await apiRequest<Candidate>(
        decisionUrl,
        {
          method: descriptor.method || "POST",
          body: JSON.stringify(body),
        },
        getServerSessionCredential(),
      );
      setData((current) => current ? {
        ...current,
        results: current.results.map((row) => row.id === candidate.id && row.review_kind === candidate.review_kind ? {...row, ...updated} : row),
      } : current);
      setMessage(action === "reject" ? "候选已拒绝，证据仍保留。" : "候选已按其领域规则处理，草稿不会自动发布。");
      setSelectionDirty(false);
      return true;
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "审核操作失败。");
      return false;
    } finally {
      actionPending.current = false;
      setBusy("");
    }
  }

  const selected = data?.results.find(row=>`${row.review_kind}:${row.id}`===selectedKey) || data?.results[0];
  const canSwitch = () => !busy && (!selectionDirty || window.confirm("当前处理选择尚未提交，放弃输入并切换吗？"));
  return <section className="admin-section candidate-review candidate-reference" aria-label="核对填写建议">
    <header className="admin-section-heading"><div><h1>核对填写建议</h1><span>根据原文内容与系统建议，核对确认以下信息是否正确。</span></div><button type="button" className="button secondary" disabled={loading || Boolean(busy)} onClick={()=>{if(canSwitch()){setSelectionDirty(false);void load();}}}><Filter size={15}/>重新读取</button></header>
    <details className="candidate-reference-directory" open={!selected}><summary>选择需要核对的内容（{data?.counts.total ?? "—"}）</summary><div className="admin-toolbar">
      <label>状态<select value={status} onChange={event=>{if(canSwitch()){setSelectionDirty(false);setStatus(event.target.value);}}}><option value="pending">待审核</option><option value="accepted">已接受</option><option value="rejected">已拒绝</option><option value="all">全部</option></select></label>
      <label>建议来源<select value={kind} onChange={event=>{if(canSwitch()){setSelectionDirty(false);setKind(event.target.value);}}}><option value="all">全部</option><option value="field_enrichment">字段补全</option><option value="query_lexicon">检索用语</option><option value="new_authority">新对象</option><option value="metadata">书目</option><option value="theory">理论与关系</option></select></label></div>
      <div className="candidate-reference-index">{data?.results.map(row=><button type="button" key={`${row.review_kind}:${row.id}`} aria-pressed={selected?.id===row.id && selected?.review_kind===row.review_kind} onClick={()=>{if(canSwitch()){setSelectionDirty(false);setSelectedKey(`${row.review_kind}:${row.id}`);}}}>{row.target_label || row.proposed_term || row.field_name || kindLabel(row.review_kind)}<small>{statusLabel(row.status)}</small></button>)}</div>{data?.truncated ? <p>当前为排序靠前的 {data.returned_count} 项，请缩小筛选范围。</p> : null}</details>
    {message ? <p className="form-message" role="status">{message}</p> : null}{loading ? <p role="status"><LoaderCircle size={18}/>正在读取建议…</p> : null}
    {!loading && !selected ? <p className="empty-state">当前筛选没有需要核对的建议。</p> : null}
    {selected ? <CandidateReviewWorkspace key={`${selected.review_kind}:${selected.id}`} candidate={selected} busy={Boolean(busy)} onDirty={setSelectionDirty} onDecision={decide}/> : null}
  </section>;
}

function CandidateReviewWorkspace({candidate,busy,onDirty,onDecision}: {candidate:Candidate;busy:boolean;onDirty:(dirty:boolean)=>void;onDecision:(candidate:Candidate,descriptor:CandidateActionDescriptor,value?:unknown)=>Promise<boolean>}) {
  const [step,setStep]=useState(1), [action,setAction]=useState("");
  const [edited,setEdited]=useState(()=>candidateEditableValue(candidate));
  const [reason,setReason]=useState("unsupported_content"), [detail,setDetail]=useState("");
  const [showPdf,setShowPdf]=useState(true);
  const dirty=useUnsavedForm(action ? {action,edited,reason,detail} : null,null);
  useEffect(()=>onDirty(dirty),[dirty,onDirty]);
  const descriptors=resolveCandidateActionDescriptors(decisionCandidate(candidate)).filter(row=>row.action!=="inspect");
  const choice=descriptors.find(row=>row.action===action);
  const disabled=busy || candidate.status!=="pending";
  const valid=Boolean(choice && !choice.disabled && (!choice.editable || edited.trim()) && (action!=="reject" || reason!=="other" || detail.trim()));
  const source=(candidate.evidence_records || []).filter(row=>row.is_current!==false);
  const pdf=source.find(row=>row.pdf_url);
  const edition=candidate.edition_id || (candidate.target_type==="edition" ? candidate.target_id : candidate.target_entity_type==="edition" ? candidate.target_entity_id : "");
  const fieldNames:Record<string,string>={publisher:"出版社",publication_year:"出版年份",title:"书名",original_title:"原文书名",abstract:"简介",language:"语言",isbn:"ISBN"};
  const heading=fieldNames[candidate.field_name || ""] || candidate.field_name || candidate.candidate_type || "建议内容";
  async function confirm() {
    if (!choice || !valid || disabled) return;
    const descriptor=action==="reject" ? candidateRejectionAction(choice,reason,detail) : choice;
    if (await onDecision(candidate,descriptor,choice.editable ? parseCandidateEditableValue(edited,candidate.proposed_value) : undefined)) {setAction("");setReason("unsupported_content");setDetail("");}
  }
  return <><nav className="knowledge-reference-steps" aria-label="核对步骤">{["查看建议","核对出处","确认采用"].map((label,index)=><button type="button" key={label} aria-current={step===index ? "step" : undefined} disabled={busy || (index===2&&!valid)} onClick={()=>setStep(index)}><span>{index+1}</span><strong>{label}</strong></button>)}</nav>
    <div className="candidate-reference-columns"><section className="admin-panel candidate-reference-form"><h2>{heading}<small>{statusLabel(candidate.status)}</small></h2><p>请根据右侧的出处核对内容，再选择处理方式。</p><div className="candidate-reference-values"><label>当前值<textarea readOnly value={valueText(candidate.current_value)}/></label><label>系统建议值<textarea readOnly value={valueText(candidate.proposed_value ?? candidate.proposed_term)}/></label></div>
      <fieldset disabled={disabled}><legend>处理方式</legend>{descriptors.map(row=><label className="candidate-reference-option" key={row.action}><input type="radio" name={`decision-${candidate.id}`} checked={action===row.action} disabled={row.disabled} onChange={()=>setAction(row.action)}/><span>{row.label}{row.disabledReason ? <small>{row.disabledReason}</small> : null}</span></label>)}
      {choice?.editable ? <label>修改后采用<textarea value={edited} onChange={event=>setEdited(event.target.value)}/></label> : null}{action==="reject" ? <><label>不采用理由<select value={reason} onChange={event=>setReason(event.target.value)}>{Object.entries(candidateRejectionReasons).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>补充说明<textarea value={detail} onChange={event=>setDetail(event.target.value)}/></label></> : null}</fieldset>
      {step===2 && choice ? <aside className="candidate-reference-notice"><strong>请确认：{choice.label}</strong><p>{choice.editable ? edited : action==="reject" ? candidateRejectionReasons[reason] : valueText(candidate.proposed_value ?? candidate.proposed_term)}</p><p>提交后按这条建议的实际规则处理；不会自动发布。</p></aside> : <aside className="candidate-reference-notice">核对提示：请检查原文的正式名称与版本。现有人工确认和锁定规则仍由保存接口校验。</aside>}
      <details><summary>其他信息（本次不处理）</summary><p>{candidate.target_label}</p><p>{kindLabel(candidate.review_kind)} · 证据 {candidate.evidence_count} 条</p>{candidate.conflicts?.length ? <pre>{valueText(candidate.conflicts)}</pre> : null}{candidate.confidence_factors ? <pre>{valueText(candidate.confidence_factors)}</pre> : null}</details>
      {!descriptors.length && candidate.workbench_url ? <a className="button" href={candidate.workbench_url}>回到书目工作页核对</a> : null}
      <footer><button type="button" className="button secondary" disabled={busy || step===0} onClick={()=>setStep(step-1)}>上一步</button><button type="button" className="button secondary" disabled title="当前接口不支持暂存处理选择">保存草稿</button>{step<2 ? <button type="button" className="button" disabled={disabled || (step===1&&!valid)} onClick={()=>setStep(step+1)}>下一步：{step===0 ? "核对出处" : "确认采用"} →</button> : <button type="button" className="button" disabled={disabled || !valid} onClick={()=>void confirm()}>{busy ? "正在提交…" : "确认处理"}</button>}</footer>
    </section><section className="admin-panel candidate-reference-evidence"><h2>证据与预览</h2><nav className="reference-tabs"><button type="button" aria-pressed={showPdf} onClick={()=>setShowPdf(true)}>原文证据</button><button type="button" aria-pressed={!showPdf} onClick={()=>setShowPdf(false)}>前台书目位置预览</button></nav>
      {showPdf ? <>{pdf?.pdf_url ? <WorkflowInspector key={pdf.pdf_url} selection={{kind:"pdf",title:pdf.work_title || "原文证据",pdfUrl:pdf.pdf_url}} token={getServerSessionCredential()} onClose={()=>setShowPdf(false)}/> : source.length ? source.map(row=><EvidenceEnvelopeCard key={row.id} evidence={row}/>) : <p className="empty-state">—</p>}</> : null}
      <div hidden={showPdf && !edition}><h3>前台书目位置预览</h3>{edition ? <SelectedWorkPreview editionId={edition} title={candidate.target_label}/> : <p className="empty-state">—</p>}</div>
    </section></div></>;
}
