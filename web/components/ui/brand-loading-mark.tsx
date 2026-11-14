"use client";

import { useEffect, useState } from "react";
import { pickBrandLoadingVariant, type BrandLoadingVariant } from "@/lib/brand-loading";
import styles from "./brand-loading-mark.module.css";

/** A brand cue, never a percentage or an estimate of backend progress. */
export function BrandLoadingMark({ size = "small", initialVariant }: { size?: "small" | "large" | "hero"; initialVariant?: BrandLoadingVariant }) {
  // Server-rendered waits animate before hydration; each mount chooses only once.
  const [variant, setVariant] = useState<BrandLoadingVariant>(initialVariant ?? "l5");
  useEffect(() => { if (!initialVariant) setVariant(pickBrandLoadingVariant()); }, [initialVariant]);
  return <span className={styles.mark} data-variant={variant} data-size={size} aria-hidden="true">
    {variant === "j" || variant === "k" ? <span className={styles.paper}>
      {variant === "j" ? <><span className={styles.leftPage} /><span className={styles.rightPage} /><span className={styles.spine} /></> : null}
      <span className={styles.reveal}><svg viewBox="12 17 230 154" focusable="false"><use href="/brand/stl-symbol-20261027.svg#mark" /></svg></span>
      {variant === "k" ? <span className={styles.rule} /> : null}
    </span> : <svg className={styles.canvas} viewBox="0 0 256 224" focusable="false">
      <g className={styles.symbol}><svg x="25" y="23" width="206" height="157" viewBox="12 17 230 154"><use href="/brand/stl-symbol-20261027.svg#mark" /></svg></g>
      <g className={styles.lines} strokeWidth="3" strokeLinecap="round"><path className={styles.ink} d="M 25 204 H 119" /><path className={styles.gold} d="M 137 204 H 231" /></g>
    </svg>}
  </span>;
}
