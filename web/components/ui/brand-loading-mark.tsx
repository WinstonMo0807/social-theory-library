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
    <svg className={styles.canvas} viewBox="0 0 256 224" focusable="false">
      <rect className={styles.frame} x="3" y="3" width="250" height="218" rx="4" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <g className={styles.symbol}><svg x="25" y="23" width="206" height="157" viewBox="12 17 230 154"><use href="/brand/stl-symbol-20261027.svg#mark" /></svg></g>
      <g className={styles.lines} strokeWidth="3" strokeLinecap="round"><path className={styles.ink} d="M 25 204 H 119" /><path className={styles.gold} d="M 137 204 H 231" /></g>
      <path className={styles.bookmark} d="M 46 3 H 77 V 38 L 61.5 29 L 46 38 Z" />
    </svg>
  </span>;
}
