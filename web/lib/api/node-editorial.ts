import type { components } from "./generated/schema";
import { scholarProseValue } from "./scholar-prose";

export type NodeEditorialDetails = components["schemas"]["NodeEditorialDetails"];
export const nodeProseFields = ["summary", "definition", "theoretical_boundary"] as const;
export type NodeProseField = typeof nodeProseFields[number];

/** Existing prose tools use UTF-16 offsets; never carry marks across a text change. */
export function nodeEditorialForSave(details: NodeEditorialDetails | undefined, text: Record<NodeProseField, string>): NodeEditorialDetails {
  const prose: NodeEditorialDetails["prose"] = {};
  for (const field of nodeProseFields) {
    if (text[field].length <= 30000) {
      const format = scholarProseValue(text[field], details?.prose?.[field]);
      prose[field] = { text: format.text, text_style: format.text_style || "paragraph", text_marks: format.text_marks || [] };
    }
  }
  return { internal_note: details?.internal_note || "", prose };
}
