import { serverRequest, ServerApiError } from "./server-request";
import { timelineFilterKeys, type TimelineEventDetail, type TimelineFilters, type TimelinePage } from "./timeline.types";

export function loadTimelinePage(filters: TimelineFilters): Promise<TimelinePage> {
  const query = new URLSearchParams();
  for (const key of timelineFilterKeys) if (filters[key]) query.set(key, filters[key]);
  return serverRequest<TimelinePage>(`/catalog/theory-system/timeline/${query.size ? `?${query}` : ""}`, { forwardSession: true });
}

export async function loadTimelineEvent(id: string): Promise<TimelineEventDetail | null> {
  try {
    return await serverRequest<TimelineEventDetail>(`/catalog/theory-system/timeline/${encodeURIComponent(id)}/`, { forwardSession: true });
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) return null;
    throw error;
  }
}
