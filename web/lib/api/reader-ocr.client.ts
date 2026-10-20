import { ApiRequestError, apiRequest, getServerSessionCredential } from "../api";

export type ReaderOcrAction = "pause" | "resume";
export type ReaderOcrStatus = {
  asset_id: string; edition_id: string; document_revision_id: string | null; source_sha256: string;
  owner_id: number | null; file_page_count: number; ocr_status: string; checked_at: string;
  job: null | {
    id: string; job_version: string; status: string; phase: string; phase_label: string;
    completed_pages: number | null; total_pages: number | null; percent: number | null;
    phase_elapsed_seconds: number | null; updated_at: string; pause_requested: boolean; stale: boolean;
  };
  can_pause: boolean; can_resume: boolean; denied_reason: string; management_url: string | null;
  processed_content: {
    state: "unavailable" | "awaiting_publication" | "published" | "admin_preview";
    url: string | null; label: string; notice: string;
  };
  receipt: null | { request_id: string; action: ReaderOcrAction; job_id: string; applied: true };
};
export type ReaderOcrCommand = {
  action: ReaderOcrAction; request_id: string; job_id: string; job_version: string;
  source_sha256: string; document_revision_id: string | null;
};
export const readerOcrPath = (assetId: string) => `/distribution/assets/${encodeURIComponent(assetId)}/ocr-status/`;

function validateStatus(value: ReaderOcrStatus, assetId: string, ownerId?: number | null) {
  if (!value || value.asset_id !== assetId || ownerId != null && value.owner_id !== ownerId) {
    throw new ApiRequestError("处理状态不属于当前文件或账户，请重新核对。", 403);
  }
  return value;
}

export async function readReaderOcrStatus(assetId: string, ownerId: number | null | undefined, signal: AbortSignal, requestId?: string) {
  const path = `${readerOcrPath(assetId)}${requestId ? `?${new URLSearchParams({ request_id: requestId })}` : ""}`;
  const value = await apiRequest<ReaderOcrStatus>(path, {
    cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
    headers: ownerId != null ? { "X-Reader-Owner": String(ownerId) } : {},
  }, getServerSessionCredential(), false);
  return validateStatus(value, assetId, ownerId);
}

export async function commandReaderOcr(assetId: string, ownerId: number, body: ReaderOcrCommand, signal: AbortSignal) {
  const value = await apiRequest<ReaderOcrStatus>(readerOcrPath(assetId), {
    method: "POST", cache: "no-store", body: JSON.stringify(body), headers: { "X-Reader-Owner": String(ownerId) },
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
  }, getServerSessionCredential(), false);
  return validateStatus(value, assetId, ownerId);
}

/** Only same-site Reader/source-workspace locations; never follow a diagnostic URL. */
export function readerOcrContentPath(value: string | null | undefined, allowManagement: boolean) {
  if (!value?.startsWith("/") || value.startsWith("//") || /[\\\s]/.test(value)) return "";
  const address = new URL(value, "https://reader.invalid");
  const uuid = "[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}";
  if (allowManagement && new RegExp(`^/admin/library/assets/${uuid}/ocr/?$`, "i").test(address.pathname)) return address.pathname;
  if (!new RegExp(`^/reader/${uuid}/?$`, "i").test(address.pathname)) return "";
  const page = address.searchParams.get("page"), revision = address.searchParams.get("revision");
  if (page && !/^[1-9]\d{0,5}$/.test(page) || revision && !new RegExp(`^${uuid}$`, "i").test(revision)) return "";
  const query = new URLSearchParams({ ...(page ? { page } : {}), ...(revision ? { revision } : {}) });
  return `${address.pathname}${query.size ? `?${query}` : ""}`;
}

export function sameReaderOcrCommandSource(status: ReaderOcrStatus, command: ReaderOcrCommand) {
  return status.source_sha256 === command.source_sha256 && status.document_revision_id === command.document_revision_id
    && status.job?.id === command.job_id && status.job.job_version === command.job_version;
}

export function readerOcrReceiptMatches(status: ReaderOcrStatus, command: ReaderOcrCommand) {
  const receipt = status.receipt;
  return receipt?.applied === true && receipt.request_id === command.request_id
    && receipt.action === command.action && receipt.job_id === command.job_id;
}
