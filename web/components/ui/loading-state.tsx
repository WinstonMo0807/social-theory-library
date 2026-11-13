import type { ComponentPropsWithoutRef } from "react";
import { BrandLoadingMark } from "./brand-loading-mark";
import styles from "./loading-state.module.css";

/** Real pending feedback, chosen by scope. No invented percentage or deadline. */
export function LoadingState({ children = "正在加载…", className = "", variant = "inline", ...props }: ComponentPropsWithoutRef<"p"> & { variant?: "brand" | "inline" | "rows" | "page" }) {
  return <p {...props} className={`stl-loading ${styles.feedback} ${className}`} data-loading={variant} role="status" aria-busy="true">
    {variant === "brand" || variant === "page" ? <BrandLoadingMark size={variant === "page" ? "large" : "small"} /> : null}
    {variant === "inline" ? <span className={styles.pulse} aria-hidden="true"><i /><i /><i /></span> : null}
    <span className="stl-loading-copy">{children}</span>
    {variant === "rows" ? <span className={styles.rows} aria-hidden="true">{[0,1,2].map(row => <span className={styles.row} key={row}><i /><span><b /><b /><b /></span></span>)}</span> : null}
  </p>;
}
