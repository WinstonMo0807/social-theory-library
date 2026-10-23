"use client";
import { useEffect } from "react";
import Link from "next/link";
import { LocalServices } from "./local-services";

/** Browser fragments cannot reach the server: preserve the exact old section here. */
export function LegacySettingsRoute() {
  useEffect(() => {
    const source = new URL(window.location.href);
    const section = source.hash.slice(1);
    if (!section) return;
    const normalized = section === "ai-runtime" ? "ai" : section;
    const target = normalized === "backups" ? "/admin/backups" : normalized === "public-display" ? "/admin/about" : ["ocr", "ai", "search", "prompts", "submissions"].includes(normalized) ? "/admin/processing/settings" : "";
    if (target) window.location.replace(`${target}${source.search}#${normalized}`);
  }, []);
  return <><LocalServices /><nav aria-label="其他运行设置"><Link href="/admin/about">网站与关于书库</Link> · <Link href="/admin/backups">备份</Link> · <Link href="/admin/processing/settings">处理服务设置</Link></nav></>;
}
