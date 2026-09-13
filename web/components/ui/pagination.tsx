import Link from "next/link";
import type { ReactNode } from "react";

type PaginationProps = {
  page: number;
  totalPages: number;
  previousHref: string;
  nextHref: string;
  label?: string;
  className?: string;
  children?: ReactNode;
};

/** URL pagination retains normal navigation and does not own remote data. */
export function Pagination({ page, totalPages, previousHref, nextHref, label = "分页", className, children }: PaginationProps) {
  if (totalPages <= 1) return null;
  return <nav className={className} aria-label={label}>
    <Link aria-disabled={page <= 1} tabIndex={page <= 1 ? -1 : undefined} href={previousHref}>上一页</Link>
    <span aria-live="polite">{children ?? <>第 {page} / {totalPages} 页</>}</span>
    <Link aria-disabled={page >= totalPages} tabIndex={page >= totalPages ? -1 : undefined} href={nextHref}>下一页</Link>
  </nav>;
}
