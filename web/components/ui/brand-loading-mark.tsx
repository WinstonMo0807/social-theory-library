"use client";

import { useEffect, useState } from "react";
import styles from "./brand-loading-mark.module.css";

/** A brand cue, never a percentage or an estimate of backend progress. */
export function BrandLoadingMark({ size = "small" }: { size?: "small" | "large" }) {
  const [variant, setVariant] = useState<string>();
  useEffect(() => { setVariant(["l5", "l6", "l7"][Math.floor(Math.random() * 3)]); }, []);
  return <span className={styles.mark} data-variant={variant} data-size={size} aria-hidden="true">
    <svg viewBox="12 17 230 154" focusable="false"><use href="/brand/stl-symbol-20261027.svg#mark" /></svg>
    <span className={styles.lines} /><span className={styles.bookmark} />
  </span>;
}
