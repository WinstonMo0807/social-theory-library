import Link from "next/link";
import type { SiteConfig } from "@/lib/site-config";

export function SiteFooterView({ config, preview = false, compact = false, reference }: { config: SiteConfig; preview?: boolean; compact?: boolean; reference?: "about" | "support" | "article" }) {
  if (compact) return <footer className="site-footer site-footer--audit"><nav aria-label="页脚导航"><Link href="/about" prefetch={false}>关于我们</Link><Link href="/help/terms" prefetch={false}>使用条款</Link><Link href="/help/account#site-privacy" prefetch={false}>隐私政策</Link><Link href="/help" prefetch={false}>帮助中心</Link></nav></footer>;
  if (reference) return <footer className={`site-footer site-footer--reference site-footer--${reference}`}><Link href="/" aria-label="社会理论书库首页"><img src={`/brand/stl-lockup-${reference}-desktop-final-r2.png`} alt={config.site_name} width={reference === "support" ? 170 : 160} height={reference === "about" ? 49 : 35} /></Link>{reference !== "article" ? <p>连接思想 · 开放知识 · 服务研究与公众</p> : null}<nav aria-label="页脚导航"><Link href="/about" prefetch={false}>关于我们</Link><Link href="/help/terms" prefetch={false}>使用条款</Link><Link href="/help/account#site-privacy" prefetch={false}>隐私政策</Link><Link href="/feedback" prefetch={false}>联系我们</Link></nav></footer>;
  return <footer className="site-footer" data-edit-section={preview ? "footer" : undefined}>
    <strong>{config.site_name}</strong><nav aria-label="页脚导航">
      <Link href="/about" prefetch={false}>{config.about_label || "关于"}</Link>
      <Link href="/help" prefetch={false}>帮助与支持</Link><Link href="/feedback" prefetch={false}>反馈与建议</Link>
      <Link href="/login" prefetch={false}>读者登录</Link><Link href="/account" prefetch={false}>读者中心</Link>
    </nav><p>{config.copyright_text}</p>
  </footer>;
}
