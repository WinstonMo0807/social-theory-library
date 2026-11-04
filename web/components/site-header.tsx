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
import { confirmUnsavedBeforeAccountChange } from "@/lib/use-unsaved-form";
import { ReaderAccountMenu } from "./reader-account-menu";
import { useActionGuard } from "@/lib/use-action-guard";
import { usePublicNavigationReturn } from "@/lib/public-navigation-return";
import { ActionButton, AsyncStatus } from "./action-feedback";
import { DisplayPreferences } from "./display-preferences";
import { ThemeToggle } from "./theme-toggle";
import { EvidenceLanguageSwitch, useEvidenceLanguage } from "./evidence-language";
import { usePublicSession } from "./public-session-provider";
import { Drawer } from "./ui/dialog";
import { IconButton } from "./ui/controls";
import { BrandImage } from "./brand-image";

export function Wordmark({ config = defaultSiteConfig }: { config?: SiteConfig }) {
  return <BrandImage config={config} />;
}

export function SiteHeader({ config = defaultSiteConfig, preview = false, reader = false, readerReference = "reader", beforeLogout }: { config?: SiteConfig; preview?: boolean; reader?: boolean; readerReference?: "reader" | "reader-outline" | "reader-search" | "reader-notes" | "parallel" | "parallel-manual"; beforeLogout?: () => boolean }) {
  const { t } = useEvidenceLanguage();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const { state: session } = usePublicSession();
  const user = session.status === "authenticated" && session.user ? session.user : null;
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const navigationReturn = usePublicNavigationReturn(`${pathname}${searchParams.size ? `?${searchParams}` : ""}`, menuButtonRef);
  const [menuSearch, setMenuSearch] = useState("");
  const isActive = (href: string) => href === "/" ? pathname === "/" || pathname === "/layout-preview"
    : ["/theories/graph", "/theories/timeline"].includes(pathname) || pathname.startsWith("/theories/reading-paths") ? href === "/explore"
    : href === "/theories" ? /^\/(theories|theory-schools|subdisciplines)(\/|$)/.test(pathname)
    : pathname === href || pathname.startsWith(`${href}/`);
  const navigation = [
    ["/", config.navigation.home],
    ["/explore", config.navigation.explore],
    ["/theories", config.navigation.theory_schools],
    ["/scholars", config.navigation.scholars],
    ["/topics", config.navigation.topics],
    ["/recommendations", "特别策划"],
  ] as const;
  const archiveRoute = pathname === "/account" && searchParams.get("view") === "archive" && !searchParams.has("section");
  const readerCenterRoute = pathname === "/account" && !preview && !archiveRoute;
  const supportRoute = pathname === "/about" || pathname === "/help" || pathname.startsWith("/help/") || pathname === "/feedback";
  const editorialRoute = pathname === "/recommendations" || pathname.startsWith("/recommendations/");
  const editorialDetailRoute = pathname.startsWith("/recommendations/");
  const topicReference = pathname === "/topics" ? searchParams.get("view") === "directory" || ["q", "search", "parent", "discipline", "subdiscipline", "theory", "sort", "page", "layout"].some(key => !!searchParams.get(key)) ? "topic-directory" : "topics" : pathname.startsWith("/topics/") ? "topic-profile" : undefined;
  const scholarReference = pathname === "/scholars" ? searchParams.get("view") === "directory" || ["q", "field", "school", "period", "sort", "page", "layout"].some(key => !!searchParams.get(key)) ? "scholar-directory" : "scholars" : pathname.startsWith("/scholars/") ? "scholar-profile" : undefined;
  const graphRoute = pathname === "/theories/graph";
  const theoryWorkspaceReference = pathname === "/theories/reading-paths" ? "reading-paths" : pathname.startsWith("/theories/reading-paths/") ? "reading-path" : pathname === "/theories/directory" ? "theory-directory" : pathname === "/theories/timeline" || /\/timeline$/.test(pathname) && pathname.startsWith("/theories/nodes/") ? "theory-timeline" : undefined;
  const theoryDetailRoute = pathname.startsWith("/theories/nodes/") && !theoryWorkspaceReference;
  const subdisciplineReference = pathname === "/subdisciplines" ? "subdisciplines" : pathname.startsWith("/subdisciplines/") ? "subdiscipline-detail" : undefined;
  const theoryOverviewRoute = pathname === "/theories" || pathname === "/theory-schools";
  const workRoute = pathname.startsWith("/works/");
  const evidenceRoute = pathname === "/explore/evidence";
  const exploreLandingRoute = pathname === "/explore" && searchParams.size === 0;
  const authRoute = ["/login","/register","/reset-password","/verify-email"].includes(pathname);
  const researchWorkspaceRoute = /^\/account\/research\/[^/]+$/.test(pathname);
  const researchAnalysisReference=/^\/account\/research\/[^/]+\/compare$/.test(pathname)?"research-compare":/^\/account\/research\/[^/]+\/counter-evidence$/.test(pathname)?"research-counter":undefined;
  const readingPlanRoute=pathname==="/account/plans"||/^\/account\/plans\/[^/]+$/.test(pathname);
  const citationDetailReference=/^\/account\/citation-audits\/[^/]+\/parse$/.test(pathname)?"citation-parse":/^\/account\/citation-audits\/[^/]+\/issues\/[^/]+$/.test(pathname)?"citation-issue":/^\/account\/citation-audits\/[^/]+$/.test(pathname)?"citation-report":undefined;
  const notebookRoute=pathname==="/account/notes"||pathname.startsWith("/account/notes/");
  const booklistsRoute=pathname==="/account/collections"||pathname.startsWith("/account/collections/");
  const replayRoute=/^\/account\/research\/[^/]+\/history$/.test(pathname);
  const privacyReference=pathname==="/account/settings/privacy"?(searchParams.get("view")==="status"?"privacy-status":"privacy"):pathname==="/account/settings/privacy/export"?"privacy-export":undefined;
  const brandReference = privacyReference?privacyReference:replayRoute?"research-replay":booklistsRoute?"booklists":notebookRoute?"notebook":citationDetailReference?citationDetailReference:pathname==="/account/confirmed-notes"?"confirmed-notes":readingPlanRoute?"reading-plan": researchAnalysisReference ? researchAnalysisReference : researchWorkspaceRoute ? "research-workspace" : authRoute ? pathname === "/reset-password" ? "auth-recovery" : "auth" : archiveRoute ? "reader-archive" : readerCenterRoute ? "reader-center" : pathname === "/account/research" ? "research-directory" : pathname === "/account/sharing/new" ? "sharing" : reader ? readerReference : editorialRoute ? (["q","topic","theory","kind","curator","year_from","year_to","page","layout"].some(key => !!searchParams.get(key)) ? "editorial-directory" : "editorial-home") : topicReference ? topicReference : scholarReference ? scholarReference : theoryWorkspaceReference ? theoryWorkspaceReference : subdisciplineReference ? subdisciplineReference : theoryOverviewRoute ? "theory-overview" : pathname === "/about" ? "about" : pathname.startsWith("/help/") ? "article" : supportRoute ? "support" : exploreLandingRoute ? "explore" : pathname === "/explore/original" ? "catalog" : pathname === "/explore/opinions" ? "opinion" : evidenceRoute ? "evidence" : undefined;
  const readerNavigation = [
    ["/account/research", "我的研究"], ["/account/notes", "笔记"], ["/account/plans", "阅读计划"],
    ["/account/collections", "书单"], ["/account/citation-audits", "引文体检"], ["/account/confirmed-notes", "已确认笔记"],
  ];
  const headerNavigation = supportRoute ? [...navigation, ["/about", "关于"]] : navigation;

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
    if (beforeLogout ? !beforeLogout() : !confirmUnsavedBeforeAccountChange()) return;
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
      data-stl-research-workspace={researchWorkspaceRoute||undefined}
      data-stl-research-analysis={researchAnalysisReference}
      data-stl-reading-plan={readingPlanRoute||undefined}
      data-stl-citation-detail={citationDetailReference}
      data-stl-notebook={notebookRoute||undefined}
      data-stl-booklists={booklistsRoute||undefined}
      data-stl-replay={replayRoute||undefined}
      data-stl-privacy={privacyReference}
      data-stl-confirmed-notes={pathname==="/account/confirmed-notes"||undefined}
      data-stl-auth={authRoute ? pathname === "/reset-password" ? "recovery" : "true" : undefined}
      data-stl-home={pathname === "/" || pathname === "/layout-preview" || preview ? "true" : undefined}
      data-stl-sharing={pathname === "/account/sharing/new" ? "true" : undefined}
      data-stl-account={readerCenterRoute ? "true" : archiveRoute ? "archive" : undefined}
      data-stl-research={pathname === "/account/research" ? "true" : undefined}
      data-stl-editorial={editorialRoute ? editorialDetailRoute ? "detail" : "directory" : undefined}
      data-stl-topic={topicReference}
      data-stl-scholar={scholarReference}
      data-stl-map={graphRoute ? "graph" : theoryWorkspaceReference}
      data-stl-theory={theoryDetailRoute ? "detail" : theoryOverviewRoute ? "overview" : subdisciplineReference}
      data-stl-work={workRoute ? "true" : undefined}
      data-stl-reader={reader ? readerReference : undefined}
      data-stl-support={supportRoute ? brandReference : undefined}
      data-stl-explore={exploreLandingRoute ? "landing" : pathname === "/explore/original" ? "catalog" : pathname === "/explore/opinions" ? "opinion" : evidenceRoute ? "evidence" : undefined}
      className="site-header site-masthead"
      data-ui-scope="stl4"
    >
      <Link className="logo-link" href="/" prefetch={false}>
        <Wordmark config={config} />
      </Link>
      <nav className="desktop-nav" aria-label={t("主导航")}>
        {headerNavigation.map(([href, label]) => {
          const active = href === "/about" && supportRoute ? true : href.includes("?") ? `${pathname}?${searchParams}` === href : isActive(href);
          return (
            <Link
              aria-current={active ? "page" : undefined}
              className={active ? "active" : ""}
              href={href}
              key={href}
              prefetch={false}
            >
              {t(evidenceRoute && href === "/theories" ? "理论" : label)}
            </Link>
          );
        })}
      </nav>
      <div className="header-actions">
        <Link className="icon-button header-search" href="/explore" prefetch={false} aria-label={t(config.navigation.search)}>
          <Search size={18} strokeWidth={1.7} />
        </Link>
        <ThemeToggle />
        <IconButton
          ref={menuButtonRef}
          className={`icon-button menu-button${(readerCenterRoute || archiveRoute) && user ? " reader-account-menu-toggle" : ""}`}
          type="button"
          aria-label={t(open ? "关闭菜单" : "打开菜单")}
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={21} /> : reader && readerReference === "reader-notes" ? <CircleUserRound size={21} /> : <Menu size={21} />}
        </IconButton>
      </div>
      <div className="header-context-actions">
        {pathname.startsWith("/account") && navigationReturn.source ? <Link className="header-return" aria-label={t("返回原页面")} title={t("返回原页面")} href={navigationReturn.source.href} prefetch={false} scroll={false} onClick={navigationReturn.requestReturn}><ArrowLeft size={17} /><span>{t("返回原页面")}</span></Link> : null}
        {evidenceRoute || theoryDetailRoute ? <form className="header-reference-search" action="/explore/original"><button type="submit" aria-label={t("搜索馆藏")}><Search size={17} /></button><label className="sr-only" htmlFor="evidence-header-query">{t("搜索书名、作者、概念")}</label><input id="evidence-header-query" name="q" type="search" maxLength={500} placeholder={t("搜索书名、作者、概念…")} /></form> : null}
        {readerCenterRoute ? <nav className="reader-center-nav" aria-label={t("读者中心导航")}>{readerNavigation.map(([href, label]) => <Link key={href} href={href} prefetch={false}>{t(label)}</Link>)}</nav> : null}
        {evidenceRoute ? <EvidenceLanguageSwitch /> : null}
        {evidenceRoute ? <Link className="header-reference-account" href={user ? "/account" : "/login?next=%2Faccount"} onClick={enterAccount} aria-label={t(user ? "读者中心" : "读者登录")}><CircleUserRound size={24} strokeWidth={1.6} /></Link> : null}
        {(readerCenterRoute || archiveRoute) && user ? <ReaderAccountMenu key={user.id} user={user} onLogout={logout} onPreferences={() => setOpen(true)} pending={pendingAction === "logout"} error={logoutError} /> : null}
      </div>
      {logoutError && !open ? <p className="site-navigation-returned" role="alert">{logoutError}</p> : null}
      {navigationReturn.returned ? <p className="site-navigation-returned" role="status">{t("已返回先前页面")}</p> : null}
      {open ? (
        <Drawer open={open} onRequestClose={closeMenu} initialFocusRef={closeButtonRef} className="site-menu-layer" id="site-menu" aria-labelledby="site-menu-title">
          <button className="site-menu-backdrop" type="button" aria-label={t("关闭菜单")} onClick={closeMenu} />
          <aside className="site-menu-panel" aria-labelledby="site-menu-title">
            <header className="site-menu-head">
              <Link href="/" prefetch={false} onClick={closeMenu}><Wordmark config={config} /><span className="sr-only" id="site-menu-title">{t("书库导航")}</span></Link>
              <IconButton ref={closeButtonRef} aria-label={t("关闭菜单")} onClick={closeMenu}>
                <X size={25} />
              </IconButton>
            </header>

            <form action="/explore" className="site-menu-search" role="search" aria-label={t("菜单内搜索")} onSubmit={closeMenu}>
              <Search size={16} aria-hidden="true" /><label className="sr-only" htmlFor="menu-search-input">{t("搜索书名、作者、概念、主题")}</label>
              <input id="menu-search-input" type="search" name="q" maxLength={500} value={menuSearch} onChange={event => setMenuSearch(event.target.value)} placeholder={t("搜索书名、作者、概念、主题…")} />
              <button type="submit" aria-label={t("提交菜单搜索")}><ChevronRight size={16} /></button>
            </form>

            <nav className="site-menu-nav" aria-label={t("书库导航")}>
              {navigation.map(([href, label]) => (
                <Link href={href} key={href} prefetch={false} onClick={closeMenu} aria-current={isActive(href) ? "page" : undefined}>
                  <strong>{t(label)}</strong>
                  <ChevronRight size={15} />
                </Link>
              ))}
            </nav>

            <div className="site-menu-tools">
              <div>
                <Link href="/account" prefetch={false} onClick={enterAccount} aria-current={pathname === "/account" && searchParams.get("section") !== "settings" ? "page" : undefined}>
                  <CircleUserRound size={18} />
                  <span><strong>{t("我的资料")}</strong></span><ChevronRight size={15} />
                </Link>
                <Link href="/account?section=settings" prefetch={false} onClick={enterAccount} aria-current={pathname === "/account" && searchParams.get("section") === "settings" ? "page" : undefined}>
                  <Settings size={18} />
                  <span><strong>{t("账户设置")}</strong></span><ChevronRight size={15} />
                </Link>
                {user ? <Link data-auth-full-page href="/login?next=%2Faccount" onClick={closeMenu}><CircleUserRound size={18} /><span><strong>{t("切换账户")}</strong><small>{t("登录另一账户，私人资料不会合并")}</small></span><ChevronRight size={15} /></Link> : null}
                {user?.capabilities?.includes("access_back_office") ? <Link href="/admin" prefetch={false} onClick={closeMenu}><Settings size={18} /><span><strong>{t("管理后台")}</strong></span><ChevronRight size={15} /></Link> : null}
                <Link href="/help" prefetch={false} onClick={closeMenu} aria-current={isActive("/help") ? "page" : undefined}><CircleHelp size={18} /><span><strong>{t("使用帮助")}</strong></span><ChevronRight size={15} /></Link>
                <Link href="/about" prefetch={false} onClick={closeMenu} aria-current={isActive("/about") ? "page" : undefined}><ArrowUpRight size={18} /><span><strong>{t("关于我们")}</strong></span><ChevronRight size={15} /></Link>
                {!user ? (
                  <>
                    <Link href="/login?next=/account" prefetch={false} onClick={enterAccount}>
                      <CircleUserRound size={18} />
                      <span><strong>{t("登录")}</strong></span>
                    </Link>
                    <Link href="/register" prefetch={false} onClick={enterAccount}>
                      <UserPlus size={18} />
                      <span><strong>{t("注册")}</strong></span>
                    </Link>
                  </>
                ) : (
                  <ActionButton
                    type="button"
                    state={pendingAction === "logout" ? "pending" : logoutError ? "error" : "idle"}
                    pendingLabel={t("正在退出")}
                    errorLabel={t("退出失败，请重试")}
                    onClick={() => void logout()}
                  >
                    <LogOut size={18} />
                    <span><strong>{t("退出登录")}</strong><small>{user.display_name}</small></span>
                  </ActionButton>
                )}
              </div>
            </div>

            {logoutError ? <AsyncStatus state="error" message={logoutError} /> : null}

            <div className="site-menu-appearance"><DisplayPreferences /></div>

            <footer className="site-menu-foot">
              <span>{user ? `${user.display_name} · ${user.role === "reader" ? t("读者") : t("馆员")}` : t("访客可直接阅读、下载、复制与引用")}</span>
              <Link href="/about" prefetch={false} onClick={closeMenu}>{t("关于书库")}<ArrowUpRight size={14} /></Link>
            </footer>
          </aside>
        </Drawer>
      ) : null}
    </header>
  );
}
