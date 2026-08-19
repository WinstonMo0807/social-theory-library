export const WORKFLOW_STEP_KEYS = [
  "file",
  "work",
  "bibliography",
  "contributors",
  "classification",
  "knowledge",
  "reader",
  "curation",
  "publication",
] as const;

export type WorkflowStepKey = (typeof WORKFLOW_STEP_KEYS)[number];
export type WorkflowStepStatus =
  | "pending"
  | "available"
  | "working"
  | "attention"
  | "blocked"
  | "complete"
  | "skipped";

export type WorkflowSectionPresentation = "summary" | "current" | "preview" | "collapsed";

export type WorkflowStepLike = {
  key: WorkflowStepKey;
  status: WorkflowStepStatus;
};

export type ValidationIssue = {
  field: string;
  message: string;
};

export const WORKFLOW_STEP_LABELS: Record<WorkflowStepKey, string> = {
  file: "文件与识别",
  work: "作品",
  bibliography: "书目与出版",
  contributors: "责任者",
  classification: "社科分类",
  knowledge: "理论与主题",
  reader: "阅读文件",
  curation: "策展",
  publication: "发布",
};

const STEP_SET = new Set<string>(WORKFLOW_STEP_KEYS);

export function isWorkflowStepKey(value: unknown): value is WorkflowStepKey {
  return typeof value === "string" && STEP_SET.has(value);
}

export function stepFromHash(hash: string, fallback: WorkflowStepKey): WorkflowStepKey {
  const normalized = hash.replace(/^#/, "").trim();
  return isWorkflowStepKey(normalized) ? normalized : fallback;
}

export function workflowHashUrl(url: string, step: WorkflowStepKey): string {
  const parsed = new URL(url, "http://workflow.local");
  return `${parsed.pathname}${parsed.search}#${step}`;
}

export function sectionPresentations(
  steps: readonly WorkflowStepLike[],
  active: WorkflowStepKey,
): Record<WorkflowStepKey, WorkflowSectionPresentation> {
  const activeIndex = WORKFLOW_STEP_KEYS.indexOf(active);
  const statusByKey = new Map(steps.map((step) => [step.key, step.status]));
  return Object.fromEntries(WORKFLOW_STEP_KEYS.map((key, index) => {
    if (key === active) return [key, "current"];
    if (index === activeIndex + 1) return [key, "preview"];
    const status = statusByKey.get(key);
    if (index < activeIndex && (status === "complete" || status === "skipped")) {
      return [key, "summary"];
    }
    return [key, "collapsed"];
  })) as Record<WorkflowStepKey, WorkflowSectionPresentation>;
}

export function nextWorkflowStep(
  active: WorkflowStepKey,
  steps: readonly WorkflowStepLike[] = [],
): WorkflowStepKey | null {
  const start = WORKFLOW_STEP_KEYS.indexOf(active) + 1;
  const statusByKey = new Map(steps.map((step) => [step.key, step.status]));
  for (let index = start; index < WORKFLOW_STEP_KEYS.length; index += 1) {
    const key = WORKFLOW_STEP_KEYS[index];
    if (statusByKey.get(key) !== "skipped") return key;
  }
  return null;
}

export function bibliographyFields(documentType: string): readonly string[] {
  const common = ["publication_year"] as const;
  if (documentType === "journal_article") {
    return [...common, "journal_title", "volume", "issue", "page_range", "doi"];
  }
  if (documentType === "thesis") {
    return [...common, "degree_institution", "degree_type"];
  }
  if (documentType === "report") {
    return [...common, "report_institution", "publisher"];
  }
  return [
    "version_label",
    ...common,
    "publisher",
    "publication_place",
    "isbn10",
    "isbn13",
    "series",
    "extent",
    "responsibility_statement",
  ];
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function validateWorkflowSection(
  step: WorkflowStepKey,
  value: Record<string, unknown>,
  documentType = "book",
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const requireText = (field: string, message: string) => {
    if (!text(value[field])) issues.push({ field, message });
  };

  if (step === "file") {
    if (value.validation === "failed" || value.is_valid_pdf === false) {
      issues.push({ field: "validation", message: "PDF 校验尚未通过。" });
    }
  }
  if (step === "work") {
    requireText("title", "请填写作品题名。");
    requireText("document_type", "请选择文献类型。");
    requireText("language", "请选择作品语言。");
  }
  if (step === "bibliography") {
    if (documentType === "journal_article") requireText("journal_title", "请填写期刊名。");
    if (documentType === "thesis") requireText("degree_institution", "请填写学位授予单位。");
    if (documentType === "report") requireText("report_institution", "请填写报告责任机构。");
  }
  if (step === "contributors") {
    const contributors = Array.isArray(value.items) ? value.items : [];
    contributors.forEach((entry, index) => {
      const contributor = entry && typeof entry === "object" ? entry as Record<string, unknown> : {};
      if (!text(contributor.display_name)) {
        issues.push({ field: `items.${index}.display_name`, message: `请填写第 ${index + 1} 位责任者名称。` });
      }
      if (!text(contributor.role)) {
        issues.push({ field: `items.${index}.role`, message: `请选择第 ${index + 1} 位责任者角色。` });
      }
    });
  }
  if (step === "classification" && value.confirmed !== true) {
    issues.push({ field: "confirmed", message: "请确认本节分类判断。" });
  }
  if (step === "knowledge" && value.confirmed !== true) {
    issues.push({ field: "confirmed", message: "请确认理论、主题与知识关系。" });
  }
  return issues;
}

export type DirtyFields = Partial<Record<WorkflowStepKey, readonly string[]>>;

export function dirtyFieldCount(dirty: DirtyFields): number {
  return WORKFLOW_STEP_KEYS.reduce((count, key) => count + new Set(dirty[key] ?? []).size, 0);
}

export function withDirtyField(
  dirty: DirtyFields,
  step: WorkflowStepKey,
  field: string,
): DirtyFields {
  const next = new Set(dirty[step] ?? []);
  next.add(field);
  return { ...dirty, [step]: [...next] };
}

function cloneRecord<T>(value: T): T {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

function valueAtPath(source: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((current, part) => {
    if (current === null || current === undefined) return undefined;
    if (Array.isArray(current)) return current[Number(part)];
    if (typeof current !== "object") return undefined;
    return (current as Record<string, unknown>)[part];
  }, source);
}

function setValueAtPath(target: Record<string, unknown>, path: string, value: unknown) {
  const parts = path.split(".");
  let cursor: Record<string, unknown> | unknown[] = target;
  parts.forEach((part, index) => {
    const last = index === parts.length - 1;
    if (last) {
      if (Array.isArray(cursor)) cursor[Number(part)] = cloneRecord(value);
      else cursor[part] = cloneRecord(value);
      return;
    }
    const nextPart = parts[index + 1];
    const wantsArray = /^\d+$/.test(nextPart);
    if (Array.isArray(cursor)) {
      const position = Number(part);
      const existing = cursor[position];
      if (!existing || typeof existing !== "object") cursor[position] = wantsArray ? [] : {};
      cursor = cursor[position] as Record<string, unknown> | unknown[];
      return;
    }
    const existing = cursor[part];
    if (!existing || typeof existing !== "object") cursor[part] = wantsArray ? [] : {};
    cursor = cursor[part] as Record<string, unknown> | unknown[];
  });
}

export function mergeRemoteDrafts<T extends Record<WorkflowStepKey, Record<string, unknown>>>(
  local: T,
  remote: T,
  dirty: DirtyFields,
): T {
  const merged = cloneRecord(remote);
  WORKFLOW_STEP_KEYS.forEach((step) => {
    (dirty[step] ?? []).forEach((path) => {
      setValueAtPath(merged[step], path, valueAtPath(local[step], path));
    });
  });
  return merged;
}
