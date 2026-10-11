type ProjectionState = { type: string; label: string; status: string; lag: number; last_error_code: string };

const names: Record<string, string> = { query_lexicon: "检索用语", claim_index: "观点索引" };
const states: Record<string, string> = {
  current: "已更新", stale: "等待更新", projecting: "更新中",
  waiting_for_capability: "等待可用执行服务", failed: "更新失败",
  unknown: "待核实", not_materialized: "尚未建立",
};

export function projectionStatusText(row: ProjectionState) {
  const status = row.last_error_code ? states.failed
    : row.status === "current" && row.lag > 0 ? states.stale
    : states[row.status] || states.unknown;
  return `${names[row.type] || row.label || "其他内容"}：${status}`;
}
