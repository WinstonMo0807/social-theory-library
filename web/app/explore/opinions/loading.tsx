import { LoadingState } from "@/components/ui/loading-state";
export default function OpinionSearchLoading() {
  return <main className="page-shell semantic-loading-page"><LoadingState variant="rows">正在载入原文检索…</LoadingState></main>;
}
