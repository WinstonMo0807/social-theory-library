import Link from "next/link";

export type SearchMode = "exact" | "semantic" | "ask";

export function SearchModeSwitch({
  mode,
  query,
}: {
  mode: SearchMode;
  query: string;
}) {
  const encodedQuery = query ? `?q=${encodeURIComponent(query)}` : "";
  const originalQuery = query ? `&q=${encodeURIComponent(query)}` : "";
  return (
    <nav className="search-mode-switch" aria-label="检索方式">
      <Link className={mode === "exact" ? "active" : ""} href={`/explore/original?context=global${originalQuery}`}>
        <strong>原文检索</strong>
      </Link>
      <Link className={mode === "semantic" ? "active" : ""} href={`/explore/opinions${encodedQuery}`}>
        <strong>观点检索</strong>
      </Link>
      <Link className={mode === "ask" ? "active" : ""} href={`/explore/ask${encodedQuery}`}>
        <strong>向书库提问</strong>
      </Link>
    </nav>
  );
}
