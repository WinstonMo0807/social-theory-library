import type { WorkflowStepKey, WorkflowStepStatus } from "./workflow-state";

export type WorkflowIssue = {
  code?: string;
  message: string;
  severity?: "blocker" | "warning" | "info";
  step?: WorkflowStepKey;
  field?: string;
  action_target?: { step?: WorkflowStepKey; field?: string } | string | null;
};

export type WorkflowStep = {
  key: WorkflowStepKey;
  label: string;
  status: WorkflowStepStatus;
  issues: WorkflowIssue[];
  summary?: string | Record<string, unknown> | null;
  next_action?: string | null;
};

export type WorkflowEvaluation = {
  overall_status: string;
  current_step: WorkflowStepKey;
  suggested_next_step: WorkflowStepKey | null;
  steps: WorkflowStep[];
  unresolved_count: number;
  warnings_count: number;
  blockers_count: number;
};

export type WorkflowContext = {
  item_id?: string | null;
  work_id?: string | null;
  edition_id?: string | null;
  title?: string;
  filename?: string;
  document_type?: string;
  publication_state?: string;
  preview_url?: string;
  public_url?: string;
  return_href?: string;
  [key: string]: unknown;
};

export type WorkflowPermissions = {
  can_edit?: boolean;
  can_confirm?: boolean;
  can_manage_publication?: boolean;
  can_publish?: boolean;
  can_withdraw?: boolean;
  can_manage_curation?: boolean;
  capabilities?: string[];
  [key: string]: unknown;
};

export type WorkflowQueue = {
  next_item_id?: string | null;
  next_work_id?: string | null;
  return_href?: string;
  remaining_count?: number;
  [key: string]: unknown;
};

export type WorkflowCandidate = {
  id: string;
  field_name?: string;
  label?: string;
  value?: unknown;
  proposed_value?: unknown;
  current_value?: unknown;
  status?: string;
  source?: string;
  confidence?: number;
  evidence?: unknown;
  evidence_records?: unknown[];
  candidate_count?: number;
  decision_url?: string;
  available_actions?: string[];
  [key: string]: unknown;
};

export type WorkflowPayload = {
  mode: "intake" | "maintenance";
  context: WorkflowContext;
  workflow: WorkflowEvaluation;
  data: Record<string, unknown>;
  candidates: Record<string, unknown>;
  permissions: WorkflowPermissions;
  queue: WorkflowQueue;
};

export type WorkflowDrafts = Record<WorkflowStepKey, Record<string, unknown>>;

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function asString(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return fallback;
}

export function asBoolean(value: unknown): boolean {
  return value === true;
}

export function asNumber(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function candidateList(value: unknown): WorkflowCandidate[] {
  if (Array.isArray(value)) {
    return value.flatMap((entry, index) => {
      const row = asRecord(entry);
      return Object.keys(row).length ? [{ id: asString(row.id, `candidate-${index}`), ...row } as WorkflowCandidate] : [];
    });
  }
  const record = asRecord(value);
  return Object.values(record).flatMap((entry) => candidateList(entry));
}
