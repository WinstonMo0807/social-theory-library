"use client";

const groups = [
  ["editorial", "书目资料", { draft: "还需填写", needs_review: "需要核对", conflict: "有人修改过，请核对", ready: "已核对" }],
  ["processing", "自动处理", { idle: "暂无任务", processing: "处理中", partial: "部分完成", ready: "已完成", failed: "需要处理失败事项" }],
  ["publication", "读者页面", { unpublished: "尚未公开", published: "已公开", changes_pending: "有修改未发布", publishing: "正在更新", withdrawn: "已下架" }],
] as const;

export function CatalogHealth({ value }: { value?: Record<string, string> }) {
  if (!value) return null;
  return <dl className="workflow-publication-summary" aria-label="编目、处理与公开状态">{groups.map(([key, title, labels]) =>
    <div key={key}><dt>{title}</dt><dd>{(labels as Record<string, string>)[value[key]] || "待核实"}</dd></div>,
  )}</dl>;
}
