import Link from "next/link";
import { ArrowRight, Compass } from "lucide-react";
import { topicHref } from "@/lib/api/topics.params";
import type { PublicTopicCard, TopicPage, TopicSearchParams } from "@/lib/api/topics.types";
import styles from "./topic.module.css";

export function TopicImage({ topic }: { topic: PublicTopicCard }) { return topic.hero_image ? <img src={topic.hero_image} alt="" loading="lazy" /> : <span className={styles.imageBlank} aria-label={`${topic.name}暂无主题图片`}><Compass size={32} strokeWidth={1} /></span>; }
export function TopicCard({ topic }: { topic: PublicTopicCard }) {
  return <article className={styles.topicCard} data-topic-id={topic.id}><Link prefetch={false} href={topic.href} className={styles.cardImage} aria-label={`进入${topic.name}`}><TopicImage topic={topic} /></Link><div className={styles.cardBody}><h3><Link prefetch={false} href={topic.href}>{topic.name}</Link></h3><p>{topic.problem_statement || topic.description || "这个主题的内容仍在补充，可查看已公开的关联材料。"}</p>{topic.matched_alias ? <p>别名命中：{topic.matched_alias}</p> : null}{topic.tags.length ? <div className={styles.cardTags}>{topic.tags.map(tag => <span key={tag}>{tag}</span>)}</div> : null}<footer className={styles.cardFooter}><span>相关作品 {topic.work_count} · 学者 {topic.scholar_count}</span><Link prefetch={false} href={topic.href}>进入<ArrowRight size={14} /></Link></footer></div></article>;
}
export function TopicPagination({ page, path, params = {}, label = "主题分页" }: { page: Pick<TopicPage<unknown>, "page" | "total_pages" | "previous" | "next">; path: string; params?: TopicSearchParams; label?: string }) {
  if (!page.previous && !page.next) return null;
  return <nav className={styles.pagination} aria-label={label}>{page.previous ? <Link prefetch={false} href={topicHref(path, params, { page: String(page.page - 1) })}>上一页</Link> : <span>上一页</span>}<span>第 {page.page} / {page.total_pages} 页</span>{page.next ? <Link prefetch={false} href={topicHref(path, params, { page: String(page.page + 1) })}>下一页</Link> : <span>下一页</span>}</nav>;
}
