import { redirect } from "next/navigation";
import { serverRequest, ServerApiError } from "./api/server-request";

/** Check the real session before rendering reader tools or starting a query. */
export async function requireReaderSession(path: string, params: Record<string, string | string[] | undefined> = {}) {
  try {
    await serverRequest("/auth/me/", { forwardSession: true });
  } catch (error) {
    if (!(error instanceof ServerApiError) || error.status !== 401) throw error;
    const query = new URLSearchParams();
    for (const [key, values] of Object.entries(params)) {
      for (const value of Array.isArray(values) ? values : values === undefined ? [] : [values]) query.append(key, value);
    }
    const next = path + (query.size ? `?${query}` : "");
    redirect(`/login?next=${encodeURIComponent(next)}`);
  }
}
