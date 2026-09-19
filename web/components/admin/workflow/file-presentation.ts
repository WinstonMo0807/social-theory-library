export function pdfValidationPresentation(value: unknown) {
  if (value === "valid") return { state: "valid", label: "已通过", tone: "success", detail: "文件已完成 PDF 校验。" };
  if (value === "invalid") return { state: "invalid", label: "未通过", tone: "error", detail: "文件未通过校验，请查看具体原因并恢复处理；不能将它作为合格阅读文件发布。" };
  return { state: "pending", label: "等待校验", tone: "pending", detail: "尚无验证通过的结果。等待文件处理完成，或在失败后重试原任务。" };
}

export function fileDraftFromWorkspace(value: Record<string, unknown>) {
  const legacyItem = value.item && typeof value.item === "object" && !Array.isArray(value.item) ? value.item as Record<string, unknown> : {};
  return {...value, ...legacyItem, assets:Array.isArray(value.assets) ? value.assets : []};
}

export const WORKFLOW_GROUPS = [
  { label:"书目信息", steps:["work","bibliography"] },
  { label:"文件与阅读", steps:["file","reader"] },
  { label:"人物及知识关联", steps:["contributors","classification","curation"] },
  { label:"预览与发布", steps:["publication"] },
] as const;

export function fileKindLabel(value:unknown){return ({original:"上传原件",normalized:"阅读文件",ocr_pdf:"可搜索的扫描文件",extracted_text:"提取的文字",ocr_text:"识别的文字"} as Record<string,string>)[String(value)] || "附件";}
import { R2_STAGING_STATUS_LABELS } from "@/lib/ingestion-staging-status";

const fileStatusLabels: Record<string, string> = {
  ...R2_STAGING_STATUS_LABELS,
  received: "已收到文件，等待处理", validating: "正在检查 PDF", deduplicating: "正在核对重复文件",
  extracting: "正在提取文字", ocr: "正在识别扫描文字", metadata: "正在识别书目信息",
  linking: "正在关联当前文献", indexing: "正在更新检索", preparing_public_asset: "正在准备阅读文件",
  syncing_cloud: "正在同步公开文件", ready: "文件已处理，等待确认发布", published: "发布请求已保存，请核对读者正在使用的文件",
  needs_review: "需要人工核对", failed: "处理失败", withdrawn: "已撤回", deleted: "已删除",
  pending: "等待处理", queued: "已排队", running: "处理中", completed: "本项处理已完成", succeeded: "本项处理已完成", paused: "已暂停",
};

export function fileProcessingStatusLabel(value: unknown) { return fileStatusLabels[String(value)] || "处理状态待核实"; }
export function fileTextProfileLabel(value: unknown) { return ({born_digital: "PDF 自带文字", scanned: "扫描图片，需要文字识别", mixed: "文字与扫描图片混合"} as Record<string, string>)[String(value)] || "尚未识别"; }
export function fileDuplicateLabel(value: unknown) { return ({existing_edition: "文件已关联到当前出版版本", existing_work: "已找到同一作品，请核对出版版本", ambiguous: "找到多个可能相同的文献，需要人工核对", new: "未找到重复文献"} as Record<string, string>)[String(value)] || "尚无重复判断结果"; }
