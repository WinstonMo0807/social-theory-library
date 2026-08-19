"use client";

import Link from "next/link";
import {
  Bell,
  Activity,
  BookOpen,
  Boxes,
  ChartNoAxesCombined,
  Cloud,
  CircleDot,
  GitBranch,
  GitFork,
  GraduationCap,
  LayoutDashboard,
  Menu,
  RefreshCw,
  Search,
  ScanSearch,
  Send,
  Sparkles,
  Tags,
  Upload,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ADMIN_VERSION_LABEL } from "@/lib/version";
import { Wordmark } from "./site-header";

const navigation = [
  ["工作", [
    ["/admin", LayoutDashboard, "今日工作"],
    ["/admin/uploads", Upload, "上传与批次"],
    ["/admin/review", Boxes, "待处理"],
    ["/admin/publication", Send, "发布准备"],
    ["/admin/candidates", CircleDot, "待候选审核"],
  ]],
  ["馆藏", [
    ["/admin/library", BookOpen, "作品"],
    ["/admin/library?view=editions", Boxes, "版本与文件"],
    ["/admin/library?view=quality", Activity, "馆藏质量"],
  ]],
  ["知识", [
    ["/admin/scholars", UserRound, "学者"],
    ["/admin/disciplines", GraduationCap, "学科"],
    ["/admin/subdisciplines", GitBranch, "子学科"],
    ["/admin/theory-nodes", CircleDot, "理论与概念"],
    ["/admin/topics", Tags, "主题"],
    ["/admin/theory-relations", GitFork, "关系与时间轴"],
    ["/admin/query-lexicon", Search, "QueryLexicon"],
    ["/admin/semantic-index", ScanSearch, "语义索引"],
  ]],
  ["策展", [
    ["/admin/reading-paths", BookOpen, "阅读路径"],
    ["/admin/recommendations", Sparkles, "推荐"],
  ]],
  ["系统", [
    ["/admin/processing", ChartNoAxesCombined, "处理任务"],
    ["/admin/status", Activity, "系统状态"],
    ["/admin/distribution", Cloud, "备份与存储"],
    ["/admin/analytics", ChartNoAxesCombined, "审计与统计"],
    ["/admin/users", Users, "用户与权限"],
    ["/admin/settings", Sparkles, "运行设置"],
  ]],
] as const;

const routeCapabilities: Record<string, string[]> = {
  "/admin/status": ["can_view_system_status"],
  "/admin/system-health": ["can_view_system_status"],
  "/admin/query-lexicon": ["can_view_query_lexicon"],
  "/admin/semantic-index": ["can_view_semantic_index"],
  "/admin/analytics": ["can_view_audit_log"],
  "/admin/users": ["can_manage_users"],
  "/admin/distribution": ["can_run_backup"],
  "/admin/settings": ["can_manage_ai", "can_manage_search_runtime"],
};

// Keep the route-level list explicit even though the server remains the
// authority for every permission check.  It gives older session payloads a
// safe, predictable fallback while newer payloads use the capability snapshot.
const administratorOnlyRoutes = new Set([
  "/admin/status",
  "/admin/system-health",
  "/admin/query-lexicon",
  "/admin/semantic-index",
  "/admin/analytics",
  "/admin/users",
  "/admin/distribution",
  "/admin/settings",
]);

const staffRoles = ["admin", "editor", "reviewer"] as const;

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const focusMode = /^\/admin\/(?:intake\/[^/]+|library\/works\/[^/]+)\/?$/.test(pathname);
  const [open, setOpen] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(false);
  const { state: session, retry: retrySession } = useSessionBootstrap(staffRoles);
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
    if (session.status === "unauthenticated") {
      window.location.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [pathname, session.status]);

  if (["unknown", "loading", "unauthenticated"].includes(session.status)) {
    return (
      <div className="admin-auth-loading">
        <strong>{session.status === "unauthenticated" ? "登录已过期" : "正在验证管理权限……"}</strong>
        {session.status === "unauthenticated" ? <p>正在转到登录页面。</p> : null}
      </div>
    );
  }

  if (session.status === "forbidden") {
    return (
      <div className="admin-auth-loading" data-error-category={session.errorCategory}>
        <strong>当前账户没有管理权限</strong>
        <p>{session.message}</p>
        <Link href="/account">返回读者中心</Link>
      </div>
    );
  }

  if (session.status === "temporary_error" || !session.user) {
    return (
      <div className="admin-auth-loading" data-error-category={session.errorCategory}>
        <strong>认证服务暂时不可用</strong>
        <p>{session.message}</p>
        <button type="button" onClick={retrySession}><RefreshCw size={15} />保留会话并重试</button>
      </div>
    );
  }

  const user = session.user;
  const capabilities = user.capabilities === undefined
    ? null
    : new Set(user.capabilities);

  function canViewRoute(href: string) {
    // A response from an older API may not contain capabilities yet.  This is
    // only a display fallback; all mutations and page APIs still enforce the
    // server-side capability checks.
    if (capabilities === null) {
      return user.role === "admin" || !administratorOnlyRoutes.has(href);
    }
    const required = routeCapabilities[href];
    if (!required) return true;
    return required.some((capability) => capabilities.has(capability));
  }

  return (
    <div className={`admin-shell ${focusMode ? "focus-mode" : ""}`}>
      {!focusMode ? <aside
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
            const visibleLinks = links.filter(([href]) => canViewRoute(href));
            if (!visibleLinks.length) return null;
            return (
            <section className="admin-nav-group" key={group}>
              <p>{group}</p>
              {visibleLinks.map(([href, Icon, label]) => {
                const [hrefPath, hrefQuery = ""] = href.split("?");
                const requestedView = new URLSearchParams(hrefQuery).get("view");
                const currentView = searchParams.get("view");
                const active = hrefPath === "/admin"
                  ? pathname === hrefPath
                  : pathname.startsWith(hrefPath)
                    && (requestedView ? currentView === requestedView : hrefPath !== "/admin/library" || !currentView);
                return <Link className={active ? "active" : ""} href={href} key={href} prefetch={false} onClick={closeNavigation}><Icon size={17} />{label}</Link>;
              })}
            </section>
            );
          })}
        </nav>
        <div className="system-status"><span /><small>当前会话</small><strong>API 已连接</strong></div>
        <footer><strong>社会理论书库</strong><span>{ADMIN_VERSION_LABEL}</span></footer>
      </aside> : null}
      <div className="admin-main">
        {!focusMode ? <header className="admin-topbar">
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
        </header> : null}
        <div className="admin-content">{children}</div>
      </div>
    </div>
  );
}
