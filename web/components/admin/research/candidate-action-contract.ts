export type CandidateActionDescriptor = {
  action: string;
  label: string;
  url: string;
  method: string;
  payload: Record<string, unknown>;
  tone: "default" | "secondary" | "danger";
  editable: boolean;
  valueField: string;
  disabled: boolean;
  disabledReason: string;
  source: "descriptor" | "legacy";
};

export type CandidateActionSource = {
  action_descriptors?: unknown;
  actionDescriptors?: unknown;
  actions?: unknown;
  available_actions?: unknown;
  decision_url?: unknown;
  verify_url?: unknown;
  verify_payload?: unknown;
  proposed_value?: unknown;
  value?: unknown;
  label?: unknown;
  entity_type?: unknown;
  kind?: unknown;
  [key: string]: unknown;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function descriptorRows(candidate: CandidateActionSource): Record<string, unknown>[] {
  const values = [candidate.action_descriptors, candidate.actionDescriptors, candidate.actions];
  for (const value of values) {
    if (!Array.isArray(value)) continue;
    const rows = value.map(asRecord).filter((row) => Object.keys(row).length > 0);
    if (rows.length) return rows;
  }
  return [];
}

function actionLabel(action: string, candidate: CandidateActionSource): string {
  const person = String(candidate.entity_type ?? "") === "person";
  return ({
    inspect: "查看依据",
    verify: "核实此结果",
    accept: "采用",
    apply_to_draft: "采用到草稿",
    apply_draft: "采用到草稿",
    accept_with_edit: "修改后采用",
    link_existing: person ? "关联已有学者" : "关联馆内实体",
    use_value: "采用规范文本",
    create_draft: person ? "创建新学者主页" : "创建实体草稿",
    keep_unresolved: person ? "仅添加为责任者" : "保留未解析值",
    defer: "稍后处理",
    reject: "拒绝/不采用",
    match_existing: "匹配已有对象",
  } as Record<string, string>)[action] ?? action;
}

function actionTone(action: string, raw: Record<string, unknown>): CandidateActionDescriptor["tone"] {
  const explicit = asString(raw.tone ?? raw.style ?? raw.variant).toLocaleLowerCase();
  if (["danger", "destructive", "critical"].includes(explicit) || action === "reject") return "danger";
  if (["secondary", "quiet", "subtle"].includes(explicit) || ["inspect", "verify", "defer"].includes(action)) return "secondary";
  return "default";
}

function defaultUrl(action: string, candidate: CandidateActionSource): string {
  return asString(action === "verify" ? candidate.verify_url : candidate.decision_url);
}

function normalizeDescriptor(
  raw: Record<string, unknown>,
  candidate: CandidateActionSource,
  source: CandidateActionDescriptor["source"],
): CandidateActionDescriptor | null {
  const action = asString(raw.action ?? raw.key ?? raw.name ?? raw.id);
  if (!action) return null;
  const payload = asRecord(raw.payload ?? raw.body);
  const explicitEditable = raw.editable === true
    || raw.requires_value === true
    || raw.requires_edited_value === true;
  const valueField = asString(
    raw.value_field ?? raw.edit_field ?? raw.payload_field,
    String(candidate.kind ?? "") === "derived_claim_curation" ? "proposition" : "proposed_value",
  );
  const availability = asRecord(raw.availability);
  const availabilityReason = availability.available === false
    ? asString(availability.reason)
    : "";
  return {
    action,
    label: asString(raw.label ?? raw.title, actionLabel(action, candidate)),
    url: asString(raw.url ?? raw.endpoint ?? raw.decision_url ?? raw.href, defaultUrl(action, candidate)),
    method: asString(raw.method, "POST").toUpperCase(),
    payload,
    tone: actionTone(action, raw),
    editable: explicitEditable || action === "accept_with_edit",
    valueField,
    disabled: raw.disabled === true || raw.enabled === false || availability.available === false,
    disabledReason: asString(raw.disabled_reason ?? raw.reason, availabilityReason),
    source,
  };
}

export function resolveCandidateActionDescriptors(
  candidate: CandidateActionSource,
): CandidateActionDescriptor[] {
  const explicit = descriptorRows(candidate)
    .map((row) => normalizeDescriptor(row, candidate, "descriptor"))
    .filter((row): row is CandidateActionDescriptor => Boolean(row));
  if (explicit.length) return dedupeActions(explicit);

  const legacy = Array.isArray(candidate.available_actions)
    ? candidate.available_actions.map((value) => String(value ?? "").trim()).filter(Boolean)
    : [];
  return dedupeActions(legacy.flatMap((action) => {
    const row = normalizeDescriptor({ action }, candidate, "legacy");
    return row ? [row] : [];
  }));
}

function dedupeActions(actions: CandidateActionDescriptor[]): CandidateActionDescriptor[] {
  const seen = new Set<string>();
  return actions.filter((descriptor) => {
    if (seen.has(descriptor.action)) return false;
    seen.add(descriptor.action);
    return true;
  });
}

export function candidateEditableValue(candidate: CandidateActionSource): string {
  const value = candidate.proposed_value ?? candidate.value ?? candidate.label ?? "";
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return JSON.stringify(value, null, 2);
}

export function parseCandidateEditableValue(text: string, original: unknown): unknown {
  if (typeof original === "number") {
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : text;
  }
  if (typeof original === "boolean") {
    if (text.trim().toLocaleLowerCase() === "true") return true;
    if (text.trim().toLocaleLowerCase() === "false") return false;
    return text;
  }
  if (original && typeof original === "object") {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  return text;
}

export function buildCandidateActionBody(
  descriptor: CandidateActionDescriptor,
  editedValue?: unknown,
  fallback: Record<string, unknown> = {},
): Record<string, unknown> {
  const body = { ...fallback, ...descriptor.payload };
  if (!("action" in descriptor.payload)) body.action = descriptor.action;
  if (editedValue !== undefined) body[descriptor.valueField] = editedValue;
  return body;
}
