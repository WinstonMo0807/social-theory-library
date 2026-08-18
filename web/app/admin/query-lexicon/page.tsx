import type { Metadata } from "next";
import { QueryLexiconWorkspace } from "@/components/query-lexicon-workspace";

export const metadata: Metadata = { title: "QueryLexicon 词典" };

export default function QueryLexiconPage() {
  return <QueryLexiconWorkspace />;
}
