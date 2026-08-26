"use client";

import { Filter, LoaderCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import {
  buildCandidateActionBody,
  type CandidateActionDescriptor,
  type CandidateActionSource,
} from "./admin/research/candidate-action-contract";
import { CandidateDecisionBar } from "./admin/research/candidate-decision-bar";
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

function entityLabel(value?: string) {
  return ({ person: "学者", work: "作品", edition: "版本", discipline: "学科", subdiscipline: "子学科", knowledge_node: "理论节点", topic: "主题", reading_path: "阅读路径" } as Record<string, string>)[value || ""] ?? (value || "未解析");
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

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const credential = getServerSessionCredential();
      const query = new URLSearchParams({ status, kind });
      const payload = await apiRequest<ReviewEnvelope>(
        `/catalog/admin/candidate-review/?${query.toString()}`,
        {},
        credential,
      );
      setData(payload);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "候选读取失败。");
    } finally {
      setLoading(false);
    }
  }, [kind, status]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function decide(candidate: Candidate, descriptor: CandidateActionDescriptor, editedValue?: unknown) {
    const action = descriptor.action;
    if (descriptor.source !== "descriptor" && !["field_enrichment", "query_lexicon", "new_authority"].includes(candidate.review_kind)) {
      setMessage("该条记录请从 Intake 或专用理论审核页面处理，统一列表只展示证据和入口。");
      return;
    }
    setBusy(`${candidate.id}:${action}`);
    setMessage("");
    try {
      const fallbackBody: Record<string, unknown> = { action, reason: `统一候选审核 ${action}` };
      if (action === "match_existing") {
        const match = candidate.possible_matches?.[0];
        if (!match?.entity_id) {
          setMessage("当前没有可安全选择的已有实体，请打开 Knowledge Workspace 后再决定。");
          return;
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
        results: current.results.map((row) => row.id === updated.id ? updated : row),
      } : current);
      setMessage(action === "reject" ? "候选已拒绝，证据仍保留。" : "候选已按其领域规则处理，草稿不会自动发布。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "审核操作失败。");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="admin-section candidate-review" aria-label="统一候选审核">
      <header className="admin-section-heading">
        <div><p className="eyebrow">审核工作流</p><h1>候选审核中心</h1><span>这里管理待审核的字段补全、PDF 词典和新权威对象候选。它不是词典本身；接受动作仍写入各自的权威来源。</span></div>
        <div className="admin-section-actions"><button type="button" onClick={() => void load()} disabled={loading}><Filter size={15} />刷新</button></div>
      </header>
      <div className="admin-toolbar candidate-review-toolbar">
        <label><span>状态</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="pending">待审核</option><option value="accepted">已接受</option><option value="rejected">已拒绝</option><option value="all">全部</option></select></label>
        <label><span>候选类型</span><select value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">全部审核来源</option><option value="field_enrichment">字段补全</option><option value="query_lexicon">PDF 词典</option><option value="new_authority">新权威对象</option><option value="metadata">书目元数据</option><option value="theory">理论 / 关系</option></select></label>
        {data ? <small>待审核队列共 {data.counts.total ?? data.results.length} 条 · 字段补全 {data.counts.field_enrichment ?? 0} · PDF 词典 {data.counts.query_lexicon ?? 0} · 新权威对象 {data.counts.new_authority ?? 0}{data.truncated ? " · 当前只显示排序靠前的一页" : ""}</small> : null}
      </div>
      <p className="admin-help candidate-review-explanation">“全部审核来源”只是把不同领域的待审记录集中展示，不是会自动更新的社会科学词典。QueryLexicon 是由已确认 authority 派生的检索词典；这里的接受、拒绝或匹配动作仍分别写回各自的来源对象。</p>
      {message ? <p className="form-message" role="status">{message}</p> : null}
      {loading ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取候选……</p> : null}
      {!loading && !data?.results.length ? <p className="admin-list-state">当前筛选没有候选。0 也是有效状态。</p> : null}
      <div className="candidate-review-list">
        {data?.results.map((candidate) => (
          <article className="panel candidate-review-card" key={`${candidate.review_kind}-${candidate.id}`}>
            <header>
              <div><p className="eyebrow">{kindLabel(candidate.review_kind)}</p><h2>{candidate.field_name ?? candidate.candidate_type ?? "候选"}</h2><span>{candidate.target_label || `${entityLabel(candidate.target_entity_type)} · ${candidate.target_entity_id ?? "未解析"}`}</span></div>
              <strong>{Math.round(candidate.confidence * 100)}%</strong>
            </header>
            <div className="candidate-review-comparison"><section><small>当前值</small><pre>{valueText(candidate.current_value)}</pre></section><section><small>候选值</small><pre>{valueText(candidate.proposed_value ?? candidate.proposed_term)}</pre></section></div>
            <p className="candidate-review-meta">{candidate.language ? `语言 ${candidate.language} · ` : ""}状态 {statusLabel(candidate.status)} · 证据 {candidate.evidence_count} 条 · 独立来源 {candidate.independent_source_count} 个</p>
            {candidate.conflicts?.length ? <details><summary>来源冲突</summary><pre>{valueText(candidate.conflicts)}</pre></details> : null}
            {candidate.confidence_factors ? <details><summary>置信度因素</summary><pre>{valueText(candidate.confidence_factors)}</pre></details> : null}
            <div className="candidate-review-evidence">
              {(candidate.evidence_records ?? []).filter((evidence) => evidence.is_current !== false).map((evidence) => <EvidenceEnvelopeCard evidence={evidence} key={evidence.id} />)}
            </div>
            {candidate.status === "pending" && (["field_enrichment", "query_lexicon", "new_authority"].includes(candidate.review_kind) || candidate.action_descriptors || candidate.actions) ? <CandidateDecisionBar
              candidate={decisionCandidate(candidate)}
              className="candidate-review-actions"
              showInspect={false}
              busyAction={busy.startsWith(`${candidate.id}:`) ? busy.slice(candidate.id.length + 1) : ""}
              disabled={Boolean(busy)}
              onAction={(descriptor, editedValue) => void decide(candidate, descriptor, editedValue)}
            /> : candidate.review_action === "open_intake_workspace" && candidate.upload_item_id ? <footer className="candidate-review-actions"><a href={`/admin/intake/${candidate.upload_item_id}`}>打开上架工作台</a></footer> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
