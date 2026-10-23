import type { PathMaterial, PathRevision, PublicReadingPath } from "@/lib/api/reading-paths.types";

type Row = Record<string, unknown>;
const text = (value: unknown) => typeof value === "string" ? value : "";
const rows = (value: unknown): Row[] => Array.isArray(value) ? value : [];
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((row): row is string => typeof row === "string") : [];

/** Local form preview: only unchanged, server-verified material keeps a reading link. */
export function projectReadingPath(base: Row, draft: Row): PublicReadingPath {
  const saved = base as Partial<PublicReadingPath>;
  const revision: PathRevision = saved.revision || { id: null, token: "preview", number: null, published_at: null, change_note: "尚未保存的草稿预览。", legacy: false };
  const stages = rows(draft.stages).map((stage, position) => {
    const id = text(stage.id) || text(stage.key) || `preview-stage-${position}`;
    const priorStage = saved.stages?.find(row => row.id === id);
    const items: PathMaterial[] = rows(stage.items).map((item, itemPosition) => {
      const prior = saved.items?.find(row => row.id === item.id);
      const exact = prior && prior.node_id === (item.node || null) && prior.work_id === (item.work || null)
        && prior.edition_id === (item.edition || null) && prior.asset_id === (item.asset || null)
        && prior.document_revision_id === (item.document_revision || null)
        && prior.page_start === (item.page_start ?? null) && prior.page_end === (item.page_end ?? null);
      const source: PathMaterial = exact ? prior : {
        id: text(item.id) || text(item.key), stage_id: id, kind: "work", title: text(item.work_name) || text(item.node_name) || "尚未选择材料",
        work_id: null, edition_id: null, node_id: null, asset_id: null, document_revision_id: null,
        chapter_title: "", page_start: null, page_end: null, printed_page_label: "", version_label: "", authors: [], publication_year: null,
        cover_url: "", href: null, reader_url: null, source_status: "unavailable", source_notice: "保存草稿后核对所选版本与原文位置。",
        reason: "", prerequisite: "", is_required: false, position: itemPosition, reading_order: itemPosition + 1, substitutes: [],
      };
      return { ...source, id: text(item.id) || text(item.key) || `${id}-${itemPosition}`, stage_id: id,
        kind: (item.node ? "node" : item.material_kind || "work") as PathMaterial["kind"],
        chapter_title: text(item.chapter_title), printed_page_label: text(item.printed_page_label),
        learning_goal:text(item.learning_goal),
        dependencies:rows(item.dependencies).filter(row=>typeof row.item_id === "string" && ["learning_order","theory_related"].includes(String(row.kind))).map(row=>({item_id:text(row.item_id),kind:row.kind as "learning_order"|"theory_related",reason:text(row.reason)})),
        reason: text(item.recommendation_reason), prerequisite: text(item.prerequisite), is_required: item.is_required === true,
        ...(item.status === "withdrawn" ? { source_status: "withdrawn" as const, reader_url: null, source_notice: "此材料在当前草稿中标记为撤回。" } : {}),
        position: itemPosition, substitutes: source.substitutes.filter(row => strings(item.substitute_edition_ids).includes(row.edition_id)),
      };
    });
    return { id, name: text(stage.name), description: text(stage.description), position, estimated_reading: text(stage.estimated_reading),
      learning_questions: strings(stage.learning_questions), related_debates: (priorStage?.related_debates || []).filter(row => strings(stage.related_debate_ids).includes(row.id)), items };
  });
  const items = stages.flatMap(stage => stage.items);
  return { id: text(base.id) || "preview", slug: text(draft.slug), title: text(draft.title), introduction: text(draft.introduction),
    learning_goal: text(draft.learning_goal), audience: text(draft.audience), difficulty: text(draft.difficulty), estimated_reading: text(draft.estimated_reading),
    estimated_weeks: typeof draft.estimated_weeks === "number" ? draft.estimated_weeks : null, prerequisite: text(draft.prerequisite), curator_note: text(draft.curator_note),
    credits: rows(draft.credits).map(row => ({ name: text(row.name), role: text(row.role) })), learning_questions: strings(draft.learning_questions),
    topics: (saved.topics || []).filter(row => strings(draft.topics).includes(row.id)), related_debates: (saved.related_debates || []).filter(row => strings(draft.related_debate_ids).includes(row.id)),
    revision, latest_revision: revision, is_current_revision: true, versions: [revision], versions_truncated: false, stages, items,
    counts: { stages: stages.length, items: items.length, required: items.filter(row => row.is_required).length, readable: items.filter(row => row.source_status === "available").length },
    cover_url: saved.cover_url || "", cover_media: saved.cover_media,
  };
}
