"use client";

import { AlertTriangle, Check, ChevronDown, ChevronRight, Eye, FileCheck2, LoaderCircle, RefreshCw, Save, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActionButton, ActionLink, AsyncStatus, type ActionState } from "@/components/action-feedback";
import { apiBlob, apiRequest, getServerSessionCredential } from "@/lib/api";
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
import { buildCandidateActionBody, type CandidateActionDescriptor } from "../research/candidate-action-contract";
import { ResearchSuggestionCapabilityContext } from "../research/research-suggestion-panel";
import { RESEARCH_SUGGESTION_REFRESH_EVENT } from "../research/research-suggestion-state";
import { ResearchWorkspaceContext } from "../research/research-workspace-context";
import {
  WORKFLOW_STEP_KEYS,
  WORKFLOW_STEP_LABELS,
  WORKBENCH_STEP_KEYS,
  bibliographyFields,
  dirtyFieldCount,
  invalidatedResearchFields,
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
  asNumber,
  asRecord,
  asString,
  candidateList,
  normalizeEditorialRevision,
  type WorkflowCandidate,
  type WorkflowDrafts,
  type WorkflowEvaluation,
  type WorkflowIssue,
  type WorkflowPayload,
  type WorkflowStep,
} from "./workflow-types";
import { WorkflowStepRail } from "./workflow-step-rail";
import { FieldAssistantControl, type AssistantFieldName } from "./field-assistant-control";
import { PublicationRetryControl } from "./publication-retry-control";
import { assistantCacheKey, cachedAssistantRequest, invalidateAssistantCache, lookupFieldSuggestions } from "./field-assistant-cache";

type EditorMode = "intake" | "maintenance";
type SectionUpdate = (step: WorkflowStepKey, field: string, value: unknown) => void;

const documentTypeOptions = [
  { value: "book", label: "图书" },
  { value: "journal_article", label: "期刊论文" },
  { value: "journal_issue", label: "整期期刊" },
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
  { value: "chief_editor", label: "主编" },
  { value: "editor", label: "编者" },
  { value: "translator", label: "译者" },
  { value: "annotator", label: "校注" },
  { value: "photographer", label: "摄影" },
  { value: "advisor", label: "导师" },
  { value: "subject", label: "研究对象" },
  { value: "other", label: "其他贡献者" },
] as const;

function contributorRoleLabel(role: string) {
  return contributorRoleOptions.find((option) => option.value === role)?.label ?? "其他贡献者";
}

function createDraftSessionId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

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
  const backendCurrent = isWorkflowStepKey(row.current_step) ? row.current_step : "file";
  const current = backendCurrent === "knowledge" ? "curation" : backendCurrent;
  const rawSteps = asArray(row.steps);
  const supplied = new Map<WorkflowStepKey, WorkflowStep>();
  let legacyKnowledgeStep: WorkflowStep | null = null;
  rawSteps.forEach((entry) => {
    const step = asRecord(entry);
    if (!isWorkflowStepKey(step.key)) return;
    const stepKey = step.key;
    const statusValue = asString(step.status, "pending") as WorkflowStepStatus;
    const normalizedStep: WorkflowStep = {
      key: stepKey,
      label: WORKFLOW_STEP_LABELS[stepKey],
      status: statusValue,
      issues: asArray(step.issues).map((issue) => normalizeIssue(issue, stepKey)),
      summary: step.summary as WorkflowStep["summary"],
      next_action: asString(step.next_action) || asString(asRecord(step.next_action).label) || null,
    };
    if (stepKey === "knowledge") legacyKnowledgeStep = normalizedStep;
    else supplied.set(stepKey, normalizedStep);
  });
  const absorbedKnowledgeStep = legacyKnowledgeStep as WorkflowStep | null;
  if (absorbedKnowledgeStep) {
    const curation = supplied.get("curation") ?? blankStep("curation", current);
    supplied.set("curation", {
      ...curation,
      status: backendCurrent === "knowledge" ? absorbedKnowledgeStep.status : curation.status,
      issues: [
        ...absorbedKnowledgeStep.issues.map((issue) => ({ ...issue, step: "curation" as const })),
        ...curation.issues,
      ],
      summary: curation.summary ?? absorbedKnowledgeStep.summary,
      next_action: curation.next_action ?? absorbedKnowledgeStep.next_action,
    });
  }
  return {
    overall_status: asString(row.overall_status, "working"),
    current_step: current,
    suggested_next_step: isWorkflowStepKey(row.suggested_next_step)
      ? row.suggested_next_step === "knowledge" ? "curation" : row.suggested_next_step
      : null,
    steps: WORKBENCH_STEP_KEYS.map((key) => supplied.get(key) ?? blankStep(key, current)),
    unresolved_count: asNumber(row.unresolved_count),
    warnings_count: asNumber(row.warnings_count),
    blockers_count: asNumber(row.blockers_count),
    absorbed_legacy_knowledge_status: absorbedKnowledgeStep?.status,
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
    editorial_revision: normalizeEditorialRevision(root.editorial_revision),
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
    knowledge: {
      ...knowledge,
      relations: normalizeItems(knowledge.relations, "name"),
      theories: normalizeItems(knowledge.theories, "name"),
      topics: normalizeItems(knowledge.topics, "name"),
      nodes: Array.isArray(knowledge.nodes) ? normalizeItems(knowledge.nodes, "name") : asArray(knowledge.node_relations).map((entry) => {
        const row = asRecord(entry);
        return { ...row, id: row.node_id, name: row.node__canonical_name_zh, evidence_asset: row.evidence_asset_id ?? null };
      }),
    },
    reader: { ...asRecord(data.reader) },
    curation: { ...asRecord(data.curation) },
    publication: { ...asRecord(data.publication) },
  };
}

function fieldValue(section: Record<string, unknown>, name: string): string {
  const value = section[name];
  return typeof value === "number" ? String(value) : asString(value);
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
  if (step === "contributors") return `${normalizeItems(draft.items, "display_name").length} 位作者、译者及其他贡献者`;
  if (step === "classification") return `${normalizeItems(draft.primary_disciplines, "name").length} 个主要学科`;
  if (step === "knowledge") return `${normalizeItems(draft.relations, "name").length} 条正式关系`;
  if (step === "reader") return [draft.readable ? "可阅读" : "待检查", draft.text_layer_status, draft.page_label_status].filter(Boolean).map(String).join(" · ");
  if (step === "curation") return draft.skipped ? "已暂不策展" : `${normalizeItems(draft.reading_path_placements ?? draft.placements, "name").length} 个阅读路径位置`;
  return asString(draft.publication_state ?? draft.status, "待发布检查");
}

function statusLabel(status: string) {
  return ({ pending: "待处理", available: "可处理", working: "处理中", attention: "需注意", blocked: "被阻止", complete: "已完成", skipped: "已跳过" } as Record<string, string>)[status] ?? status;
}

function workflowMessageState(message: string): ActionState {
  if (!message) return "idle";
  return /(失败|无法|不能|错误|缺少|仍有|请先|未完成|没有提供)/.test(message)
    ? "error"
    : "success";
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
  curationConfirm: () => Promise<void>;
  curationSkip: () => Promise<void>;
  refresh: () => Promise<boolean>;
  message: (value: string) => void;
  goToIssue: (issue: WorkflowIssue) => void;
  saveDraft: () => void;
  beforeFieldAction: () => Promise<boolean>;
  assistantContextKey: string;
  knowledgeDraft: Record<string, unknown>;
  confirmKnowledge: () => Promise<void>;
  preview: () => void;
  preflight: () => void;
  publish: (intent: "next" | "stay") => void;
  withdraw: () => void;
  publishing: boolean;
  busy: string;
  research: {
    mode: EditorMode;
    itemId?: string;
    workId?: string;
    token: string | null;
    canRun?: boolean;
    suggestions: WorkflowCandidate[];
    onInspect: (items: WorkflowCandidate[], title: string) => void;
    onUpdated: () => Promise<void> | void;
    onMessage: (value: string) => void;
  };
};

function errorFor(errors: ValidationIssue[], field: string) {
  return errors.find((error) => error.field === field)?.message;
}

function candidateCount(candidates: WorkflowCandidate[], field: string) {
  return candidates.filter((candidate) => candidateMatches(candidate, field) && candidate.status !== "rejected").length;
}

function WorkflowFieldAssistant({ fieldName, query, ...props }: BodyProps & { fieldName: AssistantFieldName; query?: string }) {
  return <FieldAssistantControl editionId={asString(props.context.edition_id)} fieldName={fieldName} query={query} token={props.research.token} disabled={!props.canEdit} beforeAction={props.beforeFieldAction} contextKey={props.assistantContextKey} onSaved={async (message) => { props.message(message); await props.research.onUpdated(); }} />;
}

type CoverOption = { id: string; page_index: number; selected: boolean; thumbnail_url: string };

function CoverThumbnail({ option, token }: { option: CoverOption; token: string | null }) {
  const [image, setImage] = useState("");
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    let objectUrl = "";
    if (option.thumbnail_url) void apiBlob(option.thumbnail_url, token).then((blob) => {
      objectUrl = URL.createObjectURL(blob);
      if (alive) setImage(objectUrl);
      else URL.revokeObjectURL(objectUrl);
    }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [option.thumbnail_url, token]);
  return image ? <img src={image} alt={`第 ${option.page_index} 页封面`} style={{ width: "100%", maxHeight: 180, objectFit: "contain" }} /> : <p>{error ? "封面暂时无法显示" : "正在读取封面"}</p>;
}

function CoverField(props: BodyProps) {
  const { context, documentType, canEdit, research, beforeFieldAction, message, assistantContextKey } = props;
  const [options, setOptions] = useState<CoverOption[] | null>(null);
  const [busy, setBusy] = useState("");
  const [more, setMore] = useState(false);
  const workId = asString(context.work_id);
  const editionId = asString(context.edition_id);
  useEffect(() => { setOptions(null); setMore(false); }, [assistantContextKey, editionId]);
  if (!["book", "journal_issue"].includes(documentType)) return null;
  const load = async (regenerate = false) => {
    if (!await beforeFieldAction()) return;
    setBusy("lookup");
    try {
      if (regenerate) invalidateAssistantCache(editionId);
      const result = regenerate
        ? await apiRequest<{ results: CoverOption[] }>(`/catalog/admin/works/${workId}/cover-candidates/`, { method: "POST", body: JSON.stringify({ edition_id: editionId }) }, research.token)
        : await cachedAssistantRequest<{ results: CoverOption[] }>(assistantCacheKey(editionId, "cover", "", assistantContextKey), `/catalog/admin/works/${workId}/cover-candidates/?edition_id=${encodeURIComponent(editionId)}`, {}, research.token);
      setOptions(result.results);
    } catch (reason) { message(reason instanceof Error ? reason.message : "暂时无法查找封面，可以继续使用默认封面。"); }
    finally { setBusy(""); }
  };
  const select = async (option: CoverOption) => {
    if (!await beforeFieldAction()) return;
    setBusy(option.id);
    try {
      await apiRequest(`/catalog/admin/works/${workId}/cover-candidates/${option.id}/select/`, { method: "POST", body: JSON.stringify({ edition_id: context.edition_id }) }, research.token);
      invalidateAssistantCache(editionId);
      setOptions((current) => current?.map((row) => ({ ...row, selected: row.id === option.id })) ?? current);
      await research.onUpdated();
      message("封面选择已保存到当前编辑内容。正式发布后对读者生效。");
    } catch (reason) { message(reason instanceof Error ? reason.message : "封面未保存成功，请重试。"); }
    finally { setBusy(""); }
  };
  return <section className="workflow-cover-field"><header className="workflow-field-assistant-row"><strong>封面</strong><button type="button" disabled={!canEdit || Boolean(busy)} onClick={() => void load()}><Eye size={13} />查找其他封面</button></header><p>优先使用当前文件中的真实封面，也可以继续使用默认封面。</p>{options ? <><div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 16 }}>{(more ? options : options.slice(0, 3)).map((option) => <article key={option.id}><CoverThumbnail option={option} token={research.token} /><small>来自本书第 {option.page_index} 页</small><button type="button" disabled={!canEdit || Boolean(busy) || option.selected} onClick={() => void select(option)}>{option.selected ? "当前选择" : busy === option.id ? "正在保存" : "采用封面"}</button></article>)}</div>{!options.length ? <p>尚未找到合适封面。</p> : null}{options.length > 3 ? <button type="button" onClick={() => setMore((current) => !current)}>{more ? "收起更多封面" : "更多封面"}</button> : null}<button type="button" disabled={!canEdit || Boolean(busy)} onClick={() => void load(true)}>{busy === "lookup" ? "正在查找" : "重新查找本书封面"}</button></> : null}</section>;
}

function KnowledgeFields(props: BodyProps) {
  const { knowledgeDraft, canEdit, update } = props;
  const nodes = entities(knowledgeDraft.nodes);
  const topics = entities(knowledgeDraft.topics);
  return <fieldset className="workflow-field-grid" disabled={!canEdit}>
    <div><div className="workflow-field-assistant-row"><strong>理论传统与理论节点</strong><WorkflowFieldAssistant {...props} fieldName="theory" /></div><EntityPicker label="搜索馆内理论与概念" endpoint="/catalog/admin/theory-system/nodes/" queryParam="q" nameField="canonical_name_zh" values={nodes} onChange={(next) => update("knowledge", "nodes", next.map((item) => ({ role: "general_mention", strength: "medium", ...item })))} /></div>
    <div><div className="workflow-field-assistant-row"><strong>主题</strong><WorkflowFieldAssistant {...props} fieldName="topic" /></div><EntityPicker label="搜索馆内主题" endpoint="/catalog/admin/topics/" values={topics} onChange={(next) => update("knowledge", "topics", next)} /></div>
  </fieldset>;
}

function WorkBody(props: BodyProps) {
  const { draft, candidates, canEdit, errors, update, inspectField, research, documentType } = props;
  const value = (field: string, next: string) => update("work", field, next);
  const identityCandidates = candidateCount(candidates, "work");
  const translationId = fieldValue(draft, "translation_of");
  const translationSuggestions = candidates.filter((candidate) => candidateMatches(candidate, "translation_of"));
  const translationName = fieldValue(draft, "translation_of_title") || asString(
    translationSuggestions.find((candidate) => asString(candidate.entity_id ?? candidate.candidate_entity_id ?? asRecord(candidate.proposed_value).id) === translationId)?.label,
    translationId ? "已关联原作" : "",
  );
  return <>{identityCandidates ? <button className="workflow-work-identity" type="button" onClick={() => inspectField("work", "作品身份与版本判断")}><AlertTriangle size={15} /><span><strong>发现 {identityCandidates} 项馆内作品候选</strong><small>请明确选择关联现有作品，或保留当前新作品。系统不会自行合并。</small></span><ChevronRight size={14} /></button> : null}<div className="workflow-field-grid"><CanonicalField name="title" label={documentType === "journal_article" ? "论文标题" : documentType === "journal_issue" ? "本期标题" : "作品题名"} value={fieldValue(draft, "title")} onChange={(next) => value("title", next)} required disabled={!canEdit} error={errorFor(errors, "title")} candidateCount={candidateCount(candidates, "title")} onInspect={() => inspectField("title", "题名候选")} /><CanonicalField name="subtitle" label="副题名" value={fieldValue(draft, "subtitle")} onChange={(next) => value("subtitle", next)} disabled={!canEdit} candidateCount={candidateCount(candidates, "subtitle")} onInspect={() => inspectField("subtitle")} /><MultilingualField primary={{ name: "original_title", label: "原题名", value: fieldValue(draft, "original_title"), onChange: (next) => value("original_title", next), disabled: !canEdit }} original={{ name: "uniform_title", label: "规范题名", value: fieldValue(draft, "uniform_title"), onChange: (next) => value("uniform_title", next), disabled: !canEdit }} /><CanonicalField name="document_type" label="文献类型" value={fieldValue(draft, "document_type") || "book"} onChange={(next) => value("document_type", next)} options={documentTypeOptions} required disabled={!canEdit} error={errorFor(errors, "document_type")} /><CanonicalField name="language" label="作品语言" value={fieldValue(draft, "language") || "zh-CN"} onChange={(next) => value("language", next)} options={languageOptions} required disabled={!canEdit} error={errorFor(errors, "language")} /><CanonicalField name="original_language" label="原作语言" value={fieldValue(draft, "original_language")} onChange={(next) => value("original_language", next)} disabled={!canEdit} /><CanonicalField name="first_publication_date" label="作品首次出版日期" value={fieldValue(draft, "first_publication_date")} onChange={(next) => value("first_publication_date", next)} type="date" disabled={!canEdit} help="记录作品最初问世的时间，不是当前 PDF 所属版本的出版日期。" /><fieldset disabled={!canEdit}><EntityPicker label="译自作品" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" values={translationId ? [{ id: translationId, name: translationName }] : []} onChange={(next) => update("work", "translation_of", next.at(-1)?.id ?? null)} /></fieldset><div><CanonicalField name="abstract" label={documentType === "journal_article" ? "论文摘要" : documentType === "journal_issue" ? "本期简介" : "馆藏简介"} value={fieldValue(draft, "abstract")} onChange={(next) => value("abstract", next)} multiline rows={6} disabled={!canEdit} candidateCount={candidateCount(candidates, "abstract")} onInspect={() => inspectField("abstract")} help="采用前请核对原文与来源。AI 整理内容经管理员确认并发布后才进入馆内知识。" /><WorkflowFieldAssistant {...props} fieldName="abstract" /></div></div><CoverField {...props} /></>;
}

function BibliographyBody(props: BodyProps) {
  const { draft, documentType, canEdit, errors, update } = props;
  const value = (field: string, next: string) => update("bibliography", field, next);
  const fields = new Set(bibliographyFields(documentType));
  const render = (name: string, label: string, options: Partial<Parameters<typeof CanonicalField>[0]> = {}) => fields.has(name) ? <CanonicalField key={name} name={name} label={label} value={fieldValue(draft, name)} onChange={(next) => value(name, next)} disabled={!canEdit} error={errorFor(errors, name)} {...options} /> : null;
  const issue = documentType === "journal_issue";
  return <ConditionalFieldGroup title={({ book: "图书版本", journal_article: "期刊论文出处", journal_issue: "整期期刊", thesis: "学位论文信息", report: "研究报告信息" } as Record<string, string>)[documentType] ?? "版本信息"} description="填写当前文件所属版本的信息。">
    <div className="workflow-field-grid">
      {render("version_label", "版本说明")}
      {render("publication_date", issue ? "本期出版日期" : "本版本出版日期", { type: "date" })}
      <div>{render("publication_year", issue ? "本期年份" : "本版本出版年份", { type: "number" })}<WorkflowFieldAssistant {...props} fieldName="publication_year" query={fieldValue(draft, "publication_year")} /></div>
      {fields.has("publisher") ? <div><CanonicalField name="publisher" label="出版社" value={fieldValue(draft, "publisher")} onChange={(next) => { value("publisher", next); update("bibliography", "publisher_authority_id", null); }} disabled={!canEdit} /><WorkflowFieldAssistant {...props} fieldName="publisher" query={fieldValue(draft, "publisher")} /></div> : null}
      {render("publication_place", "出版地")}{render("isbn10", "ISBN-10")}{render("isbn13", "ISBN-13")}{render("series", "丛书")}
      {render("journal_title", "期刊", { required: ["journal_article", "journal_issue"].includes(documentType) })}
      {render("volume", "卷", { required: issue })}{render("issue", "期", { required: issue })}
      {render("page_range", "页码范围")}{render("doi", "DOI")}
      {render("degree_institution", "学位授予单位", { required: documentType === "thesis" })}{render("degree_type", "学位类型")}
      {render("report_institution", "报告机构", { required: documentType === "report" })}
    </div>
    {issue ? <JournalContentsField {...props} /> : null}
    {fields.has("extent") || fields.has("responsibility_statement") ? <details><summary>高级书目字段</summary><div className="workflow-field-grid">{render("extent", "页数与装帧说明")}{render("responsibility_statement", "贡献说明原文")}</div></details> : null}
  </ConditionalFieldGroup>;
}

function JournalContentsField({ draft, canEdit, errors, update }: BodyProps) {
  const rows = asArray(draft.journal_contents).map(asRecord);
  const change = (next: Record<string, unknown>[]) => update("bibliography", "journal_contents", next.map((row, position) => ({ ...row, position })));
  const move = (index: number, offset: number) => {
    const next = [...rows];
    const destination = index + offset;
    if (destination < 0 || destination >= next.length) return;
    [next[index], next[destination]] = [next[destination], next[index]];
    change(next);
  };
  return <section className="workflow-journal-contents">
    <p>按本期目录顺序填写论文。可关联已入馆论文，也可先保留题名和页码。未发布的论文不会生成公开链接。</p>
    <RepeatableField label="本期目录与论文" values={rows} disabled={!canEdit} create={() => ({ id: null, article_work_id: null, title: "", author_display: "", page_range: "", position: rows.length })} addLabel="添加目录论文" onChange={change} render={(row, index, setRow) => <div>
      <div className="workflow-field-grid">
        <CanonicalField name={`journal_contents.${index}.title`} label={`第 ${index + 1} 篇题名`} value={asString(row.title)} onChange={(title) => setRow({ ...row, title })} disabled={!canEdit} required error={errorFor(errors, `journal_contents.${index}.title`)} />
        <CanonicalField name={`journal_contents.${index}.author_display`} label="作者" value={asString(row.author_display)} onChange={(author_display) => setRow({ ...row, author_display })} disabled={!canEdit} />
        <CanonicalField name={`journal_contents.${index}.page_range`} label="本期页码" value={asString(row.page_range)} onChange={(page_range) => setRow({ ...row, page_range })} disabled={!canEdit} />
        <fieldset disabled={!canEdit}><EntityPicker label="关联馆内论文" endpoint="/catalog/admin/library/works/?document_type=journal_article" queryParam="q" nameField="title" values={row.article_work_id ? [{ id: asString(row.article_work_id), name: asString(row.title, "已关联论文") }] : []} onChange={(values) => { const selected = values.at(-1); setRow({ ...row, article_work_id: selected?.id ?? null, title: asString(row.title).trim() || selected?.name || "" }); }} /></fieldset>
      </div>
      <div className="workflow-section-actions"><button type="button" className="button secondary" disabled={!canEdit || index === 0} onClick={() => move(index, -1)}>上移</button><button type="button" className="button secondary" disabled={!canEdit || index === rows.length - 1} onClick={() => move(index, 1)}>下移</button></div>
    </div>} />
  </section>;
}

function ContributorsBody(props: BodyProps) {
  const { draft, canEdit, errors, update, research, context, beforeFieldAction, assistantContextKey } = props;
  const items = normalizeItems(draft.items, "display_name");
  const authorItems = items.filter((item) => asString(item.role, "author") === "author");
  const translatorItems = items.filter((item) => asString(item.role) === "translator");
  const otherItems = items.filter((item) => !["author", "translator"].includes(asString(item.role, "author")));
  const blank = (role: string) => ({ id: null, display_name: "", role, person_id: null, resolution_state: "unresolved", candidate_count: 0 });
  const replaceRoles = (roles: string[], next: Record<string, unknown>[]) => update("contributors", "items", [
    ...items.filter((item) => !roles.includes(asString(item.role, "author"))),
    ...next,
  ]);
  const renderContributor = (fixedRole: string | undefined, item: Record<string, unknown>, index: number, setItem: (next: Record<string, unknown>) => void) => {
    const role = fixedRole ?? asString(item.role, "editor");
    const name = asString(item.display_name);
    const linked = item.person_id ? [{ id: asString(item.person_id), name }] : [];
    return <div className="workflow-contributor-row"><CanonicalField name={`items.${index}.display_name`} label={`${contributorRoleLabel(role)}姓名`} value={name} onChange={(next) => setItem({ ...item, display_name: next, role })} disabled={!canEdit} error={errorFor(errors, `items.${index}.display_name`)} />{fixedRole ? <div className="workflow-contributor-fixed-role"><span>角色</span><strong>{contributorRoleLabel(role)}</strong></div> : <CanonicalField name={`items.${index}.role`} label="贡献类型" value={role} onChange={(next) => setItem({ ...item, role: next })} options={contributorRoleOptions.filter((option) => !["author", "translator"].includes(option.value))} disabled={!canEdit} />}<div data-field={`items.${index}.person_id`}><fieldset disabled={!canEdit}><EntityPicker label="搜索馆内学者" endpoint="/catalog/admin/scholars/" idField="person_id" nameField="preferred_name" values={linked} onChange={(next) => { const person = next.at(-1); setItem({ ...item, role, person_id: person?.id ?? null, display_name: person?.name || name, resolution_state: person?.id ? "selected" : "unresolved" }); }} /></fieldset>{errorFor(errors, `items.${index}.person_id`) ? <small className="workflow-field-error" role="alert">{errorFor(errors, `items.${index}.person_id`)}</small> : null}</div></div>;
  };
  const editionId = asString(context.edition_id);
  const saved = async (text: string) => { research.onMessage(text); await research.onUpdated(); };
  return <div className="workflow-contributor-groups"><section className="workflow-field-assistant-row"><strong>作者</strong><FieldAssistantControl editionId={editionId} fieldName="author" query={asString(authorItems[0]?.display_name)} token={research.token} disabled={!canEdit} onSaved={saved} beforeAction={beforeFieldAction} contextKey={assistantContextKey} /></section><RepeatableField disabled={!canEdit} label="作者" values={authorItems} emptyValue={blank("author")} create={() => blank("author")} onChange={(next) => replaceRoles(["author"], next)} addLabel="添加作者" render={(item, index, setItem) => renderContributor("author", item, index, setItem)} /><section className="workflow-field-assistant-row"><strong>译者</strong><FieldAssistantControl editionId={editionId} fieldName="translator" query={asString(translatorItems[0]?.display_name)} token={research.token} disabled={!canEdit} onSaved={saved} beforeAction={beforeFieldAction} contextKey={assistantContextKey} /></section><RepeatableField disabled={!canEdit} label="译者" values={translatorItems} create={() => blank("translator")} onChange={(next) => replaceRoles(["translator"], next)} addLabel="添加译者" render={(item, index, setItem) => renderContributor("translator", item, index, setItem)} /><details className="workflow-other-contributors" open={otherItems.length > 0}><summary>其他贡献者 <span>{otherItems.length}</span></summary><RepeatableField disabled={!canEdit} label="主编、编者、校注、摄影及其他贡献者" values={otherItems} create={() => blank("editor")} onChange={(next) => replaceRoles([...new Set(otherItems.map((item) => asString(item.role, "editor")))], next)} addLabel="添加其他贡献者" render={(item, index, setItem) => renderContributor(undefined, item, index, setItem)} /></details></div>;
}

function ClassificationBody({ draft, canEdit, update }: BodyProps) {
  return <fieldset className="workflow-classification" disabled={!canEdit}>
    <EntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" values={entities(draft.primary_disciplines)} onChange={(next) => update("classification", "primary_disciplines", next.slice(-1))} />
    <EntityPicker label="相关学科" endpoint="/catalog/admin/disciplines/" values={entities(draft.related_disciplines)} onChange={(next) => update("classification", "related_disciplines", next)} />
    <EntityPicker label="子学科" endpoint="/catalog/admin/subdisciplines/" values={entities(draft.subdisciplines)} onChange={(next) => update("classification", "subdisciplines", next)} />
    <p className="workflow-classification-note">可随时保存草稿。核对后选择确认本节，未选分类也可以确认为不适用。</p>
  </fieldset>;
}

function FileBody({ draft, context, canEdit, errors, inspectPdf, fileAction, busy }: BodyProps) {
  const status = asString(draft.status, "pending");
  return <div className="workflow-file-summary"><dl><div><dt>文件</dt><dd>{asString(draft.filename ?? context.filename, "未建立")}</dd></div><div><dt>处理状态</dt><dd>{r2StagingStatusLabel(status)}</dd></div><div><dt>PDF 校验</dt><dd>{draft.validation === "failed" ? "未通过" : draft.validation === "passed" || draft.is_valid_pdf === true ? "已通过" : "待检查"}</dd></div><div><dt>页数</dt><dd>{asNumber(draft.page_count)}</dd></div><div><dt>文字类型</dt><dd>{asString(draft.text_profile, "待识别")}</dd></div><div><dt>重复判断</dt><dd>{draft.exact_duplicate ? "发现完全重复文件" : asString(draft.duplicate_status, "未发现完全重复")}</dd></div></dl>{errors.map((error) => <QualityIssue message={error.message} tone="blocker" key={`${error.field}-${error.message}`} />)}<div className="workflow-file-actions"><ActionButton onClick={inspectPdf}><Eye size={14} />检查 PDF</ActionButton>{draft.can_retry ? <ActionButton state={busy === "file-retry" ? "pending" : "idle"} pendingLabel="正在重试" disabled={!canEdit || Boolean(busy)} onClick={() => fileAction("retry")}><RefreshCw size={14} />{asString(draft.retry_label, "重试")}</ActionButton> : null}{draft.can_resume ? <ActionButton state={busy === "file-resume" ? "pending" : "idle"} pendingLabel="正在继续" disabled={!canEdit || Boolean(busy)} onClick={() => fileAction("resume")}><Upload size={14} />继续处理</ActionButton> : null}{draft.can_replace ? <label className="button secondary"><span>{busy === "file-replace" ? "正在替换" : "替换 PDF"}</span><input className="sr-only" type="file" accept="application/pdf,.pdf" disabled={!canEdit || Boolean(busy)} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) fileAction("replace", file); event.currentTarget.value = ""; }} /></label> : null}</div>{draft.error_message ? <p role="alert">文件处理遇到异常，可重新处理或在系统诊断中查看详情。</p> : null}</div>;
}

function ReaderBody({ draft, canEdit, update, inspectPdf }: BodyProps) {
  const label = (value: unknown, fallback = "待检查") => ({ pending: "等待处理", running: "处理中", succeeded: "已完成", failed: "失败", not_required: "无需处理", disabled: "已停用", ready: "已就绪", needs_review: "需要校对", not_indexed: "尚未建立" } as Record<string, string>)[asString(value)] ?? asString(value, fallback);
  return <div className="workflow-reader"><div className="workflow-reader-states"><article><strong>原始阅读文件</strong><span>{label(draft.original_asset_status)}</span></article><article><strong>全文文字层</strong><span>{label(draft.text_layer_status ?? draft.ocr_status)}</span></article><article><strong>引用页码</strong><span>{label(draft.page_label_status)}</span></article><article><strong>观点检索</strong><span>{label(draft.semantic_index_status)}</span></article></div><CanonicalField name="reader_rendition_policy" label="阅读文件策略" value={fieldValue(draft, "reader_rendition_policy") || "auto"} onChange={(next) => update("reader", "reader_rendition_policy", next)} options={[{ value: "auto", label: "自动，优先稳定可读文件" }, { value: "original", label: "原始 PDF" }, { value: "ocr", label: "优先已验证 OCR PDF" }]} disabled={!canEdit} help="智能内容处理异常时，已经就绪的阅读文件仍可发布。" /><button type="button" onClick={inspectPdf}><Eye size={14} />打开文件检查器</button></div>;
}

function PublicationBody({ draft, context, permissions, goToIssue, saveDraft, preview, preflight: runPreflight, publish, withdraw, publishing, busy }: BodyProps) {
  const preflight = asRecord(draft.preflight ?? draft);
  const blockers = asArray(preflight.blockers).map((entry) => normalizeIssue(entry, "publication"));
  const warnings = asArray(preflight.warnings).map((entry) => normalizeIssue(entry, "publication"));
  const tasks = asArray(preflight.background_tasks);
  const stateLabel = ({ published: "已发布", draft: "草稿", withdrawn: "已撤回", publishing: "发布处理中" } as Record<string, string>)[asString(draft.publication_state ?? draft.state ?? context.publication_state)] ?? "草稿";
  const bundle = asRecord(preflight.publication_bundle ?? draft.publication_bundle);
  const newEntities = asArray(bundle.items);
  const canPublish = permissions.can_manage_publication !== false && permissions.can_publish !== false;
  const publicationState = asString(draft.publication_state ?? draft.state ?? context.publication_state, "draft");
  return <div className="workflow-publication"><div className="workflow-publication-summary"><article><strong>公开状态</strong><span>{stateLabel}</span></article><article><strong>阅读文件</strong><span>{draft.reader_state === "ready" ? "可以阅读" : "待检查"}</span></article><article><strong>策展</strong><span>{asString(draft.curation_summary, "可选，未策展不阻止发布")}</span></article></div><div className="workflow-preflight-groups"><section className="blockers"><h3>必须解决</h3>{blockers.map((issue) => <QualityIssue key={issue.code || issue.message} message={issue.message} tone="blocker" onActivate={() => goToIssue(issue)} />)}{!blockers.length ? <p>没有发布阻止项。</p> : null}</section><section className="warnings"><h3>建议处理</h3>{warnings.map((issue) => <QualityIssue key={issue.code || issue.message} message={issue.message} tone="warning" onActivate={() => goToIssue(issue)} />)}{!warnings.length ? <p>没有发布警告。</p> : null}</section><section className="tasks"><h3>智能内容</h3><p>{tasks.length ? "发布后继续整理正文与智能检索，已就绪的阅读文件可以正常使用。" : "将按当前确认内容更新检索和关联。"}</p>{newEntities.length ? <p>本次将同时发布 {newEntities.length} 个新馆内对象。</p> : null}</section></div><div className="workflow-publication-actions"><ActionButton className="button secondary" state={busy === "save-draft" ? "pending" : "idle"} pendingLabel="正在保存草稿" disabled={Boolean(busy)} onClick={saveDraft}><Save size={14} />保存草稿</ActionButton><ActionButton className="button secondary" disabled={Boolean(busy)} onClick={preview}><Eye size={14} />预览</ActionButton><ActionButton className="button secondary" state={busy === "preflight" ? "pending" : "idle"} pendingLabel="正在检查" disabled={Boolean(busy)} onClick={runPreflight}><FileCheck2 size={14} />发布前检查</ActionButton>{publicationState === "published" ? <><span>当前版本已公开。编辑草稿 和新采用的策展内容仍需在这里确认发布。</span><ActionButton className="button" state={publishing ? "pending" : "idle"} pendingLabel="正在发布更新" disabled={!canPublish || blockers.length > 0} onClick={() => publish("stay")}><Check size={14} />发布当前更新</ActionButton><ActionButton className="button secondary" state={publishing ? "pending" : "idle"} pendingLabel="正在下架" disabled={!canPublish} onClick={withdraw}>下架当前版本</ActionButton></> : <><ActionButton className="button" state={publishing ? "pending" : "idle"} pendingLabel="正在发布" disabled={!canPublish || blockers.length > 0} onClick={() => publish("stay")}><Check size={14} />发布作品</ActionButton><ActionButton className="button secondary" state={publishing ? "pending" : "idle"} pendingLabel="正在发布" disabled={!canPublish || blockers.length > 0} onClick={() => publish("next")}>发布并处理下一项</ActionButton></>}</div>{!canPublish ? <p>当前账户可以查看检查结果，但最终发布由具有发布权限 的管理员完成。</p> : null}</div>;
}

function WorkflowSectionBody(props: BodyProps) {
  if (props.step === "file") return <FileBody {...props} />;
  if (props.step === "work") return <WorkBody {...props} />;
  if (props.step === "bibliography") return <BibliographyBody {...props} />;
  if (props.step === "contributors") return <ContributorsBody {...props} />;
  if (props.step === "classification") return <ClassificationBody {...props} />;
  if (props.step === "reader") return <ReaderBody {...props} />;
  if (props.step === "curation") return <><KnowledgeFields {...props} /><footer className="workflow-section-actions"><ActionButton className="button secondary" disabled={!props.canEdit || Boolean(props.busy)} onClick={props.saveDraft}>保存草稿</ActionButton><ActionButton className="button" disabled={!props.canEdit || Boolean(props.busy)} onClick={() => void props.confirmKnowledge()}>确认理论与主题</ActionButton></footer><WorkCurationEditor editionId={asString(props.context.edition_id)} beforeAction={props.beforeFieldAction} contextKey={props.assistantContextKey} workId={asString(props.context.work_id)} value={props.draft} canManage={props.canEdit && props.permissions.can_manage_curation !== false} canManageRecommendations={props.canEdit && props.permissions.can_publish === true} onConfirm={props.curationConfirm} onSkip={props.curationSkip} onRefresh={props.refresh} onMessage={props.message} suggestions={props.research.suggestions} onInspect={(candidate) => props.research.onInspect([candidate], "知识策展候选与依据")} /></>;
  return <PublicationBody {...props} />;
}

export function WorkflowEditor({ mode, itemId, workId, editionId: requestedEditionId }: { mode: EditorMode; itemId?: string; workId?: string; editionId?: string }) {
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
  const [researchSuggestions, setResearchSuggestions] = useState<Partial<Record<WorkflowStepKey, WorkflowCandidate[]>>>({});
  const [publishConfirmation, setPublishConfirmation] = useState<"next" | "stay" | null>(null);
  const [pendingExitHref, setPendingExitHref] = useState("");
  const draftsRef = useRef<WorkflowDrafts | null>(null);
  const dirtyRef = useRef<DirtyFields>({});
  const operationRef = useRef("");
  const [draftSessionId] = useState(createDraftSessionId);
  const token = getServerSessionCredential();
  const maintenanceEditionId = mode === "maintenance"
    ? requestedEditionId || asString(payload?.context.edition_id)
    : "";
  const maintenanceQuery = maintenanceEditionId
    ? `?edition=${encodeURIComponent(maintenanceEditionId)}`
    : "";
  const scopedEndpoint = mode === "maintenance"
    ? `${endpoint}${maintenanceQuery}`
    : endpoint;
  const currentDirtyCount = dirtyFieldCount(dirty);
  const assistantContextKey = drafts ? JSON.stringify([
    fieldValue(drafts.work, "title").trim(), fieldValue(drafts.work, "document_type"), fieldValue(drafts.work, "abstract").trim(),
    fieldValue(drafts.bibliography, "isbn10").trim(), fieldValue(drafts.bibliography, "isbn13").trim(),
    fieldValue(drafts.bibliography, "publisher").trim(), fieldValue(drafts.bibliography, "publication_year").trim(),
    normalizeItems(drafts.contributors.items, "display_name").map((person) => [asString(person.display_name).trim(), asString(person.role, "author"), asString(person.person_id)]),
    payload?.editorial_revision?.id,
  ]) : "";
  const prefetchInput = drafts && payload && payload.permissions.can_edit !== false ? JSON.stringify({
    editionId: asString(payload.context.edition_id), workId: asString(payload.context.work_id),
    title: fieldValue(drafts.work, "title").trim(), documentType: fieldValue(drafts.work, "document_type"),
    isbn: fieldValue(drafts.bibliography, "isbn13") || fieldValue(drafts.bibliography, "isbn10"),
    hasAuthor: normalizeItems(drafts.contributors.items, "display_name").some((person) => asString(person.role, "author") === "author" && Boolean(person.person_id)),
    publisher: fieldValue(drafts.bibliography, "publisher"), publicationYear: fieldValue(drafts.bibliography, "publication_year"),
    contextKey: assistantContextKey,
  }) : "";

  useEffect(() => {
    if (!prefetchInput || !token || currentDirtyCount || busy) return;
    const input = JSON.parse(prefetchInput) as { editionId: string; workId: string; title: string; documentType: string; isbn: string; hasAuthor: boolean; publisher: string; publicationYear: string; contextKey: string };
    if (!input.editionId || !input.title || (!input.isbn && !input.hasAuthor)) return;
    const request = new AbortController();
    const timer = window.setTimeout(() => {
      const options = { editionId: input.editionId, contextKey: input.contextKey, token, signal: request.signal };
      const tasks = [
        lookupFieldSuggestions({ ...options, fieldName: "publisher", query: input.publisher }),
        lookupFieldSuggestions({ ...options, fieldName: "publication_year", query: input.publicationYear }),
        lookupFieldSuggestions({ ...options, fieldName: "abstract" }),
      ];
      if (input.workId && ["book", "journal_issue"].includes(input.documentType)) {
        tasks.push(cachedAssistantRequest(assistantCacheKey(input.editionId, "cover", "", input.contextKey), `/catalog/admin/works/${input.workId}/cover-candidates/?edition_id=${encodeURIComponent(input.editionId)}`, {}, token, request.signal));
      }
      // Background preparation never blocks editing. Foreground actions still
      // surface real provider failures and permit a normal retry.
      void Promise.allSettled(tasks);
    }, 900);
    return () => { window.clearTimeout(timer); request.abort(); };
  }, [prefetchInput, token, currentDirtyCount, busy]);

  const beginOperation = useCallback((key: string) => {
    if (operationRef.current) return false;
    operationRef.current = key;
    setBusy(key);
    return true;
  }, []);
  const finishOperation = useCallback((key: string) => {
    if (operationRef.current !== key) return;
    operationRef.current = "";
    setBusy("");
  }, []);

  useEffect(() => { draftsRef.current = drafts; }, [drafts]);
  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);
  useEffect(() => {
    const receive = (event: Event) => {
      const detail = (event as CustomEvent<{ step?: unknown; suggestions?: unknown }>).detail;
      const step = detail?.step;
      if (!isWorkflowStepKey(step) || !Array.isArray(detail?.suggestions)) return;
      const rows = detail.suggestions.flatMap((entry, index) => {
        const row = asRecord(entry);
        return Object.keys(row).length ? [{ id: asString(row.id, `research-${step}-${index}`), ...row } as WorkflowCandidate] : [];
      });
      setResearchSuggestions((current) => ({ ...current, [step]: rows }));
    };
    window.addEventListener("workflow-research-suggestions", receive);
    return () => window.removeEventListener("workflow-research-suggestions", receive);
  }, []);

  const applyRemote = useCallback((raw: unknown, preserveDirty: boolean) => {
    const nextPayload = normalizePayload(raw, mode, itemId, workId);
    const remoteDrafts = draftsFromPayload(nextPayload);
    invalidateAssistantCache(asString(nextPayload.context.edition_id));
    setPayload(nextPayload);
    setDrafts((current) => preserveDirty && current ? mergeRemoteDrafts(current, remoteDrafts, dirtyRef.current) : remoteDrafts);
    setActive((current) => {
      if (typeof window !== "undefined") return stepFromHash(window.location.hash, current || nextPayload.workflow.current_step);
      return current || nextPayload.workflow.current_step;
    });
  }, [itemId, mode, workId]);

  const refresh = useCallback(async (preserveDirty = true) => {
    if (!token || (mode === "intake" ? !itemId : !workId)) return false;
    try {
      const result = await apiRequest(scopedEndpoint, {}, token);
      applyRemote(result, preserveDirty);
      return true;
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "馆藏工作读取失败。");
      return false;
    } finally {
      setLoading(false);
    }
  }, [applyRemote, itemId, mode, scopedEndpoint, token, workId]);

  const manualRefresh = useCallback(async () => {
    const key = "refresh";
    if (!beginOperation(key)) return;
    setMessage("");
    try {
      if (await refresh(true)) setMessage("已按服务器最新状态刷新，未保存字段仍保留。");
    } finally {
      finishOperation(key);
    }
  }, [beginOperation, finishOperation, refresh]);

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
    setResearchSuggestions((current) => ({ ...current, [step]: [] }));
    setInspector(null);
    setValidation((current) => ({ ...current, [step]: (current[step] ?? []).filter((issue) => issue.field !== field) }));
  }, []);

  const applyCandidateToDraft = useCallback((candidate: WorkflowCandidate) => {
    const rawField = asString(candidate.field_name ?? candidate.field);
    const field = rawField.split(".").at(-1) ?? rawField;
    const proposed = candidate.proposed_value ?? candidate.value;
    if (["authors", "translators"].includes(field)) {
      const role = field === "authors" ? "author" : "translator";
      const rawNames = Array.isArray(proposed) ? proposed : [proposed];
      const names = [...new Set(rawNames.map((entry) => {
        const row = asRecord(entry);
        return asString(row.display_name ?? row.name ?? row.label ?? entry);
      }).filter(Boolean))];
      if (!names.length) {
        setMessage("该作者或译者建议没有可采用的姓名，请查看依据后手工处理。");
        return false;
      }
      setMessage(names.length > 1
        ? `该来源识别出 ${names.length} 位${role === "author" ? "作者" : "译者"}。请在作者或译者建议中逐项核对并只采用需要的人物。`
        : `请在作者或译者建议中核对${names[0]}，再关联馆内人物、创建新学者主页或新建并关联。`);
      goToStep("contributors", "items.0.display_name");
      return false;
    }
    const explicitStep = asString(candidate.step);
    const metadataStep: WorkflowStepKey = ["version_label", "publication_date", "publication_year", "publisher", "publication_place", "isbn10", "isbn13", "series", "extent", "responsibility_statement", "journal_title", "volume", "issue", "page_range", "doi", "degree_institution", "degree_type", "report_institution"].includes(field)
      ? "bibliography"
      : ["title", "subtitle", "original_title", "uniform_title", "language", "original_language", "first_publication_date", "abstract", "document_type"].includes(field)
        ? "work"
        : "publication";
    const step = isWorkflowStepKey(explicitStep) ? explicitStep : metadataStep;
    if (!field || step === "publication") {
      setMessage("该候选需要在专用实体选择器或检查器中处理，不能作为普通文本直接填入。");
      return false;
    }
    const proposedRecord = asRecord(proposed);
    const value = Object.keys(proposedRecord).length
      ? proposedRecord.value ?? proposedRecord.name ?? proposedRecord.title ?? candidate.label ?? ""
      : proposed;
    update(step, field, value);
    setMessage("候选已填入当前草稿。保存后仍需确认发布。");
    goToStep(step, field);
    return true;
  }, [goToStep, update]);

  const allCandidates = useMemo(() => {
    const candidateRoot = asRecord(payload?.candidates);
    const researchRows = asArray(asRecord(candidateRoot.research).suggestions).map((row) => asRecord(row) as WorkflowCandidate);
    const legacyRoot = { ...candidateRoot };
    delete legacyRoot.research;
    const invalidatedFields = invalidatedResearchFields(dirty);
    const persistedRows = [...candidateList(legacyRoot), ...researchRows].filter((candidate) => {
      const field = asString(candidate.field_name ?? candidate.field).split(".").at(-1) ?? "";
      return !invalidatedFields.has(field);
    });
    const merged = [...persistedRows, ...Object.values(researchSuggestions).flat()];
    const unique = new Map<string, WorkflowCandidate>();
    merged.forEach((candidate) => unique.set(String(candidate.id), candidate));
    return [...unique.values()];
  }, [dirty, payload?.candidates, researchSuggestions]);
  const inspectField = useCallback((field: string, title = "字段候选与证据") => {
    const items = allCandidates.filter((candidate) => candidateMatches(candidate, field) || asString(candidate.source_name) === field);
    setInspector({ kind: "candidate", title, description: "候选不会自动成为正式知识。请核对来源和冲突后作出决定。", items });
  }, [allCandidates]);
  const inspectSuggestions = useCallback((items: WorkflowCandidate[], title: string) => {
    setInspector({ kind: "candidate", title, description: "研究建议只提供证据和线索。确认前不会写入当前公开内容。", items });
  }, []);

  const inspectPdf = useCallback(() => {
    const previewUrl = asString(payload?.context.pdf_preview_url) || asString(payload?.context.preview_url) || (itemId ? `/ingestion/items/${itemId}/preview/` : "");
    setInspector({ kind: "pdf", title: "PDF 与阅读文件检查", pdfUrl: previewUrl });
  }, [itemId, payload?.context.pdf_preview_url, payload?.context.preview_url]);

  const focusFirstIssue = useCallback((step: WorkflowStepKey, issues: ValidationIssue[]) => {
    const first = issues[0];
    if (first) goToStep(step, first.field);
  }, [goToStep]);

  const saveStep = useCallback(async (step: WorkflowStepKey, advance: boolean) => {
    if (!payload || !draftsRef.current || !token) return;
    const draft = draftsRef.current[step];
    const documentType = asString(draftsRef.current.work.document_type, asString(payload.context.document_type, "book"));
    const issues = advance ? validateWorkflowSection(step, draft, documentType) : [];
    setValidation((current) => ({ ...current, [step]: issues }));
    if (issues.length) {
      setMessage(issues[0].message);
      focusFirstIssue(step, issues);
      return;
    }
    const operationKey = `save-${step}`;
    if (!beginOperation(operationKey)) return;
    try {
      const result = await apiRequest(`${endpoint}sections/${step}/${maintenanceQuery}`, { method: "PATCH", body: JSON.stringify({ data: draft, confirm_section: advance }) }, token);
      const nextPayload = normalizePayload(result, mode, itemId, workId);
      const revision = asRecord(asRecord(result).editorial_revision);
      setDirty((current) => ({ ...current, [step]: [] }));
      dirtyRef.current = { ...dirtyRef.current, [step]: [] };
      applyRemote(result, true);
      const backendStep = nextPayload.workflow.steps.find((entry) => entry.key === step);
      const blockers = backendStep?.issues.filter((issue) => issue.severity === "blocker") ?? [];
      if (advance && (blockers.length || backendStep?.status === "blocked")) {
        const first = blockers[0];
        setMessage(first?.message || "本节仍有必须解决的问题。");
        goToStep(step, first?.field);
        return;
      }
      setMessage(Object.keys(revision).length
        ? "修改已保存为编辑草稿。正式页面保持原值，确认发布后才会更新。"
        : advance ? "本节已确认，可以继续编辑其他字段。" : "草稿已保存。");
      if (advance) {
        const next = nextWorkflowStep(step, nextPayload.workflow.steps);
        if (next) goToStep(next);
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "本节保存失败。");
      goToStep(step);
    } finally {
      finishOperation(operationKey);
    }
  }, [applyRemote, beginOperation, endpoint, finishOperation, focusFirstIssue, goToStep, itemId, maintenanceQuery, mode, payload, token, workId]);

  const saveAllDirty = useCallback(async (leaveHref = "") => {
    if (!payload || !draftsRef.current || !token) return false;
    const dirtySnapshot = dirtyRef.current;
    const dirtySteps = WORKFLOW_STEP_KEYS.filter((step) => (dirtySnapshot[step] ?? []).length > 0);
    if (!dirtySteps.length) {
      if (leaveHref) window.location.assign(leaveHref);
      return true;
    }
    const operationKey = "save-draft";
    if (!beginOperation(operationKey)) return false;
    try {
      let latestResult: unknown = null;
      const draftSnapshot = draftsRef.current;
      for (const step of dirtySteps) {
        latestResult = await apiRequest(`${endpoint}sections/${step}/${maintenanceQuery}`, {
          method: "PATCH",
          body: JSON.stringify({ data: draftSnapshot[step], confirm_section: false }),
        }, token);
      }
      dirtyRef.current = {};
      setDirty({});
      if (latestResult) applyRemote(latestResult, false);
      setMessage(`已保存 ${dirtySteps.length} 个步骤的草稿，尚未发布到公网。`);
      if (leaveHref) window.location.assign(leaveHref);
      return true;
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存草稿失败，未保存修改仍保留。 ");
      return false;
    } finally {
      finishOperation(operationKey);
    }
  }, [applyRemote, beginOperation, endpoint, finishOperation, maintenanceQuery, payload, token]);

  const openPreview = useCallback(() => {
    if (dirtyFieldCount(dirtyRef.current)) {
      setMessage("预览只显示已保存草稿。请先保存草稿，避免把旧内容误认为当前修改。");
      return;
    }
    const previewUrl = asString(payload?.context.page_preview_url ?? payload?.context.preview_url ?? payload?.context.public_url);
    if (!previewUrl) {
      setMessage("当前作品还没有可用预览地址。先保存书目和作品身份后再试。");
      return;
    }
    setInspector({
      kind: "page_preview",
      title: "前台预览",
      description: "这里显示已保存草稿的紧凑预览，普通访客仍使用当前正式版本。",
      previewUrl,
    });
  }, [payload?.context.page_preview_url, payload?.context.preview_url, payload?.context.public_url]);

  const runPublicationPreflight = useCallback(async () => {
    if (!token || !payload) return;
    if (dirtyFieldCount(dirtyRef.current)) {
      setMessage("发布前检查只读取已保存草稿。请先保存草稿。");
      return;
    }
    const operationKey = "preflight";
    if (!beginOperation(operationKey)) return;
    try {
      const result = await apiRequest(scopedEndpoint, {}, token);
      const nextPayload = normalizePayload(result, mode, itemId, workId);
      applyRemote(result, false);
      const publication = asRecord(nextPayload.data.publication);
      const preflight = asRecord(publication.preflight ?? publication);
      const blockerCount = asArray(preflight.blockers).length;
      const warningCount = asArray(preflight.warnings).length;
      setMessage(blockerCount ? `发布前检查发现 ${blockerCount} 个必须解决项。` : `发布前检查完成。没有阻止项，另有 ${warningCount} 个建议。`);
      goToStep("publication");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "发布前检查失败。");
    } finally {
      finishOperation(operationKey);
    }
  }, [applyRemote, beginOperation, finishOperation, goToStep, itemId, mode, payload, scopedEndpoint, token, workId]);

  const publishEditorialRevision = useCallback(async () => {
    const revision = payload?.editorial_revision;
    if (!revision || !token) return;
    if (revision.has_conflict) {
      setMessage("正式内容已经变化，请刷新后重新建立编辑草稿。");
      return;
    }
    if (!window.confirm("确认把当前编辑草稿原子发布到正式页面吗？")) return;
    const operationKey = "publish-editorial-revision";
    if (!beginOperation(operationKey)) return;
    try {
      await apiRequest(revision.publish_url, { method: "POST", body: "{}" }, token);
      setMessage("编辑草稿已发布，智能内容正在更新。");
      await refresh(true);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "编辑草稿发布失败。");
    } finally {
      finishOperation(operationKey);
    }
  }, [beginOperation, finishOperation, payload?.editorial_revision, refresh, token]);

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
    const operationKey = `file-${action}`;
    if (!beginOperation(operationKey)) return;
    try {
      const options: RequestInit = { method: "POST" };
      if (file) { const body = new FormData(); body.append("file", file); options.body = body; }
      await apiRequest(`/ingestion/items/${itemId}/${action}/`, options, token);
      setMessage(action === "replace" ? "替换文件已进入处理队列，旧文件会保留到新文件就绪。" : "文件处理任务已重新排队。");
      await refresh(true);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "文件操作失败。");
    } finally { finishOperation(operationKey); }
  }, [beginOperation, finishOperation, itemId, refresh, token]);

  const skipCuration = useCallback(async () => {
    if (!token || !draftsRef.current) return;
    const operationKey = "skip-curation";
    if (!beginOperation(operationKey)) return;
    try {
      const result = await apiRequest(`${endpoint}sections/curation/${maintenanceQuery}`, { method: "PATCH", body: JSON.stringify({ data: { ...draftsRef.current.curation, skipped: true }, skip: true, confirm_section: true }) }, token);
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
    } finally { finishOperation(operationKey); }
  }, [applyRemote, beginOperation, endpoint, finishOperation, goToStep, itemId, maintenanceQuery, mode, token, workId]);

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
    if (dirtyFieldCount(dirtyRef.current)) {
      setMessage("仍有未保存修改。请先保存草稿，再执行发布前检查和发布。 ");
      goToStep("publication");
      return;
    }
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
    const operationKey = "publish";
    if (!beginOperation(operationKey)) return;
    try {
      const publishEndpoint = mode === "intake"
        ? `/ingestion/items/${encodeURIComponent(asString(payload.context.item_id ?? itemId))}/publish/`
        : `/catalog/admin/library/works/${encodeURIComponent(asString(payload.context.work_id ?? workId))}/publication/${maintenanceQuery}`;
      const result = asRecord(await apiRequest(publishEndpoint, { method: "POST", body: JSON.stringify({ confirm_warnings: confirmWarnings, after_publish: intent, ...(maintenanceEditionId ? { edition_id: maintenanceEditionId } : {}) }) }, token));
      setPublishConfirmation(null);
      const nextTarget = asRecord(result.next_target);
      if (intent === "next") {
        const nextItem = asString(nextTarget.item_id ?? result.next_item_id ?? payload.queue.next_item_id);
        const nextWork = asString(nextTarget.work_id ?? result.next_work_id ?? payload.queue.next_work_id);
        const nextEdition = asString(nextTarget.edition_id ?? result.next_edition_id);
        if (nextItem) { window.location.assign(`/admin/intake/${nextItem}#file`); return; }
        if (nextWork) { window.location.assign(`/admin/library/works/${nextWork}${nextEdition ? `?edition=${encodeURIComponent(nextEdition)}` : ""}#work`); return; }
        window.location.assign(asString(payload.queue.return_href ?? payload.context.return_href, "/admin/review"));
        return;
      }
      const maintenanceUrl = asString(result.maintenance_url);
      const publishedWorkId = asString(asRecord(result.context).work_id ?? result.work_id ?? payload.context.work_id ?? workId);
      const publishedEditionId = asString(asRecord(result.context).edition_id ?? result.edition_id ?? payload.context.edition_id);
      if (maintenanceUrl) { window.location.replace(maintenanceUrl); return; }
      if (mode === "intake" && publishedWorkId) { window.location.replace(`/admin/library/works/${publishedWorkId}${publishedEditionId ? `?edition=${encodeURIComponent(publishedEditionId)}` : ""}#publication`); return; }
      applyRemote(result, true);
      setMessage("馆藏已发布，当前编辑器已切换为发布后维护状态。");
      goToStep("publication");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "发布失败。");
    } finally { finishOperation(operationKey); }
  }, [applyRemote, beginOperation, finishOperation, goToStep, itemId, maintenanceEditionId, maintenanceQuery, mode, payload, token, workId]);

  const performWithdraw = useCallback(async () => {
    if (!payload || !token || !window.confirm("确认下架当前版本吗？文件、审核记录和历史版本会继续保留。")) return;
    const operationKey = "publish";
    if (!beginOperation(operationKey)) return;
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
          `/catalog/admin/library/works/${encodeURIComponent(asString(payload.context.work_id ?? workId))}/publication/${maintenanceQuery}`,
          { method: "POST", body: JSON.stringify({ action: "withdraw", reason: "管理员在 2.8 馆藏工作流中下架", ...(maintenanceEditionId ? { edition_id: maintenanceEditionId } : {}) }) },
          token,
        );
        applyRemote(result, true);
      }
      setMessage("当前版本已下架，文件与历史记录保持不变。");
      goToStep("publication");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "下架失败。");
    } finally {
      finishOperation(operationKey);
    }
  }, [applyRemote, beginOperation, finishOperation, goToStep, itemId, maintenanceEditionId, maintenanceQuery, mode, payload, refresh, token, workId]);

  const decideCandidate = useCallback(async (candidate: WorkflowCandidate, action: string) => {
    if (["apply_to_draft", "apply_draft", "use_value"].includes(action)) {
      const editedValue = candidate.edited_value;
      return applyCandidateToDraft(
        editedValue === undefined
          ? candidate
          : { ...candidate, proposed_value: editedValue },
      );
    }
    const descriptorRow = asRecord(candidate.decision_descriptor);
    const descriptor = asString(descriptorRow.action) ? descriptorRow as unknown as CandidateActionDescriptor : null;
    const decisionUrl = descriptor?.url || asString(candidate.decision_url);
    if (!decisionUrl || !token) {
      setMessage("该候选没有提供安全的决定入口，请刷新后重试。");
      return false;
    }
    const operationKey = `candidate-${candidate.id}`;
    if (!beginOperation(operationKey)) {
      setMessage("另一个后台操作仍在进行，候选决定尚未提交。");
      return false;
    }
    try {
      const entityTargetType = asString(candidate.target_type ?? candidate.candidate_entity_type ?? candidate.entity_type);
      const entityTargetId = asString(candidate.candidate_entity_id ?? candidate.entity_id);
      const editedValue = candidate.edited_value;
      const legacyBody = candidate.kind === "derived_claim_curation"
        ? {
            action,
            proposition: action === "accept_with_edit" ? asString(candidate.edited_proposition) : "",
            kind: asString(candidate.curated_kind),
          }
        : entityTargetType
        ? {
            action,
            target_type: entityTargetType,
            target_id: action === "link_existing" ? entityTargetId || null : null,
            confirm_identity: action === "link_existing",
            reason: "馆藏工作流中的管理员决定",
          }
        : {
            action,
            ...(action === "accept_with_edit" && editedValue !== undefined ? { proposed_value: editedValue } : {}),
          };
      const body = descriptor
        ? buildCandidateActionBody(descriptor, editedValue, legacyBody)
        : legacyBody;
      await apiRequest(decisionUrl, { method: descriptor?.method || "POST", body: JSON.stringify(body) }, token);
      setResearchSuggestions((current) => {
        const next = { ...current };
        for (const stepKey of WORKFLOW_STEP_KEYS) {
          const rows = next[stepKey];
          if (rows) next[stepKey] = rows.filter((row) => String(row.id) !== String(candidate.id));
        }
        return next;
      });
      setInspector(null);
      setMessage("候选决定已写入审计记录。");
      await refresh(true);
      window.dispatchEvent(new Event(RESEARCH_SUGGESTION_REFRESH_EVENT));
      return true;
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "候选决定失败。");
      return false;
    } finally { finishOperation(operationKey); }
  }, [applyCandidateToDraft, beginOperation, finishOperation, refresh, token]);

  const verifyCandidate = useCallback(async (candidate: WorkflowCandidate) => {
    if (!token) return;
    const descriptor = asRecord(candidate.decision_descriptor);
    const verifyUrl = asString(descriptor.url) || asString(candidate.verify_url) || `/catalog/admin/research/candidates/${encodeURIComponent(String(candidate.id))}/verify/`;
    const operationKey = `candidate-verify-${candidate.id}`;
    if (!beginOperation(operationKey)) return;
    try {
      const result = asRecord(await apiRequest(verifyUrl, {
        method: asString(descriptor.method, "POST"),
        body: JSON.stringify({ ...asRecord(candidate.verify_payload), ...asRecord(descriptor.payload) }),
      }, token));
      const verified = asString(result.status) === "verified";
      setMessage(asString(result.detail, verified ? "已取得正文证据，候选现在可以采用。" : "没有取得达到要求的正文证据，候选仍不可采用。"));
      await refresh(true);
      window.dispatchEvent(new Event(RESEARCH_SUGGESTION_REFRESH_EVENT));
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "核实联网结果失败。");
    } finally {
      finishOperation(operationKey);
    }
  }, [beginOperation, finishOperation, refresh, token]);

  const exit = useCallback((href: string) => {
    if (dirtyFieldCount(dirtyRef.current)) {
      setPendingExitHref(href);
      return;
    }
    window.location.assign(href);
  }, []);

  const discardAndExit = useCallback(() => {
    if (!pendingExitHref) return;
    const href = pendingExitHref;
    dirtyRef.current = {};
    setDirty({});
    setPendingExitHref("");
    window.location.assign(href);
  }, [pendingExitHref]);

  const canRunResearch = payload?.permissions.capabilities?.includes("can_run_enrichment") === true;
  const editionId = asString(payload?.context.edition_id) || undefined;
  const researchWorkspace = useMemo(() => ({
    mode,
    itemId,
    workId,
    editionId,
    draftSessionId,
    token,
    canRun: canRunResearch,
    draftData: drafts ?? ({} as WorkflowDrafts),
    changedFields: dirty,
    onCandidateApply: applyCandidateToDraft,
    onCandidateDecision: decideCandidate,
    onUpdated: async () => { await refresh(true); },
    onMessage: setMessage,
  }), [applyCandidateToDraft, canRunResearch, decideCandidate, dirty, draftSessionId, drafts, editionId, itemId, mode, refresh, token, workId]);

  if (loading && !payload) return <div className="admin-page admin-loading"><LoaderCircle className="spin" size={24} /><strong>正在建立馆藏工作上下文……</strong></div>;
  if (!payload || !drafts) return <div className="admin-page workflow-load-error"><h1>无法打开馆藏工作</h1><p>{message || "没有返回可编辑数据。"}</p><button type="button" onClick={() => void refresh(false)}>重试</button></div>;

  const documentType = asString(drafts.work.document_type, asString(payload.context.document_type, "book"));
  const presentations = sectionPresentations(payload.workflow.steps, active);
  const returnHref = asString(payload.queue.return_href ?? payload.context.return_href, mode === "intake" ? "/admin/review" : "/admin/library");
  const canEdit = payload.permissions.can_edit !== false;
  return (
    <ResearchSuggestionCapabilityContext.Provider value={canRunResearch}>
    <ResearchWorkspaceContext.Provider value={researchWorkspace}>
    <div className="workflow-editor" data-workflow-mode={payload.mode}>
      <WorkflowStepRail title={asString(payload.context.title)} filename={asString(payload.context.filename)} steps={payload.workflow.steps} active={active} unresolvedCount={payload.workflow.unresolved_count} dirtyCount={currentDirtyCount} returnHref={returnHref} onStep={goToStep} onExit={exit} />
      <main className="workflow-editor-main">
        <header className="workflow-editor-header"><div><p>{payload.mode === "intake" ? "上架工作" : "馆藏维护"}</p><h1>{asString(payload.context.title, "未命名馆藏")}</h1><span>{payload.workflow.blockers_count ? `还需确认 ${payload.workflow.blockers_count} 项` : "没有阻断性问题"} · {currentDirtyCount ? `${currentDirtyCount} 项未保存` : "草稿已保存"}</span></div><div><ActionButton state={busy === "refresh" ? "pending" : "idle"} pendingLabel="正在刷新" onClick={() => void manualRefresh()} disabled={Boolean(busy)}><RefreshCw size={14} />刷新</ActionButton><ActionButton state={busy === `save-${active}` ? "pending" : "idle"} pendingLabel="正在保存" onClick={() => void saveStep(active, false)} disabled={Boolean(busy) || !canEdit}><Save size={14} />保存草稿</ActionButton><ActionButton onClick={inspectPdf}><Eye size={14} />PDF</ActionButton>{payload.context.page_preview_url ? <ActionLink className="workflow-header-preview" href={asString(payload.context.page_preview_url)} target="_blank">打开完整前台预览</ActionLink> : null}{payload.context.public_url ? <ActionLink className="workflow-header-preview" href={asString(payload.context.public_url)} target="_blank">公开页面</ActionLink> : null}</div></header>
        {busy && !message ? <AsyncStatus state="pending" message="正在执行馆藏工作操作……" className="workflow-editor-message" /> : null}
        {message ? <AsyncStatus state={workflowMessageState(message)} message={message} className="workflow-editor-message" assertive={workflowMessageState(message) === "error"} /> : null}
        {payload.editorial_revision?.status === "draft" ? <section className="workflow-editorial-revision"><div><strong>已发布作品的编辑草稿</strong><p>当前有 {payload.editorial_revision.changed_fields.length} 项已保存修改。表单和预览显示草稿，读者仍使用已发布版本。</p></div><ActionButton className="button" state={busy === "publish-editorial-revision" ? "pending" : "idle"} pendingLabel="正在发布草稿" disabled={Boolean(busy) || payload.editorial_revision.has_conflict} onClick={() => void publishEditorialRevision()}><Check size={14} />确认发布更新</ActionButton></section> : null}
        {editionId ? <PublicationRetryControl key={editionId} editionId={editionId} token={token} disabled={Boolean(busy)} refreshKey={JSON.stringify(payload.context)} onCompleted={async () => { await refresh(true); }} /> : null}
        <div className="workflow-sections">{payload.workflow.steps.map((step) => {
          const presentation = presentations[step.key];
          const expanded = presentation === "current";
          const localErrors = validation[step.key] ?? [];
          const sectionCanEdit = canEdit && !busy;
          return <section className={`workflow-section presentation-${presentation} status-${step.status}`} id={`workflow-section-${step.key}`} key={step.key} data-step={step.key}><button className="workflow-section-heading" type="button" aria-expanded={expanded} onClick={() => goToStep(step.key)}><span>{step.status === "complete" || step.status === "skipped" ? <Check size={15} /> : expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</span><div><small>{statusLabel(step.status)}</small><h2>{step.label}</h2>{presentation === "summary" ? <p>{typeof step.summary === "string" ? step.summary : summaryFor(step.key, drafts[step.key])}</p> : presentation === "preview" ? <p>{step.next_action || "可直接进入编辑，也可稍后处理。"}</p> : null}</div><b>{step.issues.length ? `${step.issues.length} 项` : ""}</b></button>{expanded ? <div className="workflow-section-content">{step.key !== "publication" ? <div className="workflow-backend-issues">{step.issues.map((issue) => <QualityIssue key={issue.code || issue.message} message={issue.message} tone={issue.severity === "blocker" ? "blocker" : issue.severity === "info" ? "info" : "warning"} onActivate={() => goToIssue(issue)} />)}</div> : null}<WorkflowSectionBody step={step.key} draft={drafts[step.key]} documentType={documentType} candidates={allCandidates} canEdit={sectionCanEdit} context={payload.context} permissions={payload.permissions} errors={localErrors} update={update} inspectField={inspectField} inspectPdf={inspectPdf} fileAction={fileAction} curationConfirm={() => saveStep("curation", true)} curationSkip={() => skipCuration()} refresh={() => refresh(true)} message={setMessage} goToIssue={goToIssue} saveDraft={() => void saveAllDirty()} beforeFieldAction={() => saveAllDirty()} knowledgeDraft={drafts.knowledge} confirmKnowledge={() => saveStep("knowledge", true)} assistantContextKey={assistantContextKey} preview={openPreview} preflight={() => void runPublicationPreflight()} publish={(intent) => void performPublish(intent, false)} withdraw={() => void performWithdraw()} publishing={busy === "publish"} busy={busy} research={{ mode, itemId, workId, token, suggestions: allCandidates, onInspect: inspectSuggestions, onUpdated: async () => { await refresh(true); }, onMessage: setMessage }} />{step.key !== "publication" && step.key !== "curation" ? <footer className="workflow-section-actions"><ActionButton className="button secondary" state={busy === `save-${step.key}` ? "pending" : "idle"} pendingLabel="正在保存" disabled={Boolean(busy) || !sectionCanEdit} onClick={() => void saveStep(step.key, false)}><Save size={14} />保存</ActionButton><ActionButton className="button" state={busy === `save-${step.key}` ? "pending" : "idle"} pendingLabel="正在确认" disabled={Boolean(busy) || !sectionCanEdit} onClick={() => void saveStep(step.key, true)}><FileCheck2 size={14} />确认本节</ActionButton></footer> : null}</div> : null}</section>;
        })}</div>
      </main>
      <WorkflowInspector selection={inspector} token={token} onClose={() => setInspector(null)} onDecision={decideCandidate} onVerify={verifyCandidate} />
      {pendingExitHref ? <div className="workflow-modal-backdrop"><div className="workflow-publication-confirmation workflow-unsaved-exit" role="dialog" aria-modal="true" aria-labelledby="workflow-unsaved-exit-title"><AlertTriangle size={21} /><div><h2 id="workflow-unsaved-exit-title">当前工作有未保存修改</h2><p>可以先把所有修改保存为草稿后退出，也可以放弃本次未保存内容。继续编辑会留在当前作品。</p></div><footer><ActionButton className="button" state={busy === "save-draft" ? "pending" : "idle"} pendingLabel="正在保存草稿" disabled={Boolean(busy)} onClick={() => void saveAllDirty(pendingExitHref)}><Save size={14} />保存草稿并退出</ActionButton><ActionButton className="button secondary" disabled={Boolean(busy)} onClick={discardAndExit}>不保存并退出</ActionButton><ActionButton className="button secondary" disabled={Boolean(busy)} onClick={() => setPendingExitHref("")}>继续编辑</ActionButton></footer></div></div> : null}
      {publishConfirmation ? <div className="workflow-modal-backdrop"><div className="workflow-publication-confirmation" role="dialog" aria-modal="true" aria-labelledby="workflow-publish-confirm-title"><AlertTriangle size={21} /><div><h2 id="workflow-publish-confirm-title">确认带警告发布</h2><p>警告不会阻止发布。正文识别、页码和智能检索会继续处理，原始 PDF 会保留。</p></div><footer><ActionButton className="button secondary" disabled={Boolean(busy)} onClick={() => setPublishConfirmation(null)}>取消</ActionButton><ActionButton className="button" state={busy === "publish" ? "pending" : "idle"} pendingLabel="正在发布" disabled={Boolean(busy)} onClick={() => void performPublish(publishConfirmation, true)}>确认发布</ActionButton></footer></div></div> : null}
      {busy === "skip-curation" ? <span className="sr-only" aria-live="polite">正在保存暂不策展决定</span> : null}
      <span className="sr-only" aria-live="polite">{currentDirtyCount ? `${currentDirtyCount} 项未保存` : "所有修改已保存"}</span>
    </div>
    </ResearchWorkspaceContext.Provider>
    </ResearchSuggestionCapabilityContext.Provider>
  );
}
