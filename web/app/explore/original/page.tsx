import type { Metadata } from "next";
import ExplorePage from "../page";

export const metadata: Metadata = { title: "原文检索" };

type SearchParams = Record<string, string | string[] | undefined>;

export default async function OriginalSearchPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  return <ExplorePage searchParams={Promise.resolve({ ...params, mode: "exact" })} />;
}
