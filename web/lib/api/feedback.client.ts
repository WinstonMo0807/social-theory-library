import { apiRequest, subscribeToSessionChanges } from "../api";

export type FeedbackCategory = "content" | "function" | "usage" | "suggestion" | "other";
export type FeedbackInput = { request_id: string; category: FeedbackCategory; body: string; contact: string; path: string; consent: true };
export type FeedbackReceipt = { id: string; request_id: string; status: "submitted" | "reviewing" | "resolved"; created_at: string; message: string };

/** Only public navigation, with a physical Reader page. Never forward a token or private query. */
export function safeFeedbackPath(value: string): string {
  const input = value.trim();
  if (!input || input.length > 400 || !input.startsWith("/") || input.startsWith("//")) return "";
  let decoded = input;
  try {
    for (let index = 0; index < 4; index += 1) {
      const next = decodeURIComponent(decoded);
      if (next === decoded) break;
      decoded = next;
    }
    if (/[\\%\u0000-\u0020\u007f]/.test(decoded) || decoded.startsWith("//")) return "";
    const address = decoded.split("#", 1)[0], separator = address.indexOf("?");
    const path = separator === -1 ? address : address.slice(0, separator), query = separator === -1 ? "" : address.slice(separator + 1);
    if (path.split("/").some(part => part === "." || part === "..")) return "";
    if (!/^\/(?:|(?:explore|works|reader|scholars|topics|theories|theory-schools|subdisciplines|concepts|recommendations|help|about)(?:\/[^?#]*)?)$/.test(path)) return "";
    const pages = query.split("&").filter(part => part.split("=", 1)[0] === "page");
    const page = /^\/reader\/[0-9a-f-]+\/?$/i.test(path) && pages.length === 1 ? pages[0].slice(5) : "";
    return path + (page && /^[1-9]\d{0,5}$/.test(page) ? `?page=${page}` : "");
  } catch { return ""; }
}

export async function submitPublicFeedback(input: FeedbackInput, signal: AbortSignal): Promise<FeedbackReceipt> {
  const session = new AbortController(), unsubscribe = subscribeToSessionChanges(() => session.abort());
  try {
    const result = await apiRequest<FeedbackReceipt>("/catalog/feedback/", { method: "POST", cache: "no-store", body: JSON.stringify(input),
      signal: AbortSignal.any([signal, session.signal, AbortSignal.timeout(30000)]) }, null, false);
    if (signal.aborted || session.signal.aborted) throw new Error("会话已变化，未显示前次提交结果。");
    if (result.request_id !== input.request_id || !result.id || !["submitted", "reviewing", "resolved"].includes(result.status) || !Number.isFinite(Date.parse(result.created_at))) {
      throw new Error("提交结果尚未确认，请使用原请求重试。输入仍保留。");
    }
    return result;
  } finally { unsubscribe(); }
}
