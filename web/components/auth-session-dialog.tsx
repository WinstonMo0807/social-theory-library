"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AccountRecoveryAppeal } from "./account-recovery-appeal";
import { GuestTransferChoice, GuestTransferProvider } from "./auth-guest-records";
import { AuthForm, type AuthMode } from "./auth-form";
import { AuthBenefitsDemo } from "./auth-benefits-demo";
import { usePublicSession } from "./public-session-provider";
import { Dialog } from "./ui/dialog";
import { safeAuthDestination } from "@/lib/auth-navigation";
import styles from "./auth-session-dialog.module.css";

type Prompt = { destination: string; expired: boolean; route: string };
const INVITATION_SEEN = "stl:library-invitation:v1";
const NOTICE_SEEN = "stl:library-trial-notice:20261107";
const ENTRY_PENDING = "stl:library-entry-pending";
const NOTICE_PENDING = "stl:library-notice-pending";
// Only presentation preferences; never authentication or permission decisions.
const memory = new Map<string, string>();
function read(key: string, persistent = false) {
  try { return (persistent ? localStorage : sessionStorage).getItem(key) || memory.get(key); }
  catch { return memory.get(key); }
}
function write(key: string, value: string, persistent = false) {
  memory.set(key, value);
  try { (persistent ? localStorage : sessionStorage).setItem(key, value); } catch { /* Browsing remains available when storage is disabled. */ }
}

export function AuthSessionDialog() {
  const pathname = usePathname();
  const { state: session } = usePublicSession();
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [noticeRoute, setNoticeRoute] = useState<string | null>(null);
  const [formGuard, setFormGuard] = useState(false), [appealGuard, setAppealGuard] = useState(false);
  const [mode, setMode] = useState<AuthMode>("login");
  const heading = useRef<HTMLHeadingElement>(null);
  const welcome = pathname === "/" || pathname === "/welcome";
  const available = !welcome && !/^\/(login|register|reset-password|verify-email|activate|admin|account)(\/|$)/.test(pathname);

  function queueNotice() {
    if (read(NOTICE_SEEN, true) !== "1") write(NOTICE_PENDING, "1");
  }
  function showNotice() {
    write(NOTICE_PENDING, "0");
    if (read(NOTICE_SEEN, true) === "1") return;
    write(NOTICE_SEEN, "1", true);
    setNoticeRoute(pathname);
  }
  function open(destination: string, expired: boolean) {
    write(INVITATION_SEEN, "1", true);
    setNoticeRoute(null);
    setMode("login");
    setPrompt(previous => previous?.route === pathname ? previous : { destination, expired, route: pathname });
  }

  useEffect(() => {
    const expired = () => {
      // Background session checks must never interrupt either landing page.
      if (available && pathname !== "/home") open(safeAuthDestination(`${location.pathname}${location.search}${location.hash}`, "/home"), true);
    };
    const click = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
      const url = new URL(anchor.href, location.href);
      if (url.origin !== location.origin) return;
      if (welcome && anchor.hasAttribute("data-library-entry") && url.pathname === "/home") {
        write(ENTRY_PENDING, "1");
        return;
      }
      if (!available || anchor.hasAttribute("data-auth-full-page") || url.pathname !== "/login") return;
      event.preventDefault();
      open(safeAuthDestination(url.searchParams.get("next"), `${location.pathname}${location.search}${location.hash}`), false);
    };
    window.addEventListener("stl:auth-required", expired);
    window.addEventListener("click", click, true);
    return () => { window.removeEventListener("stl:auth-required", expired); window.removeEventListener("click", click, true); };
  }, [available, pathname, welcome]);

  useEffect(() => {
    if (!available || prompt?.route === pathname || noticeRoute === pathname) return;
    if (pathname === "/home" && read(ENTRY_PENDING) === "1") {
      if (["loading", "unknown"].includes(session.status)) return;
      write(ENTRY_PENDING, "0");
      if (session.status === "unauthenticated" && read(INVITATION_SEEN, true) !== "1") {
        open("/home", false);
        return;
      }
      // Authenticated readers bypass the invitation; service errors are not logout.
      showNotice();
    } else if (read(NOTICE_PENDING) === "1") showNotice();
  }, [available, pathname, session.status, prompt, noticeRoute]);

  if (!available) return null;
  if (noticeRoute === pathname) return <Dialog open onRequestClose={() => setNoticeRoute(null)} className={`${styles.dialog} ${styles.notice}`} aria-labelledby="library-trial-title" initialFocusRef={heading}>
    <button className={styles.close} onClick={() => setNoticeRoute(null)} aria-label="关闭试用说明"><X size={20} /></button>
    <BookOpen className={styles.noticeMark} size={32} strokeWidth={1.4} aria-hidden="true" />
    <h2 id="library-trial-title" ref={heading} tabIndex={-1}>欢迎试读 STL 书库</h2>
    <p>目前的策展均为测试示例，后续正式策展将重新编排。</p>
    <p>现有 <strong>57 本书</strong>已进入内容策划与观点检索，欢迎尝试。</p>
    <button className={styles.noticeContinue} onClick={() => setNoticeRoute(null)}>知道了，开始浏览 <ArrowRight size={18} /></button>
  </Dialog>;
  if (!prompt || prompt.route !== pathname) return null;
  const mayLeave = () => !(formGuard || appealGuard) || window.confirm("当前有输入或尚未确认的提交结果。关闭会放弃本页输入，已提交操作可能仍在继续。确定离开吗？");
  const close = () => { if (mayLeave()) { setPrompt(null); setFormGuard(false); setAppealGuard(false); showNotice(); } };
  const changeMode = (value: AuthMode) => { if (mayLeave()) { setMode(value); setFormGuard(false); setAppealGuard(false); } };
  return <GuestTransferProvider><Dialog open onRequestClose={close} className={`auth-session-dialog ${styles.dialog}`} aria-labelledby="auth-session-title" initialFocusRef={heading}>
    <header className={styles.heading}><div><h2 id="auth-session-title" ref={heading} tabIndex={-1}>从阅读，走向自己的研究</h2><p>{prompt.expired ? "登录状态已失效，重新登录后即可继续。" : "登录或免费注册，开始阅读与检索。"}</p></div><button className={styles.close} onClick={close} aria-label="暂不登录，关闭邀请"><X size={20} /></button></header>
    <div className={styles.columns}><div className={`auth-panel ${styles.form}`}>
      <AuthForm key={mode} mode={mode} next={prompt.destination} onModeChange={changeMode} onGuardChange={setFormGuard} onSuccess={destination => { queueNotice(); window.location.assign(destination); }} />
      <button className={styles.skip} onClick={close}>暂不登录，先看看 <ArrowRight size={17} /></button>
      <GuestTransferChoice compact />
      {mode === "reset" ? <AccountRecoveryAppeal onGuardChange={setAppealGuard} /> : null}
    </div><AuthBenefitsDemo /></div>
    <footer className={styles.footer}><span>访客可浏览公开页面，阅读 PDF、下载和检索需登录。</span><Link data-auth-full-page onClick={queueNotice} href={`/login?${new URLSearchParams({ next: prompt.destination })}`}>完整登录页</Link></footer>
  </Dialog></GuestTransferProvider>;
}
