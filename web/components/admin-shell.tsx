"use client";

import Link from "next/link";
import { Archive, ChartColumn, ClipboardCheck, ClipboardList, FileCheck2, FileText, Settings, UserRound, ChevronDown, Menu, RefreshCw, Search, X, LockKeyhole, CircleHelp, MoreHorizontal } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ADMIN_VERSION_LABEL } from "@/lib/version";
import { AdminSessionContext } from "@/lib/admin-session";
import { adminLoginHref, adminTaskScope, safeAdminHref } from "@/lib/admin-route-context";
import { Wordmark } from "./site-header";
import { ThemeToggle } from "./theme-toggle";
import { AdminWorkNotices } from "./admin/admin-work-notices";

const navigationGroups = [
  { label: "工作", entries: [
    { href: "/admin", title: "今日工作", Icon: ClipboardCheck, paths: ["/admin", "/admin/search"], children: [] },
    { href: "/admin/uploads", title: "收件与编目", Icon: ClipboardList, paths: ["/admin/uploads", "/admin/intake", "/admin/cataloging", "/admin/review"], children: [["/admin/uploads", "上传与收件"], ["/admin/review", "待办与复核"], ["/admin/cataloging/new", "手工编目"]] },
    { href: "/admin/library", title: "馆藏目录", Icon: FileCheck2, paths: ["/admin/library"], children: [] },
    { href: "/admin/processing", title: "文件与处理", Icon: ClipboardCheck, paths: ["/admin/processing"], children: [["/admin/processing?surface=documents", "OCR 与文档"], ["/admin/processing?surface=workers", "后台任务"], ["/admin/processing?surface=research-sources", "资料来源"], ["/admin/processing/semantic-index", "搜索维护"]] },
  ] },
  { label: "内容", entries: [
    { href: "/admin/recommendations", title: "特别策划", Icon: FileText, paths: ["/admin/recommendations"], children: [["/admin/recommendations", "策划文章"], ["/admin/recommendations?view=home", "首页推荐位置"]] },
    { href: "/admin/content", title: "页面编排", Icon: ChartColumn, paths: ["/admin/content", "/admin/about", "/admin/media"], children: [["/admin/content", "内容编排"], ["/admin/about", "网站与关于书库"], ["/admin/media", "图片库"]] },
    { href: "/admin/theories", title: "学者与知识", Icon: ClipboardCheck, paths: ["/admin/theories", "/admin/scholars", "/admin/topics", "/admin/people", "/admin/reading-paths", "/admin/disciplines", "/admin/subdisciplines"], children: [["/admin/scholars", "学者"], ["/admin/theories", "理论流派"], ["/admin/topics", "主题"], ["/admin/theories/disciplines", "学科"], ["/admin/theories/subdisciplines", "子学科"], ["/admin/theories/relations", "学术关系"], ["/admin/theories/timeline", "时间线"], ["/admin/theories/reading-paths", "阅读路径"], ["/admin/scholars/people", "人物查重"]] },
    { href: "/admin/publication", title: "发布台", Icon: Archive, paths: ["/admin/publication"], children: [] },
  ] },
  { label: "系统", entries: [
    { href: "/admin/users", title: "账户与权限", Icon: UserRound, paths: ["/admin/users"], children: [] },
    { href: "/admin/processing/status", title: "运行维护", Icon: Settings, paths: ["/admin/processing/status", "/admin/processing/health", "/admin/processing/settings", "/admin/status", "/admin/system-health", "/admin/storage", "/admin/backups", "/admin/analytics", "/admin/recycle", "/admin/settings", "/admin/distribution", "/admin/query-lexicon", "/admin/semantic-index", "/admin/support"], children: [["/admin/processing/status", "运行检查"], ["/admin/storage", "文件存储"], ["/admin/backups", "备份与恢复"], ["/admin/analytics", "审计与统计"], ["/admin/settings", "模型与服务"], ["/admin/distribution", "分发设置"], ["/admin/recycle", "回收站"], ["/admin/support/feedback", "反馈处理"], ["/admin/support/parallel-calibrations", "公共校准"]] },
  ] },
] as const;

// A nested system page belongs to its most specific navigation group.
function navigationHref(pathname: string) {
  return navigationGroups.flatMap(group => group.entries.flatMap(entry => entry.paths.map(path => ({ path, href: entry.href }))))
    .filter(({ path }) => pathname === path || path !== "/admin" && pathname.startsWith(`${path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0]?.href;
}

const routeCapabilities: Record<string, string[]> = {
  "/admin/visual-review": ["can_manage_users"],
  "/admin/content": ["can_edit_metadata", "can_edit_draft_authority"],
  "/admin/processing": ["can_view_system_status"],
  "/admin/publication": ["can_publish_work"],
  "/admin/publication/knowledge": ["can_edit_draft_authority", "can_publish_authority", "can_view_evidence"],
  "/admin/uploads": ["can_upload"],
  "/admin/cataloging": ["can_edit_metadata"],
  "/admin/recycle": ["can_edit_metadata"],
  "/admin/status": ["can_view_system_status"],
  "/admin/system-health": ["can_view_system_status"],
  "/admin/query-lexicon": ["can_view_query_lexicon"],
  "/admin/semantic-index": ["can_view_semantic_index"],
  "/admin/analytics": ["can_view_audit_log"],
  "/admin/users": ["can_manage_users"],
  "/admin/support/feedback": ["can_manage_users"],
  "/admin/support/parallel-calibrations": ["can_review_candidate"],
  "/admin/distribution": ["can_configure_providers"],
  "/admin/storage": ["can_configure_providers"],
  "/admin/backups": ["can_run_backup"],
  "/admin/settings#backups": ["can_run_backup"],
  "/admin/settings": ["can_view_system_status"],
};

// Keep the route-level list explicit even though the server remains the
// authority for every permission check.  It gives older session payloads a
// safe, predictable fallback while newer payloads use the capability snapshot.
const administratorOnlyRoutes = new Set([
  "/admin/visual-review",
  "/admin/processing",
  "/admin/status",
  "/admin/system-health",
  "/admin/query-lexicon",
  "/admin/semantic-index",
  "/admin/analytics",
  "/admin/users",
  "/admin/support/feedback",
  "/admin/support/parallel-calibrations",
  "/admin/distribution",
  "/admin/storage",
  "/admin/backups",
  "/admin/settings",
]);

const staffRoles = ["admin", "editor"] as const;

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const scope = adminTaskScope(pathname);
  const uploadRoute = pathname === "/admin/uploads";
  const intakeRoute = pathname.startsWith("/admin/intake/");
  const manualRoute = pathname === "/admin/cataloging/new";
  const editorRoute = /^\/admin\/library\/works\/[^/]+$/.test(pathname);
  const filesRoute = /^\/admin\/library\/works\/[^/]+\/files$/.test(pathname);
  const mediaRoute = pathname === "/admin/media";
  const articleRoute = /^\/admin\/recommendations\/issues\/[^/]+(?:\/preview)?$/.test(pathname);
  const curationRoute = pathname === "/admin/recommendations" && !["home","legacy"].includes(searchParams.get("view")||"");
  const accountsRoute = pathname === "/admin/users";
  const pathRoute = pathname === "/admin/theories/reading-paths" || pathname === "/admin/reading-paths";
  const timelineRoute = pathname === "/admin/theories/timeline";
  const topicRoute = pathname === "/admin/topics" || pathname.startsWith("/admin/topics/");
  const conceptRoute = /^\/admin\/scholars\/[^/]+\/relations$/.test(pathname) || pathname === "/admin/theories" || /^\/admin\/theories\/[^/]+$/.test(pathname) && !["disciplines","subdisciplines","relations","timeline","reading-paths"].includes(pathname.split("/").at(-1)||"");
  const scholarRoute = /^\/admin\/scholars\/[^/]+$/.test(pathname) && !pathname.endsWith("/people");
  const peopleRoute = pathname === "/admin/people" || pathname === "/admin/scholars/people";
  const ledgerRoute = pathname === "/admin/publication" || /^\/admin\/publication\/[^/]+$/.test(pathname) && !pathname.endsWith("/knowledge");
  const indexRoute = pathname === "/admin/processing/semantic-index";
  const mappingRoute = /^\/admin\/library\/assets\/[^/]+\/page-mapping$/.test(pathname);
  const outlineRoute = /^\/admin\/library\/assets\/[^/]+\/outline$/.test(pathname);
  const ocrRoute = /^\/admin\/library\/assets\/[^/]+\/ocr$/.test(pathname);
  const processingRoute = pathname === "/admin/processing" && (!searchParams.get("surface") || ["documents","overview"].includes(searchParams.get("surface")!));
  const compactWorkHeader = accountsRoute || pathRoute || timelineRoute || topicRoute || conceptRoute || scholarRoute || peopleRoute || ledgerRoute || uploadRoute || intakeRoute || filesRoute || mediaRoute || ocrRoute || outlineRoute || mappingRoute || indexRoute || curationRoute || articleRoute;
  const brandReference = accountsRoute ? "admin-accounts" : pathRoute ? "admin-path" : timelineRoute ? "admin-timeline" : topicRoute ? "admin-topic" : conceptRoute ? "admin-concept" : scholarRoute ? "admin-scholar" : peopleRoute ? "admin-people" : ledgerRoute ? "admin-ledger" : articleRoute ? "admin-article" : curationRoute ? "admin-curation" : indexRoute ? "admin-index" : mappingRoute ? "admin-mapping" : outlineRoute ? "admin-outline" : ocrRoute ? "admin-ocr" : processingRoute ? "admin-processing" : mediaRoute ? "admin-media" : filesRoute ? "admin-files" : editorRoute ? "admin-editor" : manualRoute ? "admin-manual" : intakeRoute ? "admin-intake" : uploadRoute ? "admin-upload" : "admin";
  const returnHref = safeAdminHref(searchParams.get("return_to"), "");
  const curationReturn = returnHref && new URL(returnHref, "https://admin.invalid");
  const returnToCuration = curationReturn && curationReturn.pathname === "/admin/review" && curationReturn.searchParams.get("workspace") === "curation";
  const returnToToday = curationReturn && curationReturn.pathname === "/admin";
  const returnToSearch = curationReturn && curationReturn.pathname === "/admin/search";
  const focusMode = false;
  const [open, setOpen] = useState(false);
  const [expandedNavigation,setExpandedNavigation]=useState("");
  const [searchOpen, setSearchOpen] = useState(false);
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
    const path = href.split(/[?#]/)[0];
    const key = Object.keys(routeCapabilities).sort((a, b) => b.length - a.length).find(route => path === route || path.startsWith(`${route}/`));
    const required = routeCapabilities[href] ?? (key ? routeCapabilities[key] : undefined);
    if (!required) return true;
    return required.some((capability) => capabilities.has(capability));
  }

  if ((/^\/admin\/recommendations\/issues\/[0-9a-f-]+\/preview$/i.test(pathname) || /^\/admin\/preview\/works\/[0-9a-f-]+$/i.test(pathname) || /^\/admin\/preview\/knowledge\/(scholar|topic|discipline|subdiscipline|reading_path|theory|concept|debate|research_problem)\/[0-9a-f-]+$/i.test(pathname)) && searchParams.get("frame") === "1" && searchParams.get("review") !== "1" && canViewRoute(pathname)) {
    return <AdminSessionContext.Provider value={user}><div key={String(user.id)}>{children}</div></AdminSessionContext.Provider>;
  }
  return (
    <AdminSessionContext.Provider value={user}>
    <div className={`admin-shell stl4-admin-shell ${focusMode ? "focus-mode" : ""}`} data-admin-surface={accountsRoute ? "accounts" : pathRoute ? "path" : timelineRoute ? "timeline" : topicRoute ? "topic" : conceptRoute ? "concept" : scholarRoute ? "scholar" : peopleRoute ? "people" : ledgerRoute ? "ledger" : articleRoute ? "article" : curationRoute ? "curation" : indexRoute ? "index" : mappingRoute ? "mapping" : outlineRoute ? "outline" : ocrRoute ? "ocr" : processingRoute ? "processing" : mediaRoute ? "media" : filesRoute ? "files" : editorRoute ? "editor" : manualRoute ? "manual" : intakeRoute ? "intake" : uploadRoute ? "upload" : undefined}>
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
        <Link className="admin-logo" href="/" prefetch={false}><Wordmark reference={brandReference} />{articleRoute?<span className="stl4-selection-brand"><Wordmark reference="admin-selection"/></span>:null}{articleRoute?<span className="stl4-publication-brand"><Wordmark reference="admin-publication"/></span>:null}<span className="stl4-assistant-brand"><Wordmark reference="admin-assistant" /></span></Link>
        <button ref={closeButtonRef} className="admin-mobile-close" type="button" aria-label="关闭后台菜单" onClick={closeNavigation}><X size={19} /></button>
        <nav aria-label="管理工作区">
          {navigationGroups.map(group => <section className="stl4-nav-group" key={group.label} aria-label={group.label}><h2>{group.label}</h2>{group.entries.map(entry => {
            const active = (articleRoute || scholarRoute || timelineRoute || pathRoute ? "/admin/content" : ocrRoute || outlineRoute || mappingRoute || indexRoute ? "/admin/processing" : navigationHref(pathname)) === entry.href;
            const allowed = canViewRoute(entry.href);
            return <div className="admin-nav-section" key={entry.href}>
              {allowed ? <Link className={`admin-nav-primary ${active ? "active" : ""}`} aria-current={active ? "page" : undefined} href={entry.href} prefetch={false} onClick={closeNavigation}><entry.Icon size={17} /><span>{entry.title}</span>{active && entry.children.length && !peopleRoute && !scholarRoute && !conceptRoute && !topicRoute && !timelineRoute && !pathRoute ? <ChevronDown size={13} /> : null}</Link> : <span className="stl4-nav-locked" aria-disabled="true"><entry.Icon size={17} /><span>{entry.title}</span><LockKeyhole size={12} /></span>}
              {active && allowed && entry.children.length && (peopleRoute||scholarRoute||conceptRoute||topicRoute||timelineRoute||pathRoute)?<button className="stl4-subnav-toggle" type="button" aria-label={"展开或收起"+entry.title+"子页面"} aria-expanded={expandedNavigation===entry.href} onClick={()=>setExpandedNavigation(value=>value===entry.href?"":entry.href)}><ChevronDown size={12}/></button>:null}{active && allowed && entry.children.length && (!(peopleRoute||scholarRoute||conceptRoute||topicRoute||timelineRoute||pathRoute)||expandedNavigation===entry.href) ? <div className="admin-nav-children">{entry.children.filter(([href]) => canViewRoute(href)).map(([href, title]) => <Link key={href} href={href} prefetch={false} onClick={closeNavigation} aria-current={`${pathname}${searchParams.size ? `?${searchParams}` : ""}` === href ? "page" : undefined}>{title}</Link>)}</div> : null}
            </div>;
          })}</section>)}
        </nav>
        <footer><Link className="stl4-admin-help" href="/help"><CircleHelp size={17} />帮助</Link><span className="sr-only">{ADMIN_VERSION_LABEL}</span></footer>
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
          <Link className="stl4-mobile-brand" href="/admin" aria-label="管理首页"><Wordmark reference={brandReference} />{articleRoute?<span className="stl4-selection-brand"><Wordmark reference="admin-selection"/></span>:null}{articleRoute?<span className="stl4-publication-brand"><Wordmark reference="admin-publication"/></span>:null}<span className="stl4-assistant-brand"><Wordmark reference="admin-assistant" /></span></Link><span className="sr-only">{scope.title}</span>
          <button className="stl4-mobile-search-toggle" type="button" aria-label="打开后台搜索" aria-controls="admin-global-search" aria-expanded={searchOpen} onClick={() => setSearchOpen(value => !value)}><Search size={18} /></button>
          <form action="/admin/search" id="admin-global-search" className={`stl4-admin-search ${searchOpen ? "is-open" : ""}`} key={pathname === "/admin/search" ? searchParams.get("q") || "" : pathname}>
            <label><Search size={15} /><input type="search" name="q" defaultValue={pathname === "/admin/search" ? searchParams.get("q") || "" : ""} maxLength={200} placeholder="搜索书名、作者、主题、任务编号…" aria-label="搜索后台书名、作者、主题或任务编号" /></label>
            <button className="stl4-search-submit" type="submit">搜索</button>
          </form>
          {!compactWorkHeader ? <AdminWorkNotices key={String(user.id)} /> : null}
          <ThemeToggle />
          <details className="stl4-admin-account" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}><summary aria-label="账户菜单"><span>{user.display_name.slice(0, 1)}</span><ChevronDown size={13} /></summary><div><strong>{user.display_name}</strong><small>{user.role === "admin" ? "管理员" : "编辑"}</small>{compactWorkHeader || manualRoute ? <><Link href="/admin/search">搜索工作与资料</Link><Link href="/admin/review">待办与复核</Link><span className={manualRoute ? "stl4-manual-account-notices" : undefined}><AdminWorkNotices key={String(user.id)} /></span></> : null}<Link href="/account">读者中心与账户</Link><Link href="/">返回前台</Link></div></details>
        </header> : null}
        <div className="admin-content" key={String(user.id)}>{returnToCuration ? <Link className="admin-curation-return" href={returnHref} prefetch={false}>‹ 返回策展草稿</Link> : null}{returnToToday ? <Link className="admin-curation-return" href={returnHref} prefetch={false}>‹ 返回今日工作</Link> : null}{returnToSearch ? <Link className="admin-curation-return" href={returnHref} prefetch={false}>‹ 返回搜索结果</Link> : null}{canViewRoute(pathname) ? children : <section className="stl4-admin-denied" role="alert"><LockKeyhole size={28} /><h1>当前账户没有此项管理权限</h1><p>你可以返回今日工作，继续处理有权访问的条目。</p><Link href="/admin">返回今日工作</Link><Link href="/feedback?category=usage">申请权限</Link></section>}</div>
      </div>
      <nav className="stl4-admin-mobile-nav" aria-label="移动端管理导航" inert={compactNavigation && open}>{navigationGroups[0].entries.map(entry => canViewRoute(entry.href) ? <Link href={entry.href} key={entry.href} prefetch={false} aria-current={(ocrRoute || outlineRoute || mappingRoute || indexRoute ? "/admin/processing" : navigationHref(pathname)) === entry.href ? "page" : undefined}><entry.Icon size={19} /><span>{entry.title}</span></Link> : <span key={entry.href} aria-disabled="true"><LockKeyhole size={17} /><span>{entry.title}</span></span>)}<button type="button" onClick={() => setOpen(true)} aria-controls="admin-navigation" aria-expanded={open}><MoreHorizontal size={20} /><span>更多</span></button></nav>
    </div>
    </AdminSessionContext.Provider>
  );
}
