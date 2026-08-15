export type UploadMetricSnapshot = {
  logicalBytes: number;
  currentSpeedBps: number;
  averageSpeedBps: number;
  etaSeconds: number | null;
};

export class UploadRateMeter {
  private readonly totalBytes: number;
  private readonly startedAt: number;
  private readonly startingBytes: number;
  private lastSampleAt: number;
  private logicalBytes: number;
  private smoothedSpeedBps = 0;

  constructor(
    totalBytes: number,
    startingBytes = 0,
    now = 0,
  ) {
    this.totalBytes = Math.max(0, totalBytes);
    this.startedAt = now;
    this.lastSampleAt = now;
    this.startingBytes = Math.max(0, Math.min(this.totalBytes, startingBytes));
    this.logicalBytes = this.startingBytes;
  }

  sample(logicalBytes: number, networkBytes: number, now: number): UploadMetricSnapshot {
    this.logicalBytes = Math.max(
      this.logicalBytes,
      Math.min(this.totalBytes, Math.max(0, logicalBytes)),
    );
    const sampleSeconds = Math.max(0.001, (now - this.lastSampleAt) / 1000);
    if (networkBytes > 0) {
      const instantSpeed = networkBytes / sampleSeconds;
      this.smoothedSpeedBps = this.smoothedSpeedBps
        ? this.smoothedSpeedBps * 0.72 + instantSpeed * 0.28
        : instantSpeed;
    }
    this.lastSampleAt = Math.max(this.lastSampleAt, now);

    const elapsedSeconds = Math.max(0.001, (now - this.startedAt) / 1000);
    const effectiveBytes = Math.max(0, this.logicalBytes - this.startingBytes);
    const averageSpeedBps = effectiveBytes / elapsedSeconds;
    const remainingBytes = Math.max(0, this.totalBytes - this.logicalBytes);
    const etaBasis = averageSpeedBps || this.smoothedSpeedBps;

    return {
      logicalBytes: this.logicalBytes,
      currentSpeedBps: this.smoothedSpeedBps,
      averageSpeedBps,
      etaSeconds: remainingBytes > 0 && etaBasis > 0 ? remainingBytes / etaBasis : 0,
    };
  }
}

export function formatUploadBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${Math.round(bytes)} B`;
}

export function formatUploadRate(bytesPerSecond: number) {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return "正在测量";
  return `${formatUploadBytes(bytesPerSecond)}/s`;
}

export function formatUploadEta(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "计算中";
  if (seconds <= 1) return "即将完成";
  if (seconds < 60) return `约 ${Math.ceil(seconds)} 秒`;
  if (seconds < 3600) return `约 ${Math.ceil(seconds / 60)} 分钟`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.ceil((seconds % 3600) / 60);
  return `约 ${hours} 小时${minutes ? ` ${minutes} 分钟` : ""}`;
}
