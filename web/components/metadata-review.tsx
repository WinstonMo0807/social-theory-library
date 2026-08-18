"use client";

import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  ChevronsUpDown,
  Check,
  ExternalLink,
  FileText,
  LoaderCircle,
  Lock,
  Plus,
  RefreshCw,
  Send,
  Trash2,
} from "lucide-react";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useId, useMemo, useState } from "react";
import { apiBlob, apiRequest, getServerSessionCredential } from "@/lib/api";
import type { PublicationPreflight } from "@/components/item-publication-control";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { PageMappingEditor } from "@/components/page-mapping-editor";
import {
  CandidateCard,
  EvidenceChip,
  type StatusTone,
} from "@/components/admin-ui";

type CandidateValue = string | number | string[] | null | Record<string, unknown>;
type CandidateLifecycle = "proposed" | "accepted" | "rejected" | "superseded";
type EntityResolutionAction = "link_existing" | "create_draft" | "keep_unresolved" | "reject";

type CandidateEvidence = {
  id: string;
  asset: string | null;
  source_record: string | null;
  page_number: number | null;
  bbox: unknown[];
  text_quote: string;
  source_kind: string;
  external_identifier: string;
  extraction_method: string;
  model_name: string;
  model_revision: string;
  created_at: string;
};

type MetadataCandidate = {
  id: string;
  field_name: string;
  value: CandidateValue;
  source: string;
  evidence: Record<string, unknown>;
  confidence: number;
  selected: boolean;
  lifecycle: CandidateLifecycle;
  normalized_value: CandidateValue;
  score_factors: Record<string, unknown>;
  is_locked: boolean;
  accepted_by: string | null;
  accepted_at: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
  evidence_records: CandidateEvidence[];
};

type EntityResolutionCandidate = {
  id: string;
  target_type: string;
  source_name: string;
  candidate_entity_type: string;
  candidate_entity_id: string | null;
  label: string;
  aliases: string[];
  external_ids: Record<string, unknown>;
  supporting_properties: Record<string, unknown>;
  match_score: number;
  match_reasons: string[];
  conflicts: string[];
  preview_data: Record<string, unknown>;
  status: "proposed" | "linked" | "create_draft" | "unresolved" | "ignored" | "rejected";
  reviewed_by: string | null;
  reviewed_at: string | null;
  available_actions: EntityResolutionAction[];
  latest_decision: {
    id: string;
    action: string;
    created_at: string;
    reverted_at: string | null;
    reverted_by: string;
    reversal_reason: string;
    can_revert: boolean;
  } | null;
};

type ProcessingAttempt = {
  id: string;
  stage: string;
  attempt_number: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  output_summary: Record<string, unknown>;
  log_excerpt: string;
  error_code: string;
  error_message: string;
};

type RelationSuggestion = {
  kind: "theory_school" | "topic" | "concept";
  name: string;
  source: string;
  confidence: number;
  approved: boolean;
};

type EntityRef = {
  id: string | null;
  name: string;
  slug?: string;
};

type KnowledgeRef = EntityRef & {
  role?: "foundational" | "development" | "introduction" | "empirical_application" | "method_use" | "criticism" | "theory_history" | "local_mention";
  strength?: "high" | "medium" | "low";
  is_primary?: boolean;
  review_status?: string;
  evidence_page?: number | null;
  evidence_printed_label?: string;
  evidence_text?: string;
};

type ReleaseImpactItem = { label: string; href: string };
type AuthorityLink = {
  label: string;
  url: string;
  query: string;
  language: string;
  purpose: string;
  automated: boolean;
};
type ReleaseImpact = {
  work: ReleaseImpactItem;
  scholars: ReleaseImpactItem[];
  disciplines: ReleaseImpactItem[];
  theories: ReleaseImpactItem[];
  subdisciplines: ReleaseImpactItem[];
  topics: ReleaseImpactItem[];
  search: ReleaseImpactItem;
};

type CoverCandidate = {
  id: string;
  page_index: number;
  thumbnail_url: string;
  score: number;
  reasons: string[];
  metrics: Record<string, unknown>;
  selected: boolean;
};

type PublicationPlaceEvidence = {
  id: string;
  raw_value: string;
  normalized_value: string;
  place_type: "publication_place" | "distribution_place" | "printing_place" | "publisher_address" | "degree_place" | "archive_location";
  source_type: string;
  source_provider: string;
  source_record_id: string;
  evidence_page: number | null;
  evidence_text: string;
  confidence: number;
  verification_status: "auto_confirmed" | "needs_review" | "manually_confirmed" | "manually_corrected" | "unknown";
  is_primary: boolean;
  publisher_raw: string;
  publication_year: number | null;
  verified_at: string | null;
};

type PublicationPlaceRevision = {
  id: string;
  action: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  reason: string;
  actor: string;
  created_at: string;
};

type ReviewData = {
  edition_id: string;
  work_id: string;
  title: string;
  subtitle: string;
  document_type: FormState["documentType"];
  language: FormState["language"];
  abstract: string;
  version_label: string;
  publication_year: number | null;
  publisher: string;
  publication_place: string;
  publication_place_evidence: PublicationPlaceEvidence[];
  publication_place_history: PublicationPlaceRevision[];
  journal_title: string;
  volume: string;
  issue: string;
  page_range: string;
  degree_institution: string;
  degree_type: string;
  report_institution: string;
  isbn: string;
  doi: string;
  authority_links: AuthorityLink[];
  authors: string[];
  author_refs: EntityRef[];
  theory_schools: string[];
  theory_school_refs: KnowledgeRef[];
  topics: string[];
  topic_refs: KnowledgeRef[];
  discipline_refs: KnowledgeRef[];
  subdiscipline_refs: KnowledgeRef[];
  release_impact: ReleaseImpact;
  relation_suggestions: RelationSuggestion[];
  locked_fields: string[];
  normalized_asset_id: string | null;
  publication_state: string;
  ocr_status: string;
  semantic_index_status: string;
  page_label_status: string;
  review_status: string;
  review_progress: number;
  reader_rendition_policy: "auto" | "original" | "ocr";
  first_published_at: string | null;
  last_published_at: string | null;
  public_slug: string | null;
  page_count: number;
  cover_candidates: CoverCandidate[];
  first_page: {
    index: number;
    printed_label: string;
    text: string;
    text_source: string;
    confidence: number;
    label_source: string;
    label_confidence: number;
    is_label_manual: boolean;
  } | null;
};

type UploadItem = {
  id: string;
  source_filename: string;
  status: string;
  stage_progress: number;
  error_code: string;
  error_message: string;
  uploaded_by: string;
  review_data: ReviewData | null;
  metadata_candidates: MetadataCandidate[];
  entity_resolution_candidates: EntityResolutionCandidate[];
  attempts: ProcessingAttempt[];
  publication_reasons: string[];
  publication_preflight: PublicationPreflight;
  can_publish: boolean;
  can_manage_publication: boolean;
  updated_at: string;
};

type FormState = {
  title: string;
  subtitle: string;
  documentType: "book" | "journal_article" | "thesis" | "report";
  language: "zh-CN" | "zh-TW" | "en";
  versionLabel: string;
  year: string;
  publisher: string;
  place: string;
  journal: string;
  volume: string;
  issue: string;
  pages: string;
  degreeInstitution: string;
  degreeType: string;
  reportInstitution: string;
  isbn: string;
  doi: string;
  abstract: string;
};

const emptyForm: FormState = {
  title: "",
  subtitle: "",
  documentType: "book",
  language: "zh-CN",
  versionLabel: "",
  year: "",
  publisher: "",
  place: "",
  journal: "",
  volume: "",
  issue: "",
  pages: "",
  degreeInstitution: "",
  degreeType: "",
  reportInstitution: "",
  isbn: "",
  doi: "",
  abstract: "",
};

const fieldLabels: Record<string, string> = {
  title: "题名",
  subtitle: "副题名",
  document_type: "文献类型",
  language: "正文语言",
  version_label: "版本说明",
  authors: "作者",
  publication_year: "出版年份",
  publication_place: "出版地",
  publisher: "出版者",
  journal_title: "期刊名",
  volume: "卷",
  issue: "期",
  page_range: "页码范围",
  degree_institution: "学位授予单位",
  degree_type: "学位类型",
  report_institution: "报告责任机构",
  isbn: "ISBN",
  doi: "DOI",
  abstract: "摘要",
  theory_schools: "理论流派",
  disciplines: "主要或相关学科",
  subdisciplines: "子学科",
  topics: "主题",
};

const sourceLabels: Record<string, string> = {
  pdf_metadata: "PDF 内嵌属性",
  first_pages: "首页可见文字",
  document_classifier: "文献类型分类器",
  crossref: "Crossref",
  openlibrary: "Open Library",
  openlibrary_search: "Open Library 检索",
  openlibrary_title: "Open Library 题名候选",
  crossref_title: "Crossref 题名候选",
  google_books: "Google Books",
  controlled_vocabulary_match_v1: "馆内受控词表",
  grobid: "GROBID 论文头部解析",
  keyword_classifier: "全文关键词规则",
};

const candidateLifecycleLabels: Record<CandidateLifecycle, string> = {
  proposed: "待审",
  accepted: "已接受",
  rejected: "已拒绝",
  superseded: "已替代",
};

const candidateLifecycleTones: Record<CandidateLifecycle, StatusTone> = {
  proposed: "warning",
  accepted: "success",
  rejected: "danger",
  superseded: "neutral",
};

const scoreFactorLabels: Record<string, string> = {
  identifier_match: "标识符匹配",
  title_similarity: "题名相似度",
  author_similarity: "责任者相似度",
  year_match: "年份匹配",
  language_match: "语言匹配",
  source_reliability: "来源可靠性",
  ocr_quality: "OCR 文字质量",
  multi_source_agreement: "多来源一致",
  conflict_penalty: "冲突扣分",
};

const statusLabels: Record<string, string> = {
  received: "已接收",
  validating: "正在校验",
  deduplicating: "正在查重",
  extracting: "正在提取逐页文本",
  ocr: "正在 OCR",
  metadata: "正在识别元数据",
  linking: "正在建立关联",
  indexing: "正在建立索引",
  preparing_public_asset: "正在准备公开文件",
  syncing_cloud: "正在同步云端副本",
  ready: "可发布",
  published: "已发布",
  needs_review: "需要人工复核",
  failed: "处理失败",
  withdrawn: "已下架",
};

function formFromReview(review: ReviewData): FormState {
  return {
    title: review.title ?? "",
    subtitle: review.subtitle ?? "",
    documentType: review.document_type ?? "book",
    language: review.language ?? "zh-CN",
    versionLabel: review.version_label ?? "",
    year: review.publication_year ? String(review.publication_year) : "",
    publisher: review.publisher ?? "",
    place: review.publication_place ?? "",
    journal: review.journal_title ?? "",
    volume: review.volume ?? "",
    issue: review.issue ?? "",
    pages: review.page_range ?? "",
    degreeInstitution: review.degree_institution ?? "",
    degreeType: review.degree_type ?? "",
    reportInstitution: review.report_institution ?? "",
    isbn: review.isbn ?? "",
    doi: review.doi ?? "",
    abstract: review.abstract ?? "",
  };
}

function displayValue(value: CandidateValue) {
  if (Array.isArray(value)) return value.join("、");
  if (value === null || value === undefined) return "无内容";
  if (typeof value === "object") return JSON.stringify(value);
  if (value === "book") return "图书";
  if (value === "journal_article") return "期刊论文";
  if (value === "thesis") return "学位论文";
  if (value === "report") return "研究报告";
  return String(value);
}

function evidenceText(evidence: Record<string, unknown>) {
  const values = Object.entries(evidence).map(([key, value]) => `${key} ${Array.isArray(value) ? value.join("–") : String(value)}`);
  return values.join(" · ") || "未提供页码证据";
}

function resolvedCandidateLifecycle(candidate: MetadataCandidate): CandidateLifecycle {
  return candidate.lifecycle || (candidate.selected ? "accepted" : "proposed");
}

function formatAuditValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未提供";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") {
    return value >= 0 && value <= 1 ? `${Math.round(value * 100)}%` : String(value);
  }
  if (Array.isArray(value)) return value.map(formatAuditValue).join("、");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${scoreFactorLabels[key] ?? key}：${formatAuditValue(nested)}`)
      .join("；");
  }
  return String(value);
}

function hasCandidateValue(value: CandidateValue) {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function candidateEvidenceSourceLabel(value: string) {
  const label = sourceLabels[value] ?? ({
    ocr: "OCR 文字",
    pdf_text: "PDF 文字层",
    pdf_metadata: "PDF 内嵌属性",
    external_provider: "外部书目来源",
    manual: "人工记录",
  }[value] ?? value);
  return label || "未标注来源";
}

const entityResolutionStatusLabels: Record<EntityResolutionCandidate["status"], string> = {
  proposed: "待明确选择",
  linked: "已关联",
  create_draft: "已选择新建草稿",
  unresolved: "暂不处理",
  ignored: "已忽略",
  rejected: "已排除",
};

const entityResolutionStatusTones: Record<EntityResolutionCandidate["status"], StatusTone> = {
  proposed: "warning",
  linked: "success",
  create_draft: "info",
  unresolved: "neutral",
  ignored: "neutral",
  rejected: "danger",
};

const entityResolutionActionLabels: Record<EntityResolutionAction, string> = {
  link_existing: "确认关联",
  create_draft: "创建草稿",
  keep_unresolved: "保留未解析名称",
  reject: "拒绝候选",
};

function entityResolutionTargetLabel(candidate: EntityResolutionCandidate) {
  if (candidate.target_type === "person") return "作者";
  if (candidate.target_type === "work") return "作品";
  if (candidate.target_type === "publisher") return "出版者";
  if (candidate.target_type === "organization") return "责任机构";
  if (candidate.target_type === "knowledge_node") {
    const nodeType = String(candidate.supporting_properties.node_type ?? "");
    return {
      discipline: "学科",
      subdiscipline: "子学科",
      theory_tradition: "理论流派",
      topic: "主题",
    }[nodeType] ?? "知识实体";
  }
  return candidate.target_type;
}

function entityResolutionGuidance(candidate: EntityResolutionCandidate) {
  const target = entityResolutionTargetLabel(candidate);
  const isDraft = candidate.candidate_entity_type.endsWith("_draft") || !candidate.candidate_entity_id;
  if (isDraft && candidate.target_type === "person") {
    return `选择“创建草稿”只会建立未公开人物档案；选择“保留未解析名称”则不会创建权威实体。`;
  }
  if (isDraft && ["knowledge_node"].includes(candidate.target_type)) {
    return `选择“创建草稿”会建立未公开${target}，仍需后续审核。`;
  }
  if (isDraft && candidate.target_type === "organization") return "机构草稿不会直接公开，需继续核对机构类型和权威标识。";
  if (candidate.candidate_entity_id && candidate.target_type === "person") {
    return `请核对身份属性后使用“确认关联”。同名只是候选，系统不会自动合并。`;
  }
  if (candidate.candidate_entity_id && candidate.target_type === "knowledge_node") {
    return `请根据证据使用“确认关联”。术语相似不会自动关联。`;
  }
  return `该${target}结果现阶段只用于核对，不会自动关联或新建公开实体。`;
}

function MetadataCandidateScoreFactors({ factors }: { factors: Record<string, unknown> }) {
  const entries = Object.entries(factors ?? {});
  return (
    <section className="metadata-candidate-score-factors" aria-label="候选评分因素">
      <strong>评分依据</strong>
      {entries.length ? (
        <dl>
          {entries.map(([key, value]) => (
            <div key={key}>
              <dt>{scoreFactorLabels[key] ?? key}</dt>
              <dd>{formatAuditValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : <small>旧候选未记录分项评分。</small>}
    </section>
  );
}

function MetadataCandidateEvidenceList({
  candidate,
  fallbackAssetId,
}: {
  candidate: MetadataCandidate;
  fallbackAssetId: string | null;
}) {
  const records = candidate.evidence_records ?? [];
  if (!records.length) {
    return <small className="metadata-candidate-legacy-evidence">{evidenceText(candidate.evidence ?? {})}</small>;
  }
  return (
    <div className="metadata-candidate-evidence-list">
      {records.map((evidence) => {
        const assetId = evidence.asset || fallbackAssetId;
        const pageLabel = evidence.page_number ? `PDF 第 ${evidence.page_number} 页` : "未标页码";
        const quote = evidence.text_quote.trim();
        const href = assetId && evidence.page_number
          ? `/reader/${assetId}?page=${evidence.page_number}${quote ? `&q=${encodeURIComponent(quote.slice(0, 180))}` : ""}`
          : undefined;
        return (
          <div className="metadata-candidate-evidence-record" key={evidence.id}>
            <EvidenceChip
              label={quote || evidence.external_identifier || "查看候选证据"}
              source={candidateEvidenceSourceLabel(evidence.source_kind)}
              pageLabel={pageLabel}
              href={href}
            />
            {quote ? <blockquote>{quote}</blockquote> : null}
            <small>
              {evidence.extraction_method ? `提取方式：${evidence.extraction_method}` : ""}
              {evidence.model_name ? ` · 模型：${evidence.model_name}${evidence.model_revision ? `@${evidence.model_revision}` : ""}` : ""}
              {evidence.source_record ? ` · 来源记录：${evidence.source_record}` : ""}
            </small>
          </div>
        );
      })}
    </div>
  );
}

function EntityResolutionEvidence({ candidate }: { candidate: EntityResolutionCandidate }) {
  const properties = Object.entries(candidate.supporting_properties ?? {})
    .filter(([, value]) => value !== null && value !== undefined && value !== "");
  const externalIds = Object.entries(candidate.external_ids ?? {})
    .filter(([, value]) => value !== null && value !== undefined && value !== "");
  return (
    <div className="entity-resolution-evidence">
      {candidate.match_reasons?.length ? (
        <div><strong>匹配依据</strong><ul>{candidate.match_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></div>
      ) : null}
      {properties.length ? (
        <dl>{properties.map(([key, value]) => <div key={key}><dt>{scoreFactorLabels[key] ?? key}</dt><dd>{formatAuditValue(value)}</dd></div>)}</dl>
      ) : null}
      {externalIds.length ? (
        <p><strong>权威标识</strong>{externalIds.map(([key, value]) => `${key}：${formatAuditValue(value)}`).join("·")}</p>
      ) : null}
      <p className="entity-resolution-guidance">{entityResolutionGuidance(candidate)}</p>
    </div>
  );
}

function publicationPlaceTypeLabel(value: PublicationPlaceEvidence["place_type"]) {
  return {
    publication_place: "出版地",
    distribution_place: "发行地",
    printing_place: "印刷地",
    publisher_address: "出版社地址",
    degree_place: "学位授予地",
    archive_location: "收藏地",
  }[value];
}

function publicationPlaceStatusLabel(value: PublicationPlaceEvidence["verification_status"]) {
  return {
    auto_confirmed: "有直接证据，已自动确认",
    needs_review: "建议值，等待确认",
    manually_confirmed: "管理员已确认",
    manually_corrected: "管理员已校正",
    unknown: "证据不足",
  }[value];
}

export function MetadataReview({ itemId }: { itemId: string }) {
  const [item, setItem] = useState<UploadItem | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [authors, setAuthors] = useState<EntityRef[]>([]);
  const [disciplines, setDisciplines] = useState<KnowledgeRef[]>([]);
  const [schools, setSchools] = useState<KnowledgeRef[]>([]);
  const [subdisciplines, setSubdisciplines] = useState<KnowledgeRef[]>([]);
  const [topics, setTopics] = useState<KnowledgeRef[]>([]);
  const [lockedFields, setLockedFields] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"pdf" | "text" | "ocr" | "pages" | "history">("pdf");
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [placeCorrections, setPlaceCorrections] = useState<Record<string, string>>({});
  const [removeConfirmation, setRemoveConfirmation] = useState(false);
  const [suggestionsPending, setSuggestionsPending] = useState(false);
  const [candidateDecisionPending, setCandidateDecisionPending] = useState("");
  const [entityDecisionPending, setEntityDecisionPending] = useState("");
  const [metadataImportFile, setMetadataImportFile] = useState<File | null>(null);
  const [metadataImportPending, setMetadataImportPending] = useState(false);
  const [entityDecisionPrompt, setEntityDecisionPrompt] = useState<{
    candidate: EntityResolutionCandidate;
    action: EntityResolutionAction;
  } | null>(null);
  const [entityRevertPrompt, setEntityRevertPrompt] = useState<EntityResolutionCandidate | null>(null);

  const hydrate = useCallback((payload: UploadItem) => {
    setItem(payload);
    if (payload.review_data) {
      setForm(formFromReview(payload.review_data));
      setAuthors(
        payload.review_data.author_refs?.length
          ? payload.review_data.author_refs
          : payload.review_data.authors.map((name) => ({ id: null, name })),
      );
      setDisciplines(payload.review_data.discipline_refs ?? []);
      setSchools(
        payload.review_data.theory_school_refs?.length
          ? payload.review_data.theory_school_refs
          : payload.review_data.theory_schools.map((name) => ({ id: null, name })),
      );
      setSubdisciplines(payload.review_data.subdiscipline_refs ?? []);
      setTopics(
        payload.review_data.topic_refs?.length
          ? payload.review_data.topic_refs
          : payload.review_data.topics.map((name) => ({ id: null, name })),
      );
      setLockedFields(payload.review_data.locked_fields);
    }
  }, []);

  const loadItem = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) {
      setMessage("请先以管理员或编辑账户登录。");
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const payload = await apiRequest<UploadItem>(`/ingestion/items/${itemId}/`, {}, token);
      hydrate(payload);
      setMessage("");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "无法读取复核记录。");
    } finally {
      setLoading(false);
    }
  }, [hydrate, itemId]);

  useEffect(() => {
    const token = getServerSessionCredential();
    let active = true;
    if (!token) {
      Promise.resolve().then(() => {
        if (!active) return;
        setMessage("请先以管理员或编辑账户登录。");
        setLoading(false);
      });
      return () => {
        active = false;
      };
    }
    apiRequest<UploadItem>(`/ingestion/items/${itemId}/`, {}, token)
      .then((payload) => {
        if (!active) return;
        hydrate(payload);
        setMessage("");
      })
      .catch((reason) => {
        if (!active) return;
        setMessage(reason instanceof Error ? reason.message : "无法读取复核记录。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [hydrate, itemId]);

  useEffect(() => {
    if (activeTab !== "pdf" || previewUrl || !item) return;
    const token = getServerSessionCredential();
    if (!token) return;
    let active = true;
    void apiBlob(`/ingestion/items/${itemId}/preview/`, token)
      .then((blob) => {
        if (!active) return;
        setPreviewError("");
        setPreviewUrl(URL.createObjectURL(blob));
      })
      .catch((reason) => {
        if (!active) return;
        setPreviewError(reason instanceof Error ? reason.message : "PDF 预览加载失败。");
      });
    return () => {
      active = false;
    };
  }, [activeTab, item, itemId, previewUrl]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  function setField<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function toggleLock(field: string) {
    setLockedFields((current) => (
      current.includes(field)
        ? current.filter((name) => name !== field)
        : current.concat(field)
    ));
  }

  function applyCandidate(candidate: MetadataCandidate) {
    const value = candidate.value;
    const fieldLabel = fieldLabels[candidate.field_name] ?? candidate.field_name;
    const announce = () => setMessage(`已将“${fieldLabel}”候选填入表单。此操作尚未接受候选；保存复核内容后才会记录正式决定。`);
    if (candidate.field_name === "authors") {
      if (value === null || (!Array.isArray(value) && typeof value === "object")) return;
      setAuthors((Array.isArray(value) ? value : [value]).map((name) => ({ id: null, name: String(name) })));
      announce();
      return;
    }
    if (["disciplines", "subdisciplines", "theory_schools", "topics"].includes(candidate.field_name)) {
      if (value === null || (!Array.isArray(value) && typeof value === "object")) return;
      const entityId = typeof candidate.evidence.entity_id === "string"
        ? candidate.evidence.entity_id
        : null;
      const entitySlug = typeof candidate.evidence.entity_slug === "string"
        ? candidate.evidence.entity_slug
        : undefined;
      const refs = (Array.isArray(value) ? value : [value]).map((name) => ({
        id: entityId,
        name: String(name),
        slug: entitySlug,
        review_status: "suggested",
      }));
      const merge = (current: KnowledgeRef[]) => current.concat(
        refs.filter((next) => !current.some((existing) => (
          (next.id && existing.id === next.id)
          || existing.name.toLocaleLowerCase() === next.name.toLocaleLowerCase()
        ))),
      );
      if (candidate.field_name === "disciplines") setDisciplines(merge);
      if (candidate.field_name === "subdisciplines") setSubdisciplines(merge);
      if (candidate.field_name === "theory_schools") setSchools(merge);
      if (candidate.field_name === "topics") setTopics(merge);
      announce();
      return;
    }
    const fieldMap: Record<string, keyof FormState> = {
      title: "title",
      subtitle: "subtitle",
      document_type: "documentType",
      language: "language",
      version_label: "versionLabel",
      publication_year: "year",
      publisher: "publisher",
      publication_place: "place",
      journal_title: "journal",
      volume: "volume",
      issue: "issue",
      page_range: "pages",
      degree_institution: "degreeInstitution",
      degree_type: "degreeType",
      report_institution: "reportInstitution",
      isbn: "isbn",
      doi: "doi",
      abstract: "abstract",
    };
    const field = fieldMap[candidate.field_name];
    if (!field || value === null || typeof value === "object") return;
    setForm((current) => ({ ...current, [field]: String(value) }));
    announce();
  }

  async function decideMetadataCandidate(candidate: MetadataCandidate, action: "reject" | "reopen") {
    const token = getServerSessionCredential();
    if (!token) {
      setMessage("请先以管理员或编辑账户登录。");
      return;
    }
    setCandidateDecisionPending(candidate.id);
    setMessage("");
    try {
      const updated = await apiRequest<MetadataCandidate>(
        `/ingestion/items/${itemId}/metadata-candidates/${candidate.id}/decision/`,
        {
          method: "POST",
          body: JSON.stringify({ action }),
        },
        token,
      );
      setItem((current) => current ? {
        ...current,
        metadata_candidates: current.metadata_candidates.map((existing) => (
          existing.id === updated.id ? updated : existing
        )),
      } : current);
      setMessage(action === "reject"
        ? "候选已拒绝。它不会在保存时被采用，仍可恢复为待审。"
        : "候选已恢复为待审，请重新核对证据后再填入表单。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "候选状态更新失败。");
    } finally {
      setCandidateDecisionPending("");
    }
  }

  async function decideEntityResolution(
    candidate: EntityResolutionCandidate,
    action: EntityResolutionAction,
    reason = "",
  ) {
    const token = getServerSessionCredential();
    if (!token) {
      setMessage("请先以管理员或编辑账户登录。");
      return;
    }
    setEntityDecisionPending(candidate.id);
    setMessage("");
    try {
      const response = await apiRequest<{
        candidate: EntityResolutionCandidate;
        group: EntityResolutionCandidate[];
        review_task_status: string | null;
        idempotent: boolean;
      }>(
        `/ingestion/items/${itemId}/entity-resolution-candidates/${candidate.id}/decision/`,
        {
          method: "POST",
          body: JSON.stringify({
            action,
            target_type: candidate.target_type,
            target_id: action === "link_existing" ? candidate.candidate_entity_id : undefined,
            confirm_identity: action === "link_existing" && candidate.target_type === "person",
            reason,
          }),
        },
        token,
      );
      const updatedById = new Map(response.group.map((row) => [row.id, row]));
      setItem((current) => current ? {
        ...current,
        entity_resolution_candidates: current.entity_resolution_candidates.map((row) => (
          updatedById.get(row.id) ?? row
        )),
      } : current);
      setEntityDecisionPrompt(null);
      setMessage(response.idempotent
        ? "该实体候选已经记录过相同决定。"
        : `${entityResolutionActionLabels[action]}已记录。系统不会把草稿或未解析名称直接公开。`);
    } catch (reasonValue) {
      setMessage(reasonValue instanceof Error ? reasonValue.message : "实体消歧决定保存失败。");
    } finally {
      setEntityDecisionPending("");
    }
  }

  async function revertEntityResolution(candidate: EntityResolutionCandidate, reason: string) {
    const token = getServerSessionCredential();
    const decisionId = candidate.latest_decision?.id;
    if (!token || !decisionId) {
      setMessage("没有可撤销的实体决定，请刷新页面后重试。");
      return;
    }
    setEntityDecisionPending(candidate.id);
    setMessage("");
    try {
      const response = await apiRequest<{
        candidate: EntityResolutionCandidate;
        group: EntityResolutionCandidate[];
        review_task_status: string | null;
        idempotent: boolean;
      }>(
        `/ingestion/items/${itemId}/entity-resolution-decisions/${decisionId}/revert/`,
        {
          method: "POST",
          body: JSON.stringify({ reason }),
        },
        token,
      );
      const updatedById = new Map(response.group.map((row) => [row.id, row]));
      setItem((current) => current ? {
        ...current,
        entity_resolution_candidates: current.entity_resolution_candidates.map((row) => (
          updatedById.get(row.id) ?? row
        )),
      } : current);
      setEntityRevertPrompt(null);
      setMessage(response.idempotent ? "该决定此前已经撤销。" : "实体决定已撤销，候选组已恢复为待审状态。");
    } catch (reasonValue) {
      setMessage(reasonValue instanceof Error ? reasonValue.message : "实体决定撤销失败。");
    } finally {
      setEntityDecisionPending("");
    }
  }

  async function refreshMetadataSuggestions() {
    const token = getServerSessionCredential();
    if (!token || !item?.review_data) return;
    setSuggestionsPending(true);
    try {
      const result = await apiRequest<{
        added: number;
        warnings: string[];
        results: MetadataCandidate[];
        authority_links: AuthorityLink[];
      }>(`/ingestion/items/${itemId}/metadata-suggestions/`, { method: "POST" }, token);
      setItem((current) => current ? {
        ...current,
        metadata_candidates: result.results,
        review_data: current.review_data ? {
          ...current.review_data,
          authority_links: result.authority_links,
        } : null,
      } : current);
      setMessage(result.warnings.length
        ? `已新增 ${result.added} 项候选；部分来源未连接：${result.warnings.join("；")}`
        : `已新增 ${result.added} 项联网候选。候选不会自动覆盖当前表单。`
      );
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "联网候选读取失败。");
    } finally {
      setSuggestionsPending(false);
    }
  }

  async function importMetadataFile() {
    const token = getServerSessionCredential();
    if (!token) {
      setMessage("请先以管理员或编辑账户登录。");
      return;
    }
    if (!metadataImportFile) {
      setMessage("请先选择 RIS、BibTeX、CSL-JSON、sidecar JSON 或 YAML 文件。");
      return;
    }
    const body = new FormData();
    body.append("file", metadataImportFile);
    setMetadataImportPending(true);
    setMessage("");
    try {
      const result = await apiRequest<{
        format: string;
        reused_source: boolean;
        stats: { added: number; updated: number; preserved: number; superseded: number };
        candidates: MetadataCandidate[];
      }>(
        `/ingestion/items/${itemId}/metadata-import/`,
        { method: "POST", body },
        token,
      );
      setItem((current) => {
        if (!current) return current;
        const importedById = new Map(result.candidates.map((candidate) => [candidate.id, candidate]));
        const merged = current.metadata_candidates.map((candidate) => (
          importedById.get(candidate.id) ?? candidate
        ));
        const known = new Set(merged.map((candidate) => candidate.id));
        merged.push(...result.candidates.filter((candidate) => !known.has(candidate.id)));
        return { ...current, metadata_candidates: merged };
      });
      setMessage(result.reused_source
        ? "这份书目文件已经导入过，现有人工决定保持不变。"
        : `已从 ${result.format} 生成 ${result.stats.added} 项待审候选。正式元数据尚未改写。`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "书目文件导入失败。");
    } finally {
      setMetadataImportPending(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) {
      setMessage("请先以管理员或编辑账户登录。");
      return;
    }
    setPending(true);
    setMessage("");
    try {
      const payload = await apiRequest<UploadItem>(
        `/ingestion/items/${itemId}/review/`,
        {
          method: "PUT",
          body: JSON.stringify({
            title: form.title.trim(),
            subtitle: form.subtitle.trim(),
            document_type: form.documentType,
            language: form.language,
            version_label: form.versionLabel.trim(),
            publication_year: Number(form.year) || null,
            publisher: form.publisher.trim(),
            publication_place: form.place.trim(),
            journal_title: form.journal.trim(),
            volume: form.volume.trim(),
            issue: form.issue.trim(),
            page_range: form.pages.trim(),
            degree_institution: form.degreeInstitution.trim(),
            degree_type: form.degreeType.trim(),
            report_institution: form.reportInstitution.trim(),
            isbn: form.isbn.trim(),
            doi: form.doi.trim(),
            abstract: form.abstract.trim(),
            author_ids: authors.flatMap((value) => value.id ? [value.id] : []),
            authors: authors.flatMap((value) => value.id ? [] : [value.name]),
            discipline_assignments: disciplines.flatMap((value) => value.id ? [{
              id: value.id,
              is_primary: Boolean(value.is_primary),
              evidence_page: value.evidence_page || null,
              evidence_printed_label: value.evidence_printed_label || "",
              evidence_text: value.evidence_text || "",
            }] : []),
            theory_assignments: schools.flatMap((value) => value.id ? [{
              id: value.id,
              role: value.role || "local_mention",
              strength: value.strength || "medium",
              is_primary: Boolean(value.is_primary),
              evidence_page: value.evidence_page || null,
              evidence_printed_label: value.evidence_printed_label || "",
              evidence_text: value.evidence_text || "",
            }] : []),
            theory_schools: schools.flatMap((value) => value.id ? [] : [value.name]),
            subdiscipline_assignments: subdisciplines.flatMap((value) => value.id ? [{
              id: value.id,
              strength: value.strength || "medium",
              is_primary: Boolean(value.is_primary),
              evidence_page: value.evidence_page || null,
              evidence_printed_label: value.evidence_printed_label || "",
              evidence_text: value.evidence_text || "",
            }] : []),
            topic_assignments: topics.flatMap((value) => value.id ? [{
              id: value.id,
              is_primary: Boolean(value.is_primary),
              evidence_page: value.evidence_page || null,
              evidence_printed_label: value.evidence_printed_label || "",
              evidence_text: value.evidence_text || "",
            }] : []),
            topics: topics.flatMap((value) => value.id ? [] : [value.name]),
            lock_fields: lockedFields,
            retry_publication: true,
          }),
        },
        token,
      );
      hydrate(payload);
      setMessage(
        payload.error_code === "queue_unavailable"
          ? payload.error_message
          : payload.review_data?.publication_state === "published"
            ? "公开元数据已经保存，全文索引已同步更新。"
            : "元数据已经保存并锁定。管理员可以在发布管理中查看警告并决定是否发布。",
      );
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败。");
    } finally {
      setPending(false);
    }
  }

  async function retry() {
    const token = getServerSessionCredential();
    if (!token) {
      setMessage("请先登录。");
      return;
    }
    setPending(true);
    setMessage("");
    try {
      await apiRequest(`/ingestion/items/${itemId}/retry/`, { method: "POST" }, token);
      setMessage("已进入重新识别队列。原有人工锁定字段不会被自动识别覆盖。");
      await loadItem();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "重新识别失败。");
    } finally {
      setPending(false);
    }
  }

  async function removeFromQueue() {
    const token = getServerSessionCredential();
    if (!token || !item) return;
    setPending(true);
    try {
      await apiRequest(`/ingestion/items/${itemId}/delete/`, {
        method: "POST",
        body: JSON.stringify({ confirmed: true }),
      }, token);
      setRemoveConfirmation(false);
      window.location.assign("/admin/review");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "删除失败。");
      setPending(false);
    }
  }

  async function regenerateCoverCandidates() {
    const token = getServerSessionCredential();
    const workId = item?.review_data?.work_id;
    if (!token || !workId) return;
    setPending(true);
    setMessage("");
    try {
      await apiRequest(
        `/catalog/admin/works/${workId}/cover-candidates/`,
        { method: "POST" },
        token,
      );
      await loadItem();
      setMessage("已重新分析 PDF 前部页面，并生成新的封面候选。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "封面候选生成失败。");
    } finally {
      setPending(false);
    }
  }

  async function updatePublicationPlaces(action: "reanalyze" | "confirm" | "correct", evidence?: PublicationPlaceEvidence) {
    const token = getServerSessionCredential();
    if (!token) return;
    setPending(true);
    setMessage("");
    try {
      await apiRequest(`/ingestion/items/${itemId}/publication-places/`, {
        method: "POST",
        body: JSON.stringify({
          action,
          evidence_id: evidence?.id,
          value: evidence ? placeCorrections[evidence.id]?.trim() : undefined,
          reason: action === "correct" ? "管理员在元数据校准页人工修改" : "管理员核对出版信息证据",
        }),
      }, token);
      await loadItem();
      setMessage(action === "reanalyze" ? "出版信息证据已重新分析。" : "出版地已确认，引用格式已经同步更新。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "出版地校准失败。");
    } finally {
      setPending(false);
    }
  }

  async function selectCoverCandidate(candidateId: string) {
    const token = getServerSessionCredential();
    const workId = item?.review_data?.work_id;
    if (!token || !workId) return;
    setPending(true);
    setMessage("");
    try {
      await apiRequest(
        `/catalog/admin/works/${workId}/cover-candidates/${candidateId}/select/`,
        { method: "POST" },
        token,
      );
      await loadItem();
      setMessage("馆藏封面已经更新。公开页面会使用当前选择。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "封面选择失败。");
    } finally {
      setPending(false);
    }
  }

  const relationCandidates = useMemo(
    () => item?.review_data?.relation_suggestions ?? [],
    [item],
  );
  const metadataCandidates = useMemo(() => {
    const lifecycleOrder: Record<CandidateLifecycle, number> = {
      proposed: 0,
      accepted: 1,
      rejected: 2,
      superseded: 3,
    };
    return [...(item?.metadata_candidates ?? [])].sort((left, right) => (
      lifecycleOrder[resolvedCandidateLifecycle(left)] - lifecycleOrder[resolvedCandidateLifecycle(right)]
    ));
  }, [item]);
  const entityResolutionCandidates = useMemo(
    () => item?.entity_resolution_candidates ?? [],
    [item],
  );
  const metadataCandidateCounts = useMemo(() => {
    const counts: Record<CandidateLifecycle, number> = {
      proposed: 0,
      accepted: 0,
      rejected: 0,
      superseded: 0,
    };
    metadataCandidates.forEach((candidate) => {
      counts[resolvedCandidateLifecycle(candidate)] += 1;
    });
    return counts;
  }, [metadataCandidates]);
  const totalCandidateCount = metadataCandidates.length + entityResolutionCandidates.length + relationCandidates.length;
  const metadataCandidatesByField = useMemo(() => {
    const groups = new Map<string, MetadataCandidate[]>();
    metadataCandidates.forEach((candidate) => {
      const lifecycle = resolvedCandidateLifecycle(candidate);
      if (!hasCandidateValue(candidate.value) || lifecycle === "rejected" || lifecycle === "superseded") return;
      const values = groups.get(candidate.field_name) ?? [];
      values.push(candidate);
      groups.set(candidate.field_name, values);
    });
    groups.forEach((values) => values.sort((left, right) => right.confidence - left.confidence));
    return groups;
  }, [metadataCandidates]);
  const inlineCandidates = (fieldName: string) => (
    <InlineMetadataCandidates
      candidates={(metadataCandidatesByField.get(fieldName) ?? []).slice(0, 3)}
      busy={pending || Boolean(candidateDecisionPending)}
      onApply={applyCandidate}
      onReject={(candidate) => void decideMetadataCandidate(candidate, "reject")}
    />
  );
  const firstPage = item?.review_data?.first_page;
  const isPublished = item?.review_data?.publication_state === "published";

  if (loading) {
    return <div className="admin-page admin-loading"><LoaderCircle className="spin" size={28} /><p>正在读取识别记录……</p></div>;
  }

  return (
    <div className="admin-page review-editor">
      <header className="admin-page-title">
        <div>
          <Link href={isPublished ? "/admin/library" : "/admin/review"}><ArrowLeft size={15} />{isPublished ? "返回馆藏" : "返回队列"}</Link>
          <h1>{isPublished ? "编辑馆藏元数据" : "元数据复核"}</h1>
          <span>识别候选、页内证据和最终公开字段来自同一份入库记录。</span>
        </div>
        <p>
          <FileText size={16} />
          {item?.source_filename ?? "尚未建立记录"}
          {item ? <small>{statusLabels[item.status] ?? item.status} · {item.stage_progress}%</small> : null}
        </p>
      </header>

      {item?.error_message ? (
        <div className="review-error" role="alert"><AlertCircle size={16} /><p><strong>{item.error_code || "处理错误"}</strong>{item.error_message}</p></div>
      ) : null}
      {!item?.review_data ? (
        <section className="admin-panel review-unavailable">
          <h2>尚无可复核的馆藏记录</h2>
          <p>识别流程可能仍在运行，也可能在建立文献记录之前失败。可以查看处理历史并在排除错误后重新识别。</p>
          <button className="button secondary" type="button" onClick={retry} disabled={pending}><RefreshCw size={15} />重新识别</button>
          <button className="button danger" type="button" onClick={() => void removeFromQueue()} disabled={pending}><Trash2 size={15} />移出队列</button>
          <AttemptHistory attempts={item?.attempts ?? []} />
          {message ? <p className="form-message" role="status">{message}</p> : null}
        </section>
      ) : (
        <>
          <section className={`review-publication-handoff admin-panel ${isPublished ? "published" : "draft"}`}>
            <div>
              <span>{isPublished ? "当前已公开" : "当前尚未发布"}</span>
              <strong>{isPublished ? "这里保存的修改会更新公开元数据" : "保存复核内容不会自动发布"}</strong>
              <p>{isPublished ? "需要下架或重新检查发布影响时，请进入发布台。" : "完成需要的复核后，到发布台预览馆藏、核对警告，并由管理员最终确认发布。"}</p>
            </div>
            <Link className="button" href={`/admin/publication?item=${itemId}`}><Send size={15} />进入发布台</Link>
          </section>
          <form onSubmit={submit}>
          <section className="review-form admin-panel">
            <header><h2>最终馆藏元数据</h2><span><Lock size={14} /> 人工锁定字段不会被后续识别覆盖</span></header>
            <div className="form-grid">
              <Field label="题名 *" wide locked={lockedFields.includes("title")} onToggleLock={() => toggleLock("title")}>
                <input value={form.title} onChange={(event) => setField("title", event.target.value)} required />
                {inlineCandidates("title")}
              </Field>
              <Field label="副题名" locked={lockedFields.includes("subtitle")} onToggleLock={() => toggleLock("subtitle")}>
                <input value={form.subtitle} onChange={(event) => setField("subtitle", event.target.value)} />
                {inlineCandidates("subtitle")}
              </Field>
              <Field label="文献类型 *" locked={lockedFields.includes("document_type")} onToggleLock={() => toggleLock("document_type")}>
                <select value={form.documentType} onChange={(event) => setField("documentType", event.target.value as FormState["documentType"])}>
                  <option value="book">图书</option>
                  <option value="journal_article">期刊论文</option>
                  <option value="thesis">学位论文</option>
                  <option value="report">研究报告</option>
                </select>
                {inlineCandidates("document_type")}
              </Field>
              <Field label="正文语言 *" locked={lockedFields.includes("language")} onToggleLock={() => toggleLock("language")}>
                <select value={form.language} onChange={(event) => setField("language", event.target.value as FormState["language"])}>
                  <option value="zh-CN">简体中文</option>
                  <option value="zh-TW">繁体中文</option>
                  <option value="en">英文</option>
                </select>
                {inlineCandidates("language")}
              </Field>
              <Field label="版本说明" locked={lockedFields.includes("version_label")} onToggleLock={() => toggleLock("version_label")}>
                <input value={form.versionLabel} onChange={(event) => setField("versionLabel", event.target.value)} placeholder="保留未来多版本接口" />
                {inlineCandidates("version_label")}
              </Field>
              <Field label="出版年份" locked={lockedFields.includes("publication_year")} onToggleLock={() => toggleLock("publication_year")}>
                <input type="number" min="1400" max="2100" value={form.year} onChange={(event) => setField("year", event.target.value)} />
                {inlineCandidates("publication_year")}
              </Field>
              <Field label="出版地" locked={lockedFields.includes("publication_place")} onToggleLock={() => toggleLock("publication_place")}>
                <input value={form.place} onChange={(event) => setField("place", event.target.value)} />
                {inlineCandidates("publication_place")}
              </Field>

              {form.documentType === "book" ? (
                <>
                  <Field label="出版者" locked={lockedFields.includes("publisher")} onToggleLock={() => toggleLock("publisher")}>
                    <input value={form.publisher} onChange={(event) => setField("publisher", event.target.value)} />
                    {inlineCandidates("publisher")}
                  </Field>
                  <Field label="ISBN" locked={lockedFields.includes("isbn")} onToggleLock={() => toggleLock("isbn")}>
                    <input value={form.isbn} onChange={(event) => setField("isbn", event.target.value)} />
                    {inlineCandidates("isbn")}
                  </Field>
                </>
              ) : null}

              {form.documentType === "journal_article" ? (
                <>
                  <Field label="期刊名" locked={lockedFields.includes("journal_title")} onToggleLock={() => toggleLock("journal_title")}>
                    <input value={form.journal} onChange={(event) => setField("journal", event.target.value)} />
                    {inlineCandidates("journal_title")}
                  </Field>
                  <Field label="卷" locked={lockedFields.includes("volume")} onToggleLock={() => toggleLock("volume")}>
                    <input value={form.volume} onChange={(event) => setField("volume", event.target.value)} />
                    {inlineCandidates("volume")}
                  </Field>
                  <Field label="期" locked={lockedFields.includes("issue")} onToggleLock={() => toggleLock("issue")}>
                    <input value={form.issue} onChange={(event) => setField("issue", event.target.value)} />
                    {inlineCandidates("issue")}
                  </Field>
                  <Field label="页码范围" locked={lockedFields.includes("page_range")} onToggleLock={() => toggleLock("page_range")}>
                    <input value={form.pages} onChange={(event) => setField("pages", event.target.value)} />
                    {inlineCandidates("page_range")}
                  </Field>
                </>
              ) : null}

              {form.documentType === "thesis" ? (
                <>
                  <Field label="学位授予单位" locked={lockedFields.includes("degree_institution")} onToggleLock={() => toggleLock("degree_institution")}>
                    <input value={form.degreeInstitution} onChange={(event) => setField("degreeInstitution", event.target.value)} />
                    {inlineCandidates("degree_institution")}
                  </Field>
                  <Field label="学位类型" locked={lockedFields.includes("degree_type")} onToggleLock={() => toggleLock("degree_type")}>
                    <input value={form.degreeType} onChange={(event) => setField("degreeType", event.target.value)} placeholder="博士 / 硕士" />
                    {inlineCandidates("degree_type")}
                  </Field>
                </>
              ) : null}

              {form.documentType === "report" ? (
                <Field label="报告责任机构" locked={lockedFields.includes("report_institution")} onToggleLock={() => toggleLock("report_institution")}>
                  <input value={form.reportInstitution} onChange={(event) => setField("reportInstitution", event.target.value)} />
                  {inlineCandidates("report_institution")}
                </Field>
              ) : null}

              {form.documentType !== "book" ? (
                <Field label="DOI" locked={lockedFields.includes("doi")} onToggleLock={() => toggleLock("doi")}>
                  <input value={form.doi} onChange={(event) => setField("doi", event.target.value)} />
                  {inlineCandidates("doi")}
                </Field>
              ) : null}

              <EntityPicker
                label="作者（可选）"
                field="authors"
                values={authors}
                onChange={setAuthors}
                locked={lockedFields.includes("authors")}
                onToggleLock={toggleLock}
                endpoint="/catalog/admin/scholars/"
                createHref="/admin/scholars"
                createLabel="建立新学者档案"
                nameField="preferred_name"
              />
              {inlineCandidates("authors")}
              <EntityPicker
                label="主要或相关学科（可选）"
                field="disciplines"
                values={disciplines}
                onChange={(values) => setDisciplines(mergeKnowledgeRefs(disciplines, values))}
                locked={lockedFields.includes("disciplines")}
                onToggleLock={toggleLock}
                endpoint="/catalog/admin/disciplines/"
                createHref="/admin/disciplines"
                createLabel="建立新学科"
                nameField="name"
                allowInlineCreate={false}
              />
              {inlineCandidates("disciplines")}
              <RelationAssignmentEditor kind="discipline" values={disciplines} onChange={setDisciplines} />
              <EntityPicker
                label="理论流派（可选）"
                field="theory_schools"
                values={schools}
                onChange={(values) => setSchools(mergeKnowledgeRefs(schools, values))}
                locked={lockedFields.includes("theory_schools")}
                onToggleLock={toggleLock}
                endpoint="/catalog/admin/theory-schools/"
                createHref="/admin/theory-nodes?node_type=theory_tradition"
                createLabel="建立新理论流派"
                nameField="name"
              />
              {inlineCandidates("theory_schools")}
              <RelationAssignmentEditor kind="theory" values={schools} onChange={setSchools} />
              <EntityPicker
                label="子学科（可选）"
                field="subdisciplines"
                values={subdisciplines}
                onChange={(values) => setSubdisciplines(mergeKnowledgeRefs(subdisciplines, values))}
                locked={lockedFields.includes("subdisciplines")}
                onToggleLock={toggleLock}
                endpoint="/catalog/admin/subdisciplines/"
                createHref="/admin/subdisciplines"
                createLabel="建立新子学科"
                nameField="name"
                allowInlineCreate={false}
              />
              {inlineCandidates("subdisciplines")}
              <RelationAssignmentEditor kind="subdiscipline" values={subdisciplines} onChange={setSubdisciplines} />
              <EntityPicker
                label="主题（可选）"
                field="topics"
                values={topics}
                onChange={(values) => setTopics(mergeKnowledgeRefs(topics, values))}
                locked={lockedFields.includes("topics")}
                onToggleLock={toggleLock}
                endpoint="/catalog/admin/topics/"
                createHref="/admin/topics"
                createLabel="建立新主题"
                nameField="name"
              />
              {inlineCandidates("topics")}
              <RelationAssignmentEditor kind="topic" values={topics} onChange={setTopics} />
              <Field label="摘要" wide locked={lockedFields.includes("abstract")} onToggleLock={() => toggleLock("abstract")}>
                <textarea rows={6} value={form.abstract} onChange={(event) => setField("abstract", event.target.value)} />
                {inlineCandidates("abstract")}
              </Field>
            </div>
            {form.documentType === "book" ? (
              <section className="publication-place-review">
                <header>
                  <div>
                    <h3>出版信息识别与证据</h3>
                    <p>系统只确认当前版本中有直接书目证据的出版地。出版社所在地只能作为待核候选，不会静默写入引用。</p>
                  </div>
                  <button className="button secondary" type="button" disabled={pending} onClick={() => void updatePublicationPlaces("reanalyze")}><RefreshCw size={14} />重新识别</button>
                </header>
                <div className="publication-place-evidence-list">
                  {(item.review_data.publication_place_evidence ?? []).map((evidence) => (
                    <article className={evidence.is_primary ? "primary" : ""} key={evidence.id}>
                      <header>
                        <div><strong>{evidence.normalized_value || "未识别"}</strong><span>{publicationPlaceTypeLabel(evidence.place_type)}</span></div>
                        <b>{publicationPlaceStatusLabel(evidence.verification_status)}</b>
                      </header>
                      <dl>
                        <div><dt>置信度</dt><dd>{Math.round(evidence.confidence * 100)}%</dd></div>
                        <div><dt>来源</dt><dd>{evidence.source_provider || evidence.source_type}</dd></div>
                        <div><dt>对应出版者</dt><dd>{evidence.publisher_raw || "未记录"}</dd></div>
                        <div><dt>对应年份</dt><dd>{evidence.publication_year || "未记录"}</dd></div>
                      </dl>
                      <blockquote>{evidence.evidence_text || "没有可展示的直接证据。"}</blockquote>
                      <div className="publication-place-evidence-actions">
                        {evidence.evidence_page && item.review_data?.normalized_asset_id ? (
                          <Link
                            target="_blank"
                            href={`/reader/${item.review_data?.normalized_asset_id}?page=${evidence.evidence_page}&q=${encodeURIComponent((evidence.evidence_text || evidence.normalized_value).slice(0, 180))}`}
                          >
                            <ExternalLink size={14} />查看 PDF 第 {evidence.evidence_page} 页并定位证据
                          </Link>
                        ) : <span>无 PDF 页码证据</span>}
                        <button type="button" disabled={pending || !evidence.normalized_value} onClick={() => void updatePublicationPlaces("confirm", evidence)}>确认候选</button>
                      </div>
                      <label><span>人工校正</span><div><input value={placeCorrections[evidence.id] ?? ""} onChange={(event) => setPlaceCorrections((current) => ({ ...current, [evidence.id]: event.target.value }))} placeholder="输入当前版本的正确出版地" /><button type="button" disabled={pending || !placeCorrections[evidence.id]?.trim()} onClick={() => void updatePublicationPlaces("correct", evidence)}>保存校正</button></div></label>
                    </article>
                  ))}
                  {!item.review_data.publication_place_evidence?.length ? <p className="candidate-empty">尚无出版地候选。点击“重新识别”后检查题名页、版权页和书目来源。</p> : null}
                </div>
                {item.review_data.publication_place_history?.length ? (
                  <details className="publication-place-history"><summary>查看人工校准记录</summary>{item.review_data.publication_place_history.map((revision) => <p key={revision.id}><time>{new Date(revision.created_at).toLocaleString("zh-CN")}</time><strong>{revision.actor}</strong><span>{revision.action}{revision.reason ? ` · ${revision.reason}` : ""}</span></p>)}</details>
                ) : null}
              </section>
            ) : null}
            {form.documentType === "book" ? (
              <section className="cover-candidate-review">
                <header>
                  <div>
                    <h3>图书封面候选</h3>
                    <p>系统只在文献类型为图书时分析 PDF 前部页面。排序依据包括题名、作者、大字号标题、图像比例、文字密度和页面位置。</p>
                  </div>
                  <button className="button secondary" type="button" onClick={() => void regenerateCoverCandidates()} disabled={pending}>
                    <RefreshCw size={14} /> 重新分析
                  </button>
                </header>
                <div>
                  {(item.review_data.cover_candidates ?? []).map((candidate) => (
                    <article className={candidate.selected ? "selected" : ""} key={candidate.id}>
                      <CoverCandidatePreview candidate={candidate} />
                      <header>
                        <strong>PDF 第 {candidate.page_index} 页</strong>
                        <b>{Math.round(candidate.score * 100)}%</b>
                      </header>
                      <p>{candidate.reasons.join("；")}</p>
                      <button type="button" disabled={candidate.selected || pending} onClick={() => void selectCoverCandidate(candidate.id)}>
                        {candidate.selected ? "当前封面" : "采用此页"}
                      </button>
                    </article>
                  ))}
                  {!item.review_data.cover_candidates?.length ? <p className="candidate-empty">尚未生成候选。点击“重新分析”后，系统会检查 PDF 前 12 页。</p> : null}
                </div>
              </section>
            ) : null}
            <RecommendationImageEditor
              workId={item.review_data.work_id}
              documentType={form.documentType}
              onMessage={setMessage}
            />
            <footer>
              <button className="button secondary" type="button" onClick={retry} disabled={pending}><RefreshCw size={15} />重新识别</button>
              {!isPublished ? <button className="button danger" type="button" onClick={() => setRemoveConfirmation(true)} disabled={pending}><Trash2 size={15} />移除复核记录</button> : null}
              <button className="button" type="submit" disabled={pending}>{pending ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{isPublished ? "保存公开元数据" : "保存复核内容"}</button>
            </footer>
            {message ? <p className="form-message" role="status">{message}</p> : null}
          </section>

          <ReleaseImpactPanel
            form={form}
            authors={authors}
            disciplines={disciplines}
            schools={schools}
            subdisciplines={subdisciplines}
            topics={topics}
            saved={item.review_data.release_impact}
            publicSlug={item.review_data.public_slug}
          />

          <aside className="candidate-panel admin-panel">
            <header>
              <div>
                <h2>识别候选与证据</h2>
                <span className="candidate-count-summary">
                  共 {totalCandidateCount} 项 · 待审 {metadataCandidateCounts.proposed} · 已接受 {metadataCandidateCounts.accepted} · 已拒绝/替代 {metadataCandidateCounts.rejected + metadataCandidateCounts.superseded} · 实体提示 {entityResolutionCandidates.length}
                </span>
              </div>
              <button className="button secondary" type="button" disabled={suggestionsPending} onClick={() => void refreshMetadataSuggestions()}><RefreshCw size={14} />{suggestionsPending ? "正在核对" : "联网补充候选"}</button>
            </header>
            <section className="metadata-file-import" aria-labelledby="metadata-file-import-title">
              <div>
                <h3 id="metadata-file-import-title">导入标准书目</h3>
                <p>支持单条 RIS、BibTeX、CSL-JSON、sidecar JSON 与安全 YAML。导入内容只形成待审候选，不会直接覆盖馆藏。</p>
              </div>
              <label>
                <span>{metadataImportFile?.name || "选择书目文件"}</span>
                <input
                  type="file"
                  accept=".ris,.bib,.bibtex,.json,.yaml,.yml,application/json,application/yaml,text/yaml"
                  onChange={(event) => setMetadataImportFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <button
                className="button secondary"
                type="button"
                disabled={!metadataImportFile || metadataImportPending}
                onClick={() => void importMetadataFile()}
              >
                <FileText size={14} />{metadataImportPending ? "正在导入" : "生成候选"}
              </button>
            </section>
            {item.review_data.authority_links?.length ? <section className="metadata-authority-links"><h3>中文来源优先核对</h3><p>系统会自动读取有稳定接口的来源。其余权威目录提供检索词，由管理员打开核对后再采用。</p>{item.review_data.authority_links.map((link) => <a href={link.url} target="_blank" rel="noreferrer" key={`${link.label}-${link.query}`}><span><strong>{link.label}</strong><small>{link.purpose}</small></span><b>{link.query}</b><ExternalLink size={13} /></a>)}</section> : null}
            {totalCandidateCount ? (
              <>
                {entityResolutionCandidates.length ? (
                  <section className="entity-resolution-section" aria-labelledby="entity-resolution-title">
                    <header>
                      <div><h3 id="entity-resolution-title">实体消歧</h3><p>同名不会自动合并。请在候选卡中关联现有实体、建立草稿或保留未解析名称；错误决定可在发布前撤销。</p></div>
                      <span>{entityResolutionCandidates.length} 项</span>
                    </header>
                    <div className="entity-resolution-list">
                      {entityResolutionCandidates.map((candidate) => (
                        <CandidateCard
                          className="entity-resolution-card"
                          key={candidate.id}
                          title={`${entityResolutionTargetLabel(candidate)}：${candidate.source_name}`}
                          value={candidate.label}
                          source={candidate.aliases?.length ? `别名：${candidate.aliases.join("、")}` : "未提供别名"}
                          confidence={candidate.match_score}
                          status={{
                            label: entityResolutionStatusLabels[candidate.status],
                            tone: entityResolutionStatusTones[candidate.status],
                          }}
                          evidence={<EntityResolutionEvidence candidate={candidate} />}
                          conflicts={candidate.conflicts?.length ? <ul>{candidate.conflicts.map((conflict) => <li key={conflict}>{conflict}</li>)}</ul> : undefined}
                          actions={(candidate.available_actions?.length || candidate.latest_decision?.can_revert) ? (
                            <>
                              {candidate.available_actions?.map((action) => (
                                <button
                                  className={`candidate-action ${action === "reject" ? "danger" : ""}`.trim()}
                                  type="button"
                                  disabled={pending || Boolean(entityDecisionPending)}
                                  key={action}
                                  onClick={() => setEntityDecisionPrompt({ candidate, action })}
                                >
                                  {entityDecisionPending === candidate.id ? "正在处理" : entityResolutionActionLabels[action]}
                                </button>
                              ))}
                              {candidate.latest_decision?.can_revert ? (
                                <button
                                  className="candidate-action"
                                  type="button"
                                  disabled={pending || Boolean(entityDecisionPending)}
                                  onClick={() => setEntityRevertPrompt(candidate)}
                                >
                                  撤销决定
                                </button>
                              ) : null}
                            </>
                          ) : undefined}
                        />
                      ))}
                    </div>
                  </section>
                ) : null}
                {metadataCandidates.length ? <section className="metadata-candidate-section" aria-labelledby="metadata-candidates-title"><header><h3 id="metadata-candidates-title">字段候选</h3><span>填入表单不等于最终接受，以保存复核内容为准。</span></header></section> : null}
                {metadataCandidates.map((candidate) => {
                  const lifecycle = resolvedCandidateLifecycle(candidate);
                  const normalizedValue = hasCandidateValue(candidate.normalized_value)
                    && JSON.stringify(candidate.normalized_value) !== JSON.stringify(candidate.value)
                    ? displayValue(candidate.normalized_value)
                    : undefined;
                  const sourceUrl = typeof candidate.evidence?.record_url === "string"
                    ? candidate.evidence.record_url
                    : "";
                  const decisionBusy = Boolean(candidateDecisionPending);
                  const candidateActions = lifecycle === "proposed" ? (
                    <>
                      <button className="candidate-action" type="button" disabled={pending || decisionBusy || !hasCandidateValue(candidate.value)} onClick={() => applyCandidate(candidate)}>填入表单</button>
                      <button className="candidate-action danger" type="button" disabled={pending || decisionBusy || candidate.is_locked} title={candidate.is_locked ? "已锁定候选不能拒绝" : undefined} onClick={() => void decideMetadataCandidate(candidate, "reject")}>
                        {candidateDecisionPending === candidate.id ? "正在处理" : "拒绝"}
                      </button>
                      {candidate.is_locked ? <small>已锁定，不能拒绝</small> : null}
                    </>
                  ) : lifecycle === "rejected" || lifecycle === "superseded" ? (
                    <button className="candidate-action" type="button" disabled={pending || decisionBusy} onClick={() => void decideMetadataCandidate(candidate, "reopen")}>
                      {candidateDecisionPending === candidate.id ? "正在处理" : "恢复待审"}
                    </button>
                  ) : undefined;
                  return (
                    <div id={`metadata-candidate-${candidate.id}`} key={candidate.id} className="metadata-candidate-anchor">
                    <CandidateCard
                      className={`metadata-candidate-card lifecycle-${lifecycle} ${candidate.selected ? "candidate-selected" : ""}`.trim()}
                      title={fieldLabels[candidate.field_name] ?? candidate.field_name}
                      value={displayValue(candidate.value)}
                      normalizedValue={normalizedValue}
                      source={<span className="metadata-candidate-source">{sourceLabels[candidate.source] ?? candidate.source}{candidate.is_locked ? <><Lock size={11} />已锁定</> : null}</span>}
                      confidence={candidate.confidence}
                      status={{ label: candidateLifecycleLabels[lifecycle], tone: candidateLifecycleTones[lifecycle] }}
                      evidence={(
                        <>
                          <MetadataCandidateScoreFactors factors={candidate.score_factors ?? {}} />
                          <MetadataCandidateEvidenceList candidate={candidate} fallbackAssetId={item.review_data?.normalized_asset_id ?? null} />
                          {sourceUrl ? <a className="candidate-source-link" href={sourceUrl} target="_blank" rel="noreferrer">查看来源记录 <ExternalLink size={12} /></a> : null}
                        </>
                      )}
                      actions={candidateActions}
                    />
                    </div>
                  );
                })}
                {relationCandidates.map((relation, index) => (
                  <article className={relation.approved ? "candidate-selected" : ""} key={`${relation.kind}-${relation.name}-${index}`}>
                    <header><strong>{relation.kind === "theory_school" ? "理论流派" : relation.kind === "topic" ? "主题" : "概念"}</strong><b>{Math.round(relation.confidence * 100)}%</b></header>
                    <p>{relation.name}</p>
                    <small>{sourceLabels[relation.source] ?? relation.source} · {relation.approved ? "自动确认" : "等待人工确认"}</small>
                    {relation.kind === "theory_school" ? <button type="button" onClick={() => setSchools((current) => current.some((item) => item.name === relation.name) ? current : current.concat({ id: null, name: relation.name }))}>填入流派字段</button> : null}
                    {relation.kind === "topic" ? <button type="button" onClick={() => setTopics((current) => current.some((item) => item.name === relation.name) ? current : current.concat({ id: null, name: relation.name }))}>填入主题字段</button> : null}
                  </article>
                ))}
              </>
            ) : <p className="candidate-empty">尚未生成候选。请检查处理历史或重新识别。</p>}
          </aside>

          <section className="review-pdf admin-panel">
            <header>
              <h2>PDF 与规范文本对照</h2>
              <nav>
                <button className={activeTab === "pdf" ? "active" : ""} onClick={() => setActiveTab("pdf")} type="button">PDF 预览</button>
                <button className={activeTab === "text" ? "active" : ""} onClick={() => setActiveTab("text")} type="button">规范文本</button>
                <button className={activeTab === "ocr" ? "active" : ""} onClick={() => setActiveTab("ocr")} type="button">文本来源</button>
                <button className={activeTab === "pages" ? "active" : ""} onClick={() => setActiveTab("pages")} type="button">页码校对</button>
                <button className={activeTab === "history" ? "active" : ""} onClick={() => setActiveTab("history")} type="button">处理历史</button>
              </nav>
            </header>
            {activeTab === "pdf" ? (
              <div className="review-pdf-frame">
                {previewUrl ? <iframe title={`PDF 预览：${item.source_filename}`} src={previewUrl} /> : <p>{previewError || "正在安全加载后台 PDF 预览……"}</p>}
              </div>
            ) : null}
            {activeTab === "text" ? (
              <div className="review-text-page">
                <header><span>PDF 第 {firstPage?.index ?? 1} 页</span><span>{firstPage?.printed_label ? `印刷页码 ${firstPage.printed_label}` : "无印刷页码"}</span></header>
                <pre>{firstPage?.text || "尚未生成规范逐页文本。"}</pre>
              </div>
            ) : null}
            {activeTab === "ocr" ? (
              <div className="review-source-summary">
                <dl>
                  <div><dt>规范阅读文件</dt><dd>{item.review_data.normalized_asset_id ? "已建立" : "尚未建立"}</dd></div>
                  <div><dt>PDF 总页数</dt><dd>{item.review_data.page_count || "尚未知"}</dd></div>
                  <div><dt>首页文本来源</dt><dd>{firstPage?.text_source === "ocr" ? "PaddleOCR" : firstPage?.text_source === "hybrid" ? "原生文本与 OCR 混合" : firstPage?.text_source === "embedded" ? "PDF 原生文本层" : "尚未知"}</dd></div>
                  <div><dt>首页文字置信度</dt><dd>{firstPage ? `${Math.round(firstPage.confidence * 100)}%` : "尚未知"}</dd></div>
                </dl>
                <p>在线阅读、文档内搜索、全局全文搜索、复制清理和高亮定位均使用这里展示的同一份规范逐页文本。</p>
              </div>
            ) : null}
            {activeTab === "pages" && item.review_data.normalized_asset_id ? <PageMappingEditor assetId={item.review_data.normalized_asset_id} onMessage={setMessage} /> : null}
            {activeTab === "history" ? <AttemptHistory attempts={item.attempts} /> : null}
          </section>
          </form>
          <ConfirmDialog
            open={removeConfirmation}
            title={`移除“${item.review_data.title || item.source_filename}”的处理记录`}
            description="该记录会从复核队列和处理中心隐藏。NAS 原始文件、已生成资产与审计记录仍然保留。"
            confirmLabel="确认移除"
            tone="danger"
            pending={pending}
            onCancel={() => setRemoveConfirmation(false)}
            onConfirm={() => void removeFromQueue()}
          />
          <ConfirmDialog
            open={Boolean(entityRevertPrompt)}
            title={`撤销“${entityRevertPrompt?.label || "实体候选"}”的决定`}
            description="撤销只允许在发布前执行。系统会恢复候选组和审核任务；已经进入后续编辑的实体不会被强行删除。"
            confirmLabel="确认撤销"
            tone="danger"
            pending={Boolean(entityDecisionPending)}
            reasonLabel="撤销原因（必填）"
            reasonRequired
            onCancel={() => {
              if (!entityDecisionPending) setEntityRevertPrompt(null);
            }}
            onConfirm={(reason) => {
              if (entityRevertPrompt) void revertEntityResolution(entityRevertPrompt, reason);
            }}
          />
          <ConfirmDialog
            open={Boolean(entityDecisionPrompt)}
            title={entityDecisionPrompt ? `${entityResolutionActionLabels[entityDecisionPrompt.action]}“${entityDecisionPrompt.candidate.label}”` : "确认实体决定"}
            description={entityDecisionPrompt?.action === "link_existing"
              ? "确认后会把当前名称关联到这个馆内实体。同名人物必须由管理员或编辑明确判断，系统不会仅凭名称自动合并。"
              : entityDecisionPrompt?.action === "create_draft"
                ? "系统只会创建未公开草稿。草稿仍需补充权威信息并通过后续审核。"
                : entityDecisionPrompt?.action === "keep_unresolved"
                  ? "该名称会保留在本次入库记录中，但不会建立或关联权威实体。"
                  : "该候选会被拒绝，并保留在决定历史中。"}
            confirmLabel={entityDecisionPrompt ? entityResolutionActionLabels[entityDecisionPrompt.action] : "确认"}
            tone={entityDecisionPrompt?.action === "reject" ? "danger" : "default"}
            pending={Boolean(entityDecisionPending)}
            reasonLabel="决定说明（可选）"
            onCancel={() => {
              if (!entityDecisionPending) setEntityDecisionPrompt(null);
            }}
            onConfirm={(reason) => {
              if (entityDecisionPrompt) {
                void decideEntityResolution(
                  entityDecisionPrompt.candidate,
                  entityDecisionPrompt.action,
                  reason,
                );
              }
            }}
          />
        </>
      )}
    </div>
  );
}

function InlineMetadataCandidates({
  candidates,
  busy,
  onApply,
  onReject,
}: {
  candidates: MetadataCandidate[];
  busy: boolean;
  onApply: (candidate: MetadataCandidate) => void;
  onReject: (candidate: MetadataCandidate) => void;
}) {
  if (!candidates.length) return null;
  return (
    <section className="inline-metadata-candidates" aria-label="该字段的系统建议" aria-live="polite">
      <header><strong>系统建议</strong><span>最多显示 3 项，采用后仍需保存复核内容</span></header>
      {candidates.map((candidate) => {
        const lifecycle = resolvedCandidateLifecycle(candidate);
        return (
          <article key={candidate.id} className={`lifecycle-${lifecycle}`}>
            <div>
              <strong>{displayValue(candidate.value)}</strong>
              <small>{sourceLabels[candidate.source] ?? candidate.source} · {Math.round(candidate.confidence * 100)}%</small>
            </div>
            <div>
              <button type="button" disabled={busy || lifecycle === "accepted"} onClick={() => onApply(candidate)}>
                {lifecycle === "accepted" ? "已接受" : "采用"}
              </button>
              <button
                type="button"
                onClick={() => document.getElementById(`metadata-candidate-${candidate.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
              >
                证据
              </button>
              {lifecycle === "proposed" ? (
                <button className="danger" type="button" disabled={busy || candidate.is_locked} onClick={() => onReject(candidate)}>拒绝</button>
              ) : null}
            </div>
          </article>
        );
      })}
    </section>
  );
}

function Field({
  label,
  wide = false,
  locked,
  onToggleLock,
  children,
}: {
  label: string;
  wide?: boolean;
  locked: boolean;
  onToggleLock: () => void;
  children: React.ReactNode;
}) {
  return (
    <label className={wide ? "wide" : ""}>
      <span className="review-field-label">{label}<button type="button" className={locked ? "locked" : ""} onClick={onToggleLock} aria-label={locked ? `取消锁定${label}` : `锁定${label}`}><Lock size={10} />{locked ? "已锁定" : "锁定"}</button></span>
      {children}
    </label>
  );
}

function CoverCandidatePreview({ candidate }: { candidate: CoverCandidate }) {
  const token = getServerSessionCredential();
  const source = candidate.thumbnail_url;
  const [loaded, setLoaded] = useState<{ source: string; url: string } | null>(null);
  const [failedSource, setFailedSource] = useState("");

  useEffect(() => {
    if (!token || !source) return;
    let active = true;
    let objectUrl = "";
    void apiBlob(source, token)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) {
          setLoaded({ source, url: objectUrl });
        } else {
          URL.revokeObjectURL(objectUrl);
        }
      })
      .catch(() => {
        if (active) setFailedSource(source);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source, token]);

  const imageUrl = loaded?.source === source ? loaded.url : "";
  const failed = !token || !source || failedSource === source;

  return (
    <div
      className={`cover-candidate-image${failed ? " failed" : imageUrl ? "" : " loading"}`}
      role="img"
      aria-label={`PDF 第 ${candidate.page_index} 页封面候选`}
      style={imageUrl ? { backgroundImage: `url("${imageUrl}")` } : undefined}
    >
      {!imageUrl ? (
        <span>{failed ? "预览不可用，请重新分析" : "正在读取候选页……"}</span>
      ) : null}
    </div>
  );
}

function RecommendationImageEditor({
  workId,
  documentType,
  onMessage,
}: {
  workId: string;
  documentType: FormState["documentType"];
  onMessage: (message: string) => void;
}) {
  const [preview, setPreview] = useState("");
  const [missing, setMissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [image, setImage] = useState<File | null>(null);

  useEffect(() => {
    const token = getServerSessionCredential();
    if (!token || !workId) return;
    let active = true;
    let objectUrl = "";
    void apiRequest<{ available: boolean }>(
      `/catalog/admin/works/${workId}/recommendation-image/?metadata=1&v=${revision}`,
      {},
      token,
    )
      .then((metadata) => {
        if (!metadata.available) {
          if (active) {
            setPreview("");
            setMissing(true);
          }
          return null;
        }
        return apiBlob(`/catalog/admin/works/${workId}/recommendation-image/?v=${revision}`, token);
      })
      .then((blob) => {
        if (!blob) return;
        objectUrl = URL.createObjectURL(blob);
        if (active) {
          setPreview(objectUrl);
          setMissing(false);
        } else {
          URL.revokeObjectURL(objectUrl);
        }
      })
      .catch(() => {
        if (active) {
          setPreview("");
          setMissing(true);
        }
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [revision, workId]);

  async function submitImage() {
    const token = getServerSessionCredential();
    if (!token || !image) return;
    const body = new FormData();
    body.append("image", image);
    setBusy(true);
    try {
      await apiRequest(`/catalog/admin/works/${workId}/recommendation-image/`, { method: "POST", body }, token);
      setImage(null);
      setRevision((value) => value + 1);
      onMessage("推荐图例已经由管理员替换。后续自动识别不会覆盖这张图片。");
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : "推荐图例上传失败。");
    } finally {
      setBusy(false);
    }
  }

  async function change(action: "regenerate" | "clear") {
    const token = getServerSessionCredential();
    if (!token) return;
    setBusy(true);
    try {
      await apiRequest(
        `/catalog/admin/works/${workId}/recommendation-image/`,
        action === "clear"
          ? { method: "DELETE" }
          : { method: "POST", body: JSON.stringify({ action: "regenerate" }) },
        token,
      );
      setRevision((value) => value + 1);
      onMessage(action === "clear" ? "人工图例已经移除，系统将使用可用的自动图例。" : "推荐图例已经重新生成。");
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : "推荐图例处理失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="recommendation-image-review">
      <header>
        <div>
          <h3>推荐卡片图例</h3>
          <p>{documentType === "book" ? "默认使用已确认的图书封面。" : "默认使用 PDF 前部第一张有效页面。"} 管理员上传图片后，以人工图片为准。</p>
        </div>
        <div>
          <button type="button" disabled={busy} onClick={() => void change("regenerate")}><RefreshCw size={14} />恢复自动图例</button>
          <button type="button" disabled={busy} onClick={() => void change("clear")}>移除人工图例</button>
        </div>
      </header>
      <div className="recommendation-image-body">
        <div className={`recommendation-image-preview${missing ? " missing" : ""}`} style={preview ? { backgroundImage: `url("${preview}")` } : undefined}>
          {!preview ? <span>{missing ? "尚无图例" : "正在读取图例……"}</span> : null}
        </div>
        <div>
          <label className="knowledge-image-upload">
            <span>{image?.name || "选择替换图片"}</span>
            <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setImage(event.target.files?.[0] ?? null)} />
          </label>
          <button className="button secondary" type="button" disabled={!image || busy} onClick={() => void submitImage()}>{busy ? <LoaderCircle className="spin" size={15} /> : null}上传并采用</button>
          <small>支持 JPEG、PNG 与 WebP，文件不超过 12 MB。公开推荐、首页精选和相关馆藏使用同一张图例。</small>
        </div>
      </div>
    </section>
  );
}

function EntityPicker({
  label,
  field,
  values,
  onChange,
  locked,
  onToggleLock,
  endpoint,
  createHref,
  createLabel,
  nameField,
  allowInlineCreate = true,
}: {
  label: string;
  field: string;
  values: EntityRef[];
  onChange: (values: EntityRef[]) => void;
  locked: boolean;
  onToggleLock: (field: string) => void;
  endpoint: string;
  createHref: string;
  createLabel: string;
  nameField: "name" | "preferred_name";
  allowInlineCreate?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<EntityRef[]>([]);
  const [loading, setLoading] = useState(false);
  const listboxId = useId();

  useEffect(() => {
    if (!open) return;
    const token = getServerSessionCredential();
    if (!token) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setLoading(true);
      const suffix = draft.trim() ? `?search=${encodeURIComponent(draft.trim())}` : "";
      apiRequest<{ results: Array<Record<string, unknown>> }>(`${endpoint}${suffix}`, {}, token)
        .then((payload) => {
          if (!active) return;
          setOptions(payload.results.map((item) => ({
            id: String(item.id),
            name: String(item[nameField] ?? ""),
            slug: item.slug ? String(item.slug) : undefined,
          })).filter((item) => item.name));
        })
        .catch(() => {
          if (active) setOptions([]);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [draft, endpoint, nameField, open]);

  function addNew() {
    const value = draft.replace(/\s+/g, " ").trim();
    if (!value || values.some((existing) => existing.name.toLocaleLowerCase() === value.toLocaleLowerCase())) {
      setDraft("");
      return;
    }
    onChange(values.concat({ id: null, name: value }));
    setDraft("");
    setOpen(false);
  }

  function select(option: EntityRef) {
    if (!values.some((existing) => existing.id === option.id || existing.name.toLocaleLowerCase() === option.name.toLocaleLowerCase())) {
      onChange(values.concat(option));
    }
    setDraft("");
    setOpen(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      const first = options.find((option) => (
        option.name.toLocaleLowerCase() === draft.trim().toLocaleLowerCase()
      )) ?? options[0];
      if (first) select(first);
      else if (allowInlineCreate) addNew();
    }
    if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="tag-editor entity-picker wide">
      <span className="review-field-label">{label}<button type="button" className={locked ? "locked" : ""} onClick={() => onToggleLock(field)}><Lock size={10} />{locked ? "已锁定" : "锁定"}</button></span>
      <div>
        {values.map((value, index) => <button className="tag-value" type="button" key={`${value.id ?? value.name}-${index}`} onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}>{value.name}{value.id ? "" : " · 草稿"} ×</button>)}
        <span className="tag-input entity-input">
          <input
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder="搜索已有条目或输入新名称"
            role="combobox"
            aria-controls={listboxId}
            aria-expanded={open}
            aria-autocomplete="list"
          />
          <button type="button" onClick={() => setOpen((value) => !value)} aria-label="显示候选"><ChevronsUpDown size={13} /></button>
          {open ? (
            <span className="entity-options" role="listbox" id={listboxId}>
              {loading ? <small>正在搜索已有条目……</small> : null}
              {!loading && options.map((option) => (
                <button type="button" role="option" aria-selected={false} key={option.id} onClick={() => select(option)}>
                  <span><strong>{option.name}</strong><small>使用已有档案</small></span><Check size={13} />
                </button>
              ))}
              {allowInlineCreate && draft.trim() && !options.some((option) => option.name.toLocaleLowerCase() === draft.trim().toLocaleLowerCase()) ? (
                <button type="button" onClick={addNew}>
                  <span><strong>暂存“{draft.trim()}”</strong><small>保存复核内容时建立草稿档案，发布前仍需核对</small></span><Plus size={13} />
                </button>
              ) : null}
              <Link href={`${createHref}?create=${encodeURIComponent(draft.trim())}`} target="_blank">
                <span><strong>{createLabel}</strong><small>在新标签页补全详细资料</small></span><ExternalLink size={13} />
              </Link>
            </span>
          ) : null}
        </span>
      </div>
      <small className="entity-picker-help">{allowInlineCreate ? "同名不会自动合并。请明确选择已有条目；保留自由文本后保存，系统会建立草稿档案。" : "同名不会自动关联。这里只允许明确选择已有条目；没有合适候选时，请进入独立管理页建立完整档案。"}</small>
    </div>
  );
}

function mergeKnowledgeRefs(current: KnowledgeRef[], next: EntityRef[]) {
  return next.map((value, index) => {
    const existing = current.find((item) => (
      (value.id && item.id === value.id)
      || item.name.toLocaleLowerCase() === value.name.toLocaleLowerCase()
    ));
    return existing ?? {
      ...value,
      is_primary: index === 0 && current.length === 0,
      strength: "medium" as const,
      role: "local_mention" as const,
      evidence_page: null,
      evidence_text: "",
    };
  });
}

function RelationAssignmentEditor({
  kind,
  values,
  onChange,
}: {
  kind: "discipline" | "theory" | "subdiscipline" | "topic";
  values: KnowledgeRef[];
  onChange: (values: KnowledgeRef[]) => void;
}) {
  if (!values.length) return null;
  const update = (index: number, changes: Partial<KnowledgeRef>) => {
    onChange(values.map((item, itemIndex) => itemIndex === index ? { ...item, ...changes } : item));
  };
  const roleLabels: Record<NonNullable<KnowledgeRef["role"]>, string> = {
    foundational: "奠基文献",
    development: "理论发展",
    introduction: "入门综述",
    empirical_application: "经验应用",
    method_use: "方法使用",
    criticism: "理论批评",
    theory_history: "理论史研究",
    local_mention: "局部提及",
  };
  return (
    <div className="relation-assignment-editor wide">
      <header><strong>关系判断与证据</strong><span>管理员确认后优先于系统建议</span></header>
      {values.map((value, index) => (
        <article key={`${value.id ?? value.name}-assignment`}>
          <strong>{value.name}</strong>
          {kind === "theory" ? (
            <label><span>文献角色</span><select value={value.role || "local_mention"} onChange={(event) => update(index, { role: event.target.value as KnowledgeRef["role"] })}>{Object.entries(roleLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
          ) : null}
          {kind === "theory" || kind === "subdiscipline" ? (
            <label><span>关联强度</span><select value={value.strength || "medium"} onChange={(event) => update(index, { strength: event.target.value as KnowledgeRef["strength"] })}><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
          ) : null}
          <label className="relation-primary"><input type="checkbox" checked={Boolean(value.is_primary)} onChange={(event) => onChange(values.map((item, itemIndex) => ({ ...item, is_primary: itemIndex === index ? event.target.checked : event.target.checked ? false : item.is_primary })))} /><span>主要关系</span></label>
          <label><span>证据页</span><input type="number" min="1" value={value.evidence_page ?? ""} onChange={(event) => update(index, { evidence_page: Number(event.target.value) || null })} /></label>
          <label className="relation-evidence"><span>证据片段</span><textarea rows={2} value={value.evidence_text ?? ""} onChange={(event) => update(index, { evidence_text: event.target.value })} placeholder="说明为什么把本文献归入这里" /></label>
        </article>
      ))}
    </div>
  );
}

function ReleaseImpactPanel({
  form,
  authors,
  disciplines,
  schools,
  subdisciplines,
  topics,
  saved,
  publicSlug,
}: {
  form: FormState;
  authors: EntityRef[];
  disciplines: KnowledgeRef[];
  schools: KnowledgeRef[];
  subdisciplines: KnowledgeRef[];
  topics: KnowledgeRef[];
  saved: ReleaseImpact;
  publicSlug: string | null;
}) {
  const groups = [
    { label: "学者页面", values: authors },
    { label: "学科页面", values: disciplines },
    { label: "理论传统", values: schools },
    { label: "子学科", values: subdisciplines },
    { label: "研究主题", values: topics },
  ];
  const destinations = groups.reduce((total, group) => total + group.values.length, 2);
  return (
    <aside className="release-impact-panel admin-panel">
      <header><div><h2>发布影响预览</h2><p>保存后由关系数据自动生成，无需逐页重复配置。</p></div><b>{destinations} 个去向</b></header>
      <article className="release-impact-work"><span>馆藏作品</span><strong>{form.title || "待填写题名"}</strong><small>{form.documentType === "book" ? "图书" : form.documentType === "journal_article" ? "期刊论文" : form.documentType === "thesis" ? "学位论文" : "研究报告"}</small>{publicSlug ? <Link href={`/works/${publicSlug}`} target="_blank">查看公开页 <ExternalLink size={13} /></Link> : null}</article>
      {groups.map((group) => (
        <section key={group.label}><h3>{group.label}</h3>{group.values.length ? group.values.map((value) => <p key={value.id ?? value.name}><span>{value.name}</span>{value.slug ? <Link href={group.label === "学者页面" ? `/scholars/${value.slug}` : group.label === "学科页面" ? `/disciplines/${value.slug}` : group.label === "理论传统" ? `/theory-schools/${value.slug}` : group.label === "子学科" ? `/subdisciplines/${value.slug}` : `/topics/${value.slug}`} target="_blank"><ExternalLink size={12} /></Link> : <small>保存后建立</small>}</p>) : <p className="release-impact-empty">未归类，不影响发布</p>}</section>
      ))}
      <section><h3>检索与阅读</h3><p><span>全文检索结果</span><small>保存后重建索引</small></p><p><span>PDF 在线阅读</span><small>{saved?.work?.href ? "已经可访问" : "发布后可访问"}</small></p></section>
      <footer>这里显示的是当前表单预计产生的公开去向。被拒绝或未确认的系统候选不会进入前台。</footer>
    </aside>
  );
}

function AttemptHistory({ attempts }: { attempts: ProcessingAttempt[] }) {
  if (!attempts.length) return <p className="attempt-empty">尚无处理日志。</p>;
  return (
    <div className="attempt-history">
      {attempts.map((attempt) => (
        <article key={attempt.id}>
          <header><strong>{attempt.stage}</strong><span>第 {attempt.attempt_number} 次 · {attempt.status}</span><time>{new Date(attempt.started_at).toLocaleString("zh-CN")}</time></header>
          {attempt.error_message ? <p className="attempt-error">{attempt.error_code ? `${attempt.error_code} · ` : ""}{attempt.error_message}</p> : null}
          {attempt.log_excerpt ? <pre>{attempt.log_excerpt}</pre> : null}
          {Object.keys(attempt.output_summary ?? {}).length ? <small>{JSON.stringify(attempt.output_summary)}</small> : null}
        </article>
      ))}
    </div>
  );
}
