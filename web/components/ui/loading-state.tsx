import type { ComponentPropsWithoutRef } from "react";
import { BrandLoadingMark } from "./brand-loading-mark";
import styles from "./loading-state.module.css";
import type { BrandLoadingVariant } from "@/lib/brand-loading";

/** Real pending feedback, chosen by scope. No invented percentage or deadline. */
export function LoadingState({ children = "正在加载…", className = "", variant = "brand", motionVariant, ...props }: ComponentPropsWithoutRef<"p"> & { variant?: "screen" | "brand" | "compact" | "inline" | "rows" | "page"; motionVariant?: BrandLoadingVariant }) {
  return <p {...props} className={`stl-loading ${styles.feedback} ${className}`} data-loading={variant} role="status" aria-busy="true">
    {variant !== "inline" ? <span className={styles.identity}>
      <BrandLoadingMark initialVariant={motionVariant} size={variant === "screen" || variant === "page" ? "hero" : variant === "compact" ? "small" : "large"} />
      {variant === "screen" ? <span className={styles.wordmark}><span>Social Theory Library</span><strong>社会理论书库</strong></span> : null}
    </span> : null}
    {variant === "inline" ? <span className={styles.pulse} aria-hidden="true"><i /><i /><i /></span> : null}
    <span className="stl-loading-copy">{children}</span>
    {variant === "rows" ? <span className={styles.rows} aria-hidden="true">{[0,1,2].map(row => <span className={styles.row} key={row}><i /><span><b /><b /><b /></span></span>)}</span> : null}
  </p>;
}
