import { apiRequest, getServerSessionCredential } from "./api";
import { UploadRateMeter } from "./upload-metrics";

const PART_CONCURRENCY = 3;
const GLOBAL_PART_CONCURRENCY = 6;
const STALL_NOTICE_MS = 5_000;
const STALL_ABORT_MS = 18_000;
const PROGRESS_THROTTLE_MS = 150;
const MAX_PART_ATTEMPTS = 3;

export type R2CompletedPart = {
  part_number: number;
  etag: string;
  size: number;
};

export type R2StagingSession = {
  upload_session_id: string;
  batch_id: string;
  source_filename: string;
  file_size: number;
  file_last_modified: number;
  part_size: number;
  total_parts: number;
  completed_parts: R2CompletedPart[];
  staging_status: string;
  ingestion_status: string;
  stage_progress: number;
  error_code: string;
  error_message: string;
  created_at: string;
  updated_at: string;
  can_resume_upload: boolean;
  can_abort: boolean;
  can_retry_import: boolean;
};

export type R2PartState = {
  partNumber: number;
  totalBytes: number;
  loadedBytes: number;
  status: "waiting" | "uploading" | "retrying" | "completed" | "failed";
  attempt: number;
  etag: string;
};

export type R2UploadSnapshot = {
  taskId: string;
  sessionId: string;
  batchId: string;
  filename: string;
  fileSize: number;
  fileLastModified: number;
  status: "waiting" | "uploading" | "connection_waiting" | "retrying" | "uploaded" | "failed" | "aborted";
  message: string;
  uploadedBytes: number;
  progress: number;
  currentSpeedBps: number;
  averageSpeedBps: number;
  etaSeconds: number | null;
  parts: R2PartState[];
  error: string;
};

type InternalTask = R2UploadSnapshot & {
  file: File;
  token: string;
  meter: UploadRateMeter;
  lastByteAt: number;
  lastRenderAt: number;
  cumulativeNetworkBytes: number;
};

class UploadPartError extends Error {
  status: number;
  code: string;
  retryable: boolean;

  constructor(message: string, status: number, code: string, retryable: boolean) {
    super(message);
    this.name = "UploadPartError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

class GlobalPartSemaphore {
  private active = 0;
  private waiters: Array<() => void> = [];

  async acquire() {
    if (this.active < GLOBAL_PART_CONCURRENCY) {
      this.active += 1;
      return;
    }
    await new Promise<void>((resolve) => this.waiters.push(resolve));
    this.active += 1;
  }

  release() {
    this.active = Math.max(0, this.active - 1);
    this.waiters.shift()?.();
  }
}

const semaphore = new GlobalPartSemaphore();

function cloneSnapshot(task: InternalTask): R2UploadSnapshot {
  return {
    taskId: task.taskId,
    sessionId: task.sessionId,
    batchId: task.batchId,
    filename: task.filename,
    fileSize: task.fileSize,
    fileLastModified: task.fileLastModified,
    status: task.status,
    message: task.message,
    uploadedBytes: task.uploadedBytes,
    progress: task.progress,
    currentSpeedBps: task.currentSpeedBps,
    averageSpeedBps: task.averageSpeedBps,
    etaSeconds: task.etaSeconds,
    parts: task.parts.map((part) => ({ ...part })),
    error: task.error,
  };
}

function partByteLength(totalBytes: number, partSize: number, partNumber: number) {
  const start = (partNumber - 1) * partSize;
  return Math.max(0, Math.min(partSize, totalBytes - start));
}

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, milliseconds));
}

export class R2MultipartUploadManager {
  private tasks = new Map<string, InternalTask>();
  private listeners = new Set<(snapshots: R2UploadSnapshot[]) => void>();
  private requests = new Map<string, XMLHttpRequest>();
  private running = new Map<string, Promise<R2StagingSession>>();
  private ticker: ReturnType<typeof setInterval> | null = null;

  subscribe(listener: (snapshots: R2UploadSnapshot[]) => void) {
    this.listeners.add(listener);
    listener(this.snapshots());
    return () => {
      this.listeners.delete(listener);
    };
  }

  snapshots() {
    return Array.from(this.tasks.values()).map(cloneSnapshot);
  }

  findByFile(file: File) {
    return this.snapshots().find(
      (task) => task.filename === file.name
        && task.fileSize === file.size
        && task.fileLastModified === file.lastModified,
    );
  }

  hydrateSessions(sessions: R2StagingSession[]) {
    for (const session of sessions) {
      const active = Array.from(this.tasks.values()).find(
        (task) => task.sessionId === session.upload_session_id,
      );
      if (active && this.running.has(active.taskId)) continue;
      if (active) {
        active.message = this.sessionMessage(session);
        active.status = session.staging_status === "aborted" ? "aborted"
          : session.staging_status === "uploading" ? "waiting"
            : session.staging_status === "uploaded" || session.staging_status === "importing" || session.staging_status === "imported" || session.staging_status === "cleanup_pending" || session.staging_status === "cleaned"
              ? "uploaded"
              : "failed";
        active.error = session.error_message || "";
        this.emit(true);
      }
    }
  }

  async start(file: File, batchId: string, token: string) {
    const existing = this.findByFile(file);
    if (existing && this.running.has(existing.taskId)) {
      return this.running.get(existing.taskId) as Promise<R2StagingSession>;
    }
    const task = this.newTask(file, batchId, token, existing?.sessionId || "");
    this.tasks.set(task.taskId, task);
    const promise = this.run(task);
    this.running.set(task.taskId, promise);
    this.ensureTicker();
    promise.finally(() => {
      this.running.delete(task.taskId);
      this.stopTickerIfIdle();
    }).catch(() => undefined);
    return promise;
  }

  async resume(file: File, session: R2StagingSession) {
    const task = this.newTask(file, session.batch_id, session.upload_session_id, session.upload_session_id);
    this.applySession(task, session);
    this.tasks.set(task.taskId, task);
    const promise = this.run(task, session);
    this.running.set(task.taskId, promise);
    this.ensureTicker();
    promise.finally(() => {
      this.running.delete(task.taskId);
      this.stopTickerIfIdle();
    }).catch(() => undefined);
    return promise;
  }

  async abort(sessionId: string) {
    const task = Array.from(this.tasks.values()).find((value) => value.sessionId === sessionId);
    if (task) {
      for (const [key, request] of this.requests) {
        if (key.startsWith(`${task.taskId}:`)) request.abort();
      }
    }
    const token = getServerSessionCredential();
    const session = await apiRequest<R2StagingSession>(
      `/ingestion/uploads/r2/${sessionId}/abort/`,
      { method: "POST", body: "{}" },
      token,
    );
    if (task) {
      task.status = "aborted";
      task.message = "上传已取消";
      task.error = "";
      this.emit(true);
    }
    return session;
  }

  private newTask(file: File, batchId: string, token: string, sessionId: string): InternalTask {
    const now = performance.now();
    return {
      taskId: token,
      sessionId,
      batchId,
      filename: file.name,
      fileSize: file.size,
      fileLastModified: file.lastModified,
      status: "waiting",
      message: "正在建立安全上传会话",
      uploadedBytes: 0,
      progress: 0,
      currentSpeedBps: 0,
      averageSpeedBps: 0,
      etaSeconds: null,
      parts: [],
      error: "",
      file,
      token,
      meter: new UploadRateMeter(file.size, 0, now),
      lastByteAt: now,
      lastRenderAt: 0,
      cumulativeNetworkBytes: 0,
    };
  }

  private applySession(task: InternalTask, session: R2StagingSession) {
    task.sessionId = session.upload_session_id;
    task.batchId = session.batch_id;
    task.parts = Array.from({ length: session.total_parts }, (_, index) => {
      const partNumber = index + 1;
      const complete = session.completed_parts.find((part) => part.part_number === partNumber);
      const totalBytes = partByteLength(session.file_size, session.part_size, partNumber);
      return {
        partNumber,
        totalBytes,
        loadedBytes: complete ? totalBytes : 0,
        status: complete ? "completed" : "waiting",
        attempt: complete ? 1 : 0,
        etag: complete?.etag || "",
      };
    });
    const uploadedBytes = task.parts.reduce((total, part) => total + part.loadedBytes, 0);
    task.uploadedBytes = Math.min(task.fileSize, uploadedBytes);
    task.progress = task.fileSize ? Math.min(99, Math.floor((task.uploadedBytes / task.fileSize) * 100)) : 0;
    task.meter = new UploadRateMeter(task.fileSize, task.uploadedBytes, performance.now());
    task.message = session.completed_parts.length
      ? `已恢复 ${session.completed_parts.length}/${session.total_parts} 个 part`
      : "上传会话已恢复";
  }

  private async run(task: InternalTask, existingSession?: R2StagingSession) {
    try {
      const token = getServerSessionCredential();
      const session = existingSession || await apiRequest<R2StagingSession>(
        "/ingestion/uploads/r2/init/",
        {
          method: "POST",
          body: JSON.stringify({
            batch_id: task.batchId,
            source_filename: task.filename,
            file_size: task.fileSize,
            file_last_modified: task.fileLastModified,
            content_type: task.file.type || "application/pdf",
            client_token: task.token,
          }),
        },
        token,
      );
      if (session.source_filename !== task.filename || session.file_size !== task.fileSize) {
        throw new Error("服务端上传会话与当前 PDF 不一致。")
      }
      this.applySession(task, session);
      task.status = "uploading";
      this.emit(true);

      const pending = task.parts.filter((part) => part.status !== "completed");
      for (let offset = 0; offset < pending.length; offset += PART_CONCURRENCY) {
        const wave = pending.slice(offset, offset + PART_CONCURRENCY);
        const signed = await apiRequest<{
          parts: Array<{ part_number: number; size: number; url: string; expires_in: number }>;
        }>(
          `/ingestion/uploads/r2/${task.sessionId}/parts/sign/`,
          {
            method: "POST",
            body: JSON.stringify({ part_numbers: wave.map((part) => part.partNumber) }),
          },
          token,
        );
        const urlByPart = new Map(signed.parts.map((part) => [part.part_number, part.url]));
        await Promise.all(wave.map((part) => this.uploadPart(task, part, urlByPart.get(part.partNumber) || "")));
      }

      const completed = task.parts
        .map((part) => ({ part_number: part.partNumber, etag: part.etag }))
        .sort((left, right) => left.part_number - right.part_number);
      const finalSession = await apiRequest<R2StagingSession>(
        `/ingestion/uploads/r2/${task.sessionId}/complete/`,
        { method: "POST", body: JSON.stringify({ parts: completed }) },
        token,
      );
      task.status = "uploaded";
      task.uploadedBytes = task.fileSize;
      task.progress = 100;
      task.currentSpeedBps = 0;
      task.etaSeconds = 0;
      task.message = "上传完成，正在入库";
      task.error = "";
      this.emit(true);
      return finalSession;
    } catch (reason) {
      task.status = "failed";
      task.currentSpeedBps = 0;
      task.etaSeconds = null;
      task.error = reason instanceof Error ? reason.message : "上传失败。";
      task.message = task.sessionId
        ? "PDF 上传未完成，可重新选择同一文件继续"
        : "无法建立上传会话";
      this.emit(true);
      throw reason;
    }
  }

  private async uploadPart(task: InternalTask, part: R2PartState, initialUrl: string) {
    let url = initialUrl;
    let lastError: unknown = null;
    for (let attempt = 1; attempt <= MAX_PART_ATTEMPTS; attempt += 1) {
      part.attempt = attempt;
      part.loadedBytes = 0;
      part.status = attempt === 1 ? "uploading" : "retrying";
      task.status = attempt === 1 ? "uploading" : "retrying";
      task.message = attempt === 1
        ? `正在上传 part ${part.partNumber}/${task.parts.length}`
        : `正在重试 part ${part.partNumber}/${task.parts.length}，第 ${attempt}/${MAX_PART_ATTEMPTS} 次`;
      this.recalculate(task, 0, true);
      try {
        if (!url || attempt > 1) {
          const signed = await apiRequest<{
            parts: Array<{ part_number: number; url: string }>;
          }>(
            `/ingestion/uploads/r2/${task.sessionId}/parts/sign/`,
            { method: "POST", body: JSON.stringify({ part_numbers: [part.partNumber] }) },
            getServerSessionCredential(),
          );
          url = signed.parts[0]?.url || "";
        }
        if (!url) throw new UploadPartError("没有可用的 part URL。", 0, "missing_url", true);
        const start = (part.partNumber - 1) * task.parts[0].totalBytes;
        const payload = task.file.slice(start, start + part.totalBytes, "application/octet-stream");
        await semaphore.acquire();
        let etag: string;
        try {
          etag = await this.putPart(task, part, payload, url);
        } finally {
          semaphore.release();
        }
        await apiRequest(
          `/ingestion/uploads/r2/${task.sessionId}/parts/confirm/`,
          {
            method: "POST",
            body: JSON.stringify({
              part_number: part.partNumber,
              etag,
              size: part.totalBytes,
              attempt,
            }),
          },
          getServerSessionCredential(),
        );
        part.etag = etag;
        part.loadedBytes = part.totalBytes;
        part.status = "completed";
        task.status = "uploading";
        task.message = `已完成 part ${part.partNumber}/${task.parts.length}`;
        this.recalculate(task, 0, true);
        return;
      } catch (reason) {
        lastError = reason;
        const failure = reason instanceof UploadPartError
          ? reason
          : new UploadPartError(
            reason instanceof Error ? reason.message : "part 上传失败。",
            0,
            "part_upload_error",
            true,
          );
        await this.reportPartFailure(task, part, attempt, failure);
        if (!failure.retryable || attempt >= MAX_PART_ATTEMPTS) break;
        await wait(750 * 2 ** (attempt - 1));
      }
    }
    part.status = "failed";
    this.recalculate(task, 0, true);
    throw lastError instanceof Error ? lastError : new Error("part 连续上传失败。")
  }

  private putPart(task: InternalTask, part: R2PartState, payload: Blob, url: string) {
    return new Promise<string>((resolve, reject) => {
      const request = new XMLHttpRequest();
      const requestKey = `${task.taskId}:${part.partNumber}`;
      let lastLoaded = 0;
      let lastByteAt = performance.now();
      let stalled = false;
      request.open("PUT", url, true);
      request.timeout = 0;
      request.setRequestHeader("Content-Type", "application/octet-stream");
      this.requests.set(requestKey, request);
      const watchdog = setInterval(() => {
        const now = performance.now();
        if (now - lastByteAt >= STALL_NOTICE_MS) {
          task.status = "connection_waiting";
          task.message = `连接等待中，part ${part.partNumber}/${task.parts.length}`;
          this.recalculate(task, 0, true);
        }
        if (now - lastByteAt >= STALL_ABORT_MS) {
          stalled = true;
          request.abort();
        }
      }, 1_000);
      const finish = () => {
        clearInterval(watchdog);
        this.requests.delete(requestKey);
      };
      request.upload.onprogress = (event) => {
        const now = performance.now();
        const loaded = Math.min(part.totalBytes, Math.max(0, event.loaded));
        const networkDelta = Math.max(0, loaded - lastLoaded);
        if (networkDelta > 0) {
          lastByteAt = now;
          task.lastByteAt = now;
          task.status = "uploading";
        }
        lastLoaded = loaded;
        part.loadedBytes = loaded;
        this.recalculate(task, networkDelta, now - task.lastRenderAt >= PROGRESS_THROTTLE_MS);
      };
      request.onload = () => {
        finish();
        if (request.status < 200 || request.status >= 300) {
          const retryable = request.status === 403 || request.status === 408 || request.status === 429 || request.status >= 500;
          reject(new UploadPartError(
            `part 上传失败（HTTP ${request.status}）。`,
            request.status,
            `http_${request.status}`,
            retryable,
          ));
          return;
        }
        const etag = request.getResponseHeader("ETag")?.trim() || "";
        if (!etag) {
          reject(new UploadPartError(
            "R2 响应缺少 ETag，请检查 bucket CORS ExposeHeaders。",
            request.status,
            "etag_missing",
            false,
          ));
          return;
        }
        resolve(etag);
      };
      request.onerror = () => {
        finish();
        reject(new UploadPartError("上传连接中断。", 0, "network_error", true));
      };
      request.onabort = () => {
        finish();
        reject(new UploadPartError(
          stalled ? "part 18 秒没有上传字节，已重新连接。" : "part 上传已取消。",
          0,
          stalled ? "stalled" : "aborted",
          stalled,
        ));
      };
      request.send(payload);
    });
  }

  private async reportPartFailure(
    task: InternalTask,
    part: R2PartState,
    attempt: number,
    failure: UploadPartError,
  ) {
    try {
      await apiRequest(
        `/ingestion/uploads/r2/${task.sessionId}/parts/failure/`,
        {
          method: "POST",
          body: JSON.stringify({
            part_number: part.partNumber,
            attempt,
            http_status: failure.status,
            error_code: failure.code,
          }),
        },
        getServerSessionCredential(),
      );
    } catch {
      // Telemetry must never replace the actual part retry result.
    }
  }

  private logicalBytes(task: InternalTask) {
    return Math.min(
      task.fileSize,
      task.parts.reduce((total, part) => total + Math.min(part.totalBytes, part.loadedBytes), 0),
    );
  }

  private recalculate(task: InternalTask, networkDelta: number, forceEmit = false) {
    const now = performance.now();
    const logicalBytes = this.logicalBytes(task);
    const metrics = task.meter.sample(logicalBytes, networkDelta, now);
    task.cumulativeNetworkBytes += Math.max(0, networkDelta);
    task.uploadedBytes = metrics.logicalBytes;
    task.progress = task.fileSize
      ? Math.min(99, Math.floor((metrics.logicalBytes / task.fileSize) * 100))
      : 0;
    task.currentSpeedBps = metrics.currentSpeedBps;
    task.averageSpeedBps = metrics.averageSpeedBps;
    task.etaSeconds = metrics.etaSeconds;
    if (forceEmit || now - task.lastRenderAt >= PROGRESS_THROTTLE_MS) {
      task.lastRenderAt = now;
      this.emit(true);
    }
  }

  private ensureTicker() {
    if (this.ticker || typeof window === "undefined") return;
    this.ticker = setInterval(() => {
      for (const task of this.tasks.values()) {
        if (!this.running.has(task.taskId)) continue;
        this.recalculate(task, 0, true);
      }
    }, 500);
  }

  private stopTickerIfIdle() {
    if (this.running.size || !this.ticker) return;
    clearInterval(this.ticker);
    this.ticker = null;
  }

  private emit(force = false) {
    if (!force) return;
    const snapshots = this.snapshots();
    for (const listener of this.listeners) listener(snapshots);
  }

  private sessionMessage(session: R2StagingSession) {
    const labels: Record<string, string> = {
      uploading: "等待继续上传",
      uploaded: "上传完成，正在入库",
      importing: "上传完成，正在入库",
      imported: "PDF 已进入正式存储，正在处理",
      import_failed: "PDF 已安全上传，入库失败，可重试",
      cleanup_pending: "入库完成，等待清理 staging",
      cleaned: "入库完成",
      aborted: "上传已取消",
      expired: "staging object 已过期，需要重新上传",
    };
    return labels[session.staging_status] || session.staging_status;
  }
}

export const r2MultipartUploadManager = new R2MultipartUploadManager();

export async function loadR2StagingSessions() {
  const response = await apiRequest<{ results: R2StagingSession[] }>(
    "/ingestion/uploads/r2/",
    {},
    getServerSessionCredential(),
  );
  return response.results;
}

export async function retryR2Import(sessionId: string) {
  return apiRequest<R2StagingSession>(
    `/ingestion/uploads/r2/${sessionId}/retry-import/`,
    { method: "POST", body: "{}" },
    getServerSessionCredential(),
  );
}
