"use client";

import { Check, ExternalLink, Globe2, LoaderCircle, SearchCheck, X } from "lucide-react";
import { useMemo, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type Evidence = {
  id: string;
  canonical_url: string;
  source_title: string;
  source_domain: string;
  source_class: string;
  provider: string;
  supporting_text: string;
  retrieved_at: string;
  is_current: boolean;
};

type Candidate = {
  id: string;
  field_name: string;
  candidate_kind: "factual" | "classification" | "interpretive";
  proposed_value: unknown;
  current_value: unknown;
  source_class: string;
  confidence: number;
  confidence_factors: Record<string, unknown>;
  conflicts: unknown[];
  identity_status: string;
  status: "pending" | "accepted" | "rejected" | "superseded";
  evidence_count: number;
  independent_source_count: number;
  evidence_records: Evidence[];
};

type EnrichmentResponse = {
  request_id: string;
  results: Candidate[];
  errors: Array<{ code: string; detail: string; provider?: string; field_name?: string }>;
  stats: Record<string, unknown>;
};

export type FieldEnrichmentDefinition = {
  name: string;
  label: string;
  currentValue?: unknown;
};

type Props = {
  targetType: "person" | "work" | "edition" | "discipline" | "subdiscipline" | "knowledge_node" | "topic" | "reading_path";
  targetId?: string | null;
  fields: FieldEnrichmentDefinition[];
  formContext?: Record<string, unknown>;
  title?: string;
  onAccepted?: () => void;
};

const sourceLabels: Record<string, string> = {
  identifier_registry: "标识符注册库",
  publisher: "出版社",
  national_library: "国家图书馆",
  library_catalog: "图书馆目录",
  university: "大学",
  research_institute: "研究机构",
  academic_journal: "学术期刊",
  professional_association: "专业协会",
  scholarly_encyclopedia: "学术百科",
  scholar_homepage: "学者主页",
  syllabus: "课程大纲",
  general_web: "一般网页",
  unknown: "未知来源",
};

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "未填写";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value, null, 2);
}

export function FieldEnrichmentControl({
  targetType,
  targetId,
  fields,
  formContext = {},
  title = "字段联网核对",
  onAccepted,
}: Props) {
  const [results, setResults] = useState<Candidate[]>([]);
  const [errors, setErrors] = useState<EnrichmentResponse["errors"]>([]);
  const [loadingMode, setLoadingMode] = useState<"structured" | "web" | "full" | "">("");
  const [decisionId, setDecisionId] = useState("");
  const [message, setMessage] = useState("");
  const labels = useMemo(() => new Map(fields.map((field) => [field.name, field.label])), [fields]);

  async function run(mode: "structured" | "web" | "full") {
    if (!targetId || loadingMode) return;
    setLoadingMode(mode);
    setMessage("");
    setErrors([]);
    try {
      const payload = await apiRequest<EnrichmentResponse>(
        "/catalog/admin/field-enrichment/",
        {
          method: "POST",
          body: JSON.stringify({
            target_type: targetType,
            target_id: targetId,
            fields: fields.map((field) => field.name),
            current_value: Object.fromEntries(fields.map((field) => [field.name, field.currentValue])),
            form_context: formContext,
            requested_mode: mode,
            visibility: "admin",
          }),
        },
        getServerSessionCredential(),
      );
      setResults(payload.results);
      setErrors(payload.errors ?? []);
      setMessage(payload.results.length ? "候选已保存，必须逐条核对证据后接受。" : "本次没有形成满足身份与证据门槛的候选。 ");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "字段核对暂时不可用。 ");
    } finally {
      setLoadingMode("");
    }
  }

  async function decide(candidate: Candidate, action: "accept" | "reject") {
    setDecisionId(candidate.id);
    setMessage("");
    try {
      const updated = await apiRequest<Candidate>(
        `/catalog/admin/field-enrichment/candidates/${candidate.id}/decision/`,
        {
          method: "POST",
          body: JSON.stringify({ action, reason: `现有 Admin 字段审核 ${action}` }),
        },
        getServerSessionCredential(),
      );
      setResults((current) => current.map((row) => row.id === updated.id ? updated : row));
      setMessage(action === "accept" ? "候选已写入对应 authority。" : "候选已拒绝，证据继续保留。 ");
      if (action === "accept") onAccepted?.();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "审核操作失败。 ");
    } finally {
      setDecisionId("");
    }
  }

  if (!targetId) {
    return <section className="field-enrichment-control"><header><strong>{title}</strong></header><p>请先保存当前对象，再按字段核对外部来源。</p></section>;
  }

  return (
    <section className="field-enrichment-control" aria-label={title}>
      <header>
        <div><strong>{title}</strong><small>搜索摘要不作为证据。候选只引用实际来源页面或结构化记录。</small></div>
        <div className="field-enrichment-actions">
          <button type="button" disabled={Boolean(loadingMode)} onClick={() => void run("structured")}>
            {loadingMode === "structured" ? <LoaderCircle className="spin" size={14} /> : <SearchCheck size={14} />}核对结构化来源
          </button>
          <button type="button" disabled={Boolean(loadingMode)} onClick={() => void run("web")}>
            {loadingMode === "web" ? <LoaderCircle className="spin" size={14} /> : <Globe2 size={14} />}联网核对本页
          </button>
        </div>
      </header>
      <p className="field-enrichment-fields">字段 {fields.map((field) => field.label).join("、")}</p>
      {message ? <p className="field-enrichment-message" role="status">{message}</p> : null}
      {errors.length ? <details className="field-enrichment-errors"><summary>部分来源未完成（{errors.length}）</summary><ul>{errors.map((error, index) => <li key={`${error.code}-${index}`}><strong>{error.code}</strong>{error.provider ? ` · ${error.provider}` : ""} · {error.detail}</li>)}</ul></details> : null}
      <div className="field-enrichment-candidates">
        {results.map((candidate) => (
          <article key={candidate.id}>
            <header>
              <div><strong>{labels.get(candidate.field_name) ?? candidate.field_name}</strong><span>{candidate.candidate_kind} · {sourceLabels[candidate.source_class] ?? candidate.source_class}</span></div>
              <b>{Math.round(candidate.confidence * 100)}%</b>
            </header>
            <div className="field-enrichment-comparison">
              <section><small>当前值</small><pre>{displayValue(candidate.current_value)}</pre></section>
              <section><small>候选值</small><pre>{displayValue(candidate.proposed_value)}</pre></section>
            </div>
            <p>身份 {candidate.identity_status} · 证据 {candidate.evidence_count} 条 · 独立来源 {candidate.independent_source_count} 个</p>
            <details><summary>置信度组成</summary><pre>{displayValue(candidate.confidence_factors)}</pre></details>
            {candidate.conflicts.length ? <details><summary>存在来源或当前值冲突</summary><pre>{displayValue(candidate.conflicts)}</pre></details> : null}
            <div className="field-enrichment-evidence">
              {candidate.evidence_records.filter((row) => row.is_current).map((evidence) => (
                <blockquote key={evidence.id}>
                  <header><a href={evidence.canonical_url} target="_blank" rel="noreferrer">{evidence.source_title}<ExternalLink size={12} /></a><span>{sourceLabels[evidence.source_class] ?? evidence.source_class} · {new Date(evidence.retrieved_at).toLocaleDateString("zh-CN")}</span></header>
                  <p>{evidence.supporting_text}</p>
                </blockquote>
              ))}
            </div>
            {candidate.status === "pending" ? <footer><button type="button" disabled={decisionId === candidate.id} onClick={() => void decide(candidate, "accept")}><Check size={14} />接受</button><button className="danger" type="button" disabled={decisionId === candidate.id} onClick={() => void decide(candidate, "reject")}><X size={14} />拒绝</button></footer> : <footer><span>状态 {candidate.status}</span></footer>}
          </article>
        ))}
      </div>
    </section>
  );
}
