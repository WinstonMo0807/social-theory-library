"use client";

import Link from "next/link";
import { AlertTriangle, Check, ChevronDown, ChevronRight, Eye, FileCheck2, LoaderCircle, RefreshCw, Save, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { r2StagingStatusLabel } from "@/lib/ingestion-staging-status";
import {
  CanonicalField,
  ConditionalFieldGroup,
  EntityPicker,
  MultilingualField,
  QualityIssue,
  RepeatableField,
  type EntityValue,
} from "../forms/workflow-fields";
import { WorkCurationEditor } from "../curation/work-curation-editor";
import { WorkflowInspector, type InspectorSelection } from "../inspector/workflow-inspector";
import {
  WORKFLOW_STEP_KEYS,
  WORKFLOW_STEP_LABELS,
  bibliographyFields,
  dirtyFieldCount,
  isWorkflowStepKey,
  mergeRemoteDrafts,
  nextWorkflowStep,
  sectionPresentations,
  stepFromHash,
  validateWorkflowSection,
  withDirtyField,
  workflowHashUrl,
  type DirtyFields,
  type ValidationIssue,
  type WorkflowStepKey,
  type WorkflowStepStatus,
} from "./workflow-state";
import {
  asArray,
  asBoolean,
  asNumber,
  asRecord,
  asString,
  candidateList,
  type WorkflowCandidate,
  type WorkflowDrafts,
  type WorkflowEvaluation,
  type WorkflowIssue,
  type WorkflowPayload,
  type WorkflowStep,
} from "./workflow-types";
import { WorkflowStepRail } from "./workflow-step-rail";

type EditorMode = "intake" | "maintenance";
type SectionUpdate = (step: WorkflowStepKey, field: string, value: unknown) => void;

const documentTypeOptions = [
  { value: "book", label: "图书" },
  { value: "journal_article", label: "期刊论文" },
  { value: "thesis", label: "学位论文" },
  { value: "report", label: "研究报告" },
] as const;

const languageOptions = [
  { value: "zh-CN", label: "简体中文" },
  { value: "zh-TW", label: "繁体中文" },
  { value: "en", label: "英文" },
  { value: "mixed", label: "多语种" },
] as const;

const contributorRoleOptions = [
  { value: "author", label: "作者" },
  { value: "editor", label: "编者" },
  { value: "translator", label: "译者" },
  { value: "advisor", label: "导师" },
  { value: "subject", label: "研究对象" },
] as const;

const nodeRoleOptions = [
  { value: "foundational_work", label: "奠基性原著" },
  { value: "systematic_exposition", label: "系统阐释" },
  { value: "theoretical_development", label: "理论发展" },
  { value: "empirical_application", label: "经验应用" },
  { value: "comparative_study", label: "比较研究" },
  { value: "critique", label: "批评反思" },
  { value: "general_mention", label: "一般提及" },
] as const;

const theoryRoleOptions = [
  { value: "foundational", label: "奠基文献" },
  { value: "development", label: "理论发展" },
  { value: "introduction", label: "入门综述" },
  { value: "empirical_application", label: "经验应用" },
  { value: "method_use", label: "方法使用" },
  { value: "criticism", label: "理论批评" },
  { value: "theory_history", label: "理论史研究" },
  { value: "local_mention", label: "局部提及" },
] as const;

const strengthOptions = [
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
  { value: "low", label: "低" },
] as const;

function blankStep(key: WorkflowStepKey, current: WorkflowStepKey): WorkflowStep {
  return { key, label: WORKFLOW_STEP_LABELS[key], status: key === current ? "working" : "pending", issues: [] };
}

function normalizeIssue(value: unknown, fallbackStep?: WorkflowStepKey): WorkflowIssue {
  if (typeof value === "string") return { message: value, step: fallbackStep };
  const row = asRecord(value);
  const rawStep = row.step ?? asRecord(row.action_target).step;
  const step = isWorkflowStepKey(rawStep) ? rawStep : fallbackStep;
  return {
    code: asString(row.code),
    message: asString(row.message ?? row.detail, "需要管理员处理。"),
    severity: ["blocker", "warning", "info"].includes(asString(row.severity)) ? asString(row.severity) as WorkflowIssue["severity"] : undefined,
    step,
    field: asString(row.field) || undefined,
    action_target: row.action_target as WorkflowIssue["action_target"],
  };
}

function normalizeWorkflow(value: unknown): WorkflowEvaluation {
  const row = asRecord(value);
  const current = isWorkflowStepKey(row.current_step) ? row.current_step : "file";
  const rawSteps = asArray(row.steps);
  const supplied = new Map<WorkflowStepKey, WorkflowStep>();
  rawSteps.forEach((entry) => {
    const step = asRecord(entry);
    if (!isWorkflowStepKey(step.key)) return;
    const stepKey = step.key;
    const statusValue = asString(step.status, "pending") as WorkflowStepStatus;
    supplied.set(stepKey, {
      key: stepKey,
      label: asString(step.label, WORKFLOW_STEP_LABELS[stepKey]),
      status: statusValue,
      issues: asArray(step.issues).map((issue) => normalizeIssue(issue, stepKey)),
      summary: step.summary as WorkflowStep["summary"],
      next_action: asString(step.next_action) || asString(asRecord(step.next_action).label) || null,
    });
  });
  return {
    overall_status: asString(row.overall_status, "working"),
    current_step: current,
    suggested_next_step: isWorkflowStepKey(row.suggested_next_step) ? row.suggested_next_step : null,
    steps: WORKFLOW_STEP_KEYS.map((key) => supplied.get(key) ?? blankStep(key, current)),
    unresolved_count: asNumber(row.unresolved_count),
    warnings_count: asNumber(row.warnings_count),
    blockers_count: asNumber(row.blockers_count),
  };
}

function normalizePayload(value: unknown, mode: EditorMode, itemId?: string, workId?: string): WorkflowPayload {
  const root = asRecord(asRecord(value).payload ?? value);
  const legacyItem = asRecord(root.item);
  const legacyCatalog = asRecord(root.catalog);
  const context = {
    ...asRecord(root.context),
    item_id: asString(asRecord(root.context).item_id ?? legacyItem.id ?? itemId) || null,
    work_id: asString(asRecord(root.context).work_id ?? legacyCatalog.work_id ?? workId) || null,
    edition_id: asString(asRecord(root.context).edition_id ?? legacyCatalog.edition_id) || null,
    title: asString(asRecord(root.context).title ?? legacyCatalog.title ?? legacyItem.filename, "未命名馆藏"),
    filename: asString(asRecord(root.context).filename ?? legacyItem.filename),
    document_type: asString(asRecord(root.context).document_type ?? legacyCatalog.document_type, "book"),
    publication_state: asString(asRecord(root.context).publication_state ?? legacyCatalog.publication_state, "draft"),
  };
  const data = { ...asRecord(root.data) };
  if (!Object.keys(data).length && (Object.keys(legacyCatalog).length || Object.keys(legacyItem).length)) {
    data.file = { ...legacyItem, ...asRecord(root.asset) };
    data.work = legacyCatalog;
    data.bibliography = legacyCatalog;
    data.contributors = { items: asArray(legacyCatalog.contributors ?? legacyCatalog.authors) };
    data.classification = {};
    data.knowledge = {};
    data.reader = asRecord(root.asset);
    data.curation = {};
    data.publication = {};
  }
  return {
    mode: root.mode === "maintenance" ? "maintenance" : mode,
    context,
    workflow: normalizeWorkflow(root.workflow),
    data,
    candidates: asRecord(root.candidates ?? {
      metadata: root.metadata_candidates,
      entities: root.entity_candidates,
    }),
    permissions: asRecord(root.permissions),
    queue: asRecord(root.queue),
  };
}

function normalizeItems(value: unknown, fallbackKey: string): Record<string, unknown>[] {
  const direct = Array.isArray(value) ? value : asArray(asRecord(value).items);
  return direct.map((entry) => {
    if (typeof entry === "string") return { id: null, [fallbackKey]: entry };
    const row = asRecord(entry);
    return { ...row, id: row.id ?? null, [fallbackKey]: row[fallbackKey] ?? row.name ?? row.title ?? "", };
  });
}

function draftsFromPayload(payload: WorkflowPayload): WorkflowDrafts {
  const data = payload.data;
  const fileGroup = asRecord(data.file);
  const work = { document_type: payload.context.document_type ?? "book", ...asRecord(data.work) };
  const bibliography = { ...asRecord(data.edition), ...asRecord(data.bibliography) };
  const contributors = asRecord(data.contributors);
  const classification = asRecord(data.classification);
  const knowledge = asRecord(data.knowledge);
  return {
    file: { ...asRecord(fileGroup.item), assets: asArray(fileGroup.assets) },
    work,
    bibliography,
    contributors: { ...contributors, items: normalizeItems(contributors.items ?? data.contributors, "display_name") },
    classification: {
      ...classification,
      primary_disciplines: normalizeItems(classification.primary_disciplines, "name"),
      related_disciplines: normalizeItems(classification.related_disciplines, "name"),
      subdisciplines: normalizeItems(classification.subdisciplines, "name"),
    },
    knowledge: { ...knowledge, relations: normalizeItems(knowledge.relations, "name") },
    reader: { ...asRecord(data.reader) },
    curation: { ...asRecord(data.curation) },
    publication: { ...asRecord(data.publication) },
  };
}

function fieldValue(section: Record<string, unknown>, name: string): string {
  return asString(section[name]);
}

function entities(value: unknown): EntityValue[] {
  return normalizeItems(value, "name").map((row) => ({ id: asString(row.id) || null, name: asString(row.name), status: asString(row.status), ...row })).filter((row) => row.name);
}

function candidateMatches(candidate: WorkflowCandidate, field: string): boolean {
  const name = asString(candidate.field_name ?? candidate.field);
  return name === field || name.endsWith(`.${field}`);
}

function summaryFor(step: WorkflowStepKey, draft: Record<string, unknown>): string {
  if (step === "file") return [draft.filename, draft.status, draft.validation].filter(Boolean).map(String).join(" · ") || "等待文件检查";
  if (step === "work") return [draft.title, draft.document_type, draft.language].filter(Boolean).map(String).join(" · ") || "作品待确认";
  if (step === "bibliography") return [draft.journal_title, draft.publisher, draft.publication_year].filter(Boolean).map(String).join(" · ") || "书目信息待确认";
  if (step === "contributors") return `${normalizeItems(draft.items, "display_name").length} 位责任者`;
  if (step === "classification") return `${normalizeItems(draft.primary_disciplines, "name").length} 个主要学科`;
  if (step === "knowledge") return `${normalizeItems(draft.relations, "name").length} 条正式关系`;
  if (step === "reader") return [draft.readable ? "可阅读" : "待检查", draft.text_layer_status, draft.page_label_status].filter(Boolean).map(String).join(" · ");
  if (step === "curation") return draft.skipped ? "已暂不策展" : `${normalizeItems(draft.reading_path_placements ?? draft.placements, "name").length} 个阅读路径位置`;
  return asString(draft.publication_state ?? draft.status, "待发布检查");
}

function statusLabel(status: string) {
  return ({ pending: "待处理", available: "可处理", working: "处理中", attention: "需注意", blocked: "被阻止", complete: "已完成", skipped: "已跳过" } as Record<string, string>)[status] ?? status;
}

type BodyProps = {
  step: WorkflowStepKey;
  draft: Record<string, unknown>;
  documentType: string;
  candidates: WorkflowCandidate[];
  canEdit: boolean;
  context: WorkflowPayload["context"];
  permissions: WorkflowPayload["permissions"];
  errors: ValidationIssue[];
  update: SectionUpdate;
  inspectField: (field: string, title?: string) => void;
  inspectPdf: () => void;
  fileAction: (action: "retry" | "resume" | "replace", file?: File) => void;
  curationChange: (value: Record<string, unknown>) => void;
  curationConfirm: () => void;
  curationSkip: () => void;
  refresh: () => void;
  message: (value: string) => void;
  goToIssue: (issue: WorkflowIssue) => void;
  publish: (intent: "next" | "stay") => void;
  withdraw: () => void;
  publishing: boolean;
};

function errorFor(errors: ValidationIssue[], field: string) {
  return errors.find((error) => error.field === field)?.message;
}

function candidateCount(candidates: WorkflowCandidate[], field: string) {
  return candidates.filter((candidate) => candidateMatches(candidate, field) && candidate.status !== "rejected").length;
}

function WorkBody({ draft, candidates, canEdit, errors, update, inspectField }: BodyProps) {
  const value = (field: string, next: string) => update("work", field, next);
  const identityCandidates = candidateCount(candidates, "work");
  return <>{identityCandidates ? <button className="workflow-work-identity" type="button" onClick={() => inspectField("work", "作品身份与版本判断")}><AlertTriangle size={15} /><span><strong>发现 {identityCandidates} 项馆内作品候选</strong><small>请明确选择关联现有 Work，或保留当前新 Work。系统不会按高置信度静默合并。</small></span><ChevronRight size={14} /></button> : null}<div className="workflow-field-grid"><CanonicalField name="title" label="作品题名" value={fieldValue(draft, "title")} onChange={(next) => value("title", next)} required disabled={!canEdit} error={errorFor(errors, "title")} candidateCount={candidateCount(candidates, "title")} onInspect={() => inspectField("title", "题名候选")} /><CanonicalField name="subtitle" label="副题名" value={fieldValue(draft, "subtitle")} onChange={(next) => value("subtitle", next)} disabled={!canEdit} candidateCount={candidateCount(candidates, "subtitle")} onInspect={() => inspectField("subtitle")} /><MultilingualField primary={{ name: "original_title", label: "原题名", value: fieldValue(draft, "original_title"), onChange: (next) => value("original_title", next), disabled: !canEdit }} original={{ name: "uniform_title", label: "规范题名", value: fieldValue(draft, "uniform_title"), onChange: (next) => value("uniform_title", next), disabled: !canEdit }} /><CanonicalField name="document_type" label="文献类型" value={fieldValue(draft, "document_type") || "book"} onChange={(next) => value("document_type", next)} options={documentTypeOptions} required disabled={!canEdit} error={errorFor(errors, "document_type")} /><CanonicalField name="language" label="作品语言" value={fieldValue(draft, "language") || "zh-CN"} onChange={(next) => value("language", next)} options={languageOptions} required disabled={!canEdit} error={errorFor(errors, "language")} /><CanonicalField name="original_language" label="原作语言" value={fieldValue(draft, "original_language")} onChange={(next) => value("original_language", next)} disabled={!canEdit} /><CanonicalField name="first_publication_date" label="首次发表日期" value={fieldValue(draft, "first_publication_date")} onChange={(next) => value("first_publication_date", next)} type="date" disabled={!canEdit} /><CanonicalField name="translation_of" label="译自作品" value={fieldValue(draft, "translation_of")} onChange={(next) => value("translation_of", next)} disabled={!canEdit} help="填写或选择原作关系，不能用版本出版信息替代。" /><CanonicalField name="abstract" label="作品摘要" value={fieldValue(draft, "abstract")} onChange={(next) => value("abstract", next)} multiline rows={6} disabled={!canEdit} candidateCount={candidateCount(candidates, "abstract")} onInspect={() => inspectField("abstract")} /></div></>;
}

function BibliographyBody({ draft, documentType, candidates, canEdit, errors, update, inspectField }: BodyProps) {
  const value = (field: string, next: string) => update("bibliography", field, next);
  const fields = new Set(bibliographyFields(documentType));
  const render = (name: string, label: string, options: Partial<Parameters<typeof CanonicalField>[0]> = {}) => fields.has(name) ? <CanonicalField name={name} label={label} value={fieldValue(draft, name)} onChange={(next) => value(name, next)} disabled={!canEdit} error={errorFor(errors, name)} candidateCount={candidateCount(candidates, name)} onInspect={() => inspectField(name, `${label}候选`)} {...options} /> : null;
  return <ConditionalFieldGroup title={({ book: "图书版本", journal_article: "期刊论文出处", thesis: "学位论文信息", report: "研究报告信息" } as Record<string, string>)[documentType] ?? "版本信息"} description="这里保存 Edition-level metadata，与作品题名和首次发表信息分开。"><div className="workflow-field-grid">{render("version_label", "版本说明")}{render("publication_year", "出版年份", { type: "number" })}{render("publisher", "出版者")}{render("publication_place", "出版地")}{render("isbn10", "ISBN-10")}{render("isbn13", "ISBN-13")}{render("series", "丛书")}{render("extent", "载体范围")}{render("responsibility_statement", "责任说明")}{render("journal_title", "期刊名", { required: documentType === "journal_article" })}{render("volume", "卷")}{render("issue", "期")}{render("page_range", "页码范围")}{render("doi", "DOI")}{render("degree_institution", "学位授予单位", { required: documentType === "thesis" })}{render("degree_type", "学位类型")}{render("report_institution", "报告责任机构", { required: documentType === "report" })}</div></ConditionalFieldGroup>;
}

function ContributorsBody({ draft, candidates, canEdit, errors, update, inspectField }: BodyProps) {
  const items = normalizeItems(draft.items, "display_name");
  return <RepeatableField label="责任者与身份" values={items} create={() => ({ id: null, display_name: "", role: "author", person_id: null, resolution_state: "unresolved", candidate_count: 0 })} onChange={(next) => update("contributors", "items", next)} addLabel="添加责任者" render={(item, index, setItem) => <div className="workflow-contributor-row"><CanonicalField name={`items.${index}.display_name`} label="显示名称" value={asString(item.display_name)} onChange={(next) => setItem({ ...item, display_name: next })} required disabled={!canEdit} error={errorFor(errors, `items.${index}.display_name`)} /><CanonicalField name={`items.${index}.role`} label="角色" value={asString(item.role, "author")} onChange={(next) => setItem({ ...item, role: next })} options={contributorRoleOptions} required disabled={!canEdit} error={errorFor(errors, `items.${index}.role`)} /><CanonicalField name={`items.${index}.person_id`} label="正式 Person link" value={asString(item.person_id)} onChange={(next) => setItem({ ...item, person_id: next || null })} disabled={!canEdit} help={`解析状态 ${asString(item.resolution_state, "unresolved")}`} candidateCount={asNumber(item.candidate_count) || candidates.filter((candidate) => asString(candidate.source_name) === asString(item.display_name)).length} onInspect={() => inspectField(asString(item.display_name), `${asString(item.display_name, "责任者")}的身份候选`)} /></div>} />;
}

function ClassificationBody({ draft, canEdit, errors, update }: BodyProps) {
  return <div className="workflow-classification"><EntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" values={entities(draft.primary_disciplines)} onChange={(next) => update("classification", "primary_disciplines", next.slice(0, 1))} /><EntityPicker label="相关学科" endpoint="/catalog/admin/disciplines/" values={entities(draft.related_disciplines)} onChange={(next) => update("classification", "related_disciplines", next)} /><EntityPicker label="子学科" endpoint="/catalog/admin/subdisciplines/" values={entities(draft.subdisciplines)} onChange={(next) => update("classification", "subdisciplines", next)} /><label className="workflow-section-confirmation" data-field="confirmed"><input type="checkbox" checked={asBoolean(draft.confirmed)} disabled={!canEdit} onChange={(event) => update("classification", "confirmed", event.target.checked)} /><span>我已核对主要学科、相关学科与子学科的区别</span></label>{errorFor(errors, "confirmed") ? <QualityIssue message={errorFor(errors, "confirmed")!} tone="blocker" /> : null}</div>;
}

function KnowledgeBody({ draft, candidates, canEdit, errors, update, inspectField }: BodyProps) {
  const relations = normalizeItems(draft.relations, "name");
  return <><RepeatableField label="正式知识关系" values={relations} create={() => ({ id: null, target_type: "theory", target_id: null, name: "", role: "local_mention", strength: "medium", is_primary: false, review_status: "pending", evidence_summary: "" })} onChange={(next) => update("knowledge", "relations", next)} addLabel="添加理论或主题关系" render={(relation, index, setRelation) => { const targetType = asString(relation.target_type, "theory"); const relationRoleOptions = targetType === "knowledge_node" ? nodeRoleOptions : theoryRoleOptions; const defaultRole = targetType === "knowledge_node" ? "general_mention" : "local_mention"; return <div className="workflow-knowledge-relation"><CanonicalField name={`relations.${index}.target_type`} label="关联对象类型" value={targetType} onChange={(next) => setRelation({ ...relation, target_type: next, role: next === "knowledge_node" ? "general_mention" : "local_mention" })} options={[{ value: "theory", label: "理论" }, { value: "topic", label: "主题" }, { value: "knowledge_node", label: "知识节点" }]} disabled={!canEdit} /><CanonicalField name={`relations.${index}.name`} label="关联对象" value={asString(relation.name)} onChange={(next) => setRelation({ ...relation, name: next })} disabled={!canEdit} candidateCount={candidates.filter((candidate) => asString(candidate.field_name).includes("relation")).length} onInspect={() => inspectField("relations", "知识关系候选")} /><CanonicalField name={`relations.${index}.target_id`} label="正式对象 ID" value={asString(relation.target_id)} onChange={(next) => setRelation({ ...relation, target_id: next || null })} disabled={!canEdit} help="从候选或知识检索选择正式对象后保存；名称本身不会自动创建正式关系。" /><CanonicalField name={`relations.${index}.role`} label="作品角色" value={asString(relation.role, defaultRole)} onChange={(next) => setRelation({ ...relation, role: next })} options={relationRoleOptions} disabled={!canEdit || targetType === "topic"} /><CanonicalField name={`relations.${index}.strength`} label="关联强度" value={asString(relation.strength, "medium")} onChange={(next) => setRelation({ ...relation, strength: next })} options={strengthOptions} disabled={!canEdit} /><label className="workflow-checkbox"><input type="checkbox" checked={asBoolean(relation.is_primary)} disabled={!canEdit} onChange={(event) => setRelation({ ...relation, is_primary: event.target.checked })} /><span>主要关系</span></label><CanonicalField name={`relations.${index}.evidence_summary`} label="证据摘要" value={asString(relation.evidence_summary ?? relation.evidence_text)} onChange={(next) => setRelation({ ...relation, evidence_summary: next })} multiline rows={3} disabled={!canEdit} help={`审核状态 ${asString(relation.review_status, "pending")}`} /></div>; }} /><label className="workflow-section-confirmation" data-field="confirmed"><input type="checkbox" checked={asBoolean(draft.confirmed)} disabled={!canEdit} onChange={(event) => update("knowledge", "confirmed", event.target.checked)} /><span>我已核对正式 Theory、Topic 与 KnowledgeNode 关系</span></label>{errorFor(errors, "confirmed") ? <QualityIssue message={errorFor(errors, "confirmed")!} tone="blocker" /> : null}</>;
}

function FileBody({ draft, context, canEdit, errors, inspectPdf, fileAction }: BodyProps) {
  const status = asString(draft.status, "pending");
  return <div className="workflow-file-summary"><dl><div><dt>文件</dt><dd>{asString(draft.filename ?? context.filename, "未建立")}</dd></div><div><dt>处理状态</dt><dd>{r2StagingStatusLabel(status)}</dd></div><div><dt>PDF 校验</dt><dd>{asString(draft.validation, "pending")}</dd></div><div><dt>页数</dt><dd>{asNumber(draft.page_count)}</dd></div><div><dt>文字类型</dt><dd>{asString(draft.text_profile, "待识别")}</dd></div><div><dt>OCR 策略</dt><dd>{asString(draft.ocr_strategy, "auto")}</dd></div><div><dt>重复判断</dt><dd>{draft.exact_duplicate ? "发现完全重复文件" : asString(draft.duplicate_status, "未发现完全重复")}</dd></div></dl>{errors.map((error) => <QualityIssue message={error.message} tone="blocker" key={`${error.field}-${error.message}`} />)}<div className="workflow-file-actions"><button type="button" onClick={inspectPdf}><Eye size={14} />检查 PDF</button>{draft.can_retry ? <button type="button" disabled={!canEdit} onClick={() => fileAction("retry")}><RefreshCw size={14} />{asString(draft.retry_label, "重试")}</button> : null}{draft.can_resume ? <button type="button" disabled={!canEdit} onClick={() => fileAction("resume")}><Upload size={14} />继续处理</button> : null}{draft.can_replace ? <label className="button secondary"><span>替换 PDF</span><input className="sr-only" type="file" accept="application/pdf,.pdf" disabled={!canEdit} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) fileAction("replace", file); event.currentTarget.value = ""; }} /></label> : null}</div>{draft.error_message ? <details open><summary>技术错误</summary><pre>{asString(draft.error_code)} {asString(draft.error_message)}</pre></details> : null}</div>;
}

function ReaderBody({ draft, canEdit, update, inspectPdf }: BodyProps) {
  const label = (value: unknown, fallback = "待检查") => ({ pending: "等待处理", running: "处理中", succeeded: "已完成", failed: "失败", not_required: "无需处理", disabled: "已停用", ready: "已就绪", needs_review: "需要校对", not_indexed: "尚未建立" } as Record<string, string>)[asString(value)] ?? asString(value, fallback);
  return <div className="workflow-reader"><div className="workflow-reader-states"><article><strong>原始阅读文件</strong><span>{label(draft.original_asset_status)}</span></article><article><strong>全文文字层</strong><span>{label(draft.text_layer_status ?? draft.ocr_status)}</span></article><article><strong>引用页码</strong><span>{label(draft.page_label_status)}</span></article><article><strong>观点检索</strong><span>{label(draft.semantic_index_status)}</span></article></div><CanonicalField name="reader_rendition_policy" label="阅读文件策略" value={fieldValue(draft, "reader_rendition_policy") || "auto"} onChange={(next) => update("reader", "reader_rendition_policy", next)} options={[{ value: "auto", label: "自动，优先稳定可读文件" }, { value: "original", label: "原始 PDF" }, { value: "ocr", label: "优先已验证 OCR PDF" }]} disabled={!canEdit} help="语义索引等后台任务失败不会把已经可阅读的馆藏标为不能发布。" /><button type="button" onClick={inspectPdf}><Eye size={14} />打开文件检查器</button></div>;
}

function PublicationBody({ draft, context, permissions, goToIssue, publish, withdraw, publishing }: BodyProps) {
  const preflight = asRecord(draft.preflight ?? draft);
  const blockers = asArray(preflight.blockers).map((entry) => normalizeIssue(entry, "publication"));
  const warnings = asArray(preflight.warnings).map((entry) => normalizeIssue(entry, "publication"));
  const tasks = asArray(preflight.background_tasks).map((entry) => normalizeIssue(entry, "publication"));
  const canPublish = permissions.can_manage_publication !== false && permissions.can_publish !== false;
  const publicationState = asString(draft.publication_state ?? context.publication_state, "draft");
  return <div className="workflow-publication"><div className="workflow-publication-summary"><article><strong>公开状态</strong><span>{publicationState}</span></article><article><strong>阅读文件</strong><span>{asString(draft.reader_state, "待检查")}</span></article><article><strong>策展</strong><span>{asString(draft.curation_summary, "可选，未策展不阻止发布")}</span></article></div><div className="workflow-preflight-groups"><section className="blockers"><h3>必须解决</h3>{blockers.map((issue) => <QualityIssue key={issue.code || issue.message} message={issue.message} tone="blocker" onActivate={() => goToIssue(issue)} />)}{!blockers.length ? <p>没有发布阻止项。</p> : null}</section><section className="warnings"><h3>建议处理</h3>{warnings.map((issue) => <QualityIssue key={issue.code || issue.message} message={issue.message} tone="warning" onActivate={() => goToIssue(issue)} />)}{!warnings.length ? <p>没有发布警告。</p> : null}</section><section className="tasks"><h3>发布后继续处理</h3>{tasks.map((issue) => <QualityIssue key={issue.code || issue.message} message={issue.message} tone="info" onActivate={() => goToIssue(issue)} />)}{!tasks.length ? <p>没有后台任务。</p> : null}</section></div><div className="workflow-publication-actions">{publicationState === "published" ? <><span>当前版本已公开。后续元数据、知识和策展维护继续使用本编辑器。</span><button className="button secondary" type="button" disabled={!canPublish || publishing} onClick={withdraw}>下架当前版本</button></> : <><button className="button" type="button" disabled={!canPublish || blockers.length > 0 || publishing} onClick={() => publish("next")}>{publishing ? <LoaderCircle className="spin" size={14} /> : <Check size={14} />}发布并处理下一项</button><button className="button secondary" type="button" disabled={!canPublish || blockers.length > 0 || publishing} onClick={() => publish("stay")}>发布并留在当前项</button></>}</div>{!canPublish ? <p>当前账户可以查看检查结果，但最终发布由具有对应 capability 的管理员完成。</p> : null}</div>;
}

function WorkflowSectionBody(props: BodyProps) {
  if (props.step === "file") return <FileBody {...props} />;
  if (props.step === "work") return <WorkBody {...props} />;
  if (props.step === "bibliography") return <BibliographyBody {...props} />;
  if (props.step === "contributors") return <ContributorsBody {...props} />;
  if (props.step === "classification") return <ClassificationBody {...props} />;
  if (props.step === "knowledge") return <KnowledgeBody {...props} />;
  if (props.step === "reader") return <ReaderBody {...props} />;
  if (props.step === "curation") return <WorkCurationEditor workId={asString(props.context.work_id)} value={props.draft} canManage={props.permissions.can_manage_curation !== false} onChange={props.curationChange} onConfirm={props.curationConfirm} onSkip={props.curationSkip} onRefresh={props.refresh} onMessage={props.message} />;
  return <PublicationBody {...props} />;
}

export function WorkflowEditor({ mode, itemId, workId }: { mode: EditorMode; itemId?: string; workId?: string }) {
  const endpoint = mode === "intake"
    ? `/catalog/admin/intake/${encodeURIComponent(itemId ?? "")}/`
    : `/catalog/admin/library/works/${encodeURIComponent(workId ?? "")}/`;
  const [payload, setPayload] = useState<WorkflowPayload | null>(null);
  const [drafts, setDrafts] = useState<WorkflowDrafts | null>(null);
  const [dirty, setDirty] = useState<DirtyFields>({});
  const [active, setActive] = useState<WorkflowStepKey>("file");
  const [validation, setValidation] = useState<Partial<Record<WorkflowStepKey, ValidationIssue[]>>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [inspector, setInspector] = useState<InspectorSelection | null>(null);
  const [publishConfirmation, setPublishConfirmation] = useState<"next" | "stay" | null>(null);
  const draftsRef = useRef<WorkflowDrafts | null>(null);
  const dirtyRef = useRef<DirtyFields>({});
  const token = getServerSessionCredential();
  const currentDirtyCount = dirtyFieldCount(dirty);

  useEffect(() => { draftsRef.current = drafts; }, [drafts]);
  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);

  const applyRemote = useCallback((raw: unknown, preserveDirty: boolean) => {
    const nextPayload = normalizePayload(raw, mode, itemId, workId);
    const remoteDrafts = draftsFromPayload(nextPayload);
    setPayload(nextPayload);
    setDrafts((current) => preserveDirty && current ? mergeRemoteDrafts(current, remoteDrafts, dirtyRef.current) : remoteDrafts);
    setActive((current) => {
      if (typeof window !== "undefined") return stepFromHash(window.location.hash, current || nextPayload.workflow.current_step);
      return current || nextPayload.workflow.current_step;
    });
  }, [itemId, mode, workId]);

  const refresh = useCallback(async (preserveDirty = true) => {
    if (!token || (mode === "intake" ? !itemId : !workId)) return;
    try {
      const result = await apiRequest(endpoint, {}, token);
      applyRemote(result, preserveDirty);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "馆藏工作读取失败。");
    } finally {
      setLoading(false);
    }
  }, [applyRemote, endpoint, itemId, mode, token, workId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(false), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    const onHashChange = () => setActive((current) => stepFromHash(window.location.hash, current));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirtyFieldCount(dirtyRef.current)) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, []);

  const goToStep = useCallback((step: WorkflowStepKey, focusField?: string) => {
    setActive(step);
    window.history.replaceState(null, "", workflowHashUrl(window.location.href, step));
    window.requestAnimationFrame(() => {
      document.getElementById(`workflow-section-${step}`)?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
      if (focusField) window.setTimeout(() => document.querySelector<HTMLElement>(`#workflow-section-${step} [data-field="${CSS.escape(focusField)}"] input, #workflow-section-${step} [data-field="${CSS.escape(focusField)}"] select, #workflow-section-${step} [data-field="${CSS.escape(focusField)}"] textarea`)?.focus(), 180);
    });
  }, []);

  const update: SectionUpdate = useCallback((step, field, value) => {
    setDrafts((current) => current ? { ...current, [step]: { ...current[step], [field]: value } } : current);
    setDirty((current) => withDirtyField(current, step, field));
    setValidation((current) => ({ ...current, [step]: (current[step] ?? []).filter((issue) => issue.field !== field) }));
  }, []);

  const allCandidates = useMemo(() => candidateList(payload?.candidates), [payload?.candidates]);
  const inspectField = useCallback((field: string, title = "字段候选与证据") => {
    const items = allCandidates.filter((candidate) => candidateMatches(candidate, field) || asString(candidate.source_name) === field);
    setInspector({ kind: "candidate", title, description: "候选不会自动成为正式知识。请核对来源和冲突后作出决定。", items });
  }, [allCandidates]);

  const inspectPdf = useCallback(() => {
    const previewUrl = asString(payload?.context.preview_url) || (itemId ? `/ingestion/items/${itemId}/preview/` : "");
    setInspector({ kind: "pdf", title: "PDF 与阅读文件检查", pdfUrl: previewUrl });
  }, [itemId, payload?.context.preview_url]);

  const focusFirstIssue = useCallback((step: WorkflowStepKey, issues: ValidationIssue[]) => {
    const first = issues[0];
    if (first) goToStep(step, first.field);
  }, [goToStep]);

  const saveStep = useCallback(async (step: WorkflowStepKey, advance: boolean) => {
    if (!payload || !draftsRef.current || !token) return;
    if (payload.workflow.steps.find((entry) => entry.key === step)?.status === "pending") {
      setMessage("请先完成前置步骤；当前内容可查看，但尚不能保存。");
      goToStep(step);
      return;
    }
    const draft = draftsRef.current[step];
    const documentType = asString(draftsRef.current.work.document_type, asString(payload.context.document_type, "book"));
    const issues = validateWorkflowSection(step, draft, documentType);
    setValidation((current) => ({ ...current, [step]: issues }));
    if (issues.length) {
      setMessage(issues[0].message);
      focusFirstIssue(step, issues);
      return;
    }
    setBusy(`save-${step}`);
    try {
      const result = await apiRequest(`${endpoint}sections/${step}/`, { method: "PATCH", body: JSON.stringify({ data: draft, confirm_section: true }) }, token);
      const nextPayload = normalizePayload(result, mode, itemId, workId);
      setDirty((current) => ({ ...current, [step]: [] }));
      dirtyRef.current = { ...dirtyRef.current, [step]: [] };
      applyRemote(result, true);
      const backendStep = nextPayload.workflow.steps.find((entry) => entry.key === step);
      const blockers = backendStep?.issues.filter((issue) => issue.severity === "blocker") ?? [];
      if (blockers.length || backendStep?.status === "blocked") {
        const first = blockers[0];
        setMessage(first?.message || "本节仍有必须解决的问题。");
        goToStep(step, first?.field);
        return;
      }
      setMessage(advance ? "本节已确认，已进入下一步骤。" : "本节已保存。");
      if (advance) {
        const next = nextPayload.workflow.current_step !== step
          ? nextPayload.workflow.current_step
          : nextPayload.workflow.suggested_next_step ?? nextWorkflowStep(step, nextPayload.workflow.steps);
        if (next) goToStep(next);
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "本节保存失败。");
      goToStep(step);
    } finally {
      setBusy("");
    }
  }, [applyRemote, endpoint, focusFirstIssue, goToStep, itemId, mode, payload, token, workId]);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLocaleLowerCase() !== "s") return;
      event.preventDefault();
      void saveStep(active, false);
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [active, saveStep]);

  useEffect(() => {
    if (!payload) return;
    window.dispatchEvent(new CustomEvent("admin-workflow-context", { detail: { active: true, title: payload.context.title, workflow: payload.workflow, dirtyCount: currentDirtyCount } }));
    return () => {
      window.dispatchEvent(new CustomEvent("admin-workflow-context", { detail: { active: false } }));
    };
  }, [currentDirtyCount, payload]);

  const fileAction = useCallback(async (action: "retry" | "resume" | "replace", file?: File) => {
    if (!token || !itemId) return;
    setBusy(`file-${action}`);
    try {
      const options: RequestInit = { method: "POST" };
      if (file) { const body = new FormData(); body.append("file", file); options.body = body; }
      await apiRequest(`/ingestion/items/${itemId}/${action}/`, options, token);
      setMessage(action === "replace" ? "替换文件已进入处理队列，旧文件会保留到新文件就绪。" : "文件处理任务已重新排队。");
      await refresh(true);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "文件操作失败。");
    } finally { setBusy(""); }
  }, [itemId, refresh, token]);

  const skipCuration = useCallback(async () => {
    if (!token || !draftsRef.current) return;
    setBusy("skip-curation");
    try {
      const result = await apiRequest(`${endpoint}sections/curation/`, { method: "PATCH", body: JSON.stringify({ data: { ...draftsRef.current.curation, skipped: true }, skip: true, confirm_section: true }) }, token);
      setDirty((current) => ({ ...current, curation: [] }));
      dirtyRef.current = { ...dirtyRef.current, curation: [] };
      const nextPayload = normalizePayload(result, mode, itemId, workId);
      applyRemote(result, true);
      setMessage("已暂不策展。它不会成为发布阻止项。");
      goToStep(
        nextPayload.workflow.current_step === "curation"
          ? "publication"
          : nextPayload.workflow.current_step,
      );
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "暂不策展操作失败。");
    } finally { setBusy(""); }
  }, [applyRemote, endpoint, goToStep, itemId, mode, token, workId]);

  const goToIssue = useCallback((issue: WorkflowIssue) => {
    let step = issue.step;
    let field = issue.field;
    if (typeof issue.action_target === "string") {
      const [targetStep, targetField] = issue.action_target.replace(/^#/, "").split(":");
      if (isWorkflowStepKey(targetStep)) step = targetStep;
      field = targetField || field;
    } else if (issue.action_target) {
      if (isWorkflowStepKey(issue.action_target.step)) step = issue.action_target.step;
      field = issue.action_target.field || field;
    }
    goToStep(step ?? "publication", field);
  }, [goToStep]);

  const performPublish = useCallback(async (intent: "next" | "stay", confirmWarnings: boolean) => {
    if (!payload || !token) return;
    const publication = draftsRef.current?.publication ?? {};
    const preflight = asRecord(publication.preflight ?? publication);
    if (asArray(preflight.blockers).length) {
      setMessage("仍有必须解决的发布问题。");
      goToStep("publication");
      return;
    }
    if (asArray(preflight.warnings).length && !confirmWarnings) {
      setPublishConfirmation(intent);
      return;
    }
    setBusy("publish");
    try {
      const publishEndpoint = mode === "intake"
        ? `/ingestion/items/${encodeURIComponent(asString(payload.context.item_id ?? itemId))}/publish/`
        : `/catalog/admin/library/works/${encodeURIComponent(asString(payload.context.work_id ?? workId))}/publication/`;
      const result = asRecord(await apiRequest(publishEndpoint, { method: "POST", body: JSON.stringify({ confirm_warnings: confirmWarnings, after_publish: intent }) }, token));
      setPublishConfirmation(null);
      const nextTarget = asRecord(result.next_target);
      if (intent === "next") {
        const nextItem = asString(nextTarget.item_id ?? result.next_item_id ?? payload.queue.next_item_id);
        const nextWork = asString(nextTarget.work_id ?? result.next_work_id ?? payload.queue.next_work_id);
        if (nextItem) { window.location.assign(`/admin/intake/${nextItem}#file`); return; }
        if (nextWork) { window.location.assign(`/admin/library/works/${nextWork}#work`); return; }
        window.location.assign(asString(payload.queue.return_href ?? payload.context.return_href, "/admin/review"));
        return;
      }
      const maintenanceUrl = asString(result.maintenance_url);
      const publishedWorkId = asString(asRecord(result.context).work_id ?? result.work_id ?? payload.context.work_id ?? workId);
      if (maintenanceUrl) { window.location.replace(maintenanceUrl); return; }
      if (mode === "intake" && publishedWorkId) { window.location.replace(`/admin/library/works/${publishedWorkId}#publication`); return; }
      applyRemote(result, true);
      setMessage("馆藏已发布，当前编辑器已切换为发布后维护状态。");
      goToStep("publication");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "发布失败。");
    } finally { setBusy(""); }
  }, [applyRemote, goToStep, itemId, mode, payload, token, workId]);

  const performWithdraw = useCallback(async () => {
    if (!payload || !token || !window.confirm("确认下架当前版本吗？文件、审核记录和历史版本会继续保留。")) return;
    setBusy("publish");
    try {
      if (mode === "intake") {
        await apiRequest(
          `/ingestion/items/${encodeURIComponent(asString(payload.context.item_id ?? itemId))}/withdraw/`,
          { method: "POST", body: JSON.stringify({ reason: "管理员在 2.8 馆藏工作流中下架" }) },
          token,
        );
        await refresh(true);
      } else {
        const result = await apiRequest(
          `/catalog/admin/library/works/${encodeURIComponent(asString(payload.context.work_id ?? workId))}/publication/`,
          { method: "POST", body: JSON.stringify({ action: "withdraw", reason: "管理员在 2.8 馆藏工作流中下架" }) },
          token,
        );
        applyRemote(result, true);
      }
      setMessage("当前版本已下架，文件与历史记录保持不变。");
      goToStep("publication");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "下架失败。");
    } finally {
      setBusy("");
    }
  }, [applyRemote, goToStep, itemId, mode, payload, refresh, token, workId]);

  const decideCandidate = useCallback(async (candidate: WorkflowCandidate, action: string) => {
    if (!candidate.decision_url || !token) {
      setMessage("该候选没有提供安全的决定入口，请刷新后重试。");
      return;
    }
    setBusy(`candidate-${candidate.id}`);
    try {
      const entityTargetType = asString(candidate.target_type ?? candidate.candidate_entity_type);
      const entityTargetId = asString(candidate.candidate_entity_id);
      const body = entityTargetType
        ? {
            action,
            target_type: entityTargetType,
            target_id: action === "link_existing" ? entityTargetId || null : null,
            confirm_identity: action === "link_existing",
            reason: "馆藏工作流中的管理员决定",
          }
        : { action };
      await apiRequest(candidate.decision_url, { method: "POST", body: JSON.stringify(body) }, token);
      setMessage("候选决定已写入审计记录。");
      await refresh(true);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "候选决定失败。");
    } finally { setBusy(""); }
  }, [refresh, token]);

  const exit = useCallback((href: string) => {
    if (dirtyFieldCount(dirtyRef.current) && !window.confirm("当前工作仍有未保存修改。确认离开吗？")) return;
    window.location.assign(href);
  }, []);

  if (loading && !payload) return <div className="admin-page admin-loading"><LoaderCircle className="spin" size={24} /><strong>正在建立馆藏工作上下文……</strong></div>;
  if (!payload || !drafts) return <div className="admin-page workflow-load-error"><h1>无法打开馆藏工作</h1><p>{message || "没有返回可编辑数据。"}</p><button type="button" onClick={() => void refresh(false)}>重试</button></div>;

  const documentType = asString(drafts.work.document_type, asString(payload.context.document_type, "book"));
  const presentations = sectionPresentations(payload.workflow.steps, active);
  const activeStepPending = payload.workflow.steps.find((step) => step.key === active)?.status === "pending";
  const returnHref = asString(payload.queue.return_href ?? payload.context.return_href, mode === "intake" ? "/admin/review" : "/admin/library");
  const canEdit = payload.permissions.can_edit !== false;
  return (
    <div className="workflow-editor" data-workflow-mode={payload.mode}>
      <WorkflowStepRail title={asString(payload.context.title)} filename={asString(payload.context.filename)} steps={payload.workflow.steps} active={active} unresolvedCount={payload.workflow.unresolved_count} dirtyCount={currentDirtyCount} returnHref={returnHref} onStep={goToStep} onExit={exit} />
      <main className="workflow-editor-main">
        <header className="workflow-editor-header"><div><p>{payload.mode === "intake" ? "上架工作" : "馆藏维护"}</p><h1>{asString(payload.context.title, "未命名馆藏")}</h1><span>{payload.workflow.blockers_count} 个必须解决 · {payload.workflow.warnings_count} 个建议 · {currentDirtyCount} 项未保存</span></div><div><button type="button" onClick={() => void refresh(true)} disabled={Boolean(busy)}><RefreshCw size={14} />刷新</button><button type="button" onClick={() => void saveStep(active, false)} disabled={Boolean(busy) || !canEdit || activeStepPending}><Save size={14} />保存</button><button type="button" onClick={inspectPdf}><Eye size={14} />PDF</button>{payload.context.public_url ? <Link className="workflow-header-preview" href={asString(payload.context.public_url)} target="_blank">公开预览</Link> : null}</div></header>
        {message ? <p className="workflow-editor-message" role="status">{message}</p> : null}
        <div className="workflow-sections">{payload.workflow.steps.map((step) => {
          const presentation = presentations[step.key];
          const expanded = presentation === "current";
          const localErrors = validation[step.key] ?? [];
          const sectionCanEdit = canEdit && step.status !== "pending";
          return <section className={`workflow-section presentation-${presentation} status-${step.status}`} id={`workflow-section-${step.key}`} key={step.key} data-step={step.key}><button className="workflow-section-heading" type="button" aria-expanded={expanded} onClick={() => goToStep(step.key)}><span>{step.status === "complete" || step.status === "skipped" ? <Check size={15} /> : expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</span><div><small>{statusLabel(step.status)}</small><h2>{step.label}</h2>{presentation === "summary" ? <p>{typeof step.summary === "string" ? step.summary : summaryFor(step.key, drafts[step.key])}</p> : presentation === "preview" ? <p>{step.next_action || "完成当前步骤后继续处理。"}</p> : null}</div><b>{step.issues.length ? `${step.issues.length} 项` : ""}</b></button>{expanded ? <div className="workflow-section-content">{step.key !== "publication" ? <div className="workflow-backend-issues">{step.issues.map((issue) => <QualityIssue key={issue.code || issue.message} message={issue.message} tone={issue.severity === "blocker" ? "blocker" : issue.severity === "info" ? "info" : "warning"} onActivate={() => goToIssue(issue)} />)}</div> : null}<WorkflowSectionBody step={step.key} draft={drafts[step.key]} documentType={documentType} candidates={allCandidates} canEdit={sectionCanEdit} context={payload.context} permissions={payload.permissions} errors={localErrors} update={update} inspectField={inspectField} inspectPdf={inspectPdf} fileAction={fileAction} curationChange={(value) => setDrafts((current) => current ? { ...current, curation: value } : current)} curationConfirm={() => void saveStep("curation", true)} curationSkip={() => void skipCuration()} refresh={() => void refresh(true)} message={setMessage} goToIssue={goToIssue} publish={(intent) => void performPublish(intent, false)} withdraw={() => void performWithdraw()} publishing={busy === "publish"} />{step.key !== "publication" && step.key !== "curation" ? <footer className="workflow-section-actions"><button className="button secondary" type="button" disabled={Boolean(busy) || !sectionCanEdit} onClick={() => void saveStep(step.key, false)}><Save size={14} />保存</button><button className="button" type="button" disabled={Boolean(busy) || !sectionCanEdit} onClick={() => void saveStep(step.key, true)}>{busy === `save-${step.key}` ? <LoaderCircle className="spin" size={14} /> : <FileCheck2 size={14} />}保存并继续</button></footer> : null}</div> : null}</section>;
        })}</div>
      </main>
      <WorkflowInspector selection={inspector} token={token} onClose={() => setInspector(null)} onDecision={(candidate, action) => void decideCandidate(candidate, action)} />
      {publishConfirmation ? <div className="workflow-modal-backdrop"><div className="workflow-publication-confirmation" role="dialog" aria-modal="true" aria-labelledby="workflow-publish-confirm-title"><AlertTriangle size={21} /><div><h2 id="workflow-publish-confirm-title">确认带警告发布</h2><p>警告不会阻止发布。OCR、页码和语义索引等后台任务会继续处理，原始 PDF 不会被覆盖。</p></div><footer><button className="button secondary" type="button" onClick={() => setPublishConfirmation(null)}>取消</button><button className="button" type="button" onClick={() => void performPublish(publishConfirmation, true)}>确认发布</button></footer></div></div> : null}
      {busy === "skip-curation" ? <span className="sr-only" aria-live="polite">正在保存暂不策展决定</span> : null}
      <span className="sr-only" aria-live="polite">{currentDirtyCount ? `${currentDirtyCount} 项未保存` : "所有修改已保存"}</span>
    </div>
  );
}
