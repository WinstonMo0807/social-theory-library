"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { adminListHref, adminPageNumber } from "@/lib/admin-route-context";

export function useAdminListPage(key = "page") {
  const search = useSearchParams(), pathname = usePathname(), router = useRouter();
  const href = (page: number, filters: Record<string, string> = {}) => adminListHref(pathname, search.toString(), { ...filters, [key]: page });
  return { page: adminPageNumber(search.get(key)), href, reset: (filters: Record<string, string> = {}) => router.replace(href(1, filters), { scroll: false }) };
}

export function AdminListPages({ data, paging, loading, filters = {}, label = "资料列表分页" }: {
  data?: { count: number; next?: string | null; previous?: string | null } | null;
  paging: ReturnType<typeof useAdminListPage>; loading: boolean; filters?: Record<string, string>; label?: string;
}) {
  return <footer className="theory-admin-pagination" aria-busy={loading}>
    <span aria-live="polite">{data ? `共 ${data.count} 条` : loading ? "正在读取…" : "列表暂未读取成功"}</span>
    <nav aria-label={label}>
      {paging.page > 1 ? <Link scroll={false} href={paging.href(1, filters)}>第一页</Link> : null}
      {!loading && data?.previous ? <Link scroll={false} href={paging.href(paging.page - 1, filters)}>上一页</Link> : <span aria-disabled="true">上一页</span>}
      <span>第 {paging.page} 页</span>
      {!loading && data?.next ? <Link scroll={false} href={paging.href(paging.page + 1, filters)}>下一页</Link> : <span aria-disabled="true">下一页</span>}
    </nav>
  </footer>;
}
