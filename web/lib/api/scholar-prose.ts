import type { IssueBlock, IssueTextMark } from "./recommendation-issues.types";

export type ScholarProse = Partial<Record<"short_description" | "biography", Pick<IssueBlock, "text" | "text_style" | "text_marks">>>;

/** A plain-text change invalidates old offsets; source text stays authoritative. */
export function scholarProseBlock(text: string, value: unknown): IssueBlock {
  const plain: IssueBlock = { type: "paragraph", text, text_style: "paragraph", text_marks: [] };
  if (!value || typeof value !== "object") return plain;
  const row = value as Record<string, unknown>;
  if (row.text !== text || !["paragraph", "ordered", "unordered", "quote"].includes(String(row.text_style)) || !Array.isArray(row.text_marks) || row.text_marks.length > 200) return plain;
  const valid = row.text_marks.every((mark: IssueTextMark) => mark && Number.isInteger(mark.start) && Number.isInteger(mark.end) && mark.start >= 0 && mark.end <= text.length && mark.end > mark.start && ["strong", "em", "underline", "link"].includes(mark.kind) && (mark.kind !== "link" || typeof mark.href === "string"));
  return valid ? { ...plain, text_style: row.text_style as IssueBlock["text_style"], text_marks: row.text_marks as IssueTextMark[] } : plain;
}

export function scholarProseValue(text: string, value: unknown) {
  const { text_style, text_marks } = scholarProseBlock(text, value);
  return { text, text_style, text_marks };
}
