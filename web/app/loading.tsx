import { LoadingState } from "@/components/ui/loading-state";
import { pickBrandLoadingVariant } from "@/lib/brand-loading";

export default function Loading() {
  return (
    <section className="route-loading" aria-live="polite" aria-busy="true">
      <LoadingState variant="screen" motionVariant={pickBrandLoadingVariant()}>正在载入内容…</LoadingState>
    </section>
  );
}
