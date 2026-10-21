"use client";
import Link from "next/link";
import styles from "./topic.module.css";
export function TopicLoadError({ slug }: { slug: string }) { return <main className={styles.page}><section role="alert" className={styles.error}><h1>主题资料暂时无法读取</h1><p>请求未完成，当前筛选地址已保留，不能据此判断主题是否缺少内容。</p><button type="button" className={styles.primaryButton} onClick={() => window.location.reload()}>重试读取</button><Link href={`/topics/${encodeURIComponent(slug)}`}>返回主题导读</Link><Link href="/topics?view=directory">返回主题索引</Link></section></main>; }
