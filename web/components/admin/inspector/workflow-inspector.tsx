"use client";

import { ExternalLink, FileSearch, PanelRightClose } from "lucide-react";
import { useEffect, useState } from "react";
import { apiBlob } from "@/lib/api";
import { type CandidateActionDescriptor } from "../research/candidate-action-contract";
import { CandidateDecisionBar } from "../research/candidate-decision-bar";
import { EvidenceEnvelopeCard } from "../research/evidence-envelope-card";
import type { WorkflowCandidate } from "../workflow/workflow-types";

export type InspectorSelection = {
  kind: "candidate" | "entity" | "evidence" | "pdf" | "page_preview" | "history" | "publication";
  title: string;
  description?: string;
  items?: WorkflowCandidate[];
  pdfUrl?: string;
  previewUrl?: string;
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

function sourceLabel(candidate: WorkflowCandidate): string {
  const source = String(candidate.source_tier ?? candidate.source_class ?? candidate.source ?? "").toLocaleLowerCase();
  if (source.includes("library") || source.includes("local") || source.includes("lexicon")) return "馆内已有记录";
  if (source.includes("pdf") || source.includes("ocr") || source.includes("native")) return "来自本书";
  if (source.includes("publisher")) return "出版社资料";
  if (source.includes("authority") || source.includes("registry") || source.includes("catalog")) return "权威资料";
  if (source.includes("web") || source.includes("research")) return "其他外部资料";
  return "其他资料";
}

function candidateStatus(candidate: WorkflowCandidate): string {
  if (stringRows(candidate.conflicts).length) return "存在冲突";
  if (["in_library", "local", "public_active"].includes(String(candidate.source_tier ?? ""))) return "建议采用";
  return "需要确认";
}

export function WorkflowInspector({
  selection,
  token,
  onClose,
  onDecision,
  onVerify,
}: {
  selection: InspectorSelection | null;
  token: string | null;
  onClose: () => void;
  onDecision?: (candidate: WorkflowCandidate, action: string) => Promise<boolean> | boolean | void;
  onVerify?: (candidate: WorkflowCandidate) => Promise<void> | void;
}) {
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [acting, setActing] = useState("");

  const decide = async (candidate: WorkflowCandidate, descriptor: CandidateActionDescriptor, editedValue?: unknown) => {
    if (acting) return;
    const key = `${candidate.id}:${descriptor.action}`;
    setActing(key);
    try {
      if (descriptor.action === "verify") await onVerify?.({ ...candidate, decision_descriptor: descriptor });
      else await onDecision?.({
        ...candidate,
        decision_descriptor: descriptor,
        ...(editedValue === undefined ? {} : {
          edited_value: editedValue,
          ...(candidate.kind === "derived_claim_curation" ? { edited_proposition: editedValue } : {}),
        }),
      }, descriptor.action);
    } finally {
      setActing("");
    }
  };

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
        <p>选择字段建议、作者或译者、知识关系及 PDF 证据后，在这里核对。</p>
      </aside>
    );
  }

  return (
    <aside className="workflow-inspector is-open" aria-label={selection.title}>
      <header>
        <div><small>查看依据</small><h2>{selection.title}</h2>{selection.description ? <p>{selection.description}</p> : null}</div>
        <button type="button" onClick={onClose} aria-label="关闭检查器"><PanelRightClose size={17} /></button>
      </header>
      {selection.kind === "pdf" ? (
        <div className="workflow-inspector-pdf">
          {previewUrl ? <iframe title={selection.title} src={previewUrl} /> : <p>{previewError || "正在准备 PDF 预览……"}</p>}
        </div>
      ) : selection.kind === "page_preview" && selection.previewUrl ? (
        <div className="workflow-inspector-page-preview">
          <a href={selection.previewUrl} target="_blank" rel="noreferrer">打开完整前台预览 <ExternalLink size={13} /></a>
          <iframe title={selection.title} src={selection.previewUrl} />
        </div>
      ) : (
        <div className="workflow-inspector-items">
          {(selection.items ?? []).map((candidate) => {
            const proposed = candidate.proposed_value ?? candidate.value;
            const evidence = evidenceRows(candidate);
            const reasons = stringRows(candidate.match_reasons ?? candidate.reasons);
            const conflicts = stringRows(candidate.conflicts);
            const leadOnly = candidate.evidence_status === "lead_only" || candidate.source_tier === "research_lead";
            return (
              <article key={candidate.id}>
                <header><strong>{candidate.label || candidate.field_name || "建议"}</strong><span>{candidateStatus(candidate)}</span></header>
                {leadOnly ? <p className="workflow-inspector-lead-warning">这是一条待核实线索，取得可靠正文依据前不能采用。</p> : null}
                {candidate.current_value !== undefined ? <div className="workflow-inspector-comparison"><section><small>当前值</small><pre>{displayValue(candidate.current_value)}</pre></section><section><small>候选值</small><pre>{displayValue(proposed)}</pre></section></div> : <pre>{displayValue(proposed)}</pre>}
                <dl>
                  <div><dt>依据类型</dt><dd>{sourceLabel(candidate)}</dd></div>
                  {candidate.evidence_count !== undefined ? <div><dt>证据</dt><dd>{String(candidate.evidence_count)} 条</dd></div> : null}
                </dl>
                {reasons.length ? <details open><summary>匹配依据</summary><ul>{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details> : null}
                {conflicts.length ? <details open className="workflow-inspector-conflicts"><summary>冲突</summary><ul>{conflicts.map((conflict) => <li key={conflict}>{conflict}</li>)}</ul></details> : null}
                {evidence.length ? <h3>证据</h3> : null}
                {evidence.map((entry, index) => <EvidenceEnvelopeCard evidence={entry} compact key={`${candidate.id}-evidence-${index}`} />)}
                {["pending", "research_lead", "proposed"].includes(String(candidate.status ?? "pending")) ? <CandidateDecisionBar
                  candidate={candidate}
                  className="workflow-inspector-decisions"
                  showInspect={false}
                  busyAction={acting.startsWith(`${candidate.id}:`) ? acting.slice(String(candidate.id).length + 1) : ""}
                  disabled={Boolean(acting)}
                  actionFilter={(descriptor) => descriptor.action === "verify" ? Boolean(onVerify) : descriptor.action !== "inspect" && Boolean(onDecision)}
                  onAction={(descriptor, editedValue) => void decide(candidate, descriptor, editedValue)}
                /> : null}
              </article>
            );
          })}
          {!selection.items?.length ? <p>当前任务没有可展示的候选或证据。</p> : null}
        </div>
      )}
    </aside>
  );
}
