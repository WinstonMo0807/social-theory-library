import { scopedSearchHref, type SearchContext } from "@/lib/search-context";
import { Pagination } from "./ui/pagination";

export function ScopedSearchPagination({
  path,
  context,
  page,
  totalPages,
  params = {},
}: {
  path: string;
  context: SearchContext;
  page: number;
  totalPages: number;
  params?: Record<string, string | number | null | undefined>;
}) {
  return (
    <Pagination className="theory-timeline-pagination" label="搜索结果分页" page={page} totalPages={totalPages}
      previousHref={scopedSearchHref(path, context, { ...params, page: Math.max(1, page - 1) })}
      nextHref={scopedSearchHref(path, context, { ...params, page: Math.min(totalPages, page + 1) })}
    />
  );
}
