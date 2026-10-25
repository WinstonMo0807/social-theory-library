export type ResearchPromptInput = { question: string; scope: "saved" | "selected" | "library" };
export type ResearchPromptRecovery = { version: 1; owner: string; project: string; at: number; input: ResearchPromptInput };
export const researchPromptKey = (owner: string, project: string) => `stl:research-input:v1:${owner}:${project}`;

/** Caller opts in. Only typed input and the range choice belong in this tab store. */
export function parseResearchPrompt(raw: string | null, owner: string, project: string): ResearchPromptRecovery | null {
  if (!raw) return null;
  if (raw.length > 20000) throw new Error("本标签页草稿超过读取范围，原记录未覆盖。");
  const value = JSON.parse(raw) as ResearchPromptRecovery;
  if (!value || value.version !== 1 || value.owner !== owner || value.project !== project || !Number.isFinite(value.at) || value.at <= 0 || !Number.isFinite(new Date(value.at).getTime())
    || !value.input || typeof value.input.question !== "string" || value.input.question.length > 1200
    || !["saved", "selected", "library"].includes(value.input.scope)) throw new Error("本标签页草稿身份或格式无法核对，原记录未覆盖。");
  return { version: 1, owner, project, at: value.at, input: { question: value.input.question, scope: value.input.scope } };
}
