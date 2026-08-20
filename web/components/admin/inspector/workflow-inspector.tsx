"use client";

import { Check, ExternalLink, FileSearch, PanelRightClose, X } from "lucide-react";
import { useEffect, useState } from "react";
import { apiBlob } from "@/lib/api";
import type { WorkflowCandidate } from "../workflow/workflow-types";

export type InspectorSelection = {
  kind: "candidate" | "entity" | "evidence" | "pdf" | "history" | "publication";
  title: string;
  description?: string;
  items?: WorkflowCandidate[];
  pdfUrl?: string;
};

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未提供";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}

function evidenceRows(candidate: WorkflowCandidate): unknown[] {
  if (Array.isArray(candidate.evidence_records)) return candidate.evidence_records;
  if (Array.isArray(candidate.evidence)) return candidate.evidence;
  return candidate.evidence ? [candidate.evidence] : [];
}

function stringRows(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => String(row ?? "").trim()).filter(Boolean);
}

function lexiconImpact(candidate: WorkflowCandidate): string[] {
  if (candidate.kind === "lexicon_candidate") {
    return [
      "接受后先写入现有 PersonNameVariant 或 KnowledgeNodeAlias",
      "现有 QueryLexicon sync 任务随后生成 VERIFIED 检索词",
      "不会把网页或 PDF 文本直接写入正式 RAG",
    ];
  }
  if (candidate.source_tier === "query_lexicon") {
    return ["当前建议来自已有 QueryLexicon，不会新增词条", "选择后仍需在本节确认正式实体或关系"];
  }
  if (candidate.kind === "enrichment" && ["name_variant", "alias"].includes(String(candidate.field_name ?? ""))) {
    return ["接受规范名称变体后，由现有 QueryLexicon outbox 同步", "搜索和实体识别只在同步完成后使用新词"];
  }
  return ["当前操作不会直接改写 QueryLexicon", "正式实体、分类和知识关系仍需人工确认"];
}

const actionLabels: Record<string, string> = {
  link_existing: "关联现有实体",
  create_draft: "创建草稿实体",
  keep_unresolved: "保留当前未解析值",
  reject: "拒绝候选",
  reopen: "恢复待审",
  accept: "接受候选",
  inspect: "核对来源",
};

export function WorkflowInspector({
  selection,
  token,
  onClose,
  onDecision,
}: {
  selection: InspectorSelection | null;
  token: string | null;
  onClose: () => void;
  onDecision?: (candidate: WorkflowCandidate, action: string) => void;
}) {
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewError, setPreviewError] = useState("");

  useEffect(() => {
    if (selection?.kind !== "pdf" || !selection.pdfUrl || !token) return;
    let active = true;
    let objectUrl = "";
    const timer = window.setTimeout(() => {
      if (!active) return;
      setPreviewUrl("");
      setPreviewError("");
      void apiBlob(selection.pdfUrl!, token)
        .then((blob) => {
          objectUrl = URL.createObjectURL(blob);
          if (active) setPreviewUrl(objectUrl);
          else URL.revokeObjectURL(objectUrl);
        })
        .catch((reason) => {
          if (active) setPreviewError(reason instanceof Error ? reason.message : "PDF 预览不可用。");
        });
    }, 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selection?.kind, selection?.pdfUrl, token]);

  if (!selection) {
    return (
      <aside className="workflow-inspector is-empty" aria-label="证据与候选检查器">
        <FileSearch size={22} />
        <strong>检查器</strong>
        <p>选择字段候选、责任者、知识关系或 PDF 证据后，在这里集中核对。</p>
      </aside>
    );
  }

  return (
    <aside className="workflow-inspector is-open" aria-label={selection.title}>
      <header>
        <div><small>Inspector</small><h2>{selection.title}</h2>{selection.description ? <p>{selection.description}</p> : null}</div>
        <button type="button" onClick={onClose} aria-label="关闭检查器"><PanelRightClose size={17} /></button>
      </header>
      {selection.kind === "pdf" ? (
        <div className="workflow-inspector-pdf">
          {previewUrl ? <iframe title={selection.title} src={previewUrl} /> : <p>{previewError || "正在准备 PDF 预览……"}</p>}
        </div>
      ) : (
        <div className="workflow-inspector-items">
          {(selection.items ?? []).map((candidate) => {
            const proposed = candidate.proposed_value ?? candidate.value;
            const evidence = evidenceRows(candidate);
            const reasons = stringRows(candidate.reasons);
            const actions = (candidate.available_actions ?? []).filter((action) => action !== "inspect");
            const leadOnly = candidate.evidence_status === "lead_only" || candidate.source_tier === "research_lead";
            return (
              <article key={candidate.id}>
                <header><strong>{candidate.label || candidate.field_name || "候选"}</strong><span>{candidate.status || "pending"}</span></header>
                {leadOnly ? <p className="workflow-inspector-lead-warning">这是研究线索。搜索摘要不是 Evidence，不能直接接受为正式知识。</p> : null}
                {candidate.current_value !== undefined ? <div className="workflow-inspector-comparison"><section><small>当前值</small><pre>{displayValue(candidate.current_value)}</pre></section><section><small>候选值</small><pre>{displayValue(proposed)}</pre></section></div> : <pre>{displayValue(proposed)}</pre>}
                <dl>
                  {candidate.source_tier_label || candidate.source_tier ? <div><dt>来源层级</dt><dd>{String(candidate.source_tier_label ?? candidate.source_tier)}</dd></div> : null}
                  {candidate.source_class || candidate.source ? <div><dt>来源</dt><dd>{String(candidate.source_class ?? candidate.source)}</dd></div> : null}
                  {typeof candidate.confidence === "number" ? <div><dt>置信度</dt><dd>{Math.round(candidate.confidence * 100)}%</dd></div> : null}
                  {candidate.evidence_count !== undefined ? <div><dt>证据</dt><dd>{String(candidate.evidence_count)} 条</dd></div> : null}
                </dl>
                {reasons.length ? <details open><summary>匹配依据</summary><ul>{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details> : null}
                {evidence.length ? <h3>证据</h3> : null}
                {evidence.map((entry, index) => {
                  const row = entry && typeof entry === "object" ? entry as Record<string, unknown> : {};
                  const url = typeof row.canonical_url === "string" ? row.canonical_url : typeof row.url === "string" ? row.url : "";
                  return <blockquote key={`${candidate.id}-evidence-${index}`}><p>{displayValue(row.supporting_text ?? row.text_quote ?? row.quote ?? entry)}</p>{url ? <a href={url} target="_blank" rel="noreferrer">查看来源 <ExternalLink size={12} /></a> : null}</blockquote>;
                })}
                <details><summary>词典影响</summary><ul>{lexiconImpact(candidate).map((row) => <li key={row}>{row}</li>)}</ul></details>
                {candidate.status === "pending" && onDecision && candidate.decision_url && actions.length ? <footer>{actions.map((action) => <button className={action === "reject" ? "danger" : ""} type="button" key={action} onClick={() => onDecision(candidate, action)}>{action === "reject" ? <X size={13} /> : <Check size={13} />}{actionLabels[action] ?? action}</button>)}</footer> : null}
              </article>
            );
          })}
          {!selection.items?.length ? <p>当前任务没有可展示的候选或证据。</p> : null}
        </div>
      )}
    </aside>
  );
}
