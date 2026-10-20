import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "../api";
import type { ResolvedEvidence } from "./research.client";

export const calibrationStatuses = { submitted: "待审核", reviewed: "已审核", published: "已公开", rejected: "已退回" } as const;
export const calibrationScopes = { bibliography: "仅书目级", passages: "所选段落" } as const;
export const alignmentStatuses = { confirmed: "对应段落", no_match: "未找到对应段落", addition: "增补内容" } as const;
export type CalibrationStatus = keyof typeof calibrationStatuses;
export type CalibrationAction = "review" | "publish" | "reject";
export type CalibrationSource = { title: string; version_label: string; authors: string[]; reader_url: string | null };
export type AdminCalibration = {
  id: string; revision: number; request_id: string; created_at: string; updated_at: string;
  status: CalibrationStatus; scope: keyof typeof calibrationScopes; source_available: boolean; notice: string;
  review_note: string; reviewer_id: number | null;
  pair_sources: { left: CalibrationSource; right: CalibrationSource } | null;
  data: {
    left_asset_id: string; right_asset_id: string; left_document_revision_id: string; right_document_revision_id: string;
    basis: string; alignments: Array<{ id: string; left: ResolvedEvidence | null; right: ResolvedEvidence | null; status: keyof typeof alignmentStatuses }>;
  };
};
export type AdminCalibrationList = { count: number; next: string | null; previous: string | null; results: AdminCalibration[] };
export type CalibrationCommand = { request_id: string; expected_revision: number; note: string };
export const calibrationAdminPath = (id?: string) => `/reading/parallel-calibrations/admin/${id ? `${encodeURIComponent(id)}/` : ""}`;

/** Keep the exact published revision and paragraph, without accepting an external destination. */
export function calibrationReaderPath(value: string | null | undefined) {
  if (!value || !value.startsWith("/reader/") || /[\\\s]/.test(value)) return "";
  const address = new URL(value, "https://reader.invalid"), uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const asset = address.pathname.slice("/reader/".length), page = address.searchParams.get("page") || "";
  const revision = address.searchParams.get("revision") || "", passage = address.searchParams.get("passage");
  if (!uuid.test(asset) || !/^[1-9]\d{0,5}$/.test(page) || !uuid.test(revision) || passage && !uuid.test(passage)) return "";
  return `/reader/${asset}?${new URLSearchParams({ page, revision, ...(passage ? { passage } : {}) })}`;
}

export async function commandCalibration(id: string, action: CalibrationAction, input: CalibrationCommand) {
  const session = new AbortController(), unsubscribe = subscribeToSessionChanges(() => session.abort());
  try {
    return await apiRequest<AdminCalibration & { applied_revision: number }>(`${calibrationAdminPath(id)}${action}/`, {
      method: "POST", cache: "no-store", body: JSON.stringify(input),
      signal: AbortSignal.any([session.signal, AbortSignal.timeout(30000)]),
    }, getServerSessionCredential(), false);
  } catch (reason) {
    // A timeout or intermediary throttle cannot confirm whether the write reached the server.
    if (reason instanceof ApiRequestError && [408, 429].includes(reason.status)) throw new ApiRequestError(reason.message);
    throw reason;
  } finally { unsubscribe(); }
}

export function calibrationDate(value: string) {
  return Number.isNaN(Date.parse(value)) ? "时间待核对" : new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
}
