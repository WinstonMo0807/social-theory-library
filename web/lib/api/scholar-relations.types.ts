export type ScholarRelation = {
  id: string;
  source_scholar: string;
  target_scholar: string;
  source_name: string;
  target_name: string;
  source_slug?: string;
  target_slug?: string;
  relation_type: "teaching" | "cooperation" | "influence" | "criticism" | "comparative_reading" | "other";
  direction: "directed" | "bidirectional" | "undirected";
  summary: string;
  source: string;
  status: string;
  edit_version: string;
  has_unpublished_changes?: boolean;
};

export const scholarRelationLabels: Record<ScholarRelation["relation_type"], string> = {
  teaching:"师承", cooperation:"合作", influence:"影响", criticism:"批评", comparative_reading:"比较阅读", other:"其他关系",
};
export const scholarDirectionLabels: Record<ScholarRelation["direction"], string> = {
  directed:"有向（第一位 → 第二位）", bidirectional:"双向", undirected:"无向",
};
export const relationArrow = (direction: ScholarRelation["direction"]) => direction === "directed" ? "→" : direction === "bidirectional" ? "↔" : "—";
export const scholarRelationStatus = (relation: Pick<ScholarRelation,"status"|"has_unpublished_changes">) => relation.status === "archived" ? "已撤下" : relation.status === "published" ? relation.has_unpublished_changes ? "已发布 · 有未发布修改" : "已发布" : "草稿";
