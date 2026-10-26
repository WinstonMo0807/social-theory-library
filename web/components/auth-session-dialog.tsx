"use client";

import Link from "next/link";
import { ArrowRight, Clock3, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { AccountRecoveryAppeal } from "./account-recovery-appeal";
import { AuthForm, type AuthMode } from "./auth-form";
import { AuthReturnContext } from "./auth-page-frame";
import { Dialog } from "./ui/dialog";
import { safeAuthDestination } from "@/lib/auth-navigation";

type Prompt = { destination: string; expired: boolean; route: string };

export function AuthSessionDialog() {
  const pathname = usePathname();
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [formGuard, setFormGuard] = useState(false), [appealGuard, setAppealGuard] = useState(false);
  const [mode, setMode] = useState<AuthMode>("login");
  const available = !/^\/(login|register|reset-password|verify-email|activate|admin|account)(\/|$)/.test(pathname);
  useEffect(() => {
    if (!available) return;
    const open = (destination: string, expired: boolean) => {
      setMode("login"); setPrompt(previous => previous?.route === pathname ? previous : { destination, expired, route: pathname });
    };
    const expired = () => open(safeAuthDestination(`${location.pathname}${location.search}${location.hash}`, "/explore"), true);
    const click = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download") || anchor.hasAttribute("data-auth-full-page")) return;
      const url = new URL(anchor.href, location.href);
      if (url.origin !== location.origin || url.pathname !== "/login") return;
      event.preventDefault();
      open(safeAuthDestination(url.searchParams.get("next"), `${location.pathname}${location.search}${location.hash}`), false);
    };
    window.addEventListener("stl:auth-required", expired);
    window.addEventListener("click", click, true);
    return () => { window.removeEventListener("stl:auth-required", expired); window.removeEventListener("click", click, true); };
  }, [available, pathname]);
  if (!available || !prompt || prompt.route !== pathname) return null;
  const mayLeave = () => !(formGuard || appealGuard) || window.confirm("当前有输入或尚未确认的提交结果。关闭会放弃本页输入，已提交操作可能仍在继续。确定离开吗？");
  const close = () => { if (mayLeave()) setPrompt(null); };
  const changeMode = (value: AuthMode) => { if (mayLeave()) setMode(value); };
  return <Dialog open onRequestClose={close} className="auth-session-dialog" aria-labelledby="auth-session-title"><header className="auth-session-heading"><Clock3 size={30} /><div><h2 id="auth-session-title">{prompt.expired ? "会话已过期" : "登录后继续"}</h2><p>{prompt.expired ? "为保护您的账户安全，请重新登录以继续您的研究与阅读。" : "保存私人资料，并在不同设备继续。"}</p><small>登录后返回原页面；本机记录仍由你选择是否转存。</small></div><button onClick={close} aria-label="关闭登录"><X size={20} /></button></header><div className="auth-atlas-columns"><div className="auth-panel"><AuthForm key={mode} mode={mode} next={prompt.destination} onModeChange={changeMode} onGuardChange={setFormGuard} onSuccess={destination => window.location.assign(destination)} />{mode === "reset" ? <AccountRecoveryAppeal onGuardChange={setAppealGuard} /> : null}</div><AuthReturnContext destination={prompt.destination} compact /></div><footer className="auth-guest"><button onClick={close}>继续以访客身份浏览 <ArrowRight size={16} /></button><p>你仍可检索、阅读和下载公开内容，登录后可保存个人资料。</p><Link data-auth-full-page href={`/login?${new URLSearchParams({ next: prompt.destination })}`}>打开完整登录页面</Link></footer></Dialog>;
}
