export type ResearchTabDraft<T> = { version: 1; owner: string; project: string; kind: string; at: number; input: T };
export type ResearchNoteDraft = { text: string; initial: string; revision: number };
export const researchTabDraftKey = (owner: string, project: string, kind: string) => `stl:research-input:v1:${owner}:${project}:${kind}`;

export function parseResearchTabDraft<T>(raw: string | null, owner: string, project: string, kind: string, parseInput: (value: unknown) => T): ResearchTabDraft<T> | null {
  if (!raw) return null;
  if (raw.length > 300000) throw new Error("本机暂存超过读取范围，原记录未覆盖。");
  const value = JSON.parse(raw) as ResearchTabDraft<unknown>;
  if (!value || value.version !== 1 || value.owner !== owner || value.project !== project || value.kind !== kind
    || !Number.isFinite(value.at) || value.at <= 0 || !Number.isFinite(new Date(value.at).getTime())) throw new Error("暂存归属或时间无法核对，原记录未覆盖。");
  return { version: 1, owner, project, kind, at: value.at, input: parseInput(value.input) };
}

export function parseResearchNoteDraft(value: unknown): ResearchNoteDraft {
  const draft = value as ResearchNoteDraft;
  if (!draft || typeof draft.text !== "string" || draft.text.length > 20000 || typeof draft.initial !== "string" || draft.initial.length > 20000
    || !Number.isSafeInteger(draft.revision) || draft.revision < 1) throw new Error("笔记暂存格式无法核对，原记录未覆盖。");
  return { text: draft.text, initial: draft.initial, revision: draft.revision };
}
