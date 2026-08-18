import Link from "next/link";
import { Sparkles } from "lucide-react";

export type AskLibraryContext =
  | "global"
  | "works"
  | "scholars"
  | "disciplines"
  | "subdisciplines"
  | "theories"
  | "topics"
  | "reading_paths";

export function askLibraryHref({
  context,
  ids = [],
  assetId,
  query,
}: {
  context: AskLibraryContext;
  ids?: Array<string | null | undefined>;
  assetId?: string | null;
  query?: string;
}) {
  const params = new URLSearchParams({ mode: "ask", context });
  for (const id of ids) {
    if (id) params.append("id", id);
  }
  if (assetId) params.set("asset_id", assetId);
  if (query?.trim()) params.set("q", query.trim());
  return `/explore?${params.toString()}`;
}

export function AskLibraryLink({
  context,
  ids,
  assetId,
  query,
  label = "询问书库",
  className = "button secondary",
}: {
  context: AskLibraryContext;
  ids?: Array<string | null | undefined>;
  assetId?: string | null;
  query?: string;
  label?: string;
  className?: string;
}) {
  return (
    <Link className={className} href={askLibraryHref({ context, ids, assetId, query })}>
      <Sparkles aria-hidden="true" size={16} />
      {label}
    </Link>
  );
}
