"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  BookOpen,
  CircleUserRound,
  LogOut,
  Menu,
  Search,
  Settings,
  UserPlus,
  X,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getServerSessionCredential, logoutCurrentSession, subscribeToSessionChanges } from "@/lib/api";
import { bootstrapSession } from "@/lib/session";
import { defaultSiteConfig, type SiteConfig } from "@/lib/site-config";
import { DisplayPreferences } from "./display-preferences";

export function Wordmark({ config = defaultSiteConfig }: { config?: SiteConfig }) {
  return (
    <span className="wordmark" aria-label={config.site_name}>
      {config.wordmark_lines.map((line) => (
        <span key={line}>{line}</span>
      ))}
    </span>
  );
}

export function SiteHeader({ config = defaultSiteConfig }: { config?: SiteConfig }) {
  const pathname = usePathname();
  const exploreRoute = pathname === "/explore" || pathname.startsWith("/explore/");
  const authRoute = pathname === "/login" || pathname === "/register" || pathname === "/reset-password";
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState<{ display_name: string; role: string } | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const menuPanelRef = useRef<HTMLElement>(null);
  const wasMenuOpenRef = useRef(false);
  const navigation = [
    ["/", config.navigation.home],
    ["/explore", config.navigation.explore],
    ["/theories", config.navigation.theory_schools],
    ["/scholars", config.navigation.scholars],
    ["/topics", config.navigation.topics],
  ] as const;

  useEffect(() => {
    let active = true;
    const verify = async (force = false) => {
      if (!force && !getServerSessionCredential()) return;
      const session = await bootstrapSession();
      if (!active) return;
      if (session.status === "authenticated" && session.user) {
        setUser(session.user);
      } else if (["unauthenticated", "forbidden"].includes(session.status)) {
        setUser(null);
      }
    };
    void verify();
    const unsubscribe = subscribeToSessionChanges(() => void verify(true));
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    document.body.classList.toggle("menu-open", open);
    if (!open) {
      if (wasMenuOpenRef.current) menuButtonRef.current?.focus();
      wasMenuOpenRef.current = false;
      return () => document.body.classList.remove("menu-open");
    }

    wasMenuOpenRef.current = true;
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;

      const panel = menuPanelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ));
      if (!focusable.length) {
        event.preventDefault();
        closeButtonRef.current?.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.classList.remove("menu-open");
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  function closeMenu() {
    setOpen(false);
  }

  async function logout() {
    await logoutCurrentSession();
    setUser(null);
    closeMenu();
  }

  if (pathname.startsWith("/reader/") || pathname.startsWith("/admin") || authRoute) {
    return null;
  }

  return (
    <header
      className={exploreRoute ? "site-header" : "site-header site-header--editorial"}
      data-ui-scope={exploreRoute ? "explore-frozen" : "editorial-v2"}
    >
      <Link className="logo-link" href="/" prefetch={false}>
        <Wordmark config={config} />
      </Link>
      <nav className="desktop-nav" aria-label="主导航">
        {navigation.map(([href, label]) => {
          const active = href === "/"
            ? pathname === "/"
            : href === "/theories"
              ? pathname.startsWith("/theories") || pathname.startsWith("/theory-schools")
              : pathname.startsWith(href);
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
        <Link className="header-search" href="/explore" prefetch={false}>
          <Search size={18} strokeWidth={1.7} />
          <span>{config.navigation.search}</span>
        </Link>
        <button
          ref={menuButtonRef}
          className="icon-button menu-button"
          type="button"
          aria-label={open ? "关闭菜单" : "打开菜单"}
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={25} /> : <Menu size={25} />}
        </button>
      </div>
      {open ? (
        <div className="site-menu-layer" id="site-menu">
          <button className="site-menu-backdrop" type="button" aria-label="关闭菜单" onClick={closeMenu} />
          <aside ref={menuPanelRef} className="site-menu-panel" role="dialog" aria-modal="true" aria-labelledby="site-menu-title">
            <header className="site-menu-head">
              <div>
                <p>Social Theory Library</p>
                <strong id="site-menu-title">书库导航</strong>
              </div>
              <button ref={closeButtonRef} type="button" aria-label="关闭菜单" onClick={closeMenu}>
                <X size={25} />
              </button>
            </header>

            <nav className="site-menu-nav" aria-label="书库导航">
              {navigation.map(([href, label], index) => (
                <Link href={href} key={href} prefetch={false} onClick={closeMenu}>
                  <span>0{index + 1}</span>
                  <strong>{label}</strong>
                  <ArrowUpRight size={18} />
                </Link>
              ))}
            </nav>

            <div className="site-menu-tools">
              <p>读者与管理</p>
              <div>
                <Link href="/account" prefetch={false} onClick={closeMenu}>
                  <BookOpen size={18} />
                  <span><strong>读者中心</strong><small>进度、收藏、笔记与导出</small></span>
                </Link>
                <Link href="/admin" prefetch={false} onClick={closeMenu}>
                  <Settings size={18} />
                  <span><strong>管理后台</strong><small>入库、复核、馆藏与设置</small></span>
                </Link>
                {!user ? (
                  <>
                    <Link href="/login" prefetch={false} onClick={closeMenu}>
                      <CircleUserRound size={18} />
                      <span><strong>登录</strong><small>同步个人阅读资料</small></span>
                    </Link>
                    <Link href="/register" prefetch={false} onClick={closeMenu}>
                      <UserPlus size={18} />
                      <span><strong>注册</strong><small>创建免费读者账户</small></span>
                    </Link>
                  </>
                ) : (
                  <button type="button" onClick={logout}>
                    <LogOut size={18} />
                    <span><strong>退出登录</strong><small>{user.display_name}</small></span>
                  </button>
                )}
              </div>
            </div>

            <DisplayPreferences />

            <footer className="site-menu-foot">
              <span>{user ? `${user.display_name} · ${user.role === "reader" ? "读者" : "馆员"}` : "访客可直接阅读、下载、复制与引用"}</span>
              <Link href="/about" prefetch={false} onClick={closeMenu}>关于书库 <ArrowUpRight size={14} /></Link>
            </footer>
          </aside>
        </div>
      ) : null}
    </header>
  );
}
