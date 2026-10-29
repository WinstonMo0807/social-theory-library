"use client";

import { memo, useMemo } from "react";
import { formatSourceText } from "@/lib/source-text";

/** Retain the source prop unchanged; memoize only the visible, plain-text version. */
export const SourceText = memo(function SourceText({ text, original = false }: { text: string; original?: boolean }) {
  const formatted = useMemo(() => formatSourceText(text), [text]);
  return <span className="source-text" style={{ whiteSpace: "pre-wrap" }}>{original ? text : formatted}</span>;
});
