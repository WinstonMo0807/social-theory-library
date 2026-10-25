import { apiRequest, apiStreamRequest, getServerSessionCredential, subscribeToSessionChanges } from "../api";
import { PrivateOwnerVerificationError } from "./private-owner";

export type CitationPreviewStatus = {
  audit_id: string; audit_revision: number; content_hash: string; source_generation: number; manuscript_revision: number;
  preview_revision: number; preview_generation: number;
  status: "not_generated" | "queued" | "running" | "completed" | "failed" | "canceled" | "source_changed";
  enabled: boolean; page_count: number | null; converter_version: string | null; fonts_version: string | null;
  poll_after_ms: number | null; notice: string; message: string;
};
export type CitationPreviewKind = "citation-audits" | "citation-sources";
export const citationPreviewPath = (kind: CitationPreviewKind, id: string) => `/reading/${kind}/${encodeURIComponent(id)}/preview/`;
function ownerHeaders(ownerId: string) {
  if (!ownerId) throw new PrivateOwnerVerificationError("请重新验证当前账户后读取私人预览。", 403);
  return { "X-Reader-Owner": ownerId };
}
export async function readCitationPreviewStatus(ownerId: string, kind: CitationPreviewKind, id: string, signal: AbortSignal) {
  const result = await apiRequest<CitationPreviewStatus>(citationPreviewPath(kind, id), { cache: "no-store", headers: ownerHeaders(ownerId),
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]) }, getServerSessionCredential(), false);
  if (result.audit_id !== id) throw new Error("稿件预览身份不匹配，请重新读取原稿。");
  return result;
}
export async function commandCitationPreview(ownerId: string, kind: CitationPreviewKind, id: string, data: {
  action: "generate" | "cancel"; request_id: string; expected_preview_revision: number; source_generation: number;
}) {
  const controller = new AbortController(), unsubscribe = subscribeToSessionChanges(() => controller.abort());
  try {
    return await apiRequest<CitationPreviewStatus>(citationPreviewPath(kind, id), { method: "POST", body: JSON.stringify(data), cache: "no-store", headers: ownerHeaders(ownerId),
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(60000)]) }, getServerSessionCredential(), false);
  } finally { unsubscribe(); }
}
export async function readCitationPreviewPdf(ownerId: string, kind: CitationPreviewKind, id: string, generation: number, signal?: AbortSignal) {
  const response = await apiStreamRequest(`${citationPreviewPath(kind, id)}file/?generation=${generation}`, {
    cache: "no-store", headers: ownerHeaders(ownerId), signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(60000)]) : AbortSignal.timeout(60000),
  }, getServerSessionCredential(), false);
  if (!response.ok || !response.headers.get("Content-Type")?.includes("application/pdf")) throw new Error(`分页预览读取失败（${response.status}）；原稿仍保留。`);
  const blob = await response.blob();
  if (!blob.size || blob.size > 32 * 1024 * 1024) throw new Error("分页预览超出读取范围，请查看解析文字或下载原稿。");
  return blob;
}
