"use client";

import Link from "next/link";

/** Keep both editors open; never silently replace a form with a newer token. */
export function EditorialConflictHelp({ href, visible }: { href: string; visible: boolean }) {
  if (!visible) return null;
  return <div className="form-message" role="status">
    <p>本页输入仍在。打开最新内容，对照后在新页面保存。</p>
    <Link className="button secondary" href={href} target="_blank" rel="noopener noreferrer">在新标签页查看最新内容</Link>
  </div>;
}
