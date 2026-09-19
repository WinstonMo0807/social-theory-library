"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { BookOpen } from "lucide-react";
import type { ReaderFailure } from "@/lib/api/reader-failure";

export function ReaderRouteFailure({ failure, returnPath }: { failure: ReaderFailure; returnPath: string }) {
  const router = useRouter();
  const [retrying, startRetry] = useTransition();
  return <main className="reader-route-error" data-reader-failure={failure.kind}>
    <BookOpen size={32} aria-hidden="true" />
    <h1>{failure.title}</h1><p role="status">{failure.detail}</p>
    {failure.retryable ? <button className="button" type="button" disabled={retrying} onClick={() => startRetry(() => router.refresh())}>{retrying ? "正在重新读取…" : "重试阅读请求"}</button> : null}
    {failure.canSignIn ? <Link className="button secondary" href={`/login?next=${encodeURIComponent(returnPath)}`}>登录并返回原阅读位置</Link> : null}
    <Link className="button secondary" href="/explore">返回馆藏检索</Link>
  </main>;
}
