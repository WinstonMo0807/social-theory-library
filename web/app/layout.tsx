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
// The reference design must follow the legacy editor rules in the cascade.
import "../styles/features/admin/design-v2.css";
import "../styles/features/admin/collections-v2.css";
import "../styles/features/admin/recommendations-design-v2.css";
import "../styles/features/admin/storage-backups.css";
import "../styles/features/admin/operations-v2.css";
import "../styles/features/admin/knowledge-reference.css";
import "../styles/features/admin/taxonomy-reference.css";
import "../styles/features/admin/site-system-reference.css";
import "../styles/features/admin/processing-reference.css";
import { SiteHeader, SiteConfigProvider } from "@/components/site-header";
import { loadSiteConfig } from "@/lib/api/site.server";
import { RouteTransition } from "@/components/route-transition";
import { PublicSessionProvider } from "@/components/public-session-provider";

export async function generateMetadata(): Promise<Metadata> {
  const config = await loadSiteConfig();
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
  const config = await loadSiteConfig();
  return (
    <html lang="zh-CN">
      <head>
        <Script src="/runtime-config.js" strategy="beforeInteractive" />
      </head>
      <body>
        <PublicSessionProvider>
          <a className="skip-link" href="#main-content">
            跳到主要内容
          </a>
          <SiteConfigProvider config={config}><SiteHeader config={config} />
          <main id="main-content"><RouteTransition>{children}</RouteTransition></main>
          </SiteConfigProvider>
        </PublicSessionProvider>
      </body>
    </html>
  );
}
