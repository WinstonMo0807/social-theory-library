import type { OutlineNode } from "@/lib/api/document-outline";
import type { OutlineEditNode } from "@/lib/api/curation-workspace.client";

export type EditableOutlineNode = OutlineNode & { id: string; title: string; level: number };
export const outlineSourceLabels: Record<string, string> = { pdf_bookmark: "PDF 书签", printed_contents: "印刷目录", generated_heading: "正文标题", manual: "人工校准", legacy_page_heading: "历史页标题" };
export const outlineStatusLabels: Record<string, string> = { confirmed: "已确认", native: "原生书签", matched: "待复核", generated: "待复核", unverified: "待确认", needs_review: "待校准" };
export function editableOutline(nodes: OutlineNode[]): EditableOutlineNode[] {
  return nodes.map(node => ({ ...node, id: node.id!, title: node.title || node.chapter_title || "", level: node.level || 1 }));
}
export function outlineCommandNodes(nodes: EditableOutlineNode[]): OutlineEditNode[] {
  return nodes.map(node => ({ id: node.id, parent_id: node.parent_id || null, title: node.title,
    pdf_page: node.pdf_page ?? null, printed_label: node.printed_label || "", contents_page: node.contents_page ?? null,
    pdf_position: node.pdf_position || [], normalized_position: node.normalized_position || [],
    calibration_status: node.calibration_status || "unverified", ...(node.clear_position ? { clear_position: true } : {}) }));
}
export function outlineDescendants(nodes: EditableOutlineNode[], id: string) {
  const ids = new Set([id]);
  for (const node of nodes) if (node.parent_id && ids.has(node.parent_id)) ids.add(node.id);
  return ids;
}
/** Preserve sibling order while keeping every subtree contiguous and parent first. */
export function orderOutline(nodes: EditableOutlineNode[]): EditableOutlineNode[] {
  const children = new Map<string | null, EditableOutlineNode[]>();
  for (const node of nodes) { const parent = node.parent_id || null; children.set(parent, [...(children.get(parent) || []), node]); }
  const result: EditableOutlineNode[] = [];
  const stack = (children.get(null) || []).toReversed().map(node => ({ node, level: 1 }));
  const seen = new Set<string>();
  while (stack.length) {
    const { node, level } = stack.pop()!;
    if (seen.has(node.id) || level > 32) throw new Error("目录层级形成循环或超过 32 层，请重新选择上级节点。");
    seen.add(node.id); result.push({ ...node, level, position: result.length });
    for (const child of (children.get(node.id) || []).toReversed()) stack.push({ node: child, level: level + 1 });
  }
  if (result.length !== nodes.length) throw new Error("目录中有无法找到上级的节点，请重新选择上级节点。");
  return result;
}
export function moveOutlineSibling(nodes: EditableOutlineNode[], id: string, direction: -1 | 1) {
  const node = nodes.find(row => row.id === id);
  if (!node) return nodes;
  const siblings = nodes.filter(row => (row.parent_id || null) === (node.parent_id || null));
  const other = siblings[siblings.findIndex(row => row.id === id) + direction];
  if (!other) return nodes;
  const left = nodes.findIndex(row => row.id === id), right = nodes.findIndex(row => row.id === other.id);
  const copy = [...nodes];
  [copy[left], copy[right]] = [copy[right], copy[left]];
  return orderOutline(copy);
}
