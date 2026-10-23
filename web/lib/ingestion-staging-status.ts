export const INGESTION_TERMINAL_STATUSES = new Set([
  "needs_review", "ready", "failed", "published", "withdrawn", "deleted",
]);

export type DocumentStage = {job_id:string|null;source:string;status:string;progress:number|null;updated_at?:string};
export type UploadStageState = {status:string;updated_at?:string;document_stages?:Record<string,DocumentStage|null>};

export function uploadSnapshotTime(item: UploadStageState) {
  return Math.max(0, ...[item.updated_at, ...Object.values(item.document_stages || {}).map(stage=>stage?.updated_at)]
    .map(value=>value?Date.parse(value)||0:0));
}

export function activeUploadStage(item?: UploadStageState) {
  const stages = Object.values(item?.document_stages || {});
  return stages.find(stage => stage?.job_id && stage.status === "running")
    || stages.find(stage => stage?.job_id && stage.status === "paused")
    || stages.find(stage => stage?.job_id && ["pending", "queued"].includes(stage.status));
}

export function uploadNeedsRefresh(item: UploadStageState) {
  return !INGESTION_TERMINAL_STATUSES.has(item.status) || Boolean(activeUploadStage(item));
}

export const R2_STAGING_STATUS_LABELS: Record<string, string> = {
  uploading: "正在上传至临时区",
  uploaded: "PDF 已上传至临时区，等待导入书库存储",
  importing: "正在导入正式书库存储",
  imported: "PDF 已进入正式书库存储，正在识别",
  import_failed: "正式书库存储导入失败",
  cleanup_pending: "正式入库完成，等待清理临时文件",
  cleaned: "正式入库完成",
  aborted: "上传已取消",
  expired: "临时上传已过期，需要重新上传 PDF",
};

const R2_STAGING_OWNS_PRIMARY_STATUS = new Set([
  "uploading",
  "uploaded",
  "importing",
  "import_failed",
  "aborted",
  "expired",
]);

const R2_BROWSER_UPLOAD_COMPLETE = new Set([
  "uploaded",
  "importing",
  "imported",
  "import_failed",
  "cleanup_pending",
  "cleaned",
]);

export function r2StagingStatusLabel(status: string) {
  return R2_STAGING_STATUS_LABELS[status] || status;
}

export function r2StagingOwnsPrimaryStatus(status: string) {
  return R2_STAGING_OWNS_PRIMARY_STATUS.has(status);
}

export function r2BrowserUploadComplete(status: string) {
  return R2_BROWSER_UPLOAD_COMPLETE.has(status);
}

export function r2StagingWaitingAction(status: string) {
  if (status === "import_failed") return "重新导入";
  if (status === "expired") return "需要重新上传 PDF";
  if (status === "aborted") return "上传已取消";
  if (status === "uploading") return "等待浏览器完成上传";
  if (status === "uploaded" || status === "importing") return "等待正式入库";
  return "等待书目识别";
}
