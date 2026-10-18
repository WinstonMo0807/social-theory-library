/** Status polling has a foreground budget; signed URL renewal is a separate concern. */
export const TASK_POLL_BUDGET_MS = 10 * 60 * 1000;
export const isTaskRunning = (status?: string) => ["queued", "pending", "running"].includes(status || "");

export function taskPollDelay(record: { status?: string; enhancement_status?: string; poll_after_ms?: number | null }) {
  if (!isTaskRunning(record.status) && !isTaskRunning(record.enhancement_status)) return null;
  return typeof record.poll_after_ms === "number" && Number.isFinite(record.poll_after_ms) && record.poll_after_ms > 0
    ? Math.max(1000, Math.min(record.poll_after_ms, 30000)) : null;
}

export function pollBudgetExpired(startedAt: number, now = Date.now()) {
  return now - startedAt >= TASK_POLL_BUDGET_MS;
}
