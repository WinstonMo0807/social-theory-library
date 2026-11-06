"use client";

import { useEffect, useState } from "react";
import { GuestTransferProvider, GuestTransferChoice } from "./auth-guest-records";
import { AuthReturnCard } from "./auth-return-card";
import { AccountRecoveryAppeal } from "./account-recovery-appeal";
import { AccountEmailLink } from "./account-email-link";
import Link from "next/link";
import { ArrowRight, Bookmark, Clock3, FolderInput, LockKeyhole, NotebookPen, Users } from "lucide-react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { AuthForm, type AuthMode } from "./auth-form";
import { safeAuthDestination } from "@/lib/auth-navigation";

export function AuthReturnContext({ destination, recovery=false, compact=false }: { destination: string; recovery?:boolean; compact?:boolean }) {
  return <aside className="auth-context" data-recovery={recovery||undefined} data-compact={compact||undefined}><section><h2>{recovery?"即将返回的任务":"登录后，你将返回"}</h2><AuthReturnCard key={destination} destination={destination} /></section>
    <section className="auth-research-benefits"><h3>保留你的研究内容</h3><p>登录后可以在不同设备继续查看已保存的资料。</p><div className="auth-benefits"><span><Bookmark size={24} /><strong>书签</strong></span><span><NotebookPen size={24} /><strong>笔记</strong></span><span><Clock3 size={24} /><strong>阅读历史</strong></span></div></section>
    <GuestTransferChoice recovery={recovery} />
    {recovery?<p className="auth-private-note"><LockKeyhole size={17}/><span><strong>安全提示</strong>我们会向您的注册邮箱发送重置链接，链接24小时内有效。若长时间未收到，请检查垃圾邮件或稍后重试。</span></p>:null}
  </aside>;
}

function RecoveryEntry({ destination }: { destination: string }) {
  const [kind, setKind] = useState<"loading" | "link" | "request">("loading");
  useEffect(() => { queueMicrotask(() => setKind(new URLSearchParams(window.location.hash.slice(1)).has("token") ? "link" : "request")); }, []);
  return kind === "loading" ? <p role="status">正在准备恢复入口…</p> : kind === "link" ? <AccountEmailLink purpose="password" destination={destination} /> : <AuthForm mode="reset" next={destination} />;
}

export function AuthPageFrame({ mode }: { mode: AuthMode }) {
  const params = useSearchParams();
  const destination = safeAuthDestination(params.get("next"));
  const title = mode === "login" ? "登录" : mode === "register" ? "创建账户" : "登录、注册与账户恢复";
  const intro = mode === "login" ? "登录后可继续您上次的研究与阅读，保存书签、笔记与个人资料。" : mode === "register" ? "加入社会理论书库，保存你的阅读、笔记与研究，并在不同设备间同步。" : "进入私人保存能力，并返回原先的研究或阅读任务。";
  return <GuestTransferProvider><div className="auth-atlas-page" data-mode={mode}><nav className="auth-breadcrumb" aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><span>{mode === "reset" ? "找回账户" : title}</span></nav><header className="auth-heading"><h1>{title}</h1><p>{intro}</p>{mode==="register"?<div className="auth-existing">已有账户？<Link href={`/login?${new URLSearchParams({next:destination})}`}>登录</Link></div>:null}</header>
    <div className="auth-atlas-columns">{mode === "reset" ? <aside className="auth-recovery-benefits"><h2>登录后，你可以</h2><p><Bookmark size={24} /><span><strong>保存与同步</strong>收藏文献、书签与笔记。</span></p><p><Clock3 size={24} /><span><strong>继续上次的研究</strong>返回原先的研究或阅读任务。</span></p><p><FolderInput size={24} /><span><strong>本机记录转存</strong>登录后主动选择要保存的研究。</span></p><p><Users size={24} /><span><strong>一个账户的专属空间</strong>不同账户的研究与笔记独立。</span></p><hr /><h3>仍可继续匿名浏览</h3><p>可以浏览书库介绍、学者、理论流派、主题与特别策划。</p><Image unoptimized src="/brand/stl-auth-recovery-reading-final-r2.png" alt="" width={295} height={120}/><blockquote>保存思想的轨迹，<br/>是为了在更远的地方继续出发。</blockquote></aside> : null}<div className="auth-panel">{mode === "reset" ? <><RecoveryEntry destination={destination} /><AccountRecoveryAppeal /></> : <AuthForm key={mode} mode={mode} />}{mode==="register"?<div className="auth-existing auth-existing-mobile">已有账户？<Link href={`/login?${new URLSearchParams({next:destination})}`}>登录</Link></div>:null}</div>{mode === "register" ? <aside className="auth-registration-benefits"><Image src="/visual/stl4/account/registration-reading.png" alt="" width={464} height={275} priority /><div><h2>注册后，你可以</h2><p><Bookmark size={28} /><span><strong>保存与同步</strong>保存书签、笔记与阅读记录，在不同设备继续。</span></p><p><NotebookPen size={28} /><span><strong>个性化研究空间</strong>整理阅读清单与研究资料，保留原文位置。</span></p><p><Users size={28} /><span><strong>持续的学术资源</strong>关注来源、学者与主题的正式更新。</span></p><hr /><p><LockKeyhole size={28} /><span><strong>您的数据仅对您可见</strong>共享或授权使用由你明确决定。</span></p></div></aside> : <AuthReturnContext destination={destination} recovery={mode==="reset"} />}</div>
    <div className="auth-guest"><Link href="/home">继续以访客身份浏览 <ArrowRight size={15} /></Link><p>访客可浏览公开页面。阅读PDF、下载和检索请先登录。</p></div>
  </div></GuestTransferProvider>;
}
