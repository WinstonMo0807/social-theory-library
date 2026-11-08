import Link from "next/link";
import styles from "./theory-graph.module.css";

export function KnowledgeMapHero({ title = "知识地图与学科目录", description = "在局部关系中找方向，并能从图回到叙事、目录与原文。", focused = false }: { title?: string; description?: string; focused?: boolean }) {
  return <header className={styles.hero}><div>
    <nav aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><Link href="/explore">探索</Link><span>›</span><span>{title}</span></nav>
    <h1>{title}</h1><p>{description}</p>
  </div>{!focused ? <img src="/visual/stl4/graph/hero-final-r2.png" alt="" width={608} height={177} /> : null}</header>;
}
