import type { Metadata } from "next";
import ExplorePage from "../page";

export const metadata: Metadata = { title: "向书库提问" };

type SearchParams = Record<string, string | string[] | undefined>;

export default async function AskLibraryRoute({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  return <ExplorePage searchParams={Promise.resolve({ ...params, mode: "ask" })} />;
}
