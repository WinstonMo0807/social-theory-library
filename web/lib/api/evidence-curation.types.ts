export type EvidenceCurationType = "topic" | "scholar" | "node";
export type EvidenceCurationSource = {
  id: string;
  source_type: "span" | "passage";
  text: string;
  context_before?: string;
  context_after?: string;
  work_id: string;
  work_title: string;
  edition_id: string;
  edition_label: string;
  asset_id: string;
  page_start: number | null;
  page_end: number | null;
  printed_label?: string;
  document_revision_id?: string | null;
  reader_url: string;
  public_eligible: boolean;
};
export type EvidenceCurationItem = {
  id?: string;
  source_type: "span" | "passage";
  source_id: string;
  group_title: string;
  reason: string;
  order: number;
  source: EvidenceCurationSource;
};
export type PublishedEvidenceCuration = {
  configured: boolean;
  object_type: EvidenceCurationType;
  object_id: string;
  title: string;
  items: EvidenceCurationItem[];
};
export type EvidenceCurationDraft = PublishedEvidenceCuration & {
  id: string | null;
  edit_version: string;
  has_unpublished_changes: boolean;
};

/** Save references and editorial annotations only; never send source text back. */
export function evidenceCurationSavePayload(draft: EvidenceCurationDraft) {
  return {
    edit_version: draft.edit_version,
    items: draft.items.map((item, order) => ({
      ...(item.id ? { id: item.id } : {}), source_type: item.source_type,
      source_id: item.source_id, group_title: item.group_title, reason: item.reason, order,
    })),
  };
}

/** Recommendations never truncate existing annotations; required fields apply to topic curation. */
export function topicEvidenceAnnotationProblem(items: EvidenceCurationItem[]) {
  if (items.some(item => !item.group_title.trim())) return "请为每段原文填写分组名称。";
  if (items.some(item => !item.reason.trim())) return "请为每段原文填写阅读说明。";
  return "";
}

/** Display sorting retains the original editorial row index for preview-to-field navigation. */
export function topicEvidenceRows(items: EvidenceCurationItem[], ordering: "book" | "editorial") {
  const rows = items.map((item, index) => ({ item, index }));
  if (ordering === "book") rows.sort((a, b) => a.item.source.work_title.localeCompare(b.item.source.work_title, "zh-CN") || a.item.source.work_id.localeCompare(b.item.source.work_id) || a.index - b.index);
  return rows;
}
