import Link from "next/link";
import { scopedSearchHref, type SearchContext } from "@/lib/search-context";

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
  if (totalPages <= 1) return null;
  return (
    <nav className="theory-timeline-pagination" aria-label="搜索结果分页">
      <Link
        aria-disabled={page <= 1}
        href={scopedSearchHref(path, context, { ...params, page: Math.max(1, page - 1) })}
      >上一页</Link>
      <span>第 {page} / {totalPages} 页</span>
      <Link
        aria-disabled={page >= totalPages}
        href={scopedSearchHref(path, context, { ...params, page: Math.min(totalPages, page + 1) })}
      >下一页</Link>
    </nav>
  );
}
