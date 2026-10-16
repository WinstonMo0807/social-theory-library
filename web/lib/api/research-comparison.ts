import type { ComparisonCell, ResolvedEvidence } from "./research.client";
import { researchEvidenceKey } from "./research-evidence";

export type ComparisonColumn = { id: string; title: string; authors: string; references: ResolvedEvidence[] };
export function comparisonColumnId(reference: ResolvedEvidence) {
  if (reference.edition_id) return `edition:${reference.edition_id}`;
  if (reference.work_id) return `work:${reference.work_id}`;
  return `asset:${reference.asset_id || researchEvidenceKey(reference)}`;
}
/** Retain historical cells even when their selected document has been removed. */
export function comparisonColumns(selections: ResolvedEvidence[], cells: ComparisonCell[]): ComparisonColumn[] {
  const columns = new Map<string, ComparisonColumn>();
  for (const reference of selections) {
    const id = comparisonColumnId(reference);
    const column = columns.get(id) || { id, title: reference.title || "未命名文献", authors: (reference.authors || []).join("、"), references: [] };
    column.references.push(reference); columns.set(id, column);
  }
  for (const cell of cells) {
    const id = comparisonCellColumn(cell, [...columns.values()]);
    if (!columns.has(id)) columns.set(id, { id, title: cell.author || "保留的比较记录", authors: "来源待核对", references: [] });
  }
  return [...columns.values()];
}
export function comparisonCellColumn(cell: ComparisonCell, columns: ComparisonColumn[]): string {
  if (cell.column_id) return cell.column_id;
  const source = columns.find((column) => column.references.some((reference) => cell.reference_ids?.includes(researchEvidenceKey(reference))));
  if (source) return source.id;
  const authorMatches = cell.author ? columns.filter((column) => column.authors === cell.author || column.title === cell.author) : [];
  return authorMatches.length === 1 ? authorMatches[0].id : `retained:${cell.author || "unassigned"}`;
}
