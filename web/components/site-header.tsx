"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  ArrowLeft,
  ChevronRight,
  CircleHelp,
  CircleUserRound,
  LogOut,
  Menu,
  Search,
  Settings,
  UserPlus,
  X,
} from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { logoutCurrentSession } from "@/lib/api";
import { defaultSiteConfig, type SiteConfig } from "@/lib/site-config";
import { useActionGuard } from "@/lib/use-action-guard";
import { usePublicNavigationReturn } from "@/lib/public-navigation-return";
import { ActionButton, AsyncStatus } from "./action-feedback";
import { DisplayPreferences } from "./display-preferences";
import { ThemeToggle } from "./theme-toggle";
import { usePublicSession } from "./public-session-provider";
import { Drawer } from "./ui/dialog";
import { IconButton } from "./ui/controls";

export function LibraryMark({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={`brand-mark ${className}`.trim()}
      focusable="false"
      viewBox="0 0 40 32"
      role="img"
    >
      <path d="M3 7.5c5.4-.9 10.2.3 15.7 3.8v15.2C13.3 23.3 8.2 22.2 3 23.3V7.5Z" fill="currentColor" />
      <path d="M37 7.5c-5.4-.9-10.2.3-15.7 3.8v15.2c5.4-3.2 10.5-4.3 15.7-3.2V7.5Z" fill="currentColor" />
      <path d="M20 10.6v16.3" fill="none" stroke="var(--brand-mark-accent, #c9a96a)" strokeLinecap="round" strokeWidth="1.8" />
      <circle cx="11" cy="5.2" r="2.3" fill="var(--brand-mark-accent, #c9a96a)" />
      <circle cx="29" cy="5.2" r="2.3" fill="var(--brand-mark-accent, #c9a96a)" />
      <path d="M6.2 10.1c1.4-1.2 3-1.8 4.8-1.8s3.4.6 4.8 1.8M24.2 10.1c1.4-1.2 3-1.8 4.8-1.8s3.4.6 4.8 1.8" fill="none" stroke="var(--brand-mark-accent, #c9a96a)" strokeLinecap="round" strokeWidth="1.5" />
    </svg>
  );
}

export function Wordmark({ config = defaultSiteConfig }: { config?: SiteConfig }) {
  return (
    <span className="brand-lockup" aria-label={config.site_name}>
      <LibraryMark />
      <span className="brand-type" aria-hidden="true"><span className="wordmark">
        {config.wordmark_lines.map((line) => (
          <span key={line}>{line}</span>
        ))}
      </span><span className="brand-name">{config.site_name}</span></span>
    </span>
  );
}

export function SiteHeader({ config = defaultSiteConfig, preview = false, reader = false, beforeLogout }: { config?: SiteConfig; preview?: boolean; reader?: boolean; beforeLogout?: () => boolean }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const exploreRoute = pathname === "/explore" || pathname.startsWith("/explore/");
  const [open, setOpen] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const { state: session } = usePublicSession();
  const user = session.status === "authenticated" && session.user ? session.user : null;
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const navigationReturn = usePublicNavigationReturn(`${pathname}${searchParams.size ? `?${searchParams}` : ""}`, menuButtonRef);
  const [menuSearch, setMenuSearch] = useState("");
  const isActive = (href: string) => href === "/" ? pathname === "/"
    : href === "/theories" ? /^\/(theories|theory-schools)(\/|$)/.test(pathname)
    : pathname === href || pathname.startsWith(`${href}/`);
  const navigation = [
    ["/", config.navigation.home],
    ["/explore", config.navigation.explore],
    ["/theories", config.navigation.theory_schools],
    ["/scholars", config.navigation.scholars],
    ["/topics", config.navigation.topics],
    ["/recommendations", "特别策划"],
  ] as const;
  const readerCenterRoute = pathname === "/account" && !preview;
  const headerNavigation = readerCenterRoute ? [
    ["/account/research", "我的研究"], ["/account/notes", "笔记"], ["/account/plans", "阅读计划"],
    ["/account/collections", "书单"], ["/account/citation-audits", "引文体检"], ["/account/confirmed-notes", "已确认笔记"],
  ] : navigation;

  useEffect(() => {
    document.body.classList.toggle("menu-open", open);
    return () => document.body.classList.remove("menu-open");
  }, [open]);

  function closeMenu() {
    setOpen(false);
  }

  function enterAccount(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    navigationReturn.remember();
    closeMenu();
  }

  async function logout() {
    if (beforeLogout && !beforeLogout()) return;
    const actionKey = "logout";
    if (!startAction(actionKey)) return;
    setLogoutError("");
    try {
      await logoutCurrentSession(user ? String(user.id) : undefined);
      closeMenu();
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : "退出登录失败，请重试。");
    } finally {
      finishAction(actionKey);
    }
  }

  if (!preview && ((pathname.startsWith("/reader/") && !reader) || pathname.startsWith("/admin"))) {
    return null;
  }

  return (
    <header
      data-edit-section={preview ? "brand" : undefined}
      data-stl-home={pathname === "/" || preview ? "true" : undefined}
      data-stl-account={readerCenterRoute ? "true" : undefined}
      className={exploreRoute ? "site-header" : "site-header site-header--editorial"}
      data-ui-scope={exploreRoute ? "explore-frozen" : "editorial-v2"}
    >
      <Link className="logo-link" href="/" prefetch={false}>
        <Wordmark config={config} />
      </Link>
      <nav className="desktop-nav" aria-label="主导航">
        {headerNavigation.map(([href, label]) => {
          const active = href.includes("?") ? `${pathname}?${searchParams}` === href : isActive(href);
          return (
            <Link
              aria-current={active ? "page" : undefined}
              className={active ? "active" : ""}
              href={href}
              key={href}
              prefetch={false}
            >
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="header-actions">
        {pathname.startsWith("/account") && navigationReturn.source ? <Link className="header-return" href={navigationReturn.source.href} prefetch={false} scroll={false} onClick={navigationReturn.requestReturn}><ArrowLeft size={17} /><span>返回原页面</span></Link> : null}
        <Link className="header-search" href="/explore" prefetch={false}>
          <Search size={18} strokeWidth={1.7} />
          <span>{config.navigation.search}</span>
        </Link>
        <ThemeToggle />
        <IconButton
          ref={menuButtonRef}
          className="icon-button menu-button"
          type="button"
          aria-label={open ? "关闭菜单" : "打开菜单"}
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={25} /> : <Menu size={25} />}
        </IconButton>
      </div>
      {navigationReturn.returned ? <p className="site-navigation-returned" role="status">已返回先前页面</p> : null}
      {open ? (
        <Drawer open={open} onRequestClose={closeMenu} initialFocusRef={closeButtonRef} className="site-menu-layer" id="site-menu" aria-labelledby="site-menu-title">
          <button className="site-menu-backdrop" type="button" aria-label="关闭菜单" onClick={closeMenu} />
          <aside className="site-menu-panel" aria-labelledby="site-menu-title">
            <header className="site-menu-head">
              <Link href="/" prefetch={false} onClick={closeMenu}><Wordmark config={config} /><span className="sr-only" id="site-menu-title">书库导航</span></Link>
              <IconButton ref={closeButtonRef} aria-label="关闭菜单" onClick={closeMenu}>
                <X size={25} />
              </IconButton>
            </header>

            <form action="/explore" className="site-menu-search" role="search" aria-label="菜单内搜索" onSubmit={closeMenu}>
              <Search size={16} aria-hidden="true" /><label className="sr-only" htmlFor="menu-search-input">搜索书名、作者、概念、主题</label>
              <input id="menu-search-input" type="search" name="q" maxLength={500} value={menuSearch} onChange={event => setMenuSearch(event.target.value)} placeholder="搜索书名、作者、概念、主题…" />
              <button type="submit" aria-label="提交菜单搜索"><ChevronRight size={16} /></button>
            </form>

            <nav className="site-menu-nav" aria-label="书库导航">
              {navigation.map(([href, label]) => (
                <Link href={href} key={href} prefetch={false} onClick={closeMenu} aria-current={isActive(href) ? "page" : undefined}>
                  <strong>{label}</strong>
                  <ChevronRight size={15} />
                </Link>
              ))}
            </nav>

            <div className="site-menu-tools">
              <div>
                <Link href="/account" prefetch={false} onClick={enterAccount} aria-current={pathname === "/account" && searchParams.get("section") !== "settings" ? "page" : undefined}>
                  <CircleUserRound size={18} />
                  <span><strong>我的资料</strong></span><ChevronRight size={15} />
                </Link>
                <Link href="/account?section=settings" prefetch={false} onClick={enterAccount} aria-current={pathname === "/account" && searchParams.get("section") === "settings" ? "page" : undefined}>
                  <Settings size={18} />
                  <span><strong>账户设置</strong></span><ChevronRight size={15} />
                </Link>
                {user?.capabilities?.includes("access_back_office") ? <Link href="/admin" prefetch={false} onClick={closeMenu}><Settings size={18} /><span><strong>管理后台</strong></span><ChevronRight size={15} /></Link> : null}
                <Link href="/help" prefetch={false} onClick={closeMenu} aria-current={isActive("/help") ? "page" : undefined}><CircleHelp size={18} /><span><strong>帮助与支持</strong></span><ChevronRight size={15} /></Link>
                <Link href="/about" prefetch={false} onClick={closeMenu} aria-current={isActive("/about") ? "page" : undefined}><ArrowUpRight size={18} /><span><strong>关于我们</strong></span><ChevronRight size={15} /></Link>
                {!user ? (
                  <>
                    <Link href="/login?next=/account" prefetch={false} onClick={enterAccount}>
                      <CircleUserRound size={18} />
                      <span><strong>登录</strong><small>同步个人阅读资料</small></span>
                    </Link>
                    <Link href="/register" prefetch={false} onClick={enterAccount}>
                      <UserPlus size={18} />
                      <span><strong>注册</strong><small>创建免费读者账户</small></span>
                    </Link>
                  </>
                ) : (
                  <ActionButton
                    type="button"
                    state={pendingAction === "logout" ? "pending" : logoutError ? "error" : "idle"}
                    pendingLabel="正在退出"
                    errorLabel="退出失败，请重试"
                    onClick={() => void logout()}
                  >
                    <LogOut size={18} />
                    <span><strong>退出登录</strong><small>{user.display_name}</small></span>
                  </ActionButton>
                )}
              </div>
            </div>

            {logoutError ? <AsyncStatus state="error" message={logoutError} /> : null}

            <DisplayPreferences />

            <footer className="site-menu-foot">
              <span>{user ? `${user.display_name} · ${user.role === "reader" ? "读者" : "馆员"}` : "访客可直接阅读、下载、复制与引用"}</span>
              <Link href="/about" prefetch={false} onClick={closeMenu}>关于书库 <ArrowUpRight size={14} /></Link>
            </footer>
          </aside>
        </Drawer>
      ) : null}
    </header>
  );
}
