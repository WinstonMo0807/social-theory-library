import type { Metadata } from "next";
import { TheoryDirectory } from "@/components/theory/theory-directory";
import { loadTheoryDirectory, loadTheoryDirectorySelection } from "@/lib/api/theory-directory.server";
import { theoryDirectoryKinds, type TheoryDirectoryFailure, type TheoryDirectoryFilters, type TheoryDirectoryKind, type TheoryDirectorySelectionState } from "@/lib/api/theory-directory.types";
import { ServerApiError } from "@/lib/api/server-request";
import { searchPage } from "@/lib/search-context";

export const metadata: Metadata = { title: "理论目录", description: "按真实学科、条目层级与理论关系查找已公开资料。" };
const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value)?.trim() || "";

export default async function TheoryDirectoryPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const requestedKind = first(params.type);
  const filters: TheoryDirectoryFilters = {
    type: theoryDirectoryKinds.includes(requestedKind as TheoryDirectoryKind) ? requestedKind as TheoryDirectoryKind : "theory_tradition",
    discipline: first(params.discipline), parent: first(params.parent), q: first(params.q),
    selected: first(params.selected), page: searchPage(params.page),
  };
  const [directoryResult, selectionResult] = await Promise.allSettled([
    loadTheoryDirectory(filters),
    filters.selected ? loadTheoryDirectorySelection(filters.type, filters.selected) : Promise.resolve(null),
  ]);
  const directory = directoryResult.status === "fulfilled" ? directoryResult.value : null;
  let failure: TheoryDirectoryFailure = null;
  if (directoryResult.status === "rejected") {
    const error = directoryResult.reason;
    failure = error instanceof ServerApiError && error.status === 404 ? "unavailable"
      : error instanceof ServerApiError && error.status === 400 ? "invalid" : "error";
  }
  const selection: TheoryDirectorySelectionState = !filters.selected ? { status: "none" }
    : selectionResult.status === "rejected" ? { status: "error" }
      : selectionResult.value ? { status: "available", data: selectionResult.value } : { status: "unavailable" };
  return <TheoryDirectory directory={directory} failure={failure} filters={filters} selection={selection} />;
}
