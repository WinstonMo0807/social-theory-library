"use client";

import Link from "next/link";
import {
  BookOpen,
  Boxes,
  CalendarDays,
  ChartNoAxesCombined,
  CircleDot,
  ChevronDown,
  LayoutDashboard,
  ListTodo,
  Menu,
  RefreshCw,
  Tags,
  UserRound,
  X,
} from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ADMIN_VERSION_LABEL } from "@/lib/version";
import { logoutCurrentSession } from "@/lib/api";
import { AdminSessionContext } from "@/lib/admin-session";
import { adminLoginHref, adminTaskScope, safeAdminHref } from "@/lib/admin-route-context";
import { Wordmark } from "./site-header";

const navigation = [
  { key: "work", primary: "/admin", label: "工作台", Icon: LayoutDashboard, match: ["/admin"], children: [["/admin", "今日工作"], ["/admin/review?workspace=curation", "待完成"], ["/admin/uploads", "最近上传"]] },
  { key: "library", primary: "/admin/uploads", label: "馆藏", Icon: BookOpen, match: ["/admin/library", "/admin/uploads", "/admin/review", "/admin/intake", "/admin/cataloging", "/admin/" + "media", "/admin/publication"], children: [["/admin/library", "馆藏列表"], ["/admin/uploads", "上传 PDF"], ["/admin/review", "待完成"], ["/admin/" + "media", "图片库"]] },
  { key: "theory", primary: "/admin/theories", label: "理论流派", Icon: CircleDot, match: ["/admin/theories", "/admin/disciplines", "/admin/subdisciplines", "/admin/reading-paths"], children: [["/admin/theories", "流派列表"], ["/admin/theories/disciplines", "学科与子学科"], ["/admin/theories/timeline", "时间线"], ["/admin/theories/relations", "学术关系"], ["/admin/theories/reading-paths", "阅读路径"]] },
  { key: "scholars", primary: "/admin/scholars", label: "学者", Icon: UserRound, match: ["/admin/scholars", "/admin/" + "people"], children: [["/admin/scholars", "学者列表"], ["/admin/scholars/new", "新建学者"], ["/admin/scholars/people", "人物查重"]] },
  { key: "topics", primary: "/admin/topics", label: "主题", Icon: Tags, match: ["/admin/topics"], children: [["/admin/topics", "主题列表"]] },
  { key: "recommendations", primary: "/admin/recommendations", label: "每日荐读", Icon: CalendarDays, match: ["/admin/recommendations"], children: [["/admin/recommendations", "文章列表"], ["/admin/recommendations?view=calendar", "编辑日历"], ["/admin/recommendations?view=home", "首页推荐位置"]] },
  { key: "site", primary: "/admin/about", label: "网站内容", Icon: Boxes, match: ["/admin/about"], children: [["/admin/about", "首页与关于书库"], ["/admin/about?section=brand", "品牌与页脚"]] },
  { key: "processing", primary: "/admin/processing", label: "处理中心", Icon: ListTodo, match: ["/admin/processing", "/admin/status", "/admin/system-health", "/admin/query-lexicon", "/admin/semantic-index"], children: [["/admin/processing", "待处理任务"], ["/admin/processing?surface=documents", "文字识别"], ["/admin/processing?surface=research-sources", "资料来源"], ["/admin/processing/semantic-index", "搜索维护"], ["/admin/processing/query-lexicon", "检索用语"], ["/admin/processing/status", "运行检查"]] },
  { key: "system", primary: "/admin/storage", label: "系统管理", Icon: ChartNoAxesCombined, match: ["/admin/storage", "/admin/backups", "/admin/analytics", "/admin/users", "/admin/recycle", "/admin/" + "settings", "/admin/distribution"], children: [["/admin/storage", "文件存储"], ["/admin/backups", "备份与恢复"], ["/admin/analytics", "使用统计"], ["/admin/users", "用户权限"], ["/admin/recycle", "回收站"]] },
] as const;

const routeCapabilities: Record<string, string[]> = {
  "/admin/processing": ["can_view_system_status"],
  "/admin/processing/semantic-index": ["can_view_semantic_index"],
  "/admin/processing/query-lexicon": ["can_view_query_lexicon"],
  "/admin/processing/settings": ["can_manage_ai", "can_manage_search_runtime"],
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
  const [logoutPending, setLogoutPending] = useState(false);
  const [logoutError, setLogoutError] = useState("");
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
  const currentSection = navigation.find(section => pathname === "/admin/review" && searchParams.get("workspace") === "curation" ? section.key === "work" : section.match.some(match => pathname === match || (match !== "/admin" && pathname.startsWith(`${match}/`))));
  const currentChild = currentSection?.children.find(([href]) => {
    const [path, query] = href.split("?");
    return (path === pathname || (path === "/admin/theories/disciplines" && pathname === "/admin/theories/subdisciplines")) && (query ? Array.from(new URLSearchParams(query)).every(([key, value]) => searchParams.get(key) === value) : !searchParams.get("view") && !searchParams.get("workspace"));
  });
  const embeddedPreview = searchParams.get("embed") === "1" && (pathname.startsWith("/admin/preview/") || pathname === "/admin/about/preview" || /^\/admin\/recommendations\/issues\/[^/]+\/preview$/.test(pathname));
  if (embeddedPreview) return <AdminSessionContext.Provider value={user}><div className="admin-embedded-preview">{children}</div></AdminSessionContext.Provider>;
  const capabilities = user.capabilities === undefined
    ? null
    : new Set(user.capabilities);

  function canViewRoute(href: string) {
    const routePath = href.split(/[?#]/)[0];
    // A response from an older API may not contain capabilities yet.  This is
    // only a display fallback; all mutations and page APIs still enforce the
    // server-side capability checks.
    if (capabilities === null) {
      if (routePath === "/admin/backups") return user.is_library_owner === true;
      return user.role === "admin" || !Array.from(administratorOnlyRoutes).some(route => routePath === route || routePath.startsWith(`${route}/`));
    }
    const capabilityPath = Object.keys(routeCapabilities).filter(route => routePath === route || routePath.startsWith(`${route}/`)).sort((a, b) => b.length - a.length)[0];
    const required = routeCapabilities[href] ?? routeCapabilities[capabilityPath];
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
          {navigation.filter(section => section.children.some(([href]) => canViewRoute(href))).map(section => {
            const primaryHref = canViewRoute(section.primary) ? section.primary : section.children.find(([href]) => canViewRoute(href))![0];
            const curationQueue = pathname === "/admin/review" && searchParams.get("workspace") === "curation";
            const active = curationQueue ? section.key === "work" : section.match.some((match) => pathname === match || (match !== "/admin" && pathname.startsWith(`${match}/`)));
            return <div className={`admin-nav-section ${active ? "active" : ""}`} key={section.key}>
              <Link className="admin-nav-primary" aria-current={active ? "page" : undefined} href={primaryHref} prefetch={false} onClick={closeNavigation}>
                <section.Icon size={17} />
                <span>{section.label}</span>
              </Link>
              {active ? <div className="admin-nav-children">
                {section.children.filter(([childHref]) => canViewRoute(childHref)).map(([childHref, childLabel]) => {
                  const childPath = childHref.split("?")[0];
                  const childQuery = childHref.includes("?") ? new URLSearchParams(childHref.split("?")[1]) : null;
                  const queryMatches = childQuery ? Array.from(childQuery.entries()).every(([key, value]) => searchParams.get(key) === value) : !section.children.some(([otherHref]) => otherHref.startsWith(`${childPath}?`) && Array.from(new URLSearchParams(otherHref.split("?")[1]).entries()).every(([key, value]) => searchParams.get(key) === value));
                  const childActive = (pathname === childPath || (childPath === "/admin/theories/disciplines" && pathname === "/admin/theories/subdisciplines")) && queryMatches;
                  return <Link className={childActive ? "active" : ""} aria-current={childActive ? "page" : undefined} href={childHref} key={childHref} prefetch={false} onClick={closeNavigation}>{childLabel}</Link>;
                })}
              </div> : null}
            </div>;
          })}
        </nav>
        <footer><Link className="admin-back-public" href="/" prefetch={false}>← <span>返回前台</span></Link><span className="sr-only">{ADMIN_VERSION_LABEL}</span></footer>
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
          <div className="admin-breadcrumb" aria-label="当前管理范围"><strong>{currentSection?.label || scope.title}</strong><b>›</b><span>{currentChild?.[1] || "编辑内容"}</span></div>
          <details className="admin-account-menu"><summary className="admin-user"><span>{user.display_name.slice(0, 1)}</span><strong>{user.display_name}</strong><ChevronDown size={13}/></summary><div><Link href="/account" prefetch={false}>我的账户</Link><button type="button" disabled={logoutPending} onClick={async () => { if (logoutPending) return; setLogoutPending(true); setLogoutError(""); try { await logoutCurrentSession(); } catch (error) { setLogoutError(error instanceof Error ? error.message : "退出失败，请重试。"); } finally { setLogoutPending(false); } }}>{logoutPending ? "正在退出…" : "退出登录"}</button>{logoutError ? <p role="alert">{logoutError}</p> : null}</div></details>
        </header> : null}
        <div className="admin-content">{returnToCuration ? <Link className="admin-curation-return" href={returnHref} prefetch={false}>‹ 返回策展草稿</Link> : null}{children}</div>
      </div>
    </div>
    </AdminSessionContext.Provider>
  );
}
