import { WorkLibrary } from "@/components/admin/library/work-library";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const rawQuery = params.q;
  const rawView = params.view;
  const query = Array.isArray(rawQuery) ? rawQuery[0] ?? "" : rawQuery ?? "";
  const view = Array.isArray(rawView) ? rawView[0] ?? "all" : rawView ?? "all";
  return <WorkLibrary initialQuery={query.trim()} initialView={view} />;
}
