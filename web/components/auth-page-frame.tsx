"use client";

import Link from "next/link";
import { ArrowRight, Bookmark, Clock3, FolderInput, LockKeyhole, NotebookPen, Users } from "lucide-react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { AuthForm, type AuthMode } from "./auth-form";
import { safeAuthDestination } from "@/lib/auth-navigation";

export function AuthReturnContext({ destination }: { destination: string }) {
  const path = safeAuthDestination(destination);
  const label = path.startsWith("/reader/") ? "原来的阅读位置" : path.startsWith("/account/research/") ? "原来的研究会话" : path.startsWith("/account") ? "你的读者中心" : path.startsWith("/admin") ? "原来的管理工作台" : "刚才浏览的页面";
  return <aside className="auth-context"><section><h2>登录后，你将返回</h2><Link className="auth-return-card" href={path}><Bookmark size={30} /><span><strong>{label}</strong><small>保留原页面与定位，权限由当前账户重新核对。</small></span><ArrowRight size={17} /></Link></section>
    <section><h3>保留你的研究内容</h3><p>登录后可以在不同设备继续查看已保存的资料。</p><div className="auth-benefits"><span><Bookmark size={24} /><strong>书签</strong><small>保存与同步</small></span><span><NotebookPen size={24} /><strong>笔记</strong><small>梳理与复习</small></span><span><Clock3 size={24} /><strong>阅读历史</strong><small>随时继续</small></span></div></section>
    <section><h3><FolderInput size={20} />本机研究记录</h3><p>登录后可在读者中心查看、选择并转存。只有你明确确认的记录才会上传，原记录保留。</p><small>本页不读取未登录设备上的私人草稿。</small></section>
    <p className="auth-private-note"><LockKeyhole size={17} />私人资料按账户保存，登录不会合并他人的数据。</p>
  </aside>;
}

export function AuthPageFrame({ mode }: { mode: AuthMode }) {
  const params = useSearchParams();
  const destination = safeAuthDestination(params.get("next"));
  const title = mode === "login" ? "登录" : mode === "register" ? "创建账户" : "登录、注册与账户恢复";
  const intro = mode === "login" ? "登录后可继续上次的研究与阅读，保存书签、笔记与个人资料。" : mode === "register" ? "加入社会理论书库，保存你的阅读、笔记与研究，并在不同设备间同步。" : "进入私人保存能力，并返回原先的研究或阅读任务。";
  return <div className="auth-atlas-page" data-mode={mode}><nav className="auth-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span>›</span><span>{mode === "reset" ? "找回账户" : title}</span></nav><header className="auth-heading"><h1>{title}</h1><p>{intro}</p></header>
    <div className="auth-atlas-columns">{mode === "reset" ? <aside className="auth-recovery-benefits"><h2>登录后，你可以</h2><p><Bookmark size={24} /><span><strong>保存与同步</strong>收藏文献、书签与笔记。</span></p><p><Clock3 size={24} /><span><strong>继续上次的研究</strong>返回原先的研究或阅读任务。</span></p><p><FolderInput size={24} /><span><strong>本机记录转存</strong>登录后主动选择要保存的研究。</span></p><p><Users size={24} /><span><strong>一个账户的专属空间</strong>不同账户的研究与笔记独立。</span></p><hr /><h3>仍可继续匿名浏览</h3><p>公开检索、阅读、下载、复制和引用保持开放。</p><Image src="/visual/stl4/account/registration-reading.png" alt="" width={464} height={275} /></aside> : null}<div className="auth-panel"><AuthForm key={mode} mode={mode} /></div>{mode === "register" ? <aside className="auth-registration-benefits"><Image src="/visual/stl4/account/registration-reading.png" alt="" width={464} height={275} priority /><div><h2>注册后，你可以</h2><p><Bookmark size={28} /><span><strong>保存与同步</strong>保存书签、笔记与阅读记录，在不同设备继续。</span></p><p><NotebookPen size={28} /><span><strong>个人研究空间</strong>整理阅读清单与研究资料，保留原文位置。</span></p><p><Users size={28} /><span><strong>持续的学术探索</strong>关注来源、学者与主题的正式更新。</span></p><hr /><p><LockKeyhole size={28} /><span><strong>私人资料按账户保存</strong>共享或授权使用由你明确决定。</span></p></div></aside> : <AuthReturnContext destination={destination} />}</div>
    <div className="auth-guest"><Link href="/explore">继续以访客身份浏览 <ArrowRight size={15} /></Link><p>公开检索、阅读、下载、复制和引用仍然开放。</p></div>
  </div>;
}
