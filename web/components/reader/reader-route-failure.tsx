"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { BookOpen } from "lucide-react";
import { bootstrapSession } from "@/lib/session";
import { SiteHeader } from "../site-header";
import type { SiteConfig } from "@/lib/site-config";
import type { ReaderFailure } from "@/lib/api/reader-failure";

export function ReaderRouteFailure({ failure, returnPath, siteConfig }: { failure: ReaderFailure; returnPath: string; siteConfig?: SiteConfig }) {
  const router = useRouter();
  const [retrying, startRetry] = useTransition();
  return <><SiteHeader reader config={siteConfig} /><section className="reader-route-error" data-reader-failure={failure.kind}>
    <BookOpen size={32} aria-hidden="true" />
    <h1>{failure.title}</h1><p role="status">{failure.detail}</p>
    {failure.retryable ? <button className="button" type="button" disabled={retrying} onClick={() => startRetry(async () => { await bootstrapSession(); router.refresh(); })}>{retrying ? "正在重新读取…" : "重试阅读请求"}</button> : null}
    {failure.canSignIn ? <Link className="button secondary" href={`/login?next=${encodeURIComponent(returnPath)}`}>登录并返回原阅读位置</Link> : null}
    <Link className="button secondary" href="/account?section=notes">查看我的笔记</Link>
    <Link className="button secondary" href="/explore">返回馆藏检索</Link>
  </section></>;
}
