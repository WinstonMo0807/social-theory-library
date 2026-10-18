import { ApiRequestError, apiRequest, apiStreamRequest, apiUpload, getServerSessionCredential, subscribeToSessionChanges, type UploadProgress } from "../api";
import { apiEndpoint } from "../runtime-api";
import type { FileAdoptInput, FileAdoptPreview, FileAdoptResult, NewWorkEditionInput, NewWorkEditionResult, WorkFileUploadResult, WorkFilesState } from "./work-files.types";

export const workFilesPath = (workId: string, editionId = "", page = 1, impactPage = 1, historyPage = 1) => {
  const params = new URLSearchParams({ page: String(page), impact_page: String(impactPage), history_page: String(historyPage) });
  if (editionId) params.set("edition", editionId);
  return `/catalog/admin/works/${encodeURIComponent(workId)}/files/?${params}`;
};
async function request<T>(path: string, options: RequestInit = {}) {
  const controller = new AbortController(), unsubscribe = subscribeToSessionChanges(() => controller.abort());
  const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(60000), ...(options.signal ? [options.signal] : [])]);
  try { return await apiRequest<T>(path, { ...options, cache: "no-store", signal }, getServerSessionCredential(), false); }
  finally { unsubscribe(); }
}
export function readWorkFiles(workId: string, editionId = "", page = 1, impactPage = 1, historyPage = 1) {
  return request<WorkFilesState>(workFilesPath(workId, editionId, page, impactPage, historyPage));
}
export function createWorkEdition(workId: string, input: NewWorkEditionInput) {
  return request<NewWorkEditionResult>(`/catalog/admin/works/${encodeURIComponent(workId)}/editions/`, { method: "POST", body: JSON.stringify(input) });
}
const adoptPath = (editionId: string, assetId: string) => `/catalog/admin/editions/${encodeURIComponent(editionId)}/files/${encodeURIComponent(assetId)}/adopt/`;
export function prepareFileAdoption(editionId: string, assetId: string) { return request<FileAdoptPreview>(adoptPath(editionId, assetId)); }
export function adoptWorkFile(editionId: string, assetId: string, input: FileAdoptInput) { return request<FileAdoptResult>(adoptPath(editionId, assetId), { method: "POST", body: JSON.stringify(input) }); }
export function uploadWorkFile(editionId: string, body: FormData, onProgress: (progress: UploadProgress) => void, signal?: AbortSignal) {
  // Do not resubmit a large file under a refreshed identity; explicit retry retains the original request key.
  return apiUpload<WorkFileUploadResult>(`/catalog/admin/editions/${encodeURIComponent(editionId)}/files/`, body, getServerSessionCredential(), onProgress, false, { signal, timeoutMs: 15 * 60 * 1000 });
}
export function readWorkFileReceipt(editionId: string, requestKey: string, signal?: AbortSignal) {
  return request<WorkFileUploadResult>(`/catalog/admin/editions/${encodeURIComponent(editionId)}/files/requests/${encodeURIComponent(requestKey)}/`, { signal });
}
export function generateWorkFileReader(path: string, input: { request_key: string; expected_asset_updated_at: string }) {
  const value = internalPath(path);
  if (!/^\/catalog\/admin\/editions\/[0-9a-f-]+\/files\/[0-9a-f-]+\/generate-reader\/$/i.test(value)) throw new Error("阅读副本生成地址不属于当前文件。");
  return request<WorkFileUploadResult>(value, { method: "POST", body: JSON.stringify(input) });
}
export function updateWorkFileRights(editionId: string, assetId: string, input: { request_key: string; expected_asset_updated_at: string; rights_note: string }) {
  return request<{ request_key: string; asset_id: string; rights_note: string; updated_at: string }>(
    `/catalog/admin/editions/${encodeURIComponent(editionId)}/files/${encodeURIComponent(assetId)}/rights/`, { method: "PATCH", body: JSON.stringify(input) });
}
export function prepareWorkFilePublic(editionId: string, assetId: string, input: { request_key: string; expected_asset_updated_at: string; confirm: true }) {
  return request<{ request_key: string; asset_id: string; status: string; detail: string }>(
    `/catalog/admin/editions/${encodeURIComponent(editionId)}/files/${encodeURIComponent(assetId)}/prepare-public/`, { method: "POST", body: JSON.stringify(input) });
}
function internalPath(path: string) {
  const value = path.startsWith("/api/") ? path.slice(4) : path;
  if (!/^\/(catalog\/admin|ingestion\/items)\//.test(value) || decodeURIComponent(value).includes("..")) throw new Error("文件操作地址不属于当前管理工作区。");
  return value;
}
export function resumeFileTask(path: string) { return request<unknown>(internalPath(path), { method: "POST", body: JSON.stringify({}) }); }
export function isWorkFileContent(path: string) {
  return /^\/catalog\/admin\/editions\/[0-9a-f-]+\/files\/[0-9a-f-]+\/content\/(?:\?download=(?:1|true|original))?$/i.test(internalPath(path));
}
export async function readWorkFileHead(path: string, signal?: AbortSignal) {
  if (!isWorkFileContent(path)) throw new Error("文件地址不属于当前版本的受保护原件。");
  const controller = new AbortController(), unsubscribe = subscribeToSessionChanges(() => controller.abort());
  const combined = AbortSignal.any([controller.signal, AbortSignal.timeout(30000), ...(signal ? [signal] : [])]);
  try {
    const response = await apiStreamRequest(internalPath(path), { method: "HEAD", cache: "no-store", signal: combined }, getServerSessionCredential(), false);
    if (!response.ok) throw new ApiRequestError(`文件暂不可读取（${response.status}），请重新核对权限或文件状态。`, response.status);
    const contentType = response.headers.get("Content-Type") || "", size = Number(response.headers.get("Content-Length"));
    if (/json|text\/html/i.test(contentType) || !Number.isFinite(size) || size <= 0) throw new Error("服务器未返回可读取的原件，未开始预览或下载。");
    combined.throwIfAborted();
    return { url: apiEndpoint(internalPath(path)), contentType, size, sha256: (response.headers.get("ETag") || "").replace(/^W\//, "").replace(/^"|"$/g, "") };
  } finally { unsubscribe(); }
}
export async function readWorkFileBlob(path: string, signal?: AbortSignal) {
  if (!/^\/catalog\/admin\/editions\/[0-9a-f-]+\/files\/impact\.csv(?:\?asset=[0-9a-f-]+)?$/i.test(internalPath(path))) throw new Error("导出地址不属于当前版本的引用影响。");
  const controller = new AbortController(), unsubscribe = subscribeToSessionChanges(() => controller.abort());
  const combined = AbortSignal.any([controller.signal, AbortSignal.timeout(60000), ...(signal ? [signal] : [])]);
  try {
    const response = await apiStreamRequest(internalPath(path), { method: "GET", cache: "no-store", signal: combined }, getServerSessionCredential(), false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload?.error?.detail?.detail ?? payload?.error?.detail ?? payload?.detail ?? payload?.message;
      throw new ApiRequestError(typeof detail === "string" ? detail : `文件读取失败（${response.status}），未下载错误响应。`, response.status);
    }
    if (!response.headers.get("Content-Type")?.includes("text/csv")) throw new Error("服务器未返回引用影响文件，未下载错误内容。");
    // Only the small CSV export uses a Blob; original files use native/Range requests.
    const limit = 16 * 1024 * 1024;
    if (Number(response.headers.get("Content-Length")) > limit || !response.body) throw new Error("导出内容超过单次读取上限，请缩小范围。");
    const reader = response.body.getReader(), chunks: Uint8Array<ArrayBuffer>[] = []; let size = 0;
    try {
      for (;;) {
        const result = await reader.read();
        if (result.done) break;
        size += result.value.byteLength;
        if (size > limit) throw new Error("导出内容超过单次读取上限，请缩小范围。");
        chunks.push(new Uint8Array(result.value));
      }
    } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    const blob = new Blob(chunks, { type: response.headers.get("Content-Type") || "text/csv" });
    combined.throwIfAborted();
    if (!blob.size) throw new ApiRequestError("服务器返回了空文件，请重新核对文件状态。", 0);
    return blob;
  } finally { unsubscribe(); }
}
export function workFileBytes(value: number) { return value >= 1024 * 1024 ? `${(value / (1024 * 1024)).toFixed(1)} MB` : value >= 1024 ? `${(value / 1024).toFixed(1)} KB` : `${value} B`; }
export const workFileDate = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" }) : "尚未记录";
