import Link from "next/link";
import { BookOpen, House, NotebookPen, Search, UserRound } from "lucide-react";
import styles from "./reader-mobile-nav.module.css";

export function ReaderMobileNav({ variant = "research" }: { variant?: "research" | "privacy" | "booklist" }) {
  return <nav className={styles.nav} aria-label="读者快捷导航">
    <Link href="/"><House size={20}/><span>首页</span></Link>
    <Link href="/explore"><Search size={20}/><span>探索</span></Link>
    {variant === "research" ? <Link href="/account/research" aria-current="page"><NotebookPen size={20}/><span>研究</span></Link> : null}
    <Link href="/account/collections" aria-current={variant === "booklist" ? "page" : undefined}><BookOpen size={20}/><span>{variant === "privacy" ? "书架" : "书单"}</span></Link>
    {variant === "booklist" ? <Link href="/account/notes"><NotebookPen size={20}/><span>笔记</span></Link> : null}
    <Link href="/account" aria-current={variant === "privacy" ? "page" : undefined}><UserRound size={20}/><span>我的</span></Link>
  </nav>;
}
