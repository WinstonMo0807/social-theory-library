"use client";

import Link from "next/link";
import {
  Bell,
  Activity,
  BookOpen,
  Boxes,
  ChartNoAxesCombined,
  Cloud,
  Compass,
  CircleDot,
  GitBranch,
  GitFork,
  GraduationCap,
  Info,
  LayoutDashboard,
  Menu,
  RefreshCw,
  Search,
  ScanSearch,
  Send,
  Settings,
  Sparkles,
  Tags,
  Upload,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { apiRequest, clearStoredSession, getStoredAccessToken, isAuthenticationError } from "@/lib/api";
import { Wordmark } from "./site-header";

const navigation = [
  ["概览", [
    ["/admin", LayoutDashboard, "Dashboard"],
    ["/admin/analytics", ChartNoAxesCombined, "阅读与搜索统计"],
  ]],
  ["上架", [
    ["/admin/uploads", Upload, "批量上传"],
    ["/admin/review", Boxes, "元数据复核"],
    ["/admin/processing", ChartNoAxesCombined, "Processing Center"],
  ]],
  ["馆藏", [
    ["/admin/library", BookOpen, "馆藏项目"],
  ]],
  ["学者与机构", [
    ["/admin/scholars", UserRound, "学者"],
  ]],
  ["理论知识", [
    ["/admin/disciplines", GraduationCap, "学科"],
    ["/admin/subdisciplines", GitBranch, "子学科"],
    ["/admin/theory-nodes", CircleDot, "理论节点"],
    ["/admin/theory-relations", GitFork, "理论关系"],
    ["/admin/theory-timeline", Compass, "理论时间轴"],
    ["/admin/topics", Tags, "主题"],
    ["/admin/reading-paths", BookOpen, "阅读路径"],
  ]],
  ["搜索与模型", [
    ["/admin/semantic-index", ScanSearch, "Semantic Index"],
  ]],
  ["发布", [
    ["/admin/publication", Send, "发布台"],
    ["/admin/recommendations", Sparkles, "推荐管理"],
    ["/admin/about", Info, "首页与关于"],
  ]],
  ["系统", [
    ["/admin/system-health", Activity, "System Health"],
    ["/admin/users", Users, "读者用户"],
    ["/admin/distribution", Cloud, "Storage 与分发"],
    ["/admin/settings", Settings, "运行设置"],
  ]],
] as const;

const administratorOnlyRoutes = new Set([
  "/admin/system-health",
  "/admin/semantic-index",
  "/admin/analytics",
  "/admin/users",
  "/admin/distribution",
  "/admin/settings",
]);

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(false);
  const [user, setUser] = useState<{ display_name: string; role: string } | null>(null);
  const [authError, setAuthError] = useState("");
  const [verificationAttempt, setVerificationAttempt] = useState(0);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px)");
    const updateNavigationMode = () => {
      setCompactNavigation(media.matches);
      if (!media.matches) setOpen(false);
    };
    updateNavigationMode();
    media.addEventListener("change", updateNavigationMode);
    return () => media.removeEventListener("change", updateNavigationMode);
  }, []);

  useEffect(() => {
    if (!compactNavigation || !open) return;
    const frame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      window.requestAnimationFrame(() => menuButtonRef.current?.focus());
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [compactNavigation, open]);

  function closeNavigation() {
    setOpen(false);
    if (compactNavigation) {
      window.requestAnimationFrame(() => menuButtonRef.current?.focus());
    }
  }

  useEffect(() => {
    let active = true;
    const token = getStoredAccessToken();
    if (!token) {
      window.location.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return () => {
        active = false;
      };
    }
    const verify = async () => {
      let lastError: unknown = null;
      for (const wait of [0, 700, 1800]) {
        if (wait) await new Promise((resolve) => window.setTimeout(resolve, wait));
        if (!active) return;
        try {
          const profile = await apiRequest<{ display_name: string; role: string }>("/auth/me/", {}, token);
          if (!active) return;
          if (!["admin", "editor", "reviewer"].includes(profile.role)) {
            window.location.replace("/");
            return;
          }
          setUser(profile);
          return;
        } catch (reason) {
          lastError = reason;
          if (isAuthenticationError(reason)) {
            clearStoredSession();
            window.location.replace(`/login?next=${encodeURIComponent(pathname)}`);
            return;
          }
        }
      }
      if (!active) return;
      setAuthError(lastError instanceof Error ? lastError.message : "管理服务暂时不可用，请重试。");
    };
    void verify();
    return () => {
      active = false;
    };
  }, [pathname, verificationAttempt]);

  if (!user) {
    return (
      <div className="admin-auth-loading">
        <strong>{authError ? "管理服务暂时不可用" : "正在验证管理权限……"}</strong>
        {authError ? <><p>{authError}</p><button type="button" onClick={() => {
          setAuthError("");
          setVerificationAttempt((value) => value + 1);
        }}><RefreshCw size={15} />保留会话并重试</button></> : null}
      </div>
    );
  }

  return (
    <div className="admin-shell">
      <aside
        id="admin-navigation"
        className={`admin-sidebar ${open ? "open" : ""}`}
        aria-label="后台导航"
        aria-hidden={compactNavigation && !open}
        inert={compactNavigation && !open}
      >
        <Link className="admin-logo" href="/" prefetch={false}><Wordmark /></Link>
        <button ref={closeButtonRef} className="admin-mobile-close" type="button" aria-label="关闭后台菜单" onClick={closeNavigation}><X size={19} /></button>
        <nav>
          {navigation.map(([group, links]) => {
            const visibleLinks = links.filter(([href]) => (
              user.role === "admin" || !administratorOnlyRoutes.has(href)
            ));
            if (!visibleLinks.length) return null;
            return (
            <section className="admin-nav-group" key={group}>
              <p>{group}</p>
              {visibleLinks.map(([href, Icon, label]) => {
                const active = href === "/admin" ? pathname === href : pathname.startsWith(href);
                return <Link className={active ? "active" : ""} href={href} key={href} prefetch={false} onClick={closeNavigation}><Icon size={17} />{label}</Link>;
              })}
            </section>
            );
          })}
        </nav>
        <div className="system-status"><span /><small>当前会话</small><strong>API 已连接</strong></div>
        <footer><strong>社会理论书库</strong><span>v2.6.1 连续入库与检索修复版</span></footer>
      </aside>
      <div className="admin-main">
        <header className="admin-topbar">
          <button
            ref={menuButtonRef}
            className="admin-menu-button"
            type="button"
            aria-label="打开后台菜单"
            aria-expanded={compactNavigation ? open : undefined}
            aria-controls="admin-navigation"
            onClick={() => setOpen(true)}
          ><Menu size={20} /></button>
          <strong>管理后台</strong>
          <form action="/admin/library">
            <label><Search size={15} /><input type="search" name="q" placeholder="搜索馆藏……" aria-label="搜索后台馆藏" /></label>
            <button className="sr-only" type="submit">搜索</button>
          </form>
          <Link className="admin-processing-link" href="/admin/processing" prefetch={false} aria-label="打开处理中心"><Bell size={18} /></Link>
          <div className="admin-user"><span>{user.display_name.slice(0, 1)}</span><p><strong>{user.display_name}</strong><small>{user.role === "admin" ? "管理员" : user.role === "reviewer" ? "审核者" : "编辑"}</small></p></div>
        </header>
        <div className="admin-content">{children}</div>
      </div>
    </div>
  );
}
