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
  private logicalBytes: number;
  private cumulativeNetworkBytes = 0;
  private samples: Array<{ at: number; networkBytes: number }>;
  private readonly windowMilliseconds: number;

  constructor(
    totalBytes: number,
    startingBytes = 0,
    now = 0,
    windowMilliseconds = 5_000,
  ) {
    this.totalBytes = Math.max(0, totalBytes);
    this.startedAt = now;
    this.startingBytes = Math.max(0, Math.min(this.totalBytes, startingBytes));
    this.logicalBytes = this.startingBytes;
    this.windowMilliseconds = Math.max(1_000, windowMilliseconds);
    this.samples = [{ at: now, networkBytes: 0 }];
  }

  sample(logicalBytes: number, networkBytes: number, now: number): UploadMetricSnapshot {
    this.logicalBytes = Math.min(this.totalBytes, Math.max(0, logicalBytes));
    this.cumulativeNetworkBytes += Math.max(0, networkBytes);
    this.samples.push({ at: now, networkBytes: this.cumulativeNetworkBytes });
    const cutoff = now - this.windowMilliseconds;
    while (this.samples.length > 2 && this.samples[1].at <= cutoff) {
      this.samples.shift();
    }
    if (this.samples[0].at < cutoff && this.samples.length > 1) {
      const first = this.samples[0];
      const second = this.samples[1];
      const span = Math.max(1, second.at - first.at);
      const ratio = Math.min(1, Math.max(0, (cutoff - first.at) / span));
      this.samples[0] = {
        at: cutoff,
        networkBytes: first.networkBytes + (second.networkBytes - first.networkBytes) * ratio,
      };
    }

    const first = this.samples[0];
    const last = this.samples[this.samples.length - 1];
    const windowSeconds = Math.max(0.001, (last.at - first.at) / 1000);
    const currentSpeedBps = this.samples.length > 1
      ? Math.max(0, last.networkBytes - first.networkBytes) / windowSeconds
      : 0;

    const elapsedSeconds = Math.max(0.001, (now - this.startedAt) / 1000);
    const effectiveBytes = Math.max(0, this.logicalBytes - this.startingBytes);
    const averageSpeedBps = effectiveBytes / elapsedSeconds;
    const remainingBytes = Math.max(0, this.totalBytes - this.logicalBytes);

    return {
      logicalBytes: this.logicalBytes,
      currentSpeedBps,
      averageSpeedBps,
      etaSeconds: remainingBytes === 0
        ? 0
        : currentSpeedBps >= 1
          ? remainingBytes / currentSpeedBps
          : null,
    };
  }

  snapshot(logicalBytes: number, now: number): UploadMetricSnapshot {
    return this.sample(logicalBytes, 0, now);
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
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "等待网络";
  if (seconds <= 1) return "即将完成";
  if (seconds < 60) return `约 ${Math.ceil(seconds)} 秒`;
  if (seconds < 3600) return `约 ${Math.ceil(seconds / 60)} 分钟`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.ceil((seconds % 3600) / 60);
  return `约 ${hours} 小时${minutes ? ` ${minutes} 分钟` : ""}`;
}
