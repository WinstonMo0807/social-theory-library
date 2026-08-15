import type { ReactNode } from "react";
import Link from "next/link";
import { ArchitecturalImage } from "./ui";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-page">
      <section className="auth-visual">
        <Link href="/" className="auth-wordmark"><span>SOCIAL</span><span>THEORY</span><span>LIBRARY</span></Link>
        <h2>把阅读留在页码上</h2>
        <p>查找原文，记录思想，并在任何设备上继续。</p>
        <ArchitecturalImage compact />
        <dl>
          <div><dt>访客开放</dt><dd>阅读、下载、复制、引用</dd></div>
          <div><dt>登录保存</dt><dd>批注、笔记、收藏、进度</dd></div>
        </dl>
      </section>
      <section className="auth-form-side">{children}</section>
    </div>
  );
}
