"use client";

import { Check, ExternalLink, Filter, LoaderCircle, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

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
};

type ReviewEnvelope = {
  results: Candidate[];
  counts: Record<string, number>;
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
    new_authority: "新 authority 候选",
    metadata: "Metadata 候选",
    theory: "理论 / 关系审核",
  } as Record<Candidate["review_kind"], string>)[kind];
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

  async function decide(candidate: Candidate, action: "accept" | "reject" | "match_existing" | "create_draft") {
    if (!["field_enrichment", "query_lexicon", "new_authority"].includes(candidate.review_kind)) {
      setMessage("该条记录请从 Intake 或专用理论审核页面处理，统一列表只展示证据和入口。");
      return;
    }
    setBusy(candidate.id);
    setMessage("");
    try {
      const body: Record<string, unknown> = { action, reason: `统一候选审核 ${action}` };
      if (action === "match_existing") {
        const match = candidate.possible_matches?.[0];
        if (!match?.entity_id) {
          setMessage("当前没有可安全选择的已有实体，请打开 Knowledge Workspace 后再决定。");
          return;
        }
        body.target_type = match.entity_type;
        body.target_id = match.entity_id;
      }
      if (action === "create_draft") body.confirm_new = true;
      const updated = await apiRequest<Candidate>(
        `/catalog/admin/candidate-review/${candidate.review_kind}/${candidate.id}/decision/`,
        {
          method: "POST",
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
        <div><p className="eyebrow">REVIEW WORKFLOW</p><h1>候选审核</h1><span>不同业务模型共享证据展示和审核动作，接受时仍按各自 source-of-truth 路由。</span></div>
        <div className="admin-section-actions"><button type="button" onClick={() => void load()} disabled={loading}><Filter size={15} />刷新</button></div>
      </header>
      <div className="admin-toolbar candidate-review-toolbar">
        <label><span>状态</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="pending">待审核</option><option value="accepted">已接受</option><option value="rejected">已拒绝</option><option value="all">全部</option></select></label>
        <label><span>候选类型</span><select value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">全部</option><option value="field_enrichment">字段补全</option><option value="query_lexicon">PDF 词典</option><option value="new_authority">新 authority</option><option value="metadata">Metadata</option><option value="theory">理论 / 关系</option></select></label>
        {data ? <small>共 {data.counts.total ?? data.results.length} 条</small> : null}
      </div>
      {message ? <p className="form-message" role="status">{message}</p> : null}
      {loading ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取候选……</p> : null}
      {!loading && !data?.results.length ? <p className="admin-list-state">当前筛选没有候选。0 也是有效状态。</p> : null}
      <div className="candidate-review-list">
        {data?.results.map((candidate) => (
          <article className="panel candidate-review-card" key={`${candidate.review_kind}-${candidate.id}`}>
            <header>
              <div><p className="eyebrow">{kindLabel(candidate.review_kind)}</p><h2>{candidate.field_name ?? candidate.candidate_type ?? "候选"}</h2><span>{candidate.target_label || `${candidate.target_entity_type ?? ""} ${candidate.target_entity_id ?? "未解析"}`}</span></div>
              <strong>{Math.round(candidate.confidence * 100)}%</strong>
            </header>
            <div className="candidate-review-comparison"><section><small>当前值</small><pre>{valueText(candidate.current_value)}</pre></section><section><small>候选值</small><pre>{valueText(candidate.proposed_value ?? candidate.proposed_term)}</pre></section></div>
            <p className="candidate-review-meta">{candidate.language ? `语言 ${candidate.language} · ` : ""}状态 {candidate.status} · 证据 {candidate.evidence_count} 条 · 独立来源 {candidate.independent_source_count} 个</p>
            {candidate.conflicts?.length ? <details><summary>来源冲突</summary><pre>{valueText(candidate.conflicts)}</pre></details> : null}
            {candidate.confidence_factors ? <details><summary>置信度因素</summary><pre>{valueText(candidate.confidence_factors)}</pre></details> : null}
            <div className="candidate-review-evidence">
              {(candidate.evidence_records ?? []).filter((evidence) => evidence.is_current !== false).map((evidence) => {
                const quote = evidence.supporting_text || evidence.evidence_text || "未提供支撑片段";
                const readerHref = evidence.asset && evidence.page_number ? `/reader/${evidence.asset}?page=${evidence.page_number}` : "";
                return <blockquote key={evidence.id}><header><span>{evidence.source_title || evidence.work_title || "馆藏证据"}</span>{evidence.canonical_url ? <a href={evidence.canonical_url} target="_blank" rel="noreferrer" aria-label="打开来源"><ExternalLink size={13} /></a> : null}</header><p>{quote}</p><footer>{evidence.page_number ? `第 ${evidence.printed_page_label || evidence.page_number} 页` : "页码待补充"}{readerHref ? <a href={readerHref} target="_blank" rel="noreferrer">回到阅读器</a> : null}</footer></blockquote>;
              })}
            </div>
            {candidate.status === "pending" && candidate.review_kind === "new_authority" ? <footer className="candidate-review-actions"><button type="button" disabled={busy === candidate.id} onClick={() => void decide(candidate, "match_existing")}><Check size={14} />Match Existing</button><button type="button" disabled={busy === candidate.id} onClick={() => void decide(candidate, "create_draft")}><Check size={14} />Create Draft</button><button className="danger" type="button" disabled={busy === candidate.id} onClick={() => void decide(candidate, "reject")}><X size={14} />拒绝</button></footer> : candidate.status === "pending" && ["field_enrichment", "query_lexicon"].includes(candidate.review_kind) ? <footer className="candidate-review-actions"><button type="button" disabled={busy === candidate.id} onClick={() => void decide(candidate, "accept")}><Check size={14} />接受</button><button className="danger" type="button" disabled={busy === candidate.id} onClick={() => void decide(candidate, "reject")}><X size={14} />拒绝</button></footer> : candidate.review_action === "open_intake_workspace" && candidate.upload_item_id ? <footer className="candidate-review-actions"><a href={`/admin/intake/${candidate.upload_item_id}`}>打开 Intake</a></footer> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
