import type { CatalogPublication } from "./admin-collections";

export type PrimaryEditionPreview = {
  work_id: string;
  edition_id: string;
  title: string;
  request_key: string;
  fingerprint: string;
  can_select: boolean;
  blocking: string[];
  already_primary: boolean;
  current_primary_edition_ids: string[];
  target_public_url: string;
  preview_url: string;
  editions: Array<{ id: string; version_label: string; publication_year: number | null; is_primary: boolean; active_revision_id: string | null; public_slug: string }>;
  impact: string[];
};

export type PrimaryEditionResult = {
  request_key: string;
  work_id: string;
  edition_id: string;
  audit_id: string;
  command_accepted: boolean;
  listing_effective: boolean;
  projections_complete: boolean;
  publication: CatalogPublication;
  public_url: string;
  current_primary_edition_ids: string[];
  editorial_revision_ids: string[];
  events: Array<{ id: string; edition_id: string; status: string; href: string }>;
  detail: string;
};

/** Keep the exact reviewed fingerprint/key across duplicate or uncertain sends. */
export function primaryEditionRequest(preview: PrimaryEditionPreview, editionId: string) {
  if (preview.edition_id !== editionId || !preview.can_select || preview.blocking.length || !/^[a-f0-9]{64}$/i.test(preview.fingerprint) || !/^[a-f0-9-]{36}$/i.test(preview.request_key)) throw new Error("主版本预览无效或存在阻断，请重新核对当前版本。");
  return { request_key: preview.request_key, fingerprint: preview.fingerprint, confirm: true };
}
