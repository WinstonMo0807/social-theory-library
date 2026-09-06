"use client";

const groups = [
  ["editorial", "书目编辑", { draft: "未完成", needs_review: "需要核对", conflict: "存在冲突", ready: "已就绪" }],
  ["processing", "后台处理", { idle: "空闲", processing: "处理中", partial: "部分就绪", ready: "已就绪", failed: "处理失败" }],
  ["publication", "公开内容", { unpublished: "尚未公开", published: "已公开", changes_pending: "有待发布修改", publishing: "发布处理中", withdrawn: "已撤回" }],
] as const;

export function CatalogHealth({ value }: { value?: Record<string, string> }) {
  if (!value) return null;
  return <dl className="workflow-publication-summary" aria-label="编目、处理与公开状态">{groups.map(([key, title, labels]) =>
    <div key={key}><dt>{title}</dt><dd>{(labels as Record<string, string>)[value[key]] || "待核实"}</dd></div>,
  )}</dl>;
}
