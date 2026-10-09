import Link from "next/link";
import type { SiteConfig } from "@/lib/site-config";

export function SiteFooterView({ config, preview = false, readingLayout = false }: { config: SiteConfig; preview?: boolean; readingLayout?: boolean }) {
  if (readingLayout) return <footer className="site-footer reading-site-footer"><div><strong>{config.site_name}</strong><span className="reading-footer-wordmark">{config.wordmark_lines.join(" ").toLowerCase()}</span><span className="reading-footer-tagline" aria-hidden="true" /></div><p>{config.copyright_text}</p></footer>;
  return <footer className="site-footer" data-edit-section={preview ? "footer" : undefined}>
    <strong>{config.site_name}</strong><nav aria-label="页脚导航">
      <Link href="/about" prefetch={false}>{config.about_label || "关于"}</Link>
      <Link href="/login" prefetch={false}>读者登录</Link><Link href="/account" prefetch={false}>读者中心</Link>
    </nav><p>{config.copyright_text}</p>
  </footer>;
}
