import Link from "next/link";

export default function NotFound() {
  return (
    <section className="route-state-page">
      <span className="eyebrow">页面不存在</span>
      <h1>没有找到这个页面</h1>
      <p>它可能已经下架、改名，或者链接不完整。</p>
      <div className="route-state-actions">
        <Link className="button primary" href="/explore">搜索馆藏</Link>
        <Link className="button secondary" href="/">返回首页</Link>
      </div>
    </section>
  );
}
