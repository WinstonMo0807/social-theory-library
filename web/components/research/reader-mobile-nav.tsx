import Link from "next/link";
import { Bell, BookOpen, House, Menu, NotebookPen, Search, UserRound } from "lucide-react";
import styles from "./reader-mobile-nav.module.css";

export function ReaderMobileNav({ variant = "research" }: { variant?: "research" | "privacy" | "booklist" | "memory" | "memory-review" }) {
  if(variant==="memory"||variant==="memory-review") return <nav className={styles.nav} aria-label="读者快捷导航"><Link href="/home"><House size={20}/><span>首页</span></Link><Link href="/explore"><Search size={20}/><span>书库检索</span></Link><Link href="/account/confirmed-notes" aria-current="page"><NotebookPen size={20}/><span>{variant==="memory"?"读者中心":"我的笔记"}</span></Link><Link href="/account/sharing?tab=notices"><Bell size={20}/><span>通知</span></Link><Link href="/account"><Menu size={20}/><span>更多</span></Link></nav>;
  return <nav className={styles.nav} aria-label="读者快捷导航">
    <Link href="/home"><House size={20}/><span>首页</span></Link>
    <Link href="/explore"><Search size={20}/><span>书库检索</span></Link>
    {variant === "research" ? <Link href="/account/research" aria-current="page"><NotebookPen size={20}/><span>研究</span></Link> : null}
    <Link href="/account/collections" aria-current={variant === "booklist" ? "page" : undefined}><BookOpen size={20}/><span>{variant === "privacy" ? "书架" : "书单"}</span></Link>
    {variant === "booklist" ? <Link href="/account/notes"><NotebookPen size={20}/><span>笔记</span></Link> : null}
    <Link href="/account" aria-current={variant === "privacy" ? "page" : undefined}><UserRound size={20}/><span>我的</span></Link>
  </nav>;
}
