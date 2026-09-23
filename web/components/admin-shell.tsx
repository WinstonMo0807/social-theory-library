"use client";

import Link from "next/link";
import {
  Bell,
  BookOpen,
  Boxes,
  ChartNoAxesCombined,
  Cloud,
  CircleDot,
  LayoutDashboard,
  Menu,
  RefreshCw,
  Search,
  Sparkles,
  Tags,
  Upload,
  Trash2,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ADMIN_VERSION_LABEL } from "@/lib/version";
import { AdminSessionContext } from "@/lib/admin-session";
import { adminLoginHref, adminTaskScope, safeAdminHref } from "@/lib/admin-route-context";
import { Wordmark } from "./site-header";

const navigation = [
    ["/admin", LayoutDashboard, "今日工作"],
    ["/admin/uploads", Upload, "上传"],
    ["/admin/review", Boxes, "待办与复核"],
    ["/admin/recycle", Trash2, "回收站"],
    ["/admin/theories", CircleDot, "理论流派"],
    ["/admin/scholars", UserRound, "学者"],
    ["/admin/topics", Tags, "主题"],
    ["/admin/recommendations", Sparkles, "推荐与随机"],
    ["/admin/about", BookOpen, "网站与关于书库"],
    ["/admin/processing", ChartNoAxesCombined, "Processing Center"],
    ["/admin/storage", Cloud, "文件存储"],
    ["/admin/backups", Boxes, "备份"],
    ["/admin/analytics", ChartNoAxesCombined, "审计与统计"],
    ["/admin/users", Users, "用户与权限"],
] as const;

const routeCapabilities: Record<string, string[]> = {
  "/admin/processing": ["can_view_system_status"],
  "/admin/status": ["can_view_system_status"],
  "/admin/system-health": ["can_view_system_status"],
  "/admin/query-lexicon": ["can_view_query_lexicon"],
  "/admin/semantic-index": ["can_view_semantic_index"],
  "/admin/analytics": ["can_view_audit_log"],
  "/admin/users": ["can_manage_users"],
  "/admin/distribution": ["can_configure_providers"],
  "/admin/storage": ["can_configure_providers"],
  "/admin/backups": ["can_run_backup"],
  "/admin/settings#backups": ["can_run_backup"],
  "/admin/settings": ["can_manage_ai", "can_manage_search_runtime"],
};

// Keep the route-level list explicit even though the server remains the
// authority for every permission check.  It gives older session payloads a
// safe, predictable fallback while newer payloads use the capability snapshot.
const administratorOnlyRoutes = new Set([
  "/admin/processing",
  "/admin/status",
  "/admin/system-health",
  "/admin/query-lexicon",
  "/admin/semantic-index",
  "/admin/analytics",
  "/admin/users",
  "/admin/distribution",
  "/admin/storage",
  "/admin/backups",
  "/admin/settings",
]);

const staffRoles = ["admin", "editor"] as const;

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const scope = adminTaskScope(pathname);
  const searchParams = useSearchParams();
  const returnHref = safeAdminHref(searchParams.get("return_to"), "");
  const curationReturn = returnHref && new URL(returnHref, "https://admin.invalid");
  const returnToCuration = curationReturn && curationReturn.pathname === "/admin/review" && curationReturn.searchParams.get("workspace") === "curation";
  const focusMode = false;
  const [open, setOpen] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(false);
  const { state: session, retry: retrySession } = useSessionBootstrap(staffRoles);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);

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
      if (event.key === "Tab") {
        const controls = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>('a[href],button:not(:disabled)') ?? []).filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden");
        const first = controls[0], last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        return;
      }
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
      window.location.replace(adminLoginHref(pathname, searchParams.toString(), window.location.hash));
    }
  }, [pathname, searchParams, session.status]);

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
      if (href === "/admin/backups") return user.is_library_owner === true;
      return user.role === "admin" || !administratorOnlyRoutes.has(href.split(/[?#]/)[0]);
    }
    const required = routeCapabilities[href] ?? routeCapabilities[href.split(/[?#]/)[0]];
    if (!required) return true;
    return required.some((capability) => capabilities.has(capability));
  }

  return (
    <AdminSessionContext.Provider value={user}>
    <div className={`admin-shell ${focusMode ? "focus-mode" : ""}`}>
      {!focusMode ? <aside
        ref={sidebarRef}
        id="admin-navigation"
        className={`admin-sidebar ${open ? "open" : ""}`}
        aria-label="后台导航"
        role={compactNavigation && open ? "dialog" : undefined}
        aria-modal={compactNavigation && open ? true : undefined}
        aria-hidden={compactNavigation && !open}
        inert={compactNavigation && !open}
      >
        <Link className="admin-logo" href="/" prefetch={false}><Wordmark /></Link>
        <button ref={closeButtonRef} className="admin-mobile-close" type="button" aria-label="关闭后台菜单" onClick={closeNavigation}><X size={19} /></button>
        <nav>
          {navigation.filter(([href]) => canViewRoute(href)).map(([href, Icon, label]) => {
                const [hrefPath, hrefQuery = ""] = href.split("#")[0].split("?");
                const requestedView = new URLSearchParams(hrefQuery).get("view");
                const currentView = searchParams.get("view");
                const requestedSurface = new URLSearchParams(hrefQuery).get("surface");
                const active = hrefPath === "/admin"
                  ? pathname === hrefPath
                  : (pathname === hrefPath || pathname.startsWith(`${hrefPath}/`))
                    && (requestedView ? currentView === requestedView : hrefPath !== "/admin/library" || !currentView)
                    && (requestedSurface ? searchParams.get("surface") === requestedSurface : true);
                return <Link className={active ? "active" : ""} aria-current={active ? "page" : undefined} href={href} key={href} prefetch={false} onClick={closeNavigation}><Icon size={17} />{label}</Link>;
          })}
        </nav>
        <footer><strong>社会理论书库</strong><span>{ADMIN_VERSION_LABEL}</span></footer>
      </aside> : null}
      <div className="admin-main" inert={compactNavigation && open}>
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
          <strong aria-label="当前管理范围">{scope.title}</strong>
          <form action="/admin/library">
            <label><Search size={15} /><input type="search" name="q" placeholder="搜索馆藏……" aria-label="搜索后台馆藏" /></label>
            <button className="sr-only" type="submit">搜索</button>
          </form>
          {canViewRoute("/admin/processing") ? <Link className="admin-processing-link" href="/admin/processing" prefetch={false} aria-label="打开处理中心"><Bell size={18} /></Link> : null}
          <div className="admin-user"><span>{user.display_name.slice(0, 1)}</span><p><strong>{user.display_name}</strong><small>{user.role === "admin" ? "管理员" : "编辑"}</small></p></div>
        </header> : null}
        <div className="admin-content">{returnToCuration ? <Link className="admin-curation-return" href={returnHref} prefetch={false}>‹ 返回策展草稿</Link> : null}{children}</div>
      </div>
    </div>
    </AdminSessionContext.Provider>
  );
}
