import Link from "next/link";
import { loadSiteConfig } from "@/lib/server-api";

export async function SiteFooter() {
  const config = await loadSiteConfig();
  return (
    <footer className="site-footer">
      <strong>{config.site_name}</strong>
      <nav aria-label="页脚导航">
        <Link href="/about" prefetch={false}>关于</Link>
        <Link href="/login" prefetch={false}>读者登录</Link>
        <Link href="/account" prefetch={false}>读者中心</Link>
      </nav>
      <p>{config.copyright_text}</p>
    </footer>
  );
}
