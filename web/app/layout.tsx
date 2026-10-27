import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import "./editorial-v2.css";
import "./editorial-workspaces.css";
import "../styles/features/home/home-v307.css";
import "../styles/features/admin/fixed-page-editor.css";
import "../styles/features/admin/workspace-v307.css";
import "../styles/features/admin/evidence-curation.css";
import "../styles/knowledge-v307.css";
import "../styles/features/home/home-stl4.css";
import "../styles/tokens/appearance.css";
import "../styles/layout/brand-identity.css";
import { AppearanceProvider } from "@/components/appearance-provider";
import { SiteHeader } from "@/components/site-header";
import { loadSiteChromeConfig } from "@/lib/api/site.server";
import { RouteTransition } from "@/components/route-transition";
import { PublicSessionProvider } from "@/components/public-session-provider";
import { AuthSessionDialog } from "@/components/auth-session-dialog";
import { EvidenceLanguageProvider } from "@/components/evidence-language";

export async function generateMetadata(): Promise<Metadata> {
  const { config } = await loadSiteChromeConfig();
  return {
    title: {
      default: config.site_name,
      template: `%s｜${config.site_name}`,
    },
    description: config.intro_lines.join(" "),
    robots: {
      index: false,
      follow: false,
      noarchive: true,
      googleBot: {
        index: false,
        follow: false,
        noimageindex: true,
      },
    },
    icons: {
      icon: "/favicon.svg",
      shortcut: "/favicon.svg",
    },
  };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { config, unavailable } = await loadSiteChromeConfig();
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <Script src="/runtime-config.js" strategy="beforeInteractive" />
        <Script src="/appearance-init.js" strategy="beforeInteractive" />
      </head>
      <body>
        <PublicSessionProvider>
        <AppearanceProvider>
        <EvidenceLanguageProvider>
          <a className="skip-link" href="#main-content">
            跳到主要内容
          </a>
          <SiteHeader config={config} />
          {unavailable ? <p className="site-config-unavailable" role="status">网站设置暂时无法加载，当前使用默认导航。</p> : null}
          <main id="main-content"><RouteTransition>{children}</RouteTransition></main>
          <AuthSessionDialog />
        </EvidenceLanguageProvider>
        </AppearanceProvider>
        </PublicSessionProvider>
      </body>
    </html>
  );
}
