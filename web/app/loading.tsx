import { LoadingState } from "@/components/ui/loading-state";

export default function Loading() {
  return (
    <section className="route-loading" aria-live="polite" aria-busy="true">
      <LoadingState variant="screen">正在载入内容…</LoadingState>
    </section>
  );
}
