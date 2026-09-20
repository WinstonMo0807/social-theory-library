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
