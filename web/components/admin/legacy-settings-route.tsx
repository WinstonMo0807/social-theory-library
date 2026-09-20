"use client";
import { useEffect } from "react";
import Link from "next/link";

/** Browser fragments cannot reach the server: preserve the exact old section here. */
export function LegacySettingsRoute() {
  useEffect(() => {
    const source = new URL(window.location.href);
    const section = source.hash.slice(1);
    const target = section === "backups" ? "/admin/backups" : ["public-display", ""].includes(section) ? "/admin/about" : "/admin/processing/settings";
    window.location.replace(`${target}${source.search}${source.hash}`);
  }, []);
  return <div className="admin-panel"><h1>设置已归入对应工作页</h1><p>正在保留当前栏目并打开新位置。</p><Link href="/admin/about">网站与关于书库</Link> · <Link href="/admin/backups">备份</Link> · <Link href="/admin/processing/settings">处理服务设置</Link></div>;
}
