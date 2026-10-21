"use client";
import Link from "next/link";
import styles from "./scholar.module.css";

export function ScholarLoadError({ slug }: { slug: string }) {
  return <main className={styles.page}><section role="alert" className={styles.error}><h1>学者资料暂时无法读取</h1><p>当前请求没有完成，不能据此判断此学者是否缺少资料。筛选地址已保留。</p><button type="button" onClick={() => window.location.reload()}>重试读取</button><Link href={`/scholars/${encodeURIComponent(slug)}`}>返回学者概览</Link><Link href="/scholars?view=directory">返回学者索引</Link></section></main>;
}
