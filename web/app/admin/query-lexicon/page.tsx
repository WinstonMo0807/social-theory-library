import type { Metadata } from "next";
import { QueryLexiconWorkspace } from "@/components/query-lexicon-workspace";

export const metadata: Metadata = { title: "QueryLexicon" };

export default function QueryLexiconPage() {
  return <QueryLexiconWorkspace />;
}
