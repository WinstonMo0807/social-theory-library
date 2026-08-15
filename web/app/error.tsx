"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="route-state-page" role="alert">
      <span className="eyebrow">页面暂时不可用</span>
      <h1>这部分内容没有正常载入</h1>
      <p>可以重新尝试。若问题持续出现，请返回探索页继续浏览。</p>
      {error.digest ? <small>错误编号 {error.digest}</small> : null}
      <div className="route-state-actions">
        <button className="button primary" type="button" onClick={reset}>
          <RefreshCw size={16} />重新载入
        </button>
        <Link className="button secondary" href="/explore">返回探索</Link>
      </div>
    </section>
  );
}
