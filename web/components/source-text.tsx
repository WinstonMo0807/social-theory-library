"use client";

import { memo, useMemo } from "react";
import { formatSourceText } from "@/lib/source-text";
import styles from "./source-text.module.css";

/** Retain the source prop unchanged; memoize only the visible, plain-text version. */
export const SourceText = memo(function SourceText({ text, original = false, compact = false }: { text: string; original?: boolean; compact?: boolean }) {
  const formatted = useMemo(() => formatSourceText(text), [text]);
  return <span className={`source-text ${styles.text}`} data-compact={compact || undefined}>{original ? text : formatted}</span>;
});
