"use client";

import Link from "next/link";
import { AlertCircle, ArrowRight, CheckCircle2, FileText, LoaderCircle, RefreshCw, Upload, X } from "lucide-react";
import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, apiUpload, getStoredAccessToken } from "@/lib/api";
import {
  formatUploadBytes,
  formatUploadEta,
  formatUploadRate,
  UploadRateMeter,
} from "@/lib/upload-metrics";

type UploadResponse = {
  accepted: string[];
  rejected: { filename: string; reason: string }[];
  batch: { id: string; status: string };
};

type QueuedFile = {
  file: File;
  token: string;
  status: "waiting" | "uploading" | "accepted" | "failed";
  message: string;
  progress: number;
  uploadedBytes: number;
  speedBps: number;
  averageSpeedBps: number;
  etaSeconds: number | null;
  resumeBatchId?: string;
  chunkSize: number;
};

type MetadataImportState = {
  filename: string;
  status: "importing" | "imported" | "failed";
  message: string;
};

type MetadataImportResponse = {
  format: string;
  filename: string;
  reused_source: boolean;
  stats: {
    created?: number;
    updated?: number;
    superseded?: number;
  };
};

type MetadataPairing = {
  status: "matched" | "missing" | "ambiguous";
  file?: File;
  message: string;
};

type ItemUploadResponse = {
  accepted: boolean;
  item: {
    id: string;
    status: string;
    error_message: string;
  };
};

type ChunkUploadResponse = {
  accepted: boolean;
  complete: boolean;
  received_chunks?: number;
  total_chunks?: number;
  received_indices?: number[];
  source_filename?: string;
  total_size?: number;
  chunk_size?: number;
  max_chunk_size?: number;
  item?: ItemUploadResponse["item"];
};

type IngestionCandidate = {
  field_name: string;
  source: string;
  confidence: number;
};

type IngestionItem = {
  id: string;
  source_filename: string;
  status: string;
  stage_progress: number;
  error_code: string;
  error_message: string;
  dispatch_status: string;
  dispatch_task_id: string;
  dispatch_attempts: number;
  recognized_metadata: Record<string, unknown>;
  preflight_summary: {
    page_count?: number;
    text_profile?: "born_digital" | "scanned" | "mixed";
    detected_ocr_pages?: number;
    scheduled_ocr_pages?: number;
    ocr_strategy?: OcrStrategy;
    exact_duplicate?: boolean;
  };
  edition: string | null;
  metadata_candidates: IngestionCandidate[];
  review_data: null | {
    title: string;
    document_type: string;
    language: string;
    authors: string[];
    publication_year: number | null;
    publisher: string;
    publication_place: string;
    publication_state: string;
    review_progress: number;
    ocr_status: string;
    semantic_index_status: string;
  };
  can_manage_publication: boolean;
  is_stalled: boolean;
  suggested_action: string;
  updated_at: string;
};

type AccessPolicy = "public" | "registered" | "restricted";
type OcrStrategy = "auto" | "force" | "skip";
type DuplicatePolicy = "review" | "block_exact" | "allow";

const MEBIBYTE = 1024 * 1024;
const LEGACY_CHUNK_SIZE = MEBIBYTE;
// Keep every public request below the observed reverse-proxy request window
// on slow uplinks.  The API still accepts larger chunks for future clients.
const CHUNK_SIZE = 2 * MEBIBYTE;
const PUBLIC_CHUNK_THRESHOLD = 4 * MEBIBYTE;
const RESUME_STORAGE_KEY = "library_chunk_upload_sessions_v1";
const METADATA_FILE_EXTENSIONS = new Set(["ris", "bib", "bibtex", "json", "yaml", "yml"]);
const INGESTION_TERMINAL_STATUSES = new Set([
  "needs_review",
  "ready",
  "failed",
  "published",
  "withdrawn",
  "deleted",
]);

const ingestionStatusLabels: Record<string, string> = {
  received: "已接收，等待识别",
  validating: "正在校验 PDF",
  deduplicating: "正在核对重复馆藏",
  metadata: "正在识别书目信息",
  extracting: "正在提取逐页文本",
  ocr: "正在判断或执行 OCR",
  linking: "正在生成分类候选",
  indexing: "正在建立检索数据",
  preparing_public_asset: "正在准备阅读文件",
  syncing_cloud: "正在同步公开副本",
  needs_review: "候选已就绪，等待复核",
  ready: "复核已保存，可进入发布台",
  failed: "处理失败，需要检查",
  published: "已经发布",
  withdrawn: "已经下架",
};

const candidateFieldLabels: Record<string, string> = {
  title: "题名",
  authors: "作者",
  publisher: "出版者",
  publication_place: "出版地",
  disciplines: "学科",
  subdisciplines: "子学科",
  theory_schools: "理论流派",
  topics: "主题",
};

const textProfileLabels: Record<string, string> = {
  born_digital: "已有可用文字层",
  scanned: "扫描型 PDF",
  mixed: "文字与扫描混合",
};

function displayMetadataValue(value: unknown) {
  if (Array.isArray(value)) return value.map(String).join("、");
  if (value === null || value === undefined || value === "") return "待识别";
  return String(value);
}

type ResumeSession = {
  batchId: string;
  token: string;
  filename: string;
  size: number;
  lastModified: number;
  updatedAt: number;
  chunkSize?: number;
};

function fileFingerprint(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function loadResumeSessions(): Record<string, ResumeSession> {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(RESUME_STORAGE_KEY) || "{}");
    if (!parsed || typeof parsed !== "object") return {};
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
    return Object.fromEntries(
      Object.entries(parsed as Record<string, ResumeSession>).filter(
        ([, session]) => session && Number(session.updatedAt) >= cutoff,
      ),
    );
  } catch {
    return {};
  }
}

function saveResumeSession(file: File, session: ResumeSession | null) {
  if (typeof window === "undefined") return;
  const sessions = loadResumeSessions();
  const fingerprint = fileFingerprint(file);
  if (session) sessions[fingerprint] = session;
  else delete sessions[fingerprint];
  window.localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(sessions));
}

function uploadToken() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isPrivateNetworkHost(hostname: string) {
  return hostname === "localhost"
    || hostname === "127.0.0.1"
    || hostname === "::1"
    || hostname.startsWith("192.168.")
    || hostname.startsWith("10.")
    || /^172\.(1[6-9]|2\d|3[01])\./.test(hostname);
}

function chunkByteLength(totalBytes: number, chunkSize: number, chunkIndex: number) {
  const start = chunkIndex * chunkSize;
  return Math.max(0, Math.min(chunkSize, totalBytes - start));
}

function normalizedFileStem(filename: string, kind: "pdf" | "metadata") {
  let value = filename.normalize("NFKC").trim().toLocaleLowerCase();
  value = value.replace(kind === "pdf" ? /\.pdf$/i : /\.(ris|bib|bibtex|json|ya?ml)$/i, "");
  if (kind === "metadata") {
    value = value.replace(/\.(metadata|sidecar|csl|zotero)$/i, "");
  }
  return value.trim();
}

function isMetadataFile(file: File) {
  const extension = file.name.split(".").pop()?.toLocaleLowerCase() || "";
  return METADATA_FILE_EXTENSIONS.has(extension);
}

function metadataIdentity(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function buildMetadataPairings(pdfFiles: QueuedFile[], metadataFiles: File[]) {
  const pdfCounts = new Map<string, number>();
  const metadataByStem = new Map<string, File[]>();
  for (const item of pdfFiles) {
    const stem = normalizedFileStem(item.file.name, "pdf");
    pdfCounts.set(stem, (pdfCounts.get(stem) || 0) + 1);
  }
  for (const file of metadataFiles) {
    const stem = normalizedFileStem(file.name, "metadata");
    metadataByStem.set(stem, [...(metadataByStem.get(stem) || []), file]);
  }
  return Object.fromEntries(pdfFiles.map((item) => {
    const stem = normalizedFileStem(item.file.name, "pdf");
    const candidates = metadataByStem.get(stem) || [];
    let pairing: MetadataPairing;
    if (!candidates.length) {
      pairing = { status: "missing", message: "未提供配套元数据，将使用 PDF 识别和外部候选" };
    } else if (candidates.length > 1 || (pdfCounts.get(stem) || 0) > 1) {
      pairing = {
        status: "ambiguous",
        message: "同名 PDF 或元数据文件不唯一，请改为一一对应的文件名",
      };
    } else {
      pairing = {
        status: "matched",
        file: candidates[0],
        message: `将导入 ${candidates[0].name}`,
      };
    }
    return [item.token, pairing];
  })) as Record<string, MetadataPairing>;
}

export function AdminUpload() {
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<QueuedFile[]>([]);
  const [metadataFiles, setMetadataFiles] = useState<File[]>([]);
  const [metadataImportStates, setMetadataImportStates] = useState<Record<string, MetadataImportState>>({});
  const [batchLabel, setBatchLabel] = useState("");
  const [accessPolicy, setAccessPolicy] = useState<AccessPolicy>("public");
  const [ocrStrategy, setOcrStrategy] = useState<OcrStrategy>("auto");
  const [duplicatePolicy, setDuplicatePolicy] = useState<DuplicatePolicy>("review");
  const [externalEnrichmentEnabled, setExternalEnrichmentEnabled] = useState(true);
  const [aiSuggestionsEnabled, setAiSuggestionsEnabled] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState("");
  const [ingestionItems, setIngestionItems] = useState<IngestionItem[]>([]);
  const [ingestionError, setIngestionError] = useState("");
  const [retryingItem, setRetryingItem] = useState("");
  const metadataPairings = useMemo(
    () => buildMetadataPairings(files, metadataFiles),
    [files, metadataFiles],
  );
  const pairedMetadataIdentities = useMemo(
    () => new Set(
      Object.values(metadataPairings)
        .filter((pairing) => pairing.status === "matched" && pairing.file)
        .map((pairing) => metadataIdentity(pairing.file as File)),
    ),
    [metadataPairings],
  );

  useEffect(() => {
    const accepted = result?.accepted ?? [];
    if (!accepted.length) return;
    const token = getStoredAccessToken();
    if (!token) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function refresh() {
      try {
        const snapshots = await Promise.all(
          accepted.map((itemId) => apiRequest<IngestionItem>(
            `/ingestion/items/${itemId}/`,
            {},
            token,
          )),
        );
        if (!active) return;
        setIngestionItems(snapshots);
        setIngestionError("");
        if (snapshots.some((item) => !INGESTION_TERMINAL_STATUSES.has(item.status))) {
          timer = setTimeout(refresh, 2500);
        }
      } catch (reason) {
        if (!active) return;
        setIngestionError(reason instanceof Error ? reason.message : "暂时无法刷新识别状态。");
        timer = setTimeout(refresh, 5000);
      }
    }

    void refresh();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [result]);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list);
    const incomingMetadata = incoming.filter(isMetadataFile);
    if (incomingMetadata.length) {
      setMetadataFiles((current) => {
        const identities = new Set(current.map(metadataIdentity));
        return current.concat(
          incomingMetadata.filter((file) => !identities.has(metadataIdentity(file))),
        ).slice(0, 100);
      });
    }
    const resumeSessions = loadResumeSessions();
    setFiles((current) => {
      const identities = new Set(current.map((item) => `${item.file.name}:${item.file.size}`));
      return current.concat(
        incoming.filter(
          (file) =>
            file.name.toLocaleLowerCase().endsWith(".pdf") &&
            !identities.has(`${file.name}:${file.size}`),
        ).map((file) => {
          const resume = resumeSessions[fileFingerprint(file)];
          return {
            file,
            token: resume?.token || uploadToken(),
            status: "waiting" as const,
            message: resume ? "发现可恢复的公网上传记录" : "",
            progress: 0,
            uploadedBytes: 0,
            speedBps: 0,
            averageSpeedBps: 0,
            etaSeconds: null,
            resumeBatchId: resume?.batchId,
            chunkSize: resume?.batchId
              ? (resume.chunkSize || LEGACY_CHUNK_SIZE)
              : CHUNK_SIZE,
          };
        }),
      ).slice(0, 100);
    });
  }

  function updateFile(token: string, patch: Partial<QueuedFile>) {
    setFiles((current) => current.map(
      (item) => item.token === token ? { ...item, ...patch } : item,
    ));
  }

  async function retryIngestionItem(itemId: string) {
    const token = getStoredAccessToken();
    if (!token) return;
    setRetryingItem(itemId);
    setIngestionError("");
    try {
      await apiRequest(
        `/ingestion/items/${itemId}/retry/`,
        { method: "POST" },
        token,
      );
      const snapshot = await apiRequest<IngestionItem>(
        `/ingestion/items/${itemId}/`,
        {},
        token,
      );
      setIngestionItems((current) => current.map((item) => item.id === itemId ? snapshot : item));
    } catch (reason) {
      setIngestionError(reason instanceof Error ? reason.message : "重新处理失败。");
    } finally {
      setRetryingItem("");
    }
  }

  async function upload() {
    const token = getStoredAccessToken();
    if (!token) {
      setError("请先用管理员账户登录。");
      return;
    }
    const waiting = files.filter((item) => item.status === "waiting");
    if (!waiting.length) return;
    setPending(true);
    setError("");
    setResult(null);
    setIngestionItems([]);
    setIngestionError("");
    try {
      const shouldUseChunkUpload = (item: QueuedFile) => item.file.size >= PUBLIC_CHUNK_THRESHOLD
        && !isPrivateNetworkHost(window.location.hostname);
      const freshItems = waiting.filter((item) => !shouldUseChunkUpload(item) || !item.resumeBatchId);
      const freshBatch = freshItems.length
        ? await apiRequest<{ id: string; status: string }>(
          "/ingestion/batches/create/",
          {
            method: "POST",
            body: JSON.stringify({
              expected_count: freshItems.length,
              label: batchLabel.trim(),
              access_policy: accessPolicy,
              ocr_strategy: ocrStrategy,
              duplicate_policy: duplicatePolicy,
              external_enrichment_enabled: externalEnrichmentEnabled,
              ai_suggestions_enabled: aiSuggestionsEnabled,
            }),
          },
          token,
        )
        : null;
      const displayBatch = freshBatch || {
        id: waiting[0].resumeBatchId as string,
        status: "resuming",
      };
      const accepted: string[] = [];
      const rejected: { filename: string; reason: string }[] = [];
      let cursor = 0;
      const uploadMetadataPairings = buildMetadataPairings(files, metadataFiles);

      async function importMatchedMetadata(itemId: string, item: QueuedFile) {
        const pairing = uploadMetadataPairings[item.token];
        if (!pairing || pairing.status !== "matched" || !pairing.file) {
          return pairing?.status === "ambiguous"
            ? "上传完成；配套元数据文件名有冲突，尚未导入"
            : "上传完成，已进入处理队列";
        }
        setMetadataImportStates((current) => ({
          ...current,
          [item.token]: {
            filename: pairing.file?.name || "",
            status: "importing",
            message: "正在导入配套元数据",
          },
        }));
        const body = new FormData();
        body.append("file", pairing.file);
        try {
          const response = await apiUpload<MetadataImportResponse>(
            `/ingestion/items/${itemId}/metadata-import/`,
            body,
            token,
          );
          const created = response.stats.created || 0;
          const message = response.reused_source
            ? `配套元数据已核对，复用 ${response.format} 来源记录`
            : `配套元数据已生成 ${created} 个待审候选`;
          setMetadataImportStates((current) => ({
            ...current,
            [item.token]: {
              filename: pairing.file?.name || "",
              status: "imported",
              message,
            },
          }));
          return `上传完成；${message}`;
        } catch (reason) {
          const message = reason instanceof Error ? reason.message : "配套元数据导入失败";
          setMetadataImportStates((current) => ({
            ...current,
            [item.token]: {
              filename: pairing.file?.name || "",
              status: "failed",
              message,
            },
          }));
          return `PDF 已上传；配套元数据未导入：${message}`;
        }
      }

      async function sendChunks(item: QueuedFile, targetBatchId: string) {
        let chunkSize = item.chunkSize;
        let totalChunks = Math.ceil(item.file.size / chunkSize);
        let finalResponse: ChunkUploadResponse | null = null;
        const saved: ChunkUploadResponse = await apiRequest<ChunkUploadResponse>(
          `/ingestion/batches/${targetBatchId}/chunks/?client_token=${encodeURIComponent(item.token)}`,
          {},
          token,
        ).catch((): ChunkUploadResponse => ({
          accepted: false,
          complete: false,
          received_indices: [],
        }));
        if (saved.complete && saved.item) {
          return {
            accepted: saved.item.status !== "failed",
            item: saved.item,
          } satisfies ItemUploadResponse;
        }
        if (saved.chunk_size && saved.chunk_size !== chunkSize) {
          chunkSize = saved.chunk_size;
          totalChunks = Math.ceil(item.file.size / chunkSize);
          updateFile(item.token, { chunkSize });
        }
        if (saved.max_chunk_size && chunkSize > saved.max_chunk_size) {
          throw new Error("服务器允许的上传分段小于当前恢复记录，请保留页面并联系管理员升级 API。");
        }
        if (
          (saved.source_filename && saved.source_filename !== item.file.name)
          || (saved.total_size && saved.total_size !== item.file.size)
          || (saved.total_chunks && saved.total_chunks !== totalChunks)
        ) {
          throw new Error("服务器上的恢复记录属于另一个 PDF，请移除文件后重新选择。");
        }
        const received = new Set(
          (saved.received_indices || []).filter((index) => index >= 0 && index < totalChunks),
        );
        if (received.size === totalChunks && totalChunks > 0) {
          // Re-send the final idempotent chunk when the browser lost the
          // assembly response after every chunk reached the server.
          received.delete(totalChunks - 1);
        }
        let completedBytes = Array.from(received).reduce(
          (total, index) => total + chunkByteLength(item.file.size, chunkSize, index),
          0,
        );
        const resumedBytes = Math.min(item.file.size, completedBytes);
        const meter = new UploadRateMeter(item.file.size, resumedBytes, performance.now());
        if (received.size) {
          const resumedProgress = Math.min(99, Math.round((resumedBytes / item.file.size) * 100));
          updateFile(item.token, {
            uploadedBytes: resumedBytes,
            progress: resumedProgress,
            message: `已恢复 ${received.size}/${totalChunks} 个分段`,
          });
        }
        for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
          if (received.has(chunkIndex)) continue;
          const start = chunkIndex * chunkSize;
          const end = Math.min(item.file.size, start + chunkSize);
          const chunk = item.file.slice(start, end, "application/octet-stream");
          let response: ChunkUploadResponse | null = null;
          let lastError: unknown = null;
          for (let chunkAttempt = 0; chunkAttempt < 3; chunkAttempt += 1) {
            let previousLoaded = 0;
            const body = new FormData();
            body.append("chunk", chunk, `${chunkIndex}.part`);
            body.append("client_token", item.token);
            body.append("source_filename", item.file.name);
            body.append("chunk_index", String(chunkIndex));
            body.append("total_chunks", String(totalChunks));
            body.append("total_size", String(item.file.size));
            body.append("chunk_size", String(chunkSize));
            try {
              response = await apiUpload<ChunkUploadResponse>(
                `/ingestion/batches/${targetBatchId}/chunks/`,
                body,
                token,
                ({ loaded, total }) => {
                  const now = performance.now();
                  const networkBytes = Math.max(0, loaded - previousLoaded);
                  previousLoaded = Math.max(previousLoaded, loaded);
                  const metrics = meter.sample(completedBytes + loaded, networkBytes, now);
                  const progress = Math.min(99, Math.round((metrics.logicalBytes / item.file.size) * 100));
                  const finalBodySent = chunkIndex === totalChunks - 1 && total > 0 && loaded >= total;
                  const retryLabel = chunkAttempt > 0 ? `，第 ${chunkAttempt + 1} 次尝试` : "";
                  updateFile(item.token, {
                    uploadedBytes: metrics.logicalBytes,
                    progress,
                    speedBps: metrics.currentSpeedBps,
                    averageSpeedBps: metrics.averageSpeedBps,
                    etaSeconds: metrics.etaSeconds,
                    message: finalBodySent
                      ? "文件已上传，服务器正在合并和校验"
                      : `正在上传分段 ${chunkIndex + 1}/${totalChunks}${retryLabel}`,
                  });
                },
              );
              break;
            } catch (reason) {
              lastError = reason;
            }
          }
          if (!response) throw lastError instanceof Error ? lastError : new Error("文件分段上传失败。");
          completedBytes = Math.min(item.file.size, completedBytes + chunk.size);
          const metrics = meter.sample(completedBytes, 0, performance.now());
          updateFile(item.token, {
            uploadedBytes: metrics.logicalBytes,
            progress: Math.min(99, Math.round((metrics.logicalBytes / item.file.size) * 100)),
            speedBps: metrics.currentSpeedBps,
            averageSpeedBps: metrics.averageSpeedBps,
            etaSeconds: metrics.etaSeconds,
            message: response.complete
              ? "服务器已完成合并和校验"
              : `已完成分段 ${chunkIndex + 1}/${totalChunks}`,
          });
          finalResponse = response;
          saveResumeSession(item.file, {
            batchId: targetBatchId,
            token: item.token,
            filename: item.file.name,
            size: item.file.size,
            lastModified: item.file.lastModified,
            updatedAt: Date.now(),
            chunkSize,
          });
        }
        if (!finalResponse?.complete || !finalResponse.item) {
          throw new Error("文件分段已经发送，但服务器尚未完成合并，请重试。");
        }
        return {
          accepted: finalResponse.accepted,
          item: finalResponse.item,
        } satisfies ItemUploadResponse;
      }

      async function sendFile(item: QueuedFile) {
        updateFile(item.token, {
          status: "uploading",
          message: "正在连接",
          progress: 0,
          uploadedBytes: 0,
          speedBps: 0,
          averageSpeedBps: 0,
          etaSeconds: null,
        });
        let lastReason = "上传中断";
        for (let attempt = 0; attempt < 3; attempt += 1) {
          const body = new FormData();
          body.append("file", item.file);
          body.append("client_token", item.token);
          const startedAt = performance.now();
          const meter = new UploadRateMeter(item.file.size, 0, startedAt);
          let previousLoaded = 0;
          try {
            const useChunks = shouldUseChunkUpload(item);
            const targetBatchId = useChunks && item.resumeBatchId
              ? item.resumeBatchId
              : freshBatch?.id;
            if (!targetBatchId) throw new Error("没有可用的上传批次，请重新选择文件。");
            if (useChunks) {
              saveResumeSession(item.file, {
                batchId: targetBatchId,
                token: item.token,
                filename: item.file.name,
                size: item.file.size,
                lastModified: item.file.lastModified,
                updatedAt: Date.now(),
                chunkSize: item.chunkSize,
              });
            }
            const response = useChunks
              ? await sendChunks(item, targetBatchId)
              : await apiUpload<ItemUploadResponse>(
                `/ingestion/batches/${targetBatchId}/items/`,
                body,
                token,
                ({ loaded, total }) => {
                  const now = performance.now();
                  const networkBytes = Math.max(0, loaded - previousLoaded);
                  previousLoaded = Math.max(previousLoaded, loaded);
                  const logicalBytes = Math.min(item.file.size, loaded);
                  const metrics = meter.sample(logicalBytes, networkBytes, now);
                  const progress = total ? Math.min(99, Math.round((metrics.logicalBytes / item.file.size) * 100)) : 0;
                  updateFile(item.token, {
                    uploadedBytes: metrics.logicalBytes,
                    progress,
                    speedBps: metrics.currentSpeedBps,
                    averageSpeedBps: metrics.averageSpeedBps,
                    etaSeconds: metrics.etaSeconds,
                    message: total > 0 && loaded >= total
                      ? "文件已上传，服务器正在校验"
                      : attempt > 0
                        ? `正在重试完整上传，第 ${attempt + 1} 次尝试`
                        : "正在上传",
                  });
                },
              );
            if (response.accepted) {
              saveResumeSession(item.file, null);
              accepted.push(response.item.id);
              const completionMessage = await importMatchedMetadata(response.item.id, item);
              updateFile(item.token, {
                status: "accepted",
                message: completionMessage,
                progress: 100,
                uploadedBytes: item.file.size,
                etaSeconds: 0,
              });
            } else {
              const reason = response.item.error_message || "文件未通过校验";
              rejected.push({ filename: item.file.name, reason });
              updateFile(item.token, { status: "failed", message: reason });
            }
            return;
          } catch (reason) {
            lastReason = reason instanceof Error ? reason.message : "上传中断";
          }
        }

        try {
          const failureBatchId = shouldUseChunkUpload(item) && item.resumeBatchId
            ? item.resumeBatchId
            : freshBatch?.id;
          if (!failureBatchId) throw new Error(lastReason);
          const recovered = await apiRequest<{
            item: { id: string; status: string; error_message: string };
          }>(
            `/ingestion/batches/${failureBatchId}/failures/`,
            {
              method: "POST",
              body: JSON.stringify({
                client_token: item.token,
                source_filename: item.file.name,
                reason: lastReason,
              }),
            },
            token,
          );
          if (recovered.item.status !== "failed") {
            accepted.push(recovered.item.id);
            updateFile(item.token, { status: "accepted", message: "服务器已接收" });
            return;
          }
          lastReason = recovered.item.error_message || lastReason;
        } catch {
          // The local row still records the failure even if the final report is unreachable.
        }
        rejected.push({ filename: item.file.name, reason: lastReason });
        updateFile(item.token, { status: "failed", message: lastReason });
      }

      async function worker() {
        while (cursor < waiting.length) {
          const item = waiting[cursor];
          cursor += 1;
          await sendFile(item);
        }
      }

      await Promise.all(
        Array.from(
          { length: Math.min(2, waiting.length) },
          () => worker(),
        ),
      );
      setResult({ accepted, rejected, batch: displayBatch });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败。");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="admin-page upload-page">
      <header className="admin-page-title"><div><p>入库管理</p><h1>批量上传 PDF</h1><span>每个 PDF 独立校验、识别、重试和发布。</span></div></header>
      <section className="upload-policy-panel admin-panel" aria-labelledby="upload-policy-title">
        <header>
          <div>
            <h2 id="upload-policy-title">本批处理方式</h2>
            <p>这些选项只作用于本次新建批次，之后仍可在审校和发布阶段调整馆藏内容。</p>
          </div>
        </header>
        <div className="upload-policy-grid">
          <label className="upload-policy-field upload-policy-label">
            <span>批次标签</span>
            <input
              type="text"
              value={batchLabel}
              maxLength={240}
              disabled={pending}
              placeholder="例如 2026 秋季中文社会理论"
              onChange={(event) => setBatchLabel(event.target.value)}
            />
            <small>可选。用于稍后查找和筛选这一批文件。</small>
          </label>
          <label className="upload-policy-field">
            <span>访问权限</span>
            <select
              value={accessPolicy}
              disabled={pending}
              onChange={(event) => setAccessPolicy(event.target.value as AccessPolicy)}
            >
              <option value="public">公开访问</option>
              <option value="registered">登录读者</option>
              <option value="restricted">受限访问</option>
            </select>
            <small>仅设定文件的初始访问范围，不会跳过管理员发布确认。</small>
          </label>
          <label className="upload-policy-field">
            <span>OCR 策略</span>
            <select
              value={ocrStrategy}
              disabled={pending}
              onChange={(event) => setOcrStrategy(event.target.value as OcrStrategy)}
            >
              <option value="auto">自动检测（推荐）</option>
              <option value="force">强制 OCR</option>
              <option value="skip">跳过 OCR</option>
            </select>
            <small>自动检测会保留可靠原生文字，仅将扫描页排入 OCR，节省 NAS 资源。</small>
          </label>
          <label className="upload-policy-field">
            <span>重复检测</span>
            <select
              value={duplicatePolicy}
              disabled={pending}
              onChange={(event) => setDuplicatePolicy(event.target.value as DuplicatePolicy)}
            >
              <option value="review">发现重复时人工确认</option>
              <option value="block_exact">阻止完全重复文件</option>
              <option value="allow">复用已有文件并继续</option>
            </select>
            <small>推荐人工确认，以区分完全重复文件和同一作品的不同版本。</small>
          </label>
          <label className="upload-policy-toggle">
            <input
              type="checkbox"
              checked={externalEnrichmentEnabled}
              disabled={pending}
              onChange={(event) => setExternalEnrichmentEnabled(event.target.checked)}
            />
            <span><strong>外部元数据补充</strong><small>查询已配置的书目来源并生成带出处的候选。服务不可用时仍可继续本地识别。</small></span>
          </label>
          <label className="upload-policy-toggle">
            <input
              type="checkbox"
              checked={aiSuggestionsEnabled}
              disabled={pending}
              onChange={(event) => setAiSuggestionsEnabled(event.target.checked)}
            />
            <span><strong>AI 候选建议</strong><small>仅在模型服务已配置时产生候选。候选不会自动采用，仍需管理员复核。</small></span>
          </label>
        </div>
        {files.some((item) => item.resumeBatchId) ? (
          <p className="upload-resume-policy-note" role="status">
            已发现可恢复的公网上传记录。恢复文件继续使用原批次策略；上面的选项只会用于本次新建的批次，不会改写旧记录。
          </p>
        ) : null}
      </section>
      <section
        className="upload-dropzone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event: DragEvent) => {
          event.preventDefault();
          addFiles(event.dataTransfer.files);
        }}
      >
        <Upload size={31} />
        <h2>拖入 PDF 和配套元数据</h2>
        <p>支持 PDF，以及同名的 RIS、BibTeX、CSL-JSON、sidecar JSON 或 YAML。配套文件只生成待审候选，不会直接覆盖馆藏。</p>
        <button className="button secondary" type="button" onClick={() => input.current?.click()}>选择文件</button>
        <input ref={input} type="file" accept="application/pdf,.pdf,.ris,.bib,.bibtex,.json,.yaml,.yml" multiple hidden onChange={(event: ChangeEvent<HTMLInputElement>) => addFiles(event.target.files)} />
      </section>

      <section className="upload-queue admin-panel">
        <header><h2>待上传文件</h2><span>{files.length} 个 PDF · {metadataFiles.length} 个元数据文件</span></header>
        {metadataFiles.length ? (
          <div className="upload-metadata-pairing" aria-live="polite">
            <div>
              <strong>配套元数据</strong>
              <span>文件名需与 PDF 一致。允许增加 .sidecar、.metadata、.csl 或 .zotero 后缀。</span>
            </div>
            <ul>
              {metadataFiles.map((file) => {
                const matched = pairedMetadataIdentities.has(metadataIdentity(file));
                return (
                  <li className={matched ? "matched" : "unmatched"} key={metadataIdentity(file)}>
                    <span>{file.name}</span>
                    <b>{matched ? "已配对" : "未配对或存在同名冲突"}</b>
                    <button
                      type="button"
                      disabled={pending}
                      aria-label={`移除元数据文件 ${file.name}`}
                      onClick={() => setMetadataFiles((current) => current.filter((value) => metadataIdentity(value) !== metadataIdentity(file)))}
                    >
                      <X size={14} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
        {files.length ? files.map((item, index) => (
          <div key={item.token}>
            <FileText size={18} />
            <p>
              <strong>{item.file.name}</strong>
              <span>{(item.file.size / 1024 / 1024).toFixed(2)} MB</span>
              <span className={`metadata-pair-status ${metadataPairings[item.token]?.status || "missing"}`}>
                {metadataImportStates[item.token]?.message || metadataPairings[item.token]?.message}
              </span>
            </p>
            <div className="upload-file-status">
              <small aria-live="polite">{item.message || "等待上传"}</small>
              {item.status === "uploading" || item.status === "accepted" ? (
                <span>
                  {formatUploadBytes(item.uploadedBytes)} / {formatUploadBytes(item.file.size)}
                  {item.status === "uploading" ? ` · 当前 ${formatUploadRate(item.speedBps)} · 平均 ${formatUploadRate(item.averageSpeedBps)} · 剩余 ${formatUploadEta(item.etaSeconds)}` : ` · 平均 ${formatUploadRate(item.averageSpeedBps)}`}
                </span>
              ) : null}
            </div>
            {item.status === "uploading" || item.status === "accepted" ? (
              <span
                className="upload-file-progress"
                role="progressbar"
                aria-label={`${item.file.name} 上传进度`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={item.progress}
              >
                <i style={{ width: `${item.progress}%` }} />
              </span>
            ) : null}
            <button type="button" aria-label={`移除待上传文件 ${item.file.name}`} disabled={pending} onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X size={16} /></button>
          </div>
        )) : <p className="empty-row">尚未选择文件。</p>}
        <footer>
          <p className="admin-help">上传只建立馆藏和后台处理任务。公开发布必须由管理员在馆藏详情中确认。</p>
          <button className="button" type="button" disabled={!files.some((item) => item.status === "waiting") || pending} onClick={upload}>
            {pending ? <LoaderCircle className="spin" size={16} /> : <Upload size={16} />}
            开始上传
          </button>
        </footer>
      </section>

      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      {result ? (
        <section className="upload-result admin-panel">
          <header><h2><CheckCircle2 size={18} />批次已接收</h2><span>{result.batch.id}</span></header>
          <p>{result.accepted.length} 个文件进入入库工作台，{result.rejected.length} 个文件被拒绝。识别、复核和发布彼此独立，任一失败不会影响其他文件。</p>
          {result.rejected.map((item) => <p key={item.filename}><strong>{item.filename}</strong><span>{item.reason}</span></p>)}
          {ingestionError ? <p className="form-message error" role="alert">{ingestionError}</p> : null}
          <div className="ingestion-workbench" aria-live="polite">
            {result.accepted.length && !ingestionItems.length ? <p className="ingestion-loading"><LoaderCircle className="spin" size={16} />正在读取自动识别状态……</p> : null}
            {ingestionItems.map((item) => {
              const metadata = item.review_data ?? item.recognized_metadata;
              const title = item.review_data?.title || displayMetadataValue(item.recognized_metadata.title);
              const candidateCounts = item.metadata_candidates.reduce<Record<string, number>>((counts, candidate) => {
                counts[candidate.field_name] = (counts[candidate.field_name] || 0) + 1;
                return counts;
              }, {});
              const canRetry = item.status === "failed" || item.is_stalled;
              return (
                <article className={`ingestion-card status-${item.status}`} key={item.id}>
                  <header>
                    <div><FileText size={18} /><span><strong>{title}</strong><small>{item.source_filename}</small></span></div>
                    <b>{ingestionStatusLabels[item.status] ?? item.status}</b>
                  </header>
                  <div className="ingestion-card-progress">
                    <span><i style={{ width: `${Math.max(2, item.stage_progress)}%` }} /></span>
                    <b>{item.stage_progress}%</b>
                  </div>
                  <dl>
                    <div><dt>文献类型</dt><dd>{displayMetadataValue(item.review_data?.document_type ?? metadata.document_type)}</dd></div>
                    <div><dt>作者</dt><dd>{displayMetadataValue(item.review_data?.authors ?? metadata.authors)}</dd></div>
                    <div><dt>出版信息</dt><dd>{[
                      item.review_data?.publication_place ?? metadata.publication_place,
                      item.review_data?.publisher ?? metadata.publisher,
                      item.review_data?.publication_year ?? metadata.publication_year,
                    ].filter(Boolean).map(String).join(" · ") || "待识别"}</dd></div>
                    <div><dt>后台派发</dt><dd>{item.dispatch_status}{item.dispatch_attempts > 1 ? ` · ${item.dispatch_attempts} 次记录` : ""}</dd></div>
                    <div><dt>文件预检</dt><dd>{[
                      item.preflight_summary?.page_count ? `${item.preflight_summary.page_count} 页` : "",
                      textProfileLabels[item.preflight_summary?.text_profile || ""] || "",
                      item.preflight_summary?.exact_duplicate ? "发现完全重复文件" : "",
                    ].filter(Boolean).join(" · ") || "等待解析"}</dd></div>
                    <div><dt>OCR 安排</dt><dd>{item.preflight_summary?.scheduled_ocr_pages !== undefined
                      ? `${item.preflight_summary.scheduled_ocr_pages} 页${item.preflight_summary.detected_ocr_pages !== undefined ? `（检测到 ${item.preflight_summary.detected_ocr_pages} 页）` : ""}`
                      : "等待检测"}</dd></div>
                  </dl>
                  <div className="ingestion-candidate-summary">
                    {Object.entries(candidateFieldLabels).map(([field, label]) => (
                      <span className={candidateCounts[field] ? "available" : ""} key={field}>{label}<b>{candidateCounts[field] || 0}</b></span>
                    ))}
                  </div>
                  {item.error_message ? <p className="ingestion-item-error"><AlertCircle size={14} /><span><strong>{item.error_code || "处理错误"}</strong>{item.error_message}</span></p> : null}
                  {!item.edition && !item.error_message ? <p className="ingestion-item-note">文件已安全保存。书目记录建立后，可直接进入候选复核；等待期间无需重复点击。</p> : null}
                  <footer>
                    {canRetry ? <button className="button secondary" type="button" disabled={retryingItem === item.id} onClick={() => void retryIngestionItem(item.id)}>{retryingItem === item.id ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}重新处理</button> : null}
                    {item.edition ? <Link className="button secondary" href={`/admin/review/${item.id}`}>复核识别候选 <ArrowRight size={14} /></Link> : <span className="ingestion-waiting-action">等待书目识别</span>}
                    {item.edition && item.can_manage_publication ? <Link className="button" href={`/admin/publication?item=${item.id}`}>进入发布确认 <ArrowRight size={14} /></Link> : null}
                  </footer>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="pipeline-explainer admin-panel">
        <header><h2>处理步骤</h2></header>
        {["校验与哈希查重", "原生文本检测", "按需排队 PaddleOCR", "元数据候选与网页校验", "作者、理论和主题关系", "全文索引与页码坐标", "规范文件名与云端副本", "管理员发布"].map((step, index) => (
          <div key={step}><b>{String(index + 1).padStart(2, "0")}</b><span>{step}</span></div>
        ))}
      </section>
    </div>
  );
}
