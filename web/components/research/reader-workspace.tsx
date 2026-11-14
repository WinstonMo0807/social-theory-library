"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight, BookOpen, CalendarDays, ChevronDown, CircleUserRound, Folder, LayoutDashboard, LockKeyhole, PanelLeftClose, PanelLeftOpen, Plus, Quote, Rss, Search, Settings, StickyNote, Users, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { usePublicSession } from "@/components/public-session-provider";

const sections = [
  { id: "overview", label: "概览", icon: LayoutDashboard, href: "/account", children: [["/account", "继续阅读与研究"], ["/account?view=archive", "我的资料"], ["/account?section=history", "阅读历史"]] },
  { id: "research", label: "我的研究", icon: Folder, href: "/account/research", children: [["/account/research", "研究列表"], ["/explore/opinions", "开始新的研究"]] },
  { id: "notes", label: "笔记与摘录", icon: StickyNote, href: "/account/notes", children: [["/account/notes", "全部记录"], ["/account/notes?kind=note", "笔记"], ["/account/notes?kind=bookmark", "书签"], ["/account/notes?kind=excerpt", "高亮与划线"], ["/account/confirmed-notes", "已确认笔记"]] },
  { id: "citation", label: "引文体检", icon: Quote, href: "/account/citation-audits", children: [["/account/citation-audits", "稿件与报告"]] },
  { id: "plans", label: "阅读计划", icon: CalendarDays, href: "/account/plans", children: [["/account/plans", "我的计划"]] },
  { id: "lists", label: "书单与收藏", icon: BookOpen, href: "/account/collections", children: [["/account/collections", "我的书单"], ["/account?section=saved", "我的收藏"]] },
  { id: "sources", label: "来源订阅", icon: Rss, href: "/account/source-updates", children: [["/account/source-updates", "来源变化与订阅"]] },
  { id: "sharing", label: "分享与小组", icon: Users, href: "/account/sharing", children: [["/account/sharing", "分享记录"], ["/account/sharing/new", "新建分享"], ["/account/groups", "我的小组"], ["/account?section=submissions", "荐书投稿"]] },
  { id: "settings", label: "账户设置", icon: Settings, href: "/account?section=settings", children: [["/account?section=settings", "资料与外观"], ["/account/settings/privacy", "隐私与授权"], ["/account/settings/privacy/export", "导出与删除"]] },
];

export function ReaderWorkspace({ children }: { children: ReactNode }) {
  const pathname = usePathname(), params = useSearchParams(), { state } = usePublicSession();
  const section = params.get("section"), query = params.toString(), current = `${pathname}${query ? `?${query}` : ""}`;
  const groupId = pathname.includes("citation-audits") ? "citation" : pathname.includes("research") ? "research" : /\/(notes|confirmed-notes)(\/|$)/.test(pathname) ? "notes" : pathname.includes("plans") ? "plans" : pathname.includes("collections") || section === "saved" || section === "lists" ? "lists" : pathname.includes("source-updates") ? "sources" : /\/(sharing|groups)(\/|$)/.test(pathname) || section === "submissions" ? "sharing" : pathname.includes("settings") || section === "settings" ? "settings" : "overview";
  const active = sections.find(item => item.id === groupId)!;
  const [collapsed, setCollapsed] = useState(false), [searchOpen, setSearchOpen] = useState(false), [term, setTerm] = useState("");
  const searchInput = useRef<HTMLInputElement>(null), root = useRef<HTMLDivElement>(null);
  const keyboard = useRef(false);
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && !event.isComposing && !document.querySelector("dialog[open]")) { event.preventDefault(); keyboard.current = true; setSearchOpen(true); }
    }
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, []);
  useEffect(() => {
    const body = root.current?.querySelector<HTMLElement>(".reader-workspace-body");
    if (!body || keyboard.current || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const animation = body.animate([{ opacity: .65, transform: "translateY(4px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 180, easing: "cubic-bezier(.22,1,.36,1)" });
    return () => animation.cancel();
  }, [pathname, section]);
  const options = sections.flatMap(item => item.children).filter(([, label]) => !term || label.includes(term));
  const exactCurrent = (href: string) => href === current || href === pathname && !params.has("section") && !params.has("view") && !params.has("kind");
  return <div ref={root} className="reader-workspace" data-reader-section={groupId} data-collapsed={collapsed || undefined} onPointerDownCapture={() => { keyboard.current = false; if (root.current) root.current.dataset.input = "pointer"; }} onKeyDownCapture={() => { keyboard.current = true; if (root.current) root.current.dataset.input = "keyboard"; }}>
    <aside className="reader-workspace-sidebar"><div className="reader-workspace-brand"><Link href="/account" prefetch={false}>读者中心</Link><button type="button" onClick={() => setCollapsed(value => !value)} aria-label={collapsed ? "展开栏目导航" : "收起栏目导航"} aria-expanded={!collapsed}>{collapsed ? <PanelLeftOpen size={18}/> : <PanelLeftClose size={18}/>}</button></div><p className="reader-workspace-private"><LockKeyhole size={13}/>仅本人可见</p>
      <button className="reader-workspace-search" aria-label="查找资料或页面" type="button" onClick={() => { setTerm(""); setSearchOpen(true); }}><Search size={17}/><span>查找资料或页面</span><kbd>⌘ / Ctrl K</kbd></button>
      <nav className="reader-workspace-nav" aria-label="读者中心栏目">{sections.map(item => { const Icon = item.icon; return <Link key={item.id} href={item.href} prefetch={false} aria-label={item.label} title={collapsed ? item.label : undefined} aria-current={active.id === item.id ? "page" : undefined}><Icon size={19} strokeWidth={1.65}/><span>{item.label}</span><ChevronDown className="reader-nav-indicator" size={13}/></Link>; })}</nav>
      <div className="reader-workspace-profile"><CircleUserRound size={24}/><div><strong>{state.status === "authenticated" ? state.user?.display_name || "读者" : "读者中心"}</strong><Link href="/account?section=settings" prefetch={false}>资料与设置</Link></div></div>
    </aside>
    <div className="reader-workspace-main"><div className="reader-workspace-toolbar"><nav aria-label="当前栏目"><Link href="/account" prefetch={false}>读者中心</Link><span>/</span><strong>{active.label}</strong></nav><div><button type="button" aria-label="查找私人资料" onClick={() => { setTerm(""); setSearchOpen(true); }}><Search size={18}/></button><details data-action-menu className="reader-workspace-create"><summary><Plus size={17}/><span>新建</span><ChevronDown size={13}/></summary><div data-menu-panel><Link href="/explore/opinions" prefetch={false}>开始研究</Link><Link href="/library" prefetch={false}>从书中记笔记</Link><Link href="/account/plans" prefetch={false}>制定阅读计划</Link><Link href="/account/citation-audits" prefetch={false}>检查一份稿件</Link></div></details></div></div>
      <nav className="reader-workspace-subnav" aria-label="当前栏目页面">{active.children.map(([href, label]) => <Link key={href} href={href} prefetch={false} aria-current={exactCurrent(href) ? "page" : undefined}>{label}</Link>)}</nav>
      <div className="reader-workspace-body">{children}</div>
    </div>
    <Dialog open={searchOpen} onRequestClose={() => setSearchOpen(false)} initialFocusRef={searchInput} className="reader-workspace-command" aria-labelledby="reader-command-title" data-keyboard={keyboard.current || undefined}>
      <header><h2 id="reader-command-title">查找与前往</h2><button type="button" aria-label="关闭查找" onClick={() => setSearchOpen(false)}><X size={20}/></button></header>
      <form action="/account" role="search" aria-label="查找私人资料"><input type="hidden" name="view" value="archive"/><Search size={20}/><input ref={searchInput} name="q" value={term} onChange={event => setTerm(event.target.value)} maxLength={180} placeholder="资料关键词，或页面名称…" aria-label="查找资料关键词"/><button type="submit">查找资料 <ArrowRight size={16}/></button></form>
      <nav aria-label="快速前往">{options.map(([href, label]) => <Link key={href} href={href} prefetch={false} onClick={() => setSearchOpen(false)}><span>{label}</span><ArrowRight size={15}/></Link>)}</nav>
      <p>私人资料仅在你的账户内查找。</p>
    </Dialog>
  </div>;
}
