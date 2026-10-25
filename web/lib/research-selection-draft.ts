import { parseResearchReferenceDraft } from "./research-pending-turn";
import type { EvidenceReference } from "./api/research.client";

export type SelectionDraftItem = { key: string; title: string; reference: EvidenceReference };
export type ResearchSelectionDraft = { revision: number; additions: SelectionDraftItem[]; removals: Array<{ key: string; title: string }>; requestId?: string };
export function parseResearchSelectionDraft(value: unknown): ResearchSelectionDraft {
  const draft = value as ResearchSelectionDraft;
  if (!draft || !Number.isSafeInteger(draft.revision) || draft.revision < 1 || !Array.isArray(draft.additions) || !Array.isArray(draft.removals)
    || draft.additions.length + draft.removals.length > 400 || draft.additions.length + draft.removals.length < 1) throw new Error("待同步选材数量或修订号无法核对。");
  const label = (item: { key: string; title: string }) => {
    if (!item || typeof item.key !== "string" || !item.key || item.key.length > 240 || typeof item.title !== "string" || item.title.length > 500) throw new Error("待同步选材身份无法核对。");
    return { key: item.key, title: item.title };
  };
  const additions = draft.additions.map(item => ({ ...label(item), reference: parseResearchReferenceDraft(item.reference) }));
  const removals = draft.removals.map(label);
  const ids = [...additions, ...removals].map(item => item.key);
  if (new Set(ids).size !== ids.length) throw new Error("待同步选材包含重复或相冲突的修改。");
  if (draft.requestId !== undefined && (typeof draft.requestId !== "string" || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(draft.requestId))) throw new Error("选材原请求标识无法核对。");
  return { revision: draft.revision, additions, removals, ...(draft.requestId ? { requestId: draft.requestId } : {}) };
}
