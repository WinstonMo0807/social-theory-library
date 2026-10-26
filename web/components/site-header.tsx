"use client";

import Link from "next/link";
import Image from "next/image";
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
import { usePublicSession } from "./public-session-provider";
import { Drawer } from "./ui/dialog";
import { IconButton } from "./ui/controls";

export function LibraryMark({ className = "" }: { className?: string }) {
  return <Image aria-hidden="true" alt="" className={`brand-mark ${className}`.trim()}
    src="/brand/stl-mark-final-r2.png" width={61} height={45} unoptimized />;
}

const referenceBrandSize = { "admin-ledger": [178,46], "admin-publication": [184,46], "admin-selection": [195,51], "admin-article": [193,49], "admin-curation": [187,47], "admin-index": [179,47], "admin-mapping": [183,48], "admin-outline": [186,47], "admin-ocr": [206,55], "admin-processing": [183,48], "admin-media": [188,48], "admin-assistant": [198,51], "admin-files": [195,49], "admin-editor": [195,48], "admin-manual": [193,48], "admin-intake": [187,51], "admin-upload": [188,48], admin: [205,52], "editorial-directory": [224,37], "editorial-article": [195,45], "editorial-exhibition": [219,47], "editorial-exhibit": [218,45], topics: [264,57], "topic-directory": [242,35], "topic-profile": [210,47], scholars: [262,60], "scholar-directory": [180,40], "scholar-profile": [226,31], "reading-paths": [175,45], "reading-path": [233,36], graph: [112,38], "graph-topic": [147,52], "graph-scholar": [120,39], "theory-directory": [246,53], "theory-timeline": [172,34], "theory-concept": [235,35], "theory-tradition": [132,35], subdisciplines: [245,55], "subdiscipline-detail": [204,53], "theory-overview": [241,54], about: [195,60], support: [222,42], article: [191,44], explore: [264,59], catalog: [293,44], opinion: [116,38], evidence: [220,54], work: [121,42], journal: [247,38], "work-readable": [182,31], reader: [133,45], "reader-outline": [216,47], "reader-search": [232,42], "reader-notes": [242,40], parallel: [264,36], "parallel-manual": [264,37] } as const;
export function Wordmark({ config = defaultSiteConfig, home = false, reference }: { config?: SiteConfig; home?: boolean; reference?: keyof typeof referenceBrandSize }) {
  if (reference) return <picture className="brand-reference-lockup" data-brand-variant={reference}><source media="(max-width: 700px)" srcSet={`/brand/stl-lockup-${reference}-mobile-final-r2.png`} /><Image src={`/brand/stl-lockup-${reference}-desktop-final-r2.png`} alt={config.site_name} width={referenceBrandSize[reference][0]} height={referenceBrandSize[reference][1]} unoptimized /></picture>;
  return (
    <span className="brand-lockup" aria-label={config.site_name}>
      <LibraryMark />
      <span className="brand-type" aria-hidden="true"><picture className="brand-reference-type"><source media="(max-width: 700px)" srcSet="/brand/stl-wordmark-mobile-final-r2.png" /><Image src={home ? "/brand/stl-wordmark-home-final-r2.png" : "/brand/stl-wordmark-desktop-final-r2.png"} alt="" width={home ? 192 : 259} height={home ? 38 : 45} unoptimized /></picture><span className="wordmark">
        {config.wordmark_lines.map((line) => (
          <span key={line}>{line}</span>
        ))}
      </span><span className="brand-name">{config.site_name}</span></span>
    </span>
  );
}

export function SiteHeader({ config = defaultSiteConfig, preview = false, reader = false, readerReference = "reader", beforeLogout }: { config?: SiteConfig; preview?: boolean; reader?: boolean; readerReference?: "reader" | "reader-outline" | "reader-search" | "reader-notes" | "parallel" | "parallel-manual"; beforeLogout?: () => boolean }) {
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
  const isActive = (href: string) => href === "/" ? pathname === "/"
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
  const readerCenterRoute = pathname === "/account" && !preview;
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
  const brandReference = reader ? readerReference : editorialRoute ? "editorial-directory" : topicReference ? topicReference : scholarReference ? scholarReference : theoryWorkspaceReference ? theoryWorkspaceReference : subdisciplineReference ? subdisciplineReference : theoryOverviewRoute ? "theory-overview" : pathname === "/about" ? "about" : pathname.startsWith("/help/") ? "article" : supportRoute ? "support" : exploreLandingRoute ? "explore" : pathname === "/explore/original" ? "catalog" : pathname === "/explore/opinions" ? "opinion" : evidenceRoute ? "evidence" : undefined;
  const headerNavigation = readerCenterRoute ? [
    ["/account/research", "我的研究"], ["/account/notes", "笔记"], ["/account/plans", "阅读计划"],
    ["/account/collections", "书单"], ["/account/citation-audits", "引文体检"], ["/account/confirmed-notes", "已确认笔记"],
  ] : supportRoute ? [...navigation, ["/about", "关于"]] : navigation;

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
      data-stl-home={pathname === "/" || preview ? "true" : undefined}
      data-stl-account={readerCenterRoute ? "true" : undefined}
      data-stl-editorial={editorialRoute ? editorialDetailRoute ? "detail" : "directory" : undefined}
      data-stl-topic={topicReference}
      data-stl-scholar={scholarReference}
      data-stl-map={graphRoute ? "graph" : theoryWorkspaceReference}
      data-stl-theory={theoryDetailRoute ? "detail" : theoryOverviewRoute ? "overview" : subdisciplineReference}
      data-stl-work={workRoute ? "true" : undefined}
      data-stl-reader={reader ? readerReference : undefined}
      data-stl-support={supportRoute ? brandReference : undefined}
      data-stl-explore={exploreLandingRoute ? "landing" : pathname === "/explore/original" ? "catalog" : pathname === "/explore/opinions" ? "opinion" : evidenceRoute ? "evidence" : undefined}
      className="site-header"
      data-ui-scope="stl4"
    >
      <Link className="logo-link" href="/" prefetch={false}>
        {editorialDetailRoute ? <span className="brand-editorial-variants"><Wordmark config={config} reference="editorial-article" /><Wordmark config={config} reference="editorial-exhibition" /><Wordmark config={config} reference="editorial-exhibit" /></span> : graphRoute ? <span className="brand-graph-variants"><Wordmark config={config} reference="graph" /><Wordmark config={config} reference="graph-topic" /><Wordmark config={config} reference="graph-scholar" /></span> : theoryDetailRoute ? <span className="brand-theory-variants"><Wordmark config={config} reference="theory-concept" /><Wordmark config={config} reference="theory-tradition" /></span> : workRoute ? <span className="brand-work-variants"><Wordmark config={config} reference="work" /><Wordmark config={config} reference="work-readable" /><Wordmark config={config} reference="journal" /></span> : <Wordmark config={config} home={pathname === "/" || preview} reference={brandReference} />}
      </Link>
      <nav className="desktop-nav" aria-label="主导航">
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
              {evidenceRoute && href === "/theories" ? "理论" : label}
            </Link>
          );
        })}
      </nav>
      <div className="header-actions">
        {pathname.startsWith("/account") && navigationReturn.source ? <Link className="header-return" aria-label="返回原页面" title="返回原页面" href={navigationReturn.source.href} prefetch={false} scroll={false} onClick={navigationReturn.requestReturn}><ArrowLeft size={17} /><span>返回原页面</span></Link> : null}
        {evidenceRoute || theoryDetailRoute ? <form className="header-reference-search" action="/explore/original"><button type="submit" aria-label="搜索馆藏"><Search size={17} /></button><label className="sr-only" htmlFor="evidence-header-query">搜索书名、作者、概念</label><input id="evidence-header-query" name="q" type="search" maxLength={500} placeholder="搜索书名、作者、概念…" /></form> : null}
        <Link className="header-search" href="/explore" prefetch={false} aria-label={config.navigation.search}>
          <Search size={18} strokeWidth={1.7} />
          <span>{config.navigation.search}</span>
        </Link>
        <ThemeToggle />
        {evidenceRoute ? <Link className="header-reference-account" href={user ? "/account" : "/login?next=%2Faccount"} onClick={enterAccount} aria-label={user ? "读者中心" : "读者登录"}><CircleUserRound size={28} strokeWidth={1.6} /></Link> : null}
        {readerCenterRoute && user ? <ReaderAccountMenu key={user.id} user={user} onLogout={logout} onPreferences={() => setOpen(true)} pending={pendingAction === "logout"} error={logoutError} /> : null}
        <IconButton
          ref={menuButtonRef}
          className={`icon-button menu-button${readerCenterRoute && user ? " reader-account-menu-toggle" : ""}`}
          type="button"
          aria-label={open ? "关闭菜单" : "打开菜单"}
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={25} /> : reader && readerReference === "reader-notes" ? <CircleUserRound size={25} /> : <Menu size={25} />}
        </IconButton>
      </div>
      {logoutError && !open ? <p className="site-navigation-returned" role="alert">{logoutError}</p> : null}
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
                {user ? <Link data-auth-full-page href="/login?next=%2Faccount" onClick={closeMenu}><CircleUserRound size={18} /><span><strong>切换账户</strong><small>登录另一账户，私人资料不会合并</small></span><ChevronRight size={15} /></Link> : null}
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
