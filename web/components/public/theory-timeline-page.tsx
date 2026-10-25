import Link from "next/link";
import { SiteFooter } from "@/components/site-footer";
import { ServerApiError } from "@/lib/api/server-request";
import { loadTimelineEvent, loadTimelinePage } from "@/lib/api/timeline.server";
import { timelineFilters, timelineHref, type TimelineEventDetail, type TimelinePage, type TimelineSearchParams } from "@/lib/api/timeline.types";
import { TheoryTimelineWorkspace, TimelineHero } from "./theory-timeline-workspace";
import styles from "./theory-timeline.module.css";

export async function TheoryTimelinePage({ searchParams, actionPath = "/theories/timeline", scope }: {
  searchParams: TimelineSearchParams; actionPath?: string; scope?: { slug: string; name: string; href: string };
}) {
  const filters = timelineFilters({ ...searchParams, ...(scope ? { node: scope.slug } : {}) });
  let page: TimelinePage;
  try {
    page = await loadTimelinePage(filters);
  } catch (error) {
    const invalid = error instanceof ServerApiError && [400, 404].includes(error.status);
    return <><div className={styles.page}><TimelineHero scope={scope} /><section className={styles.error} role="alert"><h2>{invalid ? "当前时间线条件无法使用" : "时间线暂时无法读取"}</h2><p>{invalid ? "所选事件、年份或页码已不在当前公开范围内，或筛选条件格式不正确。请调整条件后重新读取。" : "未能取得实际事件数据，请稍后重试。这里不会用示例内容填充。"}</p><Link href={timelineHref(actionPath, filters)}>重试当前条件</Link><Link href={timelineHref(actionPath, scope ? { node: scope.slug } : {})}>清空筛选</Link></section></div><SiteFooter reference="theory-timeline" /></>;
  }
  let selected: TimelineEventDetail | null = null, group: TimelinePage | null = null;
  let selectionError = "", groupError = "";
  const selectedId = page.focus_id || page.results[0]?.id;
  if (selectedId) {
    try {
      selected = await loadTimelineEvent(selectedId);
      if (!selected) selectionError = "所选事件当前已不可公开读取，请重新选择。";
    } catch { selectionError = "事件详情暂时无法读取，请重试。"; }
  }
  if (selected) {
    const year = String(selected.start_year ?? selected.end_year ?? "undated");
    if (filters.year === year && page.page === 1) group = page;
    else {
      try { group = await loadTimelinePage({ ...filters, focus: "", year, page: "1" }); }
      catch { groupError = "同年事件暂时无法读取，请重试。"; }
    }
  }
  return <><TheoryTimelineWorkspace key={JSON.stringify(filters)} page={page} selected={selected} selectionError={selectionError} group={group} groupError={groupError} filters={filters} actionPath={actionPath} scope={scope} /><SiteFooter reference="theory-timeline" /></>;
}
